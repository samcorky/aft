"""Tests for notification API endpoints."""
import pytest
import requests


@pytest.mark.api
class TestNotificationsAPI:
    """Test cases for notification API endpoints."""
    
    def test_get_notifications_empty(self, api_client, authenticated_session):
        """Test getting notifications when there are none."""
        # Delete any existing notifications via API
        authenticated_session.delete(f'{api_client}/api/notifications/delete-all')
        
        response = authenticated_session.get(f'{api_client}/api/notifications')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['notifications'] == []
    
    def test_get_notifications_with_data(self, api_client, authenticated_session, sample_notification):
        """Test getting notifications when they exist."""
        response = authenticated_session.get(f'{api_client}/api/notifications')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['notifications']) >= 1
        
        # Verify structure of returned notification
        notification = data['notifications'][0]
        assert 'id' in notification
        assert 'subject' in notification
        assert 'message' in notification
        assert 'unread' in notification
        assert 'created_at' in notification
    
    def test_get_notifications_sorted_by_newest(self, api_client, authenticated_session):
        """Test that notifications are returned sorted by created_at descending."""
        import time
        
        # Delete existing notifications via API
        authenticated_session.delete(f'{api_client}/api/notifications/delete-all')
        
        # Create notifications with time gap
        authenticated_session.post(f'{api_client}/api/notifications', json={
            "subject": "Old Notification",
            "message": "This is old"
        })
        time.sleep(1)  # Ensure different timestamps
        authenticated_session.post(f'{api_client}/api/notifications', json={
            "subject": "New Notification",
            "message": "This is new"
        })
        
        response = authenticated_session.get(f'{api_client}/api/notifications')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['notifications']) == 2
        
        # Verify newest is first (most recent creation)
        subjects = [n['subject'] for n in data['notifications']]
        assert subjects[0] == "New Notification"
        assert subjects[1] == "Old Notification"
    
    def test_create_notification_success(self, api_client, authenticated_session):
        """Test creating a notification with valid data."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test Subject",
                "message": "Test message content"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['subject'] == "Test Subject"
        assert data['notification']['message'] == "Test message content"
        assert data['notification']['unread'] is True
        assert 'id' in data['notification']
        assert 'created_at' in data['notification']
    
    def test_create_notification_missing_subject(self, api_client, authenticated_session):
        """Test creating a notification without subject."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "message": "Test message"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'subject' in data['message'].lower()
    
    def test_create_notification_missing_message(self, api_client, authenticated_session):
        """Test creating a notification without message."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test Subject"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'message' in data['message'].lower()
    
    def test_create_notification_empty_subject(self, api_client, authenticated_session):
        """Test creating a notification with empty subject after stripping."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "   ",
                "message": "Test message"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'required' in data['message'].lower()
    
    def test_create_notification_empty_message(self, api_client, authenticated_session):
        """Test creating a notification with empty message after stripping."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test Subject",
                "message": "   "
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'required' in data['message'].lower()
    
    def test_create_notification_subject_too_long(self, api_client, authenticated_session):
        """Test creating a notification with subject exceeding 255 characters."""
        long_subject = "A" * 256
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": long_subject,
                "message": "Test message"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert '255' in data['message']
    
    def test_create_notification_message_too_long(self, api_client, authenticated_session):
        """Test creating a notification with message exceeding 65535 characters."""
        long_message = "A" * 65536
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test Subject",
                "message": long_message
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert '65535' in data['message']
    
    def test_create_notification_subject_max_length(self, api_client, authenticated_session):
        """Test creating a notification with subject at max length (255 chars)."""
        max_subject = "A" * 255
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": max_subject,
                "message": "Test message"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['subject'] == max_subject
    
    def test_create_notification_strips_whitespace(self, api_client, authenticated_session):
        """Test that subject and message have leading/trailing whitespace stripped."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "  Test Subject  ",
                "message": "  Test message  "
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['subject'] == "Test Subject"
        assert data['notification']['message'] == "Test message"
    
    def test_mark_notification_as_read(self, api_client, authenticated_session, sample_notification):
        """Test marking a notification as read."""
        response = authenticated_session.put(
            f'{api_client}/api/notifications/{sample_notification["id"]}/read'
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify it's marked as read
        verify_response = authenticated_session.get(f'{api_client}/api/notifications')
        notifications = verify_response.json()['notifications']
        notification = next(n for n in notifications if n['id'] == sample_notification['id'])
        assert notification['unread'] is False
    
    def test_mark_notification_as_read_not_found(self, api_client, authenticated_session):
        """Test marking a non-existent notification as read."""
        response = authenticated_session.put(f'{api_client}/api/notifications/9999/read')
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['message'].lower()
    
    def test_mark_notification_as_unread(self, api_client, authenticated_session, sample_notification):
        """Test marking a notification as unread."""
        # First mark it as read
        authenticated_session.put(f'{api_client}/api/notifications/{sample_notification["id"]}/read')
        
        # Now mark it as unread
        response = authenticated_session.put(
            f'{api_client}/api/notifications/{sample_notification["id"]}/unread'
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify it's marked as unread
        verify_response = authenticated_session.get(f'{api_client}/api/notifications')
        notifications = verify_response.json()['notifications']
        notification = next(n for n in notifications if n['id'] == sample_notification['id'])
        assert notification['unread'] is True
    
    def test_mark_notification_as_unread_not_found(self, api_client, authenticated_session):
        """Test marking a non-existent notification as unread."""
        response = authenticated_session.put(f'{api_client}/api/notifications/9999/unread')
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['message'].lower()
    
    def test_delete_notification(self, api_client, authenticated_session, sample_notification):
        """Test deleting a notification."""
        notification_id = sample_notification["id"]
        
        response = authenticated_session.delete(f'{api_client}/api/notifications/{notification_id}')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify it's deleted
        verify_response = authenticated_session.get(f'{api_client}/api/notifications')
        notifications = verify_response.json()['notifications']
        assert not any(n['id'] == notification_id for n in notifications)
    
    def test_delete_notification_not_found(self, api_client, authenticated_session):
        """Test deleting a non-existent notification."""
        response = authenticated_session.delete(f'{api_client}/api/notifications/9999')
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['message'].lower()
    
    def test_mark_all_notifications_as_read(self, api_client, authenticated_session):
        """Test marking all notifications as read."""
        # Delete existing and create multiple unread notifications via API
        authenticated_session.delete(f'{api_client}/api/notifications/delete-all')
        
        for i in range(3):
            authenticated_session.post(f'{api_client}/api/notifications', json={
                "subject": f"Test Subject {i}",
                "message": f"Test message {i}"
            })
        
        # Mark all as read
        response = authenticated_session.put(f'{api_client}/api/notifications/mark-all-read')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['count'] == 3
        
        # Verify all are read
        verify_response = authenticated_session.get(f'{api_client}/api/notifications')
        notifications = verify_response.json()['notifications']
        assert all(not n['unread'] for n in notifications)
    
    def test_mark_all_notifications_as_read_when_none_unread(self, api_client, authenticated_session):
        """Test marking all as read when there are no unread notifications."""
        # Delete existing, create notification, and mark it as read via API
        authenticated_session.delete(f'{api_client}/api/notifications/delete-all')
        
        create_response = authenticated_session.post(f'{api_client}/api/notifications', json={
            "subject": "Test Subject",
            "message": "Test message"
        })
        notification_id = create_response.json()['notification']['id']
        authenticated_session.put(f'{api_client}/api/notifications/{notification_id}/read')
        
        response = authenticated_session.put(f'{api_client}/api/notifications/mark-all-read')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['count'] == 0
    
    def test_delete_all_notifications(self, api_client, authenticated_session):
        """Test deleting all notifications."""
        # Delete existing and create multiple notifications via API
        authenticated_session.delete(f'{api_client}/api/notifications/delete-all')
        
        for i in range(3):
            authenticated_session.post(f'{api_client}/api/notifications', json={
                "subject": f"Test Subject {i}",
                "message": f"Test message {i}"
            })
        
        # Delete all
        response = authenticated_session.delete(f'{api_client}/api/notifications/delete-all')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['count'] == 3
        
        # Verify all are deleted
        verify_response = authenticated_session.get(f'{api_client}/api/notifications')
        notifications = verify_response.json()['notifications']
        assert len(notifications) == 0
    
    def test_delete_all_notifications_when_empty(self, api_client, authenticated_session):
        """Test deleting all notifications when there are none."""
        # Ensure empty via API
        authenticated_session.delete(f'{api_client}/api/notifications/delete-all')
        
        response = authenticated_session.delete(f'{api_client}/api/notifications/delete-all')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['count'] == 0


@pytest.mark.api
class TestNotificationsEdgeCases:
    """Edge case tests for notification API endpoints."""
    
    def test_create_notification_with_special_characters(self, api_client, authenticated_session):
        """Test creating a notification with special characters."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test <script>alert('xss')</script>",
                "message": "Message with 'quotes' and \"double quotes\" & ampersand"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        # Values should be stored as-is (escaping happens on frontend)
        assert "<script>" in data['notification']['subject']
        assert "'" in data['notification']['message']
    
    def test_create_notification_with_unicode(self, api_client, authenticated_session):
        """Test creating a notification with unicode characters."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test 😀 Emoji",
                "message": "Unicode: ñ, é, ü, 中文, العربية"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert "😀" in data['notification']['subject']
        assert "中文" in data['notification']['message']
    
    def test_create_notification_with_newlines(self, api_client, authenticated_session):
        """Test creating a notification with newline characters."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test Subject",
                "message": "Line 1\nLine 2\nLine 3"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert "\n" in data['notification']['message']
    
    def test_concurrent_mark_as_read(self, api_client, authenticated_session, sample_notification):
        """Test marking the same notification as read concurrently."""
        notification_id = sample_notification["id"]
        
        # Make multiple simultaneous requests
        import concurrent.futures
        auth_cookies = authenticated_session.cookies.get_dict()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(
                    requests.put,
                    f'{api_client}/api/notifications/{notification_id}/read',
                    cookies=auth_cookies
                )
                for _ in range(3)
            ]
            results = [f.result() for f in futures]
        
        # All should succeed
        assert all(r.status_code == 200 for r in results)
        
        # Verify it's read
        verify_response = authenticated_session.get(f'{api_client}/api/notifications')
        notifications = verify_response.json()['notifications']
        notification = next(n for n in notifications if n['id'] == notification_id)
        assert notification['unread'] is False
    
    def test_notification_with_exact_max_lengths(self, api_client, authenticated_session):
        """Test notification with exactly maximum allowed lengths."""
        max_subject = "X" * 255
        max_message = "Y" * 65535
        
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": max_subject,
                "message": max_message
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert len(data['notification']['subject']) == 255
        assert len(data['notification']['message']) == 65535


@pytest.mark.api
class TestNotificationsSecurity:
    """Security tests for notification API endpoints."""
    
    def test_create_notification_sql_injection_attempt(self, api_client, authenticated_session):
        """Test that SQL injection attempts are handled safely."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "'; DROP TABLE notifications; --",
                "message": "1' OR '1'='1"
            }
        )
        # Should create successfully (SQLAlchemy protects against SQL injection)
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        
        # Verify notifications table still exists
        verify_response = authenticated_session.get(f'{api_client}/api/notifications')
        assert verify_response.status_code == 200
    
    def test_create_notification_no_internal_error_leak(self, api_client, authenticated_session):
        """Test that internal errors don't leak implementation details."""
        # Test with extremely long input that might cause internal errors
        massive_string = "A" * 1000000  # 1MB string
        
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": massive_string,
                "message": massive_string
            }
        )
        
        # Should return an error without leaking details
        assert response.status_code in [400, 500]
        data = response.json()
        assert data['success'] is False
        # Should not contain database-specific error details
        message = data['message'].lower()
        assert 'sqlalchemy' not in message
        assert 'traceback' not in message
        assert 'exception' not in message
    
    def test_invalid_notification_id_type(self, api_client, authenticated_session):
        """Test using invalid ID types in endpoints."""
        invalid_ids = ['abc', '1.5', 'null', '<script>']
        
        for invalid_id in invalid_ids:
            response = authenticated_session.delete(f'{api_client}/api/notifications/{invalid_id}')
            # Should handle gracefully (404 or 400)
            assert response.status_code in [400, 404]
            data = response.json()
            assert data['success'] is False
    
    def test_create_notification_subject_exceeds_limit(self, api_client, authenticated_session):
        """Test creating notification with subject exceeding 255 char limit is rejected."""
        # Create subject longer than 255 chars
        subject = "A" * 300
        message = "Test message for validation"
        
        response = authenticated_session.post(f'{api_client}/api/notifications', json={
            "subject": subject,
            "message": message
        })
        
        # API should reject oversized input
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Subject must be 255 characters or less' in data['message']
    
    def test_create_notification_message_exceeds_limit(self, api_client, authenticated_session):
        """Test creating notification with message exceeding 65535 char limit is rejected."""
        subject = "Test Validation"
        # Create message longer than 65535 chars
        message = "B" * 70000
        
        response = authenticated_session.post(f'{api_client}/api/notifications', json={
            "subject": subject,
            "message": message
        })
        
        # API should reject oversized input
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Message must be 65535 characters or less' in data['message']
    
    def test_create_notification_both_exceed_limits(self, api_client, authenticated_session):
        """Test creating notification with both subject and message exceeding limits is rejected."""
        subject = "X" * 300
        message = "Y" * 70000
        
        response = authenticated_session.post(f'{api_client}/api/notifications', json={
            "subject": subject,
            "message": message
        })
        
        # API should reject oversized input (validates subject first)
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert '255 characters or less' in data['message']
    
    def test_create_notification_at_exact_limits(self, api_client, authenticated_session):
        """Test creating notification at exact character limits is accepted."""
        subject = "A" * 255
        message = "B" * 65535
        
        response = authenticated_session.post(f'{api_client}/api/notifications', json={
            "subject": subject,
            "message": message
        })
        
        # API should accept input at exact limits
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert 'notification' in data
        
        # Verify no truncation occurred
        notification = data['notification']
        assert len(notification['subject']) == 255
        assert len(notification['message']) == 65535
        assert notification['subject'] == subject
        assert notification['message'] == message


@pytest.mark.api
class TestNotificationActions:
    """Test cases for notification action fields."""
    
    def test_create_notification_with_action(self, api_client, authenticated_session):
        """Test creating a notification with action title and URL."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "New Feature",
                "message": "Check out our new feature!",
                "action_title": "Learn More",
                "action_url": "/features"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['action_title'] == "Learn More"
        assert data['notification']['action_url'] == "/features"
    
    def test_create_notification_without_action(self, api_client, authenticated_session):
        """Test creating a notification without action fields."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Simple Notification",
                "message": "Just a message"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['action_title'] is None
        assert data['notification']['action_url'] is None
    
    def test_create_notification_action_title_too_long(self, api_client, authenticated_session):
        """Test creating a notification with action title exceeding 100 characters."""
        long_title = "A" * 101
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": long_title,
                "action_url": "/test"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert '100' in data['message']
    
    def test_create_notification_action_url_too_long(self, api_client, authenticated_session):
        """Test creating a notification with action URL exceeding 500 characters."""
        long_url = "A" * 501
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": long_url
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert '500' in data['message']
    
    def test_create_notification_action_title_max_length(self, api_client, authenticated_session):
        """Test creating a notification with action title at max length (100 chars)."""
        max_title = "A" * 100
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": max_title,
                "action_url": "/test"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['action_title'] == max_title
    
    def test_create_notification_action_url_max_length(self, api_client, authenticated_session):
        """Test creating a notification with action URL at max length (500 chars)."""
        # Create a valid relative URL at max length (500 chars starting with /)
        max_url = "/" + "a" * 499
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": max_url
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['action_url'] == max_url
        assert len(data['notification']['action_url']) == 500
    
    def test_create_notification_action_title_strips_whitespace(self, api_client, authenticated_session):
        """Test that action title has whitespace stripped."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "  Click Here  ",
                "action_url": "/test"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['action_title'] == "Click Here"
    
    def test_create_notification_empty_action_title(self, api_client, authenticated_session):
        """Test creating a notification with empty action title after stripping."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "   ",
                "action_url": "/test"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        # Empty after stripping should be treated as None
        assert data['notification']['action_title'] is None
    
    def test_create_notification_empty_action_url(self, api_client, authenticated_session):
        """Test creating a notification with empty action URL after stripping."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": "   "
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        # Empty after stripping should be treated as None
        assert data['notification']['action_url'] is None
    
    def test_get_notifications_includes_action_fields(self, api_client, authenticated_session):
        """Test that GET /api/notifications includes action fields."""
        # Create notification with action
        authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "View Details",
                "action_url": "/details"
            }
        )
        
        # Get all notifications
        response = authenticated_session.get(f'{api_client}/api/notifications')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Find our notification
        notification = next(
            (n for n in data['notifications'] if n['subject'] == 'Test'),
            None
        )
        assert notification is not None
        assert notification['action_title'] == "View Details"
        assert notification['action_url'] == "/details"
    
    def test_create_notification_action_title_over_recommended_length(self, api_client, authenticated_session):
        """Test that action title over 50 chars (recommended max) still succeeds but logs warning."""
        # 51 chars (over recommended but under hard limit)
        title = "A" * 51
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": title,
                "action_url": "/test"
            }
        )
        # Should succeed since it's under hard limit of 100
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['action_title'] == title


@pytest.mark.api
class TestNotificationSecurityURLValidation:
    """Security tests for notification action URL validation."""
    
    def test_create_notification_with_javascript_protocol(self, api_client, authenticated_session):
        """Test that javascript: URLs are rejected."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": "javascript:alert('XSS')"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'javascript:' in data['message'].lower()
    
    def test_create_notification_with_data_protocol(self, api_client, authenticated_session):
        """Test that data: URLs are rejected."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": "data:text/html,<script>alert('XSS')</script>"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'data:' in data['message'].lower()
    
    def test_create_notification_with_vbscript_protocol(self, api_client, authenticated_session):
        """Test that vbscript: URLs are rejected."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": "vbscript:msgbox('XSS')"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'vbscript:' in data['message'].lower()
    
    def test_create_notification_with_file_protocol(self, api_client, authenticated_session):
        """Test that file: URLs are rejected."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": "file:///etc/passwd"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'file:' in data['message'].lower()
    
    def test_create_notification_with_about_protocol(self, api_client, authenticated_session):
        """Test that about: URLs are rejected."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": "about:blank"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_create_notification_with_blob_protocol(self, api_client, authenticated_session):
        """Test that blob: URLs are rejected."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": "blob:https://example.com/test"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_create_notification_with_relative_url(self, api_client, authenticated_session):
        """Test that relative URLs starting with / are accepted."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "View Page",
                "action_url": "/settings"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['action_url'] == "/settings"
    
    def test_create_notification_with_http_url(self, api_client, authenticated_session):
        """Test that http:// URLs are accepted."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Visit",
                "action_url": "http://example.com"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['action_url'] == "http://example.com"
    
    def test_create_notification_with_https_url(self, api_client, authenticated_session):
        """Test that https:// URLs are accepted."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Visit",
                "action_url": "https://example.com"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['notification']['action_url'] == "https://example.com"
    
    def test_create_notification_with_uppercase_javascript_protocol(self, api_client, authenticated_session):
        """Test that JavaScript: URLs (case variation) are rejected."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": "JavaScript:alert('XSS')"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_create_notification_with_mixed_case_data_protocol(self, api_client, authenticated_session):
        """Test that DaTa: URLs (case variation) are rejected."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": "DaTa:text/html,<script>alert('XSS')</script>"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_create_notification_with_protocol_only_url(self, api_client, authenticated_session):
        """Test that URLs without proper structure after protocol are rejected."""
        response = authenticated_session.post(
            f'{api_client}/api/notifications',
            json={
                "subject": "Test",
                "message": "Test message",
                "action_title": "Click",
                "action_url": "ftp://test.com"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
