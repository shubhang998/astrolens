"""Conservative render job service for V1."""

from uuid import uuid4

from astrolens.core.enums import ErrorCode, JobStatus
from astrolens.core.errors import AstroLensError
from astrolens.core.models import JobResponse, RenderJob, RenderRequest, RenderResponse
from astrolens.services.assets import response_meta
from astrolens.services.repository import EvidenceRepository, repository


class RenderService:
    """Return cached assets or create typed unsupported/queued render jobs."""

    def __init__(self, repo: EvidenceRepository = repository) -> None:
        self.repo = repo
        self.jobs: dict[str, RenderJob] = {}

    def render(self, request: RenderRequest) -> RenderResponse:
        product = self.repo.get_product(request.product_id)
        cached_asset = next(
            (
                asset
                for asset in self.repo.assets.values()
                if request.product_id in asset.source_product_ids
            ),
            None,
        )
        if cached_asset:
            return RenderResponse(status="complete", asset=cached_asset)
        if product.file_format not in {"fits", "fit", "fz"}:
            job_id = f"job:render:{uuid4().hex}"
            job = RenderJob(
                id=job_id,
                status=JobStatus.UNSUPPORTED,
                product_id=request.product_id,
                error=(
                    "Only cached assets and simple FITS image products are render candidates "
                    "in V1."
                ),
            )
            self.jobs[job_id] = job
            return RenderResponse(
                status="unsupported",
                job_id=job_id,
                poll_url=f"/v1/jobs/{job_id}",
                error=job.error,
            )
        job_id = f"job:render:{uuid4().hex}"
        job = RenderJob(id=job_id, status=JobStatus.QUEUED, product_id=request.product_id)
        self.jobs[job_id] = job
        return RenderResponse(status="queued", job_id=job_id, poll_url=f"/v1/jobs/{job_id}")

    def get_job(self, job_id: str) -> JobResponse:
        try:
            job = self.jobs[job_id]
        except KeyError as exc:
            raise AstroLensError(
                ErrorCode.OBJECT_NOT_FOUND,
                f"Job '{job_id}' was not found.",
                details={"job_id": job_id},
            ) from exc
        return JobResponse(job=job, meta=response_meta())


render_service = RenderService()
