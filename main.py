import docker
import logging
import threading
from datetime import datetime, timezone


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("fixops")


def watch_container(container, started_at):
    logger.info("Started watching %s", container.name)

    try:
        for raw_line in container.logs(
            stream=True,
            follow=True,
            timestamps=True,
            since=started_at,
        ):
            line = raw_line.decode(
                "utf-8",
                errors="replace",
            ).rstrip()

            if "ERROR" in line.upper():
                logger.error(
                    "[FOUND ERROR] %s",
                    line,
                )
            else:
                logger.info(
                    "[LOG] %s",
                    line,
                )

    except Exception:
        logger.exception(
            "Error while watching %s",
            container.name,
        )


def main():
    logger.info("FixOps started")

    # Фиксируем момент запуска FixOps.
    # Всё, что было раньше этого времени, нас НЕ интересует.
    started_at = datetime.now(timezone.utc)

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

    threads = []

    for container in containers:
        thread = threading.Thread(
            target=watch_container,
            args=(container, started_at),
            daemon=True,
        )

        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
