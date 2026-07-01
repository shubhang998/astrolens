"""FastAPI application entrypoint for AstroLens."""

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
    Observation,
    ReusePolicy,
    SourceHealthResponse,
    TargetValidation,
    View,
)


def create_app() -> FastAPI:
    """Create and configure the FastAPI app."""

    app = FastAPI(
        title="AstroLens Evidence API",
        version=__version__,
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
            status_code=status.HTTP_400_BAD_REQUEST,
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
                code=ErrorCode.INVALID_COORDINATES,
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
