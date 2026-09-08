import docker
import logging
import threading
import time


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("fixops")


def watch_container(container, started_at):
    logger.info("Watching %s", container.name)

    try:
        stream = container.logs(
            stdout=True,
            stderr=True,
            stream=True,
            follow=True,
            timestamps=True,
            since=started_at,
        )

        for raw_line in stream:
            line = raw_line.decode(
                "utf-8",
                errors="replace",
            ).rstrip()

            if not line:
                continue

            # Нам нужны ТОЛЬКО ошибки.
            if "ERROR" in line.upper():
                logger.error(
                    "[NEW ERROR] %s",
                    line,
                )

    except Exception:
        logger.exception(
            "Watcher failed for %s",
            container.name,
        )


def main():
    logger.info("FixOps started")

    # Момент запуска FixOps.
    # Всё, что было ДО него, игнорируем.
    started_at = time.time()

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
            args=(container, started_at),
            daemon=True,
        )

        thread.start()

    threading.Event().wait()


if __name__ == "__main__":
    main()
