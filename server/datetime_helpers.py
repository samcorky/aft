"""Datetime serialization helpers shared across route modules."""

from datetime import datetime, timezone


def parse_iso_datetime(value):
    """Parse an ISO-8601 datetime string into a naive UTC datetime object."""
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        if not isinstance(value, str):
            return None

        candidate = value.strip()
        if not candidate:
            return None

        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"

        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError:
            return None

    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

    return dt


def serialize_datetime(value):
    """Serialize datetime to an explicit UTC ISO-8601 string."""
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def utc_now():
    """Return the current UTC timestamp as a naive datetime for DB DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
