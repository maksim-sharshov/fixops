import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.router import api_router
from db.psql.crud.base import create_tables
from services.docker_watcher import DockerLogWatcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()

    watcher = DockerLogWatcher()

    app.state.docker_watcher = watcher

    watcher_task = asyncio.create_task(watcher.run())

    yield

    watcher_task.cancel()

    try:
        await watcher_task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
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

    app.include_router(api_router)

    return app


app = create_app()
