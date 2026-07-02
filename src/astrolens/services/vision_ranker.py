"""LLM vision ranking for showcase image selection.

The ranker is an *interpretation* layer (AGENTS.md): it only reorders the
deterministically ranked candidate views, never invents facts or assets. Every
verdict is cached on disk so each rendered image is judged at most once, and
every failure degrades to the deterministic order by returning no scores.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from astrolens.connectors.anthropic_llm import (
    AnthropicClient,
    anthropic_client,
    image_url_block,
    text_block,
)
from astrolens.core.models import View

logger = logging.getLogger(__name__)

VERDICT_VERSION = 1
VISION_CACHE_ENV = "ASTROLENS_VISION_CACHE_DIR"

_SYSTEM_PROMPT = (
    "You are an image quality judge for an astronomy evidence gallery. "
    "You score candidate images strictly on visual merit and reply with JSON only."
)


def interpretation_cache_dir(subdir: str, *, env_override: str | None = None) -> Path:
    """Resolve the on-disk cache directory for an interpretation-layer service.

    Prefers an explicit env override, then a sibling of the render cache
    (``$ASTROLENS_RENDER_CACHE_DIR/../<subdir>``), then the local default.
    """

    if env_override:
        override = os.getenv(env_override, "").strip()
        if override:
            return Path(override)
    render_dir = os.getenv("ASTROLENS_RENDER_CACHE_DIR", "").strip()
    if render_dir:
        return Path(render_dir).parent / subdir
    return Path(".astrolens-cache") / subdir


class VisionRankerService:
    """Scores candidate views with one vision call, backed by a verdict cache."""

    def __init__(
        self,
        client: AnthropicClient = anthropic_client,
        *,
        cache_dir: str | Path | None = None,
        public_base_url: str | None = None,
    ) -> None:
        self.client = client
        self.cache_dir = Path(
            cache_dir
            if cache_dir is not None
            else interpretation_cache_dir("vision-verdicts", env_override=VISION_CACHE_ENV)
        )
        self.public_base_url = public_base_url or os.getenv("ASTROLENS_PUBLIC_BASE_URL")

    async def rank_views(self, obj_name: str, views: list[View]) -> dict[str, float]:
        """Map ``view.id`` to a 0..1 quality score; empty dict means "no opinion"."""

        try:
            return await self._rank_views(obj_name, views)
        except Exception:  # noqa: BLE001 - interpretation must never break the request
            logger.warning("Vision ranking failed; using deterministic order.", exc_info=True)
            return {}

    async def _rank_views(self, obj_name: str, views: list[View]) -> dict[str, float]:
        candidates: list[tuple[View, str]] = []
        seen_urls: set[str] = set()
        for view in views:
            url = self._absolute_https_url(_view_image_url(view))
            if url is None or url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append((view, url))
        if not candidates:
            return {}

        scores: dict[str, float] = {}
        uncached: list[tuple[View, str]] = []
        for view, url in candidates:
            verdict = self._load_verdict(url)
            if verdict is not None:
                scores[view.id] = verdict["score"]
            else:
                uncached.append((view, url))
        if not uncached:
            return scores

        reply = await self.client.complete(
            system=_SYSTEM_PROMPT,
            content=self._prompt_content(obj_name, [url for _, url in uncached]),
            max_tokens=1024,
        )
        for index, score, reason in _parse_verdicts(reply, count=len(uncached)):
            view, url = uncached[index - 1]
            scores[view.id] = score
            self._store_verdict(url, score=score, reasons=[reason] if reason else [])
        return scores

    def _prompt_content(self, obj_name: str, urls: list[str]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        for number, url in enumerate(urls, start=1):
            content.append(text_block(f"Image {number}:"))
            content.append(image_url_block(url))
        content.append(
            text_block(
                f"Score each numbered image from 0 to 100 as a good, informative, "
                f"aesthetically pleasing image of {obj_name}. Penalize blank or "
                "near-empty frames, heavy pixelation or blockiness, off-center "
                "subjects, tilted frames on plain backgrounds, and pure noise. "
                "Reply with STRICT JSON only: an array like "
                '[{"index": 1, "score": 85, "reason": "..."}] with one entry per '
                "image and nothing else."
            )
        )
        return content

    def _absolute_https_url(self, url: str | None) -> str | None:
        """Absolutize a possibly relative asset URL; only https URLs are usable."""

        if not url:
            return None
        if url.startswith("https://"):
            return url
        if url.startswith("/") and self.public_base_url:
            absolute = urljoin(self.public_base_url, url)
            if absolute.startswith("https://"):
                return absolute
        return None

    # -- verdict cache -----------------------------------------------------

    def _verdict_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _load_verdict(self, url: str) -> dict[str, Any] | None:
        path = self._verdict_path(url)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(raw, dict) or raw.get("version") != VERDICT_VERSION:
            return None
        score = raw.get("score")
        if not isinstance(score, int | float):
            return None
        return {**raw, "score": _clamp01(float(score))}

    def _store_verdict(self, url: str, *, score: float, reasons: list[str]) -> None:
        verdict = {
            "score": score,
            "reasons": reasons,
            "model": self.client.model,
            "version": VERDICT_VERSION,
        }
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._verdict_path(url).write_text(json.dumps(verdict), encoding="utf-8")
        except OSError:
            logger.warning("Could not persist vision verdict cache entry.", exc_info=True)


def _view_image_url(view: View) -> str | None:
    if view.asset is None:
        return None
    return view.asset.asset_url or view.asset.thumbnail_url


def _parse_verdicts(reply: str, *, count: int) -> list[tuple[int, float, str]]:
    """Extract ``(index, score01, reason)`` rows from a model reply, defensively."""

    items = _first_json_array(reply)
    verdicts: list[tuple[int, float, str]] = []
    seen: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        score = item.get("score")
        if not isinstance(index, int) or not isinstance(score, int | float):
            continue
        if index < 1 or index > count or index in seen:
            continue
        seen.add(index)
        reason = item.get("reason")
        verdicts.append(
            (index, _clamp01(float(score) / 100.0), reason if isinstance(reason, str) else "")
        )
    return verdicts


def _first_json_array(reply: str) -> list[Any]:
    """Return the first parseable JSON array embedded anywhere in the reply."""

    start = reply.find("[")
    while start != -1:
        depth = 0
        for end in range(start, len(reply)):
            char = reply[end]
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(reply[start : end + 1])
                    except json.JSONDecodeError:
                        break
                    return parsed if isinstance(parsed, list) else []
        start = reply.find("[", start + 1)
    return []


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


vision_ranker_service = VisionRankerService()
