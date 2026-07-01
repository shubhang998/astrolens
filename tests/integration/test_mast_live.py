import asyncio
import os

import pytest

from astrolens.connectors.mast import mast_connector

pytestmark = pytest.mark.skipif(
    os.getenv("ASTROLENS_RUN_LIVE") != "1",
    reason="Live MAST integration tests are opt-in.",
)


@pytest.mark.integration
def test_live_mast_finds_public_jwst_or_hst_images_for_m87() -> None:
    result = asyncio.run(
        mast_connector.search_public_images(
            ra_deg=187.70593077,
            dec_deg=12.39112325,
            limit=2,
            product_limit=4,
            product_observation_limit=1,
        )
    )

    assert result.observations
    assert result.observations[0].collection in {"JWST", "HST"}
    assert result.products_by_observation
    assert any(product.download_url for product in result.products_by_observation[0].products)
