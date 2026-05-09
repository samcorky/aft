"""Tests for card scheduler API endpoints."""
import pytest
from datetime import datetime, timedelta


@pytest.mark.api
class TestCardSchedulerAPI:
    """Test cases for card scheduler API endpoints."""

    def _set_scheduler_enabled(self, api_client, authenticated_session, enabled: bool):
        """Enable/disable background scheduler to avoid race conditions in deterministic tests."""
        response = authenticated_session.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': enabled}
        )
        assert response.status_code == 200
    
    def test_get_card_scheduler_status(self, api_client, authenticated_session):
        """Test getting card scheduler status."""
        response = authenticated_session.get(f'{api_client}/api/settings/card-scheduler/status')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'status' in data
        assert 'running' in data['status']
        assert 'enabled' in data['status']
        assert isinstance(data['status']['running'], bool)
        assert isinstance(data['status']['enabled'], bool)
    
    def test_enable_card_scheduler(self, api_client, authenticated_session):
        """Test enabling card scheduler."""
        response = authenticated_session.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': True}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'message' in data
        
        # Verify setting was updated
        status_response = authenticated_session.get(f'{api_client}/api/settings/card-scheduler/status')
        status_data = status_response.json()
        assert status_data['status']['enabled'] is True
    
    def test_disable_card_scheduler(self, api_client, authenticated_session):
        """Test disabling card scheduler."""
        response = authenticated_session.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': False}
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'message' in data
        
        # Verify setting was updated
        status_response = authenticated_session.get(f'{api_client}/api/settings/card-scheduler/status')
        status_data = status_response.json()
        assert status_data['status']['enabled'] is False
    
    def test_card_scheduler_config_missing_enabled_field(self, api_client, authenticated_session):
        """Test that config update fails when enabled field is missing."""
        response = authenticated_session.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={}
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'enabled field is required' in data['message']
    
    def test_card_scheduler_config_invalid_enabled_type(self, api_client, authenticated_session):
        """Test that config update fails when enabled is not a boolean."""
        response = authenticated_session.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': 'yes'}
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'must be a boolean' in data['message']
    
    def test_card_scheduler_toggle_multiple_times(self, api_client, authenticated_session):
        """Test toggling card scheduler multiple times."""
        # Enable
        response = authenticated_session.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': True}
        )
        assert response.status_code == 200
        
        # Disable
        response = authenticated_session.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': False}
        )
        assert response.status_code == 200
        
        # Enable again
        response = authenticated_session.put(
            f'{api_client}/api/settings/card-scheduler/config',
            json={'enabled': True}
        )
        assert response.status_code == 200
        
        # Verify final state
        status_response = authenticated_session.get(f'{api_client}/api/settings/card-scheduler/status')
        status_data = status_response.json()
        assert status_data['status']['enabled'] is True

    def test_preview_regenerate_schedules_returns_candidates(self, api_client, authenticated_session, clean_database, sample_column):
        """Preview endpoint should return cards that would be generated for a range."""
        card_response = authenticated_session.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={'title': 'Preview Template Source', 'description': 'regeneration preview test'}
        )
        assert card_response.status_code == 201
        card_id = card_response.json()['card']['id']

        start_dt = (datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2))
        end_dt = start_dt + timedelta(hours=2)

        schedule_response = authenticated_session.post(
            f'{api_client}/api/schedules',
            json={
                'card_id': card_id,
                'run_every': 1,
                'unit': 'hour',
                'start_datetime': start_dt.isoformat(),
                'end_datetime': None,
                'schedule_enabled': True,
                'allow_duplicates': True,
                'keep_source_card': True,
            }
        )
        assert schedule_response.status_code == 201
        schedule_id = schedule_response.json()['schedule']['id']

        preview_response = authenticated_session.post(
            f'{api_client}/api/schedules/regenerate/preview',
            json={
                'start_datetime': start_dt.isoformat(),
                'end_datetime': end_dt.isoformat(),
            }
        )
        assert preview_response.status_code == 200

        data = preview_response.json()
        assert data['success'] is True
        assert 'preview' in data

        cards_for_schedule = [
            card for card in data['preview']['cards']
            if card.get('schedule_id') == schedule_id
        ]
        assert len(cards_for_schedule) == 3

    def test_regenerate_schedules_creates_cards(self, api_client, authenticated_session, clean_database, sample_column):
        """Generate endpoint should create cards for eligible runs in the selected range."""
        status_response = authenticated_session.get(f'{api_client}/api/settings/card-scheduler/status')
        assert status_response.status_code == 200
        original_enabled = bool(status_response.json().get('status', {}).get('enabled', True))

        self._set_scheduler_enabled(api_client, authenticated_session, False)

        try:
            card_response = authenticated_session.post(
                f'{api_client}/api/columns/{sample_column["id"]}/cards',
                json={'title': 'Generate Template Source', 'description': 'regeneration execute test'}
            )
            assert card_response.status_code == 201
            card_id = card_response.json()['card']['id']

            start_dt = (datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2))
            end_dt = start_dt + timedelta(hours=2)

            schedule_response = authenticated_session.post(
                f'{api_client}/api/schedules',
                json={
                    'card_id': card_id,
                    'run_every': 1,
                    'unit': 'hour',
                    'start_datetime': start_dt.isoformat(),
                    'end_datetime': None,
                    'schedule_enabled': True,
                    'allow_duplicates': True,
                    'keep_source_card': True,
                }
            )
            assert schedule_response.status_code == 201
            schedule_id = schedule_response.json()['schedule']['id']

            cards_before_response = authenticated_session.get(f'{api_client}/api/columns/{sample_column["id"]}/cards')
            assert cards_before_response.status_code == 200
            cards_before = cards_before_response.json().get('cards', [])
            generated_before = [card for card in cards_before if card.get('schedule') == schedule_id and card.get('scheduled') is False]

            generate_response = authenticated_session.post(
                f'{api_client}/api/schedules/regenerate',
                json={
                    'start_datetime': start_dt.isoformat(),
                    'end_datetime': end_dt.isoformat(),
                }
            )
            assert generate_response.status_code == 200

            data = generate_response.json()
            assert data['success'] is True
            assert data['result']['generated_count'] >= 3

            cards_response = authenticated_session.get(f'{api_client}/api/columns/{sample_column["id"]}/cards')
            assert cards_response.status_code == 200
            cards = cards_response.json().get('cards', [])
            generated_cards = [card for card in cards if card.get('schedule') == schedule_id and card.get('scheduled') is False]
            assert len(generated_cards) - len(generated_before) == 3
        finally:
            self._set_scheduler_enabled(api_client, authenticated_session, original_enabled)

    def test_regenerate_schedules_rejects_invalid_range(self, api_client, authenticated_session):
        """Generate endpoint should validate that end_datetime is on or after start_datetime."""
        response = authenticated_session.post(
            f'{api_client}/api/schedules/regenerate',
            json={
                'start_datetime': '2026-01-02T12:00:00',
                'end_datetime': '2026-01-01T12:00:00',
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False

    def test_preview_regenerate_rejects_non_object_payload(self, api_client, authenticated_session):
        """Preview endpoint should reject valid JSON payloads that are not objects."""
        response = authenticated_session.post(
            f'{api_client}/api/schedules/regenerate/preview',
            json=['not', 'an', 'object']
        )
        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False

    def test_regenerate_schedules_rejects_excessive_run_volume(self, api_client, authenticated_session, clean_database, sample_column):
        """Generate endpoint should reject ranges that would exceed server-side run limits."""
        card_response = authenticated_session.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={'title': 'Volume Guard Template', 'description': 'limit guard test'}
        )
        assert card_response.status_code == 201
        card_id = card_response.json()['card']['id']

        start_dt = datetime.now().replace(second=0, microsecond=0) - timedelta(days=8)
        end_dt = datetime.now().replace(second=0, microsecond=0)

        schedule_response = authenticated_session.post(
            f'{api_client}/api/schedules',
            json={
                'card_id': card_id,
                'run_every': 1,
                'unit': 'minute',
                'start_datetime': start_dt.isoformat(),
                'end_datetime': None,
                'schedule_enabled': True,
                'allow_duplicates': True,
                'keep_source_card': True,
            }
        )
        assert schedule_response.status_code == 201

        generate_response = authenticated_session.post(
            f'{api_client}/api/schedules/regenerate',
            json={
                'start_datetime': start_dt.isoformat(),
                'end_datetime': end_dt.isoformat(),
            }
        )
        assert generate_response.status_code == 400
        data = generate_response.json()
        assert data['success'] is False
        assert 'maximum allowed runs per schedule' in data['message']
