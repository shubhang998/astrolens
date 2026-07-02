from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from astrolens.services.preview_normalizer import (
    NormalizedResult,
    PreviewNormalizerService,
    normalize_preview_bytes,
)


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _tilted_rectangle_on_white(angle_deg: float = 30.0) -> bytes:
    """A gray detector-footprint rectangle floating tilted on white."""

    canvas = Image.new("RGB", (400, 400), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((90, 140, 310, 260), fill=(110, 110, 110))
    tilted = canvas.rotate(angle_deg, resample=Image.Resampling.BICUBIC, fillcolor="white")
    return _png_bytes(tilted)


def _diamond_on_white() -> bytes:
    """A square footprint rotated 45 degrees: the classic diamond preview."""

    canvas = Image.new("RGB", (400, 400), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((120, 120, 280, 280), fill=(110, 110, 110))
    return _png_bytes(canvas.rotate(45, resample=Image.Resampling.BICUBIC, fillcolor="white"))


def _tilted_blob_on_black() -> bytes:
    """An elongated irregular nebula-like blob that must never be rotated."""

    canvas = Image.new("RGB", (400, 400), "black")
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((100, 160, 300, 240), fill=(180, 180, 180))
    draw.ellipse((160, 140, 240, 260), fill=(140, 140, 140))
    return _png_bytes(canvas.rotate(30, resample=Image.Resampling.BICUBIC, fillcolor="black"))


def _grayscale_gradient(size: int = 300) -> bytes:
    """Full-frame grayscale content: nothing to crop, tint-eligible."""

    row = np.linspace(0.0, 255.0, size, dtype=np.float32)
    array = np.repeat(row[None, :], size, axis=0).astype(np.uint8)
    return _png_bytes(Image.fromarray(array).convert("RGB"))


def _color_gradient(size: int = 300) -> bytes:
    row = np.linspace(0.0, 255.0, size, dtype=np.float32)
    red = np.repeat(row[None, :], size, axis=0)
    blue = np.repeat(row[::-1][None, :], size, axis=0)
    green = np.full((size, size), 96.0, dtype=np.float32)
    array = np.stack([red, green, blue], axis=2).astype(np.uint8)
    return _png_bytes(Image.fromarray(array))


def _content_fill_of_bbox(payload: bytes) -> float:
    """How rectangular/axis-aligned the content is in a normalized output."""

    with Image.open(BytesIO(payload)) as image:
        array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    background = np.median(
        np.concatenate(
            [
                array[:2].reshape(-1, 3),
                array[-2:].reshape(-1, 3),
                array[:, :2].reshape(-1, 3),
                array[:, -2:].reshape(-1, 3),
            ]
        ),
        axis=0,
    )
    mask = np.max(np.abs(array - background[None, None, :]), axis=2) > 0.06
    ys, xs = np.nonzero(mask)
    bbox_area = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
    return float(mask.sum()) / float(bbox_area)


def test_tilted_rectangle_is_detilted_and_cropped() -> None:
    result = normalize_preview_bytes(_tilted_rectangle_on_white())

    assert result is not None
    assert result.cropped is True
    assert result.rotated_deg is not None
    assert abs(abs(result.rotated_deg) - 30.0) < 3.0
    # Output is tighter than the 400x400 source frame.
    assert result.width < 400 and result.height < 400
    # After de-tilting, the footprint fills its own bounding box again.
    assert _content_fill_of_bbox(result.image_bytes) > 0.85


def test_diamond_square_footprint_is_straightened() -> None:
    result = normalize_preview_bytes(_diamond_on_white())

    assert result is not None
    assert result.rotated_deg is not None
    assert abs(abs(result.rotated_deg) - 45.0) < 3.0
    assert _content_fill_of_bbox(result.image_bytes) > 0.85


def test_irregular_blob_is_cropped_but_never_rotated() -> None:
    result = normalize_preview_bytes(_tilted_blob_on_black())

    assert result is not None
    assert result.cropped is True
    assert result.rotated_deg is None


def test_grayscale_infrared_preview_gets_warm_band_tint() -> None:
    result = normalize_preview_bytes(_grayscale_gradient(), wavelength_nm=2200.0)

    assert result is not None
    assert result.tinted_band == "infrared"
    assert result.cropped is False and result.rotated_deg is None
    with Image.open(BytesIO(result.image_bytes)) as image:
        array = np.asarray(image.convert("RGB"), dtype=np.float32)
    # Infrared duotone is warm: red channel dominates blue in the midtones.
    assert float(array[:, :, 0].mean()) > float(array[:, :, 2].mean()) + 10.0


def test_color_preview_is_never_tinted() -> None:
    result = normalize_preview_bytes(_color_gradient(), wavelength_nm=2200.0)

    assert result is not None
    assert result.tinted_band is None


def test_visible_or_unknown_band_gets_no_tint() -> None:
    assert normalize_preview_bytes(_grayscale_gradient(), wavelength_nm=551.0) is not None
    for wavelength_nm in (551.0, None):
        result = normalize_preview_bytes(_grayscale_gradient(), wavelength_nm=wavelength_nm)
        assert result is not None
        assert result.tinted_band is None
        assert result.changed is False


def test_oversized_image_is_skipped_before_decode() -> None:
    huge = Image.new("RGB", (3000, 3000), "white")

    assert normalize_preview_bytes(_png_bytes(huge)) is None


def test_undecodable_payload_returns_none() -> None:
    assert normalize_preview_bytes(b"not an image at all") is None


def test_normalization_is_deterministic() -> None:
    payload = _tilted_rectangle_on_white()

    first = normalize_preview_bytes(payload)
    second = normalize_preview_bytes(payload)

    assert first is not None and second is not None
    assert first.image_bytes == second.image_bytes
    assert first.rotated_deg == second.rotated_deg


class FakeFetchNormalizer(PreviewNormalizerService):
    def __init__(self, payload: bytes, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.payload = payload
        self.fetch_calls: list[str] = []

    def _fetch(self, url: str) -> bytes:
        self.fetch_calls.append(url)
        return self.payload


def test_service_writes_normalized_png_into_render_cache_dir(tmp_path: Path) -> None:
    service = FakeFetchNormalizer(_tilted_rectangle_on_white(), cache_dir=tmp_path)

    result = service.normalized_asset_url(
        "https://mast.example.test/preview.jpg",
        wavelength_nm=None,
    )

    assert isinstance(result, NormalizedResult)
    assert result.asset_url.startswith("/v1/rendered/prevnorm_")
    assert result.asset_url.endswith(".png")
    assert result.cropped is True and result.rotated_deg is not None
    filename = result.asset_url.rsplit("/", maxsplit=1)[-1]
    assert (tmp_path / filename).exists()
    assert (tmp_path / f"{filename}.norm.json").exists()
    assert service.fetch_calls == ["https://mast.example.test/preview.jpg"]


def test_service_serves_disk_cache_hits_without_refetching(tmp_path: Path) -> None:
    payload = _tilted_rectangle_on_white()
    first_service = FakeFetchNormalizer(payload, cache_dir=tmp_path)
    first = first_service.normalized_asset_url("https://mast.example.test/preview.jpg")
    assert first is not None

    second_service = FakeFetchNormalizer(payload, cache_dir=tmp_path)
    second = second_service.normalized_asset_url("https://mast.example.test/preview.jpg")

    assert second_service.fetch_calls == []
    assert second == first
    # The in-process memo also short-circuits repeat calls.
    first_service.normalized_asset_url("https://mast.example.test/preview.jpg")
    assert first_service.fetch_calls == ["https://mast.example.test/preview.jpg"]


def test_service_returns_none_when_nothing_meaningful_changed(tmp_path: Path) -> None:
    service = FakeFetchNormalizer(_color_gradient(), cache_dir=tmp_path)

    result = service.normalized_asset_url("https://mast.example.test/fullframe.jpg")

    assert result is None
    assert list(tmp_path.iterdir()) == []


def test_service_prefixes_public_base_url(tmp_path: Path) -> None:
    service = FakeFetchNormalizer(
        _tilted_rectangle_on_white(),
        cache_dir=tmp_path,
        public_base_url="https://astrolens.example.test/",
    )

    result = service.normalized_asset_url("https://mast.example.test/preview.jpg")

    assert result is not None
    assert result.asset_url.startswith("https://astrolens.example.test/v1/rendered/prevnorm_")


def test_service_filenames_are_deterministic_and_version_scoped(tmp_path: Path) -> None:
    payload = _tilted_rectangle_on_white()
    service = FakeFetchNormalizer(payload, cache_dir=tmp_path)

    first = service.normalized_asset_url("https://mast.example.test/a.jpg")
    other = service.normalized_asset_url("https://mast.example.test/b.jpg")

    assert first is not None and other is not None
    assert first.asset_url != other.asset_url
