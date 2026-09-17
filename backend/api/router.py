from fastapi import APIRouter

from api.ws import router as ws_router
from api.containers import router as containers_router
from api.incidents import router as incidents_router


api_router = APIRouter(prefix="/api")


@api_router.get("", tags=["health"])
async def api_root():
    return {"status": "ok", "service": "FixOps API"}


api_router.include_router(ws_router)
api_router.include_router(containers_router)
api_router.include_router(incidents_router)
