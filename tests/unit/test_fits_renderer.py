import pytest

from astrolens.services.fits_renderer import (
    DEFAULT_ALLOWED_URL_HOST_SUFFIXES,
    FitsRenderer,
    FitsRendererDependencies,
    FitsRenderRequest,
    SourceFitsProduct,
    _suppress_neon_channel_artifacts,
    create_render_recipe,
    product_eligibility,
    rgb_filter_mapping,
    select_coherent_render_products,
    select_eligible_fits_products,
    validate_download_url,
)


def _product(
    product_id: str,
    *,
    file_name: str,
    calibration_level: float = 3,
    file_format: str = "fits",
    filter_name: str | None = None,
    wavelength_nm: float | None = None,
) -> SourceFitsProduct:
    return SourceFitsProduct(
        id=product_id,
        download_url=f"https://example.org/{file_name}",
        file_name=file_name,
        file_format=file_format,
        product_type="SCIENCE",
        calibration_level=calibration_level,
        filter_name=filter_name,
        wavelength_nm=wavelength_nm,
        source_record_id=f"mast:TEST/product/{file_name}",
    )


def _local_fits_product(
    product_id: str,
    path,
    *,
    wavelength_nm: float,
) -> SourceFitsProduct:
    return SourceFitsProduct(
        id=product_id,
        download_url=path.as_uri(),
        file_name=path.name,
        file_format="fits",
        product_type="SCIENCE",
        calibration_level=3,
        file_size_mb=0.01,
        wavelength_nm=wavelength_nm,
        source_record_id=f"fixture:{path.name}",
    )


def _write_wcs_fits(
    path,
    *,
    shape: tuple[int, int],
    crpix: tuple[float, float],
    scale_arcsec: float = 1.0,
    rotation_deg: float = 0.0,
    extension: bool = False,
) -> None:
    import numpy as np
    from astropy.io import fits
    from astropy.wcs import WCS

    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.crval = [150.0, 2.0]
    wcs.wcs.crpix = [crpix[0], crpix[1]]
    scale_deg = scale_arcsec / 3600.0
    theta = np.deg2rad(rotation_deg)
    wcs.wcs.cd = np.array(
        [
            [-scale_deg * np.cos(theta), scale_deg * np.sin(theta)],
            [scale_deg * np.sin(theta), scale_deg * np.cos(theta)],
        ]
    )
    data = np.zeros(shape, dtype=np.float32)
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    sources = [(-12.0, -7.0, 80.0), (3.0, 4.0, 140.0), (15.0, -2.0, 105.0)]
    for delta_ra_arcsec, delta_dec_arcsec, amplitude in sources:
        world = [
            [
                150.0 + (delta_ra_arcsec / 3600.0),
                2.0 + (delta_dec_arcsec / 3600.0),
            ]
        ]
        x, y = wcs.all_world2pix(world, 0)[0]
        data += amplitude * np.exp(-(((xx - x) ** 2 + (yy - y) ** 2) / 8.0))
    header = wcs.to_header()
    if extension:
        fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(data=data, header=header)]).writeto(
            path,
            overwrite=True,
        )
        return
    fits.writeto(path, data, header=header, overwrite=True)


def _channel_centroid(channel) -> tuple[float, float]:
    import numpy as np

    threshold = np.percentile(channel, 99.4)
    mask = channel >= threshold
    yy, xx = np.nonzero(mask)
    weights = channel[mask].astype(float) + 1.0
    return float(np.average(xx, weights=weights)), float(np.average(yy, weights=weights))


def test_suppress_neon_channel_artifacts_neutralizes_green_spikes() -> None:
    import numpy as np

    rgb = np.full((64, 64, 3), 0.28, dtype=np.float32)
    rgb[31, 31] = [0.02, 0.95, 0.08]
    rgb[31, 32] = [0.04, 0.88, 0.78]
    rgb[32, 32] = [0.0, 0.0, 0.0]
    rgb[:12, :12] = 0.02
    rgb[4, 4] = [0.02, 0.95, 0.08]

    repaired = _suppress_neon_channel_artifacts(rgb)

    assert repaired[31, 31, 1] - repaired[31, 31, 0] < 0.08
    assert repaired[31, 32, 1] - repaired[31, 32, 0] < 0.08
    assert repaired[32, 32].mean() > 0.20
    assert np.allclose(repaired[4, 4], rgb[4, 4])


def test_product_eligibility_rejects_raw_uncal_and_prefers_calibrated_fits() -> None:
    raw = _product("raw", file_name="jw00001_uncal.fits", calibration_level=1)
    jpeg = _product("jpeg", file_name="jw00001_preview.jpg", file_format="jpg")
    calibrated = _product(
        "calibrated",
        file_name="jw00001_i2d.fits.gz",
        file_format="fits.gz",
        filter_name="F277W",
    )

    assert not product_eligibility(raw).eligible
    assert not product_eligibility(jpeg).eligible
    assert product_eligibility(calibrated).eligible

    selected = select_eligible_fits_products([raw, jpeg, calibrated])

    assert [product.id for product in selected] == ["calibrated"]


def test_rgb_filter_mapping_uses_shorter_wavelength_as_blue_and_longer_as_red() -> None:
    products = [
        _product("middle", file_name="jw_f150w_i2d.fits", filter_name="F150W"),
        _product("long", file_name="jw_f277w_i2d.fits", filter_name="F277W"),
        _product("short", file_name="jw_f090w_i2d.fits", filter_name="F090W"),
    ]

    mapping = rgb_filter_mapping(products)

    assert mapping.blue.product_id == "short"
    assert mapping.green.product_id == "middle"
    assert mapping.red.product_id == "long"
    assert mapping.false_color is True


def test_create_render_recipe_includes_rgb_mapping_dimensions_and_ids() -> None:
    request = FitsRenderRequest(
        object_id="astro:object:m87",
        products=[
            _product("blue", file_name="hst_f438w_drc.fits", wavelength_nm=438),
            _product("green", file_name="hst_f606w_drc.fits", wavelength_nm=606),
            _product("red", file_name="hst_f814w_drc.fits", wavelength_nm=814),
        ],
        size="thumbnail",
    )

    recipe = create_render_recipe(request)

    assert recipe.cache_key.startswith("fits-render:v14:")
    assert recipe.asset_id.startswith("asset:fits-render:")
    assert recipe.width == 512
    assert recipe.height == 512
    assert recipe.rgb_mapping.red.product_id == "red"
    assert recipe.rgb_mapping.green.product_id == "green"
    assert recipe.rgb_mapping.blue.product_id == "blue"
    assert recipe.false_color is True
    assert recipe.alignment_mode == "wcs_reproject"


def test_renderer_returns_unsupported_when_dependencies_are_missing() -> None:
    request = FitsRenderRequest(
        products=[
            _product("blue", file_name="hst_f438w_drc.fits", wavelength_nm=438),
            _product("green", file_name="hst_f606w_drc.fits", wavelength_nm=606),
            _product("red", file_name="hst_f814w_drc.fits", wavelength_nm=814),
        ]
    )
    renderer = FitsRenderer(
        dependencies=FitsRendererDependencies(astropy=False, numpy=False, pillow=False)
    )

    result = renderer.render(request)

    assert result.status == "unsupported"
    assert result.recipe is not None
    assert result.asset_id == result.recipe.asset_id
    assert result.cache_key == result.recipe.cache_key
    assert result.missing_dependencies == ["astropy", "numpy", "Pillow"]
    assert "optional dependencies" in str(result.error)


def test_renderer_writes_cached_png_when_dependencies_are_ready(tmp_path) -> None:
    import numpy as np
    from astropy.io import fits
    from PIL import Image

    blue_path = tmp_path / "blue.fits"
    green_path = tmp_path / "green.fits"
    red_path = tmp_path / "red.fits"
    base = np.zeros((32, 32), dtype=np.float32)
    yy, xx = np.mgrid[:32, :32]
    signal = np.exp(-(((xx - 16) ** 2 + (yy - 16) ** 2) / 42.0)).astype(np.float32)
    fits.writeto(blue_path, base + signal * 80, overwrite=True)
    fits.writeto(green_path, base + signal * 120, overwrite=True)
    fits.writeto(red_path, base + signal * 160, overwrite=True)

    renderer = FitsRenderer(
        dependencies=FitsRendererDependencies(astropy=True, numpy=True, pillow=True),
        cache_dir=tmp_path / "renders",
        allow_file_urls=True,
        public_base_url="https://example.org",
    )
    request = FitsRenderRequest(
        products=[
            _local_fits_product("blue", blue_path, wavelength_nm=438),
            _local_fits_product("green", green_path, wavelength_nm=606),
            _local_fits_product("red", red_path, wavelength_nm=814),
        ],
        size="thumbnail",
    )

    result = renderer.render(request)
    cached_result = renderer.render(request)

    assert result.status == "complete"
    assert result.recipe is not None
    assert result.recipe.alignment_mode == "fallback_single_channel"
    assert result.asset_url is not None
    assert result.asset_url.startswith("https://example.org/v1/rendered/")
    assert result.file_path is not None
    with Image.open(result.file_path) as rendered:
        assert rendered.size == (512, 512)
        assert rendered.mode == "RGB"
    assert cached_result.status == "complete"
    assert cached_result.file_path == result.file_path


def test_renderer_reprojects_misaligned_wcs_channels_before_rgb_composition(tmp_path) -> None:
    import numpy as np
    from PIL import Image

    blue_path = tmp_path / "visit_clear-f277w_i2d.fits"
    green_path = tmp_path / "visit_clear-f356w_i2d.fits"
    red_path = tmp_path / "visit_clear-f444w_i2d.fits"
    _write_wcs_fits(blue_path, shape=(96, 96), crpix=(36.5, 57.5))
    _write_wcs_fits(green_path, shape=(96, 96), crpix=(48.5, 48.5))
    _write_wcs_fits(
        red_path,
        shape=(128, 128),
        crpix=(72.5, 50.5),
        scale_arcsec=0.7,
        rotation_deg=23,
    )
    renderer = FitsRenderer(
        dependencies=FitsRendererDependencies(
            astropy=True,
            numpy=True,
            pillow=True,
            reproject=True,
        ),
        cache_dir=tmp_path / "renders",
        allow_file_urls=True,
    )

    result = renderer.render(
        request := FitsRenderRequest(
            products=[
                _local_fits_product("blue", blue_path, wavelength_nm=2770),
                _local_fits_product("green", green_path, wavelength_nm=3560),
                _local_fits_product("red", red_path, wavelength_nm=4440),
            ],
            width=256,
            height=256,
            stretch="linear",
        )
    )

    assert result.status == "complete"
    assert result.recipe is not None
    assert result.recipe.false_color is True
    assert result.recipe.alignment_mode == "wcs_reproject"
    assert result.recipe.overlap_fraction is not None
    assert result.recipe.overlap_fraction > 0.2
    assert result.file_path is not None
    cached_result = renderer.render(request)
    assert cached_result.recipe is not None
    assert cached_result.recipe.alignment_mode == "wcs_reproject"
    assert cached_result.recipe.overlap_fraction == result.recipe.overlap_fraction
    with Image.open(result.file_path) as rendered:
        rgb = np.asarray(rendered.convert("RGB"), dtype=float)
    centroids = [_channel_centroid(rgb[:, :, index]) for index in range(3)]
    for first, second in [(centroids[0], centroids[1]), (centroids[1], centroids[2])]:
        distance = np.hypot(first[0] - second[0], first[1] - second[1])
        assert distance < 16.0
    luminance = np.mean(rgb, axis=2)
    bright_mask = luminance > np.percentile(luminance, 99.0)
    assert np.corrcoef(rgb[:, :, 0][bright_mask], rgb[:, :, 1][bright_mask])[0, 1] > 0.55
    assert np.corrcoef(rgb[:, :, 0][bright_mask], rgb[:, :, 2][bright_mask])[0, 1] > 0.55


def test_renderer_uses_wcs_from_image_extension_hdu(tmp_path) -> None:
    import numpy as np
    from PIL import Image

    primary_path = tmp_path / "visit_clear-f277w_i2d.fits"
    extension_path = tmp_path / "visit_clear-f356w_i2d.fits"
    _write_wcs_fits(primary_path, shape=(80, 80), crpix=(40.5, 40.5))
    _write_wcs_fits(extension_path, shape=(80, 80), crpix=(34.5, 45.5), extension=True)
    renderer = FitsRenderer(
        dependencies=FitsRendererDependencies(
            astropy=True,
            numpy=True,
            pillow=True,
            reproject=True,
        ),
        cache_dir=tmp_path / "renders",
        allow_file_urls=True,
    )

    result = renderer.render(
        FitsRenderRequest(
            products=[
                _local_fits_product("blue", primary_path, wavelength_nm=2770),
                _local_fits_product("red", extension_path, wavelength_nm=3560),
            ],
            width=256,
            height=256,
            stretch="linear",
        )
    )

    assert result.status == "complete"
    assert result.recipe is not None
    assert result.recipe.alignment_mode == "wcs_reproject"
    assert result.file_path is not None
    with Image.open(result.file_path) as rendered:
        assert rendered.size == (256, 256)
        rgb = np.asarray(rendered.convert("RGB"), dtype=float)
    assert not np.allclose(rgb[:, :, 0], rgb[:, :, 1])
    assert not np.allclose(rgb[:, :, 1], rgb[:, :, 2])


def test_renderer_recenters_off_center_signal(tmp_path) -> None:
    import numpy as np
    from astropy.io import fits
    from PIL import Image

    source_path = tmp_path / "offcenter.fits"
    yy, xx = np.mgrid[:80, :80]
    signal = np.exp(-(((xx - 14) ** 2 + (yy - 22) ** 2) / 24.0)).astype(np.float32)
    fits.writeto(source_path, signal * 100, overwrite=True)
    renderer = FitsRenderer(
        dependencies=FitsRendererDependencies(astropy=True, numpy=True, pillow=True),
        cache_dir=tmp_path / "renders",
        allow_file_urls=True,
    )

    result = renderer.render(
        FitsRenderRequest(
            products=[_local_fits_product("single", source_path, wavelength_nm=814)],
            size="thumbnail",
        )
    )

    assert result.status == "complete"
    assert result.file_path is not None
    with Image.open(result.file_path) as rendered:
        gray = np.asarray(rendered.convert("L"))
    y, x = np.unravel_index(np.argmax(gray), gray.shape)
    assert 150 <= x <= 362
    assert 150 <= y <= 362


def test_render_recipe_skips_products_above_size_limit() -> None:
    huge = _product(
        "huge",
        file_name="huge_i2d.fits",
        wavelength_nm=814,
    ).model_copy(update={"file_size_mb": 999.0})
    small = _product(
        "small",
        file_name="small_i2d.fits",
        wavelength_nm=606,
    ).model_copy(update={"file_size_mb": 1.0})

    recipe = create_render_recipe(
        FitsRenderRequest(products=[huge, small], max_source_file_mb=100.0)
    )

    assert [product.id for product in recipe.source_products] == ["small"]


def test_render_recipe_uses_cross_group_third_filter_when_same_field_has_only_two() -> None:
    same_field_blue = _product(
        "same-blue",
        file_name="jw03055-o007_t007_nircam_clear-f277w_i2d.fits",
        wavelength_nm=2770,
        filter_name="F277W",
    )
    same_field_red = _product(
        "same-red",
        file_name="jw03055-o007_t007_nircam_clear-f356w_i2d.fits",
        wavelength_nm=3560,
        filter_name="F356W",
    )
    other_field = _product(
        "other-redder",
        file_name="jw09226-o008_t008_nircam_clear-f444w_i2d.fits",
        wavelength_nm=4440,
        filter_name="F444W",
    )

    coherent = select_coherent_render_products([same_field_blue, same_field_red, other_field])
    recipe = create_render_recipe(
        FitsRenderRequest(products=[same_field_blue, same_field_red, other_field])
    )

    assert [product.id for product in coherent] == [
        "same-blue",
        "same-red",
        "other-redder",
    ]
    assert {product.id for product in recipe.source_products} == {
        "same-blue",
        "same-red",
        "other-redder",
    }
    assert recipe.rgb_mapping.blue.product_id == "same-blue"
    assert recipe.rgb_mapping.green.product_id == "same-red"
    assert recipe.rgb_mapping.red.product_id == "other-redder"
    assert recipe.rgb_mapping.false_color is True


def test_live_like_different_observation_ids_are_metadata_candidates_for_wcs_alignment() -> None:
    same_field_blue = _product(
        "same-blue",
        file_name="jw03055-o007_t007_nircam_clear-f277w_i2d.fits",
        wavelength_nm=2770,
        filter_name="F277W",
    ).model_copy(update={"observation_id": "obs-a"})
    same_field_red = _product(
        "same-red",
        file_name="jw03055-o007_t007_nircam_clear-f356w_i2d.fits",
        wavelength_nm=3560,
        filter_name="F356W",
    ).model_copy(update={"observation_id": "obs-b"})

    coherent = select_coherent_render_products([same_field_blue, same_field_red])
    recipe = create_render_recipe(FitsRenderRequest(products=[same_field_blue, same_field_red]))

    assert [product.id for product in coherent] == ["same-blue", "same-red"]
    assert {product.id for product in recipe.source_products} == {"same-blue", "same-red"}
    assert recipe.rgb_mapping.false_color is True
    assert recipe.alignment_mode == "wcs_reproject"


def test_renderer_downgrades_to_single_channel_when_rgb_wcs_is_missing(tmp_path) -> None:
    import numpy as np
    from astropy.io import fits

    blue_path = tmp_path / "visit_clear-f277w_i2d.fits"
    red_path = tmp_path / "visit_clear-f356w_i2d.fits"
    fits.writeto(blue_path, np.array([[0.0, 1.0], [1.0, 0.0]]), overwrite=True)
    fits.writeto(red_path, np.array([[1.0, 0.0], [0.0, 1.0]]), overwrite=True)
    renderer = FitsRenderer(
        dependencies=FitsRendererDependencies(
            astropy=True,
            numpy=True,
            pillow=True,
            reproject=True,
        ),
        cache_dir=tmp_path / "renders",
        allow_file_urls=True,
    )

    result = renderer.render(
        FitsRenderRequest(
            products=[
                _local_fits_product("blue", blue_path, wavelength_nm=2770),
                _local_fits_product("red", red_path, wavelength_nm=3560),
            ],
            width=128,
            height=128,
        )
    )

    assert result.status == "complete"
    assert result.recipe is not None
    assert result.recipe.false_color is False
    assert result.recipe.alignment_mode == "fallback_single_channel"
    assert "WCS alignment failed" in " ".join(result.recipe.caveats)


def test_preselected_request_bypasses_visit_grouping_and_keeps_all_products() -> None:
    # Cross-archive products share no visit fingerprint; a preselected request
    # must keep exactly what the caller chose, mapped by wavelength.
    products = [
        _product("radio", file_name="skyview_nvss.fits", wavelength_nm=214_000_000.0),
        _product("xray", file_name="skyview_rass.fits", wavelength_nm=1.2),
        _product("visible", file_name="hst_f606w_drc.fits", wavelength_nm=606.0),
    ]

    recipe = create_render_recipe(FitsRenderRequest(products=products, preselected=True))

    assert {product.id for product in recipe.source_products} == {"radio", "xray", "visible"}
    assert recipe.rgb_mapping.false_color is True
    assert recipe.rgb_mapping.blue.product_id == "xray"
    assert recipe.rgb_mapping.green.product_id == "visible"
    assert recipe.rgb_mapping.red.product_id == "radio"


def test_resolution_mismatch_adds_pixel_scale_caveat(tmp_path) -> None:
    sharp_path = tmp_path / "sharp_f356w_i2d.fits"
    coarse_path = tmp_path / "coarse_f444w_i2d.fits"
    _write_wcs_fits(sharp_path, shape=(128, 128), crpix=(64.5, 64.5), scale_arcsec=1.0)
    _write_wcs_fits(coarse_path, shape=(96, 96), crpix=(48.5, 48.5), scale_arcsec=8.0)
    renderer = FitsRenderer(
        dependencies=FitsRendererDependencies(
            astropy=True,
            numpy=True,
            pillow=True,
            reproject=True,
        ),
        cache_dir=tmp_path / "renders",
        allow_file_urls=True,
    )

    result = renderer.render(
        FitsRenderRequest(
            products=[
                _local_fits_product("sharp", sharp_path, wavelength_nm=3560),
                _local_fits_product("coarse", coarse_path, wavelength_nm=4440),
            ],
            width=128,
            height=128,
            preselected=True,
        )
    )

    assert result.recipe is not None
    assert any("resolutions differ" in caveat.lower() for caveat in result.recipe.caveats)


def test_tint_for_wavelength_follows_band_conventions() -> None:
    from astrolens.services.fits_renderer import tint_for_wavelength

    assert tint_for_wavelength(None) is None
    assert tint_for_wavelength(606.0) is None  # visible stays neutral

    def band(wavelength_nm: float) -> str:
        tint = tint_for_wavelength(wavelength_nm)
        assert tint is not None, wavelength_nm
        return tint[0]

    assert band(1.2) == "xray"
    assert band(230.0) == "ultraviolet"
    assert band(2200.0) == "infrared"
    assert band(1_382_000.0) == "millimeter"
    assert band(214_000_000.0) == "radio"
    assert band(0.001) == "gamma"


def _rendered_channel_means(tmp_path, wavelength_nm: float):
    import numpy as np
    from PIL import Image

    tmp_path.mkdir(parents=True, exist_ok=True)
    fits_path = tmp_path / f"single_{int(wavelength_nm * 1000)}_drz.fits"
    _write_wcs_fits(fits_path, shape=(96, 96), crpix=(48.5, 48.5))
    renderer = FitsRenderer(
        dependencies=FitsRendererDependencies(astropy=True, numpy=True, pillow=True),
        cache_dir=tmp_path / "renders",
        allow_file_urls=True,
    )
    result = renderer.render(
        FitsRenderRequest(
            products=[_local_fits_product("solo", fits_path, wavelength_nm=wavelength_nm)],
            width=96,
            height=96,
        )
    )
    assert result.status == "complete"
    assert result.file_path is not None
    with Image.open(result.file_path) as rendered:
        rgb = np.asarray(rendered.convert("RGB"), dtype=float)
    return result, rgb[:, :, 0].mean(), rgb[:, :, 1].mean(), rgb[:, :, 2].mean()


def test_single_band_renders_are_tinted_by_band(tmp_path) -> None:
    # Infrared leans warm (R > B); X-ray leans cool (B > R); visible stays gray.
    result_ir, red_ir, _g, blue_ir = _rendered_channel_means(tmp_path / "ir", 2200.0)
    assert red_ir > blue_ir * 1.1
    assert result_ir.recipe is not None
    assert any("infrared" in caveat for caveat in result_ir.recipe.caveats)

    result_x, red_x, _g, blue_x = _rendered_channel_means(tmp_path / "xray", 1.2)
    assert blue_x > red_x * 1.1
    assert result_x.recipe is not None
    assert any("xray" in caveat for caveat in result_x.recipe.caveats)

    result_v, red_v, green_v, blue_v = _rendered_channel_means(tmp_path / "vis", 606.0)
    assert abs(red_v - blue_v) < 2.0 and abs(green_v - blue_v) < 2.0
    assert result_v.recipe is not None
    assert not any("false-color tint" in caveat for caveat in result_v.recipe.caveats)


def test_cache_key_and_asset_id_are_stable_for_same_products_in_different_order() -> None:
    products = [
        _product("blue", file_name="hst_f438w_drc.fits", wavelength_nm=438),
        _product("green", file_name="hst_f606w_drc.fits", wavelength_nm=606),
        _product("red", file_name="hst_f814w_drc.fits", wavelength_nm=814),
    ]

    first = create_render_recipe(FitsRenderRequest(products=products))
    second = create_render_recipe(FitsRenderRequest(products=list(reversed(products))))

    assert first.cache_key == second.cache_key
    assert first.asset_id == second.asset_id


def test_cache_key_ignores_volatile_download_urls_for_same_source_record() -> None:
    """Generated cutout URLs change per request; the archive record id is stable."""

    base = _product("sdssr", file_name="skv_sdssr.fits", wavelength_nm=616)
    first_recipe = create_render_recipe(
        FitsRenderRequest(
            products=[
                base.model_copy(
                    update={"download_url": "https://skyview.gsfc.nasa.gov/tempspace/fits/skv111.fits"}
                )
            ]
        )
    )
    second_recipe = create_render_recipe(
        FitsRenderRequest(
            products=[
                base.model_copy(
                    update={"download_url": "https://skyview.gsfc.nasa.gov/tempspace/fits/skv222.fits"}
                )
            ]
        )
    )

    assert first_recipe.cache_key == second_recipe.cache_key
    assert first_recipe.asset_id == second_recipe.asset_id


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://mast.stsci.edu/x.fits",
        "https://169.254.169.254/latest/meta-data/x.fits",
        "https://evil.example.com/x.fits",
        "https://stsci.edu.evil.example/x.fits",
        "ftp://mast.stsci.edu/x.fits",
    ],
)
def test_validate_download_url_rejects_untrusted_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_download_url(
            url,
            product_id="p1",
            allowed_host_suffixes=DEFAULT_ALLOWED_URL_HOST_SUFFIXES,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://mast.stsci.edu/api/v0.1/Download/file?uri=x.fits",
        "https://skyview.gsfc.nasa.gov/tempspace/fits/skv1.fits",
        "https://archive.stsci.edu/pub/x.fits",
    ],
)
def test_validate_download_url_allows_trusted_archive_hosts(url: str) -> None:
    validate_download_url(
        url,
        product_id="p1",
        allowed_host_suffixes=DEFAULT_ALLOWED_URL_HOST_SUFFIXES,
    )


def test_render_refuses_untrusted_download_url(tmp_path) -> None:
    renderer = FitsRenderer(
        dependencies=FitsRendererDependencies(astropy=True, numpy=True, pillow=True),
        cache_dir=tmp_path / "renders",
    )

    result = renderer.render(
        FitsRenderRequest(
            products=[
                SourceFitsProduct(
                    id="hostile",
                    download_url="https://169.254.169.254/x.fits",
                    file_name="x.fits",
                    file_format="fits",
                    product_type="SCIENCE",
                    calibration_level=3,
                    file_size_mb=0.01,
                    wavelength_nm=606,
                    source_record_id="mast:TEST/product/x.fits",
                )
            ],
            width=64,
            height=64,
        )
    )

    assert result.status == "unsupported"
    assert result.error is not None and "not an allowed archive host" in result.error
    assert result.asset_url is None
    assert "file_path" not in result.model_dump(mode="json")
