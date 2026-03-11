"""
Tests for authentication API endpoints.

Tests the following endpoints:
- POST /api/auth/setup/admin - First-time admin setup
- GET /api/auth/setup/status - Check if setup is complete
- POST /api/auth/register - User registration
- POST /api/auth/login - User login
- POST /api/auth/logout - User logout
- GET /api/auth/check - Check authentication status
- GET /api/auth/me - Get current user info
- POST /api/auth/change-password - Change password
"""
import pytest
import requests
import time

# API base URL - matching conftest.py
API_BASE_URL = "http://localhost"


@pytest.fixture
def empty_database(authenticated_session, test_admin_session):
    """Delete all data including users for tests that need truly empty DB.
    
    Note: This fixture is ONLY for authentication tests. It deletes all users
    including the test-admin, then recreates test-admin after the test completes.
    We also need to refresh the session cookies since the old ones are invalid.
    """
    # Delete all data including users using the authenticated admin session.
    response = authenticated_session.delete(f"{API_BASE_URL}/api/database")
    if response.status_code != 200:
        raise AssertionError(
            f"Failed to reset database for auth test: {response.status_code} - {response.text}"
        )
    time.sleep(0.6)
    
    yield
    
    # CRITICAL: Recreate test admin after this test so other tests don't fail
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Check if setup is needed
            status = requests.get(f"{API_BASE_URL}/api/auth/setup/status", timeout=5)
            if status.status_code == 200 and not status.json().get('setup_complete', False):
                # Recreate test admin
                resp = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
                    "email": "test-admin@localhost",
                    "username": "test-admin",
                    "password": "TestAdmin123!",
                    "display_name": "Test Admin"
                }, timeout=5)
                
                # Update the shared session with new cookies from the recreated admin
                # The setup endpoint auto-logs in, but we need to ensure cookies are fresh
                if resp.status_code == 201:
                    # Clear old cookies first
                    test_admin_session.cookies.clear()
                    test_admin_session.cookies.update(resp.cookies)
                    
                    # Do an explicit login to ensure session is fully established
                    login_resp = test_admin_session.post(f"{API_BASE_URL}/api/auth/login", json={
                        "email": "test-admin@localhost",
                        "password": "TestAdmin123!"
                    }, timeout=5)
                    
                    if login_resp.status_code == 200:
                        # Clear again and use login cookies
                        test_admin_session.cookies.clear()
                        test_admin_session.cookies.update(login_resp.cookies)
                        time.sleep(0.3)
                        
                        # Verify the session works
                        verify = test_admin_session.get(f"{API_BASE_URL}/api/auth/check")
                        if verify.status_code == 200 and verify.json().get('authenticated'):
                            print(f"[Test Cleanup] Session verified after admin recreation")
                            break  # Success!
                    else:
                        print(f"[Test Cleanup] Session verification failed after admin recreation")
            else:
                # Setup already complete
                print(f"[Test Cleanup] Setup already complete, skipping recreation")
                break
        except Exception as e:
            print(f"[Test Cleanup] Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                # Last attempt failed - this is CRITICAL, must fail loudly
                import traceback
                error_msg = f"\nCRITICAL: Failed to recreate test admin after empty_database cleanup!\n{traceback.format_exc()}\nSubsequent tests WILL fail with 401/503 errors."
                print(error_msg)
                # Raise to make this failure visible
                raise Exception(error_msg)
            time.sleep(0.3)  # Wait before retry


class TestSetupFlow:
    """Test first-time setup flow."""
    
    def test_setup_status_no_users(self, empty_database):
        """Setup status should indicate setup needed when no users exist."""
        response = requests.get(f"{API_BASE_URL}/api/auth/setup/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data['setup_complete'] is False
        assert data['has_users'] is False
    
    def test_setup_admin_validation(self, empty_database):
        """Admin setup should validate input."""
        # Missing email
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "username": "admin",
            "password": "password123"
        })
        assert response.status_code == 400
        assert 'email' in response.json()['message'].lower()
        
        # Missing username
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "email": "admin@localhost",
            "password": "password123"
        })
        assert response.status_code == 400
        assert 'username' in response.json()['message'].lower()
        
        # Missing password
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "email": "admin@localhost",
            "username": "admin"
        })
        assert response.status_code == 400
        assert 'password' in response.json()['message'].lower()
        
        # Password too short
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "email": "admin@localhost",
            "username": "admin",
            "password": "123"
        })
        assert response.status_code == 400
        assert 'password' in response.json()['message'].lower()
    
    def test_setup_admin_success(self, empty_database):
        """Admin setup should create admin user."""
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "email": "admin@localhost",
            "username": "admin",
            "password": "AdminPass123!"
        })
        assert response.status_code == 201
        
        data = response.json()
        assert data['success'] is True
        assert 'user' in data
        assert data['user']['email'] == "admin@localhost"
        assert data['user']['username'] == "admin"
    
    def test_setup_status_with_users(self):
        """Setup status should indicate complete when users exist."""
        response = requests.get(f"{API_BASE_URL}/api/auth/setup/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data['setup_complete'] is True
        assert data['has_users'] is True
    
    def test_setup_admin_already_complete(self):
        """Admin setup should fail when already complete."""
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "email": "another@localhost",
            "username": "another",
            "password": "password123"
        })
        assert response.status_code == 403
        assert 'already' in response.json()['message'].lower()


class TestRegistration:
    """Test user registration."""
    
    def test_register_validation(self):
        """Registration should validate input."""
        # Missing email
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "username": "user1",
            "password": "password123"
        })
        assert response.status_code == 400
        assert 'email' in response.json()['message'].lower()
        
        # Missing username
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "user1@test.com",
            "password": "password123"
        })
        assert response.status_code == 400
        assert 'username' in response.json()['message'].lower()
        
        # Missing password
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "user1@test.com",
            "username": "user1"
        })
        assert response.status_code == 400
        assert 'password' in response.json()['message'].lower()
    
    def test_register_success(self):
        """User registration should create pending user."""
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "user1@test.com",
            "username": "testuser",
            "password": "UserPass123!"
        })
        assert response.status_code == 201
        
        data = response.json()
        assert data['success'] is True
        assert 'user' in data
        assert data['user']['email'] == "user1@test.com"
        assert data['user']['username'] == "testuser"
        assert data['user']['requires_approval'] is True  # Pending approval
    
    def test_register_duplicate_email(self):
        """Registration should prevent duplicate emails."""
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "user1@test.com",  # Already registered
            "username": "different",
            "password": "password123"
        })
        assert response.status_code == 409
        assert 'email' in response.json()['message'].lower()
    
    def test_register_duplicate_username(self):
        """Registration should prevent duplicate usernames."""
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "different@test.com",
            "username": "testuser",  # Already taken
            "password": "password123"
        })
        assert response.status_code == 409
        assert 'username' in response.json()['message'].lower()


class TestLogin:
    """Test user login."""
    
    @pytest.fixture
    def session(self):
        """Create a session for maintaining cookies."""
        return requests.Session()
    
    def test_login_not_approved(self, session):
        """Login should fail for unapproved users."""
        response = session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "user1@test.com",
            "password": "UserPass123!"
        })
        assert response.status_code == 403
        assert 'approved' in response.json()['message'].lower()
    
    def test_login_invalid_credentials(self, session):
        """Login should fail with wrong password."""
        response = session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "WrongPassword"
        })
        assert response.status_code == 401
        assert 'invalid' in response.json()['message'].lower()
    
    def test_login_success(self, session):
        """Login should succeed with correct credentials."""
        response = session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "AdminPass123!"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'user' in data
        assert data['user']['email'] == "admin@localhost"
        
        # Check session cookie was set
        assert 'session' in session.cookies
    
    def test_check_authenticated(self, session):
        """Auth check should return True when logged in."""
        # Login first
        session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "AdminPass123!"
        })
        
        # Check auth status
        response = session.get(f"{API_BASE_URL}/api/auth/check")
        assert response.status_code == 200
        
        data = response.json()
        assert data['authenticated'] is True
    
    def test_me_endpoint(self, session):
        """Me endpoint should return current user info."""
        # Login first
        session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "AdminPass123!"
        })
        
        # Get user info
        response = session.get(f"{API_BASE_URL}/api/auth/me")
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'user' in data
        assert data['user']['email'] == "admin@localhost"
        assert 'roles' in data['user']
    
    def test_logout(self, session):
        """Logout should clear session."""
        # Login first
        session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "AdminPass123!"
        })
        
        # Logout
        response = session.post(f"{API_BASE_URL}/api/auth/logout")
        assert response.status_code == 200
        assert response.json()['success'] is True
        
        # Check auth status after logout
        response = session.get(f"{API_BASE_URL}/api/auth/check")
        data = response.json()
        assert data['authenticated'] is False


class TestPasswordChange:
    """Test password change functionality."""
    
    @pytest.fixture
    def authenticated_session(self):
        """Create an authenticated session."""
        session = requests.Session()
        session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "AdminPass123!"
        })
        return session
    
    def test_change_password_unauthenticated(self):
        """Password change should require authentication."""
        session = requests.Session()
        response = session.post(f"{API_BASE_URL}/api/auth/change-password", json={
            "current_password": "AdminPass123!",
            "new_password": "NewPass456!"
        })
        assert response.status_code == 401
    
    def test_change_password_wrong_current(self, authenticated_session):
        """Password change should fail with wrong current password."""
        response = authenticated_session.post(f"{API_BASE_URL}/api/auth/change-password", json={
            "current_password": "WrongPassword",
            "new_password": "NewPass456!"
        })
        assert response.status_code == 401
        assert 'current password' in response.json()['message'].lower()
    
    def test_change_password_validation(self, authenticated_session):
        """Password change should validate new password."""
        # Too short
        response = authenticated_session.post(f"{API_BASE_URL}/api/auth/change-password", json={
            "current_password": "AdminPass123!",
            "new_password": "123"
        })
        assert response.status_code == 400
    
    def test_change_password_success(self, authenticated_session):
        """Password change should work with valid input."""
        response = authenticated_session.post(f"{API_BASE_URL}/api/auth/change-password", json={
            "current_password": "AdminPass123!",
            "new_password": "NewAdminPass456!"
        })
        assert response.status_code == 200
        assert response.json()['success'] is True
        
        # Verify old password no longer works
        new_session = requests.Session()
        response = new_session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "AdminPass123!"
        })
        assert response.status_code == 401
        
        # Verify new password works
        response = new_session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "NewAdminPass456!"
        })
        assert response.status_code == 200


class TestAuthenticationFlow:
    """Test complete authentication flow."""
    
    def test_full_user_journey(self):
        """Test complete user lifecycle."""
        session = requests.Session()
        
        # 1. Check not authenticated
        response = session.get(f"{API_BASE_URL}/api/auth/check")
        assert response.json()['authenticated'] is False
        
        # 2. Register new user
        response = session.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "journey@test.com",
            "username": "journeyuser",
            "password": "JourneyPass123!"
        })
        assert response.status_code == 201
        
        # 3. Try to login (should fail - not approved)
        response = session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "journey@test.com",
            "password": "JourneyPass123!"
        })
        assert response.status_code == 403
        
        # 4. Admin approves user (this will be tested in user_management tests)
        # For now, just verify the flow stops at approval requirement
        
        # 5. Login with admin to test their flow
        admin_session = requests.Session()
        response = admin_session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "NewAdminPass456!"
        })
        assert response.status_code == 200
        
        # 6. Get admin info
        response = admin_session.get(f"{API_BASE_URL}/api/auth/me")
        assert response.status_code == 200
        assert 'administrator' in [r['name'] for r in response.json()['user']['roles']]
        
        # 7. Logout
        response = admin_session.post(f"{API_BASE_URL}/api/auth/logout")
        assert response.status_code == 200
        
        # 8. Verify logged out
        response = admin_session.get(f"{API_BASE_URL}/api/auth/check")
        assert response.json()['authenticated'] is False
