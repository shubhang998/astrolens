import asyncio
import os

import pytest

from astrolens.connectors.simbad_tap import SimbadTapConnector

pytestmark = pytest.mark.skipif(
    os.getenv("ASTROLENS_RUN_LIVE") != "1",
    reason="Live SIMBAD TAP integration tests are opt-in.",
)


@pytest.mark.integration
def test_live_simbad_measurements_for_m87() -> None:
    connector = SimbadTapConnector()

    measurements = asyncio.run(connector.fetch_measurements("M  87"))

    assert measurements is not None
    assert measurements.main_id.replace(" ", "") in {"M87", "NGC4486"}
    assert measurements.redshift is not None and 0.003 < measurements.redshift < 0.006
    assert measurements.v_mag is not None and 8.0 < measurements.v_mag < 10.0


@pytest.mark.integration
def test_live_simbad_category_search_returns_quasars() -> None:
    connector = SimbadTapConnector()

    result = asyncio.run(
        connector.search_category(otype="QSO", magnitude_limit=17.0, limit=5)
    )

    assert len(result.hits) >= 1
    assert all(hit.ra_deg is not None for hit in result.hits)
