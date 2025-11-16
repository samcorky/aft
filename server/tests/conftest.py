"""Pytest configuration and fixtures."""
import pytest
import requests
import time


# API base URL - tests hit the running Docker container
API_BASE_URL = "http://localhost:5000"


@pytest.fixture(scope='session', autouse=True)
def wait_for_api():
    """Wait for API to be ready before running tests."""
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


@pytest.fixture(scope='session', autouse=True)
def cleanup_all_data(wait_for_api):
    """Clean up all test data before and after entire test session."""
    # Cleanup before all tests - ensure we start with clean state
    _delete_all_data()
    time.sleep(0.2)  # Extra time to ensure cleanup completes
    
    yield
    
    # Cleanup after all tests
    _delete_all_data()


@pytest.fixture(scope='function')
def clean_database():
    """Ensure database is clean before test runs. Use this for tests that need empty DB."""
    _delete_all_data()
    time.sleep(0.15)
    yield
    # Cleanup after as well
    time.sleep(0.1)
    _delete_all_data()


@pytest.fixture(autouse=True)
def cleanup_between_tests():
    """Clean up data after each test to ensure isolation.
    
    Note: We don't clean BEFORE tests because:
    1. Session-level cleanup ensures the first test starts clean
    2. Each test's post-cleanup ensures the next test starts clean
    3. Pre-test cleanup would delete fixture data (race condition)
    
    For tests that explicitly need empty DB, use clean_database or isolated_test fixtures.
    """
    yield
    
    # Cleanup after each test (important for isolation)
    time.sleep(0.1)
    _delete_all_data()
    

@pytest.fixture
def isolated_test():
    """Fixture to ensure complete test isolation - cleans before the test."""
    _delete_all_data()
    time.sleep(0.15)
    yield


def _delete_all_data():
    """Helper to delete all boards and settings, ensuring clean state."""
    try:
        # Delete all boards (cascades to columns and cards)
        response = requests.get(f"{API_BASE_URL}/api/boards", timeout=5)
        if response.status_code == 200:
            boards = response.json().get('boards', [])
            for board in boards:
                delete_response = requests.delete(f"{API_BASE_URL}/api/boards/{board['id']}", timeout=5)
                # Wait for delete to complete
                if delete_response.status_code != 200:
                    print(f"Warning: Failed to delete board {board['id']}: {delete_response.status_code}")
        
        # Verify boards are actually deleted before proceeding
        verify_response = requests.get(f"{API_BASE_URL}/api/boards", timeout=5)
        if verify_response.status_code == 200:
            remaining = verify_response.json().get('boards', [])
            if remaining:
                print(f"Warning: {len(remaining)} boards still exist after cleanup")
        
        # Reset settings to null
        requests.put(f"{API_BASE_URL}/api/settings/default_board", 
                    json={'value': None}, 
                    timeout=5)
    except requests.exceptions.RequestException as e:
        # If cleanup fails, tests will handle it
        print(f"Warning: Cleanup failed with error: {e}")


@pytest.fixture
def api_client():
    """Provide API base URL for tests."""
    return API_BASE_URL


@pytest.fixture
def sample_board(api_client):
    """Create a sample board for testing."""
    response = requests.post(f"{api_client}/api/boards", json={
        'name': 'Test Board',
        'description': 'A test board'
    })
    assert response.status_code == 201
    board = response.json()['board']
    return board


@pytest.fixture
def sample_column(api_client, sample_board):
    """Create a sample column for testing."""
    response = requests.post(f"{api_client}/api/boards/{sample_board['id']}/columns", json={
        'name': 'Test Column'
    })
    assert response.status_code == 201, f"Failed to create column: {response.status_code} - {response.text}"
    column = response.json()['column']
    
    # Ensure board_id is in the response
    assert 'board_id' in column, f"Column response missing board_id: {column}"
    assert 'id' in column, f"Column response missing id: {column}"
    
    return column


@pytest.fixture
def sample_card(api_client, sample_column):
    """Create a sample card for testing."""
    response = requests.post(f"{api_client}/api/columns/{sample_column['id']}/cards", json={
        'title': 'Test Card',
        'description': 'A test card'
    })
    assert response.status_code == 201
    card = response.json()['card']
    return card
