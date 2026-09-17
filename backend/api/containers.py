import asyncio

from fastapi import APIRouter, HTTPException, Request

from services.container_manager import run_apply, run_rollback

router = APIRouter(
    prefix="/containers",
    tags=["containers"],
)


@router.get("")
async def get_containers(request: Request):
    watcher = request.app.state.docker_watcher

    return [
        {
            "id": container.id,
            "name": container.name,
            "status": container.status,
            "project": container.labels.get("fixops.project"),
            "project_path": container.labels.get(
                "fixops.project_path"
            ),
        }
        for container in watcher.containers.values()
    ]


@router.post("/{container_id}/apply")
async def apply_fix(container_id: str):
    try:
        result = await asyncio.to_thread(
            run_apply,
            container_id,
        )

        return {
            "status": "ok",
            "action": "apply",
            "container_id": container_id,
            "output": result,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        ) from e


@router.post("/{container_id}/rollback")
async def rollback_fix(container_id: str):
    try:
        result = await asyncio.to_thread(
            run_rollback,
            container_id,
        )

        return {
            "status": "ok",
            "action": "rollback",
            "container_id": container_id,
            "output": result,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        ) from e
