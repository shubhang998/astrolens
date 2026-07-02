import asyncio
from pathlib import Path
from typing import Any

from astrolens.core.enums import BandFamily, ErrorCode
from astrolens.core.errors import AstroLensError
from astrolens.core.models import (
    CelestialObject,
    Citation,
    Coordinates,
    Fact,
    ReusePolicy,
    View,
)
from astrolens.services.summarizer import SummarizerService

_OBJECT = CelestialObject(
    id="astro:object:m87",
    name="M87",
    type="AGN",
    coordinates=Coordinates(ra_deg=187.70593, dec_deg=12.39112),
)

_FACTS = [
    Fact(
        id="fact:m87:classification",
        entity_type="object",
        entity_id=_OBJECT.id,
        claim="M87 is classified as an active galactic nucleus in the SIMBAD database.",
        scope="catalog_measurement",
        confidence=0.8,
        citation_ids=["cite:simbad"],
        quantity_kind="classification",
        source_fields=["basic.otype"],
    ),
    Fact(
        id="fact:m87:distance",
        entity_type="object",
        entity_id=_OBJECT.id,
        claim="From its redshift, M87 lies about 62 million light-years away.",
        scope="derived_measurement",
        confidence=0.7,
        citation_ids=["cite:redshift-survey"],
        value=62_000_000.0,
        unit="light-years",
        quantity_kind="distance",
        source_fields=["basic.rvz_redshift"],
        derivation="astropy.cosmology.Planck18.luminosity_distance(z)",
        scale_comparison="about 620 times the diameter of the Milky Way away",
    ),
]

_CITATIONS = [Citation(id="cite:simbad", title="SIMBAD", source="SIMBAD")]

_VIEWS = [
    View(
        id="view:visible",
        label="visible",
        band_family=BandFamily.VISIBLE,
        instrument="ACS",
        source_archive="MAST",
        reuse=ReusePolicy(id="reuse:test"),
    )
]

_GOOD_REPLY = (
    "M87 is an active galactic nucleus. [1] "
    "Its light travels from about 62 million light-years away — roughly "
    "620 times the diameter of the Milky Way. [1,2]"
)


class FakeClient:
    model = "claude-test"

    def __init__(self, reply: str | Exception = _GOOD_REPLY, *, available: bool = True) -> None:
        self.reply = reply
        self._available = available
        self.calls: list[dict[str, Any]] = []

    def available(self) -> bool:
        return self._available

    async def complete(
        self, *, system: str, content: list[dict[str, Any]], max_tokens: int = 1024
    ) -> str:
        if not self._available:
            raise AstroLensError(ErrorCode.SOURCE_UNAVAILABLE, "no API key", retryable=False)
        self.calls.append({"system": system, "content": content})
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _service(client: FakeClient, tmp_path: Path) -> SummarizerService:
    return SummarizerService(client, cache_dir=tmp_path / "summaries")  # type: ignore[arg-type]


def _summarize(service: SummarizerService):
    return asyncio.run(service.summarize(_OBJECT, _FACTS, _CITATIONS, _VIEWS))


def test_valid_summary_maps_fact_numbers_to_citation_ids(tmp_path: Path) -> None:
    client = FakeClient()
    summary = _summarize(_service(client, tmp_path))

    assert summary is not None
    assert summary.text == _GOOD_REPLY
    assert summary.citation_ids == ["cite:simbad", "cite:redshift-survey"]
    assert summary.model == "claude-test"
    assert summary.generated is True
    # The prompt numbers the facts and describes the imagery qualitatively.
    prompt = client.calls[0]["content"][0]["text"]
    assert "1. M87 is classified" in prompt
    assert "visible (ACS)" in prompt


def test_summary_with_novel_number_is_rejected_and_not_cached(tmp_path: Path) -> None:
    bad = FakeClient("M87 lies about 42 million light-years away. [2]")
    service = _service(bad, tmp_path)

    assert _summarize(service) is None
    assert list((tmp_path / "summaries").glob("*.json")) == []

    # The failure was not cached: a well-behaved reply succeeds afterwards.
    assert _summarize(_service(FakeClient(), tmp_path)) is not None


def test_summary_with_unknown_fact_marker_is_rejected(tmp_path: Path) -> None:
    client = FakeClient("M87 is an active galactic nucleus. [7]")

    assert _summarize(_service(client, tmp_path)) is None


def test_summary_without_citation_markers_is_rejected(tmp_path: Path) -> None:
    client = FakeClient("M87 is a wonderful galaxy full of mystery.")

    assert _summarize(_service(client, tmp_path)) is None


def test_disk_cache_round_trip_avoids_second_call(tmp_path: Path) -> None:
    first = _summarize(_service(FakeClient(), tmp_path))
    assert first is not None

    replay_client = FakeClient(RuntimeError("must not be called"))
    cached = _summarize(_service(replay_client, tmp_path))

    assert cached is not None
    assert cached.text == first.text
    assert cached.citation_ids == first.citation_ids
    assert replay_client.calls == []


def test_no_facts_or_no_key_yield_none(tmp_path: Path) -> None:
    service = _service(FakeClient(), tmp_path)
    assert asyncio.run(service.summarize(_OBJECT, [], _CITATIONS, _VIEWS)) is None

    unavailable = _service(FakeClient(available=False), tmp_path)
    assert _summarize(unavailable) is None
    assert unavailable.client.calls == []  # type: ignore[attr-defined]
