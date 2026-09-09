import json
import docker
import asyncio
from collections import deque

from config import settings
from core.logging import get_logger
from core.decorators import log_execution

from services.analyze_error import AnalyzeJob


class DockerLogWatcher:
    """Отслеживает логи FixOps-контейнеров и реагирует на ERROR."""

    def __init__(self):
        self.client = docker.from_env()

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

        project_root = container.labels.get("fixops.project_path")

        if not project_root:
            log.error("Container has no fixops.project_path label")
            return

        history = deque(
            maxlen=max(
                settings.analysis.LOG_TAIL_LINES - 1,
                0,
            )
        )

        log.info("Started watching container logs")

        stream = container.logs(
            stdout=True,
            stderr=True,
            stream=True,
            follow=True,
            tail=0,
        )

        for raw_line in stream:
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
                await self.handle_error(
                    container=container,
                    data=data,
                    project_root=project_root,
                    history=history,
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

        error_log = {
            "file": extra["file"],
            "line": int(extra["line"]),
            "function": extra["function"],
            "error": extra["error"],
        }

        log.error(
            "Error detected: {}:{}",
            error_log["file"],
            error_log["line"],
        )

        logs_dir = f"{project_root}/.fixops"

        job = AnalyzeJob(
            project_root=project_root,
            error_log=error_log,
            logs_dir=logs_dir,
            extra_ignore_dirs=settings.analysis.EXTRA_IGNORE_DIRS,
        )

        await job.run()


async def main():
    """Точка запуска DockerLogWatcher."""
    watcher = DockerLogWatcher()
    await watcher.run()


if __name__ == "__main__":
    asyncio.run(main())
