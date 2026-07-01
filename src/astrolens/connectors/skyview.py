"""SkyView connector for generated public survey FITS cutouts."""

from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from astrolens.connectors.base import (
    ObservationCandidate,
    ObservationFilters,
    ProductCandidate,
    ResolvedObjectCandidate,
    SkyRegion,
)
from astrolens.core.enums import BandFamily, ErrorCode, SourceHealthStatus
from astrolens.core.errors import AstroLensError, UnsupportedConnectorOperation
from astrolens.core.models import AstroLensModel, Citation, PublicUrl, SourceHealth
from astrolens.services.repository import normalize_query

SKYVIEW_SOURCE_URL = "https://skyview.gsfc.nasa.gov/current/cgi/query.pl"
SKYVIEW_DOCS_URL = "https://skyview.gsfc.nasa.gov/current/help/help.html"


class SkyViewSurveySpec(AstroLensModel):
    """A bounded survey choice exposed by AstroLens."""

    survey: str
    band_family: BandFamily
    wavelength_nm: float | None = Field(default=None, gt=0.0)
    description: str


class SkyViewProductSummary(AstroLensModel):
    """One generated SkyView FITS product URL and its normalized metadata."""

    survey: str
    band_family: BandFamily
    wavelength_nm: float | None = Field(default=None, gt=0.0)
    download_url: PublicUrl
    file_format: str = "fits"
    product_type: str = "science"
    calibration_level: str = "3"
    source_record_id: str
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class SkyViewSearchResult(AstroLensModel):
    """Result of a bounded generated-cutout search."""

    source: str = "SkyView"
    source_url: PublicUrl = SKYVIEW_SOURCE_URL
    request: dict[str, Any] = Field(default_factory=dict)
    products: list[SkyViewProductSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


SURVEY_SPECS: tuple[SkyViewSurveySpec, ...] = (
    SkyViewSurveySpec(
        survey="SDSSg",
        band_family=BandFamily.VISIBLE,
        wavelength_nm=477.0,
        description="SDSS green-band optical image useful for high-quality visible composites",
    ),
    SkyViewSurveySpec(
        survey="SDSSr",
        band_family=BandFamily.VISIBLE,
        wavelength_nm=623.0,
        description="SDSS red-band optical image useful for high-quality visible composites",
    ),
    SkyViewSurveySpec(
        survey="SDSSi",
        band_family=BandFamily.VISIBLE,
        wavelength_nm=763.0,
        description="SDSS near-infrared optical image useful for high-quality visible composites",
    ),
    SkyViewSurveySpec(
        survey="DSS2 Blue",
        band_family=BandFamily.VISIBLE,
        wavelength_nm=445.0,
        description="older all-sky blue photographic plate, useful as a fallback",
    ),
    SkyViewSurveySpec(
        survey="DSS2 Red",
        band_family=BandFamily.VISIBLE,
        wavelength_nm=658.0,
        description="older all-sky red photographic plate, useful as a fallback",
    ),
    SkyViewSurveySpec(
        survey="DSS2 IR",
        band_family=BandFamily.VISIBLE,
        wavelength_nm=806.0,
        description="older all-sky near-infrared photographic plate, useful as a fallback",
    ),
    SkyViewSurveySpec(
        survey="2MASS-J",
        band_family=BandFamily.INFRARED,
        wavelength_nm=1250.0,
        description="near-infrared survey useful for stars and dust-penetrating views",
    ),
    SkyViewSurveySpec(
        survey="2MASS-H",
        band_family=BandFamily.INFRARED,
        wavelength_nm=1650.0,
        description="near-infrared survey useful for stars and dust-penetrating views",
    ),
    SkyViewSurveySpec(
        survey="2MASS-K",
        band_family=BandFamily.INFRARED,
        wavelength_nm=2200.0,
        description="near-infrared survey useful for cooler stars and dust-penetrating views",
    ),
    SkyViewSurveySpec(
        survey="GALEX Near UV",
        band_family=BandFamily.ULTRAVIOLET,
        wavelength_nm=230.0,
        description="ultraviolet survey useful for hot stars and recent star formation",
    ),
    SkyViewSurveySpec(
        survey="RASS-Cnt Broad",
        band_family=BandFamily.XRAY,
        wavelength_nm=1.2,
        description="broad ROSAT X-ray survey useful for energetic gas and compact sources",
    ),
    SkyViewSurveySpec(
        survey="VLA FIRST (1.4 GHz)",
        band_family=BandFamily.RADIO,
        wavelength_nm=214_000_000.0,
        description="higher-resolution 1.4 GHz radio survey useful for jets and compact sources",
    ),
    SkyViewSurveySpec(
        survey="NVSS",
        band_family=BandFamily.RADIO,
        wavelength_nm=214_000_000.0,
        description="wide-coverage 1.4 GHz radio survey useful as a fallback",
    ),
)

DEFAULT_SURVEY_NAMES_BY_BAND: dict[BandFamily, tuple[str, ...]] = {
    BandFamily.VISIBLE: ("SDSSg", "SDSSr", "SDSSi"),
    BandFamily.INFRARED: ("2MASS-K",),
    BandFamily.ULTRAVIOLET: ("GALEX Near UV",),
    BandFamily.XRAY: ("RASS-Cnt Broad",),
    BandFamily.RADIO: ("VLA FIRST (1.4 GHz)",),
}

SURVEY_SPECS_BY_NAME = {
    normalize_query(spec.survey): spec for spec in SURVEY_SPECS
}


class SkyViewConnector:
    """Bounded adapter around NASA SkyView generated FITS cutouts."""

    name = "SkyView"

    def __init__(
        self,
        client: Any | None = None,
        *,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.client = client
        self.timeout_seconds = timeout_seconds

    async def healthcheck(self) -> SourceHealth:
        if self.client is not None or importlib.util.find_spec("astroquery") is not None:
            return SourceHealth(
                name=self.name,
                status=SourceHealthStatus.OK,
                last_success_at=datetime.now(UTC),
                latency_ms=0,
            )
        return SourceHealth(
            name=self.name,
            status=SourceHealthStatus.UNAVAILABLE,
            last_error_at=datetime.now(UTC),
            latency_ms=0,
            )

    async def resolve_object(self, query: str) -> list[ResolvedObjectCandidate]:
        raise UnsupportedConnectorOperation(self.name, "resolve_object")

    async def search_observations(
        self,
        region: SkyRegion,
        filters: ObservationFilters,
    ) -> list[ObservationCandidate]:
        raise UnsupportedConnectorOperation(self.name, "search_observations")

    async def list_products(self, observation_id: str) -> list[ProductCandidate]:
        raise UnsupportedConnectorOperation(self.name, "list_products")

    async def get_citation(self, source_record_id: str) -> Citation:
        return Citation(
            id="citation:skyview:generated-fits",
            title="NASA SkyView generated FITS survey cutouts",
            source="SkyView",
            url=SKYVIEW_SOURCE_URL,
            credit_text="NASA SkyView and the source survey",
        )

    async def search_generated_fits(
        self,
        *,
        ra_deg: float,
        dec_deg: float,
        radius_deg: float = 0.03,
        bands: list[BandFamily] | None = None,
        surveys: list[str] | None = None,
        pixels: int = 512,
        cache: bool = False,
    ) -> SkyViewSearchResult:
        """Return generated public FITS URLs for bounded surveys around coordinates."""

        specs = survey_specs_for_request(bands=bands, surveys=surveys)
        if not specs:
            return SkyViewSearchResult(
                request={
                    "ra_deg": ra_deg,
                    "dec_deg": dec_deg,
                    "radius_deg": radius_deg,
                    "bands": [str(band) for band in bands or []],
                    "surveys": surveys or [],
                    "pixels": pixels,
                },
                warnings=["No supported SkyView surveys matched the request."],
            )

        request = {
            "ra_deg": ra_deg,
            "dec_deg": dec_deg,
            "radius_deg": radius_deg,
            "surveys": [spec.survey for spec in specs],
            "pixels": pixels,
        }
        try:
            image_urls = await asyncio.wait_for(
                asyncio.to_thread(
                    self._get_image_list,
                    ra_deg=ra_deg,
                    dec_deg=dec_deg,
                    radius_deg=radius_deg,
                    surveys=[spec.survey for spec in specs],
                    pixels=pixels,
                    cache=cache,
                ),
                timeout=self.timeout_seconds + 5.0,
            )
        except TimeoutError as exc:
            raise AstroLensError(
                ErrorCode.SOURCE_TIMEOUT,
                "SkyView did not return generated FITS URLs before the timeout.",
                retryable=True,
                details={"source": self.name, "request": request},
            ) from exc
        except AstroLensError:
            raise
        except Exception as exc:
            raise AstroLensError(
                ErrorCode.SOURCE_UNAVAILABLE,
                "SkyView generated-FITS lookup failed.",
                retryable=True,
                details={"source": self.name, "request": request, "error": str(exc)},
            ) from exc

        warnings: list[str] = []
        if len(image_urls) != len(specs):
            warnings.append(
                "SkyView returned a different number of generated products than requested."
            )

        products: list[SkyViewProductSummary] = []
        for spec, url in zip(specs, image_urls, strict=False):
            normalized_url = str(url)
            if not normalized_url.startswith(("http://", "https://")):
                warnings.append(f"SkyView returned a non-public URL for {spec.survey}.")
                continue
            source_record_id = skyview_source_record_id(
                spec=spec,
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                radius_deg=radius_deg,
                pixels=pixels,
            )
            products.append(
                SkyViewProductSummary(
                    survey=spec.survey,
                    band_family=spec.band_family,
                    wavelength_nm=spec.wavelength_nm,
                    download_url=normalized_url,
                    source_record_id=source_record_id,
                    raw_metadata={
                        "survey": spec.survey,
                        "description": spec.description,
                        "ra_deg": ra_deg,
                        "dec_deg": dec_deg,
                        "radius_deg": radius_deg,
                        "pixels": pixels,
                        "skyview_query_url": SKYVIEW_SOURCE_URL,
                    },
                )
            )

        if not products:
            warnings.append("SkyView returned no public generated FITS URLs.")

        return SkyViewSearchResult(request=request, products=products, warnings=warnings)

    def _get_image_list(
        self,
        *,
        ra_deg: float,
        dec_deg: float,
        radius_deg: float,
        surveys: list[str],
        pixels: int,
        cache: bool,
    ) -> list[str]:
        from astropy import units as u
        from astropy.coordinates import SkyCoord

        client = self.client or _astroquery_skyview_client()
        position = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
        return list(
            client.get_image_list(
                position=position,
                survey=surveys,
                radius=radius_deg * u.deg,
                pixels=int(pixels),
                cache=cache,
            )
        )


def survey_specs_for_request(
    *,
    bands: list[BandFamily] | None = None,
    surveys: list[str] | None = None,
) -> list[SkyViewSurveySpec]:
    """Return deterministic bounded survey specs for a request."""

    if surveys:
        specs: list[SkyViewSurveySpec] = []
        for survey in surveys:
            if not survey.strip():
                continue
            spec = SURVEY_SPECS_BY_NAME.get(normalize_query(survey))
            if spec:
                specs.append(spec)
        return specs
    selected_bands = list(dict.fromkeys(bands or DEFAULT_SURVEY_NAMES_BY_BAND.keys()))
    specs: list[SkyViewSurveySpec] = []
    for band in selected_bands:
        specs.extend(
            SURVEY_SPECS_BY_NAME[normalize_query(survey)]
            for survey in DEFAULT_SURVEY_NAMES_BY_BAND.get(band, ())
        )
    return specs


def skyview_source_record_id(
    *,
    spec: SkyViewSurveySpec,
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    pixels: int,
) -> str:
    return (
        "skyview:"
        f"{normalize_query(spec.survey)}:"
        f"{ra_deg:.7f}:{dec_deg:.7f}:{radius_deg:.5f}:{int(pixels)}"
    )


def _astroquery_skyview_client() -> Any:
    try:
        from astroquery.skyview import SkyView  # type: ignore[reportMissingImports]
    except ModuleNotFoundError as exc:
        raise AstroLensError(
            ErrorCode.SOURCE_UNAVAILABLE,
            "SkyView live access requires installing the optional astrolens[skyview] extra.",
            retryable=False,
            details={"source": "SkyView", "missing_dependency": "astroquery"},
        ) from exc
    return SkyView


skyview_connector = SkyViewConnector()
