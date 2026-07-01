"""Tests for the cross-source visual-quality ranking ladder.

These cover the workstream decision "which images should be used" when candidate
views are merged from multiple live sources: outreach/HLA/HLSP, SDSS RGB, MAST
previews, and single-survey SkyView fallback cutouts.
"""

from astrolens.core.enums import BandFamily, TargetValidationStatus, VisualAssetTier
from astrolens.core.models import (
    Asset,
    ImageProvenance,
    ReusePolicy,
    TargetValidation,
    View,
    ViewScores,
)
from astrolens.services.ranking import (
    rank_views_by_source_quality,
    visual_source_quality_score,
)

_REUSE = ReusePolicy(id="reuse:test")


def make_view(
    *,
    label: str,
    tier: VisualAssetTier | None,
    band: BandFamily = BandFamily.VISIBLE,
    source_archive: str = "MAST",
    n_products: int = 1,
    target_status: TargetValidationStatus | None = None,
    scores: ViewScores | None = None,
) -> View:
    """Build a minimal View, optionally without a usable asset (``tier=None``)."""

    asset = None
    if tier is not None:
        asset = Asset(
            id=f"asset:{label}",
            source_product_ids=[f"product:{label}:{index}" for index in range(n_products)],
            format="png",
            visual_tier=tier,
            asset_url="https://example.test/a.png",
            target_validation=(
                TargetValidation(status=target_status) if target_status is not None else None
            ),
            provenance=ImageProvenance(visual_tier=tier, source_record_id=f"rec:{label}"),
            reuse_policy_id=_REUSE.id,
        )
    return View(
        id=f"view:{label}",
        label=label,
        band_family=band,
        source_archive=source_archive,
        asset=asset,
        reuse=_REUSE,
        scores=scores,
    )


def test_ladder_orders_sources_from_outreach_to_skyview_fallback() -> None:
    outreach = make_view(label="outreach", tier=VisualAssetTier.OUTREACH_RELEASE)
    hla = make_view(label="hla", tier=VisualAssetTier.PROCESSED_ARCHIVE)
    sdss_rgb = make_view(
        label="sdss_rgb",
        tier=VisualAssetTier.ASTROLENS_RENDERED,
        source_archive="SkyView",
        n_products=3,
    )
    mast_preview = make_view(label="mast_preview", tier=VisualAssetTier.RAW_ARCHIVE_PREVIEW)
    skyview_single = make_view(
        label="skyview_single",
        tier=VisualAssetTier.ASTROLENS_RENDERED,
        source_archive="SkyView",
        n_products=1,
    )
    no_asset = make_view(label="no_asset", tier=None)

    ranked = rank_views_by_source_quality(
        [mast_preview, no_asset, skyview_single, sdss_rgb, outreach, hla],
        max_views=10,
    )

    assert [view.label for view in ranked] == [
        "outreach",
        "hla",
        "sdss_rgb",
        "mast_preview",
        "skyview_single",
        "no_asset",
    ]


def test_sdss_rgb_composite_outranks_raw_mast_preview_even_with_adversarial_scores() -> None:
    # Worst-case refinements must never let a lower ladder band cross a higher one.
    sdss_rgb = make_view(
        label="sdss_rgb",
        tier=VisualAssetTier.ASTROLENS_RENDERED,
        source_archive="SkyView",
        n_products=3,
        target_status=TargetValidationStatus.OUT_OF_FRAME,
        scores=ViewScores(preview_quality=0.0, overall=0.0),
    )
    mast_preview = make_view(
        label="mast_preview",
        tier=VisualAssetTier.RAW_ARCHIVE_PREVIEW,
        target_status=TargetValidationStatus.CENTERED,
        scores=ViewScores(preview_quality=1.0, overall=1.0),
    )

    ranked = rank_views_by_source_quality([mast_preview, sdss_rgb], max_views=2)

    assert [view.label for view in ranked] == ["sdss_rgb", "mast_preview"]
    assert visual_source_quality_score(sdss_rgb) > visual_source_quality_score(mast_preview)


def test_single_survey_skyview_is_fallback_below_mast_preview() -> None:
    mast_preview = make_view(label="mast_preview", tier=VisualAssetTier.RAW_ARCHIVE_PREVIEW)
    skyview_single = make_view(
        label="skyview_single",
        tier=VisualAssetTier.ASTROLENS_RENDERED,
        source_archive="SkyView",
        n_products=1,
    )

    ranked = rank_views_by_source_quality([skyview_single, mast_preview], max_views=2)

    assert [view.label for view in ranked] == ["mast_preview", "skyview_single"]


def test_prefers_wavelength_diversity_over_second_same_band_view() -> None:
    vis_outreach = make_view(label="vis_outreach", tier=VisualAssetTier.OUTREACH_RELEASE)
    vis_hla = make_view(label="vis_hla", tier=VisualAssetTier.PROCESSED_ARCHIVE)
    ir_single = make_view(
        label="ir_single",
        tier=VisualAssetTier.ASTROLENS_RENDERED,
        source_archive="SkyView",
        band=BandFamily.INFRARED,
    )
    xray_single = make_view(
        label="xray_single",
        tier=VisualAssetTier.ASTROLENS_RENDERED,
        source_archive="SkyView",
        band=BandFamily.XRAY,
    )

    ranked = rank_views_by_source_quality(
        [vis_outreach, vis_hla, ir_single, xray_single],
        max_views=3,
    )

    labels = [view.label for view in ranked]
    bands = [view.band_family for view in ranked]
    assert labels[0] == "vis_outreach"  # single best view still leads
    assert BandFamily.INFRARED in bands and BandFamily.XRAY in bands  # missing bands filled
    assert "vis_hla" not in labels  # second optical pushed out for diversity


def test_no_asset_views_rank_last() -> None:
    mast_preview = make_view(label="preview", tier=VisualAssetTier.RAW_ARCHIVE_PREVIEW)
    no_asset = make_view(label="no_asset", tier=None)

    ranked = rank_views_by_source_quality([no_asset, mast_preview], max_views=1)

    assert [view.label for view in ranked] == ["preview"]


def test_missing_optional_fields_do_not_crash() -> None:
    without_asset = make_view(label="a", tier=None, scores=None)
    with_asset = make_view(
        label="b",
        tier=VisualAssetTier.RAW_ARCHIVE_PREVIEW,
        scores=None,
        target_status=None,
    )

    ranked = rank_views_by_source_quality([without_asset, with_asset], max_views=5)

    assert [view.label for view in ranked] == ["b", "a"]


def test_is_deterministic_and_breaks_ties_by_label() -> None:
    first = make_view(label="zzz", tier=VisualAssetTier.RAW_ARCHIVE_PREVIEW)
    second = make_view(label="aaa", tier=VisualAssetTier.RAW_ARCHIVE_PREVIEW)

    run_one = rank_views_by_source_quality([first, second], max_views=2)
    run_two = rank_views_by_source_quality([first, second], max_views=2)

    assert [view.label for view in run_one] == [view.label for view in run_two] == ["aaa", "zzz"]


def test_respects_max_views_and_rejects_nonpositive_limits() -> None:
    views = [
        make_view(label="vis", tier=VisualAssetTier.OUTREACH_RELEASE, band=BandFamily.VISIBLE),
        make_view(label="ir", tier=VisualAssetTier.PROCESSED_ARCHIVE, band=BandFamily.INFRARED),
        make_view(label="xray", tier=VisualAssetTier.RAW_ARCHIVE_PREVIEW, band=BandFamily.XRAY),
    ]

    assert len(rank_views_by_source_quality(views, max_views=2)) == 2
    assert rank_views_by_source_quality(views, max_views=0) == []
    assert rank_views_by_source_quality(views, max_views=-1) == []


def test_filters_to_requested_bands() -> None:
    visible = make_view(label="vis", tier=VisualAssetTier.OUTREACH_RELEASE, band=BandFamily.VISIBLE)
    infrared = make_view(
        label="ir",
        tier=VisualAssetTier.RAW_ARCHIVE_PREVIEW,
        band=BandFamily.INFRARED,
    )

    ranked = rank_views_by_source_quality(
        [visible, infrared],
        bands=[BandFamily.INFRARED],
        max_views=6,
    )

    assert [view.label for view in ranked] == ["ir"]


def test_preserves_view_identity_and_provenance() -> None:
    outreach = make_view(label="o", tier=VisualAssetTier.OUTREACH_RELEASE)

    ranked = rank_views_by_source_quality([outreach], max_views=1)

    assert ranked[0] is outreach  # ranking reads views, never copies or mutates them
    assert ranked[0].asset is not None
    assert ranked[0].asset.visual_tier == VisualAssetTier.OUTREACH_RELEASE
    assert ranked[0].asset.provenance is not None
    assert ranked[0].asset.provenance.source_record_id == "rec:o"
