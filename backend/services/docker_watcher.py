import os
import json
import time
import docker
import asyncio
from uuid import uuid4
from collections import deque

from config import settings
from core.logging import get_logger
from api.ws import notify_job_started
from core.decorators import log_execution

from services.analyze_error import AnalyzeJob


def _next_log_line(stream):
    try:
        return next(stream)
    except StopIteration:
        return None


class DockerLogWatcher:
    """Отслеживает логи FixOps-контейнеров и реагирует на ERROR."""

    def __init__(self):
        self.client = docker.from_env()
        self.recent_errors = {}


    @log_execution(event="docker_watcher.run")
    async def run(self):
        """Запускает отслеживание всех FixOps-контейнеров."""
        log = get_logger(event="docker_watcher.run")

        containers = self.client.containers.list(
            filters={"label": "fixops.enabled=true"},
        )

        log.info("Found {} FixOps containers", len(containers))

        tasks = [
            self.watch_container(container)
            for container in containers
        ]

        if tasks:
            await asyncio.gather(*tasks)
        else:
            await asyncio.Event().wait()


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
                    log_stream,
                )

                if raw_line is None:
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

                asyncio.create_task(
                    self.handle_error(
                        container=container,
                        data=data,
                        project_root=project_root,
                        history=history.copy(),
                    )
                )

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

        if (
            last_seen is not None
            and now - last_seen < 2
        ):
            return True

        return False

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

        await notify_job_started(job_id)

        job = AnalyzeJob(
            project_root=project_root,
            error_log=error_log,
            logs_dir=logs_dir,
            extra_ignore_dirs=settings.analysis.EXTRA_IGNORE_DIRS,
            job_id=job_id,
        )

        await job.run()
