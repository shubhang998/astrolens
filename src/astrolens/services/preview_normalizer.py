"""Deterministic normalization of archive preview images (crop, de-tilt, tint).

MAST archive preview JPEGs are often hard to read as-is: a rotated detector
footprint floating diamond-wise on a flat background, off-center content, or
huge empty margins. This service crops previews to their content, straightens
verifiably rotated rectangular footprints, and applies the same
observatory-conventional single-band tint used by the FITS renderer. It never
invents pixels: brightness is always the archive preview's own data.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from pydantic import Field

from astrolens.core.models import AstroLensModel
from astrolens.services.fits_renderer import DEFAULT_RENDER_CACHE_DIR, tint_for_wavelength

# Included in the cache filename hash so future pipeline changes regenerate
# previously normalized previews instead of serving stale derivatives.
PREVIEW_NORMALIZER_VERSION = "preview-normalize:v1"

# Decoding is the memory hazard, not downloading (see preview_image_quality):
# JPEGs above this pixel count are draft-decoded at reduced scale; anything
# still oversized after draft is skipped rather than OOM-decoded.
MAX_DECODE_PIXELS = 8_000_000

# Pixels differing from the border-median background by more than this (max
# channel difference, 0..1 units) count as content.
_CONTENT_DIFF_THRESHOLD = 0.06
# Below this many content pixels, geometry estimates are noise: skip crop/tilt.
_MIN_CONTENT_PIXELS = 64
# If the content bounding box already spans nearly the whole frame, cropping
# would only shave meaningful margins from full-field images: skip it.
_FULL_FRAME_FRACTION = 0.96
# A content mask counts as a rotated rectangle only when it fills this much of
# its own minimum-area rectangle estimate. Ellipses top out near pi/4 (~0.79),
# so nebulae and irregular blobs are never "straightened".
_ROTATED_RECT_FILL_MIN = 0.85
_MIN_TILT_DEG = 3.0
# Mean max-channel difference below which an image is effectively grayscale
# and eligible for a single-band tint.
_GRAYSCALE_CHANNEL_DIFF_MAX = 0.02
# Cap the number of mask points used for angle estimation; deterministic
# striding keeps large masks cheap without changing results meaningfully.
_MAX_ANGLE_SAMPLE_POINTS = 50_000


@dataclass(frozen=True)
class NormalizedPreview:
    """A normalized preview image and a record of what was changed."""

    image_bytes: bytes
    width: int
    height: int
    cropped: bool
    rotated_deg: float | None
    tinted_band: str | None

    @property
    def changed(self) -> bool:
        """Whether normalization actually altered the preview."""

        return self.cropped or self.rotated_deg is not None or self.tinted_band is not None


class NormalizedResult(AstroLensModel):
    """A cached normalized preview served from the render cache directory."""

    asset_url: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    cropped: bool = False
    rotated_deg: float | None = None
    tinted_band: str | None = None


def normalize_preview_bytes(
    payload: bytes,
    *,
    wavelength_nm: float | None = None,
    out_max: int = 1024,
) -> NormalizedPreview | None:
    """Deterministically crop, de-tilt, and tint one preview image payload.

    Returns None when the payload cannot be decoded safely (unsupported
    format, corrupt data, or too many pixels to decode within memory bounds).
    """

    try:
        import numpy as np
        from PIL import Image
    except ImportError:  # pragma: no cover - dependency guard
        return None

    try:
        with Image.open(BytesIO(payload)) as image:
            if image.width * image.height > MAX_DECODE_PIXELS:
                # JPEG supports cheap reduced-scale decoding; draft() mutates
                # the effective decode size. Anything still oversized after
                # draft (e.g. giant PNGs) is skipped rather than OOM-decoded.
                image.draft("RGB", (out_max, out_max))
                if image.width * image.height > MAX_DECODE_PIXELS:
                    return None
            rgb = image.convert("RGB")
    except (Image.DecompressionBombError, OSError, ValueError, SyntaxError):
        return None
    rgb.thumbnail((out_max, out_max))
    array = np.asarray(rgb, dtype=np.float32) / 255.0
    if array.ndim != 3 or array.size == 0:
        return None

    background = _border_median_color(array)
    mask = _content_mask(array, background)

    cropped = False
    rotated_deg: float | None = None
    if int(np.count_nonzero(mask)) >= _MIN_CONTENT_PIXELS:
        bounds = _content_bounds(mask)
        if bounds is not None:
            y0, y1, x0, x1 = bounds
            array = array[y0:y1, x0:x1]
            mask = mask[y0:y1, x0:x1]
            cropped = True

        angle_deg = _rotated_rectangle_angle(mask)
        if angle_deg is not None:
            array = _rotate_with_background(array, angle_deg, background)
            mask = _content_mask(array, background)
            rotated_deg = round(angle_deg, 2)
            bounds = _content_bounds(mask)
            if bounds is not None:
                y0, y1, x0, x1 = bounds
                array = array[y0:y1, x0:x1]
                cropped = True

    tinted_band: str | None = None
    if wavelength_nm is not None and _is_effectively_grayscale(array):
        tint = tint_for_wavelength(wavelength_nm)
        if tint is not None:
            band_name, hue = tint
            array = _apply_duotone(array, hue)
            tinted_band = band_name

    output = Image.fromarray((np.clip(array, 0.0, 1.0) * 255.0).astype(np.uint8))
    output.thumbnail((out_max, out_max))
    buffer = BytesIO()
    output.save(buffer, format="PNG")
    return NormalizedPreview(
        image_bytes=buffer.getvalue(),
        width=output.width,
        height=output.height,
        cropped=cropped,
        rotated_deg=rotated_deg,
        tinted_band=tinted_band,
    )


class PreviewNormalizerService:
    """Fetch, normalize, and cache archive previews in the render cache dir.

    Normalized PNGs are written under the same directory `FitsRenderer` uses,
    so they persist on the deployed disk cache and are served by the existing
    `/v1/rendered/{filename}` route.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_bytes: int = 8_000_000,
        out_max: int = 1024,
        cache_dir: str | Path | None = None,
        public_base_url: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.out_max = out_max
        self.cache_dir = Path(
            cache_dir or os.getenv("ASTROLENS_RENDER_CACHE_DIR") or DEFAULT_RENDER_CACHE_DIR
        )
        self.public_base_url = public_base_url or os.getenv("ASTROLENS_PUBLIC_BASE_URL")
        # In-process memo so unchanged previews are not refetched per request.
        self.cache: dict[str, NormalizedResult | None] = {}

    def normalized_asset_url(
        self,
        url: str,
        *,
        wavelength_nm: float | None = None,
        cache_dir: str | Path | None = None,
        public_base: str | None = None,
    ) -> NormalizedResult | None:
        """Return a served URL for the normalized preview, or None to keep the original.

        None means normalization failed or changed nothing meaningful (no
        crop, no rotation, no tint), so callers should keep the archive URL.
        """

        resolved_cache_dir = Path(cache_dir) if cache_dir is not None else self.cache_dir
        resolved_base = public_base if public_base is not None else self.public_base_url
        filename = _normalized_filename(url, wavelength_nm=wavelength_nm)
        output_path = resolved_cache_dir / filename
        memo_key = f"{output_path}|{resolved_base or ''}"
        if memo_key in self.cache:
            return self.cache[memo_key]

        result = self._cached_result(output_path, resolved_base)
        if result is None:
            result = self._normalize_and_store(
                url,
                wavelength_nm=wavelength_nm,
                output_path=output_path,
                public_base=resolved_base,
            )
        self.cache[memo_key] = result
        return result

    def _cached_result(self, output_path: Path, public_base: str | None) -> NormalizedResult | None:
        if not output_path.exists():
            return None
        try:
            sidecar = json.loads(_sidecar_path(output_path).read_text(encoding="utf-8"))
            return NormalizedResult(
                asset_url=_served_asset_url(output_path.name, public_base),
                width=int(sidecar["width"]),
                height=int(sidecar["height"]),
                cropped=bool(sidecar["cropped"]),
                rotated_deg=(
                    float(sidecar["rotated_deg"])
                    if sidecar.get("rotated_deg") is not None
                    else None
                ),
                tinted_band=sidecar.get("tinted_band"),
            )
        except (OSError, ValueError, KeyError, TypeError):
            # Missing/corrupt sidecar: fall through and regenerate.
            return None

    def _normalize_and_store(
        self,
        url: str,
        *,
        wavelength_nm: float | None,
        output_path: Path,
        public_base: str | None,
    ) -> NormalizedResult | None:
        try:
            payload = self._fetch(url)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            return None
        preview = normalize_preview_bytes(
            payload,
            wavelength_nm=wavelength_nm,
            out_max=self.out_max,
        )
        if preview is None or not preview.changed:
            return None
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_bytes(output_path, preview.image_bytes)
            _sidecar_path(output_path).write_text(
                json.dumps(
                    {
                        "version": PREVIEW_NORMALIZER_VERSION,
                        "source_url": url,
                        "wavelength_nm": wavelength_nm,
                        "width": preview.width,
                        "height": preview.height,
                        "cropped": preview.cropped,
                        "rotated_deg": preview.rotated_deg,
                        "tinted_band": preview.tinted_band,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        except OSError:
            return None
        return NormalizedResult(
            asset_url=_served_asset_url(output_path.name, public_base),
            width=preview.width,
            height=preview.height,
            cropped=preview.cropped,
            rotated_deg=preview.rotated_deg,
            tinted_band=preview.tinted_band,
        )

    def _fetch(self, url: str) -> bytes:
        request = Request(
            url,
            headers={"User-Agent": "AstroLens/0.1 preview-normalize"},
            method="GET",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > self.max_bytes:
                raise ValueError(f"Preview image is larger than {self.max_bytes} bytes.")
            payload = response.read(self.max_bytes + 1)
        if len(payload) > self.max_bytes:
            raise ValueError(f"Preview image is larger than {self.max_bytes} bytes.")
        return payload


def _normalized_filename(url: str, *, wavelength_nm: float | None) -> str:
    digest = hashlib.sha256(
        f"{PREVIEW_NORMALIZER_VERSION}|{url}|{wavelength_nm}".encode()
    ).hexdigest()
    return f"prevnorm_{digest[:24]}.png"


def _sidecar_path(output_path: Path) -> Path:
    return output_path.with_suffix(f"{output_path.suffix}.norm.json")


def _served_asset_url(filename: str, public_base: str | None) -> str:
    path = f"/v1/rendered/{quote(filename)}"
    if not public_base:
        return path
    return f"{public_base.rstrip('/')}{path}"


def _atomic_write_bytes(output_path: Path, payload: bytes) -> None:
    temp_path = output_path.parent / f"{output_path.name}.{uuid4().hex}.tmp"
    temp_path.write_bytes(payload)
    os.replace(temp_path, output_path)


def _border_median_color(array: Any) -> Any:
    import numpy as np

    height, width = array.shape[:2]
    border = max(2, min(height, width) // 100)
    strips = np.concatenate(
        [
            array[:border].reshape(-1, 3),
            array[-border:].reshape(-1, 3),
            array[:, :border].reshape(-1, 3),
            array[:, -border:].reshape(-1, 3),
        ]
    )
    return np.median(strips, axis=0)


def _content_mask(array: Any, background: Any) -> Any:
    import numpy as np

    difference = np.max(np.abs(array - background[None, None, :]), axis=2)
    mask = difference > _CONTENT_DIFF_THRESHOLD
    # Morphological opening (3x3 erode then dilate) removes isolated noise
    # pixels so compression speckle never widens the content bounding box.
    return _dilate3(_erode3(mask))


def _erode3(mask: Any) -> Any:
    import numpy as np

    height, width = mask.shape
    padded = np.pad(mask, 1, mode="edge")
    output = np.ones_like(mask, dtype=bool)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            output &= padded[dy : dy + height, dx : dx + width]
    return output


def _dilate3(mask: Any) -> Any:
    import numpy as np

    height, width = mask.shape
    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    output = np.zeros_like(mask, dtype=bool)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            output |= padded[dy : dy + height, dx : dx + width]
    return output


def _content_bounds(mask: Any) -> tuple[int, int, int, int] | None:
    """Content bbox with a small margin, or None when cropping is pointless."""

    import numpy as np

    ys, xs = np.nonzero(mask)
    if ys.size < _MIN_CONTENT_PIXELS:
        return None
    height, width = mask.shape
    margin_y = max(2, int(height * 0.02))
    margin_x = max(2, int(width * 0.02))
    y0 = max(0, int(ys.min()) - margin_y)
    y1 = min(height, int(ys.max()) + 1 + margin_y)
    x0 = max(0, int(xs.min()) - margin_x)
    x1 = min(width, int(xs.max()) + 1 + margin_x)
    if (y1 - y0) >= _FULL_FRAME_FRACTION * height and (x1 - x0) >= _FULL_FRAME_FRACTION * width:
        return None
    return y0, y1, x0, x1


def _rotated_rectangle_angle(mask: Any) -> float | None:
    """Tilt angle (degrees) when the mask is verifiably a rotated rectangle.

    Estimates the principal-axis angle from second-order image moments and
    accepts it only when the mask fills most of its own minimum-area rectangle
    at that angle. Squares rotated ~45 degrees have isotropic second moments,
    so a small deterministic angle sweep backs up the moment estimate. Returns
    None for axis-aligned or irregular content (never rotate a nebula).
    """

    import numpy as np

    ys, xs = np.nonzero(mask)
    if ys.size < _MIN_CONTENT_PIXELS:
        return None
    stride = max(1, ys.size // _MAX_ANGLE_SAMPLE_POINTS)
    x = xs[::stride].astype(np.float64)
    y = ys[::stride].astype(np.float64)

    mu20 = float(np.mean((x - x.mean()) ** 2))
    mu02 = float(np.mean((y - y.mean()) ** 2))
    mu11 = float(np.mean((x - x.mean()) * (y - y.mean())))
    moment_angle = _normalized_angle_deg(math.degrees(0.5 * math.atan2(2.0 * mu11, mu20 - mu02)))
    if (
        _MIN_TILT_DEG < abs(moment_angle) < 90.0 - _MIN_TILT_DEG
        and _rectangle_fill_ratio(x, y, moment_angle, stride) >= _ROTATED_RECT_FILL_MIN
    ):
        return moment_angle

    best_angle = 0.0
    best_fill = 0.0
    for candidate in range(-44, 46):
        fill = _rectangle_fill_ratio(x, y, float(candidate), stride)
        if fill > best_fill:
            best_fill = fill
            best_angle = float(candidate)
    if best_fill >= _ROTATED_RECT_FILL_MIN and abs(best_angle) > _MIN_TILT_DEG:
        return best_angle
    return None


def _normalized_angle_deg(angle_deg: float) -> float:
    """Fold an orientation into (-45, 45]: the minimal equivalent rotation."""

    while angle_deg > 45.0:
        angle_deg -= 90.0
    while angle_deg <= -45.0:
        angle_deg += 90.0
    return angle_deg


def _rectangle_fill_ratio(x: Any, y: Any, angle_deg: float, stride: int) -> float:
    """How much of its axis-aligned bbox (after undoing angle) the mask fills."""

    import numpy as np

    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    x_rotated = (x * cos_t) + (y * sin_t)
    y_rotated = (y * cos_t) - (x * sin_t)
    width = float(np.max(x_rotated) - np.min(x_rotated)) + 1.0
    height = float(np.max(y_rotated) - np.min(y_rotated)) + 1.0
    return (float(x.size) * stride) / (width * height)


def _rotate_with_background(array: Any, angle_deg: float, background: Any) -> Any:
    """Rotate the image by angle_deg (counterclockwise), filling with background."""

    import numpy as np
    from PIL import Image

    image = Image.fromarray((np.clip(array, 0.0, 1.0) * 255.0).astype(np.uint8))
    fill = tuple(int(round(float(channel) * 255.0)) for channel in background)
    rotated = image.rotate(
        angle_deg,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=fill,
    )
    return np.asarray(rotated, dtype=np.float32) / 255.0


def _is_effectively_grayscale(array: Any) -> bool:
    import numpy as np

    channel_spread = np.max(array, axis=2) - np.min(array, axis=2)
    return float(np.mean(channel_spread)) < _GRAYSCALE_CHANNEL_DIFF_MAX


def _apply_duotone(array: Any, hue: tuple[float, float, float]) -> Any:
    """Map grayscale intensity through the renderer's black -> hue -> white duotone."""

    import numpy as np

    intensity = np.mean(array, axis=2)
    tinted = np.empty_like(array)
    for channel_index in range(3):
        tinted[:, :, channel_index] = np.interp(
            intensity,
            [0.0, 0.55, 1.0],
            [0.0, hue[channel_index] * 0.85, 1.0],
        )
    return tinted


preview_normalizer_service = PreviewNormalizerService()

__all__ = [
    "MAX_DECODE_PIXELS",
    "PREVIEW_NORMALIZER_VERSION",
    "NormalizedPreview",
    "NormalizedResult",
    "PreviewNormalizerService",
    "normalize_preview_bytes",
    "preview_normalizer_service",
]
