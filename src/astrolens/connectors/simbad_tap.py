"""Limited live SIMBAD TAP connector for measurements and category search.

Queries are pinned to the stable ``basic``/``ident``/``otypes``/``allfluxes``
tables and always target the fixed SIMBAD TAP host, so this connector never
fetches caller-provided URLs. Identity is handed off from the CDS Sesame
resolver: ``fetch_measurements`` expects Sesame's canonical object name
because SIMBAD ``ident.id`` matching is string-exact.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import Field

from astrolens.connectors.error_mapping import connector_error_from_exception
from astrolens.core.enums import ErrorCode, SourceHealthStatus
from astrolens.core.errors import AstroLensError
from astrolens.core.models import AstroLensModel, Citation, SourceHealth

SIMBAD_TAP_SYNC_URL = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
SIMBAD_TAP_DOCS_URL = "https://simbad.cds.unistra.fr/simbad/sim-tap"

# Curated, bounded category vocabulary mapped to SIMBAD otype codes. The
# ``otypes`` table is hierarchical, so e.g. 'G' also matches Seyfert galaxies.
CATEGORY_OTYPES: dict[str, str] = {
    "agn": "AGN",
    "black-hole": "BH",
    "galaxy": "G",
    "galaxy-cluster": "ClG",
    "globular-cluster": "GlC",
    "nebula": "GNe",
    "open-cluster": "OpC",
    "planetary-nebula": "PN",
    "pulsar": "Psr",
    "quasar": "QSO",
    "star": "*",
    "star-forming-region": "HII",
    "supernova-remnant": "SNR",
    "variable-star": "V*",
}

MAX_CATEGORY_RESULTS = 20
DEFAULT_SAMPLE_MODULUS = 37

SIMBAD_TAP_CITATION = Citation(
    id="citation:simbad:tap",
    title="SIMBAD astronomical database (CDS TAP service)",
    source="SIMBAD",
    url=SIMBAD_TAP_DOCS_URL,
    credit_text="SIMBAD database, operated at CDS, Strasbourg, France",
)


class SimbadMeasurements(AstroLensModel):
    """Catalog measurements for one object, with per-measurement bibcodes."""

    main_id: str
    otype: str | None = None
    ra_deg: float | None = None
    dec_deg: float | None = None
    parallax_mas: float | None = None
    parallax_err_mas: float | None = None
    parallax_bibcode: str | None = None
    redshift: float | None = None
    radial_velocity_km_s: float | None = None
    rvz_type: str | None = None
    rvz_bibcode: str | None = None
    morph_type: str | None = None
    morph_bibcode: str | None = None
    angular_major_arcmin: float | None = None
    angular_minor_arcmin: float | None = None
    galdim_bibcode: str | None = None
    spectral_type: str | None = None
    sp_bibcode: str | None = None
    v_mag: float | None = None
    b_mag: float | None = None
    k_mag: float | None = None
    reference_count: int | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class SimbadCategoryHit(AstroLensModel):
    """One object returned by a category/region search."""

    main_id: str
    otype: str
    ra_deg: float
    dec_deg: float
    v_mag: float | None = None
    redshift: float | None = None
    angular_major_arcmin: float | None = None


class SimbadCategorySearchResult(AstroLensModel):
    """Category search hits plus the exact ADQL used, for provenance."""

    query_adql: str
    hits: list[SimbadCategoryHit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def escape_adql_string(value: str) -> str:
    """Escape a string literal for ADQL; reject control characters outright."""

    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise AstroLensError(
            ErrorCode.VALIDATION_ERROR,
            "Object identifiers must not contain control characters.",
            retryable=False,
            details={"value_repr": repr(value)},
        )
    return value.replace("'", "''")


def measurements_adql(main_id: str) -> str:
    """Build the exact-identifier measurements query."""

    escaped = escape_adql_string(main_id)
    return (
        "SELECT b.main_id, b.otype, b.ra, b.dec, "
        "b.plx_value, b.plx_err, b.plx_bibcode, "
        "b.rvz_redshift, b.rvz_radvel, b.rvz_type, b.rvz_bibcode, "
        "b.morph_type, b.morph_bibcode, "
        "b.galdim_majaxis, b.galdim_minaxis, b.galdim_bibcode, "
        "b.sp_type, b.sp_bibcode, b.nbref, "
        "f.V, f.B, f.K "
        "FROM basic AS b "
        "JOIN ident AS i ON i.oidref = b.oid "
        "LEFT JOIN allfluxes AS f ON f.oidref = b.oid "
        f"WHERE i.id = '{escaped}'"
    )


def category_adql(
    otype: str,
    *,
    cone: tuple[float, float, float] | None = None,
    magnitude_limit: float | None = None,
    limit: int = 10,
    sample_modulus: int | None = None,
    sample_residue: int | None = None,
) -> str:
    """Build the category/region search query."""

    escaped_otype = escape_adql_string(otype)
    bounded_limit = max(1, min(int(limit), MAX_CATEGORY_RESULTS))
    clauses = [f"ot.otype = '{escaped_otype}'"]
    if cone is not None:
        ra_deg, dec_deg, radius_deg = cone
        clauses.append(
            "CONTAINS(POINT('ICRS', b.ra, b.dec), "
            f"CIRCLE('ICRS', {ra_deg:.6f}, {dec_deg:.6f}, {radius_deg:.4f})) = 1"
        )
    if magnitude_limit is not None:
        clauses.append(f"f.V <= {float(magnitude_limit):.2f}")
    if sample_modulus is not None and sample_residue is not None:
        clauses.append(f"MOD(b.oid, {int(sample_modulus)}) = {int(sample_residue)}")
    # SIMBAD's ADQL parser rejects table-qualified columns in ORDER BY; both
    # oid and nbref are unambiguous (only `basic` carries them in this join).
    order = "ORDER BY oid" if sample_modulus is not None else "ORDER BY nbref DESC"
    return (
        f"SELECT TOP {bounded_limit} b.main_id, b.otype, b.ra, b.dec, "
        "b.rvz_redshift, b.galdim_majaxis, f.V "
        "FROM basic AS b "
        "JOIN otypes AS ot ON ot.oidref = b.oid "
        "LEFT JOIN allfluxes AS f ON f.oidref = b.oid "
        f"WHERE {' AND '.join(clauses)} "
        f"{order}"
    )


def otype_for_category(category: str) -> str:
    """Map a curated category name to a SIMBAD otype, teaching on miss."""

    normalized = category.strip().lower().replace("_", "-").replace(" ", "-")
    otype = CATEGORY_OTYPES.get(normalized)
    if otype is None:
        raise AstroLensError(
            ErrorCode.VALIDATION_ERROR,
            f"Unsupported object category '{category}'.",
            retryable=False,
            details={
                "category": category,
                "supported_categories": sorted(CATEGORY_OTYPES),
            },
        )
    return otype


class SimbadTapConnector:
    """Live, read-only SIMBAD TAP client for measurements and category search."""

    name = "SIMBAD TAP"

    def __init__(self, client: Any | None = None, *, timeout_seconds: float = 30.0) -> None:
        self.client = client
        self.timeout_seconds = timeout_seconds

    async def healthcheck(self) -> SourceHealth:
        started = time.monotonic()
        try:
            await asyncio.to_thread(self._query_sync, "SELECT TOP 1 b.oid FROM basic AS b")
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
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    async def fetch_measurements(self, main_id: str) -> SimbadMeasurements | None:
        """Return catalog measurements for one canonical identifier.

        ``main_id`` should be the canonical name Sesame returned (e.g. "M  87");
        one whitespace-collapsed retry covers minor spacing drift.
        """

        rows = await self._rows(measurements_adql(main_id))
        if not rows:
            collapsed = " ".join(main_id.split())
            if collapsed != main_id:
                rows = await self._rows(measurements_adql(collapsed))
        if not rows:
            return None
        return _measurements_from_row(rows[0])

    async def search_category(
        self,
        *,
        otype: str,
        cone: tuple[float, float, float] | None = None,
        magnitude_limit: float | None = None,
        limit: int = 10,
        random_sample: bool = False,
        sample_seed: int | None = None,
    ) -> SimbadCategorySearchResult:
        """Return objects of one category, optionally cone-bounded or sampled."""

        warnings: list[str] = []
        if not random_sample:
            adql = category_adql(
                otype,
                cone=cone,
                magnitude_limit=magnitude_limit,
                limit=limit,
            )
            rows = await self._rows(adql)
            return SimbadCategorySearchResult(
                query_adql=adql,
                hits=[hit for hit in map(_category_hit_from_row, rows) if hit],
                warnings=warnings,
            )

        rng = random.Random(sample_seed)
        modulus = DEFAULT_SAMPLE_MODULUS
        adql = ""
        rows: list[dict[str, Any]] = []
        while modulus >= 1:
            residue = rng.randrange(modulus) if modulus > 1 else 0
            adql = category_adql(
                otype,
                cone=cone,
                magnitude_limit=magnitude_limit,
                limit=limit,
                sample_modulus=modulus,
                sample_residue=residue,
            )
            rows = await self._rows(adql)
            if len(rows) >= min(limit, MAX_CATEGORY_RESULTS) or modulus == 1:
                break
            modulus //= 2
        if modulus == 1:
            warnings.append(
                "Random sampling fell back to an unsampled query; results are "
                "ordered by reference count rather than randomized."
            )
        return SimbadCategorySearchResult(
            query_adql=adql,
            hits=[hit for hit in map(_category_hit_from_row, rows) if hit],
            warnings=warnings,
        )

    async def get_citation(self, source_record_id: str) -> Citation:
        del source_record_id
        return SIMBAD_TAP_CITATION

    async def _rows(self, adql: str) -> list[dict[str, Any]]:
        payload = await asyncio.to_thread(self._query_sync, adql)
        return _rows_by_column_name(payload, source=self.name, adql=adql)

    def _query_sync(self, adql: str) -> dict[str, Any]:
        if self.client is not None:
            return self.client.query(adql)
        body = urlencode(
            {
                "request": "doQuery",
                "lang": "adql",
                "format": "json",
                "query": adql,
            }
        ).encode("ascii")
        request = Request(
            SIMBAD_TAP_SYNC_URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "AstroLens/0.1 limited-live-simbad-tap",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(8_000_000)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise connector_error_from_exception(
                exc,
                source=self.name,
                message="SIMBAD TAP query failed.",
            ) from exc
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AstroLensError(
                ErrorCode.SOURCE_UNAVAILABLE,
                "SIMBAD TAP returned malformed JSON.",
                retryable=True,
                details={"source": self.name, "error_type": type(exc).__name__},
            ) from exc
        if not isinstance(decoded, dict):
            raise AstroLensError(
                ErrorCode.SOURCE_UNAVAILABLE,
                "SIMBAD TAP returned a non-object JSON payload.",
                retryable=True,
                details={"source": self.name},
            )
        return decoded


def _rows_by_column_name(
    payload: dict[str, Any],
    *,
    source: str,
    adql: str,
) -> list[dict[str, Any]]:
    """Zip TAP metadata column names with data rows; never trust positions."""

    metadata = payload.get("metadata")
    data = payload.get("data")
    if not isinstance(metadata, list) or not isinstance(data, list):
        raise AstroLensError(
            ErrorCode.SOURCE_UNAVAILABLE,
            "SIMBAD TAP response is missing metadata or data sections.",
            retryable=True,
            details={"source": source, "adql": adql},
        )
    columns = [str(column.get("name", "")).lower() for column in metadata]
    rows: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, list) or len(row) != len(columns):
            continue
        rows.append(dict(zip(columns, row, strict=True)))
    return rows


def _measurements_from_row(row: dict[str, Any]) -> SimbadMeasurements:
    return SimbadMeasurements(
        main_id=str(row.get("main_id") or "").strip(),
        otype=_optional_str(row.get("otype")),
        ra_deg=_optional_float(row.get("ra")),
        dec_deg=_optional_float(row.get("dec")),
        parallax_mas=_optional_float(row.get("plx_value")),
        parallax_err_mas=_optional_float(row.get("plx_err")),
        parallax_bibcode=_optional_str(row.get("plx_bibcode")),
        redshift=_optional_float(row.get("rvz_redshift")),
        radial_velocity_km_s=_optional_float(row.get("rvz_radvel")),
        rvz_type=_optional_str(row.get("rvz_type")),
        rvz_bibcode=_optional_str(row.get("rvz_bibcode")),
        morph_type=_optional_str(row.get("morph_type")),
        morph_bibcode=_optional_str(row.get("morph_bibcode")),
        angular_major_arcmin=_optional_float(row.get("galdim_majaxis")),
        angular_minor_arcmin=_optional_float(row.get("galdim_minaxis")),
        galdim_bibcode=_optional_str(row.get("galdim_bibcode")),
        spectral_type=_optional_str(row.get("sp_type")),
        sp_bibcode=_optional_str(row.get("sp_bibcode")),
        v_mag=_optional_float(row.get("v")),
        b_mag=_optional_float(row.get("b")),
        k_mag=_optional_float(row.get("k")),
        reference_count=_optional_int(row.get("nbref")),
        raw_metadata={key: value for key, value in row.items() if value is not None},
    )


def _category_hit_from_row(row: dict[str, Any]) -> SimbadCategoryHit | None:
    main_id = str(row.get("main_id") or "").strip()
    ra_deg = _optional_float(row.get("ra"))
    dec_deg = _optional_float(row.get("dec"))
    if not main_id or ra_deg is None or dec_deg is None:
        return None
    return SimbadCategoryHit(
        main_id=main_id,
        otype=str(row.get("otype") or "unknown").strip(),
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        v_mag=_optional_float(row.get("v")),
        redshift=_optional_float(row.get("rvz_redshift")),
        angular_major_arcmin=_optional_float(row.get("galdim_majaxis")),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    parsed = _optional_float(value)
    return int(parsed) if parsed is not None else None


simbad_tap_connector = SimbadTapConnector()
