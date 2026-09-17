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
import asyncio
import contextlib
import json
import os
import re
import sys
from uuid import uuid4

from code_intel.html_view import save_html_view
from config import settings
from core.events import events
from core.logging import app_logger
from db.psql.models.models import IncidentResult
from services.workflow import FixOpsState, create_workflow

WORKFLOW_STEP_ORDER = (
    "indexer",
    "graph_builder",
    "error_analyzer",
    "context_builder",
    "llm",
    "code_fixer",
    "test_runner",
)

NODE_TO_STEP = {
    "indexer": "indexer",
    "graph_builder": "graph_builder",
    "error_analyzer": "error_analyzer",
    "context_builder": "context_builder",
    "llm": "llm",
    "apply_fix": "code_fixer",
    "run_tests": "test_runner",
}

TEST_BLOCK_RE = re.compile(r"```test\s*(.*?)```", re.DOTALL)


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
        container_id: str | None = None,
        container_name: str | None = None,
        project: str | None = None,
    ):
        self.project_root = os.path.abspath(project_root)
        self.error_log = error_log
        self.logs_dir = os.path.abspath(logs_dir or os.path.join(self.project_root, "logs"))
        self.extra_ignore_dirs = tuple(extra_ignore_dirs)
        self.workflow = create_workflow()
        self.job_id = job_id or uuid4().hex
        self.container_id = container_id
        self.container_name = container_name
        self.project = project

    # ----------------------------------------------------------------
    # Персистенция инцидента (Postgres)
    # ----------------------------------------------------------------

    def _format_error_message(self) -> str:
        """error_log['error'] — либо dict {type, message}, либо строка."""
        error = self.error_log.get("error")

        if isinstance(error, dict):
            error_type = error.get("type") or ""
            message = error.get("message") or ""
            return f"{error_type}: {message}".strip(": ") or str(error)

        return str(error) if error is not None else ""

    def _format_error_location(self) -> str:
        file = self.error_log.get("file") or ""
        with contextlib.suppress(ValueError):
            file = os.path.relpath(file, self.project_root)
        file = file.replace(os.sep, "/")
        return (
            f"{file}:{self.error_log.get('line')} "
            f"in {self.error_log.get('function')}()"
        )

    @staticmethod
    def _initial_steps() -> list[dict]:
        return [{"id": step, "state": "pending"} for step in WORKFLOW_STEP_ORDER]

    def _build_steps(self) -> list[dict]:
        """Собирает состояния шагов из событий workflow для этого job."""
        states = dict.fromkeys(WORKFLOW_STEP_ORDER, "pending")

        for event in events.history.get(self.job_id, []):
            step = NODE_TO_STEP.get(event.get("node"))
            if step is None:
                continue

            kind = event.get("event")
            if kind == "node_started":
                states[step] = "active"
            elif kind == "node_completed":
                states[step] = "completed"
            elif kind == "node_failed":
                states[step] = "failed"

        return [{"id": step, "state": states[step]} for step in WORKFLOW_STEP_ORDER]

    @staticmethod
    def _serialize_context(context) -> str | None:
        if context is None:
            return None
        if isinstance(context, str):
            return context
        try:
            return json.dumps(context, ensure_ascii=False)
        except TypeError:
            return str(context)

    @staticmethod
    def _extract_generated_tests(llm_response: str | None) -> list[str] | None:
        if not llm_response:
            return None
        blocks = [block.strip() for block in TEST_BLOCK_RE.findall(llm_response)]
        return blocks or None

    async def _create_incident(self) -> None:
        """Создаёт запись инцидента со статусом repairing до запуска workflow."""
        try:
            await IncidentResult.create(
                job_id=self.job_id,
                container_id=self.container_id,
                container_name=self.container_name,
                project=self.project,
                error_message=self._format_error_message(),
                error_location=self._format_error_location(),
                status="repairing",
                steps=self._initial_steps(),
            )
        except Exception:
            app_logger.bind(event="incident.persist").exception(
                "Failed to create incident record for job {}",
                self.job_id,
            )

    async def _persist_result(self, final_state: dict) -> None:
        """Обновляет запись инцидента итогами workflow."""
        try:
            record = await IncidentResult.get(job_id=self.job_id)
            if record is None:
                return

            await record.update(
                status="resolved" if final_state.get("tests_passed") else "failed",
                steps=self._build_steps(),
                llm_prompt=final_state.get("llm_prompt"),
                ai_context=self._serialize_context(final_state.get("llm_context")),
                fixed_file=final_state.get("fixed_file"),
                fix_diff=final_state.get("fix_diff"),
                tests_passed=final_state.get("tests_passed"),
                test_return_code=final_state.get("test_return_code"),
                test_result_type=final_state.get("test_result_type"),
                reproduction_passed=final_state.get("reproduction_passed"),
                test_stdout=final_state.get("test_stdout"),
                test_stderr=final_state.get("test_stderr"),
                generated_tests=self._extract_generated_tests(
                    final_state.get("llm_response")
                ),
            )
        except Exception:
            app_logger.bind(event="incident.persist").exception(
                "Failed to persist incident result for job {}",
                self.job_id,
            )

    async def analyze(self) -> dict:
        """Возвращает результат анализа + артефакты для сохранения."""

        await self._create_incident()

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

            llm_prompt=final_state.get("llm_prompt", ""),
            llm_response=final_state.get("llm_response", ""),

            # Тесты
            tests_passed=final_state.get("tests_passed"),
            test_return_code=final_state.get("test_return_code"),
            test_stdout=final_state.get("test_stdout", ""),
            test_stderr=final_state.get("test_stderr", "")
        )

        await self._persist_result(final_state)

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
