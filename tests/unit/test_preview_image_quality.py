from io import BytesIO

from PIL import Image, ImageDraw

from astrolens.services.preview_image_quality import assess_preview_image_bytes


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_preview_quality_scores_centered_signal_above_flat_black_image() -> None:
    clean = Image.new("RGB", (500, 500), "black")
    draw = ImageDraw.Draw(clean)
    for radius, value in [(105, 45), (70, 90), (38, 150), (15, 245)]:
        color = (value, value, min(255, value + 20))
        draw.ellipse((250 - radius, 250 - radius, 250 + radius, 250 + radius), fill=color)
    flat = Image.new("RGB", (500, 500), (2, 2, 2))

    clean_quality = assess_preview_image_bytes(_png_bytes(clean))
    flat_quality = assess_preview_image_bytes(_png_bytes(flat))

    assert clean_quality.status == "ok"
    assert clean_quality.score > 0.75
    assert "centered_signal" in clean_quality.reasons
    assert flat_quality.score < 0.35
    assert "mostly_black" in flat_quality.penalties


def test_preview_quality_penalizes_detector_panel_gaps() -> None:
    panel = Image.new("RGB", (500, 500), "black")
    draw = ImageDraw.Draw(panel)
    draw.rectangle((0, 0, 500, 24), fill="white")
    draw.rectangle((0, 240, 500, 260), fill="white")
    draw.rectangle((245, 0, 265, 500), fill="white")
    draw.ellipse((150, 150, 240, 240), fill=(190, 190, 210))

    quality = assess_preview_image_bytes(_png_bytes(panel))

    assert quality.score < 0.70
    assert "detector_panel_gaps" in quality.penalties
