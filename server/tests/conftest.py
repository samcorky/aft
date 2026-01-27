"""Pytest configuration and fixtures."""
import pytest
import requests
import time


# API base URL - tests hit through nginx like external API clients would
# This mimics how external tools/UIs would access the API (via 80/443, not internal 5000)
API_BASE_URL = "http://localhost"

# Cleanup timing constants (in seconds)
# These delays ensure async operations complete before proceeding
CLEANUP_DELAY_SHORT = 0.1    # Standard delay after test cleanup
CLEANUP_DELAY_MEDIUM = 0.15  # Delay for explicit clean operations
CLEANUP_DELAY_LONG = 0.2     # Delay for session-level initialization


@pytest.fixture(scope='session')
def wait_for_api(request):
    """Wait for API to be ready before running tests (API tests only)."""
    # Only run for API tests
    if 'unit' in request.keywords:
        return
    
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get(f"{API_BASE_URL}/api/version", timeout=1)
            if response.status_code == 200:
                return
        except requests.exceptions.RequestException:
            if i < max_retries - 1:
                time.sleep(1)
            else:
                raise Exception("API not available after 30 seconds")


@pytest.fixture(scope='session')
def test_admin_session(request, wait_for_api):
    """Create or login as test admin user and return authenticated session (API tests only).
    
    This fixture handles three scenarios:
    1. Fresh install (no users): Creates test admin via setup endpoint
    2. Test admin exists: Logs in with known credentials
    3. Other users exist but not test admin: Creates test admin via register endpoint
    
    The test admin credentials are:
    - Email: test-admin@localhost
    - Username: test-admin
    - Password: TestAdmin123!
    """
    # Only run for API tests
    if 'unit' in request.keywords:
        return None
    
    session = requests.Session()
    
    try:
        # Check if setup is needed
        setup_response = session.get(f"{API_BASE_URL}/api/auth/setup/status")
        if setup_response.status_code != 200:
            raise Exception(
                f"\n{'='*70}\n"
                f"AUTHENTICATION SETUP FAILED\n"
                f"{'='*70}\n"
                f"Could not check setup status (HTTP {setup_response.status_code})\n"
                f"The authentication system may not be running or configured correctly.\n"
                f"Make sure the API server is running: docker compose up -d\n"
                f"{'='*70}\n"
            )
        
        setup_data = setup_response.json()
        
        # If setup not complete (no users exist), create admin user via setup
        if not setup_data.get('setup_complete', False):
            print("\n[Test Setup] No users found - creating test admin user...")
            admin_response = session.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
                "email": "test-admin@localhost",
                "username": "test-admin",
                "password": "TestAdmin123!",
                "display_name": "Test Admin"
            })
            if admin_response.status_code not in (200, 201):
                raise Exception(
                    f"\n{'='*70}\n"
                    f"AUTHENTICATION SETUP FAILED\n"
                    f"{'='*70}\n"
                    f"Failed to create test admin user via setup endpoint.\n"
                    f"HTTP Status: {admin_response.status_code}\n"
                    f"Response: {admin_response.text}\n\n"
                    f"This usually means:\n"
                    f"  1. The authentication API is not properly configured\n"
                    f"  2. The database migrations have not been run\n"
                    f"  3. There's a permission or validation error\n\n"
                    f"Try resetting the database:\n"
                    f"  docker compose down\n"
                    f"  Remove-Item -Recurse -Force data\n"
                    f"  docker compose up -d\n"
                    f"{'='*70}\n"
                )
            print("[Test Setup] Test admin user created successfully")
        else:
            # Users exist - try to login as test admin
            print("\n[Test Setup] Users exist - logging in as test admin...")
            login_response = session.post(f"{API_BASE_URL}/api/auth/login", json={
                "email": "test-admin@localhost",
                "password": "TestAdmin123!"
            })
            
            # If login fails, test admin doesn't exist - can't proceed
            if login_response.status_code != 200:
                # Cannot create test admin when other users exist - would require approval
                pytest.exit(
                    f"\n{'='*70}\n"
                    f"AUTHENTICATION SETUP FAILED - FRESH DATABASE REQUIRED\n"
                    f"{'='*70}\n\n"
                    f"Cannot create test admin user because other users already exist.\n"
                    f"When users exist, new registrations require admin approval.\n\n"
                    f"SOLUTION: Reset the database AND sessions to start fresh:\n\n"
                    f"  # Windows PowerShell:\n"
                    f"  docker compose down\n"
                    f"  Remove-Item -Recurse -Force data\n"
                    f"  docker compose up -d\n\n"
                    f"  # Linux/macOS:\n"
                    f"  docker compose down\n"
                    f"  rm -rf data\n"
                    f"  docker compose up -d\n\n"
                    f"NOTE: docker compose down clears Redis sessions automatically.\n"
                    f"Then run tests again. The test suite will automatically create\n"
                    f"the test admin user on the fresh database.\n\n"
                    f"{'='*70}\n",
                    returncode=1
                )
            print("[Test Setup] Successfully logged in as test admin")
        
        return session
    
    except requests.exceptions.RequestException as e:
        raise Exception(
            f"\n{'='*70}\n"
            f"AUTHENTICATION SETUP FAILED\n"
            f"{'='*70}\n"
            f"Network error while setting up authentication.\n"
            f"Error: {str(e)}\n\n"
            f"Make sure the API server is running:\n"
            f"  docker compose up -d\n\n"
            f"Check that the API is accessible at: {API_BASE_URL}\n"
            f"{'='*70}\n"
        )
    except Exception as e:
        # Re-raise if already formatted
        if "AUTHENTICATION SETUP FAILED" in str(e):
            raise
        # Otherwise, wrap in our format
        raise Exception(
            f"\n{'='*70}\n"
            f"AUTHENTICATION SETUP FAILED\n"
            f"{'='*70}\n"
            f"Unexpected error during authentication setup.\n"
            f"Error: {str(e)}\n"
            f"{'='*70}\n"
        )


@pytest.fixture(scope='session')
def cleanup_all_data(request, test_admin_session):
    """Clean up all test data before and after entire test session (API tests only)."""
    # Only run for API tests
    if 'unit' in request.keywords:
        return
    
    # Cleanup before all tests - ensure we start with clean state
    _delete_all_data(test_admin_session)
    time.sleep(CLEANUP_DELAY_LONG)  # Extra time to ensure cleanup completes
    
    yield
    
    # Cleanup after all tests
    _delete_all_data(test_admin_session)


@pytest.fixture
def authenticated_session(test_admin_session):
    """Provide authenticated session for individual tests (API tests only).
    
    Verifies the session is still valid, and if not (e.g., after DB reset),
    recreates the test admin user and re-authenticates.
    """
    # Check if session is still valid
    check_response = test_admin_session.get(f"{API_BASE_URL}/api/auth/check")
    
    # If session is invalid (503 = no users, 401 = not authenticated)
    if check_response.status_code in (503, 401):
        print(f"\n[Test Setup] Session invalid (HTTP {check_response.status_code}) - recreating test admin...")
        
        # Clear cookies
        test_admin_session.cookies.clear()
        
        # Check if we need to create admin (no users exist)
        setup_response = test_admin_session.get(f"{API_BASE_URL}/api/auth/setup/status")
        if setup_response.status_code == 200:
            setup_data = setup_response.json()
            
            if not setup_data.get('setup_complete', False):
                # Create admin via setup
                admin_response = test_admin_session.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
                    "email": "test-admin@localhost",
                    "username": "test-admin",
                    "password": "TestAdmin123!",
                    "display_name": "Test Admin"
                })
                if admin_response.status_code not in (200, 201):
                    raise Exception(f"Failed to recreate test admin: HTTP {admin_response.status_code}")
                print("[Test Setup] Test admin recreated successfully")
            else:
                # Admin exists, just login
                login_response = test_admin_session.post(f"{API_BASE_URL}/api/auth/login", json={
                    "email": "test-admin@localhost",
                    "password": "TestAdmin123!"
                })
                if login_response.status_code != 200:
                    raise Exception(f"Failed to login as test admin: HTTP {login_response.status_code}")
                print("[Test Setup] Logged in as test admin successfully")
        
        # Verify session is now valid
        verify_response = test_admin_session.get(f"{API_BASE_URL}/api/auth/check")
        if verify_response.status_code != 200:
            raise Exception(f"Session still invalid after recreation: HTTP {verify_response.status_code}")
    
    return test_admin_session


@pytest.fixture
def clean_database(request, test_admin_session):
    """Ensure database is clean before test runs. Use this for tests that need empty DB (API tests only)."""
    # Only run for API tests
    if 'unit' in request.keywords:
        return
    
    _delete_all_data(test_admin_session)
    time.sleep(CLEANUP_DELAY_MEDIUM)
    yield
    # Cleanup after as well
    time.sleep(CLEANUP_DELAY_SHORT)
    _delete_all_data(test_admin_session)


@pytest.fixture(autouse=True)
def cleanup_between_tests(request, test_admin_session):
    """Clean up data after each test to ensure isolation (API tests only).
    
    Note: We don't clean BEFORE tests because:
    1. Session-level cleanup ensures the first test starts clean
    2. Each test's post-cleanup ensures the next test starts clean
    3. Pre-test cleanup would delete fixture data (race condition)
    
    For tests that explicitly need empty DB, use clean_database or isolated_test fixtures.
    """
    yield
    
    # Only cleanup for API tests
    if 'unit' not in request.keywords:
        # Skip cleanup if test uses empty_database fixture (it handles its own cleanup)
        if 'empty_database' in request.fixturenames:
            return
        
        # Cleanup after each test (important for isolation)
        time.sleep(CLEANUP_DELAY_SHORT)
        _delete_all_data(test_admin_session)
    

@pytest.fixture
def isolated_test(test_admin_session):
    """Fixture to ensure complete test isolation - cleans before the test."""
    _delete_all_data(test_admin_session)
    time.sleep(CLEANUP_DELAY_MEDIUM)
    yield


def _delete_all_data(session=None):
    """Helper to delete all boards, notifications and settings, ensuring clean state.
    
    Args:
        session: Optional authenticated requests.Session. If None, uses unauthenticated requests.
    """
    # Use provided session or fallback to requests module
    http = session if session else requests
    
    try:
        # Delete all boards (cascades to columns and cards)
        response = http.get(f"{API_BASE_URL}/api/boards", timeout=5)
        if response.status_code == 200:
            boards = response.json().get('boards', [])
            for board in boards:
                delete_response = http.delete(f"{API_BASE_URL}/api/boards/{board['id']}", timeout=5)
                # Wait for delete to complete
                if delete_response.status_code != 200:
                    print(f"Warning: Failed to delete board {board['id']}: {delete_response.status_code}")
        
        # Verify boards are actually deleted before proceeding
        verify_response = http.get(f"{API_BASE_URL}/api/boards", timeout=5)
        if verify_response.status_code == 200:
            remaining = verify_response.json().get('boards', [])
            if remaining:
                print(f"Warning: {len(remaining)} boards still exist after cleanup")
        
        # Delete all notifications
        delete_notif_response = http.delete(f"{API_BASE_URL}/api/notifications/delete-all", timeout=5)
        if delete_notif_response.status_code != 200:
            print(f"Warning: Failed to delete notifications: {delete_notif_response.status_code}")
        
        # Reset settings to defaults
        http.put(f"{API_BASE_URL}/api/settings/default_board", 
                    json={'value': None}, 
                    timeout=5)
        
        # Reset backup settings to migration defaults
        # This ensures tests start with known state matching fresh install
        http.put(f"{API_BASE_URL}/api/settings/backup/config",
                    json={
                        'enabled': False,
                        'frequency_value': 1,
                        'frequency_unit': 'daily',
                        'start_time': '00:00',
                        'retention_count': 7,
                        'minimum_free_space_mb': 100
                    },
                    timeout=5)
    except requests.exceptions.RequestException as e:
        # If cleanup fails, tests will handle it
        print(f"Warning: Cleanup failed with error: {e}")


@pytest.fixture
def api_client():
    """Provide API base URL for tests."""
    return API_BASE_URL


@pytest.fixture
def sample_board(api_client, authenticated_session):
    """Create a sample board for testing."""
    response = authenticated_session.post(f"{api_client}/api/boards", json={
        'name': 'Test Board',
        'description': 'A test board'
    })
    assert response.status_code == 201
    board = response.json()['board']
    return board


@pytest.fixture
def sample_column(api_client, authenticated_session, sample_board):
    """Create a sample column for testing."""
    response = authenticated_session.post(f"{api_client}/api/boards/{sample_board['id']}/columns", json={
        'name': 'Test Column'
    })
    assert response.status_code == 201, f"Failed to create column: {response.status_code} - {response.text}"
    column = response.json()['column']
    
    # Ensure board_id is in the response
    assert 'board_id' in column, f"Column response missing board_id: {column}"
    assert 'id' in column, f"Column response missing id: {column}"
    
    return column


@pytest.fixture
def sample_card(api_client, authenticated_session, sample_column):
    """Create a sample card for testing."""
    response = authenticated_session.post(f"{api_client}/api/columns/{sample_column['id']}/cards", json={
        'title': 'Test Card',
        'description': 'A test card'
    })
    assert response.status_code == 201
    card = response.json()['card']
    return card


@pytest.fixture
def sample_notification(api_client, authenticated_session):
    """Create a sample notification for testing."""
    response = authenticated_session.post(f"{api_client}/api/notifications", json={
        'subject': 'Test Notification',
        'message': 'This is a test notification'
    })
    assert response.status_code == 201
    notification = response.json()['notification']
    return notification
