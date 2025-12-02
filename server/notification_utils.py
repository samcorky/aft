"""Utility functions for notification management."""
import logging
from database import SessionLocal
from models import Notification

logger = logging.getLogger(__name__)


def create_notification(subject: str, message: str) -> bool:
    """Create a notification in the database.
    
    This is a shared utility function for both API endpoints and internal use
    (backup scheduler, error handlers, etc.) to create notifications.
    
    Args:
        subject: Notification subject (max 255 chars)
        message: Notification message (max 65535 chars)
        
    Returns:
        True if notification created successfully, False otherwise
    """
    db = SessionLocal()
    try:
        # Validate and truncate if necessary
        subject = subject.strip()[:255]
        message = message.strip()[:65535]
        
        if not subject or not message:
            logger.warning("Attempted to create notification with empty subject or message")
            return False
        
        notification = Notification(
            subject=subject,
            message=message,
            unread=True
        )
        
        db.add(notification)
        db.commit()
        logger.info(f"Created notification: {subject}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating notification: {str(e)}")
        return False
    finally:
        db.close()
