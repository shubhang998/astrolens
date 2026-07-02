"""Minimal Anthropic Messages API client for interpretation and vision ranking.

Connector-style: fixed trusted host, urllib in a worker thread, stable error
mapping, zero new dependencies. Callers must treat the LLM as an
*interpretation* layer only — deterministic facts remain canonical, and every
numeric claim shown to users must originate from compiled facts (AGENTS.md).
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from astrolens.connectors.error_mapping import connector_error_from_exception
from astrolens.core.enums import ErrorCode
from astrolens.core.errors import AstroLensError

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
API_KEY_ENV = "ANTHROPIC_API_KEY"
MODEL_ENV = "ASTROLENS_LLM_MODEL"
DEFAULT_MODEL = "claude-sonnet-5"


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def image_url_block(url: str) -> dict[str, Any]:
    """Reference a public image by URL; Anthropic fetches it server-side."""

    return {"type": "image", "source": {"type": "url", "url": url}}


class AnthropicClient:
    """Small typed wrapper over the Messages API."""

    name = "Anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self.model = model or os.getenv(MODEL_ENV, "").strip() or DEFAULT_MODEL
        self.timeout_seconds = timeout_seconds

    @property
    def api_key(self) -> str | None:
        return self._api_key or os.getenv(API_KEY_ENV, "").strip() or None

    def available(self) -> bool:
        return self.api_key is not None

    async def complete(
        self,
        *,
        system: str,
        content: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> str:
        """Run one user message through the model and return the text reply."""

        return await asyncio.to_thread(
            self._complete_sync, system=system, content=content, max_tokens=max_tokens
        )

    def _complete_sync(
        self,
        *,
        system: str,
        content: list[dict[str, Any]],
        max_tokens: int,
    ) -> str:
        api_key = self.api_key
        if not api_key:
            raise AstroLensError(
                ErrorCode.SOURCE_UNAVAILABLE,
                "Anthropic API key is not configured (ANTHROPIC_API_KEY).",
                retryable=False,
                details={"source": self.name},
            )
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
        }
        request = Request(
            ANTHROPIC_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "User-Agent": "AstroLens/0.1 interpretation-layer",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(4_000_000)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise connector_error_from_exception(
                exc,
                source=self.name,
                message="Anthropic API request failed.",
            ) from exc
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AstroLensError(
                ErrorCode.SOURCE_UNAVAILABLE,
                "Anthropic API returned malformed JSON.",
                retryable=True,
                details={"source": self.name},
            ) from exc
        blocks = decoded.get("content") or []
        texts = [
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "".join(texts).strip()
        if not text:
            raise AstroLensError(
                ErrorCode.SOURCE_UNAVAILABLE,
                "Anthropic API returned no text content.",
                retryable=True,
                details={"source": self.name, "stop_reason": decoded.get("stop_reason")},
            )
        return text


anthropic_client = AnthropicClient()
