"""Tests for board API endpoints."""
import pytest


@pytest.mark.api
class TestBoardsAPI:
    """Test cases for /api/boards endpoints."""
    
    def test_get_boards_empty(self, api_client, authenticated_session, clean_database):
        """Test getting boards when none exist."""
        response = authenticated_session.get(f'{api_client}/api/boards')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['boards'] == []
    
    def test_get_boards_with_data(self, api_client, authenticated_session, isolated_test, sample_board):
        """Test getting boards with existing data."""
        response = authenticated_session.get(f'{api_client}/api/boards')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['boards']) == 1
        assert data['boards'][0]['name'] == 'Test Board'
        assert 'created_at' in data['boards'][0]
        assert 'updated_at' in data['boards'][0]
    
    def test_create_board(self, api_client, authenticated_session):
        """Test creating a new board."""
        response = authenticated_session.post(f'{api_client}/api/boards', json={
            'name': 'New Board',
            'description': 'A new test board'
        })
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['board']['name'] == 'New Board'
        assert 'id' in data['board']
        assert 'created_at' in data['board']
        assert 'updated_at' in data['board']
    
    def test_create_board_missing_name(self, api_client, authenticated_session):
        """Test creating a board without a name fails."""
        response = authenticated_session.post(f'{api_client}/api/boards', json={
            'description': 'No name provided'
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
    
    def test_get_board_by_id(self, api_client, authenticated_session, sample_board):
        """Test getting a specific board's columns."""
        response = authenticated_session.get(f'{api_client}/api/boards/{sample_board["id"]}/columns')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'columns' in data
    
    def test_get_board_not_found(self, api_client, authenticated_session):
        """Test getting columns for a non-existent board returns 403 (no access)."""
        response = authenticated_session.get(f'{api_client}/api/boards/9999/columns')
        assert response.status_code == 403
    
    def test_update_board(self, api_client, authenticated_session, sample_board):
        """Test updating a board."""
        response = authenticated_session.patch(f'{api_client}/api/boards/{sample_board["id"]}', json={
            'name': 'Updated Board Name',
            'description': 'Updated description'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['board']['name'] == 'Updated Board Name'
    
    def test_update_board_not_found(self, api_client, authenticated_session):
        """Test updating a non-existent board returns 403 (no access)."""
        response = authenticated_session.patch(f'{api_client}/api/boards/9999', json={
            'name': 'Updated Name'
        })
        assert response.status_code == 403
    
    def test_delete_board(self, api_client, authenticated_session, sample_board):
        """Test deleting a board."""
        board_id = sample_board['id']
        response = authenticated_session.delete(f'{api_client}/api/boards/{board_id}')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify board is deleted - now returns 403 since it no longer exists in user's scope
        verify_response = authenticated_session.get(f'{api_client}/api/boards/{board_id}/columns')
        assert verify_response.status_code == 403
    
    def test_delete_board_not_found(self, api_client, authenticated_session):
        """Test deleting a non-existent board returns 403 (no access)."""
        response = authenticated_session.delete(f'{api_client}/api/boards/9999')
        assert response.status_code == 403
    
    def test_get_board_scheduled_cards(self, api_client, authenticated_session, sample_board, sample_column):
        """Test getting board with all scheduled cards in one request."""
        # First create a regular card to schedule
        card_data = {
            'title': 'Card to Schedule',
            'description': 'This will become a template'
        }
        card_response = authenticated_session.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json=card_data
        )
        assert card_response.status_code == 201
        card_id = card_response.json()['card']['id']
        
        # Create a schedule for the card (this creates the template card)
        from datetime import datetime, timedelta
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        schedule_data = {
            'card_id': card_id,
            'run_every': 1,
            'unit': 'day',
            'start_datetime': tomorrow,
            'end_datetime': None,
            'schedule_enabled': True,
            'allow_duplicates': False,
            'keep_source_card': True
        }
        schedule_response = authenticated_session.post(
            f'{api_client}/api/schedules',
            json=schedule_data
        )
        assert schedule_response.status_code == 201
        
        # Get board with scheduled cards
        response = authenticated_session.get(f'{api_client}/api/boards/{sample_board["id"]}/cards/scheduled')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'board' in data
        assert data['board']['id'] == sample_board['id']
        assert data['board']['name'] == sample_board['name']
        assert 'columns' in data['board']
        
        # Verify column structure includes cards
        column = data['board']['columns'][0]
        assert 'id' in column
        assert 'name' in column
        assert 'order' in column
        assert 'cards' in column
        assert len(column['cards']) == 1
        
        # Verify scheduled template card is returned (not the original card)
        card = column['cards'][0]
        assert card['title'] == 'Card to Schedule'
        assert card['scheduled'] is True
        assert card['schedule'] is not None
    
    def test_get_board_scheduled_cards_not_found(self, api_client, authenticated_session):
        """Test getting scheduled cards for a non-existent board returns 403 (no access)."""
        response = authenticated_session.get(f'{api_client}/api/boards/9999/cards/scheduled')
        assert response.status_code == 403

    def test_get_board_scheduled_cards_includes_assignee_filter_users(
        self,
        api_client,
        authenticated_session,
        sample_board,
        sample_column,
    ):
        """Scheduled board payload should include assignee filter users for filter UI population."""
        # Create one scheduled template card so endpoint has normal content.
        card_response = authenticated_session.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={'title': 'Scheduled Filter Users Card', 'description': 'Template source'}
        )
        assert card_response.status_code == 201

        from datetime import datetime, timedelta
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        schedule_response = authenticated_session.post(
            f'{api_client}/api/schedules',
            json={
                'card_id': card_response.json()['card']['id'],
                'run_every': 1,
                'unit': 'day',
                'start_datetime': tomorrow,
                'end_datetime': None,
                'schedule_enabled': True,
                'allow_duplicates': False,
                'keep_source_card': True,
            }
        )
        assert schedule_response.status_code == 201

        response = authenticated_session.get(f'{api_client}/api/boards/{sample_board["id"]}/cards/scheduled')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        filter_users = data['board'].get('assignee_filter_users', [])
        assert isinstance(filter_users, list)

        me_response = authenticated_session.get(f'{api_client}/api/auth/me')
        assert me_response.status_code == 200
        my_id = me_response.json()['user']['id']
        assert my_id in {u['id'] for u in filter_users}
        assert all('email' not in u for u in filter_users)

    def test_get_board_scheduled_cards_filter_includes_secondary_assignees_when_enabled(
        self,
        api_client,
        authenticated_session,
        second_user_session,
        sample_board,
        sample_column,
    ):
        """Scheduled board filtering should include secondary matches only when explicitly enabled."""
        me_response = authenticated_session.get(f'{api_client}/api/auth/me')
        assert me_response.status_code == 200
        my_id = me_response.json()['user']['id']

        second_user_me_response = second_user_session.get(f'{api_client}/api/auth/me')
        assert second_user_me_response.status_code == 200
        second_user_id = second_user_me_response.json()['user']['id']

        role_response = authenticated_session.post(
            f'{api_client}/api/users/{second_user_id}/roles',
            json={'role_name': 'board_editor', 'board_id': sample_board['id']}
        )
        assert role_response.status_code == 200, role_response.text

        # Create template source card and schedule it.
        source_card_response = authenticated_session.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={'title': 'Scheduled Secondary Filter Card', 'description': 'Template source'}
        )
        assert source_card_response.status_code == 201

        from datetime import datetime, timedelta
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        schedule_response = authenticated_session.post(
            f'{api_client}/api/schedules',
            json={
                'card_id': source_card_response.json()['card']['id'],
                'run_every': 1,
                'unit': 'day',
                'start_datetime': tomorrow,
                'end_datetime': None,
                'schedule_enabled': True,
                'allow_duplicates': False,
                'keep_source_card': True,
            }
        )
        assert schedule_response.status_code == 201

        scheduled_response = authenticated_session.get(f'{api_client}/api/boards/{sample_board["id"]}/cards/scheduled')
        assert scheduled_response.status_code == 200
        scheduled_data = scheduled_response.json()

        template_card_id = None
        for column in scheduled_data['board']['columns']:
            for card in column['cards']:
                if card['title'] == 'Scheduled Secondary Filter Card' and card['scheduled'] is True:
                    template_card_id = card['id']
                    break
            if template_card_id:
                break

        assert template_card_id is not None

        # Set primary assignee to current user and secondary to second user.
        assignee_update_response = authenticated_session.put(
            f'{api_client}/api/cards/{template_card_id}/assignees',
            json={'assigned_to_id': my_id, 'secondary_assignee_ids': [second_user_id]}
        )
        assert assignee_update_response.status_code == 200

        without_secondary_response = authenticated_session.get(
            f'{api_client}/api/boards/{sample_board["id"]}/cards/scheduled?assignee_ids={second_user_id}'
        )
        assert without_secondary_response.status_code == 200
        without_secondary_data = without_secondary_response.json()
        without_secondary_ids = {
            card['id']
            for column in without_secondary_data['board']['columns']
            for card in column['cards']
        }
        assert template_card_id not in without_secondary_ids

        with_secondary_response = authenticated_session.get(
            f'{api_client}/api/boards/{sample_board["id"]}/cards/scheduled?assignee_ids={second_user_id}&include_secondary_assignees=true'
        )
        assert with_secondary_response.status_code == 200
        with_secondary_data = with_secondary_response.json()
        with_secondary_ids = {
            card['id']
            for column in with_secondary_data['board']['columns']
            for card in column['cards']
        }
        assert template_card_id in with_secondary_ids


@pytest.mark.api
class TestBoardColumnsAPI:
    """Test cases for board column API endpoints."""
    
    def test_create_column(self, api_client, authenticated_session, sample_board):
        """Test creating a new column."""
        response = authenticated_session.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'To Do'
        })
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['column']['name'] == 'To Do'
        assert data['column']['board_id'] == sample_board['id']
    
    def test_create_column_board_not_found(self, api_client, authenticated_session):
        """Test creating a column for non-existent board returns 403 (no access)."""
        response = authenticated_session.post(f'{api_client}/api/boards/9999/columns', json={
            'name': 'To Do'
        })
        assert response.status_code == 403
    
    def test_create_column_missing_name(self, api_client, authenticated_session, sample_board):
        """Test creating a column without a name."""
        response = authenticated_session.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={})
        assert response.status_code == 400
    
    def test_update_column(self, api_client, authenticated_session, sample_column):
        """Test updating a column."""
        response = authenticated_session.patch(f'{api_client}/api/columns/{sample_column["id"]}', json={
            'name': 'Updated Column'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['column']['name'] == 'Updated Column'
    
    def test_delete_column(self, api_client, authenticated_session, sample_column):
        """Test deleting a column."""
        column_id = sample_column['id']
        board_id = sample_column['board_id']
        
        # Verify column exists first by getting board's columns
        columns_check = authenticated_session.get(f'{api_client}/api/boards/{board_id}/columns')
        assert columns_check.status_code == 200, f"Columns check failed: {columns_check.status_code} - {columns_check.text}"
        columns_before = columns_check.json()['columns']
        column_ids_before = [col['id'] for col in columns_before]
        assert column_id in column_ids_before, f"Column {column_id} not found in board before delete"
        
        # Delete the column
        response = authenticated_session.delete(f'{api_client}/api/columns/{column_id}')
        assert response.status_code == 200, f"Delete column failed: {response.status_code} - {response.text}"
        
        # Verify column is deleted by checking board's columns
        columns_after = authenticated_session.get(f'{api_client}/api/boards/{board_id}/columns')
        assert columns_after.status_code == 200, f"Columns verify failed: {columns_after.status_code} - {columns_after.text}"
        columns_data = columns_after.json()['columns']
        column_ids_after = [col['id'] for col in columns_data]
        assert column_id not in column_ids_after, f"Column {column_id} still exists in board after delete"
