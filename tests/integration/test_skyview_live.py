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
def test_live_skyview_accepts_every_configured_survey_name() -> None:
    """Catch SkyView survey-name drift for the strings in SURVEY_SPECS."""

    from astroquery.skyview import SkyView

    from astrolens.connectors.skyview import SURVEY_SPECS

    available = {name for names in SkyView.survey_dict.values() for name in names}
    missing = [spec.survey for spec in SURVEY_SPECS if spec.survey not in available]
    assert not missing, f"SkyView no longer recognizes: {missing}"


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
    visible_surveys = {"SDSSg", "SDSSr", "SDSSi", "DSS2 Blue", "DSS2 Red", "DSS2 IR"}
    assert result.products[0].survey in visible_surveys
    assert result.products[0].download_url.startswith(("http://", "https://"))
    assert result.products[0].file_format == "fits"
