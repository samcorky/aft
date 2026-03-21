"""Tests for creating template cards with scheduled parameter."""
import pytest


@pytest.mark.api
class TestCreateTemplateCards:
    """Test cases for creating cards with scheduled=true parameter."""
    
    def test_create_regular_card(self, api_client, authenticated_session, sample_board, sample_column):
        """Test creating a regular card (scheduled=false)."""
        response = authenticated_session.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={
                'title': 'Regular Task Card',
                'description': 'This is a regular task',
                'scheduled': False
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['card']['title'] == 'Regular Task Card'
        assert 'id' in data['card']
        
        # Verify it's NOT in scheduled view by checking regular column cards
        cards_response = authenticated_session.get(f'{api_client}/api/columns/{sample_column["id"]}/cards')
        cards = cards_response.json()['cards']
        regular_card = next((c for c in cards if c['title'] == 'Regular Task Card'), None)
        assert regular_card is not None
    
    def test_create_template_card(self, api_client, authenticated_session, sample_board, sample_column):
        """Test creating a template card (scheduled=true)."""
        response = authenticated_session.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={
                'title': 'Template Card',
                'description': 'This is a template for scheduled tasks',
                'scheduled': True
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['card']['title'] == 'Template Card'
        assert 'id' in data['card']
        card_id = data['card']['id']
        
        # Verify it appears in scheduled view
        scheduled_response = authenticated_session.get(f'{api_client}/api/boards/{sample_board["id"]}/cards/scheduled')
        scheduled_data = scheduled_response.json()
        template_card = None
        for column in scheduled_data['board']['columns']:
            for card in column['cards']:
                if card['id'] == card_id:
                    template_card = card
                    break
        assert template_card is not None
        assert template_card['scheduled'] is True
    
    def test_create_card_without_scheduled_defaults_false(self, api_client, authenticated_session, sample_board, sample_column):
        """Test creating a card without scheduled parameter defaults to false."""
        response = authenticated_session.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={
                'title': 'Default Card',
                'description': 'No scheduled parameter provided'
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['card']['title'] == 'Default Card'
        
        # Verify it appears in regular column cards (not scheduled)
        cards_response = authenticated_session.get(f'{api_client}/api/columns/{sample_column["id"]}/cards')
        cards = cards_response.json()['cards']
        default_card = next((c for c in cards if c['title'] == 'Default Card'), None)
        assert default_card is not None
    
    def test_template_card_appears_in_scheduled_view(self, api_client, authenticated_session, sample_board, sample_column):
        """Test that template cards appear in the scheduled cards endpoint."""
        # Create a template card
        create_response = authenticated_session.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={
                'title': 'Scheduled Template',
                'description': 'Template for testing',
                'scheduled': True
            }
        )
        assert create_response.status_code == 201
        template_card_id = create_response.json()['card']['id']
        
        # Get scheduled cards for the board
        scheduled_response = authenticated_session.get(
            f'{api_client}/api/boards/{sample_board["id"]}/cards/scheduled'
        )
        assert scheduled_response.status_code == 200
        data = scheduled_response.json()
        assert data['success'] is True
        
        # Verify the template card appears in scheduled view
        template_card = None
        for column in data['board']['columns']:
            for card in column['cards']:
                if card['id'] == template_card_id:
                    template_card = card
                    break
        assert template_card is not None
        assert template_card['scheduled'] is True
        assert template_card['title'] == 'Scheduled Template'
    
    def test_regular_card_not_in_scheduled_view(self, api_client, authenticated_session, sample_board, sample_column):
        """Test that regular cards don't appear in the scheduled cards endpoint."""
        # Create a regular card
        create_response = authenticated_session.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={
                'title': 'Regular Task',
                'description': 'Not a template',
                'scheduled': False
            }
        )
        assert create_response.status_code == 201
        regular_card_id = create_response.json()['card']['id']
        
        # Get scheduled cards for the board
        scheduled_response = authenticated_session.get(
            f'{api_client}/api/boards/{sample_board["id"]}/cards/scheduled'
        )
        assert scheduled_response.status_code == 200
        data = scheduled_response.json()
        assert data['success'] is True
        
        # Verify the regular card does NOT appear in scheduled view
        regular_card = None
        for column in data['board']['columns']:
            for card in column['cards']:
                if card['id'] == regular_card_id:
                    regular_card = card
                    break
        assert regular_card is None  # Should not be in scheduled view
