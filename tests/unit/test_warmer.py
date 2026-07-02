import asyncio
from typing import Any

from astrolens.services.repository import repository
from astrolens.services.warmer import warm_curated_cache, warming_enabled


class _RecordingService:
    def __init__(self, fail_for: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_for = fail_for

    async def bundle_for_query(self, query: str, **kwargs: Any) -> None:
        self.calls.append((query, kwargs))
        if self.fail_for and query == self.fail_for:
            raise RuntimeError("archive down")


def test_warmer_walks_every_curated_object_with_hero_request_shape() -> None:
    service = _RecordingService()

    warmed = asyncio.run(
        warm_curated_cache(service, start_delay=0.0, spacing=0.0)  # type: ignore[arg-type]
    )

    assert warmed == len(repository.list_objects()) == len(service.calls)
    names = {call[0] for call in service.calls}
    assert {"M87", "Saturn", "Orion Nebula"} <= names
    # Request shape must match ShowcaseService.show_object so caches line up.
    _query, kwargs = service.calls[0]
    assert kwargs == {
        "max_views": 6,
        "sources": ("mast", "skyview"),
        "pixels": 512,
        "composite": True,
        "include_facts": True,
        "size": "thumbnail",
    }


def test_warmer_continues_past_failures() -> None:
    service = _RecordingService(fail_for="M87")

    warmed = asyncio.run(
        warm_curated_cache(service, start_delay=0.0, spacing=0.0)  # type: ignore[arg-type]
    )

    assert warmed == len(repository.list_objects()) - 1
    assert len(service.calls) == len(repository.list_objects())


def test_warming_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("ASTROLENS_WARM_CACHE", raising=False)
    assert warming_enabled() is False
    monkeypatch.setenv("ASTROLENS_WARM_CACHE", "1")
    assert warming_enabled() is True
    monkeypatch.setenv("ASTROLENS_WARM_CACHE", "0")
    assert warming_enabled() is False


def test_warm_status_is_tracked_for_health_reporting() -> None:
    from astrolens.services.warmer import warm_status

    service = _RecordingService()
    asyncio.run(warm_curated_cache(service, start_delay=0.0, spacing=0.0))  # type: ignore[arg-type]

    assert warm_status["enabled"] is True
    assert warm_status["complete"] is True
    assert warm_status["warmed"] == warm_status["total"] == len(repository.list_objects())
    assert warm_status["current"] is None
