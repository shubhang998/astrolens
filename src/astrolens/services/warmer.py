"""Background cache warmer for the curated seed objects.

Walks the curated catalog slowly on startup so the objects people actually ask
about (M87, Orion, Saturn, ...) answer from warm caches instead of paying
worst-case live-archive latency. Uses the exact same request shape as the
`show_object` hero tool so cache keys line up.
"""

from __future__ import annotations

import asyncio
import logging
import os

from astrolens.services.live_sources import (
    LiveSourceEvidenceService,
    live_source_evidence_service,
)
from astrolens.services.repository import repository

logger = logging.getLogger("astrolens.warmer")

WARM_CACHE_ENV = "ASTROLENS_WARM_CACHE"
# Give the service time to pass health checks and serve first traffic before
# adding background archive load.
WARM_START_DELAY_SECONDS = 30.0
# Pause between objects: the warmer is a polite background crawler, not a
# stress test of NASA services.
WARM_OBJECT_SPACING_SECONDS = 20.0


def warming_enabled() -> bool:
    return os.getenv(WARM_CACHE_ENV, "").strip() == "1"


async def warm_curated_cache(
    service: LiveSourceEvidenceService = live_source_evidence_service,
    *,
    start_delay: float = WARM_START_DELAY_SECONDS,
    spacing: float = WARM_OBJECT_SPACING_SECONDS,
) -> int:
    """Warm hero-call caches for every curated object; returns objects warmed."""

    await asyncio.sleep(start_delay)
    warmed = 0
    for obj in repository.list_objects():
        try:
            # Mirrors ShowcaseService.show_object's bundle request so the
            # SkyView render cache and fact caches are hit by real queries.
            await service.bundle_for_query(
                obj.name,
                max_views=6,
                sources=("mast", "skyview"),
                pixels=512,
                composite=True,
                include_facts=True,
                size="thumbnail",
            )
            warmed += 1
            logger.info("warmed %s (%d)", obj.name, warmed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - warming must never crash the app
            logger.warning("warm failed for %s: %s", obj.name, exc)
        await asyncio.sleep(spacing)
    logger.info("cache warm complete: %d objects", warmed)
    return warmed
