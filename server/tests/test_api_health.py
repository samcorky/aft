"""Tests for health and statistics API endpoints."""

import requests


class TestHealthEndpoints:
    """Tests for /api/test and /api/stats endpoints."""

    def test_database_connection(self, api_client):
        """Test database connection endpoint."""
        response = requests.get(f"{api_client}/api/test")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Connected to database"
        assert "boards_count" in data
        assert isinstance(data["boards_count"], int)
        assert data["boards_count"] >= 0

    def test_database_stats_empty(self, api_client, isolated_test):
        """Test stats endpoint with empty database."""
        response = requests.get(f"{api_client}/api/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["boards_count"] == 0
        assert data["columns_count"] == 0
        assert data["cards_count"] == 0
        assert data["cards_archived_count"] == 0
        assert data["checklist_items_total"] == 0
        assert data["checklist_items_checked"] == 0
        assert data["checklist_items_unchecked"] == 0

    def test_database_stats_with_data(self, api_client, isolated_test, sample_board):
        """Test stats endpoint with sample data."""
        # Create additional data
        # Add a column
        col_response = requests.post(
            f"{api_client}/api/boards/{sample_board['id']}/columns",
            json={"name": "Test Column"}
        )
        assert col_response.status_code == 201
        column = col_response.json()["column"]
        
        # Add active card
        card1_response = requests.post(
            f"{api_client}/api/columns/{column['id']}/cards",
            json={"title": "Active Card", "description": "Test"}
        )
        assert card1_response.status_code == 201
        card1 = card1_response.json()["card"]
        
        # Add archived card
        card2_response = requests.post(
            f"{api_client}/api/columns/{column['id']}/cards",
            json={"title": "Archived Card", "description": "Test"}
        )
        assert card2_response.status_code == 201
        card2 = card2_response.json()["card"]
        
        # Archive the second card
        archive_response = requests.patch(f"{api_client}/api/cards/{card2['id']}/archive")
        assert archive_response.status_code == 200
        
        # Add checklist items
        item1_response = requests.post(
            f"{api_client}/api/cards/{card1['id']}/checklist-items",
            json={"name": "Task 1", "checked": True}
        )
        assert item1_response.status_code == 201
        
        item2_response = requests.post(
            f"{api_client}/api/cards/{card1['id']}/checklist-items",
            json={"name": "Task 2", "checked": False}
        )
        assert item2_response.status_code == 201
        
        # Check stats
        response = requests.get(f"{api_client}/api/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["boards_count"] == 1
        assert data["columns_count"] == 1
        assert data["cards_count"] == 2
        assert data["cards_archived_count"] == 1
        assert data["checklist_items_total"] == 2
        assert data["checklist_items_checked"] == 1
        assert data["checklist_items_unchecked"] == 1

    def test_stats_updates_after_archive(self, api_client, isolated_test, sample_board):
        """Test that stats update correctly when cards are archived/unarchived."""
        # Create column and cards
        col_response = requests.post(
            f"{api_client}/api/boards/{sample_board['id']}/columns",
            json={"name": "Test Column"}
        )
        column = col_response.json()["column"]
        
        card1_response = requests.post(
            f"{api_client}/api/columns/{column['id']}/cards",
            json={"title": "Card 1", "description": "Test"}
        )
        card1 = card1_response.json()["card"]
        
        card2_response = requests.post(
            f"{api_client}/api/columns/{column['id']}/cards",
            json={"title": "Card 2", "description": "Test"}
        )
        card2 = card2_response.json()["card"]
        
        # Initial stats - no archived cards
        response = requests.get(f"{api_client}/api/stats")
        data = response.json()
        assert data["cards_count"] == 2
        assert data["cards_archived_count"] == 0
        
        # Archive one card
        requests.patch(f"{api_client}/api/cards/{card1['id']}/archive")
        
        response = requests.get(f"{api_client}/api/stats")
        data = response.json()
        assert data["cards_count"] == 2
        assert data["cards_archived_count"] == 1
        
        # Archive another card
        requests.patch(f"{api_client}/api/cards/{card2['id']}/archive")
        
        response = requests.get(f"{api_client}/api/stats")
        data = response.json()
        assert data["cards_count"] == 2
        assert data["cards_archived_count"] == 2
        
        # Unarchive one card
        requests.patch(f"{api_client}/api/cards/{card1['id']}/unarchive")
        
        response = requests.get(f"{api_client}/api/stats")
        data = response.json()
        assert data["cards_count"] == 2
        assert data["cards_archived_count"] == 1
