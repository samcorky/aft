"""Automatic backup scheduler service."""
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging

from sqlalchemy import text
from database import SessionLocal
from models import Setting

logger = logging.getLogger(__name__)


def _get_setting_value(db, key: str, default=None):
    """Get a setting value from the database with JSON parsing.
    
    Args:
        db: Database session
        key: Setting key
        default: Default value if setting not found
        
    Returns:
        Parsed setting value or default
    """
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting and setting.value:
        try:
            return json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            return setting.value
    return default

class BackupScheduler:
    """Manages automatic database backups on a schedule."""
    
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_backup_time: Optional[datetime] = None
        self.backup_dir = Path("/app/backups")
        self.lock_file = Path("/tmp/aft_backup_scheduler.lock")
        
    def start(self):
        """Start the backup scheduler thread."""
        if self.running:
            logger.warning("Backup scheduler already running")
            return
        
        # Use file lock to ensure only one worker starts the scheduler
        try:
            # Check if lock file exists and if the process is still running
            if self.lock_file.exists():
                try:
                    with open(self.lock_file, 'r') as f:
                        old_pid = int(f.read().strip())
                    # Check if process is still running
                    try:
                        os.kill(old_pid, 0)  # Signal 0 doesn't kill, just checks if process exists
                        logger.info("Backup scheduler lock file exists, another worker is handling backups")
                        return
                    except OSError:
                        # Process doesn't exist, remove stale lock file
                        logger.info("Removing stale backup scheduler lock file")
                        self.lock_file.unlink()
                except (ValueError, FileNotFoundError):
                    # Invalid lock file, remove it
                    self.lock_file.unlink()
            
            # Try to create lock file exclusively (fails if already exists)
            with open(self.lock_file, 'x') as f:
                f.write(str(os.getpid()))
        except FileExistsError:
            logger.info("Backup scheduler lock file exists, another worker is handling backups")
            return
        except Exception as e:
            logger.error(f"Error creating scheduler lock file: {str(e)}")
            return
        
        # Validate settings on startup
        try:
            settings = self._get_settings()
            self._validate_settings(settings)
            logger.info(f"Backup scheduler validated settings: enabled={settings.get('backup_enabled')}, "
                       f"frequency={settings.get('backup_frequency_value')} {settings.get('backup_frequency_unit')}")
        except Exception as e:
            logger.error(f"Invalid backup settings on startup: {str(e)}")
            # Disable backups if settings are invalid
            self._disable_backups_due_to_invalid_settings(str(e))
            
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info("Backup scheduler started")
        
    def stop(self):
        """Stop the backup scheduler thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        
        # Clean up lock file
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
                logger.info("Removed backup scheduler lock file")
        except Exception as e:
            logger.error(f"Error removing lock file: {str(e)}")
        
        logger.info("Backup scheduler stopped")
        
    def _disable_backups_due_to_invalid_settings(self, error_msg: str):
        """Disable backups in database due to invalid settings."""
        db = SessionLocal()
        try:
            setting = db.query(Setting).filter(Setting.key == "backup_enabled").first()
            if setting:
                setting.value = json.dumps(False)
                db.commit()
                logger.warning(f"Disabled backups due to invalid settings: {error_msg}")
        except Exception as e:
            logger.error(f"Failed to disable backups: {str(e)}")
            db.rollback()
        finally:
            db.close()
    
    def _validate_settings(self, settings: dict):
        """Validate backup settings against expected types and ranges.
        
        Raises:
            ValueError: If any setting is invalid
        """
        enabled = settings.get("backup_enabled")
        if not isinstance(enabled, bool):
            raise ValueError(f"backup_enabled must be boolean, got {type(enabled)}")
        
        freq_value = settings.get("backup_frequency_value")
        if not isinstance(freq_value, int) or not (1 <= freq_value <= 99):
            raise ValueError(f"backup_frequency_value must be integer 1-99, got {freq_value}")
        
        freq_unit = settings.get("backup_frequency_unit")
        if freq_unit not in ["minutes", "hours", "days"]:
            raise ValueError(f"backup_frequency_unit must be minutes/hours/days, got {freq_unit}")
        
        start_time = settings.get("backup_start_time")
        if not isinstance(start_time, str):
            raise ValueError(f"backup_start_time must be string, got {type(start_time)}")
        try:
            parts = start_time.split(":")
            if len(parts) != 2:
                raise ValueError("Invalid time format")
            hours, minutes = int(parts[0]), int(parts[1])
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError("Time out of range")
        except (ValueError, AttributeError) as e:
            raise ValueError(f"backup_start_time must be HH:MM format, got {start_time}: {e}")
        
        retention = settings.get("backup_retention_count")
        if not isinstance(retention, int) or not (1 <= retention <= 100):
            raise ValueError(f"backup_retention_count must be integer 1-100, got {retention}")
    
    def _get_settings(self):
        """Retrieve backup settings from database."""
        db = SessionLocal()
        try:
            settings = {
                "backup_enabled": _get_setting_value(db, "backup_enabled", False),
                "backup_frequency_value": _get_setting_value(db, "backup_frequency_value", 1),
                "backup_frequency_unit": _get_setting_value(db, "backup_frequency_unit", "days"),
                "backup_start_time": _get_setting_value(db, "backup_start_time", "00:00"),
                "backup_retention_count": _get_setting_value(db, "backup_retention_count", 7)
            }
            return settings
        finally:
            db.close()
            
    def _update_last_backup_setting(self):
        """Update the last backup timestamp in settings."""
        db = SessionLocal()
        try:
            timestamp = datetime.now().isoformat()
            setting = db.query(Setting).filter(Setting.key == "backup_last_run").first()
            if setting:
                setting.value = json.dumps(timestamp)
            else:
                setting = Setting(key="backup_last_run", value=json.dumps(timestamp))
                db.add(setting)
            db.commit()
            self.last_backup_time = datetime.now()
        except Exception as e:
            logger.error(f"Error updating backup timestamp: {str(e)}")
            db.rollback()
            # Still update in-memory time even if DB update fails
            self.last_backup_time = datetime.now()
        finally:
            db.close()
            
    def _parse_start_time(self, time_str: str) -> datetime:
        """Parse time string (HH:MM) and return next occurrence as datetime."""
        try:
            hour, minute = map(int, time_str.split(':'))
            now = datetime.now()
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # If the time has already passed today, schedule for tomorrow
            if next_run <= now:
                next_run += timedelta(days=1)
                
            return next_run
        except (ValueError, AttributeError):
            # Default to current time if parsing fails
            return datetime.now()
            
    def _get_frequency_timedelta(self, value, unit: str) -> timedelta:
        """Convert frequency value and unit to timedelta."""
        try:
            val = int(value) if not isinstance(value, int) else value
            if unit == "minutes":
                return timedelta(minutes=val)
            elif unit == "hours":
                return timedelta(hours=val)
            elif unit == "days":
                return timedelta(days=val)
        except (ValueError, TypeError):
            # Invalid value or unit, fall through to default
            pass
        
        # Default to 24 hours
        return timedelta(hours=24)
        
    def _should_run_backup(self, settings: dict) -> bool:
        """Determine if a backup should run now."""
        # Check if backups are enabled
        if not settings.get("backup_enabled"):
            return False
        
        # Validate settings before attempting backup
        try:
            self._validate_settings(settings)
        except ValueError as e:
            logger.error(f"Invalid backup settings detected: {str(e)}")
            self._disable_backups_due_to_invalid_settings(str(e))
            return False
            
        # Get frequency settings
        freq_value = settings.get("backup_frequency_value", 1)
        freq_unit = settings.get("backup_frequency_unit", "days")
        start_time = settings.get("backup_start_time", "00:00")
        
        frequency = self._get_frequency_timedelta(freq_value, freq_unit)
        now = datetime.now()
        
        # If no last backup time, check if we should run initial backup
        if not self.last_backup_time:
            # Load last run from settings
            db = SessionLocal()
            try:
                last_run = _get_setting_value(db, "backup_last_run")
                if last_run:
                    try:
                        self.last_backup_time = datetime.fromisoformat(last_run)
                    except ValueError:
                        # Invalid timestamp format, leave last_backup_time as None
                        pass
            finally:
                db.close()
                
            # If still no last backup, run immediately if we're past the first interval
            if not self.last_backup_time:
                # For the first backup, check if we're within one frequency period of start_time
                # If we are, wait for the next aligned time. If not, run immediately.
                start_hour, start_minute = map(int, start_time.split(':'))
                today_start = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
                yesterday_start = today_start - timedelta(days=1)
                
                # Find the most recent start_time occurrence
                if now >= today_start:
                    last_start = today_start
                else:
                    last_start = yesterday_start
                
                time_since_start = now - last_start
                
                # If we're more than one frequency period past the start time, run immediately
                if time_since_start > frequency:
                    logger.info(f"No previous backup and overdue by {time_since_start - frequency}, running immediately")
                    return True
                else:
                    # Within the window, wait for next aligned time
                    next_scheduled = self._parse_start_time(start_time)
                    return now >= next_scheduled
        
        # Check if enough time has passed since last backup
        time_since_last = now - self.last_backup_time
        if time_since_last < frequency:
            return False
        
        # If we're significantly overdue (more than 2x frequency), run immediately
        if time_since_last > frequency * 2:
            logger.info(f"Backup overdue by {time_since_last - frequency}, running immediately")
            return True
        
        # Align to start_time pattern for hourly/minute intervals
        if freq_unit in ["minutes", "hours"]:
            start_hour, start_minute = map(int, start_time.split(':'))
            
            if freq_unit == "minutes":
                # Calculate minutes since start_time alignment
                minutes_since_midnight = now.hour * 60 + now.minute
                start_minutes_since_midnight = start_hour * 60 + start_minute
                
                # Calculate how many intervals have passed since start_time
                if minutes_since_midnight >= start_minutes_since_midnight:
                    minutes_diff = minutes_since_midnight - start_minutes_since_midnight
                else:
                    # Wrap around to previous day
                    minutes_diff = (1440 - start_minutes_since_midnight) + minutes_since_midnight
                
                # Check if we're at an interval boundary
                if minutes_diff % freq_value == 0:
                    # Make sure we haven't already run in this minute
                    if self.last_backup_time.hour != now.hour or self.last_backup_time.minute != now.minute:
                        return True
                return False
            
            elif freq_unit == "hours":
                # For hourly, run at the specified minute past each hour
                if now.minute == start_minute:
                    # Make sure we haven't already run in this hour
                    if self.last_backup_time.hour != now.hour:
                        return True
                return False
        
        # For daily backups, check if we're at the scheduled time
        elif freq_unit == "days":
            start_hour, start_minute = map(int, start_time.split(':'))
            
            # Check if current time matches start_time (within the same minute)
            if now.hour == start_hour and now.minute == start_minute:
                # Make sure we haven't already run today
                if self.last_backup_time.date() != now.date():
                    return True
            return False
        
        return False
        
    def _create_backup(self):
        """Create a database backup file."""
        try:
            # Ensure backup directory exists
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Get current Alembic version
            db = SessionLocal()
            try:
                result = db.execute(text("SELECT version_num FROM alembic_version"))
                row = result.fetchone()
                db_version = row[0] if row else "unknown"
            finally:
                db.close()
            
            # Get database credentials
            db_user = os.environ.get("MYSQL_USER")
            db_password = os.environ.get("MYSQL_PASSWORD")
            db_name = os.environ.get("MYSQL_DATABASE")
            db_host = "db"
            
            # Create backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"auto_backup_{timestamp}.sql"
            backup_path = self.backup_dir / backup_filename
            
            # Write version header
            with open(backup_path, "w") as f:
                f.write("-- AFT Automatic Database Backup\n")
                f.write(f"-- Alembic Version: {db_version}\n")
                f.write(f"-- Backup Date: {datetime.now().isoformat()}\n")
                f.write("--\n\n")
            
            # Run mysqldump
            mysqldump_cmd = [
                "mysqldump",
                "-h", db_host,
                "-u", db_user,
                f"-p{db_password}",
                "--single-transaction",
                "--routines",
                "--triggers",
                "--skip-ssl",
                db_name,
            ]
            
            with open(backup_path, "a") as f:
                result = subprocess.run(
                    mysqldump_cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True
                )
            
            if result.returncode != 0:
                backup_path.unlink(missing_ok=True)
                raise Exception(f"mysqldump failed: {result.stderr}")
            
            logger.info(f"Automatic backup created: {backup_filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating automatic backup: {str(e)}")
            return False
            
    def _rotate_backups(self, retention_count: int):
        """Remove old backups to maintain retention count."""
        try:
            # Get all auto backup files sorted by modification time
            backup_files = sorted(
                self.backup_dir.glob("auto_backup_*.sql"),
                key=lambda p: p.stat().st_mtime,
                reverse=True  # Newest first
            )
            
            # Remove old backups beyond retention count
            for backup_file in backup_files[retention_count:]:
                backup_file.unlink()
                logger.info(f"Rotated old backup: {backup_file.name}")
                
        except Exception as e:
            logger.error(f"Error rotating backups: {str(e)}")
            
    def _run_scheduler(self):
        """Main scheduler loop."""
        logger.info("Backup scheduler loop started")
        
        while self.running:
            logger.info("Backup scheduler loop iteration starting")
            try:
                settings = self._get_settings()
                
                should_run = self._should_run_backup(settings)
                logger.info(f"Backup check: should_run={should_run}, enabled={settings.get('backup_enabled')}, last_backup={self.last_backup_time}")
                
                if should_run:
                    logger.info("Running scheduled backup")
                    
                    if self._create_backup():
                        self._update_last_backup_setting()
                        
                        # Rotate old backups
                        try:
                            retention = settings.get("backup_retention_count", 7)
                            if not isinstance(retention, int):
                                retention = int(retention)
                            self._rotate_backups(retention)
                        except (ValueError, TypeError):
                            logger.warning("Invalid retention count, skipping rotation")
                
                # Sleep for 1 minute before next check
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in backup scheduler loop: {str(e)}")
                time.sleep(60)  # Sleep before retrying
                
        logger.info("Backup scheduler loop stopped")
        
    def get_status(self) -> dict:
        """Get current scheduler status."""
        settings = self._get_settings()
        
        enabled = settings.get("backup_enabled", False)
        freq_value = settings.get("backup_frequency_value", 1)
        freq_unit = settings.get("backup_frequency_unit", "days")
        retention = settings.get("backup_retention_count", 7)
        
        # Check if scheduler is actually running by checking lock file and process
        is_running = False
        if self.lock_file.exists():
            try:
                with open(self.lock_file, 'r') as f:
                    pid = int(f.read().strip())
                logger.info(f"Lock file exists with PID {pid}, checking if process is alive")
                try:
                    os.kill(pid, 0)  # Check if process exists
                    is_running = True
                    logger.info(f"Process {pid} is alive, scheduler is running")
                except OSError as e:
                    # Process doesn't exist
                    logger.warning(f"Process {pid} not found (errno {e.errno}), scheduler not running")
                    is_running = False
            except (ValueError, FileNotFoundError) as e:
                logger.error(f"Error reading lock file: {str(e)}")
                is_running = False
        else:
            logger.info("Lock file does not exist, scheduler not running")
        
        # Get latest backup file info
        latest_backup = self._get_latest_backup_info()
        latest_backup_path = latest_backup.get("path")
        latest_backup_date = latest_backup.get("date")
        
        # Check if backup is within expected window
        within_window = False
        if latest_backup_date and enabled:
            within_window = self._is_backup_within_window(
                latest_backup_date, 
                freq_value, 
                freq_unit
            )
        
        return {
            "running": is_running,
            "enabled": enabled,
            "last_backup": self.last_backup_time.isoformat() if self.last_backup_time else None,
            "frequency": f"{freq_value} {freq_unit}",
            "retention_count": retention,
            "start_time": settings.get("backup_start_time", "00:00"),
            "latest_backup_file": latest_backup_path,
            "latest_backup_date": latest_backup_date.isoformat() if latest_backup_date else None,
            "backup_within_window": within_window
        }
    
    def _get_latest_backup_info(self) -> dict:
        """Get information about the latest backup file.
        
        Returns:
            dict: Contains 'path' (filename or None) and 'date' (datetime or None)
        """
        try:
            if not self.backup_dir.exists():
                return {"path": None, "date": None}
            
            # Find all .sql files in backup directory
            backup_files = list(self.backup_dir.glob("auto_backup_*.sql"))
            
            if not backup_files:
                return {"path": None, "date": None}
            
            # Get the most recent file by creation time
            latest_file = max(backup_files, key=lambda f: f.stat().st_ctime)
            latest_date = datetime.fromtimestamp(latest_file.stat().st_ctime)
            
            return {
                "path": latest_file.name,
                "date": latest_date
            }
        except Exception as e:
            logger.error(f"Error getting latest backup info: {str(e)}")
            return {"path": None, "date": None}
    
    def _is_backup_within_window(self, backup_date: datetime, freq_value: int, freq_unit: str) -> bool:
        """Check if backup is within the expected backup window.
        
        Args:
            backup_date: Date of the backup file
            freq_value: Frequency value (e.g., 5, 24, 7)
            freq_unit: Frequency unit ('minutes', 'hours', 'days')
            
        Returns:
            bool: True if backup is within expected window, False otherwise
        """
        now = datetime.now()
        
        # Calculate expected window (frequency * 2 to allow some leeway)
        if freq_unit == "minutes":
            window = timedelta(minutes=freq_value * 2)
        elif freq_unit == "hours":
            window = timedelta(hours=freq_value * 2)
        elif freq_unit == "days":
            window = timedelta(days=freq_value * 2)
        else:
            # Unknown unit, assume not within window
            return False
        
        time_since_backup = now - backup_date
        return time_since_backup <= window



# Global scheduler instance
_scheduler = None
_scheduler_lock = threading.Lock()

def get_scheduler() -> BackupScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = BackupScheduler()
    return _scheduler
