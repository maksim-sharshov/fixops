import os
import sys
import json
import asyncio
import shutil
import subprocess

from uuid import uuid4
from typing import TypedDict, Dict, Any

from langgraph.graph import StateGraph, END

from config import settings
from core.logging import app_logger
from core.decorators import log_execution

from ai.deepseek import DeepSeekHandler
from code_intel.graph import GraphBuilder
from code_intel.executor import FixExecutor
from code_intel.indexer import ProjectIndexer
from code_intel.error_analyzer import ErrorAnalyzer
from code_intel.context_builder import ContextBuilder
from code_intel.resolver import ProjectIndex, CallResolver


class FixOpsState(TypedDict, total=False):
    job_id: str

    project_root: str
    error_log: dict
    logs_dir: str
    extra_ignore_dirs: tuple

    session_id: str | None
    llm_context: Any
    llm_prompt: str
    llm_response: str

    modules: Any
    indexer: Any
    index: Any
    graph: Any
    analysis_result: Dict

    fixed_file: str | None
    fix_applied: bool
    fix_error: str | None
    fix_diff: str | None

    test_command: list[str]
    tests_passed: bool
    reproduction_passed: bool
    test_return_code: int | None
    test_stdout: str
    test_stderr: str
    test_result_type: str | None

    fix_attempt: int
    max_fix_attempts: int
    retry_reason: str | None
    reset_error: str | None


# Сканирование проекта
@log_execution(event="workflow_step", operation="indexer")
async def indexer_node(state: FixOpsState):
    await asyncio.sleep(7)
    indexer = ProjectIndexer()

    ignore_dirs = (
        ProjectIndexer.IGNORE_DIRS
        + state.get("extra_ignore_dirs", ())
    )

    modules = await indexer.scan(
        state["project_root"],
        ignore_dirs=ignore_dirs,
    )

    index = indexer.to_dict(modules)

    os.makedirs(state["logs_dir"], exist_ok=True)

    with open(
        os.path.join(state["logs_dir"], "index.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            index,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return {
        "modules": modules,
        "indexer": indexer,
    }


# Построение карты связей кода
@log_execution(event="workflow_step", operation="graph_builder")
async def graph_builder_node(state: FixOpsState):
    await asyncio.sleep(0.2)
    idx = ProjectIndex(state["modules"])

    graph = await GraphBuilder(
        CallResolver(idx)
    ).build(idx)

    with open(
        os.path.join(state["logs_dir"], "graph.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            graph.to_dict(),
            f,
            ensure_ascii=False,
            indent=2,
        )

    return {
        "index": idx,
        "graph": graph,
    }


# Анализ ошибки
@log_execution(event="workflow_step", operation="error_analyzer")
async def error_analyzer_node(state: FixOpsState):
    await asyncio.sleep(0.2)
    analyzer = ErrorAnalyzer(
        state["index"],
        state["graph"],
    )

    result = await analyzer.analyze_error(
        state["error_log"]
    )

    return {
        "analysis_result": result,
    }


# Сбор контекста и генерация промпта
@log_execution(event="workflow_step", operation="context_builder")
async def context_builder_node(state: FixOpsState):
    await asyncio.sleep(0.2)
    ctx = await ContextBuilder(
        state["project_root"]
    ).build_llm_context(
        state["index"],
        state["analysis_result"],
    )

    prompt = ContextBuilder.render_llm_prompt(ctx)

    attempt = state.get("fix_attempt", 0)

    os.makedirs(
        state["logs_dir"],
        exist_ok=True,
    )

    with open(
        os.path.join(
            state["logs_dir"],
            f"llm_prompt_{attempt}.md",
        ),
        "w",
        encoding="utf-8",
    ) as f:
        f.write(prompt)

    return {
        "llm_context": ctx,
        "llm_prompt": prompt,
    }


# Запрос в ИИ
@log_execution(event="workflow_step", operation="llm")
async def handle_fix_request(state: FixOpsState):
    attempt = state.get("fix_attempt", 0) + 1

    session_id = uuid4().hex

    handler = DeepSeekHandler(
        session_id=session_id
    )

    try:
        content = await handler.generate_response(
            user_message=state["llm_prompt"]
        )
    except Exception as e:
        app_logger.bind(
            event="workflow_step",
            operation="llm",
        ).error(
            f"LLM request failed: {e}"
        )

        return {
            "session_id": session_id,
            "fix_attempt": attempt,
            "llm_response": json.dumps({
                "error": str(e)
            }),
        }

    os.makedirs(
        state["logs_dir"],
        exist_ok=True,
    )

    with open(
        os.path.join(
            state["logs_dir"],
            f"llm_response_{attempt}.txt",
        ),
        "w",
        encoding="utf-8",
    ) as f:
        f.write(content)

    return {
        "session_id": session_id,
        "fix_attempt": attempt,
        "llm_response": content,
    }


# Применение исправления
@log_execution(event="workflow_step", operation="apply_fix")
async def apply_fix_node(state: FixOpsState):
    try:
        data = json.loads(state["llm_response"])

        if "choices" in data:
            content = data["choices"][0]["message"]["content"]
        else:
            content = state["llm_response"]

    except json.JSONDecodeError:
        content = state["llm_response"]

    executor = FixExecutor(
        project_root=state["project_root"]
    )

    try:
        file_path = None

        # Запоминаем содержимое файлов до исправления
        before = {}

        for root, _, files in os.walk(state["project_root"]):
            for filename in files:
                if filename.endswith(".py"):
                    path = os.path.join(root, filename)

                    try:
                        with open(
                            path,
                            "r",
                            encoding="utf-8",
                        ) as f:
                            before[path] = f.read()
                    except Exception:
                        pass

        file_path, changed = executor.apply_fix(content)

        # Ищем реальные изменения
        changed_files = []
        diffs = []

        for path, old_content in before.items():
            if not os.path.exists(path):
                continue

            try:
                with open(
                    path,
                    "r",
                    encoding="utf-8",
                ) as f:
                    new_content = f.read()
            except Exception:
                continue

            if old_content != new_content:
                relative_path = os.path.relpath(
                    path,
                    state["project_root"],
                )

                changed_files.append(relative_path)

                import difflib

                diff = "".join(
                    difflib.unified_diff(
                        old_content.splitlines(True),
                        new_content.splitlines(True),
                        fromfile=relative_path,
                        tofile=relative_path,
                    )
                )

                if diff:
                    diffs.append(diff)

        return {
            "fixed_file": file_path,
            "fix_applied": changed,
            "fix_error": None,
            "fix_diff": "\n".join(diffs),
        }

    except Exception as e:
        return {
            "fix_applied": False,
            "fix_error": str(e),
            "fix_diff": None,
        }


# Запуск тестов
@log_execution(event="workflow_step", operation="run_tests")
async def run_tests_node(state: FixOpsState):
    command = (
        state.get("test_command")
        or [
            sys.executable,
            "-m",
            "pytest",
        ]
    )

    executor = FixExecutor(
        project_root=state["project_root"]
    )

    result = executor.run_tests(
        command=command
    )

    logger = app_logger.bind(
        event="workflow_step",
        operation="run_tests",
    )

    if result.success:
        logger.info(
            "TESTS PASSED: "
            + (
                result.stdout.splitlines()[-1]
                if result.stdout
                else "All tests passed"
            )
        )
    else:
        logger.error(
            "TESTS FAILED:\n"
            + (
                result.stderr
                or result.stdout
            )
        )

    repro_passed = False

    repro_script = os.path.join(
        state["project_root"],
        "reproduce.py",
    )

    if os.path.exists(repro_script):
        proc = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                repro_script,
            ],
            cwd=state["project_root"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        repro_passed = (
            proc.returncode == 0
        )

        if repro_passed:
            logger.info(
                "REPRODUCTION PASSED"
            )
        else:
            logger.error(
                "REPRODUCTION FAILED:\n"
                + (
                    proc.stderr
                    or proc.stdout
                )
            )

    retry_reason = None

    if not result.success:
        retry_reason = (
            "TEST RESULT\n\n"
            f"return_code: {result.return_code}\n"
            f"result_type: {result.result_type}\n\n"
            "STDOUT:\n"
            f"{result.stdout}\n\n"
            "STDERR:\n"
            f"{result.stderr}\n"
        )

    return {
        "tests_passed": result.success,
        "reproduction_passed": repro_passed,
        "test_return_code": result.return_code,
        "test_stdout": result.stdout,
        "test_stderr": result.stderr,
        "test_result_type": result.result_type,
        "retry_reason": retry_reason,
    }


# Полный откат проекта
@log_execution(
    event="workflow_step",
    operation="reset_project",
)
async def reset_project_node(state: FixOpsState):
    project_root = state["project_root"]

    logger = app_logger.bind(
        event="workflow_step",
        operation="reset_project",
    )

    logger.warning(
        "Resetting project to clean state"
    )

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "git",
                "-c",
                f"safe.directory={project_root}",
                "reset",
                "--hard",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            raise RuntimeError(
                "git reset --hard failed:\n"
                + (
                    result.stderr
                    or result.stdout
                )
            )

        fixops_dir = os.path.join(
            project_root,
            ".fixops",
        )

        if os.path.exists(fixops_dir):
            shutil.rmtree(fixops_dir)

        tests_dir = os.path.join(
            project_root,
            "tests",
        )

        if os.path.exists(tests_dir):
            shutil.rmtree(tests_dir)

        logger.info(
            "Project successfully reset"
        )

        return {
            "reset_error": None,
            "retry_reason": None,
        }

    except Exception as e:
        logger.error(
            f"Project reset failed: {e}"
        )

        return {
            "reset_error": str(e),
            "fix_error": str(e),
        }


# Проверяем, найден ли источник ошибки
def should_continue_to_context(
    state: FixOpsState,
):
    if (
        state["analysis_result"]
        .get("resolved_node") is None
    ):
        return "end"

    return "build_context"


# Проверяем результат применения исправления
def should_run_tests(
    state: FixOpsState,
):
    if state.get(
        "fix_applied",
        False,
    ):
        return "run_tests"

    attempt = state.get(
        "fix_attempt",
        0,
    )

    max_attempts = state.get(
        "max_fix_attempts",
        settings.analysis.MAX_FIX_ATTEMPTS,
    )

    if attempt >= max_attempts:
        return "failed"

    return "reset_project"


# Проверяем результат тестов
def should_retry(
    state: FixOpsState,
):
    if state.get(
        "tests_passed",
        False,
    ):
        return "success"

    if state.get(
        "test_result_type"
    ) == "INFRA_FAILURE":
        return "failed"

    attempt = state.get(
        "fix_attempt",
        0,
    )

    max_attempts = state.get(
        "max_fix_attempts",
        settings.analysis.MAX_FIX_ATTEMPTS,
    )

    if attempt >= max_attempts:
        return "failed"

    return "reset_project"


# Создание графа
def create_workflow():
    workflow = StateGraph(
        FixOpsState
    )

    workflow.add_node(
        "indexer",
        indexer_node,
    )

    workflow.add_node(
        "graph_builder",
        graph_builder_node,
    )

    workflow.add_node(
        "error_analyzer",
        error_analyzer_node,
    )

    workflow.add_node(
        "context_builder",
        context_builder_node,
    )

    workflow.add_node(
        "llm",
        handle_fix_request,
    )

    workflow.add_node(
        "apply_fix",
        apply_fix_node,
    )

    workflow.add_node(
        "run_tests",
        run_tests_node,
    )

    workflow.add_node(
        "reset_project",
        reset_project_node,
    )

    workflow.set_entry_point(
        "indexer"
    )

    workflow.add_edge(
        "indexer",
        "graph_builder",
    )

    workflow.add_edge(
        "graph_builder",
        "error_analyzer",
    )

    workflow.add_conditional_edges(
        "error_analyzer",
        should_continue_to_context,
        {
            "build_context": "context_builder",
            "end": END,
        },
    )

    workflow.add_edge(
        "context_builder",
        "llm",
    )

    workflow.add_edge(
        "llm",
        "apply_fix",
    )

    workflow.add_conditional_edges(
        "apply_fix",
        should_run_tests,
        {
            "run_tests": "run_tests",
            "reset_project": "reset_project",
            "failed": END,
        },
    )
    workflow.add_conditional_edges(
        "run_tests",
        should_retry,
        {
            "success": END,
            "reset_project": "reset_project",
            "failed": END,
        },
    )

    workflow.add_edge(
        "reset_project",
        "indexer",
    )

    return workflow.compile()
