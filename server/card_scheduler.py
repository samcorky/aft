"""Automatic card scheduler service."""
import os
import threading
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging

from sqlalchemy import func
from database import SessionLocal
from models import Card, ScheduledCard, Comment, ChecklistItem, BoardColumn
from notification_utils import create_notification
from schedule_utils import get_next_run

logger = logging.getLogger(__name__)


class CardScheduler:
    """Manages automatic card creation on a schedule."""
    
    def __init__(self):
        import tempfile
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock_file = Path(tempfile.gettempdir()) / "aft_card_scheduler.lock"
    
    def _is_lock_stale(self) -> bool:
        """Check if existing lock file is stale.
        
        Returns:
            True if lock file is stale and should be removed, False otherwise.
        """
        try:
            import json
            lock_data = json.loads(self.lock_file.read_text())
            
            # Check container ID (hostname in Docker)
            current_container = os.environ.get('HOSTNAME', 'unknown')
            lock_container = lock_data.get('container_id', 'unknown')
            if lock_container != current_container:
                logger.info(f"Lock file from different container: {lock_container} vs {current_container}")
                return True  # Different container = stale
            
            # Check heartbeat age
            last_heartbeat_str = lock_data.get('last_heartbeat')
            if last_heartbeat_str:
                last_heartbeat = datetime.fromisoformat(last_heartbeat_str)
                age_seconds = (datetime.now() - last_heartbeat).total_seconds()
                
                if age_seconds > 300:  # 5 minutes without heartbeat = stale
                    logger.info(f"Lock file heartbeat is stale: {age_seconds:.0f} seconds old")
                    return True
                
                # Lock is fresh and from same container
                logger.info(f"Lock file is active (heartbeat {age_seconds:.0f}s ago, container {lock_container})")
                return False
            
            # No heartbeat in lock file = old format or invalid
            logger.info("Lock file has no heartbeat, considering stale")
            return True
            
        except (json.JSONDecodeError, ValueError, KeyError, FileNotFoundError) as e:
            logger.info(f"Lock file is invalid or corrupted: {e}")
            return True  # Invalid lock file = stale
        except Exception as e:
            logger.warning(f"Error checking lock staleness: {e}")
            return True  # Error reading = assume stale for safety
    
    def _update_heartbeat(self):
        """Update lock file with current timestamp to prove thread is alive."""
        try:
            lock_data = {
                "pid": os.getpid(),
                "container_id": os.environ.get('HOSTNAME', 'unknown'),
                "last_heartbeat": datetime.now().isoformat(),
                "scheduler_type": "card"
            }
            self.lock_file.write_text(json.dumps(lock_data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to update heartbeat: {e}")
    
    def _acquire_lock(self) -> bool:
        """Attempt to acquire the scheduler lock with heartbeat.
        
        Returns:
            bool: True if lock acquired, False otherwise
        """
        try:
            if self.lock_file.exists():
                if self._is_lock_stale():
                    logger.info("Removing stale lock file")
                    self.lock_file.unlink()
                else:
                    return False  # Active lock exists
            
            # Create lock file with heartbeat
            lock_data = {
                "pid": os.getpid(),
                "container_id": os.environ.get('HOSTNAME', 'unknown'),
                "last_heartbeat": datetime.now().isoformat(),
                "scheduler_type": "card"
            }
            
            # Atomic write: write to temp file then rename
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', dir=tempfile.gettempdir(), delete=False) as tf:
                json.dump(lock_data, tf, indent=2)
                temp_path = tf.name
            
            os.rename(temp_path, str(self.lock_file))
            return True
            
        except Exception as e:
            logger.error(f"Error acquiring card scheduler lock: {e}")
            return False
    
    def _release_lock(self):
        """Release the scheduler lock."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception as e:
            logger.error(f"Error releasing card scheduler lock: {str(e)}")
    
    def start(self):
        """Start the card scheduler in a background thread."""
        logger.info("=== Card Scheduler Start Attempt ===")
        logger.info(f"PID: {os.getpid()}, Container: {os.environ.get('HOSTNAME', 'unknown')}")
        
        if self.running:
            logger.warning("Card scheduler is already running in this instance")
            return
        
        if not self._acquire_lock():
            logger.info("Could not acquire card scheduler lock - another instance is active")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info(f"✓ Card scheduler started successfully - PID: {os.getpid()}, Thread ID: {self.thread.ident}")
    
    def stop(self):
        """Stop the card scheduler."""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        
        self._release_lock()
        logger.info("Card scheduler stopped")
    
    def _run(self):
        """Main scheduler loop - runs every minute."""
        logger.info("Card scheduler loop started")
        
        while self.running:
            try:
                # Update heartbeat to prove we're alive
                self._update_heartbeat()
                
                # Check if card scheduler is enabled
                if self._is_enabled():
                    self._check_and_create_cards()
                else:
                    logger.debug("Card scheduler is disabled, skipping card creation")
            except Exception as e:
                logger.error(f"Error in card scheduler loop: {str(e)}")
                create_notification(
                    subject="❌ Card Scheduler Error",
                    message=f"An error occurred in the card scheduler:\n\n{str(e)}\n\nThe scheduler will continue running, but please check the logs."
                )
            
            # Sleep for 60 seconds
            for _ in range(60):
                if not self.running:
                    break
                time.sleep(1)
    
    def _is_enabled(self) -> bool:
        """Check if card scheduler is enabled in settings."""
        try:
            import json
            from models import Setting
            
            db = SessionLocal()
            try:
                setting = db.query(Setting).filter(Setting.key == "card_scheduler_enabled").first()
                if setting is not None and setting.value is not None:
                    return json.loads(str(setting.value))
                return True  # Default to enabled
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error checking card_scheduler_enabled setting: {e}")
            return True  # Default to enabled on error
    
    def _check_and_create_cards(self):
        """Check all enabled schedules and create cards if needed."""
        db = SessionLocal()
        try:
            now = datetime.now()
            
            # Get all enabled schedules
            schedules = (
                db.query(ScheduledCard)
                .filter(ScheduledCard.schedule_enabled.is_(True))
                .all()
            )
            
            for schedule in schedules:
                try:
                    self._process_schedule(db, schedule, now)
                except Exception as e:
                    logger.error(f"Error processing schedule {schedule.id}: {str(e)}")
                    # Continue with other schedules
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Error checking schedules: {str(e)}")
            db.rollback()
        finally:
            db.close()
    
    def _process_schedule(self, db, schedule: ScheduledCard, now: datetime):
        """Process a single schedule and create card if needed.
        
        This method implements a catch-up mechanism to handle missed schedules:
        - Looks back up to 1 hour to find the most recent scheduled run time
        - Creates the card if we're within 1 minute of any missed run time
        - Only creates ONE card per missed window to prevent duplicates
        
        Limitations:
        - If the server is down for more than 1 hour, schedules in that period won't be caught up
        - Only catches up the most recent missed run, not all missed runs
        - Relies on checking the database for existing cards to prevent duplicates
        
        Args:
            db: Database session
            schedule: ScheduledCard instance
            now: Current datetime
        """
        # Check if we're past the start time
        if now < schedule.start_datetime:  # type: ignore
            return
        
        # Check if we're past the end time (if set)
        if schedule.end_datetime is not None:
            if now > schedule.end_datetime:  # type: ignore
                # Disable the schedule
                if schedule.schedule_enabled:  # type: ignore
                    schedule.schedule_enabled = False  # type: ignore
                    logger.info(f"Disabled schedule {schedule.id} - past end time")
                    create_notification(
                        subject="⏰ Schedule Ended",
                        message=f"The schedule for card '{schedule.template_card.title}' has been automatically disabled because it reached its end time."
                    )
                return
        
        # Calculate next run time - check if we should run now
        # Look back up to 1 hour to catch any runs we might have missed due to:
        # - Server restarts
        # - Heavy load causing delayed execution
        # - Temporary service interruptions
        # This provides a reasonable catch-up window without going too far back
        lookback_window = timedelta(hours=1)
        check_time = now - lookback_window
        
        next_run = get_next_run(
            start=schedule.start_datetime,  # type: ignore
            after=check_time,
            run_every=schedule.run_every,  # type: ignore
            unit=schedule.unit  # type: ignore
        )
        
        # Check if it's time to create a card
        # We create a card if the calculated next_run is in the past but within our lookback window
        # This allows catching up on missed schedules while preventing old schedules from triggering
        if next_run and next_run <= now:
            # Check how far in the past this run was
            time_since_run = (now - next_run).total_seconds()
            
            # Only create if within lookback window (prevents very old schedules from triggering)
            if time_since_run < lookback_window.total_seconds():
                # Additional safety when duplicates not allowed: Check if card already exists
                # This prevents creating duplicate cards if the scheduler runs multiple times
                # within the lookback window (e.g., after a restart)
                if not schedule.allow_duplicates:  # type: ignore
                    # Get the template card to check its column
                    template = db.query(Card).filter(Card.id == schedule.card_id).first()
                    if not template:
                        logger.error(f"Template card {schedule.card_id} not found for schedule {schedule.id}")
                        return
                    
                    # For non-duplicate schedules, check if any active cards exist from this schedule IN THE SAME COLUMN
                    # This is a simple but effective way to prevent duplicates without needing timestamps
                    existing_card = (
                        db.query(Card)
                        .filter(Card.column_id == template.column_id)  # Check same column only
                        .filter(Card.schedule == schedule.id)
                        .filter(Card.scheduled.is_(False))  # Don't count template cards
                        .filter(Card.archived.is_(False))  # Only check active cards
                        .first()
                    )
                    
                    if existing_card:
                        # Already have an active card for this schedule in this column, skip
                        logger.debug(f"Skipping schedule {schedule.id} - active card already exists in column {template.column_id}")
                        return
                
                logger.info(f"Creating card for schedule {schedule.id} (missed by {time_since_run:.0f} seconds)")
                self._create_scheduled_card(db, schedule)
            else:
                logger.debug(f"Skipping schedule {schedule.id} - next_run too old ({time_since_run:.0f} seconds ago)")
    
    def _create_scheduled_card(self, db, schedule: ScheduledCard):
        """Create a new card from a schedule template.
        
        Args:
            db: Database session
            schedule: ScheduledCard instance
        """
        try:
            # Get the template card
            template = db.query(Card).filter(Card.id == schedule.card_id).first()
            if not template:
                logger.error(f"Template card {schedule.card_id} not found for schedule {schedule.id}")
                return
            
            # Check for duplicates if not allowed
            if not schedule.allow_duplicates:  # type: ignore
                # Check for unarchived cards in the same column with this schedule ID
                existing_count = (
                    db.query(Card)
                    .filter(Card.column_id == template.column_id)
                    .filter(Card.schedule == schedule.id)
                    .filter(Card.archived.is_(False))
                    .filter(Card.scheduled.is_(False))  # Don't count template cards
                    .count()
                )
                
                if existing_count > 0:
                    logger.info(f"Skipping card creation for schedule {schedule.id} - duplicate exists in column")
                    return
            
            # Get the highest order in the column for new cards
            max_order = db.query(func.max(Card.order)).filter(
                Card.column_id == template.column_id,
                Card.scheduled.is_(False)  # Only consider real cards, not templates
            ).scalar() or 0
            
            # Create new card from template
            new_card = Card(
                column_id=template.column_id,
                title=template.title,
                description=template.description,
                order=max_order + 1,
                archived=False,
                scheduled=False,  # This is a real card, not a template
                schedule=schedule.id  # Link back to the schedule
            )
            
            db.add(new_card)
            db.flush()  # Get the new card ID
            
            # Copy checklist items
            for item in template.checklist_items:
                new_item = ChecklistItem(
                    card_id=new_card.id,
                    name=item.name,
                    checked=item.checked,
                    order=item.order
                )
                db.add(new_item)
            
            # Add a comment to track creation
            # Get the highest comment order
            max_comment_order = db.query(func.max(Comment.order)).filter(
                Comment.card_id == new_card.id
            ).scalar() or 0
            
            comment_text = (
                f"🤖 Created by scheduling system\n\n"
                f"Schedule ID: {schedule.id}\n"
                f"Frequency: Every {schedule.run_every} {schedule.unit if schedule.run_every == 1 else schedule.unit + 's'}\n"  # type: ignore
                f"Created at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            comment = Comment(
                card_id=new_card.id,
                comment=comment_text,
                order=max_comment_order + 1
            )
            db.add(comment)

            # Broadcast so connected clients see scheduler-created cards immediately.
            try:
                column = db.query(BoardColumn).filter(BoardColumn.id == template.column_id).first()
                board_id = column.board_id if column else None
                if board_id is not None:
                    from app import broadcast_event

                    broadcast_event('card_created', {
                        'board_id': board_id,
                        'column_id': new_card.column_id,
                        'card_id': new_card.id,
                        'card_data': {
                            'id': new_card.id,
                            'column_id': new_card.column_id,
                            'title': new_card.title,
                            'description': new_card.description,
                            'order': new_card.order,
                            'scheduled': new_card.scheduled,
                            'schedule': new_card.schedule,
                            'archived': new_card.archived,
                            'done': new_card.done,
                            'created_at': new_card.created_at.isoformat() if new_card.created_at else None,
                            'updated_at': new_card.updated_at.isoformat() if new_card.updated_at else None
                        }
                    }, board_id)
                else:
                    logger.warning(
                        f"Skipping scheduler card_created broadcast for card {new_card.id}: column {template.column_id} has no board_id"
                    )
            except Exception as broadcast_error:
                logger.warning(f"Failed to broadcast scheduler-created card {new_card.id}: {broadcast_error}")
            
            logger.info(f"Created card {new_card.id} from schedule {schedule.id}")
            
        except Exception as e:
            logger.error(f"Error creating card from schedule {schedule.id}: {str(e)}")
            raise


# Global scheduler instance
_scheduler = None


def get_scheduler() -> CardScheduler:
    """Get the global card scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = CardScheduler()
    return _scheduler


def start_scheduler():
    """Start the card scheduler."""
    scheduler = get_scheduler()
    scheduler.start()


def stop_scheduler():
    """Stop the card scheduler."""
    scheduler = get_scheduler()
    scheduler.stop()


if __name__ == "__main__":
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("Starting card scheduler in standalone mode")
    start_scheduler()
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        stop_scheduler()
