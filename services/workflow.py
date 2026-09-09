import os
import sys
import json
import asyncio
import subprocess

from uuid import uuid4
from typing import TypedDict, Dict, Any

from langgraph.graph import StateGraph, END

from core.decorators import log_execution
from core.logging import app_logger

from code_intel.indexer import ProjectIndexer
from code_intel.graph import GraphBuilder
from code_intel.error_analyzer import ErrorAnalyzer
from code_intel.context_builder import ContextBuilder
from code_intel.resolver import ProjectIndex, CallResolver
from code_intel.executor import FixExecutor

from ai.deepseek import DeepSeekHandler
from ai.groq import GroqHandler

from config import settings


class FixOpsState(TypedDict, total=False):

    job_id: str

    # Проект
    project_root: str
    error_log: dict
    logs_dir: str
    extra_ignore_dirs: tuple

    # LLM
    session_id: str | None
    llm_context: Any
    llm_prompt: str
    llm_response: str

    # Индекс проекта
    modules: Any
    indexer: Any
    index: Any
    graph: Any
    analysis_result: Dict

    # Исправление
    fixed_file: str | None
    fix_applied: bool
    fix_error: str | None

    # Тестирование
    test_command: list[str]
    tests_passed: bool
    reproduction_passed: bool
    test_return_code: int | None
    test_stdout: str
    test_stderr: str
    test_result_type: str | None

    # Retry
    fix_attempt: int
    max_fix_attempts: int
    retry_reason: str | None



# INDEXER
@log_execution(event="workflow_step", operation="indexer")
async def indexer_node(state: FixOpsState):

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



# GRAPH BUILDER
@log_execution(event="workflow_step", operation="graph_builder")
async def graph_builder_node(state: FixOpsState):

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



# ERROR ANALYZER
@log_execution(event="workflow_step", operation="error_analyzer")
async def error_analyzer_node(state: FixOpsState):

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



# CONTEXT BUILDER
@log_execution(event="workflow_step", operation="context_builder")
async def context_builder_node(state: FixOpsState):

    ctx = await ContextBuilder(
        state["project_root"]
    ).build_llm_context(
        state["index"],
        state["analysis_result"],
    )

    prompt = ContextBuilder.render_llm_prompt(ctx)

    # Если это retry — добавляем информацию
    # о предыдущем неудачном исправлении.
    retry_reason = state.get("retry_reason")

    if retry_reason:

        prompt += """

# ПРЕДЫДУЩАЯ ПОПЫТКА

Предыдущий patch уже был применён к проекту.

Он не прошёл тестирование.

ВАЖНО:

- предыдущий patch уже находится в текущем коде;
- НЕ пытайся применить его повторно;
- анализируй именно ТЕКУЩЕЕ состояние проекта;
- если предыдущий patch был неправильным, исправь текущий код;
- не возвращай проект искусственно к состоянию до предыдущего patch.

Результат предыдущего тестирования:

"""

        prompt += retry_reason

        prompt += """

Сначала заново определи ROOT CAUSE
в текущем состоянии проекта.

Затем выбери новый минимальный PATCH.

Regression-тест не должен придумывать новый
бизнес-контракт и не должен определять expected value
из выбранного PATCH.
"""

    attempt = state.get("fix_attempt", 0)

    prompt_path = os.path.join(
        state["logs_dir"],
        f"llm_prompt_{attempt}.md",
    )

    with open(
        prompt_path,
        "w",
        encoding="utf-8",
    ) as f:
        f.write(prompt)

    return {
        "llm_context": ctx,
        "llm_prompt": prompt,
    }



# LLM
@log_execution(event="workflow_step", operation="llm")
async def handle_fix_request(state: FixOpsState):

    # Номер текущей попытки.
    attempt = state.get("fix_attempt", 0) + 1

    session_id = state.get("session_id")

    if session_id is None:
        session_id = uuid4().hex

    if state.get("fix_attempt", 0) > 0:
        session_id = uuid4().hex

    # handler = GroqHandler(session_id=session_id)
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



# APPLY FIX
@log_execution(event="workflow_step", operation="apply_fix")
async def apply_fix_node(state: FixOpsState):

    try:

        data = json.loads(
            state["llm_response"]
        )

        if "choices" in data:

            content = data[
                "choices"
            ][0][
                "message"
            ][
                "content"
            ]

        else:
            content = state["llm_response"]

    except json.JSONDecodeError:

        content = state["llm_response"]

    executor = FixExecutor(
        project_root=state["project_root"]
    )

    try:

        file_path, changed = executor.apply_fix(
            content
        )

        return {
            "fixed_file": file_path,
            "fix_applied": changed,
            "fix_error": None,
        }

    except Exception as e:

        return {
            "fix_applied": False,
            "fix_error": str(e),
        }



# RUN TESTS
@log_execution(event="workflow_step", operation="run_tests")
async def run_tests_node(state: FixOpsState):

    command = (
        state.get("test_command")
        or ["pytest"]
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

        if state.get("fixed_file"):

            retry_reason += (
                "\nFILE CHANGED:\n"
                f"{state['fixed_file']}\n"
            )

    return {
        "tests_passed": result.success,
        "reproduction_passed": repro_passed,

        "test_return_code": (
            result.return_code
        ),

        "test_stdout": result.stdout,
        "test_stderr": result.stderr,

        "test_result_type": (
            result.result_type
        ),

        "retry_reason": retry_reason,
    }



# ROUTER: SHOULD CONTINUE TO CONTEXT
def should_continue_to_context(
    state: FixOpsState,
):

    if (
        state["analysis_result"]
        .get("resolved_node") is None
    ):
        return "end"

    return "build_context"



# ROUTER: AFTER APPLY FIX
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

    return "retry"



# ROUTER: AFTER TESTS
def should_retry(
    state: FixOpsState,
):

    # Успешные тесты.
    if state.get(
        "tests_passed",
        False,
    ):
        return "success"

    # Инфраструктурная ошибка.
    if state.get(
        "test_result_type"
    ) == "INFRA_FAILURE":

        app_logger.bind(
            event="workflow_step",
            operation="router",
        ).error(
            "Infrastructure failure detected, stopping."
        )

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

    return "retry"



# RETRY NODE
@log_execution(
    event="workflow_step",
    operation="prepare_retry",
)
async def prepare_retry_node(
    state: FixOpsState,
):

    """
    Retry НЕ генерирует новый prompt.

    Он только фиксирует факт неудачи.

    После этого workflow снова проходит:

        indexer
          ↓
        graph_builder
          ↓
        error_analyzer
          ↓
        context_builder
          ↓
        LLM

    Поэтому LLM получает уже изменённый проект.
    """

    attempt = state.get(
        "fix_attempt",
        0,
    )

    app_logger.bind(
        event="workflow_step",
        operation="prepare_retry",
    ).warning(
        f"Preparing retry #{attempt + 1}"
    )

    return {
        # Ничего не увеличиваем здесь.
        #
        # fix_attempt увеличивается непосредственно
        # перед новым вызовом LLM.
        "retry_reason": (
            state.get("retry_reason")
            or state.get("fix_error")
            or "Previous attempt failed."
        ),
    }



# CREATE WORKFLOW
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
        "prepare_retry",
        prepare_retry_node,
    )


    # INITIAL
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


    # APPLY FIX
    workflow.add_conditional_edges(
        "apply_fix",
        should_run_tests,
        {
            "run_tests": "run_tests",
            "retry": "prepare_retry",
            "failed": END,
        },
    )


    # TESTS


    workflow.add_conditional_edges(
        "run_tests",
        should_retry,
        {
            "success": END,
            "retry": "prepare_retry",
            "failed": END,
        },
    )

    # RETRY

    # ВАЖНО:
    #
    # После failed test мы НЕ идём сразу в LLM.
    #
    # Сначала повторно индексируем изменённый проект.
    #
    workflow.add_edge(
        "prepare_retry",
        "indexer",
    )

    return workflow.compile()
