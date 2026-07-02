"""FastAPI application entrypoint for AstroLens."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from astrolens import __version__
from astrolens.api.routes import (
    assets,
    compare,
    evidence,
    health,
    mcp,
    objects,
    render,
    resolve,
    search,
)
from astrolens.core.enums import ErrorCode
from astrolens.core.errors import APIError, APIErrorDetail, AstroLensError
from astrolens.core.models import (
    Asset,
    CelestialObject,
    Citation,
    DataProduct,
    EvidenceBundle,
    Fact,
    ImageProvenance,
    ObjectAlias,
    ObjectFactsResponse,
    Observation,
    ReusePolicy,
    SourceHealthResponse,
    TargetValidation,
    View,
)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    import logging

    from astrolens.services.warmer import warm_curated_cache, warming_enabled

    # Application loggers (e.g. astrolens.warmer) need a handler or their
    # INFO lines silently vanish from platform logs; uvicorn only configures
    # its own loggers.
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )

    warm_task: asyncio.Task[int] | None = None
    if warming_enabled():
        warm_task = asyncio.create_task(warm_curated_cache())
    try:
        yield
    finally:
        if warm_task is not None:
            warm_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await warm_task


def create_app() -> FastAPI:
    """Create and configure the FastAPI app."""

    app = FastAPI(
        title="AstroLens Evidence API",
        version=__version__,
        lifespan=_lifespan,
        description=(
            "Read-only astronomy evidence API for agents. AstroLens returns "
            "structured evidence, assets, citations, reuse metadata, and caveats; "
            "it does not generate lessons, scripts, or social content."
        ),
        openapi_tags=[{"name": "health", "description": "Service and source health."}],
    )
    app.include_router(health.router, prefix="/v1")
    app.include_router(resolve.router, prefix="/v1")
    app.include_router(search.router, prefix="/v1")
    app.include_router(evidence.router, prefix="/v1")
    app.include_router(objects.router, prefix="/v1")
    app.include_router(assets.router, prefix="/v1")
    app.include_router(compare.router, prefix="/v1")
    app.include_router(render.router, prefix="/v1")
    app.include_router(mcp.router)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Send browser users to the interactive API docs."""

        return RedirectResponse(url="/docs")

    register_schema_models(app)
    register_exception_handlers(app)
    return app


def register_schema_models(app: FastAPI) -> None:
    """Expose core contracts in OpenAPI even before all routes exist."""

    original_openapi = app.openapi

    def custom_openapi() -> dict[str, object]:
        schema = original_openapi()
        components = schema.setdefault("components", {})
        schemas = components.setdefault("schemas", {})
        for model in (
            CelestialObject,
            ObjectAlias,
            Observation,
            DataProduct,
            View,
            Asset,
            Fact,
            TargetValidation,
            ImageProvenance,
            Citation,
            ReusePolicy,
            EvidenceBundle,
            ObjectFactsResponse,
            SourceHealthResponse,
            APIError,
        ):
            schemas.setdefault(
                model.__name__,
                model.model_json_schema(ref_template="#/components/schemas/{model}"),
            )
        return schema

    app.openapi = custom_openapi


def register_exception_handlers(app: FastAPI) -> None:
    """Register stable public error envelopes."""

    @app.exception_handler(AstroLensError)
    async def handle_astrolens_error(_request: Request, exc: AstroLensError) -> JSONResponse:
        request_id = f"req_{uuid4().hex}"
        error = APIError(
            error=APIErrorDetail(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                request_id=request_id,
                details=exc.details,
            )
        )
        return JSONResponse(
            status_code=_status_for_error(exc.code),
            content=error.model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        request_id = f"req_{uuid4().hex}"
        error = APIError(
            error=APIErrorDetail(
                code=ErrorCode.VALIDATION_ERROR,
                message="Request validation failed.",
                retryable=False,
                request_id=request_id,
                details={"errors": exc.errors()},
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error.model_dump(mode="json"),
        )


app = create_app()


def _status_for_error(code: ErrorCode) -> int:
    if code == ErrorCode.OBJECT_NOT_FOUND:
        return status.HTTP_404_NOT_FOUND
    if code == ErrorCode.OBJECT_AMBIGUOUS:
        return status.HTTP_409_CONFLICT
    if code == ErrorCode.PRODUCT_NOT_PUBLIC:
        return status.HTTP_403_FORBIDDEN
    if code == ErrorCode.RATE_LIMITED:
        return status.HTTP_429_TOO_MANY_REQUESTS
    if code == ErrorCode.SOURCE_TIMEOUT:
        return status.HTTP_504_GATEWAY_TIMEOUT
    if code == ErrorCode.SOURCE_UNAVAILABLE:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if code in {
        ErrorCode.INVALID_COORDINATES,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.UNSUPPORTED_BAND,
        ErrorCode.RENDER_NOT_SUPPORTED,
        ErrorCode.PRODUCT_TOO_LARGE,
        ErrorCode.UNSUPPORTED_CONNECTOR_OPERATION,
    }:
        return status.HTTP_422_UNPROCESSABLE_ENTITY
    return status.HTTP_500_INTERNAL_SERVER_ERROR
