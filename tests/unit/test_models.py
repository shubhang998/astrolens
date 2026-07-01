from astrolens.core.enums import (
    BandFamily,
    CacheStatus,
    ReuseStatus,
    TargetValidationStatus,
    VisualAssetTier,
)
from astrolens.core.models import (
    Asset,
    CacheMeta,
    CelestialObject,
    Citation,
    Coordinates,
    EvidenceBundle,
    ImageProvenance,
    ResponseMeta,
    ReusePolicy,
    TargetValidation,
    View,
    ViewScores,
)


def test_evidence_bundle_requires_provenance_ready_shapes() -> None:
    citation = Citation(
        id="citation:test",
        title="Synthetic source record",
        source="AstroLens Test Fixture",
        url="https://example.org/source",
        credit_text="Example credit",
    )
    reuse = ReusePolicy(
        id="reuse:test",
        status=ReuseStatus.USABLE_WITH_CREDIT,
        credit_text="Example credit",
        policy_url="https://example.org/policy",
    )
    asset = Asset(
        id="asset:test",
        format="png",
        width=1920,
        height=1080,
        visual_tier=VisualAssetTier.PROCESSED_ARCHIVE,
        asset_url="https://example.org/asset.png",
        thumbnail_url="https://example.org/thumb.png",
        false_color=True,
        processing_note="Synthetic test asset.",
        selection_reason="Selected as processed archive product.",
        target_validation=TargetValidation(
            status=TargetValidationStatus.CENTERED,
            confidence=0.95,
            distance_arcsec=0.2,
            target_in_frame=True,
        ),
        provenance=ImageProvenance(
            visual_tier=VisualAssetTier.PROCESSED_ARCHIVE,
            source_archive="Synthetic",
            observation_id="obs:test",
            source_product_id="product:test",
            source_record_id="synthetic:test",
        ),
        credit_text="Example credit",
        reuse_policy_id="reuse:test",
        citations=[citation],
    )
    view = View(
        id="view:test",
        label="Visible-light view",
        band_family=BandFamily.VISIBLE,
        source_archive="Synthetic",
        asset=asset,
        reuse=reuse,
        citations=[citation],
        caveats=["Synthetic fixture; not real telescope evidence."],
        scores=ViewScores(overall=0.9),
    )
    bundle = EvidenceBundle(
        object=CelestialObject(
            id="astro:object:test",
            name="Test Object",
            coordinates=Coordinates(ra_deg=10.0, dec_deg=-5.0),
            identity_sources=[],
        ),
        views=[view],
        meta=ResponseMeta(
            request_id="req_test",
            cache=CacheMeta(status=CacheStatus.HIT, stale=False),
        ),
    )

    dumped = bundle.model_dump(mode="json")
    assert dumped["views"][0]["asset"]["citations"][0]["credit_text"] == "Example credit"
    assert dumped["views"][0]["asset"]["visual_tier"] == "processed_archive"
    assert dumped["views"][0]["asset"]["target_validation"]["status"] == "centered"
    assert dumped["views"][0]["asset"]["provenance"]["source_record_id"] == "synthetic:test"
    assert dumped["views"][0]["reuse"]["status"] == "usable_with_credit"
