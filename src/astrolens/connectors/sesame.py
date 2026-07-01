"""Limited live CDS Sesame/SIMBAD resolver connector."""

import asyncio
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from astrolens.connectors.base import ResolvedObjectCandidate
from astrolens.core.enums import ErrorCode, SourceHealthStatus
from astrolens.core.errors import AstroLensError
from astrolens.core.models import SourceHealth

SESAME_BASE_URL = "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp"


class SesameConnector:
    """Live, read-only object identity resolver using CDS Sesame."""

    name = "CDS Sesame"
    timeout_seconds = 8.0

    async def healthcheck(self) -> SourceHealth:
        try:
            await self.resolve_object("M87")
        except Exception:  # pragma: no cover - defensive health boundary
            return SourceHealth(
                name=self.name,
                status=SourceHealthStatus.UNAVAILABLE,
                last_error_at=datetime.now(UTC),
            )
        return SourceHealth(
            name=self.name,
            status=SourceHealthStatus.OK,
            last_success_at=datetime.now(UTC),
            latency_ms=None,
        )

    async def resolve_object(self, query: str) -> list[ResolvedObjectCandidate]:
        """Resolve a name through CDS Sesame and parse the XML response."""

        return await asyncio.to_thread(self._resolve_sync, query)

    def _resolve_sync(self, query: str) -> list[ResolvedObjectCandidate]:
        url = f"{SESAME_BASE_URL}?{urlencode({query: ''})}".removesuffix("=")
        request = Request(url, headers={"User-Agent": "AstroLens/0.1 limited-live-resolver"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read()
        except Exception as exc:  # pragma: no cover - live network error branch
            raise AstroLensError(
                ErrorCode.SOURCE_UNAVAILABLE,
                f"CDS Sesame live resolver failed for '{query}'.",
                retryable=True,
                details={"source": self.name, "query": query},
            ) from exc
        return self.parse_response(body, query=query, source_url=url)

    def parse_response(
        self,
        body: bytes,
        *,
        query: str,
        source_url: str,
    ) -> list[ResolvedObjectCandidate]:
        root = ElementTree.fromstring(body)
        resolver = root.find(".//Resolver")
        if resolver is None:
            return []
        ra_text = resolver.findtext("jradeg")
        dec_text = resolver.findtext("jdedeg")
        if not ra_text or not dec_text:
            return []
        canonical = resolver.findtext("oname") or query
        aliases = [query]
        if canonical and canonical not in aliases:
            aliases.append(canonical)
        return [
            ResolvedObjectCandidate(
                name=canonical.strip(),
                aliases=aliases,
                object_type=(resolver.findtext("otype") or "unknown").strip(),
                ra_deg=float(ra_text),
                dec_deg=float(dec_text),
                frame="ICRS",
                source=self.name,
                source_url=source_url,
                confidence=0.95,
                raw_metadata={
                    "oid": resolver.findtext("oid"),
                    "otype": resolver.findtext("otype"),
                    "jpos": resolver.findtext("jpos"),
                    "redshift": resolver.findtext("z/v"),
                    "redshift_reference": resolver.findtext("z/r"),
                    "reference_position": resolver.findtext("refPos"),
                    "nrefs": resolver.findtext("nrefs"),
                },
            )
        ]


sesame_connector = SesameConnector()
