"""Tests for card API endpoints."""
import pytest
import requests


@pytest.mark.api
class TestCardsAPI:
    """Test cases for card API endpoints."""
    
    def test_get_column_cards_empty(self, api_client, sample_column):
        """Test getting cards when column is empty."""
        response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['cards'] == []
    
    def test_get_column_cards_with_data(self, api_client, sample_card):
        """Test getting cards from a column."""
        response = requests.get(f'{api_client}/api/columns/{sample_card["column_id"]}/cards')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['cards']) == 1
        assert data['cards'][0]['title'] == "Test Card"
    
    def test_get_single_card(self, api_client, sample_card):
        """Test getting a single card by ID."""
        response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['card']['id'] == sample_card['id']
        assert data['card']['title'] == "Test Card"
        assert data['card']['column_id'] == sample_card['column_id']
        assert 'checklist_items' in data['card']
        assert isinstance(data['card']['checklist_items'], list)
    
    def test_get_single_card_not_found(self, api_client):
        """Test getting a non-existent card."""
        response = requests.get(f'{api_client}/api/cards/9999')
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['message'].lower()
    
    def test_get_single_card_with_checklist(self, api_client, sample_card):
        """Test getting a card with checklist items."""
        # Add checklist items to the card
        requests.post(f'{api_client}/api/cards/{sample_card["id"]}/checklist-items', json={
            'name': 'First item',
            'checked': False,
            'order': 0
        })
        requests.post(f'{api_client}/api/cards/{sample_card["id"]}/checklist-items', json={
            'name': 'Second item',
            'checked': True,
            'order': 1
        })
        
        # Get the card
        response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['card']['checklist_items']) == 2
        assert data['card']['checklist_items'][0]['name'] == 'First item'
        assert data['card']['checklist_items'][0]['checked'] is False
        assert data['card']['checklist_items'][1]['name'] == 'Second item'
        assert data['card']['checklist_items'][1]['checked'] is True
    
    def test_create_card(self, api_client, sample_column):
        """Test creating a new card."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'New Task',
            'description': 'Task description'
        })
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['card']['title'] == 'New Task'
        assert data['card']['column_id'] == sample_column['id']
    
    def test_create_card_missing_title(self, api_client, sample_column):
        """Test creating a card without title fails."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'description': 'No title'
        })
        assert response.status_code == 400
    
    def test_create_card_with_order(self, api_client, sample_column):
        """Test creating a card with specific order."""
        # Create first card
        response1 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'First Card'
        })
        assert response1.status_code == 201
        
        # Create second card at position 0 (should shift first card)
        response2 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Second Card',
            'order': 0
        })
        assert response2.status_code == 201
        data = response2.json()
        assert data['card']['order'] == 0
    
    def test_update_card(self, api_client, sample_card):
        """Test updating a card."""
        response = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}', json={
            'title': 'Updated Title',
            'description': 'Updated description'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['card']['title'] == 'Updated Title'
    
    def test_update_card_not_found(self, api_client):
        """Test updating a non-existent card."""
        response = requests.patch(f'{api_client}/api/cards/9999', json={
            'title': 'Updated'
        })
        assert response.status_code == 404
    
    def test_move_card_within_column(self, api_client, sample_column):
        """Test moving a card to a different position within the same column."""
        # Create multiple cards
        card1 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 1'
        }).json()['card']
        
        requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 2'
        })
        
        # Move card 1 to position after card 2
        response = requests.patch(f'{api_client}/api/cards/{card1["id"]}', json={
            'order': 1
        })
        assert response.status_code == 200
        data = response.json()
        assert data['card']['order'] == 1
    
    def test_delete_card(self, api_client, sample_card):
        """Test deleting a card."""
        card_id = sample_card['id']
        response = requests.delete(f'{api_client}/api/cards/{card_id}')
        assert response.status_code == 200
        
        # Verify card is deleted
        verify_response = requests.get(f'{api_client}/api/columns/{sample_card["column_id"]}/cards')
        cards = verify_response.json()['cards']
        card_ids = [card['id'] for card in cards]
        assert card_id not in card_ids
    
    def test_delete_card_not_found(self, api_client):
        """Test deleting a non-existent card."""
        response = requests.delete(f'{api_client}/api/cards/9999')
        assert response.status_code == 404
    
    def test_delete_all_cards_in_column(self, api_client, sample_column):
        """Test deleting all cards in a column."""
        # Create multiple cards
        for i in range(3):
            requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
                'title': f'Card {i}'
            })
        
        response = requests.delete(f'{api_client}/api/columns/{sample_column["id"]}/cards')
        assert response.status_code == 200, f"DELETE failed with status {response.status_code}: {response.text}"
        data = response.json()
        assert data['success'] is True
        assert data['deleted_count'] == 3
        
        # Verify all cards deleted
        verify_response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards')
        assert len(verify_response.json()['cards']) == 0
    
    def test_archive_card(self, api_client, sample_card):
        """Test archiving a card."""
        response = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/archive')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['card']['archived'] is True
        
        # Verify card is archived
        verify_response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        assert verify_response.json()['card']['archived'] is True
    
    def test_archive_card_not_found(self, api_client):
        """Test archiving a non-existent card."""
        response = requests.patch(f'{api_client}/api/cards/9999/archive')
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
    
    def test_unarchive_card(self, api_client, sample_card):
        """Test unarchiving a card."""
        # First archive the card
        requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/archive')
        
        # Then unarchive it
        response = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/unarchive')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['card']['archived'] is False
        
        # Verify card is unarchived
        verify_response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        assert verify_response.json()['card']['archived'] is False
    
    def test_unarchive_card_not_found(self, api_client):
        """Test unarchiving a non-existent card."""
        response = requests.patch(f'{api_client}/api/cards/9999/unarchive')
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
    
    def test_get_column_cards_excludes_archived_by_default(self, api_client, sample_column):
        """Test that GET column cards excludes archived cards by default."""
        # Create two cards
        card1 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Active Card'
        }).json()['card']
        
        card2 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card to Archive'
        }).json()['card']
        
        # Archive one card
        requests.patch(f'{api_client}/api/cards/{card2["id"]}/archive')
        
        # Get cards without archived parameter (should exclude archived)
        response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards')
        assert response.status_code == 200
        data = response.json()
        assert len(data['cards']) == 1
        assert data['cards'][0]['id'] == card1['id']
    
    def test_get_column_cards_with_archived_filter(self, api_client, sample_column):
        """Test filtering column cards by archived status."""
        # Create two cards
        card1 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Active Card'
        }).json()['card']
        
        card2 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card to Archive'
        }).json()['card']
        
        # Archive one card
        requests.patch(f'{api_client}/api/cards/{card2["id"]}/archive')
        
        # Test archived=false (explicit)
        response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards?archived=false')
        assert response.status_code == 200
        data = response.json()
        assert len(data['cards']) == 1
        assert data['cards'][0]['id'] == card1['id']
        
        # Test archived=true
        response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards?archived=true')
        assert response.status_code == 200
        data = response.json()
        assert len(data['cards']) == 1
        assert data['cards'][0]['id'] == card2['id']
        
        # Test archived=both
        response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards?archived=both')
        assert response.status_code == 200
        data = response.json()
        assert len(data['cards']) == 2
    
    def test_order_updates_exclude_archived_cards(self, api_client, sample_column):
        """Test that card order updates don't affect archived cards."""
        # Create three cards
        card1 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 1'
        }).json()['card']
        
        card2 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 2'
        }).json()['card']
        
        card3 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 3'
        }).json()['card']
        
        # Archive card 2
        requests.patch(f'{api_client}/api/cards/{card2["id"]}/archive')
        
        # Move card 3 to position 0 (should not affect archived card 2's order)
        requests.patch(f'{api_client}/api/cards/{card3["id"]}', json={'order': 0})
        
        # Get all cards including archived
        response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards?archived=both')
        cards = response.json()['cards']
        
        # Find each card in the response
        card1_result = next(c for c in cards if c['id'] == card1['id'])
        card2_result = next(c for c in cards if c['id'] == card2['id'])
        card3_result = next(c for c in cards if c['id'] == card3['id'])
        
        # Card 3 should be at position 0
        assert card3_result['order'] == 0
        # Card 1 should be at position 1
        assert card1_result['order'] == 1
        # Archived card 2 should still be at its original position 1 (unchanged)
        assert card2_result['order'] == 1
    
    def test_unarchive_handles_order_conflicts(self, api_client, sample_column):
        """Test that unarchiving a card with a clashing order value properly reorders cards."""
        # Create three cards at positions 0, 1, 2
        card1 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 1'
        }).json()['card']
        
        card2 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 2'
        }).json()['card']
        
        card3 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 3'
        }).json()['card']
        
        # Archive card 2 (which is at position 1)
        requests.patch(f'{api_client}/api/cards/{card2["id"]}/archive')
        
        # Now active cards are: card1 (order 0), card3 (order 2)
        # Unarchive card2 - it still has order 1, which should push card3 to order 3
        response = requests.patch(f'{api_client}/api/cards/{card2["id"]}/unarchive')
        assert response.status_code == 200
        assert response.json()['success'] is True
        
        # Get all active cards and check their order
        response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards?archived=false')
        cards = response.json()['cards']
        
        # Find each card in the response
        card1_result = next(c for c in cards if c['id'] == card1['id'])
        card2_result = next(c for c in cards if c['id'] == card2['id'])
        card3_result = next(c for c in cards if c['id'] == card3['id'])
        
        # Card 1 should still be at position 0
        assert card1_result['order'] == 0
        # Card 2 should be at position 1 (its original position)
        assert card2_result['order'] == 1
        # Card 3 should now be at position 3 (pushed up from 2)
        assert card3_result['order'] == 3

    def test_move_all_cards_to_bottom(self, api_client, sample_board):
        """Test moving all cards from one column to the bottom of another."""
        # Create two columns
        col1 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Source Column'
        }).json()['column']
        
        col2 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Target Column'
        }).json()['column']
        
        # Create cards in source column
        source_cards = []
        for i in range(3):
            card = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
                'title': f'Source Card {i}'
            }).json()['card']
            source_cards.append(card)
        
        # Create cards in target column
        target_cards = []
        for i in range(2):
            card = requests.post(f'{api_client}/api/columns/{col2["id"]}/cards', json={
                'title': f'Target Card {i}'
            }).json()['card']
            target_cards.append(card)
        
        # Move all cards from source to bottom of target
        response = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards/move', json={
            'target_column_id': col2['id'],
            'position': 'bottom'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['moved_count'] == 3
        
        # Verify source column is empty
        source_response = requests.get(f'{api_client}/api/columns/{col1["id"]}/cards')
        assert len(source_response.json()['cards']) == 0
        
        # Verify target column has all cards in correct order
        target_response = requests.get(f'{api_client}/api/columns/{col2["id"]}/cards')
        target_result = target_response.json()['cards']
        assert len(target_result) == 5
        
        # Original target cards should be at positions 0 and 1
        assert target_result[0]['title'] == 'Target Card 0'
        assert target_result[0]['order'] == 0
        assert target_result[1]['title'] == 'Target Card 1'
        assert target_result[1]['order'] == 1
        
        # Moved cards should be at positions 2, 3, 4 in original order
        assert target_result[2]['title'] == 'Source Card 0'
        assert target_result[2]['order'] == 2
        assert target_result[3]['title'] == 'Source Card 1'
        assert target_result[3]['order'] == 3
        assert target_result[4]['title'] == 'Source Card 2'
        assert target_result[4]['order'] == 4
    
    def test_move_all_cards_to_top(self, api_client, sample_board):
        """Test moving all cards from one column to the top of another."""
        # Create two columns
        col1 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Source Column'
        }).json()['column']
        
        col2 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Target Column'
        }).json()['column']
        
        # Create cards in source column
        for i in range(3):
            requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
                'title': f'Source Card {i}'
            })
        
        # Create cards in target column
        for i in range(2):
            requests.post(f'{api_client}/api/columns/{col2["id"]}/cards', json={
                'title': f'Target Card {i}'
            })
        
        # Move all cards from source to top of target
        response = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards/move', json={
            'target_column_id': col2['id'],
            'position': 'top'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['moved_count'] == 3
        
        # Verify source column is empty
        source_response = requests.get(f'{api_client}/api/columns/{col1["id"]}/cards')
        assert len(source_response.json()['cards']) == 0
        
        # Verify target column has all cards in correct order
        target_response = requests.get(f'{api_client}/api/columns/{col2["id"]}/cards')
        target_result = target_response.json()['cards']
        assert len(target_result) == 5
        
        # Moved cards should be at top (positions 0, 1, 2) in original order
        assert target_result[0]['title'] == 'Source Card 0'
        assert target_result[0]['order'] == 0
        assert target_result[1]['title'] == 'Source Card 1'
        assert target_result[1]['order'] == 1
        assert target_result[2]['title'] == 'Source Card 2'
        assert target_result[2]['order'] == 2
        
        # Original target cards should be pushed down to positions 3 and 4
        assert target_result[3]['title'] == 'Target Card 0'
        assert target_result[3]['order'] == 3
        assert target_result[4]['title'] == 'Target Card 1'
        assert target_result[4]['order'] == 4
    
    def test_move_all_cards_empty_source(self, api_client, sample_board):
        """Test moving cards when source column is empty."""
        # Create two columns
        col1 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Empty Column'
        }).json()['column']
        
        col2 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Target Column'
        }).json()['column']
        
        # Move all cards (should handle empty source gracefully)
        response = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards/move', json={
            'target_column_id': col2['id'],
            'position': 'bottom'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['moved_count'] == 0
        assert 'No cards to move' in data['message']
    
    def test_move_all_cards_to_empty_target(self, api_client, sample_board):
        """Test moving cards to an empty target column."""
        # Create two columns
        col1 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Source Column'
        }).json()['column']
        
        col2 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Empty Target'
        }).json()['column']
        
        # Create cards in source column
        for i in range(3):
            requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
                'title': f'Card {i}'
            })
        
        # Move all cards to empty target
        response = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards/move', json={
            'target_column_id': col2['id'],
            'position': 'bottom'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['moved_count'] == 3
        
        # Verify cards are in target with correct order
        target_response = requests.get(f'{api_client}/api/columns/{col2["id"]}/cards')
        target_result = target_response.json()['cards']
        assert len(target_result) == 3
        assert target_result[0]['order'] == 0
        assert target_result[1]['order'] == 1
        assert target_result[2]['order'] == 2
    
    def test_move_all_cards_invalid_position(self, api_client, sample_column):
        """Test move all cards with invalid position parameter."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards/move', json={
            'target_column_id': sample_column['id'],
            'position': 'middle'  # Invalid position
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert "Invalid position value. Must be 'top' or 'bottom'" in data['message']
    
    def test_move_all_cards_missing_target_column(self, api_client, sample_column):
        """Test move all cards without target_column_id."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards/move', json={
            'position': 'bottom'
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'target_column_id is required' in data['message']
    
    def test_move_all_cards_nonexistent_source(self, api_client, sample_column):
        """Test move all cards with non-existent source column."""
        response = requests.post(f'{api_client}/api/columns/9999/cards/move', json={
            'target_column_id': sample_column['id'],
            'position': 'bottom'
        })
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Source column not found' in data['message']
    
    def test_move_all_cards_nonexistent_target(self, api_client, sample_column):
        """Test move all cards with non-existent target column."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards/move', json={
            'target_column_id': 9999,
            'position': 'bottom'
        })
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Target column not found' in data['message']
    
    def test_move_all_cards_maintains_archived_status(self, api_client, sample_board):
        """Test that moving cards preserves their archived status."""
        # Create two columns
        col1 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Source Column'
        }).json()['column']
        
        col2 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Target Column'
        }).json()['column']
        
        # Create cards in source column
        card1 = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
            'title': 'Active Card'
        }).json()['card']
        
        card2 = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
            'title': 'Archived Card'
        }).json()['card']
        
        # Archive second card
        requests.patch(f'{api_client}/api/cards/{card2["id"]}/archive')
        
        # Move all cards (including archived)
        response = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards/move', json={
            'target_column_id': col2['id'],
            'position': 'bottom',
            'include_archived': True
        })
        assert response.status_code == 200
        assert response.json()['moved_count'] == 2
        
        # Verify archived status is preserved
        card1_result = requests.get(f'{api_client}/api/cards/{card1["id"]}').json()['card']
        card2_result = requests.get(f'{api_client}/api/cards/{card2["id"]}').json()['card']
        
        assert card1_result['archived'] is False
        assert card2_result['archived'] is True
        assert card1_result['column_id'] == col2['id']
        assert card2_result['column_id'] == col2['id']

    def test_move_all_cards_excludes_archived_by_default(self, api_client, sample_board):
        """Test that moving cards excludes archived cards by default."""
        # Create two columns
        col1 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Source Column'
        }).json()['column']
        
        col2 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Target Column'
        }).json()['column']
        
        # Create cards in source column
        card1 = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
            'title': 'Active Card 1'
        }).json()['card']
        
        card2 = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
            'title': 'Active Card 2'
        }).json()['card']
        
        card3 = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
            'title': 'Archived Card'
        }).json()['card']
        
        # Archive third card
        requests.patch(f'{api_client}/api/cards/{card3["id"]}/archive')
        
        # Move all cards without include_archived flag (should exclude archived)
        response = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards/move', json={
            'target_column_id': col2['id'],
            'position': 'bottom'
        })
        assert response.status_code == 200
        assert response.json()['moved_count'] == 2  # Only active cards
        
        # Verify active cards moved to target
        card1_result = requests.get(f'{api_client}/api/cards/{card1["id"]}').json()['card']
        card2_result = requests.get(f'{api_client}/api/cards/{card2["id"]}').json()['card']
        assert card1_result['column_id'] == col2['id']
        assert card2_result['column_id'] == col2['id']
        
        # Verify archived card stayed in source column
        card3_result = requests.get(f'{api_client}/api/cards/{card3["id"]}').json()['card']
        assert card3_result['column_id'] == col1['id']
        assert card3_result['archived'] is True

    def test_move_all_cards_with_include_archived_true(self, api_client, sample_board):
        """Test that moving cards with include_archived=true moves all cards."""
        # Create two columns
        col1 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Source Column'
        }).json()['column']
        
        col2 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Target Column'
        }).json()['column']
        
        # Create cards in source column
        card1 = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
            'title': 'Active Card'
        }).json()['card']
        
        card2 = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
            'title': 'Archived Card'
        }).json()['card']
        
        # Archive second card
        requests.patch(f'{api_client}/api/cards/{card2["id"]}/archive')
        
        # Move all cards with include_archived=true
        response = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards/move', json={
            'target_column_id': col2['id'],
            'position': 'bottom',
            'include_archived': True
        })
        assert response.status_code == 200
        assert response.json()['moved_count'] == 2  # Both cards
        
        # Verify both cards moved to target
        card1_result = requests.get(f'{api_client}/api/cards/{card1["id"]}').json()['card']
        card2_result = requests.get(f'{api_client}/api/cards/{card2["id"]}').json()['card']
        assert card1_result['column_id'] == col2['id']
        assert card2_result['column_id'] == col2['id']
        
        # Verify archived status is preserved
        assert card1_result['archived'] is False
        assert card2_result['archived'] is True

    def test_batch_archive_cards(self, api_client, sample_column):
        """Test archiving multiple cards in a batch."""
        # Create multiple cards
        card_ids = []
        for i in range(3):
            card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
                'title': f'Card {i}'
            }).json()['card']
            card_ids.append(card['id'])
        
        # Batch archive the cards
        response = requests.post(f'{api_client}/api/cards/batch/archive', json={
            'card_ids': card_ids
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['archived_count'] == 3
        
        # Verify all cards are archived
        for card_id in card_ids:
            card_response = requests.get(f'{api_client}/api/cards/{card_id}')
            assert card_response.json()['card']['archived'] is True
    
    def test_batch_archive_cards_empty_list(self, api_client):
        """Test batch archive with empty card_ids list."""
        response = requests.post(f'{api_client}/api/cards/batch/archive', json={
            'card_ids': []
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'card_ids is required' in data['message']
    
    def test_batch_archive_cards_missing_card_ids(self, api_client):
        """Test batch archive without card_ids parameter."""
        response = requests.post(f'{api_client}/api/cards/batch/archive', json={})
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'card_ids is required' in data['message']
    
    def test_batch_archive_cards_invalid_type(self, api_client):
        """Test batch archive with invalid card_ids type."""
        response = requests.post(f'{api_client}/api/cards/batch/archive', json={
            'card_ids': 'not-an-array'
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'card_ids must be an array' in data['message']
    
    def test_batch_archive_cards_nonexistent_ids(self, api_client):
        """Test batch archive with non-existent card IDs."""
        response = requests.post(f'{api_client}/api/cards/batch/archive', json={
            'card_ids': [9999, 9998, 9997]
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['archived_count'] == 0  # No cards found to archive
    
    def test_batch_archive_cards_partial_valid_ids(self, api_client, sample_column):
        """Test batch archive with mix of valid and invalid IDs."""
        # Create one card
        card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Valid Card'
        }).json()['card']
        
        # Attempt to archive valid card and non-existent cards
        response = requests.post(f'{api_client}/api/cards/batch/archive', json={
            'card_ids': [card['id'], 9999, 9998]
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['archived_count'] == 1  # Only the valid card
        
        # Verify the valid card is archived
        card_response = requests.get(f'{api_client}/api/cards/{card["id"]}')
        assert card_response.json()['card']['archived'] is True
    
    def test_batch_unarchive_cards(self, api_client, sample_column):
        """Test unarchiving multiple cards in a batch."""
        # Create and archive multiple cards
        card_ids = []
        for i in range(3):
            card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
                'title': f'Card {i}'
            }).json()['card']
            requests.patch(f'{api_client}/api/cards/{card["id"]}/archive')
            card_ids.append(card['id'])
        
        # Batch unarchive the cards
        response = requests.post(f'{api_client}/api/cards/batch/unarchive', json={
            'card_ids': card_ids
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['unarchived_count'] == 3
        
        # Verify all cards are unarchived
        for card_id in card_ids:
            card_response = requests.get(f'{api_client}/api/cards/{card_id}')
            assert card_response.json()['card']['archived'] is False
    
    def test_batch_unarchive_cards_empty_list(self, api_client):
        """Test batch unarchive with empty card_ids list."""
        response = requests.post(f'{api_client}/api/cards/batch/unarchive', json={
            'card_ids': []
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'card_ids is required' in data['message']
    
    def test_batch_unarchive_cards_missing_card_ids(self, api_client):
        """Test batch unarchive without card_ids parameter."""
        response = requests.post(f'{api_client}/api/cards/batch/unarchive', json={})
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'card_ids is required' in data['message']
    
    def test_batch_unarchive_cards_invalid_type(self, api_client):
        """Test batch unarchive with invalid card_ids type."""
        response = requests.post(f'{api_client}/api/cards/batch/unarchive', json={
            'card_ids': 123
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'card_ids must be an array' in data['message']
    
    def test_batch_unarchive_already_active_cards(self, api_client, sample_column):
        """Test batch unarchive on already active cards."""
        # Create active cards (not archived)
        card_ids = []
        for i in range(2):
            card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
                'title': f'Active Card {i}'
            }).json()['card']
            card_ids.append(card['id'])
        
        # Attempt to unarchive already active cards
        response = requests.post(f'{api_client}/api/cards/batch/unarchive', json={
            'card_ids': card_ids
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['unarchived_count'] == 2  # Operation succeeds but cards were already active
        
        # Verify cards remain unarchived
        for card_id in card_ids:
            card_response = requests.get(f'{api_client}/api/cards/{card_id}')
            assert card_response.json()['card']['archived'] is False
    
    def test_batch_operations_are_atomic(self, api_client, sample_column):
        """Test that batch operations work correctly with mixed states."""
        # Create cards: some archived, some not
        archived_card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Already Archived'
        }).json()['card']
        requests.patch(f'{api_client}/api/cards/{archived_card["id"]}/archive')
        
        active_card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Active Card'
        }).json()['card']
        
        # Batch archive both cards
        response = requests.post(f'{api_client}/api/cards/batch/archive', json={
            'card_ids': [archived_card['id'], active_card['id']]
        })
        assert response.status_code == 200
        assert response.json()['archived_count'] == 2
        
        # Verify both are archived
        for card_id in [archived_card['id'], active_card['id']]:
            card_response = requests.get(f'{api_client}/api/cards/{card_id}')
            assert card_response.json()['card']['archived'] is True

    def test_batch_unarchive_handles_order_conflicts(self, api_client, sample_column):
        """Test that batch unarchiving properly manages card ordering."""
        # Create several active cards
        active_cards = []
        for i in range(3):
            card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
                'title': f'Active Card {i}'
            }).json()['card']
            active_cards.append(card)
        
        # Create and archive several cards that will have order conflicts
        archived_cards = []
        for i in range(2):
            card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
                'title': f'To Archive Card {i}'
            }).json()['card']
            requests.patch(f'{api_client}/api/cards/{card["id"]}/archive')
            archived_cards.append(card)
        
        # Batch unarchive the archived cards
        response = requests.post(f'{api_client}/api/cards/batch/unarchive', json={
            'card_ids': [c['id'] for c in archived_cards]
        })
        assert response.status_code == 200
        assert response.json()['unarchived_count'] == 2
        
        # Get all active cards and verify ordering
        column_response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards?archived=false')
        all_cards = column_response.json()['cards']
        
        # Should have 5 total cards now (3 original active + 2 unarchived)
        assert len(all_cards) == 5
        
        # Verify no duplicate order values
        orders = [c['order'] for c in all_cards]
        assert len(orders) == len(set(orders)), "Found duplicate order values"
        
        # Verify orders are sequential starting from 0
        orders.sort()
        assert orders == list(range(5)), f"Expected [0, 1, 2, 3, 4], got {orders}"
        
        # Verify all cards are unarchived
        for card_id in [c['id'] for c in archived_cards]:
            card_response = requests.get(f'{api_client}/api/cards/{card_id}')
            assert card_response.json()['card']['archived'] is False

    def test_batch_unarchive_multiple_columns(self, api_client, sample_board):
        """Test batch unarchiving cards from multiple columns."""
        # Create two columns
        col1 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Column 1'
        }).json()['column']
        
        col2 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Column 2'
        }).json()['column']
        
        # Create and archive cards in both columns
        card_ids = []
        for col in [col1, col2]:
            for i in range(2):
                card = requests.post(f'{api_client}/api/columns/{col["id"]}/cards', json={
                    'title': f'Card in {col["name"]} - {i}'
                }).json()['card']
                requests.patch(f'{api_client}/api/cards/{card["id"]}/archive')
                card_ids.append(card['id'])
        
        # Batch unarchive all cards
        response = requests.post(f'{api_client}/api/cards/batch/unarchive', json={
            'card_ids': card_ids
        })
        assert response.status_code == 200
        assert response.json()['unarchived_count'] == 4
        
        # Verify cards in each column have proper ordering
        for col in [col1, col2]:
            col_response = requests.get(f'{api_client}/api/columns/{col["id"]}/cards?archived=false')
            cards = col_response.json()['cards']
            assert len(cards) == 2
            
            # Check for duplicate orders within the column
            orders = [c['order'] for c in cards]
            assert len(orders) == len(set(orders)), f"Found duplicate order values in {col['name']}"



