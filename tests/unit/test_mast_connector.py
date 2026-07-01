import asyncio
import json
from pathlib import Path
from typing import Any

from astrolens.connectors.base import ResolvedObjectCandidate
from astrolens.connectors.mast import (
    MastConnector,
    MastImageSearchResult,
    MastObservationProducts,
    MastObservationSummary,
    MastProductSummary,
    mast_download_url,
)
from astrolens.core.enums import BandFamily, TargetValidationStatus, VisualAssetTier
from astrolens.services.live_evidence import LiveEvidenceService
from astrolens.services.live_ingestion import LiveIngestionService
from astrolens.services.preview_image_quality import (
    PreviewImageQuality,
    PreviewImageQualityAnalyzer,
)
from astrolens.services.repository import EvidenceRepository


def _fixture(name: str) -> dict[str, Any]:
    return json.loads(Path(f"tests/fixtures/mast/{name}.json").read_text())


class FixtureMastConnector(MastConnector):
    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        service = str(payload["service"])
        if service == "Mast.Caom.Filtered.Position":
            return _fixture("m87_observations")
        if service == "Mast.Caom.Products":
            return _fixture("m87_products")
        raise AssertionError(f"Unexpected MAST service: {service}")


class DuplicateFixtureMastConnector(MastConnector):
    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        service = str(payload["service"])
        if service == "Mast.Caom.Filtered.Position":
            fixture = _fixture("m87_observations")
            rows = fixture["data"]
            duplicate = dict(rows[0])
            duplicate["obsid"] = 999999999
            fixture["data"] = [dict(rows[0]), duplicate, dict(rows[1])]
            return fixture
        if service == "Mast.Caom.Products":
            return _fixture("m87_products")
        raise AssertionError(f"Unexpected MAST service: {service}")


class VisualRankingMastConnector(MastConnector):
    async def search_public_images(self, **kwargs: Any) -> MastImageSearchResult:
        jwst_uri = "mast:JWST/product/jw03055-o007_t007_nircam_clear-f277w_i2d.jpg"
        hst_uri = "mast:HST/product/hst_17902_02_wfc3_uvis_total_ifjp02_drc_color.jpg"
        return MastImageSearchResult(
            observations=[
                MastObservationSummary(
                    obsid="jwst-row",
                    obs_id="jwst-row",
                    collection="JWST",
                    instrument="NIRCAM/IMAGE",
                    filters="F277W",
                    target_name="M87",
                    data_rights="PUBLIC",
                    calibration_level="3",
                    band_family=BandFamily.INFRARED,
                ),
                MastObservationSummary(
                    obsid="hst-row",
                    obs_id="hst-row",
                    collection="HST",
                    instrument="WFC3/UVIS",
                    filters="detection",
                    target_name="M87",
                    data_rights="PUBLIC",
                    calibration_level="3",
                    band_family=BandFamily.VISIBLE,
                ),
            ],
            products_by_observation=[
                MastObservationProducts(
                    obsid="jwst-row",
                    obs_id="jwst-row",
                    products=[
                        MastProductSummary(
                            product_filename="jw03055-o007_t007_nircam_clear-f277w_i2d.jpg",
                            product_type="PREVIEW",
                            calibration_level="3",
                            data_uri=jwst_uri,
                            download_url=mast_download_url(jwst_uri),
                            description="Preview-Full",
                            file_format="jpg",
                            raw_metadata={
                                "dataURI": jwst_uri,
                                "productFilename": (
                                    "jw03055-o007_t007_nircam_clear-f277w_i2d.jpg"
                                ),
                                "project": "CALJWST",
                                "description": "Preview-Full",
                            },
                        )
                    ],
                ),
                MastObservationProducts(
                    obsid="hst-row",
                    obs_id="hst-row",
                    products=[
                        MastProductSummary(
                            product_filename=(
                                "hst_17902_02_wfc3_uvis_total_ifjp02_drc_color.jpg"
                            ),
                            product_type="PREVIEW",
                            calibration_level="3",
                            data_uri=hst_uri,
                            download_url=mast_download_url(hst_uri),
                            description="Preview-Full",
                            file_format="jpg",
                            raw_metadata={
                                "dataURI": hst_uri,
                                "productFilename": (
                                    "hst_17902_02_wfc3_uvis_total_ifjp02_drc_color.jpg"
                                ),
                                "project": "HAP-SVM",
                                "description": "Preview-Full",
                            },
                        )
                    ],
                ),
            ],
        )


class VisualDiversityMastConnector(MastConnector):
    async def search_public_images(self, **kwargs: Any) -> MastImageSearchResult:
        color_a_uri = "mast:HST/product/hst_17902_02_wfc3_uvis_total_ifjp02_drc_color.jpg"
        color_b_uri = "mast:HST/product/hst_17592_02_wfc3_uvis_total_ifbb02_drc_color.jpg"
        acs_uri = "mast:HST/product/hst_13731_03_acs_wfc_f814w_jcl403_drc.jpg"
        return MastImageSearchResult(
            observations=[
                MastObservationSummary(
                    obsid="hst-color-a",
                    obs_id="hst-color-a",
                    collection="HST",
                    instrument="WFC3/UVIS",
                    filters="detection",
                    target_name="M87",
                    data_rights="PUBLIC",
                    calibration_level="3",
                    band_family=BandFamily.VISIBLE,
                    distance_degrees=0.0,
                ),
                MastObservationSummary(
                    obsid="hst-color-b",
                    obs_id="hst-color-b",
                    collection="HST",
                    instrument="WFC3/UVIS",
                    filters="detection",
                    target_name="M87",
                    data_rights="PUBLIC",
                    calibration_level="3",
                    band_family=BandFamily.VISIBLE,
                    distance_degrees=0.0,
                ),
                MastObservationSummary(
                    obsid="hst-acs",
                    obs_id="hst-acs",
                    collection="HST",
                    instrument="ACS/WFC",
                    filters="F814W",
                    target_name="M87",
                    data_rights="PUBLIC",
                    calibration_level="3",
                    band_family=BandFamily.VISIBLE,
                    distance_degrees=0.0,
                ),
            ],
            products_by_observation=[
                MastObservationProducts(
                    obsid="hst-color-a",
                    obs_id="hst-color-a",
                    products=[_preview_product(color_a_uri, "HAP-SVM")],
                ),
                MastObservationProducts(
                    obsid="hst-color-b",
                    obs_id="hst-color-b",
                    products=[_preview_product(color_b_uri, "HAP-SVM")],
                ),
                MastObservationProducts(
                    obsid="hst-acs",
                    obs_id="hst-acs",
                    products=[_preview_product(acs_uri, "HAP-SVM")],
                ),
            ],
        )


class PixelQualityMastConnector(MastConnector):
    async def search_public_images(self, **kwargs: Any) -> MastImageSearchResult:
        bad_uri = "mast:HST/product/hst_bad_acs_wfc_f814w_jbad01_drc.jpg"
        good_uri = "mast:HST/product/hst_good_wfc3_uvis_f606w_jgood01_drc.jpg"
        return MastImageSearchResult(
            observations=[
                MastObservationSummary(
                    obsid="bad-preview",
                    obs_id="bad-preview",
                    collection="HST",
                    instrument="ACS/WFC",
                    filters="F814W",
                    target_name="M87",
                    data_rights="PUBLIC",
                    calibration_level="3",
                    band_family=BandFamily.VISIBLE,
                    distance_degrees=0.0,
                ),
                MastObservationSummary(
                    obsid="good-preview",
                    obs_id="good-preview",
                    collection="HST",
                    instrument="WFC3/UVIS",
                    filters="F606W",
                    target_name="M87",
                    data_rights="PUBLIC",
                    calibration_level="3",
                    band_family=BandFamily.VISIBLE,
                    distance_degrees=0.0,
                ),
            ],
            products_by_observation=[
                MastObservationProducts(
                    obsid="bad-preview",
                    obs_id="bad-preview",
                    products=[_preview_product(bad_uri, "HAP-SVM")],
                ),
                MastObservationProducts(
                    obsid="good-preview",
                    obs_id="good-preview",
                    products=[_preview_product(good_uri, "HAP-SVM")],
                ),
            ],
        )


class FakeSesameConnector:
    name = "Fake Sesame"

    async def resolve_object(self, query: str) -> list[ResolvedObjectCandidate]:
        return [
            ResolvedObjectCandidate(
                name=query,
                aliases=[query, "NGC 4486"],
                object_type="galaxy",
                ra_deg=187.70593077,
                dec_deg=12.39112325,
                source=self.name,
                source_url="https://example.org/sesame",
                confidence=0.95,
                raw_metadata={"oid": "fixture"},
            )
        ]


def _preview_product(uri: str, project: str) -> MastProductSummary:
    filename = uri.rsplit("/", maxsplit=1)[-1]
    return MastProductSummary(
        product_filename=filename,
        product_type="PREVIEW",
        calibration_level="3",
        data_uri=uri,
        download_url=mast_download_url(uri),
        description="Preview-Full",
        file_format="jpg",
        raw_metadata={
            "dataURI": uri,
            "productFilename": filename,
            "project": project,
            "description": "Preview-Full",
            "obs_collection": "HST",
        },
        )


class FakePreviewQualityAnalyzer(PreviewImageQualityAnalyzer):
    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores

    def assess_url(self, url: str) -> PreviewImageQuality:
        score = next(
            (value for key, value in self.scores.items() if key in url),
            0.5,
        )
        return PreviewImageQuality(status="ok", score=score)


def test_mast_download_url_preserves_public_file_endpoint() -> None:
    url = mast_download_url("mast:JWST/product/example_i2d.jpg")

    assert url == "https://mast.stsci.edu/api/v0.1/Download/file?uri=mast%3AJWST%2Fproduct%2Fexample_i2d.jpg"


def test_mast_fixture_search_normalizes_observations_and_products() -> None:
    connector = FixtureMastConnector()

    result = asyncio.run(
        connector.search_public_images(
            ra_deg=187.70593077,
            dec_deg=12.39112325,
            limit=2,
            product_limit=3,
            product_observation_limit=1,
        )
    )

    assert result.total_matching_images == 2
    assert result.observations[0].collection == "JWST"
    assert result.observations[0].band_family == "infrared"
    assert result.observations[0].wavelength_min_nm == 1300.0
    assert result.products_by_observation[0].products[0].file_format == "jpg"
    assert result.products_by_observation[0].products[0].download_url is not None


def test_mast_search_deduplicates_observation_rows_before_limit() -> None:
    connector = DuplicateFixtureMastConnector()

    result = asyncio.run(
        connector.search_public_images(
            ra_deg=187.70593077,
            dec_deg=12.39112325,
            limit=3,
            product_limit=3,
            product_observation_limit=3,
        )
    )

    obsids = [observation.obsid for observation in result.observations]
    assert obsids == list(dict.fromkeys(obsids))
    assert len(result.observations) == 2
    assert result.total_matching_images == 2
    assert len(result.products_by_observation) == 2


def test_live_evidence_service_builds_bundle_and_caches_fixture_result() -> None:
    resolver = LiveIngestionService(
        repo=EvidenceRepository(),
        connector=FakeSesameConnector(),
    )
    service = LiveEvidenceService(resolver=resolver, mast=FixtureMastConnector())

    first = asyncio.run(service.bundle_for_query("M87", max_views=2))
    second = asyncio.run(service.bundle_for_query("M87", max_views=2))

    assert first.object.name == "M87"
    assert first.views
    assert first.views[0].source_archive == "MAST"
    assert first.views[0].raw_products
    assert first.views[0].asset is not None
    assert first.views[0].asset.asset_url is not None
    assert first.views[0].asset.visual_tier == VisualAssetTier.PROCESSED_ARCHIVE
    assert first.views[0].asset.provenance is not None
    assert first.views[0].asset.provenance.source_archive == "MAST"
    assert first.views[0].asset.target_validation is not None
    assert first.views[0].asset.target_validation.status == TargetValidationStatus.CENTERED
    assert "i2d.jpg" in first.views[0].asset.asset_url
    assert first.meta.cache is not None
    assert second.meta.cache is not None
    assert first.meta.cache.status == "miss"
    assert second.meta.cache.status == "hit"


def test_best_visual_prefers_color_archive_product_over_single_filter_preview() -> None:
    resolver = LiveIngestionService(
        repo=EvidenceRepository(),
        connector=FakeSesameConnector(),
    )
    service = LiveEvidenceService(resolver=resolver, mast=VisualRankingMastConnector())

    bundle = asyncio.run(service.bundle_for_query("M87", max_views=2, rank_mode="best_visual"))

    assert bundle.views[0].facility == "Hubble Space Telescope"
    assert bundle.views[0].asset is not None
    assert bundle.views[0].asset.selection_reason
    assert "drc_color" in str(bundle.views[0].asset.asset_url)


def test_live_visual_metadata_avoids_repeated_publication_disclaimers() -> None:
    resolver = LiveIngestionService(
        repo=EvidenceRepository(),
        connector=FakeSesameConnector(),
    )
    service = LiveEvidenceService(resolver=resolver, mast=VisualRankingMastConnector())

    bundle = asyncio.run(service.bundle_for_query("M87", max_views=2, rank_mode="best_visual"))

    exposed_text = " ".join(
        [
            " ".join(view.caveats)
            for view in bundle.views
        ]
        + [
            view.asset.processing_note or ""
            for view in bundle.views
            if view.asset
        ]
        + [
            " ".join(view.asset.provenance.notes)
            for view in bundle.views
            if view.asset and view.asset.provenance
        ]
        + [
            " ".join(view.reuse.notes)
            for view in bundle.views
        ]
    ).lower()
    assert "publication" not in exposed_text
    assert "calibrated fits" not in exposed_text


def test_best_visual_diversifies_near_duplicate_archive_visuals() -> None:
    resolver = LiveIngestionService(
        repo=EvidenceRepository(),
        connector=FakeSesameConnector(),
    )
    service = LiveEvidenceService(resolver=resolver, mast=VisualDiversityMastConnector())

    bundle = asyncio.run(service.bundle_for_query("M87", max_views=2, rank_mode="best_visual"))

    urls = [str(view.asset.asset_url) for view in bundle.views if view.asset]
    assert len(urls) == 2
    assert sum("wfc3_uvis" in url for url in urls) == 1
    assert any("acs_wfc" in url for url in urls)


def test_best_visual_uses_pixel_quality_when_available() -> None:
    resolver = LiveIngestionService(
        repo=EvidenceRepository(),
        connector=FakeSesameConnector(),
    )
    service = LiveEvidenceService(
        resolver=resolver,
        mast=PixelQualityMastConnector(),
        preview_quality=FakePreviewQualityAnalyzer({"bad": 0.15, "good": 0.95}),
    )

    bundle = asyncio.run(service.bundle_for_query("M87", max_views=2, rank_mode="best_visual"))

    assert bundle.views[0].asset is not None
    assert "good" in str(bundle.views[0].asset.asset_url)
    assert bundle.views[0].scores is not None
    assert bundle.views[0].scores.preview_quality == 0.95


def test_latest_keeps_distinct_archive_products_from_same_visual_family() -> None:
    resolver = LiveIngestionService(
        repo=EvidenceRepository(),
        connector=FakeSesameConnector(),
    )
    service = LiveEvidenceService(resolver=resolver, mast=VisualDiversityMastConnector())

    bundle = asyncio.run(service.bundle_for_query("M87", max_views=2, rank_mode="latest"))

    urls = [str(view.asset.asset_url) for view in bundle.views if view.asset]
    assert len(urls) == 2
    assert all("wfc3_uvis" in url for url in urls)
