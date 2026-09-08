import docker
import logging
import threading
import json


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("fixops")


def is_error(line: str) -> bool:
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

    # Обычный текстовый лог
    upper_line = line.upper()

    return (
        upper_line.startswith("ERROR:")
        or "TRACEBACK (MOST RECENT CALL LAST)" in upper_line
        or "KEYERROR:" in upper_line
        or "VALUEERROR:" in upper_line
        or "TYPEERROR:" in upper_line
        or "EXCEPTION:" in upper_line
    )

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

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            record = data.get("record", {})
            level = record.get("level", {})

            if level.get("name") != "ERROR":
                continue

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
