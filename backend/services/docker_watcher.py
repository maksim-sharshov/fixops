import asyncio
import json
import os
import time
from collections import deque
from uuid import uuid4

import docker

from api.ws import notify_job_started
from config import settings
from core.decorators import log_execution
from core.logging import get_logger
from services.analyze_error import AnalyzeJob


def _next_log_line(stream):
    try:
        return next(stream)
    except StopIteration:
        return None


class DockerLogWatcher:

    def __init__(self):
        self.client = docker.from_env()
        self.recent_errors = {}
        self.containers = {}
        self.watch_tasks: dict[str, asyncio.Task] = {}
        self.error_tasks: set[asyncio.Task] = set()


    @log_execution(event="docker_watcher.run")
    async def run(self):
        """Постоянно ищет новые FixOps-контейнеры."""

        log = get_logger(
            event="docker_watcher.run"
        )

        log.info("Docker watcher started")

        try:
            while True:

                containers = await asyncio.to_thread(
                    self.client.containers.list,
                    filters={
                        "label": "fixops.enabled=true"
                    },
                )

                self.containers = {
                    container.id: container
                    for container in containers
                }

                for container in containers:

                    if container.id in self.watch_tasks:
                        continue

                    log.info(
                        "New FixOps container detected: {}",
                        container.name,
                    )

                    task = asyncio.create_task(
                        self.start_watching(container)
                    )

                    self.watch_tasks[
                        container.id
                    ] = task


                # Удаляем завершённые задачи
                finished_ids = [
                    container_id
                    for container_id, task
                    in self.watch_tasks.items()
                    if task.done()
                ]

                for container_id in finished_ids:
                    self.watch_tasks.pop(
                        container_id,
                        None,
                    )

                await asyncio.sleep(2)

        except asyncio.CancelledError:

            log.info(
                "Docker watcher shutting down"
            )

            for task in self.watch_tasks.values():
                task.cancel()

            await asyncio.gather(
                *self.watch_tasks.values(),
                return_exceptions=True,
            )

            raise


    async def start_watching(self, container):

        try:
            await self.watch_container(container)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            log = get_logger(
                event="docker_watcher.container",
                container=container.name,
            )

            log.exception(
                "Container watcher crashed: {}",
                exc,
            )

        finally:
            self.watch_tasks.pop(
                container.id,
                None,
            )

    @log_execution(event="docker_watcher.container")
    async def watch_container(self, container):
        """Отслеживает новые логи одного контейнера."""

        log = get_logger(
            event="docker_watcher.container",
            container=container.name,
        )

        project_root = container.labels.get(
            "fixops.project_path"
        )

        if not project_root:
            log.error(
                "Container has no fixops.project_path label"
            )
            return

        history = deque(
            maxlen=max(
                settings.analysis.LOG_TAIL_LINES - 1,
                0,
            )
        )

        log.info(
            "Started watching container logs"
        )

        stream = await asyncio.to_thread(
            container.logs,
            stdout=True,
            stderr=True,
            stream=True,
            follow=True,
            tail=0,
        )

        while True:

            try:
                raw_line = await asyncio.to_thread(
                    _next_log_line,
                    stream,
                )

                if raw_line is None:
                    log.warning("Docker log stream ended")
                    break

            except StopIteration:
                log.warning(
                    "Docker log stream ended"
                )
                break

            line = raw_line.decode(
                "utf-8",
                errors="replace",
            ).rstrip()

            if not line:
                continue

            data = self.parse_log(line)

            if data is None:
                continue

            if self.is_error(data):

                if self.is_duplicate_error(
                    data,
                    container.name,
                ):
                    continue

                task = asyncio.create_task(
                    self.handle_error(
                        container=container,
                        data=data,
                        project_root=project_root,
                        history=history.copy(),
                    )
                )
                self.error_tasks.add(task)
                task.add_done_callback(self.error_tasks.discard)

                continue

            history.append(data)


    @staticmethod
    def parse_log(line: str) -> dict | None:
        """Парсит JSON-запись Docker-лога."""
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None


    @staticmethod
    def is_error(data: dict) -> bool:
        """Проверяет, является ли лог ERROR."""
        record = data.get("record", {})

        return (
            record.get("level", {}).get("name") == "ERROR"
            or record.get("extra", {}).get("severity") == "ERROR"
        )


    def is_duplicate_error(
        self,
        data: dict,
        container_name: str,
    ) -> bool:
        """Проверяет, является ли ERROR повтором уже обработанной ошибки."""

        record = data.get("record", {})
        extra = record.get("extra", {})
        error = extra.get("error", {})

        if error.get("type") == "HTTPException":
            return True

        error_key = (
            container_name,
            extra.get("file"),
            extra.get("line"),
            error.get("type"),
            error.get("message"),
        )

        now = time.monotonic()

        last_seen = self.recent_errors.get(
            error_key
        )

        self.recent_errors[error_key] = now

        return (
            last_seen is not None
            and now - last_seen < 2
        )

    @log_execution(event="docker_watcher.handle_error")
    async def handle_error(
        self,
        container,
        data: dict,
        project_root: str,
        history: deque,
    ):
        """Обрабатывает ERROR и запускает анализ."""
        log = get_logger(
            event="docker_watcher.handle_error",
            container=container.name,
            project=project_root,
        )

        record = data.get("record", {})
        extra = record.get("extra", {})

        file_path = extra["file"]

        if file_path.startswith("/app/"):
            file_path = file_path.removeprefix("/app/")

        file_path = os.path.join(project_root, file_path)

        error_log = {
            "file": file_path,
            "line": int(extra["line"]),
            "function": extra["function"],
            "error": extra["error"],
        }

        log.warning(
            "Error detected: {}:{}",
            error_log["file"],
            error_log["line"],
        )

        logs_dir = f"{project_root}/.fixops"
        job_id = uuid4().hex

        await notify_job_started(
            job_id=job_id,
            container_id=container.id
        )

        job = AnalyzeJob(
            project_root=project_root,
            error_log=error_log,
            logs_dir=logs_dir,
            extra_ignore_dirs=settings.analysis.EXTRA_IGNORE_DIRS,
            job_id=job_id,
            container_id=container.id,
            container_name=container.name,
            project=container.labels.get("fixops.project"),
        )

        await job.run()
