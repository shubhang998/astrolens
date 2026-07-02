import asyncio
from pathlib import Path
from typing import Any

import pytest

from astrolens.core.enums import BandFamily, ErrorCode, VisualAssetTier
from astrolens.core.errors import AstroLensError
from astrolens.core.models import Asset, Citation, ReusePolicy, View, ViewScores
from astrolens.services.vision_ranker import VisionRankerService

_REUSE = ReusePolicy(id="reuse:test", credit_text="Credit the test archive")


class FakeClient:
    """Offline stand-in for AnthropicClient; unit tests never hit the network."""

    model = "claude-test"

    def __init__(self, reply: str | Exception = "[]", *, available: bool = True) -> None:
        self.reply = reply
        self._available = available
        self.calls: list[dict[str, Any]] = []

    def available(self) -> bool:
        return self._available

    async def complete(
        self, *, system: str, content: list[dict[str, Any]], max_tokens: int = 1024
    ) -> str:
        if not self._available:
            raise AstroLensError(
                ErrorCode.SOURCE_UNAVAILABLE, "no API key", retryable=False
            )
        self.calls.append({"system": system, "content": content})
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _view(label: str, url: str | None, band: BandFamily = BandFamily.VISIBLE) -> View:
    asset = None
    if url is not None:
        asset = Asset(
            id=f"asset:{label}",
            format="png",
            visual_tier=VisualAssetTier.ASTROLENS_RENDERED,
            asset_url=url,
            reuse_policy_id=_REUSE.id,
        )
    return View(
        id=f"view:{label}",
        label=label,
        band_family=band,
        source_archive="MAST",
        asset=asset,
        reuse=_REUSE,
        citations=[Citation(id=f"cite:{label}", title=label, source="MAST")],
        scores=ViewScores(overall=0.8),
    )


def _service(
    client: FakeClient, tmp_path: Path, *, public_base_url: str | None = None
) -> VisionRankerService:
    return VisionRankerService(
        client,  # type: ignore[arg-type]
        cache_dir=tmp_path / "vision-verdicts",
        public_base_url=public_base_url,
    )


_MESSY_REPLY = (
    "Sure! Here are my scores:\n"
    '[{"index": 1, "score": 88, "reason": "sharp and centered"},'
    ' {"index": 2, "score": 15, "reason": "nearly blank"}]\n'
    "Let me know if you need anything else."
)


def test_rank_views_parses_messy_reply_and_persists_verdicts(tmp_path: Path) -> None:
    client = FakeClient(_MESSY_REPLY)
    service = _service(client, tmp_path)
    views = [
        _view("a", "https://example.org/a.png"),
        _view("b", "https://example.org/b.png"),
    ]

    scores = asyncio.run(service.rank_views("M87", views))

    assert scores == {"view:a": 0.88, "view:b": 0.15}
    assert len(client.calls) == 1
    # One numbered image block per candidate plus the scoring instructions.
    content = client.calls[0]["content"]
    image_urls = [
        block["source"]["url"] for block in content if block.get("type") == "image"
    ]
    assert image_urls == ["https://example.org/a.png", "https://example.org/b.png"]
    assert "M87" in content[-1]["text"]
    assert len(list((tmp_path / "vision-verdicts").glob("*.json"))) == 2


def test_cache_hit_avoids_a_second_model_call(tmp_path: Path) -> None:
    views = [_view("a", "https://example.org/a.png"), _view("b", "https://example.org/b.png")]
    asyncio.run(_service(FakeClient(_MESSY_REPLY), tmp_path).rank_views("M87", views))

    # A fresh service over the same cache dir must answer purely from disk.
    replay_client = FakeClient(RuntimeError("must not be called"))
    scores = asyncio.run(_service(replay_client, tmp_path).rank_views("M87", views))

    assert scores == {"view:a": 0.88, "view:b": 0.15}
    assert replay_client.calls == []


def test_only_uncached_images_are_sent_to_the_model(tmp_path: Path) -> None:
    cached = _view("a", "https://example.org/a.png")
    asyncio.run(
        _service(
            FakeClient('[{"index": 1, "score": 70, "reason": "fine"}]'), tmp_path
        ).rank_views("M87", [cached])
    )

    client = FakeClient('[{"index": 1, "score": 40, "reason": "noisy"}]')
    fresh = _view("b", "https://example.org/b.png")
    scores = asyncio.run(_service(client, tmp_path).rank_views("M87", [cached, fresh]))

    assert scores == {"view:a": 0.7, "view:b": 0.4}
    image_urls = [
        block["source"]["url"]
        for block in client.calls[0]["content"]
        if block.get("type") == "image"
    ]
    assert image_urls == ["https://example.org/b.png"]


def test_relative_urls_absolutized_only_with_https_public_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ASTROLENS_PUBLIC_BASE_URL", raising=False)
    client = FakeClient('[{"index": 1, "score": 90, "reason": "good"}]')
    service = _service(client, tmp_path, public_base_url="https://astrolens.example")
    views = [
        _view("rendered", "/v1/rendered/x.png"),
        _view("insecure", "http://example.org/plain.png"),  # not https: skipped
        _view("bare", None),  # no asset: skipped
    ]

    scores = asyncio.run(service.rank_views("Saturn", views))

    assert scores == {"view:rendered": 0.9}
    image_urls = [
        block["source"]["url"]
        for block in client.calls[0]["content"]
        if block.get("type") == "image"
    ]
    assert image_urls == ["https://astrolens.example/v1/rendered/x.png"]


def test_relative_urls_without_public_base_yield_no_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ASTROLENS_PUBLIC_BASE_URL", raising=False)
    client = FakeClient(_MESSY_REPLY)
    service = _service(client, tmp_path)

    scores = asyncio.run(service.rank_views("Saturn", [_view("rendered", "/v1/rendered/x.png")]))

    assert scores == {}
    assert client.calls == []


def test_rank_views_returns_empty_on_any_failure(tmp_path: Path) -> None:
    views = [_view("a", "https://example.org/a.png")]
    failures = [
        FakeClient(available=False),  # no API key
        FakeClient(AstroLensError(ErrorCode.SOURCE_TIMEOUT, "slow", retryable=True)),
        FakeClient("I could not score these images."),  # unparseable reply
    ]
    for client in failures:
        scores = asyncio.run(_service(client, tmp_path).rank_views("M87", views))
        assert scores == {}
    assert list((tmp_path / "vision-verdicts").glob("*.json")) == []
