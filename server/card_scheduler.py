"""Automatic card scheduler service."""
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging

from sqlalchemy import func
from database import SessionLocal
from models import Card, ScheduledCard, Comment, ChecklistItem
from notification_utils import create_notification
from schedule_utils import get_next_run

logger = logging.getLogger(__name__)


class CardScheduler:
    """Manages automatic card creation on a schedule."""
    
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock_file = Path("/tmp/aft_card_scheduler.lock")
    
    def _acquire_lock(self) -> bool:
        """Attempt to acquire the scheduler lock.
        
        Returns:
            bool: True if lock acquired, False otherwise
        """
        try:
            if self.lock_file.exists():
                # Check if lock is stale (> 5 minutes old)
                age = time.time() - self.lock_file.stat().st_mtime
                if age > 300:  # 5 minutes
                    logger.warning("Removing stale card scheduler lock file")
                    self.lock_file.unlink()
                else:
                    return False
            
            # Create lock file with PID
            self.lock_file.write_text(str(os.getpid()))
            return True
        except Exception as e:
            logger.error(f"Error acquiring card scheduler lock: {str(e)}")
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
        if self.running:
            logger.warning("Card scheduler is already running")
            return
        
        if not self._acquire_lock():
            logger.error("Could not acquire card scheduler lock - another instance may be running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("Card scheduler started")
    
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
                self._check_and_create_cards()
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
        # Look back 1 minute to catch any runs we might have missed
        check_time = now - timedelta(minutes=1)
        next_run = get_next_run(
            start=schedule.start_datetime,  # type: ignore
            after=check_time,
            run_every=schedule.run_every,  # type: ignore
            unit=schedule.unit  # type: ignore
        )
        
        # Check if it's time to create a card (within the last minute)
        if next_run and (now - next_run).total_seconds() < 60:
            self._create_scheduled_card(db, schedule)
    
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
                f"Frequency: Every {schedule.run_every} {schedule.unit}{'s' if int(schedule.run_every) > 1 else ''}\n"  # type: ignore
                f"Created at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            comment = Comment(
                card_id=new_card.id,
                comment=comment_text,
                order=max_comment_order + 1
            )
            db.add(comment)
            
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
