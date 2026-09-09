import docker
import logging
import threading
import json
from collections import deque

from config import settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
)

logger = logging.getLogger("fixops")


def is_error(line: str) -> bool:
    try:
        data = json.loads(line)
        record = data.get("record", {})

        return (
            record.get("level", {}).get("name") == "ERROR"
            or record.get("extra", {}).get("severity") == "ERROR"
        )

    except json.JSONDecodeError:
        return False


def watch_container(container):
    history = deque(
        maxlen=max(settings.analysis.LOG_TAIL_LINES - 1, 0)
    )

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
            json.loads(line)
        except json.JSONDecodeError:
            continue

        if is_error(line):
            logs = list(history)
            logs.append(line)

            logger.info("ОШИБКА в %s", container.name)

            for log in logs:
                logger.info(log)

            continue

        history.append(line)


def main():
    client = docker.from_env()

    containers = client.containers.list(
        filters={
            "label": "fixops.enabled=true",
        }
    )

    for container in containers:
        threading.Thread(
            target=watch_container,
            args=(container,),
            daemon=True,
        ).start()

    threading.Event().wait()


if __name__ == "__main__":
    main()
