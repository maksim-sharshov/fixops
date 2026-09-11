import asyncio
from services.container_manager import (
    run_apply,
    run_rollback
)

from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api/containers",
    tags=["containers"],
)


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
        )


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
        )
