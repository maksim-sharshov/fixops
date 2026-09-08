import docker
import logging
import time


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("fixops-reader")


def main():
    logger.info("FixOps Log Reader started")

    client = docker.from_env()

    while True:
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
            logger.info(
                "Reading logs from %s",
                container.name,
            )

            logs = container.logs(
                tail=10,
                timestamps=True,
            ).decode(
                "utf-8",
                errors="replace",
            )

            for line in logs.splitlines():
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

        time.sleep(3)


if __name__ == "__main__":
    main()
