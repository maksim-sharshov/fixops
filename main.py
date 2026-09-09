import asyncio
from services.docker_watcher import DockerLogWatcher


async def main():
    watcher = DockerLogWatcher()
    await watcher.run()


if __name__ == "__main__":
    asyncio.run(main())
