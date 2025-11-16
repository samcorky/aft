# Testing Guide

## Overview

This test suite performs **API integration testing** by making HTTP requests to the running Docker container. Tests validate the external behavior of the API endpoints rather than internal code coverage.

## Running Tests Locally (Recommended)

### Prerequisites

1. **Python 3.11+** installed on your machine
2. **Docker containers running** for the database and API server:
```powershell
docker compose up -d
```
   - The API must be running at `http://localhost:5000`
   - Wait a few seconds for the server to be ready

### Setup Local Environment

1. **Create virtual environment** (one-time setup):
```powershell
cd server
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. **Install development dependencies** (includes pytest and test tools):
```powershell
pip install -r requirements-dev.txt
```

3. **Configure VS Code** (optional):
   - Select Python interpreter: `Ctrl+Shift+P` → "Python: Select Interpreter"
   - Choose: `.\server\venv\Scripts\python.exe`
   - Tests will auto-discover in the Testing panel

### Run Tests

```powershell
cd server
.\venv\Scripts\Activate.ps1

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with detailed output and stop on first failure
pytest -v -x

# Run specific test file
pytest tests/test_api_boards.py -v
```

### Note on Coverage

**Coverage reporting is not applicable** for these tests because they make HTTP requests to an external server (Docker container). The tests validate API behavior, not internal code paths. This is the correct approach for API integration testing.

### Run Specific Test Categories

```powershell
# Run only API tests
pytest -m api

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration
```

### Run Specific Test Files

```powershell
# Test boards API
pytest tests/test_api_boards.py

# Test cards API
pytest tests/test_api_cards.py

# Test settings API
pytest tests/test_api_settings.py
```

### Run Specific Test Functions

```powershell
# Run a specific test by name
pytest tests/test_api_boards.py::TestBoardsAPI::test_create_board

# Run tests matching a pattern
pytest -k "test_create"

# Run with extra verbosity to see request/response details
pytest -v -s
```

## VS Code Integration

Tests are configured to work with VS Code's Testing panel:

1. Ensure Docker containers are running: `docker compose up -d`
2. Open the Testing view (beaker icon in sidebar)
3. Tests will auto-discover
4. Click play buttons to run individual tests or test suites

### VS Code Test Features

- ✅ Run tests from the UI
- ✅ Debug tests with breakpoints
- ✅ Auto-discover tests on save
- ✅ View test results inline
- ✅ Navigate to failed tests

**Note**: When running tests from VS Code, they may occasionally fail due to timing issues. Running from command line (`pytest tests/`) is more reliable for full test suite execution.

## Test Architecture

These are **API integration tests** that:
- Make real HTTP requests to `http://localhost:5000`
- Test the running Docker container, not Python code directly
- Validate API behavior, status codes, and response data
- Automatically clean up test data between runs

### Test Isolation Strategy

- **Session cleanup**: Cleans all data before test suite starts
- **Test cleanup**: Cleans all data after each test completes
- **Explicit fixtures**: `clean_database` and `isolated_test` for tests needing guaranteed clean state
- **Data fixtures**: `sample_board`, `sample_column`, `sample_card` create test data as needed

## Test Structure

```
server/tests/
├── __init__.py              # Test package
├── conftest.py              # Pytest fixtures and configuration
├── test_api_boards.py       # Board and column API endpoint tests
├── test_api_cards.py        # Card API endpoint tests
└── test_api_settings.py     # Settings API endpoint tests
```

## Available Fixtures

Defined in `conftest.py`:

- `api_client` - Base URL for API (`http://localhost:5000`)
- `clean_database` - Ensures database is empty before test runs
- `isolated_test` - Ensures database is clean before fixtures create data
- `sample_board` - Creates a test board via API
- `sample_column` - Creates a test column via API (requires `sample_board`)
- `sample_card` - Creates a test card via API (requires `sample_column`)

## Writing New Tests

### Example API Test

```python
import requests
import pytest

@pytest.mark.api
class TestMyAPI:
    def test_my_endpoint(self, api_client):
        """Test description."""
        response = requests.get(f'{api_client}/api/my-endpoint')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
    
    def test_with_clean_database(self, api_client, clean_database):
        """Test that needs empty database."""
        response = requests.get(f'{api_client}/api/boards')
        assert response.json()['boards'] == []
    
    def test_with_data(self, api_client, isolated_test, sample_board):
        """Test with exactly one board."""
        response = requests.get(f'{api_client}/api/boards')
        assert len(response.json()['boards']) == 1
```

## Continuous Integration

Tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Start services
  run: docker compose up -d

- name: Wait for API
  run: |
    timeout 30 bash -c 'until curl -f http://localhost:5000/api/version; do sleep 1; done'

- name: Setup Python
  uses: actions/setup-python@v4
  with:
    python-version: '3.11'

- name: Install dependencies
  run: |
    cd server
    pip install -r requirements-dev.txt

- name: Run tests
  run: |
    cd server
    pytest -v
```

## Troubleshooting

### API Connection Issues

If tests fail with connection errors:
```powershell
# Check if API is running
curl http://localhost:5000/api/version

# Restart containers
docker compose restart

# View logs
docker compose logs server
```

### Tests Fail Randomly in VS Code

The command line is more reliable. Run tests via:
```powershell
cd server
pytest tests/ -v
```

### Database State Issues

Tests automatically clean up, but if you need to manually reset:
```powershell
# Restart database container
docker compose restart db

# Or recreate all containers
docker compose down
docker compose up -d
```

### Permission Errors on Windows

If you see `.coverage` permission errors:
- This is expected - coverage doesn't work for API tests
- Tests will still run successfully
- You can disable coverage in `pytest.ini` if it bothers you
