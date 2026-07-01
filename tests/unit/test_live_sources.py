"""Tests for cross-source dispatch and quality-ranked merging in LiveSourceEvidenceService.

No live network calls: the MAST and SkyView sub-services are replaced with fakes
that return canned EvidenceBundles.
"""

import asyncio
from typing import Any

from astrolens.core.enums import (
    BandFamily,
    CacheStatus,
    TargetValidationStatus,
    VisualAssetTier,
)
from astrolens.core.models import (
    Asset,
    CacheMeta,
    CelestialObject,
    Coordinates,
    CrossWavelengthNote,
    EvidenceBundle,
    ImageProvenance,
    ResponseMeta,
    ReusePolicy,
    TargetValidation,
    View,
    ViewScores,
    WarningMessage,
)
from astrolens.services.live_sources import LiveSourceEvidenceService

_REUSE = ReusePolicy(id="reuse:test")
_OBJECT = CelestialObject(
    id="astro:object:m87",
    name="M87",
    coordinates=Coordinates(ra_deg=187.70593, dec_deg=12.39112),
)


def _view(
    label: str,
    tier: VisualAssetTier,
    band: BandFamily,
    source_archive: str,
    *,
    n_products: int = 1,
) -> View:
    return View(
        id=f"view:{label}",
        label=label,
        band_family=band,
        source_archive=source_archive,
        asset=Asset(
            id=f"asset:{label}",
            source_product_ids=[f"product:{label}:{index}" for index in range(n_products)],
            format="png",
            visual_tier=tier,
            asset_url="https://example.test/a.png",
            target_validation=TargetValidation(status=TargetValidationStatus.CENTERED),
            provenance=ImageProvenance(visual_tier=tier, source_record_id=f"rec:{label}"),
            reuse_policy_id=_REUSE.id,
        ),
        reuse=_REUSE,
        scores=ViewScores(overall=0.8),
    )


def _bundle(
    views: list[View],
    warnings: list[WarningMessage],
    notes: list[CrossWavelengthNote],
) -> EvidenceBundle:
    return EvidenceBundle(
        object=_OBJECT,
        views=views,
        cross_wavelength_notes=notes,
        warnings=warnings,
        meta=ResponseMeta(request_id="req_test", cache=CacheMeta(status=CacheStatus.MISS)),
    )


class _FakeSource:
    def __init__(self, bundle: EvidenceBundle) -> None:
        self.bundle = bundle
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def bundle_for_query(self, query: str, **kwargs: Any) -> EvidenceBundle:
        self.calls.append((query, kwargs))
        return self.bundle


def _service(mast: _FakeSource, skyview: _FakeSource) -> LiveSourceEvidenceService:
    # The service injects its source dependencies; fakes stand in for the concrete
    # MAST/SkyView services so the merge path can be exercised without network I/O.
    return LiveSourceEvidenceService(mast=mast, skyview=skyview)  # type: ignore[arg-type]


def _visible_note() -> CrossWavelengthNote:
    return CrossWavelengthNote(
        band_family=BandFamily.VISIBLE,
        general_meaning="Visible light traces starlight.",
        confidence=0.9,
    )


def _infrared_note() -> CrossWavelengthNote:
    return CrossWavelengthNote(
        band_family=BandFamily.INFRARED,
        general_meaning="Infrared traces dust and cooler material.",
        confidence=0.9,
    )


def test_merge_ranks_sdss_rgb_above_mast_raw_preview_and_keeps_provenance() -> None:
    mast_raw = _view("mast_raw", VisualAssetTier.RAW_ARCHIVE_PREVIEW, BandFamily.VISIBLE, "MAST")
    sdss_rgb = _view(
        "sdss_rgb",
        VisualAssetTier.ASTROLENS_RENDERED,
        BandFamily.VISIBLE,
        "SkyView",
        n_products=3,
    )
    sky_ir = _view("sky_ir", VisualAssetTier.ASTROLENS_RENDERED, BandFamily.INFRARED, "SkyView")

    mast = _FakeSource(
        _bundle([mast_raw], [WarningMessage(code="W_MAST", message="mast note")], [_visible_note()])
    )
    skyview = _FakeSource(
        _bundle(
            [sdss_rgb, sky_ir],
            [WarningMessage(code="W_SKY", message="skyview note")],
            [_visible_note(), _infrared_note()],
        )
    )
    service = _service(mast, skyview)

    bundle = asyncio.run(service.bundle_for_query("M87", sources=("mast", "skyview"), max_views=3))

    labels = [view.label for view in bundle.views]
    assert labels[0] == "sdss_rgb"  # SDSS RGB composite beats the raw MAST preview
    assert set(labels) == {"sdss_rgb", "sky_ir", "mast_raw"}
    # Provenance/tier metadata for the chosen visual is preserved verbatim.
    top_asset = bundle.views[0].asset
    assert top_asset is not None
    assert top_asset.visual_tier == VisualAssetTier.ASTROLENS_RENDERED
    assert top_asset.provenance is not None
    assert top_asset.provenance.source_record_id == "rec:sdss_rgb"
    # Warnings from both sources survive the merge.
    assert {warning.code for warning in bundle.warnings} == {"W_MAST", "W_SKY"}
    # Notes are aligned to the bands actually shown, deduped by band.
    note_bands = [note.band_family for note in bundle.cross_wavelength_notes]
    assert len(note_bands) == len(set(note_bands))
    assert set(note_bands) <= {view.band_family for view in bundle.views}
    # Both sources were consulted.
    assert mast.calls and skyview.calls


def test_single_source_mast_delegates_without_calling_skyview() -> None:
    mast_view = _view("m", VisualAssetTier.OUTREACH_RELEASE, BandFamily.VISIBLE, "MAST")
    mast = _FakeSource(_bundle([mast_view], [], []))
    skyview = _FakeSource(_bundle([], [], []))
    service = _service(mast, skyview)

    bundle = asyncio.run(service.bundle_for_query("M87", sources=("mast",)))

    assert bundle is mast.bundle  # delegated straight through, no re-ranking wrapper
    assert skyview.calls == []


def test_single_source_skyview_delegates_without_calling_mast() -> None:
    skyview_view = _view("s", VisualAssetTier.ASTROLENS_RENDERED, BandFamily.XRAY, "SkyView")
    mast = _FakeSource(_bundle([], [], []))
    skyview = _FakeSource(_bundle([skyview_view], [], []))
    service = _service(mast, skyview)

    bundle = asyncio.run(service.bundle_for_query("M87", sources=("skyview",)))

    assert bundle is skyview.bundle
    assert mast.calls == []
