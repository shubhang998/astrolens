"""Deterministic V1 ranking service.

Two ranking entry points live here:

- ``rank_views`` ranks curated seed views by their precomputed ``scores.overall``.
- ``rank_views_by_source_quality`` decides *which images to show* when candidate
  views are merged from multiple live sources (MAST, SkyView). It applies an
  explicit visual-source-quality ladder so a clean SDSS RGB composite is never
  buried under a raw detector preview, and treats single-survey SkyView cutouts
  as the fallback tier. See ``docs/design-docs/ranking.md``.
"""

from astrolens.core.enums import BandFamily, TargetValidationStatus, VisualAssetTier
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


# --- Cross-source visual-quality ranking -------------------------------------
#
# Well-separated ladder bands (higher is a better default visual). The workstream
# preference order is:
#   outreach releases > HLA/HLSP/processed-archive products > SDSS / multi-band
#   rendered composites > MAST archive previews > single-survey SkyView fallback.
# Bands are spaced by >=50 so the bounded refinements below never let one band
# cross into another.
_OUTREACH_BAND = 500.0
_PROCESSED_ARCHIVE_BAND = 400.0
_RENDERED_COMPOSITE_BAND = 350.0
_RAW_PREVIEW_BAND = 300.0
_RENDERED_SINGLE_BAND = 200.0
_ASSET_UNKNOWN_BAND = 150.0
_NO_ASSET_BAND = 0.0

# Refinements are clamped to +/-_MAX_REFINEMENT, kept below the smallest ladder
# gap (350 - 300) so they only reorder views *within* a band, never across bands.
_MAX_REFINEMENT = 24.0

_TARGET_VALIDATION_BONUS = {
    TargetValidationStatus.CENTERED: 12.0,
    TargetValidationStatus.IN_FRAME: 6.0,
    TargetValidationStatus.UNVERIFIED: 0.0,
    TargetValidationStatus.NEARBY_OFFSET: -6.0,
    TargetValidationStatus.OUT_OF_FRAME: -12.0,
}


def _is_composite_asset(view: View) -> bool:
    """True when the asset was built from multiple aligned source products (e.g. RGB)."""

    return bool(view.asset and len(view.asset.source_product_ids) >= 2)


def _ladder_band(view: View) -> float:
    asset = view.asset
    if asset is None or not asset.asset_url:
        return _NO_ASSET_BAND
    tier = asset.visual_tier
    if tier == VisualAssetTier.OUTREACH_RELEASE:
        return _OUTREACH_BAND
    if tier == VisualAssetTier.PROCESSED_ARCHIVE:
        return _PROCESSED_ARCHIVE_BAND
    if tier == VisualAssetTier.ASTROLENS_RENDERED:
        # A multi-band composite (SDSS RGB) outranks MAST raw previews; a single
        # survey cutout is the fallback tier below them.
        return _RENDERED_COMPOSITE_BAND if _is_composite_asset(view) else _RENDERED_SINGLE_BAND
    if tier == VisualAssetTier.RAW_ARCHIVE_PREVIEW:
        return _RAW_PREVIEW_BAND
    return _ASSET_UNKNOWN_BAND


def _quality_refinement(view: View) -> float:
    """Bounded in-band tie-break from target validation and precomputed scores."""

    bonus = 0.0
    asset = view.asset
    if asset and asset.target_validation:
        bonus += _TARGET_VALIDATION_BONUS.get(asset.target_validation.status, 0.0)
    scores = view.scores
    if scores is not None:
        if scores.preview_quality is not None:
            bonus += (scores.preview_quality - 0.5) * 12.0  # -6 .. +6
        bonus += min(max(scores.overall, 0.0), 1.0) * 6.0  # 0 .. +6
    return max(-_MAX_REFINEMENT, min(_MAX_REFINEMENT, bonus))


def _source_preference(view: View) -> float:
    """Mild tie-break preferring MAST over SkyView, since SkyView is the fallback source."""

    archive = (view.source_archive or "").lower()
    if "mast" in archive:
        return 1.0
    if "skyview" in archive:
        return 0.0
    return 0.5


def visual_source_quality_score(view: View) -> float:
    """Return a higher-is-better visual-source-quality score for one view."""

    return _ladder_band(view) + _quality_refinement(view)


def visual_source_quality_key(view: View) -> tuple[float, float, str]:
    """Deterministic sort key (ascending sort yields best-first order)."""

    return (
        -visual_source_quality_score(view),
        -_source_preference(view),
        view.label,
    )


def rank_views_by_source_quality(
    views: list[View],
    *,
    bands: list[BandFamily] | None = None,
    max_views: int = 6,
) -> list[View]:
    """Rank merged multi-source views by the visual-source-quality ladder.

    Selection is wavelength-diversity-first: the single best view is always first,
    then remaining slots prefer the best not-yet-seen band before filling with the
    next best regardless of band. With a single-band candidate set this degrades to
    pure quality order. Input views are read, never mutated, so provenance and tier
    metadata are preserved verbatim.
    """

    if max_views <= 0:
        return []
    requested = set(bands or [])
    candidates = [view for view in views if not requested or view.band_family in requested]
    ranked = sorted(candidates, key=visual_source_quality_key)

    selected: list[View] = []
    overflow: list[View] = []
    seen_bands: set[BandFamily] = set()
    for view in ranked:
        if view.band_family in seen_bands:
            overflow.append(view)
            continue
        seen_bands.add(view.band_family)
        selected.append(view)
        if len(selected) >= max_views:
            return selected
    for view in overflow:
        if len(selected) >= max_views:
            break
        selected.append(view)
    return selected
