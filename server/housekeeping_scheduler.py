"""Housekeeping scheduler service for periodic maintenance tasks."""
import threading
import time
import logging
import requests
import json
from typing import Optional
from pathlib import Path
from packaging import version

from notification_utils import create_notification

logger = logging.getLogger(__name__)

# GitHub API configuration
GITHUB_REPO_OWNER = "sjefferson99"
GITHUB_REPO_NAME = "aft"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"


class HousekeepingScheduler:
    """Manages periodic housekeeping tasks."""
    
    def __init__(self, app_version: str):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock_file = Path("/tmp/aft_housekeeping_scheduler.lock")
        self.app_version = app_version
        self.check_interval = 3600  # Run every hour (3600 seconds)
    
    def start(self):
        """Start the housekeeping scheduler thread."""
        if self.running:
            logger.warning("Housekeeping scheduler already running")
            return
        
        # Use file lock to ensure only one worker starts the scheduler
        try:
            if self.lock_file.exists():
                try:
                    with open(self.lock_file, 'r') as f:
                        pid = int(f.read().strip())
                    
                    # Check if process is still running
                    import psutil
                    if psutil.pid_exists(pid):
                        logger.info(f"Housekeeping scheduler already running in process {pid}")
                        return
                    else:
                        logger.info(f"Removing stale lock file for process {pid}")
                        self.lock_file.unlink()
                except (ValueError, FileNotFoundError):
                    logger.warning("Invalid lock file, removing")
                    self.lock_file.unlink()
            
            # Create lock file with current PID
            import os
            with open(self.lock_file, 'w') as f:
                f.write(str(os.getpid()))
            
            self.running = True
            self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.thread.start()
            logger.info("Housekeeping scheduler started")
            
        except Exception as e:
            logger.error(f"Failed to start housekeeping scheduler: {e}")
    
    def stop(self):
        """Stop the housekeeping scheduler thread."""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        
        # Remove lock file
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception as e:
            logger.error(f"Error removing lock file: {e}")
        
        logger.info("Housekeeping scheduler stopped")
    
    def _run_scheduler(self):
        """Main scheduler loop - runs every minute."""
        logger.info("Housekeeping scheduler thread started")
        
        while self.running:
            try:
                # Check if housekeeping is enabled
                if self._is_enabled():
                    # Run housekeeping tasks
                    self._check_for_updates()
                else:
                    logger.debug("Housekeeping scheduler is disabled, skipping checks")
                
                # Sleep for the check interval
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in housekeeping scheduler loop: {e}", exc_info=True)
                time.sleep(self.check_interval)
    
    def _is_enabled(self) -> bool:
        """Check if housekeeping scheduler is enabled in settings."""
        try:
            from database import SessionLocal
            from models import Setting
            
            db = SessionLocal()
            try:
                setting = db.query(Setting).filter(Setting.key == "housekeeping_enabled").first()
                if setting is not None and setting.value is not None:
                    return json.loads(str(setting.value))
                return True  # Default to enabled
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error checking housekeeping_enabled setting: {e}")
            return True  # Default to enabled on error
    
    def _check_for_updates(self):
        """Check GitHub for new releases and create notification if update available."""
        try:
            # Fetch latest release from GitHub
            response = requests.get(GITHUB_API_URL, timeout=10)
            
            if response.status_code != 200:
                logger.warning(f"Failed to check for updates: HTTP {response.status_code}")
                return
            
            data = response.json()
            latest_version = data.get('tag_name', '').lstrip('v')
            release_url = data.get('html_url', f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases")
            
            if not latest_version:
                logger.warning("No version information in GitHub release")
                return
            
            # Parse versions for comparison
            try:
                current_ver = version.parse(self.app_version)
                latest_ver = version.parse(latest_version)
            except Exception as e:
                logger.error(f"Error parsing version numbers: {e}")
                return
            
            # Compare versions
            if latest_ver > current_ver:
                # New version available - check if we should notify
                logger.info(f"New version available: {latest_version} (current: {self.app_version})")
                
                # Check if an unread notification already exists
                if self._has_unread_version_notification(latest_version):
                    logger.debug(f"Unread notification already exists for version {latest_version}")
                    return
                
                # Create notification
                subject = f"New Version Available: {latest_version}"
                message = (
                    f"A new version of AFT ({latest_version}) is available. "
                    f"You are currently running version {self.app_version}. "
                    f"Click the button below to view the release notes and download."
                )
                action_title = "View Release"
                action_url = release_url
                
                success = create_notification(
                    subject=subject,
                    message=message,
                    action_title=action_title,
                    action_url=action_url
                )
                
                if success:
                    logger.info(f"Created notification for new version {latest_version}")
                else:
                    logger.error("Failed to create notification for new version")
            
            elif latest_ver == current_ver:
                logger.debug(f"Already running latest version: {self.app_version}")
            else:
                # Current version is newer (development/testing branch)
                logger.debug(f"Running development version {self.app_version} (latest release: {latest_version})")
        
        except requests.RequestException as e:
            logger.warning(f"Network error checking for updates: {e}")
        except Exception as e:
            logger.error(f"Unexpected error checking for updates: {e}", exc_info=True)
    
    def _has_unread_version_notification(self, new_version: str) -> bool:
        """Check if an unread notification already exists for this version.
        
        Returns True if unread notification exists, False otherwise.
        """
        try:
            from models import Notification
            from database import SessionLocal
            
            # Look for unread notifications with this version in the subject
            subject_pattern = f"New Version Available: {new_version}"
            
            session = SessionLocal()
            try:
                existing = session.query(Notification).filter(
                    Notification.subject == subject_pattern,
                    Notification.unread.is_(True)
                ).first()
                
                return existing is not None
            finally:
                session.close()
            
        except Exception as e:
            logger.error(f"Error checking for existing notifications: {e}")
            # On error, assume notification doesn't exist to avoid missing updates
            return False
    
    def get_status(self) -> dict:
        """Get current scheduler status."""
        from database import SessionLocal
        from models import Setting
        import os
        
        # Get enabled setting from database
        db = SessionLocal()
        try:
            setting = db.query(Setting).filter(Setting.key == "housekeeping_enabled").first()
            if setting is not None and setting.value is not None:
                enabled = json.loads(str(setting.value))
            else:
                enabled = True
        except Exception as e:
            logger.error(f"Error reading housekeeping_enabled setting: {e}")
            enabled = True  # Default to enabled
        finally:
            db.close()
        
        # Check if scheduler is actually running
        is_running = False
        if self.lock_file.exists():
            try:
                with open(self.lock_file, 'r') as f:
                    pid = int(f.read().strip())
                try:
                    os.kill(pid, 0)  # Check if process exists
                    is_running = True
                except OSError:
                    is_running = False
            except (ValueError, FileNotFoundError):
                is_running = False
        
        return {
            "running": is_running,
            "enabled": enabled,
            "check_interval": self.check_interval,
            "app_version": self.app_version
        }


# Global scheduler instance
_housekeeping_scheduler: Optional[HousekeepingScheduler] = None


def get_housekeeping_scheduler(app_version: str) -> HousekeepingScheduler:
    """Get or create the housekeeping scheduler instance."""
    global _housekeeping_scheduler
    if _housekeeping_scheduler is None:
        _housekeeping_scheduler = HousekeepingScheduler(app_version)
    return _housekeeping_scheduler


def start_housekeeping_scheduler(app_version: str):
    """Start the housekeeping scheduler."""
    scheduler = get_housekeeping_scheduler(app_version)
    scheduler.start()


def stop_housekeeping_scheduler():
    """Stop the housekeeping scheduler."""
    global _housekeeping_scheduler
    if _housekeeping_scheduler:
        _housekeeping_scheduler.stop()
