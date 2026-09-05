import os
import asyncio
from uuid import uuid4
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from config import settings
from core.events import events
from analyze_error import ErrorLoader, AnalyzeJob


app = FastAPI(
    title="FixOps API"
)


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    job_id: str,
):
    await events.connect(job_id, websocket)

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        events.disconnect(job_id, websocket)


@app.post("/analyze")
async def analyze_project():

    job_id = uuid4().hex

    project_path = "generator_report"

    base_dir = Path(__file__).resolve().parent.parent

    project_root = str(
        base_dir / project_path
    )

    error_log_path = os.path.join(
        project_root,
        "logs",
        "app.log"
    )

    logs_dir = os.path.join(
        project_root,
        ".fixops"
    )

    error_log = await ErrorLoader.from_file(
        error_log_path
    )

    job = AnalyzeJob(
        project_root=project_root,
        error_log=error_log,
        logs_dir=logs_dir,
        extra_ignore_dirs=settings.analysis.EXTRA_IGNORE_DIRS,
        job_id=job_id,
    )

    asyncio.create_task(
        run_job(job)
    )

    return {
        "job_id": job_id,
        "status": "started"
    }


async def run_job(job: AnalyzeJob):

    try:

        await events.emit(
            job.job_id,
            "workflow",
            step="fixops",
            status="started",
            message="FixOps started",
        )

        result_code = await job.run()

        await events.emit(
            job.job_id,
            "result",
            status="completed",
            result_code=result_code,
        )

    except Exception as e:

        await events.emit(
            job.job_id,
            "error",
            message=str(e),
        )
