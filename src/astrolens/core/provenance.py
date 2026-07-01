"""Provenance helpers for later connector and service work."""

from datetime import UTC, datetime

from astrolens.core.models import SourceReference


def source_reference(name: str, url: str | None = None) -> SourceReference:
    """Create a source reference with a UTC retrieval timestamp."""

    return SourceReference(name=name, url=url, retrieved_at=datetime.now(UTC))
