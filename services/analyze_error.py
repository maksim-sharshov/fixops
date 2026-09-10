"""
analyze_error.py — статический анализ ошибки по графу вызовов проекта.

Пути вписываются прямо в код ниже (блок КОНФИГУРАЦИЯ): путь к корню
проекта и путь к файлу с логами. Запуск обычный:

    python analyze_error.py

Скрипт:
  - читает лог-файл проекта (<корень проекта>/logs/app.log) и из последней
    ERROR-записи достаёт ошибку в формате {file, line, function, error};
  - индексирует проект (AST, без выполнения кода);
  - строит граф вызовов;
  - находит узел ошибки и раскладывает его на цепочку callers/callees;
  - собирает финальный промпт для LLM с реальным исходным кодом функций.

Все артефакты, как в demo.py, складываются в каталог логов пайплайна (LOGS_DIR):
  - index.json               — AST-индекс проекта
  - graph.json               — граф вызовов (для визуализации)
  - last_error_analysis.json — цепочка/координаты ошибки
  - llm_prompt.md            — ИТОГОВЫЙ промпт, который уходит в LLM
"""
import os
import sys
import json
import asyncio
from uuid import uuid4

from config import settings
from core.events import events
from code_intel.html_view import save_html_view
from services.workflow import create_workflow, FixOpsState


# Принудительно устанавливаем UTF-8 для стандартного вывода
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


class ErrorLoader:
    """Читает последнюю ERROR-запись из хвоста лог-файла проекта (loguru, serialize=True).

    Читаются не все строки, а только последние LOG_TAIL_LINES — ошибка почти
    всегда в конце лога. Формат строки — JSON:
    {"text": ..., "record": {"level": {...}, "extra": {...}}}.
    Из extra последней ERROR-записи (checkout failed в reproduce.py) достаются
    координаты ошибки: file / line / function / error.
    """

    @staticmethod
    def _sync_tail(path: str, n: int) -> list[str]:
        """Читает последние n строк файла, не загружая его целиком."""
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 8192
            data = b""
            while size > 0 and data.count(b"\n") <= n:
                read = min(block, size)
                size -= read
                f.seek(size)
                data = f.read(read) + data
        return [
            ln.decode("utf-8", errors="replace")
            for ln in data.splitlines()[-n:]
        ]

    @staticmethod
    async def from_file(path: str, tail: int = settings.analysis.LOG_TAIL_LINES) -> dict:
        lines = await asyncio.to_thread(ErrorLoader._sync_tail, path, tail)
        if not lines:
            raise ValueError(f"Лог-файл пуст: {path}")

        for raw in reversed(lines):
            try:
                record = json.loads(raw).get("record", {})
            except json.JSONDecodeError:
                continue  # не-json строка (например, обрыв записи) — пропускаем
            level = (record.get("level") or {}).get("name")
            extra = record.get("extra") or {}
            if level == "ERROR" and all(extra.get(k) is not None for k in settings.analysis.REQUIRED_ERROR_KEYS):
                return {
                    "file": extra["file"],
                    "line": int(extra["line"]),
                    "function": extra["function"],
                    "error": extra["error"],
                }

        raise ValueError(
            f"В последних {tail} строках лога {path} не найдено ERROR-записи "
            f"с координатами ошибки ({', '.join(settings.analysis.REQUIRED_ERROR_KEYS)}). "
        )


class AnalyzeJob:
    """Полный статический анализ одного лога ошибки в заданном проекте."""

    def __init__(
        self,
        project_root: str,
        error_log: dict,
        logs_dir: str | None = None,
        extra_ignore_dirs: tuple = (),
        job_id: str | None = None,
    ):
        self.project_root = os.path.abspath(project_root)
        self.error_log = error_log
        self.logs_dir = os.path.abspath(logs_dir or os.path.join(self.project_root, "logs"))
        self.extra_ignore_dirs = tuple(extra_ignore_dirs)
        self.workflow = create_workflow()
        self.job_id = job_id or uuid4().hex

    async def analyze(self) -> dict:
        """Возвращает результат анализа + артефакты для сохранения."""

        await events.emit(
            self.job_id,
            "workflow_started",
        )

        initial_state: FixOpsState = {
            "job_id": self.job_id,
            "project_root": self.project_root,
            "error_log": self.error_log,
            "logs_dir": self.logs_dir,
            "extra_ignore_dirs": self.extra_ignore_dirs,

            "session_id": None,

            "modules": None,
            "indexer": None,
            "index": None,
            "graph": None,
            "analysis_result": {},

            "llm_context": None,
            "llm_prompt": "",
            "llm_response": "",

            "fixed_file": None,
            "fix_applied": False,
            "fix_error": None,
            "fix_diff": None,

            "test_command": [],
            "tests_passed": False,
            "reproduction_passed": False,
            "test_return_code": None,
            "test_stdout": "",
            "test_stderr": "",
            "test_result_type": None,

            "fix_attempt": 0,
            "max_fix_attempts": settings.analysis.MAX_FIX_ATTEMPTS,
        }
        final_state = await self.workflow.ainvoke(initial_state)

        await events.emit(
            self.job_id,
            "workflow_finished",
            status="success" if final_state.get("tests_passed") else "failed",
            attempts=final_state.get("fix_attempt", 0),

            # Что исправили
            fixed_file=final_state.get("fixed_file"),
            fix_applied=final_state.get("fix_applied"),
            fix_diff=final_state.get("fix_diff"),

            # Тесты
            tests_passed=final_state.get("tests_passed"),
            reproduction_passed=final_state.get(
                "reproduction_passed"
            ),
            test_return_code=final_state.get(
                "test_return_code"
            ),
            test_result_type=final_state.get(
                "test_result_type"
            ),

            # Что отправляли LLM
            llm_prompt=final_state.get("llm_prompt"),
        )

        # Отображение результата обратно в исходный формат артефакта для экономии времени
        return {
            "index": final_state["indexer"].to_dict(final_state["modules"]), # Используем indexer для генерации dict
            "graph": final_state["graph"].to_dict(),
            "analysis": final_state["analysis_result"],
            "prompt": final_state.get("llm_prompt")
        }

    @staticmethod
    def _sync_write_json(path: str, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def _write_json(self, path: str, data: dict) -> None:
        await asyncio.to_thread(self._sync_write_json, path, data)

    async def _save_artifacts(self, artifacts: dict) -> None:
        await asyncio.to_thread(os.makedirs, self.logs_dir, exist_ok=True)
        await self._write_json(os.path.join(self.logs_dir, "index.json"), artifacts["index"])
        await self._write_json(os.path.join(self.logs_dir, "graph.json"), artifacts["graph"])
        await self._write_json(os.path.join(self.logs_dir, "last_error_analysis.json"), artifacts["analysis"])

        await save_html_view(
            artifacts["graph"],
            artifacts["analysis"],
            os.path.join(self.logs_dir, "graph_view.html"),
        )

    async def run(self) -> int:

        artifacts = await self.analyze()
        result = artifacts["analysis"]

        await self._save_artifacts(artifacts)
        if result.get("resolved_node") is None:
            print(result["message"])
            return 1
        return 0
