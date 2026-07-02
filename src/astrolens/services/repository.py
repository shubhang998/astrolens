"""Read-only local repository for AstroLens V1 seed evidence."""

from collections.abc import Iterable

from astrolens.core.enums import BandFamily, ErrorCode
from astrolens.core.errors import AstroLensError
from astrolens.core.models import (
    Asset,
    CelestialObject,
    Citation,
    DataProduct,
    Observation,
    ReusePolicy,
    View,
)
from astrolens.data import seed


def normalize_query(value: str) -> str:
    """Normalize names and aliases for lookup/search."""

    return "".join(ch.lower() for ch in value.strip() if ch.isalnum())


class EvidenceRepository:
    """In-memory cache-first repository backed by curated seed data."""

    def __init__(self) -> None:
        self.objects = {obj.id: obj for obj in seed.OBJECTS}
        self.observations = {obs.id: obs for obs in seed.OBSERVATIONS}
        self.products = {product.id: product for product in seed.PRODUCTS}
        self.assets = {asset.id: asset for asset in seed.ASSETS}
        self.views = {view.id: view for view in seed.VIEWS}
        self.facts = {fact.id: fact for fact in seed.FACTS}
        self.citations = dict(seed.CITATIONS)
        self.reuse_policies = dict(seed.REUSE_POLICIES)
        self.alias_index = self._build_alias_index(seed.OBJECTS)

    def _build_alias_index(self, objects: Iterable[CelestialObject]) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for obj in objects:
            for alias in [obj.name, *obj.aliases, obj.id.rsplit(":", maxsplit=1)[-1]]:
                key = normalize_query(alias)
                indexed = index.setdefault(key, [])
                if obj.id not in indexed:
                    indexed.append(obj.id)
        return index

    def list_objects(self) -> list[CelestialObject]:
        return list(self.objects.values())

    def upsert_object(self, obj: CelestialObject) -> None:
        self.objects[obj.id] = obj
        for alias in [obj.name, *obj.aliases, obj.id.rsplit(":", maxsplit=1)[-1]]:
            key = normalize_query(alias)
            indexed = self.alias_index.setdefault(key, [])
            if obj.id not in indexed:
                indexed.append(obj.id)

    def get_object(self, object_id: str) -> CelestialObject:
        try:
            return self.objects[object_id]
        except KeyError as exc:
            raise AstroLensError(
                ErrorCode.OBJECT_NOT_FOUND,
                f"Object '{object_id}' was not found.",
                details={"object_id": object_id},
            ) from exc

    def find_objects(self, query: str, *, limit: int = 10) -> list[CelestialObject]:
        normalized = normalize_query(query)
        if not normalized:
            return []
        exact_ids = self.alias_index.get(normalized, [])
        if exact_ids:
            return [self.objects[object_id] for object_id in exact_ids[:limit]]

        matches: list[CelestialObject] = []
        for obj in self.objects.values():
            fields = [obj.name, obj.type, *obj.aliases]
            # Match whole fields ("NGC 5128" vs "ngc5128") or within single
            # words; never across word boundaries, where concatenation creates
            # false hits (e.g. "vega" inside "active galaxy" -> "activegalaxy").
            if any(normalized == normalize_query(field) for field in fields):
                matches.append(obj)
                continue
            words = {
                normalize_query(word) for field in fields for word in field.split()
            }
            if any(normalized in word for word in words if word):
                matches.append(obj)
        return matches[:limit]

    def observations_for_object(
        self, object_id: str, bands: list[BandFamily] | None = None
    ) -> list[Observation]:
        selected_bands = set(bands or [])
        observations = [
            obs
            for obs in self.observations.values()
            if obs.object_id == object_id
            and (not selected_bands or obs.band_family in selected_bands)
        ]
        return observations

    def views_for_object(self, object_id: str, bands: list[BandFamily] | None = None) -> list[View]:
        selected_bands = set(bands or [])
        views = [
            view
            for view in self.views.values()
            if view.id.startswith(f"view:{object_id.rsplit(':', maxsplit=1)[-1]}:")
            and (not selected_bands or view.band_family in selected_bands)
        ]
        return views

    def get_asset(self, asset_id: str) -> Asset:
        try:
            return self.assets[asset_id]
        except KeyError as exc:
            raise AstroLensError(
                ErrorCode.OBJECT_NOT_FOUND,
                f"Asset '{asset_id}' was not found.",
                details={"asset_id": asset_id},
            ) from exc

    def get_product(self, product_id: str) -> DataProduct:
        try:
            return self.products[product_id]
        except KeyError as exc:
            raise AstroLensError(
                ErrorCode.OBJECT_NOT_FOUND,
                f"Product '{product_id}' was not found.",
                details={"product_id": product_id},
            ) from exc

    def get_reuse_policy(self, reuse_policy_id: str) -> ReusePolicy:
        return self.reuse_policies.get(reuse_policy_id, self.reuse_policies["reuse:unknown"])

    def get_citation(self, citation_id: str) -> Citation:
        try:
            return self.citations[citation_id]
        except KeyError as exc:
            raise AstroLensError(
                ErrorCode.OBJECT_NOT_FOUND,
                f"Citation '{citation_id}' was not found.",
                details={"citation_id": citation_id},
            ) from exc

    def citations_for_asset(self, asset_id: str) -> list[Citation]:
        return self.get_asset(asset_id).citations

    def citations_for_product(self, product_id: str) -> list[Citation]:
        product = self.get_product(product_id)
        matches = [
            citation
            for citation in self.citations.values()
            if product.source_record_id
            and product.source_record_id.split(":")[0].lower() in citation.source.lower()
        ]
        return matches or list(self.citations.values())[:1]


repository = EvidenceRepository()
