import os
import re
import ast
import difflib
import subprocess
from pathlib import Path
from dataclasses import dataclass

from core.decorators import log_execution, get_logger


@dataclass
class TestResult:
    success: bool
    return_code: int
    stdout: str
    stderr: str
    result_type: str  # 'SUCCESS', 'CODE_FAILURE', 'INFRA_FAILURE'


class FixExecutor:

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)

    @staticmethod
    def _remove_duplicate_returns(content: str) -> str:
        """Удаляет дублированные return statements в функциях."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return content  # Если синтаксис сломан, не трогаем

        lines = content.split("\n")
        lines_to_remove = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                returns = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Return):
                        returns.append(child.lineno)

                # Если есть дублированные return на разных строках
                if len(returns) > 1:
                    # Проверяем, идут ли они подряд
                    for i in range(len(returns) - 1):
                        if returns[i + 1] == returns[i] + 1:
                            # Второй return — дубль, помечаем для удаления
                            lines_to_remove.add(returns[i + 1] - 1)  # 0-based

        # Удаляем помеченные строки
        if lines_to_remove:
            new_lines = [
                line for idx, line in enumerate(lines)
                if idx not in lines_to_remove
            ]
            return "\n".join(new_lines)

        return content

    @staticmethod
    def _normalize(text: str) -> str:
        """Нормализует текст для сравнения: унифицирует окончания строк,
        убирает концевые пробелы на каждой строке."""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in text.split("\n")]
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

    @staticmethod
    def _find_best_match(search: str, content: str) -> tuple[str | None, float]:
        """Ищет наилучшее совпадение search в content с помощью difflib.
        Возвращает (найденный фрагмент, коэффициент схожести)."""
        search_norm = FixExecutor._normalize(search)
        content_norm = FixExecutor._normalize(content)

        # Сначала точное совпадение
        if search_norm in content_norm:
            return search, 1.0

        # Ищем построчно через SequenceMatcher
        search_lines = search_norm.split("\n")
        content_lines = content_norm.split("\n")

        best_ratio = 0.0
        best_start = -1
        best_end = -1

        n_search = len(search_lines)
        # Скользящее окно по content
        for i in range(len(content_lines) - n_search + 1):
            window = content_lines[i:i + n_search]
            matcher = difflib.SequenceMatcher(None, search_lines, window)
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_start = i
                best_end = i + n_search

        if best_ratio >= 0.85 and best_start >= 0:
            # Возвращаем оригинальные строки (с оригинальными окончаниями)
            original_lines = content.split("\n")
            matched = "\n".join(original_lines[best_start:best_end])
            return matched, best_ratio

        return None, best_ratio

    @log_execution(event="executor.apply_fix")
    def apply_fix(self, response: str) -> tuple[str | None, bool]:
        """Применяет исправления и создаёт тесты из ответа LLM."""
        log = get_logger(event="executor.apply_fix")

        fix_blocks = re.findall(
            r"```fix\s*(.*?)```",
            response,
            re.DOTALL,
        )

        if not fix_blocks:
            raise ValueError(
                "LLM response does not contain ```fix block"
            )

        any_changed = False
        last_file_path = None

        for idx, fix_block in enumerate(fix_blocks, 1):
            match = re.search(
                r"FILE:\s*(.+?)\n"
                r"<<<<<<< SEARCH\n"
                r"(.*?)"
                r"\n=======\n"
                r"(.*?)"
                r"\n>>>>>>> REPLACE",
                fix_block,
                re.DOTALL,
            )

            if not match:
                log.warning(
                    "Invalid fix block, skipping",
                    fix_number=idx,
                )
                continue

            file_path = match.group(1).strip()
            search = match.group(2)
            replace = match.group(3)

            replace = re.sub(
                r'(\n[ \t]*return total)(\n[ \t]*return total)+',
                r'\1',
                replace,
            )

            path = self.project_root / file_path

            if not path.exists():
                log.warning(
                    "File not found, skipping",
                    file=file_path,
                )
                continue

            content = path.read_text(
                encoding="utf-8"
            )

            matched_fragment = None
            match_type = None

            if search in content:
                matched_fragment = search
                match_type = "exact"

            else:
                search_norm = self._normalize(search)
                content_norm = self._normalize(content)

                if search_norm in content_norm:
                    matched_fragment = search
                    match_type = "normalized"

                else:
                    fuzzy_match, ratio = self._find_best_match(
                        search,
                        content,
                    )

                    if fuzzy_match is not None:
                        matched_fragment = fuzzy_match
                        match_type = "fuzzy"

                        log.warning(
                            "Fuzzy match used",
                            file=file_path,
                            similarity=f"{ratio:.2%}",
                        )

            if matched_fragment is None:
                log.error(
                    "Search block not found",
                    file=file_path,
                )
                continue

            new_content = content.replace(
                matched_fragment,
                replace,
                1,
            )

            path.write_text(
                new_content,
                encoding="utf-8",
            )

            any_changed = True
            last_file_path = file_path

            log.info(
                "Fix applied",
                file=file_path,
                match=match_type,
            )

        test_blocks = re.findall(
            r"```test\s*(.*?)```",
            response,
            re.DOTALL,
        )

        for idx, test_block in enumerate(test_blocks, 1):
            file_match = re.search(
                r"FILE:\s*(.+?)\n(.*)",
                test_block,
                re.DOTALL,
            )

            if not file_match:
                log.warning(
                    "Invalid test block, skipping",
                    test_number=idx,
                )
                continue

            test_path = (
                self.project_root
                / file_match.group(1).strip()
            )

            test_content = file_match.group(2).strip()

            test_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            test_path.write_text(
                test_content,
                encoding="utf-8",
            )

            any_changed = True

            log.info(
                "Test created",
                file=str(
                    test_path.relative_to(
                        self.project_root
                    )
                ),
            )

        return last_file_path, any_changed


    def _find_python_root(self) -> Path:
        candidates = [
            self.project_root,
            self.project_root / "backend",
            self.project_root / "src",
        ]

        for path in candidates:
            if not path.is_dir():
                continue

            if (
                (path / "app").is_dir()
                or (path / "src").is_dir()
            ):
                return path

            pyproject = path / "pyproject.toml"
            setup_py = path / "setup.py"

            if pyproject.exists() or setup_py.exists():
                return path

        return self.project_root


    def run_tests(self, command: list[str]) -> TestResult:
        env = os.environ.copy()

        python_root = self._find_python_root()

        env["PYTHONPATH"] = (
            f"{python_root}{os.pathsep}{self.project_root}"
        )

        env["LOG_DIR"] = str(self.project_root / "logs")
        env["APP_LOG_DIR"] = str(self.project_root / "logs")

        process = subprocess.run(
            command,
            cwd=self.project_root,
            env=env,
            capture_output=True,
            text=True,
        )

        if process.returncode == 0:
            result_type = "SUCCESS"

        elif process.returncode == 5:
            result_type = "CODE_FAILURE"
            print("DEBUG: No tests collected (pytest exit code 5).")

        elif (
            "ModuleNotFoundError" in (process.stderr + process.stdout)
            or "ImportError" in (process.stderr + process.stdout)
        ):
            result_type = "INFRA_FAILURE"

        elif process.returncode == 1:
            result_type = "CODE_FAILURE"

        else:
            result_type = "INFRA_FAILURE"
            print(
                f"DEBUG: Infrastructure failure. "
                f"Pytest returncode: {process.returncode}"
            )

        return TestResult(
            success=process.returncode == 0,
            return_code=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
            result_type=result_type,
        )
