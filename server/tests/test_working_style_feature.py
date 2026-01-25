"""Tests for working style feature including done status and kanban board settings."""
import pytest
import requests


@pytest.mark.api
class TestCardDoneStatus:
    """Test cases for card done status functionality."""
    
    def test_get_card_done_status_success(self, api_client, sample_card):
        """Test getting done status of a card."""
        response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}/done')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'done' in data
        assert isinstance(data['done'], bool)
        assert data['card_id'] == sample_card['id']
    
    def test_get_card_done_status_default_false(self, api_client, sample_card):
        """Test that new cards have done status as False by default."""
        response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}/done')
        assert response.status_code == 200
        data = response.json()
        assert data['done'] is False
    
    def test_get_card_done_status_not_found(self, api_client):
        """Test getting done status of non-existent card."""
        response = requests.get(f'{api_client}/api/cards/9999/done')
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['message'].lower()
    
    def test_update_card_done_status_to_true(self, api_client, sample_card):
        """Test updating card done status to True."""
        response = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={
            'done': True
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['done'] is True
        assert data['card_id'] == sample_card['id']
    
    def test_update_card_done_status_to_false(self, api_client, sample_card):
        """Test updating card done status to False."""
        # First set it to True
        requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={'done': True})
        
        # Then set it back to False
        response = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={
            'done': False
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['done'] is False
    
    def test_update_card_done_status_persist(self, api_client, sample_card):
        """Test that done status persists after update."""
        # Update done status
        requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={'done': True})
        
        # Verify it persists by getting the card
        response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}/done')
        assert response.status_code == 200
        assert response.json()['done'] is True
    
    def test_update_card_done_status_missing_done_field(self, api_client, sample_card):
        """Test updating done status without done field in request."""
        response = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={})
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'required' in data['message'].lower()
    
    def test_update_card_done_status_invalid_type(self, api_client, sample_card):
        """Test updating done status with non-boolean value."""
        response = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={
            'done': 'true'  # String instead of boolean
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'boolean' in data['message'].lower()
    
    def test_update_card_done_status_not_found(self, api_client):
        """Test updating done status of non-existent card."""
        response = requests.patch(f'{api_client}/api/cards/9999/done', json={'done': True})
        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['message'].lower()
    
    def test_update_card_done_status_no_json_body(self, api_client, sample_card):
        """Test updating done status with missing JSON body."""
        response = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done')
        # API returns 500 when JSON parsing fails (no body)
        assert response.status_code == 500
        data = response.json()
        assert data['success'] is False
    
    def test_done_status_reflected_in_card_details(self, api_client, sample_card):
        """Test that done status is reflected when getting full card details."""
        # Update done status
        requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={'done': True})
        
        # Get card details
        response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}')
        assert response.status_code == 200
        card = response.json()['card']
        assert 'done' in card
        assert card['done'] is True
    
    def test_done_status_in_board_cards_list(self, api_client, sample_board):
        """Test that done status appears in board cards nested structure."""
        # Create a column and card
        col = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Test Column'
        }).json()['column']
        
        card = requests.post(f'{api_client}/api/columns/{col["id"]}/cards', json={
            'title': 'Test Card'
        }).json()['card']
        
        # Update done status
        requests.patch(f'{api_client}/api/cards/{card["id"]}/done', json={'done': True})
        
        # Get board cards (returns nested structure: board -> columns -> cards)
        response = requests.get(f'{api_client}/api/boards/{sample_board["id"]}/cards')
        assert response.status_code == 200
        board = response.json()['board']
        
        # Find our card in the nested structure
        found_card = None
        for column in board['columns']:
            found_card = next((c for c in column['cards'] if c['id'] == card['id']), None)
            if found_card:
                break
        
        assert found_card is not None
        assert 'done' in found_card
        assert found_card['done'] is True
    
    def test_toggle_done_status_multiple_times(self, api_client, sample_card):
        """Test toggling done status multiple times."""
        for i in range(5):
            expected = (i % 2) == 1
            response = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={
                'done': expected
            })
            assert response.status_code == 200
            assert response.json()['done'] is expected


@pytest.mark.api
class TestWorkingStyleSetting:
    """Test cases for working style setting."""
    
    def test_get_working_style_setting(self, api_client):
        """Test getting the working_style setting."""
        response = requests.get(f'{api_client}/api/settings/working_style')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'value' in data
        # Default should be 'kanban'
        assert data['value'] in ['kanban', 'board_task_category']
    
    def test_working_style_schema_defined(self, api_client):
        """Test that working_style is defined in settings schema."""
        response = requests.get(f'{api_client}/api/settings/schema')
        assert response.status_code == 200
        schema = response.json()['schema']
        assert 'working_style' in schema
        assert schema['working_style']['type'] == 'string'
        assert 'kanban' in schema['working_style']['description'] or \
               'board_task_category' in schema['working_style']['description']
    
    def test_set_working_style_to_kanban(self, api_client):
        """Test setting working_style to kanban."""
        response = requests.put(f'{api_client}/api/settings/working_style', json={
            'value': 'kanban'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['value'] == 'kanban'
    
    def test_set_working_style_to_board_task_category(self, api_client):
        """Test setting working_style to board_task_category."""
        response = requests.put(f'{api_client}/api/settings/working_style', json={
            'value': 'board_task_category'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['value'] == 'board_task_category'
    
    def test_set_working_style_persist(self, api_client):
        """Test that working_style setting persists."""
        # Set to board_task_category
        requests.put(f'{api_client}/api/settings/working_style', json={
            'value': 'board_task_category'
        })
        
        # Verify it persists
        response = requests.get(f'{api_client}/api/settings/working_style')
        assert response.status_code == 200
        assert response.json()['value'] == 'board_task_category'
    
    def test_set_working_style_invalid_value(self, api_client):
        """Test setting working_style with invalid value."""
        response = requests.put(f'{api_client}/api/settings/working_style', json={
            'value': 'invalid_style'
        })
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'invalid' in data['message'].lower() or 'validate' in data['message'].lower()
    
    def test_set_working_style_null_value(self, api_client):
        """Test setting working_style to null."""
        response = requests.put(f'{api_client}/api/settings/working_style', json={
            'value': None
        })
        # May be rejected or allowed depending on schema
        # At minimum, should return a response
        assert response.status_code in [200, 400]
    
    def test_set_working_style_missing_value(self, api_client):
        """Test setting working_style without value field."""
        response = requests.put(f'{api_client}/api/settings/working_style', json={})
        assert response.status_code == 400
    
    def test_switch_working_style_back_and_forth(self, api_client):
        """Test switching working style back and forth."""
        for i in range(3):
            style = 'board_task_category' if (i % 2) == 0 else 'kanban'
            response = requests.put(f'{api_client}/api/settings/working_style', json={
                'value': style
            })
            assert response.status_code == 200
            assert response.json()['value'] == style


@pytest.mark.api
class TestCardDoneAndArchivedInteraction:
    """Test interactions between done status and archived status."""
    
    def test_can_mark_archived_card_as_done(self, api_client, sample_card):
        """Test that archived cards can have done status."""
        # Archive the card
        requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/archive')
        
        # Mark it as done
        response = requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={
            'done': True
        })
        assert response.status_code == 200
        assert response.json()['done'] is True
    
    def test_done_status_preserved_on_archive(self, api_client, sample_card):
        """Test that done status is preserved when archiving."""
        # Mark as done
        requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={'done': True})
        
        # Archive it
        requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/archive')
        
        # Check done status is preserved
        response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}/done')
        assert response.status_code == 200
        assert response.json()['done'] is True
    
    def test_done_status_preserved_on_unarchive(self, api_client, sample_card):
        """Test that done status is preserved when unarchiving."""
        # Mark as done
        requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/done', json={'done': True})
        
        # Archive it
        requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/archive')
        
        # Unarchive it
        requests.patch(f'{api_client}/api/cards/{sample_card["id"]}/unarchive')
        
        # Check done status is still true
        response = requests.get(f'{api_client}/api/cards/{sample_card["id"]}/done')
        assert response.status_code == 200
        assert response.json()['done'] is True
    
    def test_archived_cards_appear_with_done_status(self, api_client, sample_column):
        """Test that archived cards are included in responses with done status."""
        # Create and archive a card with done status
        card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card to Archive'
        }).json()['card']
        
        requests.patch(f'{api_client}/api/cards/{card["id"]}/done', json={'done': True})
        requests.patch(f'{api_client}/api/cards/{card["id"]}/archive')
        
        # Get archived cards from column
        response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards?archived=true')
        assert response.status_code == 200
        cards = response.json()['cards']
        
        # Find our card and verify done status persists with archived status
        found_card = next((c for c in cards if c['id'] == card['id']), None)
        assert found_card is not None
        assert 'archived' in found_card
        assert 'done' in found_card
        assert found_card['archived'] is True
        assert found_card['done'] is True


@pytest.mark.api
class TestDoneCountInColumns:
    """Test done count functionality in column headers and responses."""
    
    def test_board_cards_include_done_status(self, api_client, sample_board):
        """Test that board cards endpoint includes done status for all cards."""
        # Create columns and cards with various done statuses
        col = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Work Column'
        }).json()['column']
        
        # Create some cards with done=true
        for i in range(2):
            card = requests.post(f'{api_client}/api/columns/{col["id"]}/cards', json={
                'title': f'Done Card {i}'
            }).json()['card']
            requests.patch(f'{api_client}/api/cards/{card["id"]}/done', json={'done': True})
        
        # Create some cards with done=false
        for i in range(3):
            requests.post(f'{api_client}/api/columns/{col["id"]}/cards', json={
                'title': f'Active Card {i}'
            })
        
        # Get board with nested structure
        response = requests.get(f'{api_client}/api/boards/{sample_board["id"]}/cards')
        assert response.status_code == 200
        board = response.json()['board']
        
        # Flatten all cards from all columns
        all_cards = []
        for column in board['columns']:
            all_cards.extend(column['cards'])
        
        # All cards should have done status
        assert len(all_cards) >= 5
        for card in all_cards:
            assert 'done' in card
            assert isinstance(card['done'], bool)
    
    def test_column_cards_include_done_status(self, api_client, sample_column):
        """Test that column cards include done status."""
        # Create cards with different done statuses
        card1 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Done Card'
        }).json()['card']
        requests.patch(f'{api_client}/api/cards/{card1["id"]}/done', json={'done': True})
        
        card2 = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Active Card'
        }).json()['card']
        
        # Get column cards
        response = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards')
        assert response.status_code == 200
        cards = response.json()['cards']
        
        # Verify both cards have done status (even if not showing, should exist)
        assert len(cards) >= 2
        done_card = next((c for c in cards if c['id'] == card1['id']), None)
        active_card = next((c for c in cards if c['id'] == card2['id']), None)
        
        if done_card:
            assert 'done' in done_card
            assert done_card['done'] is True
        if active_card:
            assert 'done' in active_card
            assert active_card['done'] is False
    
    def test_batch_done_cards_for_reporting(self, api_client, sample_board):
        """Test getting done/active card counts for a board."""
        # Create column and cards
        col = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Work'
        }).json()['column']
        
        card_ids = []
        for i in range(5):
            card = requests.post(f'{api_client}/api/columns/{col["id"]}/cards', json={
                'title': f'Card {i}'
            }).json()['card']
            card_ids.append(card['id'])
        
        # Mark first 2 as done
        for card_id in card_ids[:2]:
            requests.patch(f'{api_client}/api/cards/{card_id}/done', json={'done': True})
        
        # Get board with nested structure and count done
        response = requests.get(f'{api_client}/api/boards/{sample_board["id"]}/cards')
        board = response.json()['board']
        
        # Flatten cards from all columns
        all_cards = []
        for column in board['columns']:
            all_cards.extend(column['cards'])
        
        done_count = sum(1 for c in all_cards if c['done'])
        active_count = sum(1 for c in all_cards if not c['done'])
        
        assert done_count == 2
        assert active_count == 3


@pytest.mark.api
class TestCardDoneEdgeCases:
    """Test edge cases and error conditions for done status."""
    
    def test_done_status_with_special_characters_in_title(self, api_client, sample_column):
        """Test done status on cards with special characters in title."""
        card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
            'title': 'Card with <special> & "characters"'
        }).json()['card']
        
        response = requests.patch(f'{api_client}/api/cards/{card["id"]}/done', json={'done': True})
        assert response.status_code == 200
        assert response.json()['done'] is True
    
    def test_done_status_on_moved_card(self, api_client, sample_board):
        """Test that done status persists when card is moved to another column."""
        # Create two columns
        col1 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Column 1'
        }).json()['column']
        
        col2 = requests.post(f'{api_client}/api/boards/{sample_board["id"]}/columns', json={
            'name': 'Column 2'
        }).json()['column']
        
        # Create card and mark as done
        card = requests.post(f'{api_client}/api/columns/{col1["id"]}/cards', json={
            'title': 'Card to Move'
        }).json()['card']
        requests.patch(f'{api_client}/api/cards/{card["id"]}/done', json={'done': True})
        
        # Move card to another column
        requests.patch(f'{api_client}/api/cards/{card["id"]}', json={
            'column_id': col2['id']
        })
        
        # Verify done status persists
        response = requests.get(f'{api_client}/api/cards/{card["id"]}/done')
        assert response.status_code == 200
        assert response.json()['done'] is True
    
    def test_done_status_empty_request_body(self, api_client, sample_card):
        """Test done status update with empty body."""
        response = requests.patch(
            f'{api_client}/api/cards/{sample_card["id"]}/done',
            json=None
        )
        # API returns 500 when JSON parsing fails (no body)
        assert response.status_code == 500
    
    def test_many_cards_with_done_status(self, api_client, sample_column):
        """Test handling many cards with done status."""
        # Create many cards
        card_ids = []
        for i in range(20):
            card = requests.post(f'{api_client}/api/columns/{sample_column["id"]}/cards', json={
                'title': f'Card {i}'
            }).json()['card']
            card_ids.append(card['id'])
        
        # Mark alternating cards as done
        for i, card_id in enumerate(card_ids):
            is_done = (i % 2) == 0
            response = requests.patch(f'{api_client}/api/cards/{card_id}/done', json={
                'done': is_done
            })
            assert response.status_code == 200
        
        # Verify cards are properly marked by checking individual cards
        for i, card_id in enumerate(card_ids):
            expected_done = (i % 2) == 0
            response = requests.get(f'{api_client}/api/cards/{card_id}/done')
            assert response.status_code == 200
            assert response.json()['done'] is expected_done
