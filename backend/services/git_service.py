import subprocess


class GitService:

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

        self._run(
            "git",
            "config",
            "--global",
            "--add",
            "safe.directory",
            self.repo_path,
        )

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(
            list(args),
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or f"Command failed: {' '.join(args)}"
            )

        return result

    def status(self) -> str:
        return self._run(
            "git",
            "status",
            "--short",
        ).stdout.strip()

    def current_branch(self) -> str:
        return self._run(
            "git",
            "branch",
            "--show-current",
        ).stdout.strip()

    def fetch(self) -> None:
        self._run(
            "git",
            "fetch",
            "origin",
        )

    def sync(self) -> None:
        """
        Синхронизирует локальную ветку с origin.

        Если remote впереди — выполняется rebase.
        При конфликте rebase автоматически прерывается.
        """

        self.fetch()

        branch = self.current_branch()

        if not branch:
            raise RuntimeError(
                "Cannot determine current Git branch"
            )

        result = subprocess.run(
            [
                "git",
                "rev-list",
                "--left-right",
                "--count",
                f"HEAD...origin/{branch}",
            ],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
            )

        ahead, behind = map(
            int,
            result.stdout.strip().split(),
        )

        if behind == 0:
            return

        try:
            self._run(
                "git",
                "rebase",
                f"origin/{branch}",
            )
        except RuntimeError:
            subprocess.run(
                [
                    "git",
                    "rebase",
                    "--abort",
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            raise RuntimeError(
                "Git rebase conflict. "
                "FixOps stopped before commit/push."
            )

    def add(self, files: list[str]) -> None:
        if not files:
            raise RuntimeError(
                "No files specified for git add"
            )

        self._run(
            "git",
            "add",
            "--",
            *files,
        )

    def commit(self, message: str) -> str:
        result = self._run(
            "git",
            "commit",
            "-m",
            message,
        )

        return result.stdout.strip()

    def push(self) -> str:
        branch = self.current_branch()

        if not branch:
            raise RuntimeError(
                "Cannot determine current Git branch"
            )

        return self._run(
            "git",
            "push",
            "origin",
            branch,
        ).stdout.strip()

    def restore(self) -> None:
        self._run(
            "git",
            "restore",
            ".",
        )

    def revert(self, commit_hash: str) -> str:
        return self._run(
            "git",
            "revert",
            "--no-edit",
            commit_hash,
        ).stdout.strip()
