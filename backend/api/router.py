from fastapi import APIRouter

from api.ws import router as ws_router
from api.containers import router as containers_router


api_router = APIRouter()

api_router.include_router(ws_router)
api_router.include_router(containers_router)
