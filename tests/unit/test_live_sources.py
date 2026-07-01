import asyncio
from typing import Any

from astrolens.core.enums import CacheStatus, VisualMode
from astrolens.core.models import CacheMeta, EvidenceBundle, ResponseMeta
from astrolens.services.live_sources import LiveSourceEvidenceService
from astrolens.services.repository import repository


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        object=repository.get_object("astro:object:m87"),
        views=[],
        warnings=[],
        meta=ResponseMeta(request_id="req_test", cache=CacheMeta(status=CacheStatus.MISS)),
    )


class FakeLiveBackend:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def bundle_for_query(self, query: str, **kwargs: Any) -> EvidenceBundle:
        self.calls.append({"query": query, **kwargs})
        return _bundle()


def test_visual_mode_presets_fan_out_to_source_specific_radius_and_pixels() -> None:
    mast = FakeLiveBackend()
    skyview = FakeLiveBackend()
    service = LiveSourceEvidenceService(
        mast=mast,  # type: ignore[arg-type]
        skyview=skyview,  # type: ignore[arg-type]
    )

    asyncio.run(
        service.bundle_for_query(
            "M87",
            visual_mode=VisualMode.WIDE,
            sources=("mast", "skyview"),
        )
    )

    assert mast.calls[0]["radius_deg"] == 0.08
    assert skyview.calls[0]["radius_deg"] == 0.20
    assert skyview.calls[0]["pixels"] == 1536
    assert skyview.calls[0]["visual_mode"] == VisualMode.WIDE


def test_explicit_radius_and_pixels_override_visual_mode_presets() -> None:
    skyview = FakeLiveBackend()
    service = LiveSourceEvidenceService(
        mast=FakeLiveBackend(),  # type: ignore[arg-type]
        skyview=skyview,  # type: ignore[arg-type]
    )

    asyncio.run(
        service.bundle_for_query(
            "M87",
            visual_mode=VisualMode.WIDE,
            radius_deg=0.04,
            pixels=768,
            sources=("skyview",),
        )
    )

    assert skyview.calls[0]["radius_deg"] == 0.04
    assert skyview.calls[0]["pixels"] == 768
    assert skyview.calls[0]["visual_mode"] == VisualMode.WIDE
