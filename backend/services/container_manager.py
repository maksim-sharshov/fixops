import docker
import subprocess

from config import settings
from services.git_service import GitService


def get_project_paths(container_id: str):

    client = docker.from_env()
    container = client.containers.get(container_id)

    container_project_path = container.labels.get(
        "fixops.project_path"
    )

    if not container_project_path:
        raise RuntimeError(
            "Container has no fixops.project_path label"
        )

    if not container_project_path.startswith(
        settings.paths.FIXOPS_PROJECTS_ROOT + "/"
    ):
        raise RuntimeError(
            f"Invalid FixOps project path: "
            f"{container_project_path}"
        )

    relative_path = container_project_path[
        len(settings.paths.FIXOPS_PROJECTS_ROOT) + 1:
    ]

    host_project_path = (
        f"{settings.paths.HOST_PROJECTS_ROOT}/{relative_path}"
    )

    subprocess.run(
        [
            "git",
            "config",
            "--global",
            "--add",
            "safe.directory",
            host_project_path,
        ],
        cwd=host_project_path,
        check=True,
    )

    return (
        container_project_path,
        host_project_path,
    )


def run_apply(container_id: str):
    (
        container_project_path,
        host_project_path,
    ) = get_project_paths(container_id)

    # 1. Apply изменения
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            f"{host_project_path}/docker-compose.yml",
            "--project-directory",
            host_project_path,
            "down",
        ],
        cwd=host_project_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr or result.stdout
        )

    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            f"{host_project_path}/docker-compose.yml",
            "--project-directory",
            host_project_path,
            "up",
            "--build",
            "-d",
        ],
        cwd=host_project_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr or result.stdout
        )

    # 2. Только после успешного Apply
    git = GitService(host_project_path)

    # 3. Синхронизация с remote
    git.sync()

    # 4. Забираем изменения FixOps
    files = git.changed_files()

    if not files:
        return result.stdout

    # 5. Commit
    git.add(files)

    git.commit(
        "fix: automated FixOps repair"
    )

    # 6. Push
    git.push()

    return result.stdout


def run_rollback(container_id: str):
    (
        container_project_path,
        host_project_path,
    ) = get_project_paths(container_id)

    subprocess.run(
        [
            "git",
            "config",
            "--global",
            "--add",
            "safe.directory",
            host_project_path,
        ],
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        [
            "git",
            "restore",
            ".",
        ],
        cwd=host_project_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr or result.stdout
        )

    return result.stdout
