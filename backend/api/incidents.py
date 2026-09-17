import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from db.psql.models.models import IncidentResult
from services.container_manager import run_apply, run_rollback

router = APIRouter(
    prefix="/incidents",
    tags=["incidents"],
)


LIST_FIELDS = [
    "id",
    "job_id",
    "container_id",
    "container_name",
    "project",
    "error_message",
    "error_location",
    "status",
    "applied_at",
    "rolled_back_at",
    "created_at",
]


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _to_dict(incident, fields: list[str] | None = None) -> dict:
    if fields is None:
        fields = [column.name for column in incident.__table__.columns]

    return {field: _serialize(getattr(incident, field)) for field in fields}


@router.get("")
async def list_incidents():
    """Список всех инцидентов (краткая карточка, без тяжёлых полей)."""
    incidents = await IncidentResult.all(values=LIST_FIELDS)

    incidents = sorted(
        incidents,
        key=lambda item: item.created_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )

    return [_to_dict(incident, LIST_FIELDS) for incident in incidents]


@router.get("/{job_id}")
async def get_incident(job_id: str):
    """Полная информация по одному инциденту."""
    incident = await IncidentResult.get(job_id=job_id)

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    return _to_dict(incident)


async def _get_incident_with_container(job_id: str):
    incident = await IncidentResult.get(job_id=job_id)

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    if not incident.container_id:
        raise HTTPException(
            status_code=400,
            detail="Incident has no container_id",
        )

    return incident


@router.post("/{job_id}/apply")
async def apply_incident(job_id: str):
    """Применяет исправление инцидента и фиксирует это в БД."""
    incident = await _get_incident_with_container(job_id)

    if incident.applied_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Fix already applied for this incident",
        )

    try:
        output = await asyncio.to_thread(run_apply, incident.container_id)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    await incident.update(
        applied_at=datetime.now(UTC),
        apply_output=output,
    )

    return {
        "status": "ok",
        "action": "apply",
        "job_id": job_id,
        "container_id": incident.container_id,
        "output": output,
    }


@router.post("/{job_id}/rollback")
async def rollback_incident(job_id: str):
    """Откатывает исправление инцидента и фиксирует это в БД."""
    incident = await _get_incident_with_container(job_id)

    try:
        output = await asyncio.to_thread(run_rollback, incident.container_id)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    await incident.update(
        rolled_back_at=datetime.now(UTC),
    )

    return {
        "status": "ok",
        "action": "rollback",
        "job_id": job_id,
        "container_id": incident.container_id,
        "output": output,
    }
