"""Unit tests for utility functions."""

import pytest
from utils import (
    validate_string_length,
    validate_integer,
    sanitize_string,
    MAX_TITLE_LENGTH,
    MAX_DESCRIPTION_LENGTH,
)

# Mark all tests in this module as unit tests (don't wait for API)
pytestmark = pytest.mark.unit


class TestValidateStringLength:
    """Tests for validate_string_length function."""

    def test_valid_string(self):
        """Test validation passes for valid string."""
        is_valid, error = validate_string_length("Test", 100, "field")
        assert is_valid is True
        assert error is None

    def test_none_value(self):
        """Test None value is allowed."""
        is_valid, error = validate_string_length(None, 100, "field")
        assert is_valid is True
        assert error is None

    def test_empty_string(self):
        """Test empty string is valid."""
        is_valid, error = validate_string_length("", 100, "field")
        assert is_valid is True
        assert error is None

    def test_max_length_exceeded(self):
        """Test validation fails when max length exceeded."""
        long_string = "a" * 101
        is_valid, error = validate_string_length(long_string, 100, "field")
        assert is_valid is False
        assert "exceeds maximum length" in error

    def test_exact_max_length(self):
        """Test string at exact max length is valid."""
        exact_string = "a" * 100
        is_valid, error = validate_string_length(exact_string, 100, "field")
        assert is_valid is True
        assert error is None

    def test_non_string_value(self):
        """Test non-string value fails validation."""
        is_valid, error = validate_string_length(123, 100, "field")
        assert is_valid is False
        assert "must be a string" in error


class TestValidateInteger:
    """Tests for validate_integer function."""

    def test_valid_integer(self):
        """Test validation passes for valid integer."""
        is_valid, error = validate_integer(42, "field")
        assert is_valid is True
        assert error is None

    def test_zero_is_valid(self):
        """Test zero is a valid integer."""
        is_valid, error = validate_integer(0, "field")
        assert is_valid is True
        assert error is None

    def test_negative_integer(self):
        """Test negative integer is valid without constraints."""
        is_valid, error = validate_integer(-5, "field")
        assert is_valid is True
        assert error is None

    def test_none_not_allowed(self):
        """Test None fails when not allowed."""
        is_valid, error = validate_integer(None, "field", allow_none=False)
        assert is_valid is False
        assert "is required" in error

    def test_none_allowed(self):
        """Test None passes when allowed."""
        is_valid, error = validate_integer(None, "field", allow_none=True)
        assert is_valid is True
        assert error is None

    def test_boolean_rejected(self):
        """Test boolean values are rejected (even though they're int subclass)."""
        is_valid, error = validate_integer(True, "field")
        assert is_valid is False
        assert "not boolean" in error

        is_valid, error = validate_integer(False, "field")
        assert is_valid is False
        assert "not boolean" in error

    def test_string_rejected(self):
        """Test string value is rejected."""
        is_valid, error = validate_integer("123", "field")
        assert is_valid is False
        assert "must be an integer" in error

    def test_float_rejected(self):
        """Test float value is rejected."""
        is_valid, error = validate_integer(12.5, "field")
        assert is_valid is False
        assert "must be an integer" in error

    def test_min_value_constraint(self):
        """Test minimum value constraint."""
        is_valid, error = validate_integer(5, "field", min_value=10)
        assert is_valid is False
        assert "at least 10" in error

        is_valid, error = validate_integer(10, "field", min_value=10)
        assert is_valid is True
        assert error is None

    def test_max_value_constraint(self):
        """Test maximum value constraint."""
        is_valid, error = validate_integer(15, "field", max_value=10)
        assert is_valid is False
        assert "at most 10" in error

        is_valid, error = validate_integer(10, "field", max_value=10)
        assert is_valid is True
        assert error is None

    def test_min_and_max_constraints(self):
        """Test both min and max constraints."""
        is_valid, error = validate_integer(5, "field", min_value=10, max_value=20)
        assert is_valid is False

        is_valid, error = validate_integer(15, "field", min_value=10, max_value=20)
        assert is_valid is True
        assert error is None

        is_valid, error = validate_integer(25, "field", min_value=10, max_value=20)
        assert is_valid is False


class TestSanitizeString:
    """Tests for sanitize_string function."""

    def test_none_value(self):
        """Test None returns None."""
        result = sanitize_string(None)
        assert result is None

    def test_strips_whitespace(self):
        """Test leading and trailing whitespace is stripped."""
        result = sanitize_string("  test  ")
        assert result == "test"

    def test_preserves_internal_whitespace(self):
        """Test internal whitespace is preserved."""
        result = sanitize_string("test  value")
        assert result == "test  value"

    def test_empty_string(self):
        """Test empty string."""
        result = sanitize_string("")
        assert result == ""

    def test_whitespace_only(self):
        """Test whitespace-only string becomes empty."""
        result = sanitize_string("   ")
        assert result == ""

    def test_normal_string_unchanged(self):
        """Test normal string without whitespace is unchanged."""
        result = sanitize_string("test")
        assert result == "test"


class TestConstants:
    """Tests to ensure constants are reasonable."""

    def test_max_lengths_are_positive(self):
        """Test that max length constants are positive integers."""
        assert MAX_TITLE_LENGTH > 0
        assert MAX_DESCRIPTION_LENGTH > 0
        assert isinstance(MAX_TITLE_LENGTH, int)
        assert isinstance(MAX_DESCRIPTION_LENGTH, int)

    def test_max_lengths_are_reasonable(self):
        """Test that max lengths are within reasonable bounds."""
        assert MAX_TITLE_LENGTH >= 100  # At least 100 chars for titles
        assert MAX_DESCRIPTION_LENGTH >= 500  # At least 500 chars for descriptions
        assert MAX_TITLE_LENGTH <= 10000  # Not too large
        assert MAX_DESCRIPTION_LENGTH <= 100000  # Not too large
