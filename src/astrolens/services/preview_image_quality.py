"""Pixel-level quality scoring for renderable archive preview images."""

from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import Field

from astrolens.core.models import AstroLensModel

PreviewQualityStatus = Literal["ok", "unsupported", "failed"]

# Decoding is the memory hazard, not downloading: an 8MB JPEG of a large
# mosaic can decode to hundreds of MB of RGB pixels. JPEGs above this pixel
# count are draft-decoded at reduced scale; other formats are skipped.
MAX_DECODE_PIXELS = 8_000_000


class PreviewImageQuality(AstroLensModel):
    """Compact quality analysis for one JPG/PNG preview image."""

    status: PreviewQualityStatus
    score: float = Field(ge=0.0, le=1.0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    contrast_std: float | None = Field(default=None, ge=0.0)
    dark_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    bright_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    detector_gap_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    central_signal_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)
    error: str | None = None


class PreviewImageQualityAnalyzer:
    """Fetch and score image previews using small, deterministic pixel heuristics."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_bytes: int = 8_000_000,
        resize_max: int = 256,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.resize_max = resize_max
        self.cache: dict[str, PreviewImageQuality] = {}

    def assess_url(self, url: str) -> PreviewImageQuality:
        """Fetch and score a preview URL, returning a graceful failed result on errors."""

        cached = self.cache.get(url)
        if cached:
            return cached
        try:
            payload = self._fetch(url)
            quality = assess_preview_image_bytes(payload, resize_max=self.resize_max)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            quality = PreviewImageQuality(status="failed", score=0.0, error=str(exc))
        self.cache[url] = quality
        return quality

    def _fetch(self, url: str) -> bytes:
        request = Request(
            url,
            headers={"User-Agent": "AstroLens/0.1 preview-quality"},
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


def assess_preview_image_bytes(
    payload: bytes,
    *,
    resize_max: int = 256,
) -> PreviewImageQuality:
    """Score an image payload for gallery usefulness, independent of source metadata."""

    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency guard
        return PreviewImageQuality(status="unsupported", score=0.0, error=str(exc))

    with Image.open(BytesIO(payload)) as image:
        width, height = image.size
        if width * height > MAX_DECODE_PIXELS:
            # JPEG supports cheap reduced-scale decoding; draft() mutates the
            # effective decode size. Anything still oversized after draft
            # (e.g. giant PNGs) is skipped rather than OOM-decoded.
            image.draft("RGB", (resize_max, resize_max))
            effective_width, effective_height = image.size
            if effective_width * effective_height > MAX_DECODE_PIXELS:
                return PreviewImageQuality(
                    status="unsupported",
                    score=0.5,
                    width=width,
                    height=height,
                    error=(
                        f"Preview is {width}x{height}; too large to decode "
                        "safely for pixel scoring."
                    ),
                )
        rgb = image.convert("RGB")
        rgb.thumbnail((resize_max, resize_max))
        array = np.asarray(rgb, dtype=np.float32) / 255.0

    if array.size == 0:
        return PreviewImageQuality(status="failed", score=0.0, error="Image has no pixels.")

    luminance = (
        (array[:, :, 0] * 0.2126)
        + (array[:, :, 1] * 0.7152)
        + (array[:, :, 2] * 0.0722)
    )
    contrast_std = float(np.std(luminance))
    dark_fraction = float(np.mean(luminance < 0.025))
    bright_mask = luminance > 0.965
    bright_fraction = float(np.mean(bright_mask))
    p50 = float(np.percentile(luminance, 50))
    p90 = float(np.percentile(luminance, 90))
    p99 = float(np.percentile(luminance, 99))

    hard_blank_mask = (luminance < 0.004) | (luminance > 0.985)
    row_gap_fraction = _internal_blank_run_fraction(np.mean(hard_blank_mask, axis=1) > 0.92)
    col_gap_fraction = _internal_blank_run_fraction(np.mean(hard_blank_mask, axis=0) > 0.92)
    detector_gap_fraction = max(row_gap_fraction, col_gap_fraction)

    signal_threshold = min(max(p50 + max(contrast_std, 0.04), 0.08), 0.78)
    signal_mask = luminance > signal_threshold
    signal_fraction = float(np.mean(signal_mask))
    central_signal_fraction = _central_signal_fraction(signal_mask)

    score = 0.72
    reasons: list[str] = []
    penalties: list[str] = []

    if contrast_std >= 0.12:
        score += 0.12
        reasons.append("good_contrast")
    elif contrast_std < 0.025:
        score -= 0.38
        penalties.append("nearly_flat")
    elif contrast_std < 0.06:
        score -= 0.16
        penalties.append("low_contrast")

    if p99 < 0.09:
        score -= 0.34
        penalties.append("mostly_black")
    elif p90 > 0.18:
        reasons.append("visible_signal")

    if bright_fraction > 0.18:
        score -= 0.22
        penalties.append("large_bright_gaps")
    elif bright_fraction > 0.08:
        score -= 0.12
        penalties.append("bright_gaps")

    if detector_gap_fraction > 0.08:
        score -= 0.30
        penalties.append("detector_panel_gaps")
    elif detector_gap_fraction > 0.035:
        score -= 0.12
        penalties.append("visible_detector_seams")

    if signal_fraction < 0.01 and dark_fraction > 0.88:
        score -= 0.14
        penalties.append("tiny_or_missing_subject")

    if central_signal_fraction >= 0.22:
        score += 0.08
        reasons.append("centered_signal")
    elif signal_fraction >= 0.015 and central_signal_fraction < 0.08:
        score -= 0.10
        penalties.append("off_center_signal")

    if min(width, height) < 300:
        score -= 0.06
        penalties.append("small_preview")

    return PreviewImageQuality(
        status="ok",
        score=max(0.0, min(1.0, score)),
        width=width,
        height=height,
        contrast_std=contrast_std,
        dark_fraction=dark_fraction,
        bright_fraction=bright_fraction,
        detector_gap_fraction=detector_gap_fraction,
        central_signal_fraction=central_signal_fraction,
        reasons=reasons,
        penalties=penalties,
    )


def _central_signal_fraction(signal_mask: object) -> float:
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - dependency guard
        return 0.0

    mask = np.asarray(signal_mask)
    if mask.size == 0 or not bool(np.any(mask)):
        return 0.0
    height, width = mask.shape
    y0 = int(height * 0.30)
    y1 = max(y0 + 1, int(height * 0.70))
    x0 = int(width * 0.30)
    x1 = max(x0 + 1, int(width * 0.70))
    return float(np.sum(mask[y0:y1, x0:x1]) / np.sum(mask))


def _internal_blank_run_fraction(flags: Iterable[object]) -> float:
    sequence = [bool(value) for value in flags]
    while sequence and sequence[0]:
        sequence.pop(0)
    while sequence and sequence[-1]:
        sequence.pop()
    if not sequence:
        return 0.0
    longest = 0
    current = 0
    for value in sequence:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest / len(sequence)


preview_image_quality_analyzer = PreviewImageQualityAnalyzer()
