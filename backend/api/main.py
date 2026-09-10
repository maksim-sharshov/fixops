import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.ws import router as ws_router
from api.jobs import router as jobs_router

from services.docker_watcher import DockerLogWatcher


@asynccontextmanager
async def lifespan(app: FastAPI):

    watcher = DockerLogWatcher()

    watcher_task = asyncio.create_task(
        watcher.run()
    )

    yield

    watcher_task.cancel()

    try:
        await watcher_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="FixOps API",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(ws_router)
app.include_router(jobs_router)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "FixOps",
    }
