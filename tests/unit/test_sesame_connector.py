import asyncio
from pathlib import Path

from astrolens.connectors.base import ResolvedObjectCandidate
from astrolens.connectors.sesame import SesameConnector
from astrolens.services.live_ingestion import LiveIngestionService
from astrolens.services.repository import EvidenceRepository


def test_sesame_fixture_parses_to_resolved_object_candidate() -> None:
    body = Path("tests/fixtures/sesame/m87.xml").read_bytes()
    connector = SesameConnector()

    candidates = connector.parse_response(
        body,
        query="M87",
        source_url="https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp?M87",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.name == "M  87"
    assert candidate.object_type == "AGN"
    assert candidate.ra_deg == 187.70593077
    assert candidate.dec_deg == 12.39112325
    assert candidate.raw_metadata["redshift"] == "0.00420"


class FakeSesameConnector:
    name = "Fake Sesame"

    def __init__(self) -> None:
        self.calls = 0

    async def resolve_object(self, query: str) -> list[ResolvedObjectCandidate]:
        self.calls += 1
        return [
            ResolvedObjectCandidate(
                name=query,
                aliases=[query, "Live Alias"],
                object_type="galaxy",
                ra_deg=1.0,
                dec_deg=2.0,
                source=self.name,
                source_url="https://example.org/live",
                confidence=0.95,
                raw_metadata={"oid": "live"},
            )
        ]


def test_live_ingestion_uses_connector_then_in_memory_cache() -> None:
    connector = FakeSesameConnector()
    service = LiveIngestionService(repo=EvidenceRepository(), connector=connector)

    first = asyncio.run(service.resolve_live("Live Object"))
    second = asyncio.run(service.resolve_live("Live Object"))

    assert first.object_id == "astro:object:live:liveobject"
    assert first.meta.cache is not None
    assert second.meta.cache is not None
    assert first.meta.cache.status == "miss"
    assert second.meta.cache.status == "hit"
    assert connector.calls == 1
