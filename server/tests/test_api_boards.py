"""Tests for board API endpoints."""
import pytest
import requests


@pytest.mark.api
class TestBoardsAPI:
    """Test cases for /api/boards endpoints."""
    
    def test_get_boards_empty(self, api_client, clean_database):
        """Test getting boards when none exist."""
        response = requests.get(f'{api_client}/api/boards')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['boards'] == []
    
    def test_get_boards_with_data(self, api_client, isolated_test, sample_board):
        """Test getting boards with existing data."""
        response = requests.get(f'{api_client}/api/boards')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['boards']) == 1
        assert data['boards'][0]['name'] == 'Test Board'
    
    def test_create_board(self, api_client):
        """Test creating a new board."""
        response = requests.post(f'{api_client}/api/boards', json={
            'name': 'New Board',
            'description': 'A new test board'
        })
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['board']['name'] == 'New Board'
        assert 'id' in data['board']
    
    def test_create_board_missing_name(self, api_client):
        """Test creating a board without a name fails."""
        response = requests.post(f'{api_client}/api/boards', json={
            'description': 'No name provided'
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_get_board_by_id(self, api_client, sample_board):
        """Test getting a specific board's columns."""
        response = requests.get(f'{api_client}/api/boards/{sample_board["id"]}/columns')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'columns' in data
    
    def test_get_board_not_found(self, api_client):
        """Test getting columns for a non-existent board returns empty list."""
        response = requests.get(f'{api_client}/api/boards/9999/columns')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['columns'] == []
    
    def test_update_board(self, api_client, sample_board):
        """Test updating a board."""
        response = requests.patch(f'{api_client}/api/boards/{sample_board["id"]}', json={
            'name': 'Updated Board Name',
            'description': 'Updated description'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['board']['name'] == 'Updated Board Name'
    
    def test_update_board_not_found(self, api_client):
        """Test updating a non-existent board."""
        response = requests.patch(f'{api_client}/api/boards/9999', json={
            'name': 'Updated Name'
        })
        assert response.status_code == 404
    
    def test_delete_board(self, api_client, sample_board):
        """Test deleting a board."""
        board_id = sample_board['id']
        response = requests.delete(f'{api_client}/api/boards/{board_id}')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify board is deleted by checking columns endpoint returns empty
        verify_response = requests.get(f'{api_client}/api/boards/{board_id}/columns')
        assert verify_response.status_code == 200
        assert verify_response.json()['columns'] == []
    
    def test_delete_board_not_found(self, api_client):
        """Test deleting a non-existent board."""
        response = requests.delete(f'{api_client}/api/boards/9999')
        assert response.status_code == 404


@pytest.mark.api
class TestBoardColumnsAPI:
    """Test cases for board column API endpoints."""
    
    def test_create_column(self, api_client, sample_board):
        """Test creating a new column."""
        response = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'To Do'
        })
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['column']['name'] == 'To Do'
        assert data['column']['board_id'] == sample_board['id']
    
    def test_create_column_board_not_found(self, api_client):
        """Test creating a column for non-existent board."""
        response = requests.post(f'{api_client}/api/boards/9999/columns', json={
            'name': 'To Do'
        })
        assert response.status_code == 404
    
    def test_create_column_missing_name(self, api_client, sample_board):
        """Test creating a column without a name."""
        response = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={})
        assert response.status_code == 400
    
    def test_update_column(self, api_client, sample_column):
        """Test updating a column."""
        response = requests.patch(f'{api_client}/api/columns/{sample_column["id"]}', json={
            'name': 'Updated Column'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['column']['name'] == 'Updated Column'
    
    def test_delete_column(self, api_client, sample_column):
        """Test deleting a column."""
        column_id = sample_column['id']
        board_id = sample_column['board_id']
        
        # Verify column exists first by getting board's columns
        columns_check = requests.get(f'{api_client}/api/boards/{board_id}/columns')
        assert columns_check.status_code == 200, f"Columns check failed: {columns_check.status_code} - {columns_check.text}"
        columns_before = columns_check.json()['columns']
        column_ids_before = [col['id'] for col in columns_before]
        assert column_id in column_ids_before, f"Column {column_id} not found in board before delete"
        
        # Delete the column
        response = requests.delete(f'{api_client}/api/columns/{column_id}')
        assert response.status_code == 200, f"Delete column failed: {response.status_code} - {response.text}"
        
        # Verify column is deleted by checking board's columns
        columns_after = requests.get(f'{api_client}/api/boards/{board_id}/columns')
        assert columns_after.status_code == 200, f"Columns verify failed: {columns_after.status_code} - {columns_after.text}"
        columns_data = columns_after.json()['columns']
        column_ids_after = [col['id'] for col in columns_data]
        assert column_id not in column_ids_after, f"Column {column_id} still exists in board after delete"
