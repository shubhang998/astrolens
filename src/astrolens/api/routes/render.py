"""Render and job routes."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from astrolens.core.models import JobResponse, RenderRequest, RenderResponse
from astrolens.services.fits_renderer import FitsRenderer, FitsRenderRequest, FitsRenderResult
from astrolens.services.rendering import render_service

router = APIRouter(tags=["render"])
fits_renderer = FitsRenderer()


@router.post("/render", response_model=RenderResponse)
async def render(request: RenderRequest) -> RenderResponse:
    return render_service.render(request)


@router.post("/render/fits-plan", response_model=FitsRenderResult)
async def plan_fits_render(request: FitsRenderRequest) -> FitsRenderResult:
    return fits_renderer.render(request)


@router.get("/rendered/{filename}")
async def get_rendered_asset(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=404, detail="Rendered asset not found.")
    path = fits_renderer.cache_dir / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Rendered asset not found.")
    media_type = "image/jpeg" if Path(filename).suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return FileResponse(path, media_type=media_type)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    return render_service.get_job(job_id)
