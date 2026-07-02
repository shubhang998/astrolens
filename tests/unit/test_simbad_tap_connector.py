import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from astrolens.connectors.simbad_tap import (
    MAX_CATEGORY_RESULTS,
    SimbadTapConnector,
    category_adql,
    escape_adql_string,
    measurements_adql,
    otype_for_category,
)
from astrolens.core.enums import ErrorCode, SourceHealthStatus
from astrolens.core.errors import AstroLensError

FIXTURES = Path("tests/fixtures/simbad")


class FakeTapClient:
    def __init__(self, payloads: list[dict[str, Any]] | None = None) -> None:
        self.payloads = payloads or []
        self.queries: list[str] = []

    def query(self, adql: str) -> dict[str, Any]:
        self.queries.append(adql)
        if not self.payloads:
            return {"metadata": [], "data": []}
        if len(self.payloads) == 1:
            return self.payloads[0]
        return self.payloads.pop(0)


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_measurements_adql_is_exact_and_escaped() -> None:
    adql = measurements_adql("M  87")
    assert "WHERE i.id = 'M  87'" in adql
    assert "FROM basic AS b" in adql
    assert "JOIN ident AS i ON i.oidref = b.oid" in adql
    assert "LEFT JOIN allfluxes AS f ON f.oidref = b.oid" in adql

    quoted = measurements_adql("Barnard's Star")
    assert "WHERE i.id = 'Barnard''s Star'" in quoted


def test_escape_adql_rejects_control_characters() -> None:
    with pytest.raises(AstroLensError) as exc_info:
        escape_adql_string("M87\n; DROP TABLE basic")

    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_category_adql_includes_cone_magnitude_and_sampling_clauses() -> None:
    adql = category_adql(
        "QSO",
        cone=(187.70593, 12.39112, 5.0),
        magnitude_limit=18.0,
        limit=10,
        sample_modulus=37,
        sample_residue=14,
    )

    assert adql.startswith("SELECT TOP 10 ")
    assert "ot.otype = 'QSO'" in adql
    assert "CIRCLE('ICRS', 187.705930, 12.391120, 5.0000)" in adql
    assert "f.V <= 18.00" in adql
    assert "MOD(b.oid, 37) = 14" in adql
    # Sampled queries stay unordered so SIMBAD can stream rows cheaply.
    assert "ORDER BY" not in adql


def test_category_adql_clamps_limit_and_defaults_to_reference_ordering() -> None:
    adql = category_adql("G", limit=500)

    assert f"SELECT TOP {MAX_CATEGORY_RESULTS} " in adql
    assert adql.endswith("ORDER BY nbref DESC")


def test_otype_for_category_teaches_on_unknown_category() -> None:
    assert otype_for_category("Supernova Remnant") == "SNR"

    with pytest.raises(AstroLensError) as exc_info:
        otype_for_category("wormhole")

    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert "quasar" in exc_info.value.details["supported_categories"]


def test_fetch_measurements_parses_by_column_name() -> None:
    client = FakeTapClient([_fixture("m87_measurements.json")])
    connector = SimbadTapConnector(client=client)

    measurements = asyncio.run(connector.fetch_measurements("M  87"))

    assert measurements is not None
    assert measurements.main_id == "M  87"
    assert measurements.otype == "AGN"
    assert measurements.redshift == pytest.approx(0.00428)
    assert measurements.rvz_type == "z"
    assert measurements.rvz_bibcode == "2011MNRAS.413..813C"
    assert measurements.angular_major_arcmin == pytest.approx(8.3)
    assert measurements.v_mag == pytest.approx(8.6)
    assert measurements.reference_count == 7195
    assert measurements.parallax_mas is None


def test_fetch_measurements_handles_parallax_star_without_redshift() -> None:
    client = FakeTapClient([_fixture("vega_measurements.json")])
    connector = SimbadTapConnector(client=client)

    measurements = asyncio.run(connector.fetch_measurements("* alf Lyr"))

    assert measurements is not None
    assert measurements.parallax_mas == pytest.approx(130.23)
    assert measurements.parallax_bibcode == "2007A&A...474..653V"
    assert measurements.redshift is None
    assert measurements.rvz_type == "v"
    assert measurements.spectral_type == "A0Va"


def test_fetch_measurements_retries_with_collapsed_whitespace() -> None:
    client = FakeTapClient([_fixture("empty.json"), _fixture("m87_measurements.json")])
    connector = SimbadTapConnector(client=client)

    measurements = asyncio.run(connector.fetch_measurements("M   87"))

    assert measurements is not None
    assert len(client.queries) == 2
    assert "WHERE i.id = 'M   87'" in client.queries[0]
    assert "WHERE i.id = 'M 87'" in client.queries[1]


def test_fetch_measurements_returns_none_when_unknown() -> None:
    client = FakeTapClient([_fixture("empty.json")])
    connector = SimbadTapConnector(client=client)

    assert asyncio.run(connector.fetch_measurements("Nonexistent")) is None


def test_search_category_parses_hits() -> None:
    client = FakeTapClient([_fixture("qso_category.json")])
    connector = SimbadTapConnector(client=client)

    result = asyncio.run(connector.search_category(otype="QSO", limit=5))

    assert [hit.main_id for hit in result.hits] == ["3C 273", "3C 48", "QSO B1422+2309"]
    assert result.hits[0].redshift == pytest.approx(0.1583)
    assert result.hits[0].v_mag == pytest.approx(12.85)
    assert "ot.otype = 'QSO'" in result.query_adql
    assert result.warnings == []


def test_search_category_random_sampling_halves_modulus_until_filled() -> None:
    # First two sampled queries return nothing; the third succeeds.
    client = FakeTapClient(
        [_fixture("empty.json"), _fixture("empty.json"), _fixture("qso_category.json")]
    )
    connector = SimbadTapConnector(client=client)

    result = asyncio.run(
        connector.search_category(otype="QSO", limit=3, random_sample=True, sample_seed=7)
    )

    assert len(result.hits) == 3
    assert len(client.queries) == 3
    assert "MOD(b.oid, 37)" in client.queries[0]
    assert "MOD(b.oid, 18)" in client.queries[1]
    assert "MOD(b.oid, 9)" in client.queries[2]


def test_search_category_random_sampling_warns_on_unsampled_fallback() -> None:
    client = FakeTapClient([_fixture("empty.json")])
    connector = SimbadTapConnector(client=client)

    result = asyncio.run(
        connector.search_category(otype="QSO", limit=3, random_sample=True, sample_seed=7)
    )

    assert result.hits == []
    assert any("non-random" in warning or "unsampled" in warning for warning in result.warnings)
    assert "MOD(b.oid, 1) = 0" in client.queries[-1]


def test_malformed_json_maps_to_source_unavailable(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self, limit: int = -1) -> bytes:
            return b"<html>gateway error</html>"

    monkeypatch.setattr(
        "astrolens.connectors.simbad_tap.urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    connector = SimbadTapConnector()

    with pytest.raises(AstroLensError) as exc_info:
        asyncio.run(connector.fetch_measurements("M  87"))

    assert exc_info.value.code == ErrorCode.SOURCE_UNAVAILABLE
    assert exc_info.value.retryable is True


def test_timeout_maps_to_source_timeout(monkeypatch) -> None:
    def fake_urlopen(*_args: Any, **_kwargs: Any) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr("astrolens.connectors.simbad_tap.urlopen", fake_urlopen)
    connector = SimbadTapConnector()

    with pytest.raises(AstroLensError) as exc_info:
        asyncio.run(connector.fetch_measurements("M  87"))

    assert exc_info.value.code == ErrorCode.SOURCE_TIMEOUT


def test_query_fails_over_to_mirror_when_primary_is_down(monkeypatch) -> None:
    import json as json_module

    from astrolens.connectors.simbad_tap import (
        SIMBAD_TAP_MIRROR_SYNC_URL,
        SIMBAD_TAP_SYNC_URL,
    )

    attempted: list[str] = []

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self, limit: int = -1) -> bytes:
            return json_module.dumps(_fixture("m87_measurements.json")).encode()

    def fake_urlopen(request: Any, **_kwargs: Any) -> FakeResponse:
        attempted.append(request.full_url)
        if request.full_url == SIMBAD_TAP_SYNC_URL:
            raise TimeoutError("primary down")
        return FakeResponse()

    monkeypatch.setattr("astrolens.connectors.simbad_tap.urlopen", fake_urlopen)
    connector = SimbadTapConnector()

    measurements = asyncio.run(connector.fetch_measurements("M  87"))

    assert measurements is not None
    assert measurements.main_id == "M  87"
    assert attempted == [SIMBAD_TAP_SYNC_URL, SIMBAD_TAP_MIRROR_SYNC_URL]


def test_http_400_does_not_fail_over(monkeypatch) -> None:
    from email.message import Message
    from urllib.error import HTTPError

    attempted: list[str] = []

    def fake_urlopen(request: Any, **_kwargs: Any) -> None:
        attempted.append(request.full_url)
        raise HTTPError(request.full_url, 400, "Bad Request", Message(), None)

    monkeypatch.setattr("astrolens.connectors.simbad_tap.urlopen", fake_urlopen)
    connector = SimbadTapConnector()

    with pytest.raises(AstroLensError):
        asyncio.run(connector.fetch_measurements("M  87"))

    assert len(attempted) == 1  # bad ADQL is identical on every mirror


def test_measurements_are_cached_per_identifier() -> None:
    client = FakeTapClient([_fixture("m87_measurements.json")])
    connector = SimbadTapConnector(client=client)

    first = asyncio.run(connector.fetch_measurements("M  87"))
    second = asyncio.run(connector.fetch_measurements("M  87"))

    assert first is not None and second is not None
    assert len(client.queries) == 1


def test_healthcheck_never_raises(monkeypatch) -> None:
    def fake_urlopen(*_args: Any, **_kwargs: Any) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr("astrolens.connectors.simbad_tap.urlopen", fake_urlopen)
    connector = SimbadTapConnector()

    health = asyncio.run(connector.healthcheck())

    assert health.status == SourceHealthStatus.UNAVAILABLE
