"""LLM interpretation summaries grounded in compiled facts.

The summarizer never authors facts: it rewrites the numbered, already-cited
``Fact`` claims into 2-3 plain-language sentences with bracketed citation
markers, and every numeric token in the reply is validated against the fact
text before the summary is served. Anything that fails validation — or any
missing API key or API error — degrades to ``None`` so callers simply omit the
summary field.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from astrolens.connectors.anthropic_llm import AnthropicClient, anthropic_client, text_block
from astrolens.core.models import AstroLensModel, CelestialObject, Citation, Fact, View
from astrolens.services.vision_ranker import interpretation_cache_dir

logger = logging.getLogger(__name__)

PROMPT_VERSION = 1
SUMMARY_CACHE_ENV = "ASTROLENS_SUMMARY_CACHE_DIR"

SUMMARY_SYSTEM_PROMPT = (
    "You write 2-3 sentence plain-language summaries for a science evidence card. "
    "Use ONLY the numbered facts provided. Every sentence must end with bracketed "
    "citation markers like [1] or [1,2] referring to the fact numbers used. Never "
    "introduce any number, measurement, or claim not present in the facts. Write "
    "for a curious adult; warm, clear, no hype."
)

_MARKER_PATTERN = re.compile(r"\[([\d,\s]+)\]")
_NUMBER_PATTERN = re.compile(r"\d[\d,.]*")


class Summary(AstroLensModel):
    """Labeled LLM interpretation of compiled facts; never a source of numbers."""

    text: str
    citation_ids: list[str] = []
    model: str
    generated: bool = True


class SummarizerService:
    """Generates cached, validated fact summaries via the Anthropic client."""

    def __init__(
        self,
        client: AnthropicClient = anthropic_client,
        *,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.client = client
        self.cache_dir = Path(
            cache_dir
            if cache_dir is not None
            else interpretation_cache_dir("summaries", env_override=SUMMARY_CACHE_ENV)
        )

    async def summarize(
        self,
        obj: CelestialObject,
        facts: list[Fact],
        citations: list[Citation],
        views: list[View],
    ) -> Summary | None:
        try:
            return await self._summarize(obj, facts, views)
        except Exception:  # noqa: BLE001 - interpretation must never break the request
            logger.warning("Summary generation failed; omitting the summary.", exc_info=True)
            return None

    async def _summarize(
        self,
        obj: CelestialObject,
        facts: list[Fact],
        views: list[View],
    ) -> Summary | None:
        if not facts or not self.client.available():
            return None
        cache_path = self._cache_path(obj, facts)
        cached = self._load_summary(cache_path)
        if cached is not None:
            return cached

        reply = await self.client.complete(
            system=SUMMARY_SYSTEM_PROMPT,
            content=[text_block(self._user_prompt(obj, facts, views))],
            max_tokens=400,
        )
        text = reply.strip()
        fact_numbers = _validated_fact_numbers(text, facts)
        if fact_numbers is None:
            return None
        summary = Summary(
            text=text,
            citation_ids=_citation_ids(facts, fact_numbers),
            model=self.client.model,
        )
        self._store_summary(cache_path, summary)
        return summary

    def _user_prompt(self, obj: CelestialObject, facts: list[Fact], views: list[View]) -> str:
        lines = [f"Object: {obj.name} ({obj.type})", "", "Facts:"]
        for number, fact in enumerate(facts, start=1):
            line = f"{number}. {fact.claim}"
            if fact.scale_comparison:
                line = f"{line} ({fact.scale_comparison})"
            lines.append(line)
        imagery = _imagery_line(views)
        if imagery:
            lines += ["", f"Imagery shown (describe qualitatively only): {imagery}"]
        return "\n".join(lines)

    # -- summary cache -----------------------------------------------------

    def _cache_path(self, obj: CelestialObject, facts: list[Fact]) -> Path:
        parts = [obj.id, self.client.model, str(PROMPT_VERSION)]
        parts.extend(sorted(f"{fact.id}|{fact.claim}" for fact in facts))
        digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _load_summary(self, path: Path) -> Summary | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(raw, dict) or raw.get("version") != PROMPT_VERSION:
            return None
        try:
            return Summary.model_validate(raw.get("summary"))
        except ValueError:
            return None

    def _store_summary(self, path: Path, summary: Summary) -> None:
        payload = {"version": PROMPT_VERSION, "summary": summary.model_dump(mode="json")}
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            logger.warning("Could not persist summary cache entry.", exc_info=True)


def _imagery_line(views: list[View]) -> str:
    described: list[str] = []
    for view in views:
        band = str(view.band_family)
        label = f"{band} ({view.instrument})" if view.instrument else band
        if label not in described:
            described.append(label)
    return ", ".join(described)


def _validated_fact_numbers(text: str, facts: list[Fact]) -> list[int] | None:
    """Return the cited fact numbers, or None when the reply fails validation."""

    markers = _MARKER_PATTERN.findall(text)
    if not markers:
        return None
    fact_numbers: list[int] = []
    for marker in markers:
        for token in marker.split(","):
            token = token.strip()
            if not token.isdigit():
                return None
            number = int(token)
            if not 1 <= number <= len(facts):
                return None
            if number not in fact_numbers:
                fact_numbers.append(number)
    if not _numbers_are_grounded(text, facts):
        return None
    return fact_numbers


def _numbers_are_grounded(text: str, facts: list[Fact]) -> bool:
    """Every numeric token outside citation markers must come from the facts."""

    haystack_parts: list[str] = []
    for fact in facts:
        haystack_parts.append(fact.claim)
        if fact.value is not None:
            haystack_parts.append(f"{fact.value:g}")
            haystack_parts.append(str(fact.value))
        if fact.scale_comparison:
            haystack_parts.append(fact.scale_comparison)
    haystack = " ".join(haystack_parts).replace(",", "")
    prose = _MARKER_PATTERN.sub(" ", text)  # tolerate pure citation-marker digits
    for token in _NUMBER_PATTERN.findall(prose):
        normalized = token.replace(",", "").rstrip(".")
        if normalized and normalized not in haystack:
            return False
    return True


def _citation_ids(facts: list[Fact], fact_numbers: list[int]) -> list[str]:
    citation_ids: list[str] = []
    for number in fact_numbers:
        for citation_id in facts[number - 1].citation_ids:
            if citation_id not in citation_ids:
                citation_ids.append(citation_id)
    return citation_ids


summarizer_service = SummarizerService()
