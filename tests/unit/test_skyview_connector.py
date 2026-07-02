import asyncio
from typing import Any

import pytest

from astrolens.connectors.skyview import (
    SkyViewConnector,
    SkyViewProductSummary,
    SkyViewSearchResult,
)
from astrolens.core.enums import (
    BandFamily,
    CacheStatus,
    ErrorCode,
    SourceHealthStatus,
    VisualMode,
)
from astrolens.core.errors import AstroLensError
from astrolens.services.fits_renderer import FitsRenderRequest, FitsRenderResult
from astrolens.services.repository import repository
from astrolens.services.skyview_evidence import SkyViewEvidenceService


class FakeSkyViewClient:
    def __init__(self, urls: list[str] | None = None, error: Exception | None = None) -> None:
        self.urls = urls if urls is not None else [
            "https://skyview.example.test/sdss-g.fits",
            "https://skyview.example.test/sdss-r.fits",
            "https://skyview.example.test/sdss-i.fits",
            "https://skyview.example.test/2mass-k.fits",
        ]
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def get_image_list(self, position: Any, survey: list[str], **kwargs: Any) -> list[str]:
        self.calls.append({"position": position, "survey": survey, **kwargs})
        if self.error:
            raise self.error
        return self.urls


class FakeResolver:
    async def object_live(self, query: str) -> tuple[Any, CacheStatus]:
        assert query == "M87"
        return repository.get_object("astro:object:m87"), CacheStatus.MISS


class FakeSkyViewEvidenceConnector:
    async def search_generated_fits(self, **kwargs: Any) -> SkyViewSearchResult:
        assert kwargs["ra_deg"] == pytest.approx(187.70593077)
        assert kwargs["pixels"] == 256
        assert kwargs["visual_mode"] == VisualMode.CONTEXT
        return SkyViewSearchResult(
            request=kwargs,
            products=[
                SkyViewProductSummary(
                    survey="SDSSg",
                    band_family=BandFamily.VISIBLE,
                    wavelength_nm=477.0,
                    download_url="https://skyview.example.test/sdss-g.fits",
                    source_record_id="skyview:sdssg:187.7059308:12.3911233:0.03000:256",
                ),
                SkyViewProductSummary(
                    survey="SDSSr",
                    band_family=BandFamily.VISIBLE,
                    wavelength_nm=623.0,
                    download_url="https://skyview.example.test/sdss-r.fits",
                    source_record_id="skyview:sdssr:187.7059308:12.3911233:0.03000:256",
                ),
                SkyViewProductSummary(
                    survey="SDSSi",
                    band_family=BandFamily.VISIBLE,
                    wavelength_nm=763.0,
                    download_url="https://skyview.example.test/sdss-i.fits",
                    source_record_id="skyview:sdssi:187.7059308:12.3911233:0.03000:256",
                ),
            ],
        )


class FakeRenderer:
    def __init__(self) -> None:
        self.requests: list[FitsRenderRequest] = []

    def render(self, request: FitsRenderRequest) -> FitsRenderResult:
        self.requests.append(request)
        return FitsRenderResult(
            status="complete",
            asset_id="asset:test:skyview-render",
            asset_url="/v1/rendered/fake-skyview.png",
            cache_key="render:test:skyview",
        )


def test_survey_specs_cover_every_imaging_band() -> None:
    from astrolens.connectors.skyview import DEFAULT_SURVEY_NAMES_BY_BAND, SURVEY_SPECS

    covered = {spec.band_family for spec in SURVEY_SPECS}
    expected = {
        band
        for band in BandFamily
        if band not in {BandFamily.UNKNOWN, BandFamily.MULTIWAVELENGTH}
    }
    assert expected <= covered

    # Every default survey name must resolve to a spec, so band requests can't
    # silently reference a survey SkyView was never asked for.
    from astrolens.services.repository import normalize_query

    spec_names = {normalize_query(spec.survey) for spec in SURVEY_SPECS}
    for names in DEFAULT_SURVEY_NAMES_BY_BAND.values():
        for name in names:
            assert normalize_query(name) in spec_names, name


def test_gamma_and_millimeter_bands_request_new_surveys() -> None:
    client = FakeSkyViewClient(
        urls=["https://skyview.example.test/fermi.fits", "https://skyview.example.test/planck.fits"]
    )
    connector = SkyViewConnector(client=client)

    result = asyncio.run(
        connector.search_generated_fits(
            ra_deg=187.70593077,
            dec_deg=12.39112325,
            bands=[BandFamily.GAMMA, BandFamily.MILLIMETER],
        )
    )

    assert client.calls[0]["survey"] == ["Planck 217 I", "Fermi 5"] or client.calls[0][
        "survey"
    ] == ["Fermi 5", "Planck 217 I"]
    assert {product.band_family for product in result.products} == {
        BandFamily.GAMMA,
        BandFamily.MILLIMETER,
    }


def test_skyview_connector_normalizes_generated_fits_products() -> None:
    client = FakeSkyViewClient()
    connector = SkyViewConnector(client=client)

    result = asyncio.run(
        connector.search_generated_fits(
            ra_deg=187.70593077,
            dec_deg=12.39112325,
            radius_deg=0.03,
            bands=[BandFamily.VISIBLE, BandFamily.INFRARED],
            pixels=256,
            visual_mode=VisualMode.WIDE,
        )
    )

    assert result.request["visual_mode"] == "wide"
    assert [product.survey for product in result.products] == [
        "SDSSg",
        "SDSSr",
        "SDSSi",
        "2MASS-K",
    ]
    assert result.products[0].download_url == "https://skyview.example.test/sdss-g.fits"
    assert result.products[0].source_record_id.startswith("skyview:sdssg:")
    assert result.products[0].raw_metadata["pixels"] == 256
    assert result.products[0].raw_metadata["visual_mode"] == "wide"
    assert client.calls[0]["survey"] == ["SDSSg", "SDSSr", "SDSSi", "2MASS-K"]
    assert client.calls[0]["pixels"] == 256


class PerSurveyFakeClient:
    """SkyView client where one requested survey has no coverage."""

    def __init__(self, urls_by_survey: dict[str, str]) -> None:
        self.urls_by_survey = urls_by_survey
        self.calls: list[list[str]] = []

    def get_image_list(self, position: Any, survey: list[str], **kwargs: Any) -> list[str]:
        self.calls.append(list(survey))
        return [self.urls_by_survey[name] for name in survey if name in self.urls_by_survey]


def test_skyview_connector_requeries_per_survey_on_url_count_mismatch() -> None:
    # SDSSr missing: a bulk query returns 3 URLs for 4 surveys. Positional
    # pairing would attribute SDSSi's FITS to SDSSr and corrupt provenance.
    client = PerSurveyFakeClient(
        {
            "SDSSg": "https://skyview.example.test/sdss-g.fits",
            "SDSSi": "https://skyview.example.test/sdss-i.fits",
            "2MASS-K": "https://skyview.example.test/2mass-k.fits",
        }
    )
    connector = SkyViewConnector(client=client)

    result = asyncio.run(
        connector.search_generated_fits(
            ra_deg=187.70593077,
            dec_deg=12.39112325,
            radius_deg=0.03,
            bands=[BandFamily.VISIBLE, BandFamily.INFRARED],
            pixels=256,
        )
    )

    by_survey = {product.survey: product for product in result.products}
    assert set(by_survey) == {"SDSSg", "SDSSi", "2MASS-K"}
    assert by_survey["SDSSi"].download_url == "https://skyview.example.test/sdss-i.fits"
    assert by_survey["2MASS-K"].download_url == "https://skyview.example.test/2mass-k.fits"
    assert by_survey["2MASS-K"].band_family == BandFamily.INFRARED
    assert any("SDSSr" in warning for warning in result.warnings)


def test_skyview_connector_rejects_invalid_visual_mode() -> None:
    connector = SkyViewConnector(client=FakeSkyViewClient())

    with pytest.raises(AstroLensError) as exc_info:
        asyncio.run(
            connector.search_generated_fits(
                ra_deg=187.70593077,
                dec_deg=12.39112325,
                visual_mode="ultra-zoom",
            )
        )

    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert exc_info.value.retryable is False


def test_skyview_connector_empty_response_is_warning_not_crash() -> None:
    connector = SkyViewConnector(client=FakeSkyViewClient(urls=[]))

    result = asyncio.run(
        connector.search_generated_fits(
            ra_deg=187.70593077,
            dec_deg=12.39112325,
            bands=[BandFamily.VISIBLE],
        )
    )

    assert result.products == []
    assert "no public generated fits urls" in result.warnings[-1].lower()


def test_skyview_connector_ignores_unbounded_survey_names() -> None:
    client = FakeSkyViewClient()
    connector = SkyViewConnector(client=client)

    result = asyncio.run(
        connector.search_generated_fits(
            ra_deg=187.70593077,
            dec_deg=12.39112325,
            surveys=["https://example.test/arbitrary.fits", "Not A SkyView Survey"],
        )
    )

    assert result.products == []
    assert client.calls == []
    assert "no supported skyview surveys" in result.warnings[0].lower()


def test_skyview_connector_source_error_maps_to_astrolens_error() -> None:
    connector = SkyViewConnector(client=FakeSkyViewClient(error=RuntimeError("upstream down")))

    with pytest.raises(AstroLensError) as exc_info:
        asyncio.run(
            connector.search_generated_fits(
                ra_deg=187.70593077,
                dec_deg=12.39112325,
                bands=[BandFamily.VISIBLE],
            )
        )

    assert exc_info.value.code == ErrorCode.SOURCE_UNAVAILABLE
    assert exc_info.value.details["source"] == "SkyView"


def test_skyview_health_is_graceful_without_optional_dependency(monkeypatch) -> None:
    monkeypatch.setattr(
        "astrolens.connectors.skyview.importlib.util.find_spec",
        lambda _name: None,
    )
    connector = SkyViewConnector()

    health = asyncio.run(connector.healthcheck())

    assert health.name == "SkyView"
    assert health.status == SourceHealthStatus.UNAVAILABLE


def test_skyview_evidence_service_builds_rendered_views() -> None:
    renderer = FakeRenderer()
    service = SkyViewEvidenceService(
        resolver=FakeResolver(),  # type: ignore[arg-type]
        skyview=FakeSkyViewEvidenceConnector(),  # type: ignore[arg-type]
        renderer=renderer,  # type: ignore[arg-type]
    )

    bundle = asyncio.run(
        service.bundle_for_query(
            "M87",
            bands=[BandFamily.VISIBLE],
            pixels=256,
            max_views=1,
        )
    )

    assert bundle.object.name == "M87"
    assert len(bundle.views) == 1
    view = bundle.views[0]
    assert view.source_archive == "SkyView"
    assert view.id == "view:m87:skyview:visible-rgb"
    assert len(view.raw_products) == 3
    assert view.raw_products[0].download_url == "https://skyview.example.test/sdss-g.fits"
    assert view.asset
    assert view.asset.asset_url == "/v1/rendered/fake-skyview.png"
    assert view.asset.visual_tier == "astrolens_rendered"
    assert view.citations
    assert view.reuse.credit_required is True
    assert len(renderer.requests[0].products) == 3
    assert renderer.requests[0].products[0].download_url == "https://skyview.example.test/sdss-g.fits"
    assert renderer.requests[0].products[0].wavelength_nm == 477.0
