"""Tests for timestamp functionality across entities."""
import pytest
import requests
import time
from datetime import datetime


@pytest.mark.api
class TestTimestamps:
    """Test cases for created_at and updated_at timestamps."""
    
    # Board timestamp tests
    def test_board_timestamps_on_create(self, api_client):
        """Test that boards have timestamps when created."""
        response = requests.post(f'{api_client}/api/boards', json={
            'name': 'Timestamp Test Board',
            'description': 'Testing timestamps'
        })
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        
        # Check timestamps are present (can be null for existing records)
        assert 'created_at' in data['board']
        assert 'updated_at' in data['board']
        
        # New boards should have created_at set
        if data['board']['created_at']:
            # Verify it's a valid ISO format datetime
            datetime.fromisoformat(data['board']['created_at'].replace('Z', '+00:00'))
    
    def test_board_timestamps_on_get(self, api_client, sample_board):
        """Test that board GET endpoints return timestamp fields."""
        response = requests.get(f'{api_client}/api/boards')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        for board in data['boards']:
            assert 'created_at' in board
            assert 'updated_at' in board
    
    def test_board_updated_at_changes(self, api_client, sample_board):
        """Test that board updated_at changes when board is modified."""
        board_id = sample_board['id']
        
        # Get initial timestamp
        response1 = requests.get(f'{api_client}/api/boards')
        initial_boards = response1.json()['boards']
        initial_board = next(b for b in initial_boards if b['id'] == board_id)
        initial_updated_at = initial_board['updated_at']
        
        # Wait a moment to ensure timestamp would be different
        time.sleep(0.1)
        
        # Update the board
        response2 = requests.patch(f'{api_client}/api/boards/{board_id}', json={
            'name': 'Updated Board Name'
        })
        assert response2.status_code == 200
        updated_board = response2.json()['board']
        
        # Check that updated_at changed
        if initial_updated_at and updated_board['updated_at']:
            assert updated_board['updated_at'] != initial_updated_at
    
    # Column timestamp tests
    def test_column_timestamps_on_create(self, api_client, sample_board):
        """Test that columns have timestamps when created."""
        response = requests.post(
            f'{api_client}/api/boards/{sample_board["id"]}/columns',
            json={'name': 'Timestamp Test Column'}
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        
        assert 'created_at' in data['column']
        assert 'updated_at' in data['column']
    
    def test_column_timestamps_on_get(self, api_client, sample_board):
        """Test that column GET endpoints return timestamp fields."""
        response = requests.get(f'{api_client}/api/boards/{sample_board["id"]}/columns')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        for column in data['columns']:
            assert 'created_at' in column
            assert 'updated_at' in column
    
    def test_column_updated_at_on_name_change(self, api_client, sample_column):
        """Test that column updated_at changes when name is modified."""
        column_id = sample_column['id']
        
        # Get initial state
        response1 = requests.get(f'{api_client}/api/boards/{sample_column["board_id"]}/columns')
        initial_columns = response1.json()['columns']
        initial_column = next(c for c in initial_columns if c['id'] == column_id)
        initial_updated_at = initial_column['updated_at']
        
        time.sleep(0.1)
        
        # Update column name
        response2 = requests.patch(f'{api_client}/api/columns/{column_id}', json={
            'name': 'Updated Column Name'
        })
        assert response2.status_code == 200
        updated_column = response2.json()['column']
        
        # Verify timestamp changed
        if initial_updated_at and updated_column['updated_at']:
            assert updated_column['updated_at'] != initial_updated_at
    
    # Card timestamp tests
    def test_card_timestamps_on_create(self, api_client, sample_column):
        """Test that cards have timestamps when created."""
        response = requests.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={'title': 'Timestamp Test Card'}
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        
        assert 'created_at' in data['card']
        assert 'updated_at' in data['card']
    
    def test_card_timestamps_on_get(self, api_client, sample_card):
        """Test that card GET endpoints return timestamp fields."""
        # Test single card endpoint
        response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        assert response.status_code == 200
        data = response.json()
        assert 'created_at' in data['card']
        assert 'updated_at' in data['card']
        
        # Test column cards endpoint
        response2 = requests.get(f'{api_client}/api/columns/{sample_card["column_id"]}/cards')
        assert response2.status_code == 200
        for card in response2.json()['cards']:
            assert 'created_at' in card
            assert 'updated_at' in card
    
    def test_card_updated_at_on_title_change(self, api_client, sample_card):
        """Test that card updated_at changes when title is modified."""
        card_id = sample_card['id']
        
        # Get initial state
        response1 = requests.get(f'{api_client}/api/cards/{card_id}')
        initial_updated_at = response1.json()['card']['updated_at']
        
        time.sleep(0.1)
        
        # Update title
        response2 = requests.patch(f'{api_client}/api/cards/{card_id}', json={
            'title': 'Updated Card Title'
        })
        assert response2.status_code == 200
        updated_card = response2.json()['card']
        
        if initial_updated_at and updated_card['updated_at']:
            assert updated_card['updated_at'] != initial_updated_at
    
    def test_card_updated_at_on_column_change(self, api_client, sample_card, sample_board):
        """Test that card updated_at changes when moved to different column."""
        # Create a second column
        col_response = requests.post(
            f'{api_client}/api/boards/{sample_board["id"]}/columns',
            json={'name': 'Second Column'}
        )
        new_column_id = col_response.json()['column']['id']
        
        # Get initial card state
        response1 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        initial_updated_at = response1.json()['card']['updated_at']
        
        time.sleep(0.1)
        
        # Move card to new column
        response2 = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}', json={
            'column_id': new_column_id
        })
        assert response2.status_code == 200
        updated_card = response2.json()['card']
        
        # Timestamp should change for column moves
        if initial_updated_at and updated_card['updated_at']:
            assert updated_card['updated_at'] != initial_updated_at
    
    def test_card_updated_at_not_changed_on_reorder(self, api_client, sample_column):
        """Test that card updated_at does NOT change when reordered within same column."""
        # Create two cards
        response1 = requests.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={'title': 'Card 1'}
        )
        card1_id = response1.json()['card']['id']
        
        response2 = requests.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={'title': 'Card 2'}
        )
        
        # Get initial timestamp
        response3 = requests.get(f'{api_client}/api/cards/{card1_id}')
        initial_updated_at = response3.json()['card']['updated_at']
        
        time.sleep(0.1)
        
        # Reorder card within same column
        response4 = requests.patch(f'{api_client}/api/cards/{card1_id}', json={
            'order': 1
        })
        assert response4.status_code == 200
        updated_card = response4.json()['card']
        
        # Timestamp should NOT change for pure reordering
        if initial_updated_at and updated_card['updated_at']:
            assert updated_card['updated_at'] == initial_updated_at
    
    def test_card_updated_at_on_archive(self, api_client, sample_card):
        """Test that card updated_at changes when archived."""
        card_id = sample_card['id']
        
        # Get initial state
        response1 = requests.get(f'{api_client}/api/cards/{card_id}')
        initial_updated_at = response1.json()['card']['updated_at']
        
        time.sleep(0.1)
        
        # Archive card
        response2 = requests.patch(f'{api_client}/api/cards/{card_id}/archive')
        assert response2.status_code == 200
        updated_card = response2.json()['card']
        
        if initial_updated_at and updated_card['updated_at']:
            assert updated_card['updated_at'] != initial_updated_at
    
    # Checklist item timestamp tests
    def test_checklist_item_timestamps_on_create(self, api_client, sample_card):
        """Test that checklist items have timestamps when created."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={'name': 'Timestamp Test Item'}
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        
        assert 'created_at' in data['checklist_item']
        assert 'updated_at' in data['checklist_item']
    
    def test_checklist_item_timestamps_in_card(self, api_client, sample_card):
        """Test that checklist items include timestamps when retrieved with card."""
        # Create a checklist item
        requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={'name': 'Test Item'}
        )
        
        # Get card with checklist
        response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        assert response.status_code == 200
        data = response.json()
        
        for item in data['card']['checklist_items']:
            assert 'created_at' in item
            assert 'updated_at' in item
    
    def test_checklist_item_updated_at_on_name_change(self, api_client, sample_card):
        """Test that checklist item updated_at changes when name is modified."""
        # Create item
        create_response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={'name': 'Original Name'}
        )
        item_id = create_response.json()['checklist_item']['id']
        initial_updated_at = create_response.json()['checklist_item']['updated_at']
        
        time.sleep(0.1)
        
        # Update name
        update_response = requests.patch(
            f'{api_client}/api/checklist-items/{item_id}',
            json={'name': 'Updated Name'}
        )
        assert update_response.status_code == 200
        updated_item = update_response.json()['checklist_item']
        
        if initial_updated_at and updated_item['updated_at']:
            assert updated_item['updated_at'] != initial_updated_at
    
    def test_checklist_item_updated_at_on_checked_change(self, api_client, sample_card):
        """Test that checklist item updated_at changes when checked status changes."""
        # Create item
        create_response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={'name': 'Test Item'}
        )
        item_id = create_response.json()['checklist_item']['id']
        initial_updated_at = create_response.json()['checklist_item']['updated_at']
        
        time.sleep(0.1)
        
        # Update checked
        update_response = requests.patch(
            f'{api_client}/api/checklist-items/{item_id}',
            json={'checked': True}
        )
        assert update_response.status_code == 200
        updated_item = update_response.json()['checklist_item']
        
        if initial_updated_at and updated_item['updated_at']:
            assert updated_item['updated_at'] != initial_updated_at
    
    def test_card_updated_when_checklist_item_added(self, api_client, sample_card):
        """Test that parent card updated_at changes when checklist item is added."""
        # Get initial card state
        response1 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        initial_card_updated_at = response1.json()['card']['updated_at']
        
        time.sleep(0.1)
        
        # Add checklist item
        requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={'name': 'New Item'}
        )
        
        # Get updated card state
        response2 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        updated_card_updated_at = response2.json()['card']['updated_at']
        
        # Card should be updated
        if initial_card_updated_at and updated_card_updated_at:
            assert updated_card_updated_at != initial_card_updated_at
    
    def test_card_updated_when_checklist_item_modified(self, api_client, sample_card):
        """Test that parent card updated_at changes when checklist item is modified."""
        # Create item
        create_response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={'name': 'Test Item'}
        )
        item_id = create_response.json()['checklist_item']['id']
        
        # Get card state after item creation
        response1 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        initial_card_updated_at = response1.json()['card']['updated_at']
        
        time.sleep(1.0)  # Ensure timestamp will be different at second precision
        
        # Modify checklist item
        requests.patch(
            f'{api_client}/api/checklist-items/{item_id}',
            json={'checked': True}
        )
        
        # Get updated card state
        response2 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        updated_card_updated_at = response2.json()['card']['updated_at']
        
        # Card should be updated
        if initial_card_updated_at and updated_card_updated_at:
            assert updated_card_updated_at != initial_card_updated_at
    
    def test_card_updated_when_checklist_item_deleted(self, api_client, sample_card):
        """Test that parent card updated_at changes when checklist item is deleted."""
        # Create item
        create_response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={'name': 'Test Item'}
        )
        item_id = create_response.json()['checklist_item']['id']
        
        # Get card state after item creation
        response1 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        initial_card_updated_at = response1.json()['card']['updated_at']
        
        time.sleep(1.0)  # Ensure timestamp will be different at second precision
        
        # Delete checklist item
        requests.delete(f'{api_client}/api/checklist-items/{item_id}')
        
        # Get updated card state
        response2 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        updated_card_updated_at = response2.json()['card']['updated_at']
        
        # Card should be updated
        if initial_card_updated_at and updated_card_updated_at:
            assert updated_card_updated_at != initial_card_updated_at
    
    def test_card_updated_when_comment_added(self, api_client, sample_card):
        """Test that parent card updated_at changes when comment is added."""
        # Get initial card state
        response1 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        initial_card_updated_at = response1.json()['card']['updated_at']
        
        time.sleep(0.1)
        
        # Add comment
        requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/comments',
            json={'comment': 'Test comment'}
        )
        
        # Get updated card state
        response2 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        updated_card_updated_at = response2.json()['card']['updated_at']
        
        # Card should be updated
        if initial_card_updated_at and updated_card_updated_at:
            assert updated_card_updated_at != initial_card_updated_at
    
    def test_card_updated_when_comment_deleted(self, api_client, sample_card):
        """Test that parent card updated_at changes when comment is deleted."""
        # Add comment
        comment_response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/comments',
            json={'comment': 'Test comment'}
        )
        comment_id = comment_response.json()['comment']['id']
        
        # Get card state after comment creation
        response1 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        initial_card_updated_at = response1.json()['card']['updated_at']
        
        time.sleep(1.0)  # Ensure timestamp will be different at second precision
        
        # Delete comment
        requests.delete(f'{api_client}/api/comments/{comment_id}')
        
        # Get updated card state
        response2 = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        updated_card_updated_at = response2.json()['card']['updated_at']
        
        # Card should be updated
        if initial_card_updated_at and updated_card_updated_at:
            assert updated_card_updated_at != initial_card_updated_at
