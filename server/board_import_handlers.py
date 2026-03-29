"""Board import handlers.

This module provides an extensible handler framework so new import formats
can be added without changing endpoint logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


def get_payload_list(payload, key):
    """Return a payload key as list, defaulting to empty list."""
    value = payload.get(key)
    return value if isinstance(value, list) else []


@dataclass
class ImportValidationResult:
    """Result of import payload validation."""

    is_valid: bool
    errors: list = field(default_factory=list)


class BoardImportHandler(ABC):
    """Base class for board import handlers."""

    @abstractmethod
    def validate(self, payload) -> ImportValidationResult:
        """Validate payload structure and return ImportValidationResult."""
        raise NotImplementedError

    @abstractmethod
    def parse(self, payload) -> dict:
        """Parse payload into normalized import schema."""
        raise NotImplementedError


class AFTBoardImportHandler(BoardImportHandler):
    """Import handler for native AFT board export files."""

    FORMAT = "aft-board"
    SUPPORTED_MAJOR_VERSION = "1"

    REQUIRED_ROOT_KEYS = {
        "export",
        "board",
        "board_settings",
        "columns",
        "cards",
        "card_secondary_assignees",
        "checklists",
        "comments",
        "scheduled_cards",
    }

    def validate(self, payload) -> ImportValidationResult:
        errors = []

        if not isinstance(payload, dict):
            return ImportValidationResult(False, ["Import payload must be a JSON object"])

        missing_keys = sorted(self.REQUIRED_ROOT_KEYS - set(payload.keys()))
        if missing_keys:
            errors.append(f"Missing required top-level keys: {', '.join(missing_keys)}")

        export_meta = payload.get("export")
        if not isinstance(export_meta, dict):
            errors.append("Missing or invalid export metadata")
        else:
            format_name = export_meta.get("format")
            if format_name != self.FORMAT:
                errors.append("Unsupported export format. Expected aft-board")

            version = export_meta.get("format_version")
            if not isinstance(version, str) or not version:
                errors.append("Missing export.format_version")
            else:
                major = version.split(".", 1)[0]
                if major != self.SUPPORTED_MAJOR_VERSION:
                    errors.append(
                        f"Unsupported format major version {major}. "
                        f"Expected {self.SUPPORTED_MAJOR_VERSION}.x"
                    )

        board = payload.get("board")
        if not isinstance(board, dict):
            errors.append("board must be an object")
        else:
            board_name = board.get("name")
            if not isinstance(board_name, str) or not board_name.strip():
                errors.append("board.name is required and must be a non-empty string")
            if board.get("description") is not None and not isinstance(board.get("description"), str):
                errors.append("board.description must be a string or null")

        list_keys = [
            "board_settings",
            "columns",
            "cards",
            "card_secondary_assignees",
            "checklists",
            "comments",
            "scheduled_cards",
        ]
        for key in list_keys:
            value = payload.get(key)
            if not isinstance(value, list):
                errors.append(f"{key} must be an array")

        columns = get_payload_list(payload, "columns")
        cards = get_payload_list(payload, "cards")
        checklists = get_payload_list(payload, "checklists")
        comments = get_payload_list(payload, "comments")
        schedules = get_payload_list(payload, "scheduled_cards")

        column_ids = set()
        for index, column in enumerate(columns):
            if not isinstance(column, dict):
                errors.append(f"columns[{index}] must be an object")
                continue
            column_id = column.get("id")
            if not isinstance(column_id, int):
                errors.append(f"columns[{index}].id must be an integer")
            else:
                column_ids.add(column_id)
            column_name = column.get("name")
            if not isinstance(column_name, str) or not column_name.strip():
                errors.append(f"columns[{index}].name is required")

        card_ids = set()
        for index, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append(f"cards[{index}] must be an object")
                continue

            card_id = card.get("id")
            if not isinstance(card_id, int):
                errors.append(f"cards[{index}].id must be an integer")
            else:
                card_ids.add(card_id)

            column_id = card.get("column_id")
            if not isinstance(column_id, int) or column_id not in column_ids:
                errors.append(f"cards[{index}].column_id must reference a valid column")

            card_title = card.get("title")
            if not isinstance(card_title, str) or not card_title.strip():
                errors.append(f"cards[{index}].title is required")

        for index, item in enumerate(checklists):
            if not isinstance(item, dict):
                errors.append(f"checklists[{index}] must be an object")
                continue
            card_id = item.get("card_id")
            if not isinstance(card_id, int) or card_id not in card_ids:
                errors.append(f"checklists[{index}].card_id must reference a valid card")
            item_name = item.get("name")
            if not isinstance(item_name, str) or not item_name.strip():
                errors.append(f"checklists[{index}].name is required")

        for index, comment in enumerate(comments):
            if not isinstance(comment, dict):
                errors.append(f"comments[{index}] must be an object")
                continue
            card_id = comment.get("card_id")
            if not isinstance(card_id, int) or card_id not in card_ids:
                errors.append(f"comments[{index}].card_id must reference a valid card")
            comment_text = comment.get("comment")
            if not isinstance(comment_text, str) or not comment_text.strip():
                errors.append(f"comments[{index}].comment is required")

        schedule_ids = set()
        for index, schedule in enumerate(schedules):
            if not isinstance(schedule, dict):
                errors.append(f"scheduled_cards[{index}] must be an object")
                continue

            schedule_id = schedule.get("id")
            if isinstance(schedule_id, int):
                schedule_ids.add(schedule_id)

            template_card_id = schedule.get("card_id")
            if not isinstance(template_card_id, int) or template_card_id not in card_ids:
                errors.append(f"scheduled_cards[{index}].card_id must reference a valid card")

        for index, card in enumerate(cards):
            schedule_id = card.get("schedule")
            if schedule_id is None:
                continue
            if not isinstance(schedule_id, int) or schedule_id not in schedule_ids:
                errors.append(f"cards[{index}].schedule must reference a valid scheduled_cards entry")

        return ImportValidationResult(len(errors) == 0, errors)

    def parse(self, payload) -> dict:
        """Normalize payload with safe defaults for optional collections."""
        export_meta = payload.get("export") or {}

        return {
            "import_format": export_meta.get("format", self.FORMAT),
            "import_format_version": export_meta.get("format_version", "1.0"),
            "board": payload.get("board") or {},
            "board_settings": payload.get("board_settings") or [],
            "columns": payload.get("columns") or [],
            "cards": payload.get("cards") or [],
            "card_secondary_assignees": payload.get("card_secondary_assignees") or [],
            "checklists": payload.get("checklists") or [],
            "comments": payload.get("comments") or [],
            "scheduled_cards": payload.get("scheduled_cards") or [],
        }


class ImportHandlerFactory:
    """Factory for obtaining import handlers by payload metadata."""

    @staticmethod
    def get_handler(payload):
        if not isinstance(payload, dict):
            return None

        export_meta = payload.get("export")
        if not isinstance(export_meta, dict):
            return None

        format_name = export_meta.get("format")
        if format_name == AFTBoardImportHandler.FORMAT:
            return AFTBoardImportHandler()

        return None
