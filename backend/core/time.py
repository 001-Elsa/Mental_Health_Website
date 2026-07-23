"""UTC helpers for databases that currently store naive UTC timestamps."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return naive UTC without relying on deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
