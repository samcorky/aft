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
