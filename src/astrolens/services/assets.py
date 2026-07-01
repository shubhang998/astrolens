"""Asset, citation, and raw-link lookup services."""

from uuid import uuid4

from astrolens.core.enums import CacheStatus
from astrolens.core.models import (
    AssetResponse,
    CacheMeta,
    CitationsResponse,
    RawLink,
    RawLinksResponse,
    ResponseMeta,
)
from astrolens.services.repository import EvidenceRepository, repository


def response_meta() -> ResponseMeta:
    """Create request metadata for lookup responses."""

    return ResponseMeta(
        request_id=f"req_{uuid4().hex}",
        cache=CacheMeta(status=CacheStatus.HIT, stale=False),
    )


class AssetService:
    """Resolve assets, citations, and raw links."""

    def __init__(self, repo: EvidenceRepository = repository) -> None:
        self.repo = repo

    def get_asset(self, asset_id: str) -> AssetResponse:
        asset = self.repo.get_asset(asset_id)
        return AssetResponse(
            asset=asset,
            reuse=self.repo.get_reuse_policy(asset.reuse_policy_id),
            citations=asset.citations,
            caveats=[
                "Preserve credit text and source links.",
                "Preview assets may be generated from survey/archive data.",
            ],
            meta=response_meta(),
        )

    def get_asset_citations(self, asset_id: str) -> CitationsResponse:
        return CitationsResponse(
            citations=self.repo.citations_for_asset(asset_id), meta=response_meta()
        )

    def get_product_raw_links(self, product_id: str) -> RawLinksResponse:
        product = self.repo.get_product(product_id)
        citations = self.repo.citations_for_product(product_id)
        raw_links: list[RawLink] = []
        if product.download_url:
            raw_links.append(
                RawLink(
                    label="Source product or archive record",
                    url=product.download_url,
                    source=product.source_record_id.split(":")[0]
                    if product.source_record_id
                    else "unknown",
                    product_id=product.id,
                    citation_ids=[citation.id for citation in citations],
                )
            )
        return RawLinksResponse(
            product=product,
            raw_links=raw_links,
            citations=citations,
            meta=response_meta(),
        )


asset_service = AssetService()
