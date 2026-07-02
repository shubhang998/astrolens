"""Limited live MAST connector for public HST/JWST image metadata."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from time import sleep
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import Field

from astrolens.connectors.error_mapping import connector_error_from_exception
from astrolens.core.enums import BandFamily, ErrorCode, SourceHealthStatus
from astrolens.core.errors import AstroLensError
from astrolens.core.models import AstroLensModel, SourceHealth
from astrolens.services.visual_quality import visual_quality_sort_key

MAST_INVOKE_URL = "https://mast.stsci.edu/api/v0/invoke"
MAST_DOWNLOAD_BASE = "https://mast.stsci.edu/api/v0.1/Download/file"
MAST_SOURCE_URL = "https://mast.stsci.edu/api/v0/"
MAST_PORTAL_URL = "https://mast.stsci.edu/portal/Mashup/Clients/Mast/Portal.html"

MAST_IMAGE_COLUMNS = ",".join(
    [
        "obsid",
        "obs_id",
        "obs_collection",
        "instrument_name",
        "filters",
        "target_name",
        "dataproduct_type",
        "dataRights",
        "t_exptime",
        "t_min",
        "t_max",
        "wave_region",
        "wavelength_region",
        "em_min",
        "em_max",
        "wave_min",
        "wave_max",
        "calib_level",
        "s_ra",
        "s_dec",
        "distance",
    ]
)

RANK_MODES = {"best_visual", "latest", "science_ready", "balanced"}


class MastObservationSummary(AstroLensModel):
    """Normalized subset of one MAST CAOM observation row."""

    obsid: str
    obs_id: str | None = None
    collection: str | None = None
    instrument: str | None = None
    filters: str | None = None
    target_name: str | None = None
    data_product_type: str | None = None
    data_rights: str | None = None
    calibration_level: str | None = None
    exposure_seconds: float | None = None
    observation_start: datetime | None = None
    wave_region: str | None = None
    band_family: BandFamily = BandFamily.UNKNOWN
    wavelength_min_nm: float | None = None
    wavelength_max_nm: float | None = None
    ra_deg: float | None = Field(default=None, ge=0.0, lt=360.0)
    dec_deg: float | None = Field(default=None, ge=-90.0, le=90.0)
    distance_degrees: float | None = Field(default=None, ge=0.0)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class MastProductSummary(AstroLensModel):
    """Normalized subset of one MAST product row."""

    product_filename: str | None = None
    product_type: str | None = None
    data_product_type: str | None = None
    calibration_level: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    data_uri: str | None = None
    download_url: str | None = None
    description: str | None = None
    file_format: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class MastObservationProducts(AstroLensModel):
    """Product manifest associated with one MAST observation."""

    obsid: str
    obs_id: str | None = None
    products: list[MastProductSummary] = Field(default_factory=list)
    error: str | None = None


class MastImageSearchResult(AstroLensModel):
    """Result of a limited live MAST image search."""

    source: str = "MAST CAOM"
    source_url: str = MAST_SOURCE_URL
    request: dict[str, Any] = Field(default_factory=dict)
    total_rows_in_cone: int = 0
    total_matching_images: int = 0
    returned: int = 0
    mission_filter: list[str] = Field(default_factory=list)
    observations: list[MastObservationSummary] = Field(default_factory=list)
    products_by_observation: list[MastObservationProducts] = Field(default_factory=list)
    filtered_server_side: bool = True
    fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)


def mast_download_url(data_uri: str | None) -> str | None:
    """Return the public MAST download URL for a MAST product URI."""

    if not data_uri:
        return None
    return f"{MAST_DOWNLOAD_BASE}?uri={urlencode({'': data_uri})[1:]}"


def _safe_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _mjd_to_datetime(value: object) -> datetime | None:
    days = _safe_float(value)
    if days is None:
        return None
    return datetime(1858, 11, 17, tzinfo=UTC) + timedelta(days=days)


def _wavelength_to_nm(value: object) -> float | None:
    number = _safe_float(value)
    if number is None:
        return None
    if 0 < number < 0.001:
        return number * 1_000_000_000.0
    return number


def band_from_mast_row(row: dict[str, Any]) -> BandFamily:
    """Infer an agent-facing wavelength family from MAST metadata."""

    wave_region = str(row.get("wave_region") or row.get("wavelength_region") or "").upper()
    instrument = str(row.get("instrument_name") or "").upper()
    collection = str(row.get("obs_collection") or "").upper()
    if "X-RAY" in wave_region or "XRAY" in wave_region:
        return BandFamily.XRAY
    if "GAMMA" in wave_region:
        return BandFamily.GAMMA
    if "RADIO" in wave_region:
        return BandFamily.RADIO
    if "MILLIMETER" in wave_region or "SUBMILLIMETER" in wave_region:
        return BandFamily.MILLIMETER
    if "INFRARED" in wave_region or collection == "JWST" or "NIRCAM" in instrument:
        return BandFamily.INFRARED
    if "UV" in wave_region or "ULTRAVIOLET" in wave_region:
        return BandFamily.ULTRAVIOLET
    if "OPTICAL" in wave_region or "VISIBLE" in wave_region or collection == "HST":
        return BandFamily.VISIBLE
    return BandFamily.UNKNOWN


def _file_format(filename: str | None, data_uri: str | None) -> str | None:
    candidate = filename or data_uri
    if not candidate or "." not in candidate:
        return None
    suffix = candidate.rsplit(".", maxsplit=1)[-1].lower()
    if suffix in {"gz", "bz2"} and "." in candidate.rsplit(".", maxsplit=1)[0]:
        return candidate.rsplit(".", maxsplit=2)[-2].lower() + f".{suffix}"
    return suffix


def _is_public_image_row(row: dict[str, Any], missions: list[str]) -> bool:
    collection = str(row.get("obs_collection") or "").upper()
    product_type = str(row.get("dataproduct_type") or "").lower()
    rights = str(row.get("dataRights") or "").upper()
    return collection in missions and product_type == "image" and rights in {"PUBLIC", ""}


def _is_science_like_row(row: dict[str, Any]) -> bool:
    target = str(row.get("target_name") or "").upper()
    filters = str(row.get("filters") or "").upper()
    calibration_targets = {
        "BIAS",
        "CCDFLAT",
        "DARK",
        "FLAT",
        "INTFLAT",
        "POST-SAA-DARK",
        "TUNGSTEN",
    }
    if target in calibration_targets or "DARK" in target or "FLAT" in target:
        return False
    return not (
        not filters
        or filters == "BLANK"
        or all(part == "CLEAR" for part in filters.split(";"))
    )


def _is_useful_product(product: MastProductSummary) -> bool:
    product_type = str(product.product_type or "").upper()
    calibration = _safe_float(product.calibration_level)
    if product_type == "PREVIEW":
        return True
    if product_type == "INFO":
        return False
    return product_type in {"SCIENCE", "AUXILIARY"} and calibration is not None and calibration >= 2


def _sort_observations(
    row: MastObservationSummary,
    *,
    rank_mode: str,
) -> tuple[float, float, float, int, str, str]:
    distance = row.distance_degrees if row.distance_degrees is not None else 999.0
    mission_rank = 0 if row.collection == "JWST" else 1
    timestamp = row.observation_start.timestamp() if row.observation_start else 0.0
    quality = _observation_visual_score(row)
    if rank_mode == "latest":
        return (-timestamp, -quality, distance, mission_rank, row.filters or "", row.obsid)
    if rank_mode == "science_ready":
        science = _science_readiness_score(row)
        return (-science, -quality, distance, mission_rank, row.filters or "", row.obsid)
    if rank_mode == "balanced":
        balanced = quality + (_recency_score(timestamp) * 3.0)
        return (-balanced, distance, -timestamp, mission_rank, row.filters or "", row.obsid)
    return (-quality, distance, -timestamp, mission_rank, row.filters or "", row.obsid)


def _observation_visual_score(row: MastObservationSummary) -> float:
    score = 0.0
    instrument = str(row.instrument or "").upper()
    filters = str(row.filters or "").upper()
    target = str(row.target_name or "").upper()
    if row.collection == "JWST":
        score += 7.0
    if row.collection == "HST":
        score += 4.0
    if any(token in instrument for token in ("NIRCAM", "WFC3", "ACS", "WFPC2")):
        score += 4.0
    if any(token in instrument for token in ("FOC", "NICMOS")):
        score -= 1.5
    if row.observation_start:
        score += _recency_score(row.observation_start.timestamp()) * 4.0
    if _filter_count(filters) >= 2:
        score += 1.0
    if any(name in target for name in ("M87", "NGC4486", "MESSIER-087", "VIRGO")):
        score += 1.0
    if row.exposure_seconds:
        score += min(row.exposure_seconds / 1200.0, 2.0)
    return score


def _science_readiness_score(row: MastObservationSummary) -> float:
    calibration = _safe_float(row.calibration_level) or 0.0
    score = calibration * 2.0
    if row.data_rights == "PUBLIC":
        score += 2.0
    if row.exposure_seconds:
        score += min(row.exposure_seconds / 1800.0, 2.0)
    score += _observation_visual_score(row) * 0.25
    return score


def _recency_score(timestamp: float) -> float:
    if timestamp <= 0:
        return 0.0
    # 1990-2030 normalized recency window for HST/JWST-era observations.
    start = datetime(1990, 1, 1, tzinfo=UTC).timestamp()
    end = datetime(2030, 1, 1, tzinfo=UTC).timestamp()
    return max(0.0, min(1.0, (timestamp - start) / (end - start)))


def _filter_count(filters: str) -> int:
    return len([part for part in filters.split(";") if part and part not in {"CLEAR", "BLANK"}])


def _sort_products(product: MastProductSummary) -> tuple[int, int, str]:
    score, tier, name = visual_quality_sort_key(product)
    if str(product.product_type or "").upper() == "PREVIEW" and product.file_format in {
        "gif",
        "jpeg",
        "jpg",
        "png",
    }:
        score += 100
    return (-score, -tier, name)


def _is_fits_product(product: MastProductSummary) -> bool:
    return product.file_format in {"fit", "fits", "fit.gz", "fits.gz"}


def _select_products_for_manifest(
    products: list[MastProductSummary],
    *,
    limit: int,
) -> list[MastProductSummary]:
    sorted_products = sorted(products, key=_sort_products)
    selected = sorted_products[:limit]
    if limit <= 0 or any(_is_fits_product(product) for product in selected):
        return selected
    fits_candidate = next(
        (product for product in sorted_products if _is_fits_product(product)),
        None,
    )
    if fits_candidate is None:
        return selected
    if len(selected) < limit:
        return [*selected, fits_candidate]
    return [*selected[:-1], fits_candidate]


def _dedupe_observations(
    observations: list[MastObservationSummary],
) -> list[MastObservationSummary]:
    unique: list[MastObservationSummary] = []
    seen: set[str] = set()
    for observation in observations:
        fallback_key = (
            f"{observation.collection}:{observation.obs_id}:"
            f"{observation.instrument}:{observation.filters}:"
            f"{observation.observation_start}:{observation.ra_deg}:{observation.dec_deg}"
        )
        key = observation.obs_id or observation.obsid or fallback_key
        if key in seen:
            continue
        seen.add(key)
        unique.append(observation)
    return unique


class MastConnector:
    """Read-only connector for a small, live MAST HST/JWST image slice."""

    name = "MAST"
    timeout_seconds = 35.0
    retry_count = 2

    async def healthcheck(self) -> SourceHealth:
        try:
            await self.search_public_images(ra_deg=187.70593077, dec_deg=12.39112325, limit=1)
        except Exception:  # pragma: no cover - defensive health boundary
            return SourceHealth(
                name=self.name,
                status=SourceHealthStatus.UNAVAILABLE,
                last_error_at=datetime.now(UTC),
            )
        return SourceHealth(
            name=self.name,
            status=SourceHealthStatus.OK,
            last_success_at=datetime.now(UTC),
            latency_ms=None,
        )

    async def search_public_images(
        self,
        *,
        ra_deg: float,
        dec_deg: float,
        radius_deg: float = 0.03,
        missions: tuple[str, ...] = ("HST", "JWST"),
        limit: int = 6,
        product_limit: int = 8,
        product_observation_limit: int = 3,
        rank_mode: str = "best_visual",
    ) -> MastImageSearchResult:
        """Search public HST/JWST image observations and selected products."""

        normalized_missions = [mission.strip().upper() for mission in missions if mission.strip()]
        normalized_rank_mode = rank_mode if rank_mode in RANK_MODES else "best_visual"
        query_result = await self._search_rows(
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            radius_deg=radius_deg,
            missions=normalized_missions,
        )
        return await self._assemble_image_search_result(
            query_result,
            normalized_missions=normalized_missions,
            rank_mode=normalized_rank_mode,
            limit=limit,
            product_limit=product_limit,
            product_observation_limit=product_observation_limit,
        )

    async def search_public_images_by_target_name(
        self,
        target_name: str,
        *,
        missions: tuple[str, ...] = ("HST", "JWST"),
        limit: int = 6,
        product_limit: int = 8,
        product_observation_limit: int = 3,
        rank_mode: str = "best_visual",
    ) -> MastImageSearchResult:
        """Search public images by archive target name (for moving targets).

        Solar-system bodies move across the sky, so fixed-coordinate cone
        searches can never find them; CAOM target names (upper-cased) can.
        """

        normalized_missions = [mission.strip().upper() for mission in missions if mission.strip()]
        normalized_rank_mode = rank_mode if rank_mode in RANK_MODES else "best_visual"
        normalized_target = target_name.strip().upper()
        request = {
            "service": "Mast.Caom.Filtered",
            "params": {
                "columns": MAST_IMAGE_COLUMNS,
                "filters": [
                    {"paramName": "target_name", "values": [normalized_target]},
                    {"paramName": "obs_collection", "values": normalized_missions},
                    {"paramName": "dataproduct_type", "values": ["image"]},
                    {"paramName": "dataRights", "values": ["PUBLIC"]},
                ],
            },
            "format": "json",
            "pagesize": 500,
            "removenullcolumns": True,
            "timeout": 30,
        }
        response = await self.invoke(request)
        response_data = response.get("data")
        rows = cast(list[dict[str, Any]], response_data) if isinstance(response_data, list) else []
        query_result: dict[str, Any] = {
            "request": request,
            "rows": rows,
            "total_rows_in_cone": len(rows),
            "filtered_server_side": True,
            "fallback_used": False,
            "warnings": [],
        }
        return await self._assemble_image_search_result(
            query_result,
            normalized_missions=normalized_missions,
            rank_mode=normalized_rank_mode,
            limit=limit,
            product_limit=product_limit,
            product_observation_limit=product_observation_limit,
        )

    async def _assemble_image_search_result(
        self,
        query_result: dict[str, Any],
        *,
        normalized_missions: list[str],
        rank_mode: str,
        limit: int,
        product_limit: int,
        product_observation_limit: int,
    ) -> MastImageSearchResult:
        normalized_rank_mode = rank_mode
        rows = query_result["rows"]
        science_rows = [row for row in rows if _is_science_like_row(row)]
        selected_rows = science_rows or rows
        ranked_observations = sorted(
            [self.parse_observation_row(row) for row in selected_rows],
            key=lambda row: _sort_observations(row, rank_mode=normalized_rank_mode),
        )
        unique_observations = _dedupe_observations(ranked_observations)
        observations = unique_observations[:limit]

        warnings = list(query_result["warnings"])
        product_sets: list[MastObservationProducts] = []
        if product_limit > 0:
            semaphore = asyncio.Semaphore(4)
            product_results = await asyncio.gather(
                *[
                    self._product_set_for_observation(
                        observation,
                        product_limit=product_limit,
                        semaphore=semaphore,
                    )
                    for observation in observations[:product_observation_limit]
                ]
            )
            for product_set, warning in product_results:
                product_sets.append(product_set)
                if warning:
                    warnings.append(warning)

        return MastImageSearchResult(
            request=query_result["request"],
            total_rows_in_cone=int(query_result["total_rows_in_cone"]),
            total_matching_images=len(unique_observations),
            returned=len(observations),
            mission_filter=normalized_missions,
            observations=observations,
            products_by_observation=product_sets,
            filtered_server_side=bool(query_result["filtered_server_side"]),
            fallback_used=bool(query_result["fallback_used"]),
            warnings=warnings,
        )

    async def list_products(self, obsid: str, *, limit: int = 8) -> list[MastProductSummary]:
        request = {
            "service": "Mast.Caom.Products",
            "params": {"obsid": obsid},
            "format": "json",
            "pagesize": 80,
            "removenullcolumns": True,
            "timeout": 30,
        }
        response = await self.invoke(request)
        response_data = response.get("data")
        rows = cast(list[dict[str, Any]], response_data) if isinstance(response_data, list) else []
        products = [self.parse_product_row(row) for row in rows]
        useful = [product for product in products if _is_useful_product(product)]
        return _select_products_for_manifest(useful, limit=limit)

    async def _product_set_for_observation(
        self,
        observation: MastObservationSummary,
        *,
        product_limit: int,
        semaphore: asyncio.Semaphore,
    ) -> tuple[MastObservationProducts, str | None]:
        async with semaphore:
            try:
                products = await self.list_products(observation.obsid, limit=product_limit)
            except AstroLensError as exc:
                message = (
                    f"MAST product lookup failed for obsid {observation.obsid}; "
                    "returned observation metadata without products."
                )
                return (
                    MastObservationProducts(
                        obsid=observation.obsid,
                        obs_id=observation.obs_id,
                        products=[],
                        error=exc.message,
                    ),
                    message,
                )
        return (
            MastObservationProducts(
                obsid=observation.obsid,
                obs_id=observation.obs_id,
                products=products,
            ),
            None,
        )

    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke a MAST API payload in a worker thread."""

        return await asyncio.to_thread(self._invoke_sync, payload)

    def _invoke_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = urlencode({"request": json.dumps(payload)}).encode("utf-8")
        request = Request(
            MAST_INVOKE_URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "AstroLens/0.1 limited-live-mast-ingestion",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read()
                decoded = json.loads(raw.decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise AstroLensError(
                        ErrorCode.SOURCE_UNAVAILABLE,
                        "MAST returned a non-object JSON payload.",
                        retryable=True,
                        details={"source": self.name},
                    )
                status = decoded.get("status")
                if status and status != "COMPLETE":
                    raise AstroLensError(
                        ErrorCode.SOURCE_UNAVAILABLE,
                        f"MAST query did not complete: {status} {decoded.get('msg') or ''}".strip(),
                        retryable=True,
                        details={"source": self.name, "status": status},
                    )
                return decoded
            except json.JSONDecodeError as exc:
                last_error = exc
                if attempt < self.retry_count:
                    sleep(0.6 * (2**attempt))
                    continue
                raise AstroLensError(
                    ErrorCode.SOURCE_UNAVAILABLE,
                    "MAST returned malformed JSON.",
                    retryable=True,
                    details={"source": self.name, "error_type": type(exc).__name__},
                ) from exc
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt < self.retry_count:
                    sleep(0.6 * (2**attempt))
                    continue
                raise connector_error_from_exception(
                    exc,
                    source=self.name,
                    message="MAST live archive query failed.",
                ) from exc
            except AstroLensError:
                raise
        raise AstroLensError(
            ErrorCode.SOURCE_UNAVAILABLE,
            "MAST live archive query failed.",
            retryable=True,
            details={"source": self.name, "error": str(last_error)},
        )

    async def _search_rows(
        self,
        *,
        ra_deg: float,
        dec_deg: float,
        radius_deg: float,
        missions: list[str],
    ) -> dict[str, Any]:
        request = {
            "service": "Mast.Caom.Filtered.Position",
            "params": {
                "position": f"{ra_deg}, {dec_deg}, {radius_deg}",
                "columns": MAST_IMAGE_COLUMNS,
                "filters": [
                    {"paramName": "obs_collection", "values": missions},
                    {"paramName": "dataproduct_type", "values": ["image"]},
                    {"paramName": "dataRights", "values": ["PUBLIC"]},
                ],
            },
            "format": "json",
            "pagesize": 500,
            "removenullcolumns": True,
            "timeout": 30,
        }
        try:
            response = await self.invoke(request)
            response_data = response.get("data")
            rows = (
                cast(list[dict[str, Any]], response_data)
                if isinstance(response_data, list)
                else []
            )
            return {
                "request": request,
                "rows": rows,
                "total_rows_in_cone": len(rows),
                "filtered_server_side": True,
                "fallback_used": False,
                "warnings": [],
            }
        except AstroLensError as primary_error:
            fallback_radius = min(radius_deg, 0.01)
            fallback_request = {
                "service": "Mast.Caom.Cone",
                "params": {"ra": ra_deg, "dec": dec_deg, "radius": fallback_radius},
                "format": "json",
                "pagesize": 1500,
                "removenullcolumns": True,
                "timeout": 30,
            }
            response = await self.invoke(fallback_request)
            response_data = response.get("data")
            raw_rows = (
                cast(list[dict[str, Any]], response_data)
                if isinstance(response_data, list)
                else []
            )
            rows = [row for row in raw_rows if _is_public_image_row(row, missions)]
            return {
                "request": fallback_request,
                "rows": rows,
                "total_rows_in_cone": len(raw_rows),
                "filtered_server_side": False,
                "fallback_used": True,
                "warnings": [
                    "MAST server-side filtered image query failed; retried with a smaller "
                    f"{fallback_radius} degree cone and client-side filtering.",
                    f"Primary MAST error: {primary_error.message}",
                ],
            }

    def parse_observation_row(self, row: dict[str, Any]) -> MastObservationSummary:
        wave_min = row.get("em_min", row.get("wave_min"))
        wave_max = row.get("em_max", row.get("wave_max"))
        return MastObservationSummary(
            obsid=str(row.get("obsid") or row.get("obs_id") or ""),
            obs_id=str(row["obs_id"]) if row.get("obs_id") is not None else None,
            collection=str(row["obs_collection"]) if row.get("obs_collection") else None,
            instrument=str(row["instrument_name"]) if row.get("instrument_name") else None,
            filters=str(row["filters"]) if row.get("filters") else None,
            target_name=str(row["target_name"]) if row.get("target_name") else None,
            data_product_type=(
                str(row["dataproduct_type"]) if row.get("dataproduct_type") else None
            ),
            data_rights=str(row["dataRights"]) if row.get("dataRights") else None,
            calibration_level=(
                str(row["calib_level"]) if row.get("calib_level") is not None else None
            ),
            exposure_seconds=_safe_float(row.get("t_exptime")),
            observation_start=_mjd_to_datetime(row.get("t_min")),
            wave_region=(
                str(row.get("wave_region") or row.get("wavelength_region"))
                if row.get("wave_region") or row.get("wavelength_region")
                else None
            ),
            band_family=band_from_mast_row(row),
            wavelength_min_nm=_wavelength_to_nm(wave_min),
            wavelength_max_nm=_wavelength_to_nm(wave_max),
            ra_deg=_safe_float(row.get("s_ra")),
            dec_deg=_safe_float(row.get("s_dec")),
            distance_degrees=_safe_float(row.get("distance")),
            raw_metadata=dict(row),
        )

    def parse_product_row(self, row: dict[str, Any]) -> MastProductSummary:
        filename = str(row["productFilename"]) if row.get("productFilename") else None
        data_uri = str(row["dataURI"]) if row.get("dataURI") else None
        return MastProductSummary(
            product_filename=filename,
            product_type=str(row["productType"]) if row.get("productType") else None,
            data_product_type=str(row["dataproduct_type"]) if row.get("dataproduct_type") else None,
            calibration_level=(
                str(row["calib_level"]) if row.get("calib_level") is not None else None
            ),
            size_bytes=_safe_int(row.get("size")),
            data_uri=data_uri,
            download_url=mast_download_url(data_uri),
            description=str(row["description"]) if row.get("description") else None,
            file_format=_file_format(filename, data_uri),
            raw_metadata=dict(row),
        )


mast_connector = MastConnector()
