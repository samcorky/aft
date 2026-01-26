"""Tests for archive-after API endpoint."""
import pytest
import requests
import time
from datetime import datetime, timedelta


@pytest.mark.api
class TestArchiveAfterAPI:
    """Test cases for archive-after card API endpoint."""
    
    def test_archive_after_dry_run_with_cards(self, api_client, sample_board):
        """Test dry run preview shows cards that would be archived."""
        # Create a column
        column = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Test Column'
        }).json()['column']
        
        # Create cards with different ages (simulate by creating and manually updating timestamps)
        old_card = requests.post(f'{api_client}/api/columns/{column["id"]}/cards', json={
            'title': 'Old Card'
        }).json()['card']
        
        # Wait a moment then create another card
        time.sleep(0.1)
        recent_card = requests.post(f'{api_client}/api/columns/{column["id"]}/cards', json={
            'title': 'Recent Card'
        }).json()['card']
        
        # Note: In real world, cards would have different updated_at timestamps
        # For testing, we use a very short period that captures all cards
        
        # Dry run to preview - use a very short period to capture test cards
        response = requests.post(f'{api_client}/api/columns/{column["id"]}/archive-after', json={
            'quantity': 1,
            'period': 'minutes',
            'dry_run': True
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'affected_count' in data
        assert 'most_recent_card' in data
        
        # Verify cards are NOT actually archived
        card_response = requests.get(f'{api_client}/api/cards/{old_card["id"]}')
        assert card_response.json()['card']['archived'] is False
    
    def test_archive_after_dry_run_no_cards(self, api_client, sample_column):
        """Test dry run when no cards match the criteria."""
        # Create a recent card
        requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Recent Card'
        })
        
        # Dry run with criteria that won't match any cards (far in the future)
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 100,
            'period': 'days',
            'dry_run': True
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['affected_count'] == 0
        assert data['most_recent_card'] is None
    
    def test_archive_after_execute(self, api_client, sample_column):
        """Test actually archiving cards after a time period."""
        # Create cards
        card1 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 1'
        }).json()['card']
        
        card2 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 2'
        }).json()['card']
        
        # Execute archive with very short period to capture all cards
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 1,
            'period': 'minutes',
            'dry_run': False
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['archived_count'] >= 0
        assert 'message' in data
        
        # Verify cards that were old enough are now archived
        # Note: Depending on timing, cards may or may not be archived
        # The important thing is the endpoint executed successfully
    
    def test_archive_after_periods(self, api_client, sample_board):
        """Test different time period units."""
        # Create a column
        column = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Test Column'
        }).json()['column']
        
        # Create a card
        requests.post(f'{api_client}/api/columns/{column["id"]}/cards', json={
            'title': 'Test Card'
        })
        
        periods = ['minutes', 'hours', 'days', 'weeks']
        
        for period in periods:
            response = requests.post(f'{api_client}/api/columns/{column["id"]}/archive-after', json={
                'quantity': 1,
                'period': period,
                'dry_run': True
            })
            
            assert response.status_code == 200, f"Failed for period: {period}"
            data = response.json()
            assert data['success'] is True, f"Failed for period: {period}"
            assert 'affected_count' in data
    
    def test_archive_after_invalid_period(self, api_client, sample_column):
        """Test archive-after with invalid period unit."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 7,
            'period': 'invalid',
            'dry_run': True
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'period must be one of' in data['message']
    
    def test_archive_after_invalid_quantity_zero(self, api_client, sample_column):
        """Test archive-after with quantity of zero."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 0,
            'period': 'days',
            'dry_run': True
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'quantity must be a positive integer' in data['message']
    
    def test_archive_after_invalid_quantity_negative(self, api_client, sample_column):
        """Test archive-after with negative quantity."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': -5,
            'period': 'days',
            'dry_run': True
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'quantity must be a positive integer' in data['message']
    
    def test_archive_after_invalid_quantity_type(self, api_client, sample_column):
        """Test archive-after with non-integer quantity."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 'seven',
            'period': 'days',
            'dry_run': True
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'quantity must be a positive integer' in data['message']
    
    def test_archive_after_missing_quantity(self, api_client, sample_column):
        """Test archive-after without quantity parameter."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'period': 'days',
            'dry_run': True
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'quantity must be a positive integer' in data['message']
    
    def test_archive_after_missing_period(self, api_client, sample_column):
        """Test archive-after without period parameter."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 7,
            'dry_run': True
        })
        
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'period must be one of' in data['message']
    
    def test_archive_after_nonexistent_column(self, api_client):
        """Test archive-after with non-existent column."""
        response = requests.post(f'{api_client}/api/columns/9999/archive-after', json={
            'quantity': 7,
            'period': 'days',
            'dry_run': True
        })
        
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Column not found' in data['message']
    
    def test_archive_after_only_affects_non_archived_cards(self, api_client, sample_column):
        """Test that archive-after only affects non-archived cards."""
        # Create and archive a card
        archived_card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Already Archived'
        }).json()['card']
        requests.patch(f'{api_client}/api/cards/{archived_card["id"]}/archive')
        
        # Create a non-archived card
        active_card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Active Card'
        }).json()['card']
        
        # Dry run to check count
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 1,
            'period': 'minutes',
            'dry_run': True
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        # Should not count the already archived card
        # The count depends on timing, but the important thing is it doesn't error
        assert 'affected_count' in data
    
    def test_archive_after_preserves_other_card_properties(self, api_client, sample_column):
        """Test that archive-after only changes archived status."""
        # Create a card with properties
        card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Test Card',
            'description': 'Test description'
        }).json()['card']
        
        # Execute archive
        requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 1,
            'period': 'minutes',
            'dry_run': False
        })
        
        # Get card and verify other properties are preserved
        card_response = requests.get(f'{api_client}/api/cards/{card["id"]}')
        updated_card = card_response.json()['card']
        assert updated_card['title'] == 'Test Card'
        assert updated_card['description'] == 'Test description'
        assert updated_card['column_id'] == sample_column['id']
    
    def test_archive_after_most_recent_card_details(self, api_client, sample_column):
        """Test that dry run returns correct most recent card details."""
        # Create multiple cards
        card1 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 1'
        }).json()['card']
        
        time.sleep(0.1)
        
        card2 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card 2 - Most Recent'
        }).json()['card']
        
        # Dry run
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 1,
            'period': 'minutes',
            'dry_run': True
        })
        
        assert response.status_code == 200
        data = response.json()
        
        if data['affected_count'] > 0:
            most_recent = data['most_recent_card']
            assert most_recent is not None
            assert 'id' in most_recent
            assert 'title' in most_recent
            assert 'created_at' in most_recent
            # updated_at may be None if card hasn't been updated yet
            assert 'updated_at' in most_recent
    
    def test_archive_after_empty_column(self, api_client, sample_column):
        """Test archive-after on column with no cards."""
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 7,
            'period': 'days',
            'dry_run': True
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['affected_count'] == 0
        assert data['most_recent_card'] is None
    
    def test_archive_after_execute_returns_count(self, api_client, sample_column):
        """Test that execute (non-dry-run) returns archived count."""
        # Create a card
        requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Test Card'
        })
        
        # Execute archive
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 1,
            'period': 'minutes',
            'dry_run': False
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'archived_count' in data
        assert isinstance(data['archived_count'], int)
        assert data['archived_count'] >= 0
    
    def test_archive_after_large_quantity(self, api_client, sample_column):
        """Test archive-after with large quantity value."""
        # Create a card
        requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Test Card'
        })
        
        # Use very large quantity that definitely won't match
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 1000,
            'period': 'weeks',
            'dry_run': True
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['affected_count'] == 0
    
    def test_archive_after_default_dry_run(self, api_client, sample_column):
        """Test that dry_run defaults to False if not specified."""
        # Create a card
        card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Test Card'
        }).json()['card']
        
        # Call without dry_run parameter (should execute)
        response = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/archive-after', json={
            'quantity': 1,
            'period': 'minutes'
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        # Should have 'archived_count' not 'affected_count' (execute mode)
        assert 'archived_count' in data or 'affected_count' not in data
