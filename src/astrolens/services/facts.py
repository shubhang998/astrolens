"""Compile catalog measurements into layered, cited, deterministic facts.

Every numeric fact here is traceable: ``source_fields`` names the SIMBAD
catalog fields it came from and ``derivation`` names the deterministic
function applied. Nothing in this module is free-form or model-generated.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from pydantic import Field

from astrolens.connectors.simbad_tap import (
    SIMBAD_TAP_CITATION,
    SimbadMeasurements,
    SimbadTapConnector,
    simbad_tap_connector,
)
from astrolens.core.errors import AstroLensError
from astrolens.core.models import (
    AstroLensModel,
    CelestialObject,
    Citation,
    Fact,
    WarningMessage,
)
from astrolens.services.repository import normalize_query

PC_TO_LIGHT_YEARS = 3.26156
MPC_TO_LIGHT_YEARS = 3.26156e6
NAKED_EYE_LIMIT_V_MAG = 6.0
FULL_MOON_ARCMIN = 31.0
MILKY_WAY_DIAMETER_LY = 100_000.0
EARTH_AGE_GYR = 4.54
PARALLAX_MAX_RELATIVE_ERROR = 0.2
MIN_COSMOLOGICAL_REDSHIFT = 0.003

OTYPE_LABELS = {
    "AGN": "active galactic nucleus",
    "BH": "black hole",
    "ClG": "galaxy cluster",
    "E": "elliptical galaxy",
    "G": "galaxy",
    "GlC": "globular cluster",
    "GNe": "nebula",
    "HII": "star-forming (HII) region",
    "OpC": "open star cluster",
    "PN": "planetary nebula",
    "Psr": "pulsar",
    "QSO": "quasar",
    "SNR": "supernova remnant",
    "Sy1": "Seyfert 1 galaxy",
    "Sy2": "Seyfert 2 galaxy",
    "V*": "variable star",
    "dS*": "delta Scuti variable star",
    "*": "star",
}


class ObjectFactsResult(AstroLensModel):
    """Compiled facts plus their citations and any compilation warnings."""

    facts: list[Fact] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[WarningMessage] = Field(default_factory=list)


def distance_pc_from_parallax(parallax_mas: float) -> float:
    """Distance in parsecs from a parallax in milliarcseconds."""

    return 1000.0 / parallax_mas


def _planck18() -> Any:
    """Load the Planck 2018 cosmology lazily; typed loosely for pyright."""

    from astropy.cosmology import Planck18

    return Planck18


def lookback_time_gyr(redshift: float) -> float:
    """Lookback time in Gyr under the Planck 2018 cosmology."""

    return float(_planck18().lookback_time(redshift).to_value("Gyr"))


def luminosity_distance_mpc(redshift: float) -> float:
    """Luminosity distance in Mpc under the Planck 2018 cosmology."""

    return float(_planck18().luminosity_distance(redshift).to_value("Mpc"))


def physical_size_kly(angular_major_arcmin: float, distance_ly: float) -> float:
    """Physical major-axis size in kilo-light-years via the small-angle formula."""

    radians = angular_major_arcmin * (3.141592653589793 / (180.0 * 60.0))
    return radians * distance_ly / 1000.0


def naked_eye_visible(v_mag: float) -> bool:
    """Whether an object is visible to the naked eye under dark skies."""

    return v_mag <= NAKED_EYE_LIMIT_V_MAG


def scale_comparison_for(quantity_kind: str, value: float, unit: str) -> str | None:
    """Deterministic anchor comparisons; arithmetic only, no free-form text."""

    if quantity_kind == "distance" and unit == "light-years":
        if value < 1000.0:
            return "within our local stellar neighborhood of the Milky Way"
        if value < MILKY_WAY_DIAMETER_LY:
            return "inside the Milky Way, whose disk spans about 100,000 light-years"
        ratio = value / MILKY_WAY_DIAMETER_LY
        return f"about {ratio:,.0f} times the diameter of the Milky Way away"
    if quantity_kind == "lookback_time" and unit == "Gyr":
        if value >= EARTH_AGE_GYR:
            return (
                f"this light left before the Earth formed {EARTH_AGE_GYR:.2f} "
                "billion years ago"
            )
        if value >= 0.001:
            return f"this light has traveled for about {value * 1000.0:,.0f} million years"
        return "this light left in the recent astronomical past"
    if quantity_kind == "angular_size" and unit == "arcmin":
        ratio = value / FULL_MOON_ARCMIN
        if ratio >= 0.1:
            return f"about {ratio:.1f} times the apparent width of the full Moon"
        return "far smaller than the full Moon on the sky"
    if quantity_kind == "apparent_magnitude" and unit == "mag":
        if naked_eye_visible(value):
            return "bright enough to see with the naked eye under dark skies"
        return "too faint for the naked eye; binoculars or a telescope are needed"
    if quantity_kind == "physical_size" and unit == "kilo-light-years":
        ratio = value * 1000.0 / MILKY_WAY_DIAMETER_LY
        if ratio >= 0.05:
            return f"about {ratio:.1f} times the diameter of the Milky Way"
        return None
    return None


class FactsCompilerService:
    """Fetch SIMBAD measurements for an object and compile them into facts."""

    def __init__(self, simbad: SimbadTapConnector = simbad_tap_connector) -> None:
        self.simbad = simbad

    async def facts_for_object(self, obj: CelestialObject) -> ObjectFactsResult:
        try:
            measurements = await self.simbad.fetch_measurements(obj.name)
        except AstroLensError as exc:
            return ObjectFactsResult(
                warnings=[
                    WarningMessage(
                        code="FACTS_SOURCE_UNAVAILABLE",
                        message=f"SIMBAD measurements unavailable: {exc.message}",
                        source="SIMBAD",
                        retryable=exc.retryable,
                    )
                ]
            )
        if measurements is None:
            return ObjectFactsResult(
                warnings=[
                    WarningMessage(
                        code="FACTS_OBJECT_UNKNOWN",
                        message=(
                            f"SIMBAD has no measurement record matching '{obj.name}'."
                        ),
                        source="SIMBAD",
                        retryable=False,
                    )
                ]
            )
        return self.compile(obj, measurements)

    def compile(self, obj: CelestialObject, m: SimbadMeasurements) -> ObjectFactsResult:
        slug = normalize_query(obj.name) or "object"
        builder = _FactBuilder(obj=obj, slug=slug)

        if m.otype:
            label = OTYPE_LABELS.get(m.otype, m.otype)
            builder.direct(
                quantity_kind="classification",
                claim=f"{obj.name} is classified as a {label} in the SIMBAD database.",
                source_fields=["basic.otype"],
                bibcode=None,
            )
        if m.v_mag is not None:
            builder.direct(
                quantity_kind="apparent_magnitude",
                claim=(
                    f"{obj.name} has an apparent visual magnitude of {m.v_mag:.2f}."
                ),
                source_fields=["allfluxes.V"],
                bibcode=None,
                value=m.v_mag,
                unit="mag",
            )
        if m.angular_major_arcmin is not None:
            builder.direct(
                quantity_kind="angular_size",
                claim=(
                    f"{obj.name} spans about {m.angular_major_arcmin:.1f} arcminutes "
                    "across its major axis on the sky."
                ),
                source_fields=["basic.galdim_majaxis"],
                bibcode=m.galdim_bibcode,
                value=m.angular_major_arcmin,
                unit="arcmin",
            )
        if m.morph_type:
            builder.direct(
                quantity_kind="morphology",
                claim=f"{obj.name} has morphological type {m.morph_type}.",
                source_fields=["basic.morph_type"],
                bibcode=m.morph_bibcode,
            )
        if m.spectral_type:
            builder.direct(
                quantity_kind="spectral_type",
                claim=f"{obj.name} has spectral type {m.spectral_type}.",
                source_fields=["basic.sp_type"],
                bibcode=m.sp_bibcode,
            )

        redshift = self._cosmological_redshift(m)
        if redshift is not None:
            builder.direct(
                quantity_kind="redshift",
                claim=f"{obj.name} has a measured redshift of z = {redshift:.5f}.",
                source_fields=["basic.rvz_redshift"],
                bibcode=m.rvz_bibcode,
                value=redshift,
                unit="dimensionless",
            )
        elif m.radial_velocity_km_s is not None:
            builder.direct(
                quantity_kind="radial_velocity",
                claim=(
                    f"{obj.name} has a measured radial velocity of "
                    f"{m.radial_velocity_km_s:+.1f} km/s."
                ),
                source_fields=["basic.rvz_radvel"],
                bibcode=m.rvz_bibcode,
                value=m.radial_velocity_km_s,
                unit="km/s",
            )

        distance_ly = self._distance_facts(builder, m, redshift)
        if redshift is not None:
            lookback = lookback_time_gyr(redshift)
            builder.derived(
                quantity_kind="lookback_time",
                claim=(
                    f"The light from {obj.name} seen today left it about "
                    f"{_format_gyr(lookback)} ago, assuming the Planck 2018 cosmology."
                ),
                source_fields=["basic.rvz_redshift"],
                derivation="astropy.cosmology.Planck18.lookback_time(z)",
                value=lookback,
                unit="Gyr",
                steps=1,
            )
        if distance_ly is not None and m.angular_major_arcmin is not None:
            size_kly = physical_size_kly(m.angular_major_arcmin, distance_ly)
            builder.derived(
                quantity_kind="physical_size",
                claim=(
                    f"Combining its apparent size and distance, {obj.name} is about "
                    f"{size_kly:,.0f} thousand light-years across."
                ),
                source_fields=["basic.galdim_majaxis", *builder.distance_source_fields],
                derivation="small_angle(galdim_majaxis, distance)",
                value=size_kly,
                unit="kilo-light-years",
                steps=2,
            )

        return ObjectFactsResult(
            facts=builder.facts,
            citations=builder.citations(),
            warnings=builder.warnings,
        )

    def _cosmological_redshift(self, m: SimbadMeasurements) -> float | None:
        if m.redshift is None:
            return None
        if m.rvz_type == "z" or m.redshift > MIN_COSMOLOGICAL_REDSHIFT:
            return m.redshift
        return None

    def _distance_facts(
        self,
        builder: _FactBuilder,
        m: SimbadMeasurements,
        redshift: float | None,
    ) -> float | None:
        """Emit the best available distance fact; return distance in light-years."""

        if m.parallax_mas is not None and m.parallax_mas > 0:
            relative_error = (
                (m.parallax_err_mas / m.parallax_mas)
                if m.parallax_err_mas is not None
                else 0.0
            )
            if relative_error > PARALLAX_MAX_RELATIVE_ERROR:
                builder.warn(
                    "FACTS_PARALLAX_UNCERTAIN",
                    "Parallax measurement is too uncertain for a distance estimate "
                    f"(relative error {relative_error:.0%}).",
                )
            else:
                distance_pc = distance_pc_from_parallax(m.parallax_mas)
                distance_ly = distance_pc * PC_TO_LIGHT_YEARS
                builder.distance_source_fields = ["basic.plx_value"]
                builder.derived(
                    quantity_kind="distance",
                    claim=(
                        f"From its parallax, {builder.obj.name} lies about "
                        f"{distance_ly:,.0f} light-years away."
                    ),
                    source_fields=["basic.plx_value"],
                    derivation="distance_pc = 1000 / parallax_mas",
                    value=distance_ly,
                    unit="light-years",
                    steps=1,
                    bibcode=m.parallax_bibcode,
                )
                return distance_ly
        if redshift is not None:
            distance_mpc = luminosity_distance_mpc(redshift)
            distance_ly = distance_mpc * MPC_TO_LIGHT_YEARS
            builder.distance_source_fields = ["basic.rvz_redshift"]
            builder.derived(
                quantity_kind="distance",
                claim=(
                    f"From its redshift, {builder.obj.name} lies about "
                    f"{distance_ly / 1e6:,.0f} million light-years away, assuming "
                    "the Planck 2018 cosmology."
                ),
                source_fields=["basic.rvz_redshift"],
                derivation="astropy.cosmology.Planck18.luminosity_distance(z)",
                value=distance_ly,
                unit="light-years",
                steps=1,
                bibcode=m.rvz_bibcode,
            )
            return distance_ly
        return None


class _FactBuilder:
    """Accumulates facts, bibcode citations, and warnings for one object."""

    def __init__(self, *, obj: CelestialObject, slug: str) -> None:
        self.obj = obj
        self.slug = slug
        self.facts: list[Fact] = []
        self.warnings: list[WarningMessage] = []
        self.distance_source_fields: list[str] = []
        self._bibcodes: list[str] = []

    def direct(
        self,
        *,
        quantity_kind: str,
        claim: str,
        source_fields: list[str],
        bibcode: str | None,
        value: float | None = None,
        unit: str | None = None,
    ) -> None:
        confidence = 0.9 if bibcode else 0.8
        self._append(
            quantity_kind=quantity_kind,
            claim=claim,
            source_fields=source_fields,
            derivation=None,
            value=value,
            unit=unit,
            confidence=confidence,
            bibcode=bibcode,
            scope="catalog_measurement",
        )

    def derived(
        self,
        *,
        quantity_kind: str,
        claim: str,
        source_fields: list[str],
        derivation: str,
        value: float,
        unit: str,
        steps: int,
        bibcode: str | None = None,
    ) -> None:
        confidence = 0.7 if steps <= 1 else 0.6
        self._append(
            quantity_kind=quantity_kind,
            claim=claim,
            source_fields=source_fields,
            derivation=derivation,
            value=value,
            unit=unit,
            confidence=confidence,
            bibcode=bibcode,
            scope="derived_measurement",
        )

    def warn(self, code: str, message: str) -> None:
        self.warnings.append(
            WarningMessage(code=code, message=message, source="SIMBAD", retryable=False)
        )

    def citations(self) -> list[Citation]:
        cited: list[Citation] = [SIMBAD_TAP_CITATION]
        for bibcode in self._bibcodes:
            cited.append(_bibcode_citation(bibcode))
        return cited

    def _append(
        self,
        *,
        quantity_kind: str,
        claim: str,
        source_fields: list[str],
        derivation: str | None,
        value: float | None,
        unit: str | None,
        confidence: float,
        bibcode: str | None,
        scope: str,
    ) -> None:
        citation_ids = [SIMBAD_TAP_CITATION.id]
        if bibcode:
            citation_ids.append(f"citation:bibcode:{bibcode}")
            if bibcode not in self._bibcodes:
                self._bibcodes.append(bibcode)
        scale = (
            scale_comparison_for(quantity_kind, value, unit)
            if value is not None and unit is not None
            else None
        )
        self.facts.append(
            Fact(
                id=f"fact:{self.slug}:{quantity_kind}",
                entity_type="object",
                entity_id=self.obj.id,
                claim=claim,
                scope=scope,
                confidence=confidence,
                citation_ids=citation_ids,
                value=value,
                unit=unit,
                quantity_kind=quantity_kind,
                source_fields=source_fields,
                derivation=derivation,
                scale_comparison=scale,
            )
        )


def _bibcode_citation(bibcode: str) -> Citation:
    return Citation(
        id=f"citation:bibcode:{bibcode}",
        title=f"Measurement reference {bibcode}",
        source="SIMBAD/ADS",
        url=f"https://ui.adsabs.harvard.edu/abs/{quote(bibcode)}",
        credit_text=None,
    )


def _format_gyr(value: float) -> str:
    if value >= 1.0:
        return f"{value:.1f} billion years"
    return f"{value * 1000.0:,.0f} million years"


facts_compiler_service = FactsCompilerService()
