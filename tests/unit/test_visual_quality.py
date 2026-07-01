from astrolens.services.visual_quality import (
    VisualQualityTier,
    assess_visual_quality,
    choose_preferred_visual_product,
)


def test_visual_quality_tier_ladder_matches_production_expectations() -> None:
    assert VisualQualityTier.OUTREACH_RELEASE > VisualQualityTier.ASTROLENS_RENDERED
    assert VisualQualityTier.ASTROLENS_RENDERED > VisualQualityTier.HLA_HLSP_HAP_COLOR_COMPOSITE
    assert (
        VisualQualityTier.HLA_HLSP_HAP_COLOR_COMPOSITE > VisualQualityTier.PROCESSED_ARCHIVE_PRODUCT
    )
    assert VisualQualityTier.PROCESSED_ARCHIVE_PRODUCT > VisualQualityTier.RAW_PREVIEW


def test_classifies_product_tiers_from_filename_project_and_description() -> None:
    outreach = assess_visual_quality(
        product_filename="opo0328a.jpg",
        project="Hubble Heritage",
        description="STScI image release color composite",
        product_type="PREVIEW",
        file_format="jpg",
    )
    rendered = assess_visual_quality(
        product_filename="m87_astrolens_rendered_visible.png",
        project="AstroLens",
        description="Rendered science-ready PNG from calibrated FITS products",
        file_format="png",
    )
    hap_color = assess_visual_quality(
        product_filename="hst_17902_02_wfc3_uvis_total_ifjp02_drc_color.jpg",
        project="HAP-SVM",
        description="Preview-Full",
        product_type="PREVIEW",
        file_format="jpg",
        calibration_level="3",
    )
    processed = assess_visual_quality(
        product_filename="jw02736-o003_t002_nircam_clear-f444w_i2d.fits",
        project="CALJWST",
        description="Level 3 calibrated mosaic product",
        product_type="SCIENCE",
        file_format="fits",
        calibration_level="3",
    )
    raw_preview = assess_visual_quality(
        product_filename="jw02736-o003_t002_nircam_clear-f444w_uncal.jpg",
        project="CALJWST",
        description="Preview-Full",
        product_type="PREVIEW",
        file_format="jpg",
    )

    assert outreach.tier == VisualQualityTier.OUTREACH_RELEASE
    assert rendered.tier == VisualQualityTier.ASTROLENS_RENDERED
    assert hap_color.tier == VisualQualityTier.HLA_HLSP_HAP_COLOR_COMPOSITE
    assert processed.tier == VisualQualityTier.PROCESSED_ARCHIVE_PRODUCT
    assert raw_preview.tier == VisualQualityTier.RAW_PREVIEW


def test_hap_drc_color_is_preferred_over_jwst_single_filter_detector_preview() -> None:
    hap_color = {
        "product_filename": "hst_17902_02_wfc3_uvis_total_ifjp02_drc_color.jpg",
        "project": "HAP-SVM",
        "description": "Preview-Full",
        "product_type": "PREVIEW",
        "file_format": "jpg",
        "calibration_level": "3",
        "raw_metadata": {
            "productFilename": "hst_17902_02_wfc3_uvis_total_ifjp02_drc_color.jpg",
            "project": "HAP-SVM",
            "description": "Preview-Full",
        },
    }
    jwst_single_filter = {
        "product_filename": "jw03055-o007_t007_nircam_clear-f277w_i2d.jpg",
        "project": "CALJWST",
        "description": "Preview-Full",
        "product_type": "PREVIEW",
        "file_format": "jpg",
        "calibration_level": "3",
        "raw_metadata": {
            "productFilename": "jw03055-o007_t007_nircam_clear-f277w_i2d.jpg",
            "project": "CALJWST",
            "description": "Preview-Full",
        },
    }

    hap_assessment = assess_visual_quality(hap_color)
    jwst_assessment = assess_visual_quality(jwst_single_filter)

    assert hap_assessment.tier == VisualQualityTier.HLA_HLSP_HAP_COLOR_COMPOSITE
    assert hap_assessment.provenance_label == "HLA/HLSP/HAP color composite"
    assert "jwst_single_filter_preview" in jwst_assessment.penalties
    assert "detector_panel_preview" in jwst_assessment.penalties
    assert hap_assessment.score > jwst_assessment.score
    assert choose_preferred_visual_product([jwst_single_filter, hap_color]) == hap_color
