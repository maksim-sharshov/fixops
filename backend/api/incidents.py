from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from db.psql.models.models import IncidentResult


router = APIRouter(
    prefix="/api/incidents",
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
        key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc),
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
