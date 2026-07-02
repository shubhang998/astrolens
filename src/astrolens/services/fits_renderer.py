"""Dependency-backed FITS render planning and cached image generation.

This module avoids importing astropy, numpy, or Pillow at import time so the API
can still start without the optional image stack. When those libraries are
installed, it can turn manageable calibrated FITS products into cached PNG/JPG
derivatives with stable provenance-friendly recipes.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from itertools import combinations
from pathlib import Path
from typing import Any, Literal, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from pydantic import Field

from astrolens.core.models import AstroLensModel, DataProduct

RENDER_PIPELINE_VERSION = "fits-render:v13"
DEFAULT_RENDER_CACHE_DIR = ".astrolens-cache/renders"
DEFAULT_MAX_SOURCE_FILE_MB = 300.0
# Hosts (matched by registered-domain suffix) the renderer may download FITS
# payloads from. Extend at deploy time with ASTROLENS_RENDER_URL_ALLOWLIST
# (comma-separated suffixes) rather than widening this default.
DEFAULT_ALLOWED_URL_HOST_SUFFIXES = (
    "stsci.edu",
    "gsfc.nasa.gov",
)
RENDER_URL_ALLOWLIST_ENV = "ASTROLENS_RENDER_URL_ALLOWLIST"
SUPPORTED_FITS_FORMATS = {"fit", "fits", "fit.gz", "fits.gz"}
REJECTED_PRODUCT_TYPES = {"catalog", "event", "info", "preview", "raw", "spectrum", "spectra"}
UNCALIBRATED_TOKENS = {"raw", "uncal", "uncalibrated"}
CALIBRATED_FILENAME_HINTS = (
    "_cal",
    "_crf",
    "_drc",
    "_drz",
    "_flc",
    "_flt",
    "_i2d",
    "_rate",
)
OUTPUT_SIZES: dict[str, tuple[int, int]] = {
    "thumbnail": (512, 512),
    "standard": (1920, 1080),
    "square": (1080, 1080),
}
FILTER_WAVELENGTH_NM = {
    "FUV": 150.0,
    "NUV": 230.0,
    "U": 365.0,
    "B": 445.0,
    "V": 551.0,
    "R": 658.0,
    "I": 806.0,
    "Y": 1020.0,
    "J": 1250.0,
    "H": 1650.0,
    "K": 2200.0,
}


RenderStatus = Literal["planned", "complete", "unsupported", "failed"]
OutputFormat = Literal["png", "jpg", "jpeg"]
OutputSize = Literal["thumbnail", "standard", "square"]
StretchMode = Literal["asinh", "linear", "log", "sqrt"]
RgbChannelName = Literal["red", "green", "blue"]
AlignmentMode = Literal["single_channel", "wcs_reproject", "fallback_single_channel"]


class FitsRendererDependencies(AstroLensModel):
    """Availability of optional libraries needed for actual FITS rendering."""

    astropy: bool = False
    numpy: bool = False
    pillow: bool = False
    reproject: bool = False

    @property
    def ready(self) -> bool:
        """Return whether all optional rendering dependencies are importable."""

        return self.astropy and self.numpy and self.pillow

    @property
    def missing(self) -> list[str]:
        """Return human-facing dependency names that are unavailable."""

        missing: list[str] = []
        if not self.astropy:
            missing.append("astropy")
        if not self.numpy:
            missing.append("numpy")
        if not self.pillow:
            missing.append("Pillow")
        return missing

    @property
    def alignment_ready(self) -> bool:
        """Return whether WCS reprojection is available for multi-product RGB."""

        return self.ready and self.reproject


class SourceFitsProduct(AstroLensModel):
    """Normalized source product inputs for FITS render planning."""

    id: str
    download_url: str | None = None
    file_name: str | None = None
    file_format: str | None = None
    product_type: str | None = None
    calibration_level: float | None = Field(default=None, ge=0.0)
    file_size_mb: float | None = Field(default=None, ge=0.0)
    filter_name: str | None = None
    wavelength_nm: float | None = Field(default=None, gt=0.0)
    instrument: str | None = None
    observation_id: str | None = None
    source_record_id: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_data_product(cls, product: DataProduct) -> SourceFitsProduct:
        """Build a render input from the public AstroLens data product model."""

        return cls(
            id=product.id,
            download_url=product.download_url,
            file_name=_metadata_string(
                product.raw_metadata,
                "productFilename",
                "filename",
                "fileName",
            ),
            file_format=product.file_format,
            product_type=product.product_type,
            calibration_level=_safe_float(product.calibration_level),
            file_size_mb=product.file_size_mb,
            filter_name=_metadata_string(product.raw_metadata, "filters", "filter", "FILTER"),
            wavelength_nm=_safe_float(
                product.raw_metadata.get("wavelength_nm")
                or product.raw_metadata.get("wavelength")
                or product.raw_metadata.get("em_min")
            ),
            observation_id=product.observation_id,
            source_record_id=product.source_record_id,
            raw_metadata=product.raw_metadata,
        )


class ProductEligibility(AstroLensModel):
    """Eligibility decision for one source product."""

    product_id: str
    eligible: bool
    reason: str
    score: float = Field(ge=0.0, le=1.0)
    normalized_format: str | None = None
    calibration_level: float | None = None


class FitsRenderRequest(AstroLensModel):
    """Request to plan or execute a calibrated FITS render."""

    products: list[SourceFitsProduct] = Field(min_length=1)
    object_id: str | None = None
    output_format: OutputFormat = "png"
    size: OutputSize = "standard"
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    stretch: StretchMode = "asinh"
    max_source_file_mb: float | None = Field(default=DEFAULT_MAX_SOURCE_FILE_MB, gt=0.0)
    # When True the caller has already chosen exactly the products to composite
    # (e.g. one per wavelength band across archives); skip visit-coherence
    # grouping and map channels purely by wavelength.
    preselected: bool = False


class RenderChannel(AstroLensModel):
    """One RGB channel assignment in a FITS render recipe."""

    channel: RgbChannelName
    product_id: str
    filter_name: str | None = None
    wavelength_nm: float | None = Field(default=None, gt=0.0)


class RgbMapping(AstroLensModel):
    """Deterministic mapping from source products to RGB channels."""

    red: RenderChannel
    green: RenderChannel
    blue: RenderChannel
    false_color: bool = True
    note: str

    @property
    def channels(self) -> list[RenderChannel]:
        """Return channels in image order."""

        return [self.red, self.green, self.blue]


class RenderRecipe(AstroLensModel):
    """Deterministic render plan for later FITS download and composite creation."""

    cache_key: str
    asset_id: str
    source_products: list[SourceFitsProduct]
    rgb_mapping: RgbMapping
    output_format: OutputFormat
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    stretch: StretchMode
    false_color: bool
    alignment_mode: AlignmentMode
    reference_product_id: str | None = None
    overlap_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)


class FitsRenderResult(AstroLensModel):
    """Typed result from the renderer facade."""

    status: RenderStatus
    asset_id: str | None = None
    asset_url: str | None = None
    # Local cache path for in-process consumers; excluded so API/MCP responses
    # never expose server filesystem layout.
    file_path: str | None = Field(default=None, exclude=True)
    cache_key: str | None = None
    recipe: RenderRecipe | None = None
    dependencies: FitsRendererDependencies = Field(default_factory=FitsRendererDependencies)
    missing_dependencies: list[str] = Field(default_factory=list)
    eligibility: list[ProductEligibility] = Field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class LoadedFitsImage:
    """Pixel data and celestial WCS read from the actual image HDU."""

    array: Any
    wcs: Any | None


class FitsRenderer:
    """Small facade for planning and eventually rendering calibrated FITS assets."""

    def __init__(
        self,
        dependencies: FitsRendererDependencies | None = None,
        *,
        cache_dir: str | Path | None = None,
        public_base_url: str | None = None,
        timeout_seconds: float = 60.0,
        allowed_url_host_suffixes: tuple[str, ...] | None = None,
        allow_file_urls: bool = False,
    ) -> None:
        self.dependencies = dependencies
        self.cache_dir = Path(
            cache_dir or os.getenv("ASTROLENS_RENDER_CACHE_DIR") or DEFAULT_RENDER_CACHE_DIR
        )
        self.public_base_url = public_base_url or os.getenv("ASTROLENS_PUBLIC_BASE_URL")
        self.timeout_seconds = timeout_seconds
        self.allowed_url_host_suffixes = (
            allowed_url_host_suffixes
            if allowed_url_host_suffixes is not None
            else _configured_url_host_suffixes()
        )
        self.allow_file_urls = allow_file_urls

    def create_recipe(self, request: FitsRenderRequest) -> RenderRecipe:
        """Create a deterministic render recipe for eligible calibrated FITS products."""

        return create_render_recipe(request)

    def render(self, request: FitsRenderRequest) -> FitsRenderResult:
        """Return a planned render or graceful unsupported result.

        Actual FITS download, pixel scaling, and image writing run only when the
        optional rendering dependencies are available. Otherwise callers still get
        a deterministic recipe and clear unsupported result.
        """

        eligibility = [product_eligibility(product) for product in request.products]
        try:
            recipe = create_render_recipe(request)
        except ValueError as exc:
            return FitsRenderResult(
                status="unsupported",
                dependencies=self._dependencies(),
                eligibility=eligibility,
                error=str(exc),
            )

        dependencies = self._dependencies()
        if not dependencies.ready:
            missing = dependencies.missing
            return FitsRenderResult(
                status="unsupported",
                asset_id=recipe.asset_id,
                cache_key=recipe.cache_key,
                recipe=recipe,
                dependencies=dependencies,
                missing_dependencies=missing,
                eligibility=eligibility,
                error=(
                    "FITS rendering requires optional dependencies that are not installed: "
                    f"{', '.join(missing)}."
                ),
            )

        return self._execute_render(
            request=request,
            recipe=recipe,
            dependencies=dependencies,
            eligibility=eligibility,
        )

    def _dependencies(self) -> FitsRendererDependencies:
        return self.dependencies or detect_fits_render_dependencies()

    def _execute_render(
        self,
        *,
        request: FitsRenderRequest,
        recipe: RenderRecipe,
        dependencies: FitsRendererDependencies,
        eligibility: list[ProductEligibility],
    ) -> FitsRenderResult:
        active_recipe = recipe
        output_path = self._output_path(active_recipe)
        if output_path.exists():
            cached_recipe = self._load_cached_recipe(output_path, fallback=active_recipe)
            return FitsRenderResult(
                status="complete",
                asset_id=cached_recipe.asset_id,
                asset_url=self._asset_url(output_path),
                file_path=str(output_path),
                cache_key=cached_recipe.cache_key,
                recipe=cached_recipe,
                dependencies=dependencies,
                eligibility=eligibility,
            )
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            payloads = self._download_recipe_products(recipe, request)
            try:
                rendered = _compose_rgb_image(
                    recipe,
                    payloads,
                    allow_reprojection=dependencies.alignment_ready,
                )
            except ValueError as exc:
                if not _recipe_uses_multiple_source_products(recipe):
                    raise
                active_recipe = _fallback_single_channel_recipe(
                    request=request,
                    source_recipe=recipe,
                    reason=str(exc),
                )
                output_path = self._output_path(active_recipe)
                if output_path.exists():
                    cached_recipe = self._load_cached_recipe(output_path, fallback=active_recipe)
                    return FitsRenderResult(
                        status="complete",
                        asset_id=cached_recipe.asset_id,
                        asset_url=self._asset_url(output_path),
                        file_path=str(output_path),
                        cache_key=cached_recipe.cache_key,
                        recipe=cached_recipe,
                        dependencies=dependencies,
                        eligibility=eligibility,
                    )
                fallback_payloads = {
                    product.id: payloads[product.id]
                    for product in active_recipe.source_products
                    if product.id in payloads
                }
                rendered = _compose_rgb_image(
                    active_recipe,
                    fallback_payloads,
                    allow_reprojection=False,
                )
            rendered.save(
                output_path,
                format=_pillow_format(active_recipe.output_format),
                quality=94,
            )
            self._write_cached_recipe(output_path, active_recipe)
        except ValueError as exc:
            return FitsRenderResult(
                status="unsupported",
                asset_id=active_recipe.asset_id,
                cache_key=active_recipe.cache_key,
                recipe=active_recipe,
                dependencies=dependencies,
                eligibility=eligibility,
                error=str(exc),
            )
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            return FitsRenderResult(
                status="failed",
                asset_id=active_recipe.asset_id,
                cache_key=active_recipe.cache_key,
                recipe=active_recipe,
                dependencies=dependencies,
                eligibility=eligibility,
                error=str(exc),
            )
        return FitsRenderResult(
            status="complete",
            asset_id=active_recipe.asset_id,
            asset_url=self._asset_url(output_path),
            file_path=str(output_path),
            cache_key=active_recipe.cache_key,
            recipe=active_recipe,
            dependencies=dependencies,
            eligibility=eligibility,
        )

    def _download_recipe_products(
        self,
        recipe: RenderRecipe,
        request: FitsRenderRequest,
    ) -> dict[str, bytes]:
        payloads: dict[str, bytes] = {}
        for product in recipe.source_products:
            if product.id in payloads:
                continue
            payloads[product.id] = self._download_product(product, request)
        return payloads

    def _download_product(
        self,
        product: SourceFitsProduct,
        request: FitsRenderRequest,
    ) -> bytes:
        if not product.download_url:
            raise ValueError(f"FITS product {product.id} has no download URL.")
        validate_download_url(
            product.download_url,
            product_id=product.id,
            allowed_host_suffixes=self.allowed_url_host_suffixes,
            allow_file_urls=self.allow_file_urls,
        )
        max_mb = request.max_source_file_mb
        if (
            max_mb is not None
            and product.file_size_mb is not None
            and product.file_size_mb > max_mb
        ):
            raise ValueError(
                f"FITS product {product.id} is {product.file_size_mb:.1f} MB, "
                f"above the {max_mb:.1f} MB render limit."
            )
        max_bytes = int((max_mb or DEFAULT_MAX_SOURCE_FILE_MB) * 1024 * 1024)
        http_request = Request(
            product.download_url,
            headers={"User-Agent": "AstroLens/0.1 fits-render"},
            method="GET",
        )
        with urlopen(http_request, timeout=self.timeout_seconds) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise ValueError(
                    f"FITS product {product.id} is larger than the render limit."
                )
            payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError(f"FITS product {product.id} is larger than the render limit.")
        return payload

    def _output_path(self, recipe: RenderRecipe) -> Path:
        extension = "jpg" if recipe.output_format == "jpeg" else recipe.output_format
        digest = recipe.asset_id.rsplit(":", maxsplit=1)[-1]
        return self.cache_dir / f"{digest}.{extension}"

    def _recipe_sidecar_path(self, output_path: Path) -> Path:
        return output_path.with_suffix(f"{output_path.suffix}.recipe.json")

    def _load_cached_recipe(self, output_path: Path, *, fallback: RenderRecipe) -> RenderRecipe:
        sidecar_path = self._recipe_sidecar_path(output_path)
        try:
            cached = RenderRecipe.model_validate_json(
                sidecar_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return fallback
        if cached.asset_id != fallback.asset_id or cached.cache_key != fallback.cache_key:
            return fallback
        return cached

    def _write_cached_recipe(self, output_path: Path, recipe: RenderRecipe) -> None:
        sidecar_path = self._recipe_sidecar_path(output_path)
        sidecar_path.write_text(recipe.model_dump_json(indent=2), encoding="utf-8")

    def _asset_url(self, output_path: Path) -> str:
        path = f"/v1/rendered/{quote(output_path.name)}"
        if not self.public_base_url:
            return path
        return f"{self.public_base_url.rstrip('/')}{path}"


def detect_fits_render_dependencies() -> FitsRendererDependencies:
    """Detect optional FITS rendering dependencies without importing them."""

    return FitsRendererDependencies(
        astropy=_module_available("astropy"),
        numpy=_module_available("numpy"),
        pillow=_module_available("PIL"),
        reproject=_module_available("reproject"),
    )


def _configured_url_host_suffixes() -> tuple[str, ...]:
    configured = os.getenv(RENDER_URL_ALLOWLIST_ENV, "")
    extra = tuple(
        suffix.strip().lower().lstrip(".")
        for suffix in configured.split(",")
        if suffix.strip()
    )
    return DEFAULT_ALLOWED_URL_HOST_SUFFIXES + extra


def validate_download_url(
    url: str,
    *,
    product_id: str,
    allowed_host_suffixes: tuple[str, ...],
    allow_file_urls: bool = False,
) -> None:
    """Reject download URLs that are not https to a trusted archive host.

    Raises ValueError so callers surface a graceful ``unsupported`` result
    instead of fetching attacker-controlled schemes or internal hosts.
    """

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme == "file":
        if allow_file_urls:
            return
        raise ValueError(f"FITS product {product_id} download URL scheme 'file' is not allowed.")
    if scheme != "https":
        raise ValueError(
            f"FITS product {product_id} download URL must use https, got '{scheme or 'none'}'."
        )
    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError(f"FITS product {product_id} download URL has no host.")
    for suffix in allowed_host_suffixes:
        if host == suffix or host.endswith(f".{suffix}"):
            return
    raise ValueError(
        f"FITS product {product_id} download host '{host}' is not an allowed archive host."
    )


def product_eligibility(product: SourceFitsProduct) -> ProductEligibility:
    """Return whether a product is a safe calibrated FITS render candidate."""

    normalized_format = normalize_file_format(
        product.file_format or product.file_name or product.source_record_id or product.download_url
    )
    calibration_level = product.calibration_level
    product_type = str(product.product_type or "").strip().lower()

    if normalized_format not in SUPPORTED_FITS_FORMATS:
        return ProductEligibility(
            product_id=product.id,
            eligible=False,
            reason="Only FITS or FITS.GZ image products are render candidates.",
            score=0.0,
            normalized_format=normalized_format,
            calibration_level=calibration_level,
        )
    if product_type in REJECTED_PRODUCT_TYPES:
        return ProductEligibility(
            product_id=product.id,
            eligible=False,
            reason=f"Product type '{product_type}' is not a calibrated image product.",
            score=0.0,
            normalized_format=normalized_format,
            calibration_level=calibration_level,
        )
    if _looks_uncalibrated(product):
        return ProductEligibility(
            product_id=product.id,
            eligible=False,
            reason="Raw or uncalibrated source products are not rendered by AstroLens.",
            score=0.0,
            normalized_format=normalized_format,
            calibration_level=calibration_level,
        )
    if calibration_level is None:
        return ProductEligibility(
            product_id=product.id,
            eligible=False,
            reason="Calibration level is required before rendering source FITS.",
            score=0.0,
            normalized_format=normalized_format,
            calibration_level=calibration_level,
        )
    if calibration_level < 2:
        return ProductEligibility(
            product_id=product.id,
            eligible=False,
            reason="Only calibrated products with calibration level >= 2 are supported.",
            score=0.0,
            normalized_format=normalized_format,
            calibration_level=calibration_level,
        )

    score = 0.55
    if normalized_format == "fits.gz":
        score += 0.05
    if product_type in {"science", "auxiliary"}:
        score += 0.1
    score += min((calibration_level - 2.0) * 0.1, 0.2)
    if _has_calibrated_filename_hint(product):
        score += 0.05
    if inferred_wavelength_nm(product) is not None:
        score += 0.05

    return ProductEligibility(
        product_id=product.id,
        eligible=True,
        reason="Calibrated FITS product is eligible for render planning.",
        score=min(score, 1.0),
        normalized_format=normalized_format,
        calibration_level=calibration_level,
    )


def select_eligible_fits_products(
    products: list[SourceFitsProduct],
    *,
    max_file_size_mb: float | None = None,
) -> list[SourceFitsProduct]:
    """Return eligible products sorted by render preference and stable tie breakers."""

    return sorted(
        [
            product
            for product in _dedupe_products(products)
            if product_eligibility(product).eligible
            and not _exceeds_max_file_size(product, max_file_size_mb)
        ],
        key=lambda product: (
            -product_eligibility(product).score,
            product.file_size_mb if product.file_size_mb is not None else 999_999.0,
            _sort_wavelength(product),
            product.id,
        ),
    )


def rgb_filter_mapping(products: list[SourceFitsProduct]) -> RgbMapping:
    """Map calibrated FITS filters to RGB channels deterministically."""

    if not products:
        raise ValueError("At least one FITS product is required for RGB mapping.")

    ordered = sorted(
        _dedupe_products(products),
        key=lambda product: (_sort_wavelength(product), product.id),
    )
    if len(ordered) == 1:
        only = ordered[0]
        note = "Single FITS product mapped to grayscale RGB channels."
        return RgbMapping(
            red=_channel("red", only),
            green=_channel("green", only),
            blue=_channel("blue", only),
            false_color=False,
            note=note,
        )
    if len(ordered) == 2:
        blue_product = ordered[0]
        red_product = ordered[-1]
        green_product = min(
            ordered,
            key=lambda product: (
                abs((_sort_wavelength(product) or 0.0) - _mapping_midpoint(ordered)),
                product.id,
            ),
        )
        note = (
            "Two FITS filters mapped by wavelength; green is synthesized during rendering "
            "from the short and long wavelength channels."
        )
        return RgbMapping(
            red=_channel("red", red_product),
            green=_channel("green", green_product),
            blue=_channel("blue", blue_product),
            false_color=True,
            note=note,
        )

    blue_product = ordered[0]
    green_product = ordered[len(ordered) // 2]
    red_product = ordered[-1]
    note = "FITS filters mapped by wavelength: shortest to blue, middle to green, longest to red."
    return RgbMapping(
        red=_channel("red", red_product),
        green=_channel("green", green_product),
        blue=_channel("blue", blue_product),
        false_color=True,
        note=note,
    )


def create_render_recipe(request: FitsRenderRequest) -> RenderRecipe:
    """Create a deterministic recipe for an eligible FITS render request."""

    eligible_products = select_eligible_fits_products(
        request.products,
        max_file_size_mb=request.max_source_file_mb,
    )
    if not eligible_products:
        reasons = [product_eligibility(product).reason for product in request.products]
        reasons.extend(
            _max_file_size_reason(product, request.max_source_file_mb)
            for product in request.products
            if _exceeds_max_file_size(product, request.max_source_file_mb)
        )
        raise ValueError(
            "No eligible calibrated FITS products found. "
            + " ".join(sorted(set(reasons)))
        )

    coherent_products = (
        eligible_products
        if request.preselected
        else select_coherent_render_products(eligible_products)
    )
    rgb_mapping = rgb_filter_mapping(coherent_products)
    channel_product_ids = {channel.product_id for channel in rgb_mapping.channels}
    source_products = sorted(
        [product for product in coherent_products if product.id in channel_product_ids],
        key=lambda product: product.id,
    )
    width, height = _dimensions(request)
    cache_key = stable_render_cache_key(
        request=request,
        source_products=source_products,
        rgb_mapping=rgb_mapping,
        width=width,
        height=height,
    )
    return RenderRecipe(
        cache_key=cache_key,
        asset_id=asset_id_for_cache_key(cache_key),
        source_products=source_products,
        rgb_mapping=rgb_mapping,
        output_format=request.output_format,
        width=width,
        height=height,
        stretch=request.stretch,
        false_color=rgb_mapping.false_color,
        alignment_mode="wcs_reproject" if len(source_products) > 1 else "single_channel",
        reference_product_id=rgb_mapping.green.product_id,
        caveats=[
            "AstroLens-rendered FITS images are generated from public archive data, "
            "not official press imagery.",
            "Colors may be mapped from wavelengths or filters rather than natural human vision.",
            "Processing choices such as stretch and channel mapping affect visual appearance.",
        ],
    )


def _fallback_single_channel_recipe(
    *,
    request: FitsRenderRequest,
    source_recipe: RenderRecipe,
    reason: str,
) -> RenderRecipe:
    product = source_recipe.source_products[0]
    mapping = rgb_filter_mapping([product])
    cache_key = stable_render_cache_key(
        request=request,
        source_products=[product],
        rgb_mapping=mapping,
        width=source_recipe.width,
        height=source_recipe.height,
    )
    return RenderRecipe(
        cache_key=cache_key,
        asset_id=asset_id_for_cache_key(cache_key),
        source_products=[product],
        rgb_mapping=mapping,
        output_format=source_recipe.output_format,
        width=source_recipe.width,
        height=source_recipe.height,
        stretch=source_recipe.stretch,
        false_color=False,
        alignment_mode="fallback_single_channel",
        reference_product_id=product.id,
        caveats=[
            *source_recipe.caveats,
            f"Downgraded to a single-channel render because RGB WCS alignment failed: {reason}",
        ],
    )


def stable_render_cache_key(
    *,
    request: FitsRenderRequest,
    source_products: list[SourceFitsProduct],
    rgb_mapping: RgbMapping,
    width: int,
    height: int,
) -> str:
    """Return a stable cache key for a render request and deterministic recipe inputs."""

    payload = {
        "version": RENDER_PIPELINE_VERSION,
        "object_id": request.object_id,
        "output_format": request.output_format,
        "width": width,
        "height": height,
        "stretch": request.stretch,
        "alignment": "wcs_reproject" if len(source_products) > 1 else "single_channel",
        "products": [
            _product_cache_payload(product)
            for product in sorted(source_products, key=lambda p: p.id)
        ],
        "channels": [
            {
                "channel": channel.channel,
                "product_id": channel.product_id,
                "wavelength_nm": channel.wavelength_nm,
            }
            for channel in rgb_mapping.channels
        ],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"{RENDER_PIPELINE_VERSION}:{digest}"


def asset_id_for_cache_key(cache_key: str) -> str:
    """Return the deterministic asset ID associated with a render cache key."""

    digest = cache_key.rsplit(":", maxsplit=1)[-1]
    return f"asset:fits-render:{digest[:24]}"


def normalize_file_format(value: str | None) -> str | None:
    """Normalize FITS-like suffixes from a format field, filename, or URL."""

    if not value:
        return None
    candidate = value.split("?", maxsplit=1)[0].strip().lower()
    if candidate in SUPPORTED_FITS_FORMATS:
        return candidate
    if candidate.endswith(".fits.gz"):
        return "fits.gz"
    if candidate.endswith(".fit.gz"):
        return "fit.gz"
    if candidate.endswith(".fits"):
        return "fits"
    if candidate.endswith(".fit"):
        return "fit"
    if "." in candidate:
        suffix = candidate.rsplit(".", maxsplit=1)[-1]
        return suffix or None
    return candidate or None


def inferred_wavelength_nm(product: SourceFitsProduct) -> float | None:
    """Infer an approximate filter wavelength in nanometers when available."""

    if product.wavelength_nm is not None:
        return product.wavelength_nm
    filter_name = _filter_name(product)
    if not filter_name:
        return None
    upper_filter = filter_name.upper().strip()
    if upper_filter in FILTER_WAVELENGTH_NM:
        return FILTER_WAVELENGTH_NM[upper_filter]

    match = re.search(r"F(\d{2,4})(?:[A-Z]+)?", upper_filter)
    if not match:
        return None
    number = float(match.group(1))
    instrument = str(product.instrument or product.raw_metadata.get("instrument") or "").upper()
    collection = str(
        product.raw_metadata.get("collection") or product.raw_metadata.get("obs_collection") or ""
    ).upper()
    jwst_instrument = any(
        token in instrument for token in ("MIRI", "NIRCAM", "NIRISS", "NIRSPEC")
    )
    if number < 300 or jwst_instrument or collection == "JWST":
        return number * 10.0
    return number


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _safe_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _metadata_string(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _dedupe_products(products: list[SourceFitsProduct]) -> list[SourceFitsProduct]:
    by_id: dict[str, SourceFitsProduct] = {}
    for product in products:
        by_id.setdefault(product.id, product)
    return list(by_id.values())


def _product_cache_payload(product: SourceFitsProduct) -> dict[str, object]:
    # Key on the stable archive record id when available: generated-cutout URLs
    # (e.g. SkyView tempspace) change per request and would defeat the cache.
    return {
        "id": product.id,
        "source_ref": product.source_record_id or product.download_url,
        "file_name": product.file_name,
        "file_format": normalize_file_format(product.file_format or product.file_name),
        "calibration_level": product.calibration_level,
        "file_size_mb": product.file_size_mb,
        "filter_name": _filter_name(product),
        "wavelength_nm": inferred_wavelength_nm(product),
        "source_record_id": product.source_record_id,
    }


def _dimensions(request: FitsRenderRequest) -> tuple[int, int]:
    default_width, default_height = OUTPUT_SIZES[request.size]
    return request.width or default_width, request.height or default_height


def _filter_name(product: SourceFitsProduct) -> str | None:
    if product.filter_name:
        return product.filter_name
    return _metadata_string(product.raw_metadata, "filters", "filter", "FILTER", "filter_name")


def _sort_wavelength(product: SourceFitsProduct) -> float:
    wavelength = inferred_wavelength_nm(product)
    return wavelength if wavelength is not None else 1_000_000.0


def _mapping_midpoint(products: list[SourceFitsProduct]) -> float:
    wavelengths = [_sort_wavelength(product) for product in products]
    return (wavelengths[0] + wavelengths[-1]) / 2.0


def _channel(channel: RgbChannelName, product: SourceFitsProduct) -> RenderChannel:
    return RenderChannel(
        channel=channel,
        product_id=product.id,
        filter_name=_filter_name(product),
        wavelength_nm=inferred_wavelength_nm(product),
    )


def _looks_uncalibrated(product: SourceFitsProduct) -> bool:
    haystack = " ".join(
        str(value)
        for value in (
            product.product_type,
            product.file_name,
            product.source_record_id,
            product.raw_metadata.get("productSubGroupDescription"),
            product.raw_metadata.get("description"),
        )
        if value
    ).lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", haystack) if token}
    return bool(tokens.intersection(UNCALIBRATED_TOKENS))


def _has_calibrated_filename_hint(product: SourceFitsProduct) -> bool:
    name = str(product.file_name or product.source_record_id or "").lower()
    return any(hint in name for hint in CALIBRATED_FILENAME_HINTS)


def select_coherent_render_products(
    products: list[SourceFitsProduct],
) -> list[SourceFitsProduct]:
    """Prefer products from one coherent visit/field before RGB channel mapping."""

    groups: dict[str, list[SourceFitsProduct]] = {}
    for product in products:
        groups.setdefault(_render_group_key(product), []).append(product)
    three_filter_groups = [
        group for group in groups.values() if _distinct_filter_count(group) >= 3
    ]
    if three_filter_groups:
        return sorted(three_filter_groups, key=_render_group_sort_key)[0]

    global_color_set = _best_cross_group_color_set(products)
    if len(global_color_set) >= 3:
        return global_color_set

    multi_filter_groups = [
        group for group in groups.values() if _distinct_filter_count(group) >= 2
    ]
    if not multi_filter_groups:
        return products[:1]
    return sorted(multi_filter_groups, key=_render_group_sort_key)[0]


def _render_group_sort_key(group: list[SourceFitsProduct]) -> tuple[float, float, float, str]:
    distinct_filters = _distinct_filter_count(group)
    total_size = sum(product.file_size_mb or 999.0 for product in group)
    average_score = sum(product_eligibility(product).score for product in group) / len(group)
    key = _render_group_key(group[0]) if group else ""
    return (-min(distinct_filters, 3), -average_score, total_size, key)


def _distinct_filter_count(products: list[SourceFitsProduct]) -> int:
    return len({_filter_key(product) for product in products})


def _best_cross_group_color_set(products: list[SourceFitsProduct]) -> list[SourceFitsProduct]:
    best_by_filter: dict[str, SourceFitsProduct] = {}
    for product in products:
        key = _filter_key(product)
        current = best_by_filter.get(key)
        if current is None or _product_color_candidate_key(product) < _product_color_candidate_key(
            current
        ):
            best_by_filter[key] = product

    candidates = sorted(
        best_by_filter.values(),
        key=lambda product: (_sort_wavelength(product), product.id),
    )
    if len(candidates) < 3:
        return []
    if len(candidates) == 3:
        return candidates

    best_triplet = min(combinations(candidates, 3), key=_color_triplet_sort_key)
    return sorted(best_triplet, key=lambda product: (_sort_wavelength(product), product.id))


def _product_color_candidate_key(product: SourceFitsProduct) -> tuple[float, float, str]:
    return (
        -product_eligibility(product).score,
        product.file_size_mb if product.file_size_mb is not None else 999_999.0,
        product.id,
    )


def _color_triplet_sort_key(
    products: tuple[SourceFitsProduct, SourceFitsProduct, SourceFitsProduct],
) -> tuple[float, float, float, float, str]:
    ordered = sorted(products, key=lambda product: (_sort_wavelength(product), product.id))
    low = _sort_wavelength(ordered[0])
    mid = _sort_wavelength(ordered[1])
    high = _sort_wavelength(ordered[2])
    midpoint = (low + high) / 2.0
    total_size = sum(product.file_size_mb or 999.0 for product in ordered)
    average_score = sum(product_eligibility(product).score for product in ordered) / len(ordered)
    ids = ",".join(product.id for product in ordered)
    return (-(high - low), abs(mid - midpoint), -average_score, total_size, ids)


def _filter_key(product: SourceFitsProduct) -> str:
    return (_filter_name(product) or product.id).strip().upper()


def _render_group_key(product: SourceFitsProduct) -> str:
    name = str(product.file_name or product.source_record_id or product.id).lower()
    normalized = re.sub(r"[\?#].*$", "", name)
    normalized = re.sub(r"\.(fits|fit)(\.gz)?$", "", normalized)
    normalized = re.sub(r"-(f\d{3,4}[a-z]?)", "-filter", normalized)
    normalized = re.sub(r"_(f\d{3,4}[a-z]?|total|detection)_", "_filter_", normalized)
    normalized = re.sub(r"_(i2d|drc|drz|flt|flc|cal|rate|crf)$", "", normalized)
    return normalized


def _exceeds_max_file_size(
    product: SourceFitsProduct,
    max_file_size_mb: float | None,
) -> bool:
    return (
        max_file_size_mb is not None
        and product.file_size_mb is not None
        and product.file_size_mb > max_file_size_mb
    )


def _recipe_uses_multiple_source_products(recipe: RenderRecipe) -> bool:
    return len({product.id for product in recipe.source_products}) > 1


def _max_file_size_reason(
    product: SourceFitsProduct,
    max_file_size_mb: float | None,
) -> str:
    if max_file_size_mb is None or product.file_size_mb is None:
        return "FITS product size is unknown."
    return (
        f"FITS product {product.id} is {product.file_size_mb:.1f} MB, "
        f"above the {max_file_size_mb:.1f} MB render limit."
    )


def _compose_rgb_image(
    recipe: RenderRecipe,
    payloads: dict[str, bytes],
    *,
    allow_reprojection: bool,
) -> Any:
    import numpy as np
    from PIL import Image

    channel_images = []
    unique_product_ids = {channel.product_id for channel in recipe.rgb_mapping.channels}
    loaded_images = {
        product_id: _fits_payload_to_image(payloads[product_id])
        for product_id in unique_product_ids
    }
    scale_ratio = pixel_scale_ratio(loaded_images.values())
    if scale_ratio is not None and scale_ratio > MAX_PIXEL_SCALE_RATIO:
        caveat = (
            "Source resolutions differ by about "
            f"{scale_ratio:.0f}x between channels; fine structure in this "
            "composite comes from the sharper channel(s)."
        )
        if caveat not in recipe.caveats:
            recipe.caveats.append(caveat)
    aligned_arrays, overlap_fraction = _aligned_channel_arrays(
        recipe,
        loaded_images,
        allow_reprojection=allow_reprojection,
    )
    recipe.overlap_fraction = overlap_fraction
    target_aspect = recipe.width / recipe.height
    combined = _combined_signal_array(
        [aligned_arrays[channel.product_id] for channel in recipe.rgb_mapping.channels]
    )
    crop_bounds = _content_crop_bounds(combined, target_aspect)
    cropped_by_product = {
        product_id: _crop_to_bounds(array, crop_bounds)
        for product_id, array in aligned_arrays.items()
    }
    normalized_by_product = {
        product_id: _normalize_fits_array(array, recipe.stretch)
        for product_id, array in cropped_by_product.items()
    }
    synthesize_green = _should_synthesize_green(recipe)
    for channel in recipe.rgb_mapping.channels:
        if channel.channel == "green" and synthesize_green:
            normalized = _synthetic_green_plane(recipe, normalized_by_product)
        else:
            normalized = normalized_by_product[channel.product_id]
        gray = Image.fromarray((np.clip(normalized, 0.0, 1.0) * 255.0).astype(np.uint8))
        gray = gray.resize((recipe.width, recipe.height), resample=Image.Resampling.LANCZOS)
        channel_images.append(np.asarray(gray, dtype=np.float32) / 255.0)
    rgb = np.dstack(channel_images)
    rgb = _repair_bright_channel_dropouts(rgb)
    if recipe.false_color:
        strength = 2.15 if len(unique_product_ids) == 2 else 1.55
        rgb = _boost_color_separation(rgb, strength=strength)
        rgb = _suppress_neon_channel_artifacts(rgb)
    return Image.fromarray((np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8))


def _should_synthesize_green(recipe: RenderRecipe) -> bool:
    product_ids = {channel.product_id for channel in recipe.rgb_mapping.channels}
    if len(product_ids) != 2:
        return False
    return recipe.rgb_mapping.green.product_id in {
        recipe.rgb_mapping.red.product_id,
        recipe.rgb_mapping.blue.product_id,
    }


def _synthetic_green_plane(recipe: RenderRecipe, normalized_by_product: dict[str, Any]) -> Any:
    import numpy as np

    red = normalized_by_product[recipe.rgb_mapping.red.product_id]
    blue = normalized_by_product[recipe.rgb_mapping.blue.product_id]
    blended = np.sqrt(np.clip(red, 0.0, 1.0) * np.clip(blue, 0.0, 1.0))
    return np.clip(blended * 0.72, 0.0, 1.0)


def _boost_color_separation(rgb: Any, *, strength: float) -> Any:
    import numpy as np

    luminance = np.mean(rgb, axis=2, keepdims=True)
    boosted = luminance + ((rgb - luminance) * strength)
    return np.clip(boosted, 0.0, 1.0)


def _repair_bright_channel_dropouts(rgb: Any) -> Any:
    import numpy as np

    maximum = np.max(rgb, axis=2)
    minimum = np.min(rgb, axis=2)
    dropout = (maximum > 0.62) & (minimum < 0.08) & ((maximum - minimum) > 0.55)
    if not bool(np.any(dropout)):
        return rgb
    repaired = np.array(rgb, copy=True)
    replacement = maximum * 0.85
    for index in range(3):
        channel = repaired[:, :, index]
        mask = dropout & (channel < 0.08)
        channel[mask] = replacement[mask]
        repaired[:, :, index] = channel
    return repaired


def _suppress_neon_channel_artifacts(rgb: Any) -> Any:
    import numpy as np

    red = rgb[:, :, 0]
    green = rgb[:, :, 1]
    blue = rgb[:, :, 2]
    maximum = np.max(rgb, axis=2)
    minimum = np.min(rgb, axis=2)
    chroma = maximum - minimum
    luminance = np.mean(rgb, axis=2)
    local_background = _box_mean_2d(luminance, radius=24)
    subject_region = local_background > 0.22
    saturated = (maximum > 0.38) & (chroma > 0.22) & subject_region
    green_spike = saturated & (green > red * 1.08) & (green > blue * 1.02)
    cyan_spike = saturated & (red < 0.38) & (green > 0.32) & (blue > 0.26)
    yellow_green_spike = saturated & (blue < 0.30) & (green > 0.38) & (red > 0.28)
    artifact_core = green_spike | cyan_spike | yellow_green_spike
    if not bool(np.any(artifact_core)):
        return rgb

    local_maximum = _local_maximum_2d(maximum, radius=12)
    near_artifact = _dilate_mask_2d(artifact_core, radius=8) & subject_region
    dark_dropout = (
        near_artifact
        & (maximum < 0.20)
        & (local_maximum > 0.50)
        & (local_background > 0.30)
    )
    artifact_halo = (
        _dilate_mask_2d(artifact_core | dark_dropout, radius=2)
        & subject_region
        & ((chroma > 0.08) | (maximum < 0.28))
    )
    artifact = artifact_core | dark_dropout | artifact_halo
    repaired = np.array(rgb, copy=True)
    neutral = np.maximum(luminance, local_maximum * 0.92)
    neutral = np.minimum(neutral, 1.0)
    neutral_rgb = np.repeat(neutral[:, :, None], 3, axis=2)
    repaired[artifact] = neutral_rgb[artifact]
    return repaired


def _dilate_mask_2d(mask: Any, *, radius: int) -> Any:
    import numpy as np

    padded = np.pad(mask, radius, mode="constant", constant_values=False)
    output = np.zeros_like(mask, dtype=bool)
    height, width = mask.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if (dx * dx) + (dy * dy) <= radius * radius:
                output |= padded[
                    radius + dy : radius + dy + height,
                    radius + dx : radius + dx + width,
                ]
    return output


def _local_maximum_2d(values: Any, *, radius: int) -> Any:
    import numpy as np

    padded = np.pad(values, radius, mode="edge")
    output = np.zeros_like(values)
    height, width = values.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if (dx * dx) + (dy * dy) <= radius * radius:
                output = np.maximum(
                    output,
                    padded[
                        radius + dy : radius + dy + height,
                        radius + dx : radius + dx + width,
                    ],
                )
    return output


def _box_mean_2d(values: Any, *, radius: int) -> Any:
    import numpy as np

    padded = np.pad(values, radius, mode="edge")
    integral = np.pad(padded, ((1, 0), (1, 0)), mode="constant").cumsum(0).cumsum(1)
    height, width = values.shape
    y0 = np.arange(height)
    y1 = y0 + (2 * radius) + 1
    x0 = np.arange(width)
    x1 = x0 + (2 * radius) + 1
    total = (
        integral[y1[:, None], x1[None, :]]
        - integral[y0[:, None], x1[None, :]]
        - integral[y1[:, None], x0[None, :]]
        + integral[y0[:, None], x0[None, :]]
    )
    return total / float(((2 * radius) + 1) ** 2)


MAX_PIXEL_SCALE_RATIO = 4.0


def pixel_scale_ratio(images: Any) -> float | None:
    """Return the max/min pixel-scale ratio across loaded images with WCS."""

    scales: list[float] = []
    for image in images:
        if image.wcs is None:
            continue
        try:
            from astropy.wcs.utils import proj_plane_pixel_scales

            plane_scales = proj_plane_pixel_scales(image.wcs)
            scale = float(abs(plane_scales[0]))
        except Exception:
            continue
        if scale > 0:
            scales.append(scale)
    if len(scales) < 2:
        return None
    return max(scales) / min(scales)


def _fits_payload_to_image(payload: bytes) -> LoadedFitsImage:
    import numpy as np
    from astropy.io import fits
    from astropy.wcs import WCS

    with fits.open(BytesIO(payload), memmap=False) as hdul:
        for hdu in hdul:
            image_hdu = cast(Any, hdu)
            if image_hdu.data is None:
                continue
            array = np.asarray(image_hdu.data, dtype=np.float32)
            while array.ndim > 2:
                array = array[0]
            if array.ndim == 2 and array.size:
                wcs = _celestial_wcs_for_header(WCS(image_hdu.header))
                return LoadedFitsImage(array=array, wcs=wcs)
    raise ValueError("No 2D image plane was found in the FITS payload.")


def _celestial_wcs_for_header(wcs: Any) -> Any | None:
    try:
        celestial = wcs.celestial
    except (AttributeError, ValueError):
        return None
    if not getattr(celestial, "has_celestial", False):
        return None
    return celestial


def _aligned_channel_arrays(
    recipe: RenderRecipe,
    loaded_images: dict[str, LoadedFitsImage],
    *,
    allow_reprojection: bool,
) -> tuple[dict[str, Any], float | None]:
    unique_product_ids = set(loaded_images)
    if len(unique_product_ids) == 1:
        product_id = next(iter(unique_product_ids))
        return {product_id: loaded_images[product_id].array}, None
    if not allow_reprojection:
        raise ValueError("WCS reprojection is required for multi-product FITS RGB composites.")

    reference_id = recipe.reference_product_id or recipe.rgb_mapping.green.product_id
    if reference_id not in loaded_images:
        reference_id = sorted(loaded_images)[0]
    reference = loaded_images[reference_id]
    if reference.wcs is None:
        raise ValueError(f"Reference FITS product {reference_id} has no usable celestial WCS.")

    import numpy as np
    from reproject import reproject_interp

    aligned: dict[str, Any] = {reference_id: reference.array}
    footprints = [np.isfinite(reference.array).astype(np.float32)]
    for product_id, image in loaded_images.items():
        if product_id == reference_id:
            continue
        if image.wcs is None:
            raise ValueError(f"FITS product {product_id} has no usable celestial WCS.")
        reprojected, footprint = reproject_interp(
            (image.array, image.wcs),
            reference.wcs,
            shape_out=reference.array.shape,
            order="bilinear",
            return_footprint=True,
        )
        reprojected = np.asarray(reprojected, dtype=np.float32)
        footprint = np.asarray(footprint, dtype=np.float32)
        reprojected[footprint <= 0] = np.nan
        aligned[product_id] = reprojected
        footprints.append(footprint > 0)

    common_footprint = np.logical_and.reduce([np.asarray(item) > 0 for item in footprints])
    overlap_fraction = float(np.mean(common_footprint))
    if overlap_fraction < 0.05:
        raise ValueError("FITS products do not have enough common WCS overlap for RGB.")
    for product_id, array in aligned.items():
        valid_fraction = float(np.mean(np.isfinite(array) & common_footprint))
        if valid_fraction < 0.05:
            raise ValueError(f"FITS product {product_id} is mostly blank after reprojection.")
    recipe.reference_product_id = reference_id
    recipe.overlap_fraction = overlap_fraction
    return aligned, overlap_fraction


def _content_crop_to_aspect(array: Any, target_aspect: float) -> Any:
    return _crop_to_bounds(array, _content_crop_bounds(array, target_aspect))


def _content_crop_bounds(array: Any, target_aspect: float) -> tuple[int, int, int, int]:
    import numpy as np

    height, width = array.shape
    if height <= 0 or width <= 0:
        raise ValueError("FITS image plane has invalid dimensions.")
    crop_width, crop_height = _beauty_crop_dimensions(width, height, target_aspect)
    center_x, center_y = _bright_signal_center(array)
    crop_width, crop_height = _centerable_crop_dimensions(
        width,
        height,
        target_aspect,
        center_x=center_x,
        center_y=center_y,
        crop_width=crop_width,
        crop_height=crop_height,
    )
    x0 = int(round(center_x - (crop_width / 2.0)))
    y0 = int(round(center_y - (crop_height / 2.0)))
    x0 = max(0, min(width - crop_width, x0))
    y0 = max(0, min(height - crop_height, y0))
    if np.size(array[y0 : y0 + crop_height, x0 : x0 + crop_width]) > 0:
        return y0, y0 + crop_height, x0, x0 + crop_width
    return _center_crop_bounds(array, target_aspect)


def _crop_to_bounds(array: Any, bounds: tuple[int, int, int, int]) -> Any:
    y0, y1, x0, x1 = bounds
    return array[y0:y1, x0:x1]


def _center_crop_to_aspect(array: Any, target_aspect: float) -> Any:
    return _crop_to_bounds(array, _center_crop_bounds(array, target_aspect))


def _center_crop_bounds(array: Any, target_aspect: float) -> tuple[int, int, int, int]:
    height, width = array.shape
    current_aspect = width / height
    if current_aspect > target_aspect:
        new_width = max(1, int(height * target_aspect))
        x0 = max(0, (width - new_width) // 2)
        return 0, height, x0, x0 + new_width
    if current_aspect < target_aspect:
        new_height = max(1, int(width / target_aspect))
        y0 = max(0, (height - new_height) // 2)
        return y0, y0 + new_height, 0, width
    return 0, height, 0, width


def _beauty_crop_dimensions(width: int, height: int, target_aspect: float) -> tuple[int, int]:
    current_aspect = width / height
    if current_aspect > target_aspect:
        max_height = height
        max_width = max(1, int(max_height * target_aspect))
    else:
        max_width = width
        max_height = max(1, int(max_width / target_aspect))
    crop_width = max(1, int(max_width * 0.72))
    crop_height = max(1, int(crop_width / target_aspect))
    if crop_height > max_height:
        crop_height = max(1, int(max_height * 0.72))
        crop_width = max(1, int(crop_height * target_aspect))
    return min(crop_width, width), min(crop_height, height)


def _centerable_crop_dimensions(
    width: int,
    height: int,
    target_aspect: float,
    *,
    center_x: float,
    center_y: float,
    crop_width: int,
    crop_height: int,
) -> tuple[int, int]:
    max_centered_width = max(1, int(2.0 * min(center_x, width - center_x)))
    max_centered_height = max(1, int(2.0 * min(center_y, height - center_y)))
    centered_width = min(crop_width, max_centered_width)
    centered_height = max(1, int(centered_width / target_aspect))
    if centered_height <= max_centered_height:
        return max(1, centered_width), centered_height
    centered_height = min(crop_height, max_centered_height)
    centered_width = max(1, int(centered_height * target_aspect))
    return centered_width, max(1, centered_height)


def _bright_signal_center(array: Any) -> tuple[float, float]:
    import numpy as np

    finite = np.isfinite(array)
    if not bool(np.any(finite)):
        height, width = array.shape
        return width / 2.0, height / 2.0
    values = array[finite]
    threshold = np.percentile(values, 99.6)
    signal = finite & (array >= threshold)
    if not bool(np.any(signal)):
        height, width = array.shape
        return width / 2.0, height / 2.0
    yy, xx = np.nonzero(signal)
    weights = np.asarray(array[signal], dtype=np.float64)
    weights = np.clip(weights - threshold, 0.0, None) + 1.0
    return float(np.average(xx, weights=weights)), float(np.average(yy, weights=weights))


def _combined_signal_array(arrays: list[Any]) -> Any:
    import numpy as np

    if not arrays:
        raise ValueError("No FITS arrays were available for RGB composition.")
    normalized = [_normalize_fits_array(array, "asinh") for array in arrays]
    return np.nanmean(np.stack(normalized), axis=0)


def _normalize_fits_array(array: Any, stretch: StretchMode) -> Any:
    import numpy as np

    finite = np.isfinite(array)
    if not bool(np.any(finite)):
        raise ValueError("FITS image plane has no finite pixels.")
    values = array[finite]
    low, high = np.percentile(values, [1.0, 99.7])
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low, high = np.min(values), np.max(values)
    if high <= low:
        return np.zeros_like(array, dtype=np.float32)
    scaled = np.clip((np.where(finite, array, low) - low) / (high - low), 0.0, 1.0)
    if stretch == "asinh":
        return np.arcsinh(scaled * 10.0) / np.arcsinh(10.0)
    if stretch == "log":
        return np.log1p(scaled * 100.0) / np.log1p(100.0)
    if stretch == "sqrt":
        return np.sqrt(scaled)
    return scaled


def _pillow_format(output_format: OutputFormat) -> str:
    if output_format in {"jpg", "jpeg"}:
        return "JPEG"
    return "PNG"


__all__ = [
    "FitsRenderer",
    "FitsRendererDependencies",
    "FitsRenderRequest",
    "FitsRenderResult",
    "ProductEligibility",
    "RenderChannel",
    "RenderRecipe",
    "RgbMapping",
    "SourceFitsProduct",
    "asset_id_for_cache_key",
    "create_render_recipe",
    "detect_fits_render_dependencies",
    "inferred_wavelength_nm",
    "normalize_file_format",
    "product_eligibility",
    "rgb_filter_mapping",
    "select_coherent_render_products",
    "select_eligible_fits_products",
    "stable_render_cache_key",
]
