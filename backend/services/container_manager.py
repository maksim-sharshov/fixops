import docker
import subprocess

HOST_PROJECTS_ROOT = "/home/virtu/projects"
FIXOPS_PROJECTS_ROOT = "/projects"


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
        FIXOPS_PROJECTS_ROOT + "/"
    ):
        raise RuntimeError(
            f"Invalid FixOps project path: "
            f"{container_project_path}"
        )

    relative_path = container_project_path[
        len(FIXOPS_PROJECTS_ROOT) + 1:
    ]

    host_project_path = (
        f"{HOST_PROJECTS_ROOT}/{relative_path}"
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

    return result.stdout


def run_rollback(container_id: str):
    (
        container_project_path,
        host_project_path,
    ) = get_project_paths(container_id)

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
