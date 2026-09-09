import docker
import logging
import threading
import json
from collections import deque

from config import settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("fixops")


def is_error(line: str) -> bool:
    """
    Проверяет, является ли лог ошибкой.

    Основной формат — JSON от Loguru с serialize=True.
    """

    try:
        data = json.loads(line)

        record = data.get("record", {})
        level = record.get("level", {})

        if level.get("name") == "ERROR":
            return True

        severity = record.get("extra", {}).get("severity")

        if severity == "ERROR":
            return True

    except json.JSONDecodeError:
        pass

    return False


def handle_error(container, logs: list[str]):
    """
    Получает последние LOG_TAIL_LINES логов,
    где последняя строка — обнаруженная ERROR.

    Здесь дальше будет запускаться анализ FixOps.
    """

    logger.error(
        "Error detected in container: %s",
        container.name,
    )

    logger.info(
        "Collected %d log(s) for analysis",
        len(logs),
    )

    for line in logs:
        logger.info("[ANALYSIS LOG] %s", line)

    # ==================================================
    # ЗДЕСЬ ДАЛЬШЕ ПЕРЕДАЁМ logs В AnalyzeJob
    # ==================================================

    # Например в будущем:
    #
    # asyncio.run(
    #     run_fixops_analysis(
    #         container=container,
    #         logs=logs,
    #     )
    # )


def watch_container(container):
    """
    Слушает контейнер в реальном времени.

    Старые логи НЕ читаются.
    В history находятся только логи,
    появившиеся после запуска FixOps.
    """

    logger.info("Watching %s", container.name)

    # Храним последние N новых логов.
    history = deque(
        maxlen=settings.analysis.LOG_TAIL_LINES
    )

    try:
        stream = container.logs(
            stdout=True,
            stderr=True,
            stream=True,
            follow=True,

            # КРИТИЧЕСКИ ВАЖНО:
            # старые Docker-логи не получаем.
            tail=0,
        )

        for raw_line in stream:

            line = raw_line.decode(
                "utf-8",
                errors="replace",
            ).rstrip()

            if not line:
                continue

            # Нас интересуют только JSON-логи Loguru.
            try:
                json.loads(line)

            except json.JSONDecodeError:
                continue

            # Добавляем каждый новый лог в историю.
            history.append(line)

            # Если это ошибка —
            # берём последние N логов.
            if is_error(line):

                logs_for_analysis = list(history)

                logger.error(
                    "[FOUND ERROR] %s",
                    line,
                )

                # Передаём последние N логов дальше.
                handle_error(
                    container,
                    logs_for_analysis,
                )

    except Exception:

        logger.exception(
            "Watcher failed for %s",
            container.name,
        )


def main():

    logger.info("FixOps started")

    logger.info(
        "Log context size: %d",
        settings.analysis.LOG_TAIL_LINES,
    )

    client = docker.from_env()

    containers = client.containers.list(
        filters={
            "label": "fixops.enabled=true"
        }
    )

    logger.info(
        "Found %d target container(s)",
        len(containers),
    )

    for container in containers:

        thread = threading.Thread(
            target=watch_container,
            args=(container,),
            daemon=True,
        )

        thread.start()

    # FixOps продолжает работать.
    threading.Event().wait()


if __name__ == "__main__":
    main()
