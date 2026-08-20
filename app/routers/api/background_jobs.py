from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from app.routers.api.schemas import PaginatedResponse
from app.routers.dependencies import get_superuser
from infra.jobs import JobDefinitionClass, enqueue_job, job_registry

# Superuser-only: enqueueing maintenance jobs can break production and many are
# irreversible. Mirrors the include-time gate on the HTML page in app/main.py.
router = APIRouter(tags=["background jobs"], dependencies=[Depends(get_superuser)])


def sorted_jobs_registry() -> dict[str, JobDefinitionClass]:
    return {k: v for k, v in sorted(job_registry.items(), key=lambda item: item[0])}


class JobTypeResponse(BaseModel):
    job_type: str
    name: str
    # The queue the job runs on by default. It's a ClassVar (not a model field),
    # so it isn't in args_schema — surface it explicitly. The instance `queue`
    # field is only an override; with default args the job lands here.
    queue: str
    # Pydantic JSON Schema of the job's arguments; the client derives a template
    # of required fields from it. Named args_schema, not schema, to avoid the
    # collision with BaseModel.schema.
    args_schema: dict[str, Any]


class JobTypesListResponse(PaginatedResponse):
    job_types: list[JobTypeResponse]


class EnqueueJobRequest(BaseModel):
    job_type: str
    arguments: dict[str, Any]


class EnqueueJobResponse(BaseModel):
    job_id: str
    job_type: str


# The catalog of runnable jobs is a distinct resource from a created job run, so
# it lives at its own path — GET /background_job_types lists what you can run;
# POST /background_jobs creates an actual run.
@router.get("/background_job_types", response_model=JobTypesListResponse)
async def api_background_job_types_index(
    registry: dict[str, JobDefinitionClass] = Depends(sorted_jobs_registry),
) -> JobTypesListResponse:
    return JobTypesListResponse(
        job_types=[
            JobTypeResponse(
                job_type=job_type,
                name=job_class.__name__,
                queue=job_class.default_queue.value,
                args_schema=job_class.model_json_schema(),
            )
            for job_type, job_class in registry.items()
        ]
    )


@router.post("/background_jobs", status_code=status.HTTP_202_ACCEPTED, response_model=EnqueueJobResponse)
async def api_background_jobs_create(body: EnqueueJobRequest) -> EnqueueJobResponse:
    # Both rejections come back as the same structured RequestValidationError
    # payload (detail: [{loc, msg, ...}]) so a client never has to branch on the
    # error shape. The /api/ error handler preserves it; a plain HTTPException
    # would stringify a list detail (app/routers/errors.py).
    job_class = job_registry.get(body.job_type)
    if job_class is None:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "job_type"),
                    "msg": f"Unknown job type: {body.job_type}",
                    "input": body.job_type,
                }
            ]
        )

    try:
        job_definition = job_class(**body.arguments)
    except ValidationError as error:
        # Prefix each error's loc with the request-body path so it reads as
        # body.arguments.<field>, matching FastAPI's own validation-error shape.
        raise RequestValidationError([{**err, "loc": ("body", "arguments", *err["loc"])} for err in error.errors()])

    job = await enqueue_job(job_definition)
    return EnqueueJobResponse(job_id=str(job.id), job_type=body.job_type)
