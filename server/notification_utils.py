"""Utility functions for notification management."""
import logging
from database import SessionLocal
from models import Notification

logger = logging.getLogger(__name__)


def create_notification(subject: str, message: str, action_title: str = None, action_url: str = None) -> bool:
    """Create a notification in the database.
    
    This is a shared utility function for internal use (backup scheduler, 
    error handlers, etc.) to create notifications. Unlike the API endpoint 
    which validates and rejects oversized input, this function silently 
    truncates content that exceeds database column limits and logs an info message.
    
    This forgiving behavior is intentional for internal operations where
    notifications should not fail due to message length.
    
    Args:
        subject: Notification subject (truncated to 255 chars if longer)
        message: Notification message (truncated to 65535 chars if longer)
        action_title: Optional action button title (truncated to 100 chars if longer)
        action_url: Optional action button URL (truncated to 500 chars if longer)
        
    Returns:
        True if notification created successfully, False otherwise
        
    Note:
        If truncation occurs, an info message is logged with details about
        the truncated content.
    """
    db = SessionLocal()
    try:
        # Validate and warn about truncation if necessary
        original_subject = subject.strip()
        original_message = message.strip()
        
        subject = original_subject[:255]
        message = original_message[:65535]
        
        # Process action fields if provided
        if action_title is not None:
            original_action_title = action_title.strip()
            action_title = original_action_title[:100] if original_action_title else None
            if original_action_title and len(original_action_title) > 100:
                truncated_chars = len(original_action_title) - 100
                logger.info(
                    f"Notification action_title truncated: {truncated_chars} characters removed. "
                    f"Original: '{original_action_title[:50]}...', Truncated: '{action_title[:50]}...'"
                )
        else:
            action_title = None
            
        if action_url is not None:
            original_action_url = action_url.strip()
            action_url = original_action_url[:500] if original_action_url else None
            if original_action_url and len(original_action_url) > 500:
                truncated_chars = len(original_action_url) - 500
                logger.info(
                    f"Notification action_url truncated: {truncated_chars} characters removed. "
                    f"Original: '{original_action_url[:50]}...', Truncated: '{action_url[:50]}...'"
                )
        else:
            action_url = None
        
        # Log info messages if truncation occurred (INFO level for routine internal operations)
        if len(original_subject) > 255:
            truncated_chars = len(original_subject) - 255
            logger.info(
                f"Notification subject truncated: {truncated_chars} characters removed. "
                f"Original: '{original_subject[:50]}...', Truncated: '{subject[:50]}...'"
            )
        
        if len(original_message) > 65535:
            truncated_chars = len(original_message) - 65535
            logger.info(
                f"Notification message truncated: {truncated_chars} characters removed. "
                f"Original length: {len(original_message)}, Truncated length: {len(message)}"
            )
        
        if not subject or not message:
            logger.warning("Attempted to create notification with empty subject or message")
            return False
        
        notification = Notification(
            subject=subject,
            message=message,
            unread=True,
            action_title=action_title,
            action_url=action_url
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
