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


