"""Deterministic V1 ranking service."""

from astrolens.core.enums import BandFamily
from astrolens.core.models import View


def rank_views(
    views: list[View],
    *,
    bands: list[BandFamily] | None = None,
    max_views: int = 6,
    max_views_per_band: int | None = None,
) -> list[View]:
    """Rank views by score while preserving wavelength diversity."""

    requested = set(bands or [])
    candidates = [view for view in views if not requested or view.band_family in requested]
    candidates.sort(key=lambda view: view.scores.overall if view.scores else 0.0, reverse=True)

    selected: list[View] = []
    per_band_count: dict[BandFamily, int] = {}
    for view in candidates:
        count = per_band_count.get(view.band_family, 0)
        if max_views_per_band is not None and count >= max_views_per_band:
            continue
        selected.append(view)
        per_band_count[view.band_family] = count + 1
        if len(selected) >= max_views:
            break
    return selected
