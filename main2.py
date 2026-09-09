import os
import sys
import asyncio
from pathlib import Path

from config import settings
from services.analyze_error import *

async def main(project_path: str) -> int:

    base_dir = Path(__file__).resolve().parent.parent
    project_root = str(base_dir / project_path)

    error_log_path = os.path.join(project_root, "logs", "app.log")
    logs_dir = os.path.join(project_root, ".fixops")

    if not os.path.isdir(project_root):
        sys.stderr.write(f"Не найдена папка проекта: {project_root}\n")
        return 2
    if not os.path.isfile(error_log_path):
        sys.stderr.write(f"Не найден лог-файл проекта: {error_log_path}\n")
        return 2

    try:
        error_log = await ErrorLoader.from_file(error_log_path)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"Ошибка чтения лога: {exc}\n")
        return 2

    job = AnalyzeJob(project_root, error_log, logs_dir=logs_dir,
                     extra_ignore_dirs=settings.analysis.EXTRA_IGNORE_DIRS)
    return await job.run()


if __name__ == "__main__":
    project_path = r"D:\Programs\fixops-workspaces\fast_api_test_project"
    asyncio.run(main(project_path=project_path))
