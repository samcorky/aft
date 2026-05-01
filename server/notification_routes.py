"""Notification API routes extracted from app.py."""

import logging

from flask import Blueprint, g, jsonify, request

from database import SessionLocal
from models import Notification, User
from permissions import has_permission
from security_validators import validate_safe_url
from utils import (
    create_error_response,
    get_current_user_id,
    get_user_permissions,
    get_user_scoped_query,
    require_authentication,
)

logger = logging.getLogger(__name__)

notification_bp = Blueprint("notification_routes", __name__)


@notification_bp.route("/api/notifications", methods=["GET"])
@require_authentication
def get_notifications():
    """Get all notifications for the current user."""
    db = SessionLocal()
    try:
        user_id = g.user.id
        notifications = (
            get_user_scoped_query(db, Notification, user_id)
            .order_by(Notification.created_at.desc())
            .all()
        )

        return jsonify(
            {
                "success": True,
                "notifications": [
                    {
                        "id": n.id,
                        "subject": n.subject,
                        "message": n.message,
                        "unread": n.unread,
                        "created_at": n.created_at.isoformat() if n.created_at else None,
                        "action_title": n.action_title,
                        "action_url": n.action_url,
                    }
                    for n in notifications
                ],
            }
        ), 200

    except Exception as e:
        logger.error(f"Error getting notifications: {str(e)}")
        return jsonify({"success": False, "message": "Failed to retrieve notifications"}), 500
    finally:
        db.close()


@notification_bp.route("/api/notifications", methods=["POST"])
@require_authentication
def create_notification():
    """Create a new notification."""
    db = SessionLocal()
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400

        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()
        for_all_users = data.get('for_all_users', False)

        if not isinstance(for_all_users, bool):
            return jsonify({"success": False, "message": "for_all_users must be a boolean"}), 400

        if not subject or not message:
            return jsonify({"success": False, "message": "Subject and message are required"}), 400

        if len(subject) > 255:
            return jsonify({"success": False, "message": "Subject must be 255 characters or less"}), 400

        if len(message) > 65535:
            return jsonify({"success": False, "message": "Message must be 65535 characters or less"}), 400

        action_title = data.get('action_title', '').strip() or None if 'action_title' in data else None
        action_url = data.get('action_url', '').strip() or None if 'action_url' in data else None

        if action_title is not None:
            if len(action_title) > 100:
                return jsonify({"success": False, "message": "Action title must be 100 characters or less"}), 400
            if len(action_title) > 50:
                logger.warning(f"Action title exceeds recommended length of 50 chars: {len(action_title)} chars")

        if action_url is not None:
            if len(action_url) > 500:
                return jsonify({"success": False, "message": "Action URL must be 500 characters or less"}), 400
            is_valid, error_msg = validate_safe_url(action_url)
            if not is_valid:
                return jsonify({"success": False, "message": f"Invalid action URL: {error_msg}"}), 400

        if for_all_users:
            user_permissions = get_user_permissions(g.user.id)
            if not has_permission(user_permissions, 'system.admin'):
                return jsonify({
                    "success": False,
                    "message": "Only administrators can create notifications for all users"
                }), 403

            target_user_ids = [
                user_id for (user_id,) in db.query(User.id)
                .filter(User.is_active.is_(True), User.is_approved.is_(True))
                .all()
            ]

            if not target_user_ids:
                return jsonify({
                    "success": False,
                    "message": "No eligible users found to receive notification"
                }), 400
        else:
            current_user_id = get_current_user_id()
            logger.info(f"Creating notification for current user only: user_id={current_user_id}, subject='{subject}'")
            target_user_ids = [current_user_id]

        created_ids = []
        for user_id in target_user_ids:
            notification = Notification(
                subject=subject,
                message=message,
                unread=True,
                action_title=action_title,
                action_url=action_url,
                user_id=user_id,
            )
            db.add(notification)
            db.flush()
            created_ids.append(notification.id)

        db.commit()

        logger.info(f"Created notification for {len(created_ids)} user(s): {subject}")

        response_data = {
            "success": True,
            "message": f"Notification created for {len(created_ids)} user(s)",
            "count": len(created_ids),
        }

        if len(created_ids) == 1:
            response_data["notification_id"] = created_ids[0]
        else:
            response_data["notification_ids"] = created_ids

        return jsonify(response_data), 201

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating notification: {str(e)}")
        return jsonify({"success": False, "message": "Failed to create notification"}), 500
    finally:
        db.close()


@notification_bp.route("/api/notifications/<int:notification_id>/read", methods=["PUT"])
@require_authentication
def mark_notification_read(notification_id):
    """Mark a notification as read."""
    db = SessionLocal()
    try:
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == get_current_user_id()
        ).first()

        if not notification:
            return create_error_response("Notification not found", 404)

        notification.unread = False
        db.commit()

        logger.info(f"Notification {notification_id} marked as read")
        return jsonify({"success": True, "message": "Notification marked as read"}), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error marking notification {notification_id} as read: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@notification_bp.route("/api/notifications/<int:notification_id>/unread", methods=["PUT"])
@require_authentication
def mark_notification_unread(notification_id):
    """Mark a notification as unread."""
    db = SessionLocal()
    try:
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == get_current_user_id()
        ).first()

        if not notification:
            return create_error_response("Notification not found", 404)

        notification.unread = True
        db.commit()

        logger.info(f"Notification {notification_id} marked as unread")
        return jsonify({"success": True, "message": "Notification marked as unread"}), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error marking notification {notification_id} as unread: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@notification_bp.route("/api/notifications/<int:notification_id>", methods=["DELETE"])
@require_authentication
def delete_notification(notification_id):
    """Delete a notification."""
    db = SessionLocal()
    try:
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == get_current_user_id()
        ).first()

        if not notification:
            return create_error_response("Notification not found", 404)

        db.delete(notification)
        db.commit()

        logger.info(f"Notification {notification_id} deleted")
        return jsonify({"success": True, "message": "Notification deleted successfully"}), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting notification {notification_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@notification_bp.route("/api/notifications/mark-all-read", methods=["PUT"])
@require_authentication
def mark_all_notifications_read():
    """Mark all notifications as read."""
    db = SessionLocal()
    try:
        current_user_id = get_current_user_id()
        result = db.query(Notification).filter(
            Notification.unread.is_(True),
            Notification.user_id == current_user_id
        ).update({"unread": False})
        db.commit()

        logger.info(f"Marked {result} notifications as read")
        return jsonify({
            "success": True,
            "message": "All notifications marked as read",
            "count": result,
        }), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error marking all notifications as read: {str(e)}")
        return jsonify({"success": False, "message": "Failed to mark all notifications as read"}), 500
    finally:
        db.close()


@notification_bp.route("/api/notifications/delete-all", methods=["DELETE"])
@require_authentication
def delete_all_notifications():
    """Delete all notifications for the current user."""
    db = SessionLocal()
    try:
        current_user_id = get_current_user_id()
        result = db.query(Notification).filter(
            Notification.user_id == current_user_id
        ).delete()
        db.commit()

        logger.info(f"Deleted {result} notifications")
        return jsonify({
            "success": True,
            "message": "All notifications deleted",
            "count": result,
        }), 200

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting all notifications: {str(e)}")
        return jsonify({"success": False, "message": "Failed to delete all notifications"}), 500
    finally:
        db.close()