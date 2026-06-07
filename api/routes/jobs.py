from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.ingestion_jobs import job_manager

router = APIRouter()


class CreateJobRequest(BaseModel):
    root_id: str
    relative_path: str = ""
    category: str = Field(default="dokumente")
    confidential: bool = True


@router.get("/roots")
def list_roots():
    return {"roots": job_manager.list_roots()}


@router.get("")
def list_jobs(limit: int = 20):
    return {"jobs": job_manager.list_jobs(limit)}


@router.post("")
def create_job(request: CreateJobRequest):
    try:
        return job_manager.create_job(
            root_id=request.root_id,
            relative_path=request.relative_path,
            category=request.category,
            confidential=request.confidential,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{job_id}")
def get_job(job_id: str):
    try:
        return job_manager.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job nicht gefunden.") from exc


@router.post("/{job_id}/pause")
def pause_job(job_id: str):
    return _change_job(job_manager.pause_job, job_id)


@router.post("/{job_id}/resume")
def resume_job(job_id: str):
    return _change_job(job_manager.resume_job, job_id)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    return _change_job(job_manager.cancel_job, job_id)


def _change_job(action, job_id: str):
    try:
        return action(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job nicht gefunden.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
