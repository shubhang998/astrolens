import asyncio
import os

import pytest

from astrolens.connectors.sesame import sesame_connector

pytestmark = pytest.mark.skipif(
    os.getenv("ASTROLENS_RUN_LIVE") != "1",
    reason="Live Sesame integration tests are opt-in.",
)


@pytest.mark.integration
def test_live_sesame_resolves_m87() -> None:
    candidates = asyncio.run(sesame_connector.resolve_object("M87"))

    assert candidates
    assert abs(candidates[0].ra_deg - 187.70593077) < 0.01
    assert abs(candidates[0].dec_deg - 12.39112325) < 0.01
