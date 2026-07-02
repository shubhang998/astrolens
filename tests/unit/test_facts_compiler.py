import asyncio

import pytest

from astrolens.connectors.simbad_tap import SimbadMeasurements
from astrolens.core.enums import ErrorCode
from astrolens.core.errors import AstroLensError
from astrolens.services.facts import (
    FactsCompilerService,
    distance_pc_from_parallax,
    lookback_time_gyr,
    luminosity_distance_mpc,
    naked_eye_visible,
    physical_size_kly,
)
from astrolens.services.repository import repository

M87 = repository.get_object("astro:object:m87")

M87_MEASUREMENTS = SimbadMeasurements(
    main_id="M  87",
    otype="AGN",
    ra_deg=187.70593077,
    dec_deg=12.39112325,
    redshift=0.00428,
    rvz_type="z",
    rvz_bibcode="2011MNRAS.413..813C",
    morph_type="E",
    morph_bibcode="2019ApJ...875L...1E",
    angular_major_arcmin=8.3,
    angular_minor_arcmin=6.6,
    galdim_bibcode="2003AJ....125..525J",
    v_mag=8.6,
    reference_count=7195,
)

VEGA_MEASUREMENTS = SimbadMeasurements(
    main_id="* alf Lyr",
    otype="dS*",
    ra_deg=279.23473479,
    dec_deg=38.78368896,
    parallax_mas=130.23,
    parallax_err_mas=0.36,
    parallax_bibcode="2007A&A...474..653V",
    radial_velocity_km_s=-20.6,
    rvz_type="v",
    spectral_type="A0Va",
    sp_bibcode="2003AJ....126.2048G",
    v_mag=0.03,
)


def test_derivations_match_known_values() -> None:
    assert distance_pc_from_parallax(130.23) == pytest.approx(7.679, abs=1e-3)
    assert lookback_time_gyr(0.00428) == pytest.approx(0.0617, abs=1e-3)
    assert luminosity_distance_mpc(0.00428) == pytest.approx(19.03, rel=0.01)
    # Small-angle check: 8.3 arcmin at 60 million light-years is ~145 kly.
    assert physical_size_kly(8.3, 60_000_000.0) == pytest.approx(144.9, rel=0.01)
    assert naked_eye_visible(0.03) is True
    assert naked_eye_visible(8.6) is False


def test_compile_m87_produces_redshift_distance_lookback_and_size() -> None:
    service = FactsCompilerService()

    result = service.compile(M87, M87_MEASUREMENTS)

    by_kind = {fact.quantity_kind: fact for fact in result.facts}
    assert by_kind["redshift"].value == pytest.approx(0.00428)
    assert by_kind["redshift"].derivation is None
    assert by_kind["redshift"].source_fields == ["basic.rvz_redshift"]

    lookback = by_kind["lookback_time"]
    assert lookback.value == pytest.approx(0.0617, abs=1e-3)
    assert lookback.unit == "Gyr"
    assert lookback.derivation == "astropy.cosmology.Planck18.lookback_time(z)"
    assert "million years" in lookback.claim

    distance = by_kind["distance"]
    assert distance.unit == "light-years"
    assert distance.value == pytest.approx(19.03 * 3.26156e6, rel=0.01)
    assert distance.derivation == "astropy.cosmology.Planck18.luminosity_distance(z)"

    size = by_kind["physical_size"]
    assert size.derivation == "small_angle(galdim_majaxis, distance)"
    assert set(size.source_fields) == {"basic.galdim_majaxis", "basic.rvz_redshift"}

    magnitude = by_kind["apparent_magnitude"]
    assert magnitude.scale_comparison is not None
    assert "too faint" in magnitude.scale_comparison


def test_compile_vega_uses_parallax_not_redshift() -> None:
    service = FactsCompilerService()

    result = service.compile(M87.model_copy(update={"name": "Vega"}), VEGA_MEASUREMENTS)

    by_kind = {fact.quantity_kind: fact for fact in result.facts}
    assert "redshift" not in by_kind
    assert "lookback_time" not in by_kind
    assert by_kind["radial_velocity"].value == pytest.approx(-20.6)

    distance = by_kind["distance"]
    assert distance.derivation == "distance_pc = 1000 / parallax_mas"
    assert distance.value == pytest.approx(7.679 * 3.26156, rel=0.01)
    assert "citation:bibcode:2007A&A...474..653V" in distance.citation_ids

    magnitude = by_kind["apparent_magnitude"]
    assert magnitude.scale_comparison is not None
    assert "naked eye" in magnitude.scale_comparison


def test_uncertain_parallax_is_gated_with_warning() -> None:
    service = FactsCompilerService()
    uncertain = VEGA_MEASUREMENTS.model_copy(
        update={"parallax_mas": 2.0, "parallax_err_mas": 1.0}
    )

    result = service.compile(M87.model_copy(update={"name": "Far Star"}), uncertain)

    by_kind = {fact.quantity_kind: fact for fact in result.facts}
    assert "distance" not in by_kind
    assert any(warning.code == "FACTS_PARALLAX_UNCERTAIN" for warning in result.warnings)


def test_kinematic_radial_velocity_is_not_treated_as_redshift() -> None:
    service = FactsCompilerService()
    kinematic = VEGA_MEASUREMENTS.model_copy(
        update={"redshift": 0.0001, "rvz_type": "v", "parallax_mas": None}
    )

    result = service.compile(M87.model_copy(update={"name": "Nearby Star"}), kinematic)

    by_kind = {fact.quantity_kind: fact for fact in result.facts}
    assert "redshift" not in by_kind
    assert "lookback_time" not in by_kind


def test_every_fact_is_cited_and_traceable() -> None:
    service = FactsCompilerService()

    for measurements in (M87_MEASUREMENTS, VEGA_MEASUREMENTS):
        result = service.compile(M87, measurements)
        assert result.facts
        for fact in result.facts:
            assert fact.citation_ids, fact.id
            assert fact.source_fields, fact.id
            if fact.value is not None:
                assert fact.unit is not None, fact.id
        citation_ids = {citation.id for citation in result.citations}
        assert "citation:simbad:tap" in citation_ids
        for fact in result.facts:
            for cited in fact.citation_ids:
                assert cited in citation_ids, cited


class _MustNotBeCalledSimbad:
    async def fetch_measurements(self, main_id: str) -> None:
        raise AssertionError("SIMBAD must not be queried for solar-system objects")


def test_curated_planetary_facts_bypass_simbad() -> None:
    service = FactsCompilerService(simbad=_MustNotBeCalledSimbad())  # type: ignore[arg-type]
    saturn = repository.get_object("astro:object:saturn")

    result = asyncio.run(service.facts_for_object(saturn))

    by_kind = {fact.quantity_kind: fact for fact in result.facts}
    assert by_kind["diameter"].value == pytest.approx(120_536.0)
    assert by_kind["density"].scale_comparison == "less dense than water"
    assert result.warnings == []
    assert {citation.id for citation in result.citations} == {
        "citation:nssdc:planetary-fact-sheet"
    }
    for fact in result.facts:
        assert fact.citation_ids == ["citation:nssdc:planetary-fact-sheet"]
        assert fact.source_fields == ["nssdc.planetary_fact_sheet"]


def test_all_seeded_solar_system_objects_have_curated_facts() -> None:
    from astrolens.data.seed import CURATED_OBJECT_FACTS

    for slug in ("jupiter", "saturn", "uranus", "neptune", "titan", "io"):
        facts = CURATED_OBJECT_FACTS[f"astro:object:{slug}"]
        assert facts, slug
        for fact in facts:
            assert fact.citation_ids and fact.source_fields, fact.id


def test_uncurated_ephemeris_object_gets_teaching_warning_not_simbad_lookup() -> None:
    service = FactsCompilerService(simbad=_MustNotBeCalledSimbad())  # type: ignore[arg-type]
    mars = M87.model_copy(
        update={"name": "Mars", "id": "astro:object:mars", "ephemeris_object": True}
    )

    result = asyncio.run(service.facts_for_object(mars))

    assert result.facts == []
    assert result.warnings[0].code == "FACTS_EPHEMERIS_OBJECT"
    assert "solar-system body" in result.warnings[0].message


def test_facts_for_object_degrades_to_warning_on_source_failure() -> None:
    class FailingSimbad:
        async def fetch_measurements(self, main_id: str) -> None:
            raise AstroLensError(
                ErrorCode.SOURCE_TIMEOUT,
                "SIMBAD TAP timed out.",
                retryable=True,
            )

    service = FactsCompilerService(simbad=FailingSimbad())  # type: ignore[arg-type]

    result = asyncio.run(service.facts_for_object(M87))

    assert result.facts == []
    assert result.warnings[0].code == "FACTS_SOURCE_UNAVAILABLE"
    assert result.warnings[0].retryable is True


def test_facts_for_object_warns_when_object_unknown() -> None:
    class EmptySimbad:
        async def fetch_measurements(self, main_id: str) -> None:
            return None

    service = FactsCompilerService(simbad=EmptySimbad())  # type: ignore[arg-type]

    result = asyncio.run(service.facts_for_object(M87))

    assert result.facts == []
    assert result.warnings[0].code == "FACTS_OBJECT_UNKNOWN"
