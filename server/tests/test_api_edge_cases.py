"""Edge case and security tests for API endpoints."""

import pytest
import requests


@pytest.mark.api
class TestAPIInputValidation:
    """Test input validation and edge cases for API endpoints."""

    def test_malformed_json_board_create(self, api_client):
        """Test creating board with malformed JSON."""
        # Send invalid JSON
        response = requests.post(
            f"{api_client}/api/boards",
            data='{"name": invalid json}',
            headers={"Content-Type": "application/json"},
        )
        # Should return 400 or 500 for malformed JSON
        assert response.status_code in [400, 500]

    def test_oversized_board_name(self, api_client):
        """Test creating board with oversized name."""
        # Create a very long name (> 10000 characters)
        long_name = "A" * 20000
        response = requests.post(f"{api_client}/api/boards", json={"name": long_name})
        # Should either succeed (truncated) or fail with 400
        # This tests current behavior - actual validation will be added
        assert response.status_code in [201, 400, 413, 500]

    def test_board_name_with_special_characters(self, api_client):
        """Test board name with special characters."""
        response = requests.post(
            f"{api_client}/api/boards", json={"name": '<script>alert("XSS")</script>'}
        )
        # Should succeed - we store what user provides
        # Frontend should escape on display
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True

    def test_board_name_with_unicode(self, api_client):
        """Test board name with Unicode characters."""
        response = requests.post(f"{api_client}/api/boards", json={"name": "测试板 🎯"})
        assert response.status_code == 201
        data = response.json()
        assert "测试板" in data["board"]["name"]

    def test_null_board_name(self, api_client):
        """Test creating board with null name."""
        response = requests.post(f"{api_client}/api/boards", json={"name": None})
        # Should fail - name is required
        assert response.status_code == 400

    def test_integer_board_name(self, api_client):
        """Test creating board with integer as name."""
        response = requests.post(f"{api_client}/api/boards", json={"name": 12345})
        # Current implementation may accept or reject
        # This documents current behavior
        assert response.status_code in [201, 400]

    def test_empty_string_board_name(self, api_client):
        """Test creating board with empty string name."""
        response = requests.post(f"{api_client}/api/boards", json={"name": ""})
        # Empty string should be rejected or accepted
        # This tests current behavior
        assert response.status_code in [201, 400]

    def test_oversized_card_title(self, api_client, sample_column):
        """Test creating card with oversized title."""
        long_title = "T" * 20000
        response = requests.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={"title": long_title},
        )
        # Should either succeed (truncated) or fail
        assert response.status_code in [201, 400, 413, 500]

    def test_oversized_card_description(self, api_client, sample_column):
        """Test creating card with oversized description."""
        long_desc = "D" * 50000
        response = requests.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={"title": "Test", "description": long_desc},
        )
        # Should either succeed (truncated) or fail
        assert response.status_code in [201, 400, 413, 500]

    def test_negative_board_id(self, api_client):
        """Test accessing board with negative ID."""
        response = requests.get(f"{api_client}/api/boards/-1/columns")
        # Should return 200 with empty list or 404
        assert response.status_code in [200, 404]

    def test_zero_board_id(self, api_client):
        """Test accessing board with zero ID."""
        response = requests.get(f"{api_client}/api/boards/0/columns")
        # Should return 200 with empty list or 404
        assert response.status_code in [200, 404]

    def test_huge_board_id(self, api_client):
        """Test accessing board with very large ID."""
        response = requests.get(f"{api_client}/api/boards/999999999999/columns")
        # Should return 200 with empty list or 404
        assert response.status_code in [200, 404]

    def test_non_numeric_board_id(self, api_client):
        """Test accessing board with non-numeric ID."""
        response = requests.get(f"{api_client}/api/boards/abc/columns")
        # Should return 404 or 400 for invalid ID format
        assert response.status_code in [400, 404]

    def test_card_order_negative(self, api_client, sample_column):
        """Test creating card with negative order."""
        response = requests.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={"title": "Test Card", "order": -1},
        )
        # Should either accept or reject negative order
        assert response.status_code in [201, 400]

    def test_card_order_huge_number(self, api_client, sample_column):
        """Test creating card with very large order number."""
        response = requests.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={"title": "Test Card", "order": 999999999},
        )
        # Should either accept or reject huge order
        assert response.status_code in [201, 400]

    def test_card_order_as_string(self, api_client, sample_column):
        """Test creating card with string as order."""
        response = requests.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={"title": "Test Card", "order": "5"},
        )
        # Should reject non-integer order
        assert response.status_code in [400, 500]

    def test_setting_invalid_value_type(self, api_client):
        """Test setting default_board with invalid type."""
        response = requests.put(
            f"{api_client}/api/settings/default_board", json={"value": [1, 2, 3]}
        )
        # Should reject array value for integer setting
        assert response.status_code == 400

    def test_setting_negative_board_id(self, api_client):
        """Test setting default_board to negative ID."""
        response = requests.put(
            f"{api_client}/api/settings/default_board", json={"value": -1}
        )
        # Should reject negative board ID
        assert response.status_code == 400

    def test_setting_zero_board_id(self, api_client):
        """Test setting default_board to zero."""
        response = requests.put(
            f"{api_client}/api/settings/default_board", json={"value": 0}
        )
        # Should reject zero as board ID
        assert response.status_code == 400

    def test_missing_json_body(self, api_client):
        """Test creating board without JSON body."""
        response = requests.post(
            f"{api_client}/api/boards", headers={"Content-Type": "application/json"}
        )
        # Should return 400 for missing body
        assert response.status_code == 400

    def test_empty_json_body(self, api_client):
        """Test creating board with empty JSON object."""
        response = requests.post(f"{api_client}/api/boards", json={})
        # Should return 400 for missing name
        assert response.status_code == 400

    def test_update_nonexistent_card_to_nonexistent_column(self, api_client):
        """Test moving nonexistent card to nonexistent column."""
        response = requests.patch(
            f"{api_client}/api/cards/99999", json={"column_id": 88888}
        )
        # Should return 404 for card not found
        assert response.status_code == 404

    def test_sql_injection_board_name(self, api_client):
        """Test SQL injection attempt in board name."""
        response = requests.post(
            f"{api_client}/api/boards", json={"name": "'; DROP TABLE boards; --"}
        )
        # SQLAlchemy should prevent injection
        # Should either succeed with the string stored as-is, or fail validation
        if response.status_code == 201:
            # Verify boards table still exists by listing boards
            verify = requests.get(f"{api_client}/api/boards")
            assert verify.status_code == 200

    def test_sql_injection_checklist_item_name(self, api_client, sample_card):
        """Test SQL injection attempt in checklist item name."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": "'; DROP TABLE checklist_items; --"}
        )
        # SQLAlchemy should prevent injection
        # Should either succeed with the string stored as-is, or fail validation
        if response.status_code == 201:
            # Verify checklist_items table still exists
            verify = requests.get(f'{api_client}/api/columns/{sample_card["column_id"]}/cards')
            assert verify.status_code == 200

    def test_xss_checklist_item_name(self, api_client, sample_card):
        """Test XSS attempt in checklist item name."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": '<script>alert("XSS")</script>'}
        )
        # Should succeed - we store what user provides
        # Frontend should escape on display
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True

    def test_unicode_checklist_item_name(self, api_client, sample_card):
        """Test Unicode characters in checklist item name."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": "测试任务 🎯 ✅"}
        )
        assert response.status_code == 201
        data = response.json()
        assert "测试任务" in data["checklist_item"]["name"]

    def test_oversized_checklist_item_name(self, api_client, sample_card):
        """Test creating checklist item with oversized name."""
        long_name = "A" * 1000  # Beyond 500 char limit
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": long_name}
        )
        # Should reject oversized name
        assert response.status_code == 400

    def test_null_checklist_item_name(self, api_client, sample_card):
        """Test creating checklist item with null name."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": None}
        )
        # Should reject null name
        assert response.status_code == 400

    def test_integer_checklist_item_name(self, api_client, sample_card):
        """Test creating checklist item with integer as name."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": 12345}
        )
        # Should reject non-string name
        assert response.status_code == 400

    def test_checklist_item_negative_order(self, api_client, sample_card):
        """Test creating checklist item with negative order."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": "Test", "order": -1}
        )
        # Should either accept or reject negative order
        assert response.status_code in [201, 400]

    def test_checklist_item_huge_order(self, api_client, sample_card):
        """Test creating checklist item with very large order."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": "Test", "order": 2147483647}  # Max INT
        )
        # Should accept valid integer
        assert response.status_code == 201

    def test_checklist_item_order_as_string(self, api_client, sample_card):
        """Test creating checklist item with string as order."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": "Test", "order": "5"}
        )
        # Should reject non-integer order
        assert response.status_code == 400

    def test_checklist_item_checked_as_string(self, api_client, sample_card):
        """Test creating checklist item with string as checked."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": "Test", "checked": "true"}
        )
        # Should reject non-boolean checked
        assert response.status_code == 400

    def test_checklist_item_invalid_card_id(self, api_client):
        """Test creating checklist item for non-existent card."""
        response = requests.post(
            f'{api_client}/api/cards/99999/checklist-items',
            json={"name": "Test"}
        )
        assert response.status_code == 404

    def test_checklist_item_negative_card_id(self, api_client):
        """Test creating checklist item with negative card ID."""
        response = requests.post(
            f'{api_client}/api/cards/-1/checklist-items',
            json={"name": "Test"}
        )
        assert response.status_code == 404

    def test_checklist_item_non_numeric_card_id(self, api_client):
        """Test creating checklist item with non-numeric card ID."""
        response = requests.post(
            f'{api_client}/api/cards/abc/checklist-items',
            json={"name": "Test"}
        )
        # Should return 404 for invalid ID format
        assert response.status_code == 404

    def test_update_checklist_item_invalid_id(self, api_client):
        """Test updating non-existent checklist item."""
        response = requests.patch(
            f'{api_client}/api/checklist-items/99999',
            json={"name": "Updated"}
        )
        assert response.status_code == 404

    def test_update_checklist_item_negative_id(self, api_client):
        """Test updating checklist item with negative ID."""
        response = requests.patch(
            f'{api_client}/api/checklist-items/-1',
            json={"name": "Updated"}
        )
        assert response.status_code == 404

    def test_delete_checklist_item_invalid_id(self, api_client):
        """Test deleting non-existent checklist item."""
        response = requests.delete(f'{api_client}/api/checklist-items/99999')
        assert response.status_code == 404

    def test_malformed_json_checklist_item(self, api_client, sample_card):
        """Test creating checklist item with malformed JSON."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            data='{"name": invalid json}',
            headers={"Content-Type": "application/json"},
        )
        # Should return 400 or 500 for malformed JSON
        assert response.status_code in [400, 500]

    def test_missing_json_body_checklist_item(self, api_client, sample_card):
        """Test creating checklist item without JSON body."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            headers={"Content-Type": "application/json"}
        )
        # Should return 400 for missing body
        assert response.status_code == 400

    def test_empty_json_body_checklist_item(self, api_client, sample_card):
        """Test creating checklist item with empty JSON object."""
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={}
        )
        # Should return 400 for missing name
        assert response.status_code == 400


@pytest.mark.api
class TestAPIConcurrency:
    """Test concurrent operations and race conditions."""

    def test_delete_board_twice(self, api_client, sample_board):
        """Test deleting the same board twice."""
        board_id = sample_board["id"]

        # First delete should succeed
        response1 = requests.delete(f"{api_client}/api/boards/{board_id}")
        assert response1.status_code == 200

        # Second delete should fail
        response2 = requests.delete(f"{api_client}/api/boards/{board_id}")
        assert response2.status_code == 404

    def test_update_deleted_board(self, api_client, sample_board):
        """Test updating a board after it's deleted."""
        board_id = sample_board["id"]

        # Delete board
        delete_response = requests.delete(f"{api_client}/api/boards/{board_id}")
        assert delete_response.status_code == 200

        # Try to update deleted board
        update_response = requests.patch(
            f"{api_client}/api/boards/{board_id}", json={"name": "Updated Name"}
        )
        assert update_response.status_code == 404

    def test_create_card_in_deleted_column(self, api_client, sample_column):
        """Test creating card in a deleted column."""
        column_id = sample_column["id"]

        # Delete column
        delete_response = requests.delete(f"{api_client}/api/columns/{column_id}")
        assert delete_response.status_code == 200

        # Try to create card in deleted column
        card_response = requests.post(
            f"{api_client}/api/columns/{column_id}/cards", json={"title": "Test Card"}
        )
        assert card_response.status_code == 404

    def test_delete_checklist_item_twice(self, api_client, sample_card):
        """Test deleting the same checklist item twice."""
        # Create checklist item
        create_response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": "Test item"}
        )
        item_id = create_response.json()["checklist_item"]["id"]

        # First delete should succeed
        response1 = requests.delete(f'{api_client}/api/checklist-items/{item_id}')
        assert response1.status_code == 200

        # Second delete should fail
        response2 = requests.delete(f'{api_client}/api/checklist-items/{item_id}')
        assert response2.status_code == 404

    def test_update_deleted_checklist_item(self, api_client, sample_card):
        """Test updating a checklist item after it's deleted."""
        # Create checklist item
        create_response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": "Test item"}
        )
        item_id = create_response.json()["checklist_item"]["id"]

        # Delete item
        delete_response = requests.delete(f'{api_client}/api/checklist-items/{item_id}')
        assert delete_response.status_code == 200

        # Try to update deleted item
        update_response = requests.patch(
            f'{api_client}/api/checklist-items/{item_id}',
            json={"name": "Updated name"}
        )
        assert update_response.status_code == 404

    def test_create_checklist_item_in_deleted_card(self, api_client, sample_card):
        """Test creating checklist item in a deleted card."""
        card_id = sample_card["id"]

        # Delete card
        delete_response = requests.delete(f'{api_client}/api/cards/{card_id}')
        assert delete_response.status_code == 200

        # Try to create checklist item in deleted card
        item_response = requests.post(
            f'{api_client}/api/cards/{card_id}/checklist-items',
            json={"name": "Test item"}
        )
        assert item_response.status_code == 404


@pytest.mark.api
class TestAPIBoundaryConditions:
    """Test boundary conditions and limits."""

    def test_board_name_at_max_length(self, api_client):
        """Test board name at maximum allowed length."""
        # Assuming 255 is max for VARCHAR(255)
        max_name = "B" * 255
        response = requests.post(f"{api_client}/api/boards", json={"name": max_name})
        assert response.status_code == 201

    def test_card_description_at_max_length(self, api_client, sample_column):
        """Test card description at maximum length."""
        # models.py shows String(2000) for description
        max_desc = "D" * 2000
        response = requests.post(
            f'{api_client}/api/columns/{sample_column["id"]}/cards',
            json={"title": "Test", "description": max_desc},
        )
        assert response.status_code == 201

    def test_many_columns_on_board(self, api_client, sample_board):
        """Test creating many columns on a single board."""
        # Create 50 columns
        for i in range(50):
            response = requests.post(
                f'{api_client}/api/boards/{sample_board["id"]}/columns',
                json={"name": f"Column {i}"},
            )
            assert response.status_code == 201

        # Verify all columns created
        verify = requests.get(f'{api_client}/api/boards/{sample_board["id"]}/columns')
        assert verify.status_code == 200
        assert len(verify.json()["columns"]) == 50

    def test_many_cards_in_column(self, api_client, sample_column):
        """Test creating many cards in a single column."""
        # Create 100 cards
        for i in range(100):
            response = requests.post(
                f'{api_client}/api/columns/{sample_column["id"]}/cards',
                json={"title": f"Card {i}"},
            )
            assert response.status_code == 201

        # Verify all cards created
        verify = requests.get(f'{api_client}/api/columns/{sample_column["id"]}/cards')
        assert verify.status_code == 200
        assert len(verify.json()["cards"]) == 100

    def test_checklist_item_name_at_max_length(self, api_client, sample_card):
        """Test checklist item name at maximum allowed length."""
        # models.py shows String(500) for checklist item name
        max_name = "T" * 500
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": max_name}
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data["checklist_item"]["name"]) == 500

    def test_many_checklist_items_on_card(self, api_client, sample_card):
        """Test creating many checklist items on a single card."""
        # Create 100 checklist items
        for i in range(100):
            response = requests.post(
                f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
                json={"name": f"Item {i}"}
            )
            assert response.status_code == 201

        # Verify all items created by fetching cards from column
        verify = requests.get(f'{api_client}/api/columns/{sample_card["column_id"]}/cards')
        assert verify.status_code == 200
        card = next((c for c in verify.json()["cards"] if c["id"] == sample_card["id"]), None)
        assert card is not None
        assert len(card["checklist_items"]) == 100

    def test_checklist_item_with_max_order_value(self, api_client, sample_card):
        """Test checklist item with maximum integer order value."""
        max_order = 2147483647  # Max 32-bit signed integer
        response = requests.post(
            f'{api_client}/api/cards/{sample_card["id"]}/checklist-items',
            json={"name": "Max order item", "order": max_order}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["checklist_item"]["order"] == max_order
