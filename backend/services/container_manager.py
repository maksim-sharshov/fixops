import subprocess


def run_apply(container_id: str):
    project_path = get_project_path(container_id)

    result = subprocess.run(
        [
            "docker",
            "compose",
            "down",
        ],
        cwd=project_path,
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
            "up",
            "--build",
            "-d",
        ],
        cwd=project_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr or result.stdout
        )

    return result.stdout


def run_rollback(container_id: str):
    project_path = get_project_path(container_id)

    result = subprocess.run(
        [
            "git",
            "restore",
            ".",
        ],
        cwd=project_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr or result.stdout
        )

    return result.stdout


def get_project_path(container_id: str):
    import docker

    client = docker.from_env()

    container = client.containers.get(container_id)

    project_path = container.labels.get(
        "fixops.project_path"
    )

    if not project_path:
        raise RuntimeError(
            "Container has no fixops.project_path label"
        )

    return project_path
