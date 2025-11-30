# Testing Guidelines

This document outlines testing standards and best practices for the AFT application.

## Testing Philosophy

- **Test Behavior, Not Implementation**: Focus on what the code does, not how it does it
- **API-Only Tests**: Integration tests should only interact with APIs, not directly with filesystems or databases
- **Comprehensive Coverage**: Test happy paths, edge cases, error conditions, and security scenarios
- **Isolation**: Tests should not depend on each other or external state
- **Clarity**: Test names should clearly describe what is being tested

## Test Organization

```
server/tests/
├── conftest.py                           # Shared fixtures and configuration
├── test_api_*.py                         # API endpoint tests
├── test_utils.py                         # Utility function tests
└── test_*_permissions.py                 # Permission and security tests
```

### Naming Conventions

- **Test Files**: `test_<feature>.py`
- **Test Classes**: `Test<FeatureName>` (e.g., `TestBackupAPI`)
- **Test Methods**: `test_<action>_<expected_result>` (e.g., `test_create_backup_success`)

## Test Structure

### Standard Test Pattern

```python
import pytest
import requests


@pytest.mark.api
class TestFeatureAPI:
    """Test cases for feature API endpoints."""
    
    def test_operation_success(self, api_client):
        """Test successful operation with valid input."""
        # Arrange - Set up test data
        test_data = {"name": "Test Item"}
        
        # Act - Execute the operation
        response = requests.post(f'{api_client}/api/resource', json=test_data)
        
        # Assert - Verify the results
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'id' in data
        
        # Cleanup - Remove test data if needed
        try:
            requests.delete(f'{api_client}/api/resource/{data["id"]}')
        except Exception:
            pass
    
    def test_operation_invalid_input(self, api_client):
        """Test operation with invalid input returns appropriate error."""
        # Arrange
        invalid_data = {"name": ""}
        
        # Act
        response = requests.post(f'{api_client}/api/resource', json=invalid_data)
        
        # Assert
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'message' in data
```

## API Testing Best Practices

### 1. API-Only Interactions

❌ **DON'T** access filesystem or database directly:

```python
# Bad - direct filesystem access
backup_path = Path("/app/backups") / filename
assert backup_path.exists()
```

✅ **DO** validate through API responses:

```python
# Good - validate via API
list_response = requests.get(f'{api_client}/api/database/backups/list')
list_data = list_response.json()
filenames = [b['filename'] for b in list_data['backups']]
assert filename in filenames
```

### 2. Cleanup

Always clean up test data, even if the test fails:

```python
def test_with_cleanup(self, api_client):
    created_ids = []
    
    try:
        # Create test resources
        response = requests.post(f'{api_client}/api/resource', json=test_data)
        created_ids.append(response.json()['id'])
        
        # Perform test operations
        # ...
        
    finally:
        # Cleanup
        for resource_id in created_ids:
            try:
                requests.delete(f'{api_client}/api/resource/{resource_id}')
            except Exception:
                pass
```

### 3. Timing-Sensitive Operations

For operations that require unique timestamps:

```python
import time

def test_multiple_backups(self, api_client):
    backup_files = []
    
    try:
        # Create multiple backups with unique timestamps
        for i in range(3):
            response = requests.post(f'{api_client}/api/database/backup/manual')
            backup_files.append(response.json()['filename'])
            # Ensure unique timestamp for next backup
            if i < 2:
                time.sleep(1.1)
        
        # Test operations
        # ...
        
    finally:
        # Cleanup
        for filename in backup_files:
            try:
                requests.delete(f'{api_client}/api/database/backups/delete/{filename}')
            except Exception:
                pass
```

### 4. Testing Error Responses

Always verify error response structure:

```python
def test_operation_not_found(self, api_client):
    """Test operation on non-existent resource."""
    response = requests.get(f'{api_client}/api/resource/99999')
    
    assert response.status_code == 404
    
    # Verify JSON response even for errors
    data = response.json()
    assert data['success'] is False
    assert 'message' in data
```

### 5. Testing Invalid Input

Test various forms of invalid input:

```python
def test_operation_invalid_filename(self, api_client):
    """Test operation rejects invalid filename formats."""
    invalid_filenames = [
        "invalid_backup.sql",
        "../etc/passwd",
        "backup_123.sql",
        "aft_backup_invalid.sql",
    ]
    
    for filename in invalid_filenames:
        response = requests.delete(
            f'{api_client}/api/database/backups/delete/{filename}'
        )
        # May return 400 (invalid) or 404 (not found after URL encoding)
        assert response.status_code in [400, 404]
        
        # Verify error response
        data = response.json()
        assert data['success'] is False
```

## Security Testing

### Path Traversal Attacks

```python
def test_prevents_path_traversal(self, api_client):
    """Test that path traversal attempts are blocked."""
    path_traversal_attempts = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "valid_name/../../../etc/passwd",
    ]
    
    for attempt in path_traversal_attempts:
        response = requests.delete(
            f'{api_client}/api/resource/{attempt}'
        )
        # Should be rejected with 400 or 404
        assert response.status_code in [400, 404]
        
        data = response.json()
        assert data['success'] is False
```

### Input Validation

```python
def test_rejects_oversized_input(self, api_client):
    """Test that oversized input is rejected."""
    oversized_data = {
        "name": "x" * 10000  # Exceeds max length
    }
    
    response = requests.post(f'{api_client}/api/resource', json=oversized_data)
    
    assert response.status_code == 400
    data = response.json()
    assert data['success'] is False
    assert 'too long' in data['message'].lower()
```

### SQL Injection Prevention

```python
def test_prevents_sql_injection(self, api_client):
    """Test that SQL injection attempts are safely handled."""
    sql_injection_attempts = [
        "'; DROP TABLE boards; --",
        "1' OR '1'='1",
        "admin'--",
    ]
    
    for attempt in sql_injection_attempts:
        response = requests.post(
            f'{api_client}/api/resource',
            json={"name": attempt}
        )
        
        # Should either succeed (storing as string) or reject
        assert response.status_code in [200, 400]
        
        # Verify database integrity is maintained
        list_response = requests.get(f'{api_client}/api/resources')
        assert list_response.status_code == 200
```

## Integration Testing

### Workflow Tests

Test complete workflows from start to finish:

```python
def test_complete_workflow(self, api_client):
    """Test complete resource lifecycle: create, read, update, delete."""
    created_id = None
    
    try:
        # Step 1: Create resource
        create_response = requests.post(
            f'{api_client}/api/resource',
            json={"name": "Test Resource"}
        )
        assert create_response.status_code == 200
        create_data = create_response.json()
        created_id = create_data['id']
        
        # Step 2: Read resource
        read_response = requests.get(f'{api_client}/api/resource/{created_id}')
        assert read_response.status_code == 200
        read_data = read_response.json()
        assert read_data['name'] == "Test Resource"
        
        # Step 3: Update resource
        update_response = requests.put(
            f'{api_client}/api/resource/{created_id}',
            json={"name": "Updated Resource"}
        )
        assert update_response.status_code == 200
        
        # Step 4: Verify update
        verify_response = requests.get(f'{api_client}/api/resource/{created_id}')
        verify_data = verify_response.json()
        assert verify_data['name'] == "Updated Resource"
        
        # Step 5: Delete resource
        delete_response = requests.delete(f'{api_client}/api/resource/{created_id}')
        assert delete_response.status_code == 200
        
        # Step 6: Verify deletion
        verify_delete_response = requests.get(f'{api_client}/api/resource/{created_id}')
        assert verify_delete_response.status_code == 404
        
        created_id = None  # Cleared successfully
        
    finally:
        # Cleanup if test failed
        if created_id:
            try:
                requests.delete(f'{api_client}/api/resource/{created_id}')
            except Exception:
                pass
```

## Test Coverage Requirements

### Minimum Coverage

Every API endpoint must have tests for:

- ✅ **Happy Path**: Valid input, successful operation
- ✅ **Invalid Input**: Missing fields, wrong types, empty values
- ✅ **Not Found**: Operations on non-existent resources
- ✅ **Validation**: Boundary conditions (min/max lengths, values)
- ✅ **Error Handling**: Server errors are caught and reported correctly

### Recommended Additional Coverage

- **Edge Cases**: Unusual but valid inputs
- **Concurrent Operations**: Race conditions, double deletes
- **State Changes**: Verify state transitions
- **Side Effects**: Verify related data is updated correctly
- **Security**: Path traversal, injection attempts

## Running Tests

### Run All Tests

```bash
cd server
pytest -v
```

### Run Specific Test File

```bash
pytest tests/test_api_boards.py -v
```

### Run Specific Test Class

```bash
pytest tests/test_api_boards.py::TestBoardsAPI -v
```

### Run Specific Test Method

```bash
pytest tests/test_api_boards.py::TestBoardsAPI::test_create_board_success -v
```

### Run Tests with Coverage

```bash
pytest --cov=. --cov-report=html
```

### Run Only API Tests

```bash
pytest -m api -v
```

## Test Fixtures

### Using the API Client Fixture

The `api_client` fixture provides the base URL for API calls:

```python
@pytest.fixture
def api_client():
    """Provides the base URL for API endpoints."""
    return "http://localhost:5000"


def test_example(api_client):
    response = requests.get(f'{api_client}/api/health')
    assert response.status_code == 200
```

### Custom Fixtures

Create reusable fixtures for common setup:

```python
@pytest.fixture
def sample_board(api_client):
    """Creates a sample board for testing, cleans up after."""
    response = requests.post(
        f'{api_client}/api/boards',
        json={"name": "Test Board"}
    )
    board = response.json()
    
    yield board
    
    # Cleanup
    try:
        requests.delete(f'{api_client}/api/boards/{board["id"]}')
    except Exception:
        pass


def test_with_board(api_client, sample_board):
    """Test that uses the sample_board fixture."""
    response = requests.get(f'{api_client}/api/boards/{sample_board["id"]}')
    assert response.status_code == 200
```

## Common Testing Patterns

### Testing List Operations

```python
def test_list_includes_created_item(self, api_client):
    """Test that created item appears in list."""
    created_id = None
    
    try:
        # Create item
        create_response = requests.post(
            f'{api_client}/api/resources',
            json={"name": "Test Item"}
        )
        created_id = create_response.json()['id']
        
        # Get list
        list_response = requests.get(f'{api_client}/api/resources')
        items = list_response.json()['resources']
        
        # Verify item is in list
        item_ids = [item['id'] for item in items]
        assert created_id in item_ids
        
    finally:
        if created_id:
            try:
                requests.delete(f'{api_client}/api/resources/{created_id}')
            except Exception:
                pass
```

### Testing Pagination

```python
def test_pagination(self, api_client):
    """Test that pagination works correctly."""
    created_ids = []
    
    try:
        # Create multiple items
        for i in range(15):
            response = requests.post(
                f'{api_client}/api/resources',
                json={"name": f"Item {i}"}
            )
            created_ids.append(response.json()['id'])
        
        # Test first page
        page1 = requests.get(f'{api_client}/api/resources?page=1&per_page=10')
        assert len(page1.json()['resources']) == 10
        
        # Test second page
        page2 = requests.get(f'{api_client}/api/resources?page=2&per_page=10')
        assert len(page2.json()['resources']) == 5
        
    finally:
        for resource_id in created_ids:
            try:
                requests.delete(f'{api_client}/api/resources/{resource_id}')
            except Exception:
                pass
```

### Testing Ordering

```python
def test_ordering(self, api_client):
    """Test that items are returned in correct order."""
    created_ids = []
    
    try:
        # Create items with specific order
        for i in range(3):
            response = requests.post(
                f'{api_client}/api/resources',
                json={"name": f"Item {i}", "order": i}
            )
            created_ids.append(response.json()['id'])
        
        # Get list
        response = requests.get(f'{api_client}/api/resources')
        items = response.json()['resources']
        
        # Verify order
        for i, item in enumerate(items):
            if item['id'] in created_ids:
                expected_name = f"Item {item['order']}"
                assert item['name'] == expected_name
        
    finally:
        for resource_id in created_ids:
            try:
                requests.delete(f'{api_client}/api/resources/{resource_id}')
            except Exception:
                pass
```

## Debugging Failed Tests

### Verbose Output

```bash
pytest -vv --tb=long
```

### Show Print Statements

```bash
pytest -s
```

### Stop on First Failure

```bash
pytest -x
```

### Run Last Failed Tests

```bash
pytest --lf
```

### Debug Mode

```python
import pytest

def test_example(api_client):
    response = requests.get(f'{api_client}/api/health')
    
    # Drop into debugger
    import pdb; pdb.set_trace()
    
    assert response.status_code == 200
```

## Continuous Integration

Tests should be run automatically in CI/CD:

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        cd server
        pytest --cov=. --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

## Best Practices Summary

1. ✅ **API-Only**: Never access filesystem or database directly in integration tests
2. ✅ **Cleanup**: Always clean up test data in `finally` blocks
3. ✅ **Isolation**: Tests should not depend on each other
4. ✅ **Descriptive Names**: Test names should describe what is being tested
5. ✅ **Assertions**: Include clear assertion messages
6. ✅ **Coverage**: Test happy path, errors, edge cases, and security
7. ✅ **Timing**: Add delays for operations requiring unique timestamps
8. ✅ **Error Handling**: Verify error responses have correct structure
9. ✅ **Documentation**: Include docstrings explaining what each test validates
10. ✅ **Maintainability**: Keep tests simple and focused on one thing

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [requests Documentation](https://requests.readthedocs.io/)
- [AFT Security Guidelines](./server/SECURITY.md)
- [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/)

**Last Updated**: 2025-11-30
