import asyncio
import os

import pytest

from astrolens.connectors.skyview import SkyViewConnector
from astrolens.core.enums import BandFamily

pytestmark = pytest.mark.skipif(
    os.getenv("ASTROLENS_RUN_LIVE") != "1",
    reason="Live SkyView integration tests are opt-in.",
)

pytest.importorskip("astroquery", reason="Install astrolens[skyview] for SkyView live tests.")


@pytest.mark.integration
def test_live_skyview_returns_public_fits_url_for_m87() -> None:
    connector = SkyViewConnector()

    result = asyncio.run(
        connector.search_generated_fits(
            ra_deg=187.70593077,
            dec_deg=12.39112325,
            radius_deg=0.03,
            bands=[BandFamily.VISIBLE],
            pixels=128,
        )
    )

    assert result.products
    assert result.products[0].survey == "DSS2 Red"
    assert result.products[0].download_url.startswith(("http://", "https://"))
    assert result.products[0].file_format == "fits"
