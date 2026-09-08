import docker
import logging
import threading


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("fixops")


def watch_container(container):
    logger.info("Watching %s", container.name)

    try:
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

            if "ERROR" in line.upper():
                logger.error(
                    "[FOUND ERROR] %s",
                    line,
                )

    except Exception:
        logger.exception(
            "Watcher failed for %s",
            container.name,
        )


def main():
    logger.info("FixOps started")

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

    threading.Event().wait()


if __name__ == "__main__":
    main()
