import asyncio
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
from services.analyze_error import AnalyzeJob, ErrorLoader


router = APIRouter(prefix="/jobs")

BASE_DIR = r"D:\Programs\fixops-workspaces"


class CreateJobRequest(BaseModel):
    project_path: str


jobs = {}


@router.post("")
async def create_job(
    request: CreateJobRequest,
):
    project_root = (
        BASE_DIR
        + "\\"
        + request.project_path
    ).rstrip("\\/")

    error_log_path = (
        project_root
        + "\\logs\\app.log"
    )

    logs_dir = (
        project_root
        + "\\.fixops"
    )

    if not __import__("os").path.isdir(project_root):
        raise HTTPException(
            status_code=400,
            detail=f"Project not found: {project_root}",
        )

    if not __import__("os").path.isfile(error_log_path):
        raise HTTPException(
            status_code=400,
            detail=f"Log file not found: {error_log_path}",
        )

    try:
        error_log = await ErrorLoader.from_file(
            error_log_path
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    job_id = uuid4().hex

    job = AnalyzeJob(
        project_root=project_root,
        error_log=error_log,
        logs_dir=logs_dir,
        extra_ignore_dirs=(
            settings.analysis.EXTRA_IGNORE_DIRS
        ),
        job_id=job_id,
    )

    jobs[job_id] = job

    asyncio.create_task(job.run())

    return {
        "job_id": job_id,
        "status": "started",
    }
