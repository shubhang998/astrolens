from astrolens.core.enums import BandFamily
from astrolens.data.seed import DETAILED_OBJECT_BANDS, OBJECTS
from astrolens.services.evidence import evidence_service


def test_v1_has_at_least_50_curated_objects() -> None:
    assert len(OBJECTS) >= 50


def test_golden_objects_have_evidence_citations_reuse_and_caveats() -> None:
    for object_id in DETAILED_OBJECT_BANDS:
        bundle = evidence_service.bundle_for_object(object_id, max_views=6)
        assert bundle.object.id == object_id
        assert bundle.views
        for view in bundle.views:
            assert view.citations
            assert view.reuse.status
            assert view.caveats


def test_wavelength_diversity_keeps_crab_multi_band() -> None:
    bundle = evidence_service.bundle_for_query(
        "Crab Nebula",
        bands=[BandFamily.VISIBLE, BandFamily.INFRARED, BandFamily.XRAY, BandFamily.RADIO],
        max_views=6,
    )
    assert {view.band_family for view in bundle.views} == {
        "visible",
        "infrared",
        "xray",
        "radio",
    }
