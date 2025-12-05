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
    # Import here to avoid circular dependency
    from app import validate_safe_url
    
    db = SessionLocal()
    try:
        # Preserve original values before any processing
        original_subject_raw = subject
        original_message_raw = message
        original_action_title_raw = action_title
        original_action_url_raw = action_url
        
        # Strip whitespace
        subject = subject.strip()
        message = message.strip()
        
        # Truncate subject and message
        subject = subject[:255]
        message = message[:65535]
        
        # Process action fields if provided
        if action_title is not None:
            action_title = action_title.strip()
            # Set to None if empty after stripping
            if not action_title:
                action_title = None
            elif len(action_title) > 100:
                # Log truncation before truncating
                truncated_chars = len(action_title) - 100
                preview_suffix = '...' if len(action_title) > 50 else ''
                logger.info(
                    f"Notification action_title truncated: {truncated_chars} characters removed. "
                    f"Original: '{action_title[:50]}{preview_suffix}', "
                    f"Truncated: '{action_title[:100][:50]}{preview_suffix}'"
                )
                action_title = action_title[:100]
            
        if action_url is not None:
            action_url = action_url.strip()
            # Set to None if empty after stripping
            if not action_url:
                action_url = None
            else:
                # Truncate first
                if len(action_url) > 500:
                    truncated_chars = len(action_url) - 500
                    preview_suffix = '...' if len(action_url) > 50 else ''
                    logger.info(
                        f"Notification action_url truncated: {truncated_chars} characters removed. "
                        f"Original: '{action_url[:50]}{preview_suffix}', "
                        f"Truncated: '{action_url[:500][:50]}{preview_suffix}'"
                    )
                    action_url = action_url[:500]
                
                # Validate URL safety on the (possibly truncated) value
                is_valid, error_msg = validate_safe_url(action_url)
                if not is_valid:
                    logger.warning(f"Notification action_url rejected due to unsafe protocol: {action_url[:50]}")
                    action_url = None
        
        # Log info messages if truncation occurred (INFO level for routine internal operations)
        if len(original_subject_raw.strip()) > 255:
            truncated_chars = len(original_subject_raw.strip()) - 255
            preview_suffix = '...' if len(original_subject_raw.strip()) > 50 else ''
            logger.info(
                f"Notification subject truncated: {truncated_chars} characters removed. "
                f"Original: '{original_subject_raw.strip()[:50]}{preview_suffix}', "
                f"Truncated: '{subject[:50]}{preview_suffix}'"
            )
        
        if len(original_message_raw.strip()) > 65535:
            truncated_chars = len(original_message_raw.strip()) - 65535
            logger.info(
                f"Notification message truncated: {truncated_chars} characters removed. "
                f"Original length: {len(original_message_raw.strip())}, Truncated length: {len(message)}"
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
