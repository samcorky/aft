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


@pytest.fixture(scope="module")
def clean_database():
    """Start with a clean database for auth tests."""
    # Delete all data including users
    try:
        response = requests.delete(f"{API_BASE_URL}/api/database")
        if response.status_code == 200:
            time.sleep(0.5)  # Wait for cleanup
    except:
        pass
    
    yield
    
    # Cleanup after tests
    try:
        requests.delete(f"{API_BASE_URL}/api/database")
    except:
        pass


class TestSetupFlow:
    """Test first-time setup flow."""
    
    def test_setup_status_no_users(self, clean_database):
        """Setup status should indicate setup needed when no users exist."""
        response = requests.get(f"{API_BASE_URL}/api/auth/setup/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert data['setup_complete'] is False
        assert data['requires_setup'] is True
    
    def test_setup_admin_validation(self):
        """Admin setup should validate input."""
        # Missing email
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "username": "admin",
            "password": "password123"
        })
        assert response.status_code == 400
        assert 'email' in response.json()['error'].lower()
        
        # Missing username
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "email": "admin@localhost",
            "password": "password123"
        })
        assert response.status_code == 400
        assert 'username' in response.json()['error'].lower()
        
        # Missing password
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "email": "admin@localhost",
            "username": "admin"
        })
        assert response.status_code == 400
        assert 'password' in response.json()['error'].lower()
        
        # Password too short
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "email": "admin@localhost",
            "username": "admin",
            "password": "123"
        })
        assert response.status_code == 400
        assert 'password' in response.json()['error'].lower()
    
    def test_setup_admin_success(self):
        """Admin setup should create admin user."""
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "email": "admin@localhost",
            "username": "admin",
            "password": "AdminPass123!"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'user' in data
        assert data['user']['email'] == "admin@localhost"
        assert data['user']['username'] == "admin"
        assert data['user']['is_active'] is True
        assert data['user']['is_approved'] is True
    
    def test_setup_status_with_users(self):
        """Setup status should indicate complete when users exist."""
        response = requests.get(f"{API_BASE_URL}/api/auth/setup/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert data['setup_complete'] is True
        assert data['requires_setup'] is False
    
    def test_setup_admin_already_complete(self):
        """Admin setup should fail when already complete."""
        response = requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
            "email": "another@localhost",
            "username": "another",
            "password": "password123"
        })
        assert response.status_code == 400
        assert 'already' in response.json()['error'].lower()


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
        
        # Missing username
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "user1@test.com",
            "password": "password123"
        })
        assert response.status_code == 400
        
        # Invalid email
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "not-an-email",
            "username": "user1",
            "password": "password123"
        })
        assert response.status_code == 400
    
    def test_register_success(self):
        """User registration should create pending user."""
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "user1@test.com",
            "username": "testuser",
            "password": "UserPass123!"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'user' in data
        assert data['user']['email'] == "user1@test.com"
        assert data['user']['username'] == "testuser"
        assert data['user']['is_approved'] is False  # Pending approval
    
    def test_register_duplicate_email(self):
        """Registration should prevent duplicate emails."""
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "user1@test.com",  # Already registered
            "username": "different",
            "password": "password123"
        })
        assert response.status_code == 400
        assert 'email' in response.json()['error'].lower()
    
    def test_register_duplicate_username(self):
        """Registration should prevent duplicate usernames."""
        response = requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": "different@test.com",
            "username": "testuser",  # Already taken
            "password": "password123"
        })
        assert response.status_code == 400
        assert 'username' in response.json()['error'].lower()


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
        assert 'approved' in response.json()['error'].lower()
    
    def test_login_invalid_credentials(self, session):
        """Login should fail with wrong password."""
        response = session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "WrongPassword"
        })
        assert response.status_code == 401
        assert 'invalid' in response.json()['error'].lower()
    
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
        assert 'permissions' in data['user']
    
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
        assert response.status_code == 400
        assert 'current password' in response.json()['error'].lower()
    
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
        assert response.status_code == 200
        
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
