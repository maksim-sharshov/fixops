import time
import inspect
import functools
import traceback

from core.events import events
from core.logging import get_logger


SENSITIVE_FIELDS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "secret",
}


NODE_LABELS_RU = {
    "indexer": "Сканирование проекта",
    "graph_builder": "Построение графа связей",
    "error_analyzer": "Анализ ошибки",
    "context_builder": "Сбор контекста",
    "llm": "Запрос к LLM",
    "apply_fix": "Применение исправления",
    "run_tests": "Запуск тестов",
    "reset_project": "Откат проекта",
}


def sanitize(value):
    """
    Удаляет потенциально чувствительные данные
    перед записью в лог.
    """

    if isinstance(value, dict):
        return {
            key: "***"
            if key.lower() in SENSITIVE_FIELDS
            else sanitize(val)
            for key, val in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            sanitize(item)
            for item in value
        ]

    if isinstance(value, (str, int, float, bool, type(None))):
        return value

    return f"<{type(value).__name__}>"


def log_execution(
    event: str,
    operation: str | None = None,
):
    """
    Логирует выполнение sync/async функции.

    Для FixOps async-ноды дополнительно отправляет события:

        node_started
        node_completed
        node_failed

    При ошибке записывает:

        file       — файл, где реально произошла ошибка
        line       — строка ошибки
        function   — функция, где произошла ошибка
        error      — тип и сообщение ошибки
        arguments  — аргументы функции
    """

    def decorator(func):

        operation_name = operation or func.__name__

        # ASYNC
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):

                start = time.perf_counter()

                # FixOps state находится первым аргументом
                state = (
                    args[0]
                    if args and isinstance(args[0], dict)
                    else None
                )

                job_id = (
                    state.get("job_id")
                    if state
                    else None
                )

                label = NODE_LABELS_RU.get(
                    operation_name,
                    operation_name,
                )

                attempt = (
                    state.get("fix_attempt", 0)
                    if state
                    else 0
                )

                # NODE STARTED
                if job_id:
                    await events.emit(
                        job_id,
                        "node_started",
                        node=operation_name,
                        label=label,
                        attempt=attempt,
                    )

                log = get_logger(
                    event=event,
                    operation=operation_name,
                    function=func.__qualname__,
                    module=func.__module__,
                )

                log.debug("Function started")

                try:

                    # EXECUTE
                    result = await func(
                        *args,
                        **kwargs,
                    )

                    duration_ms = (
                        time.perf_counter() - start
                    ) * 1000


                    # LOG SUCCESS
                    log.bind(
                        status="success",
                        severity="INFO",
                        duration_ms=round(
                            duration_ms,
                            2,
                        ),
                    ).info(
                        "Function completed"
                    )


                    # NODE COMPLETED
                    if job_id:
                        await events.emit(
                            job_id,
                            "node_completed",
                            node=operation_name,
                            label=label,
                            duration_ms=int(
                                duration_ms
                            ),
                            data=_summarize(
                                operation_name,
                                result,
                            ),
                        )

                    return result

                except Exception as exc:

                    duration_ms = (
                        time.perf_counter() - start
                    ) * 1000

                    tb = traceback.extract_tb(
                        exc.__traceback__
                    )

                    last = tb[-1] if tb else None


                    # ERROR DATA
                    file = (
                        last.filename
                        if last
                        else None
                    )

                    line = (
                        last.lineno
                        if last
                        else None
                    )

                    function = (
                        last.name
                        if last
                        else None
                    )

                    error_data = {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    }


                    # LOG ERROR
                    log.bind(
                        status="error",
                        severity="ERROR",
                        duration_ms=round(
                            duration_ms,
                            2,
                        ),
                        file=file,
                        line=line,
                        function=function,
                        error=error_data,
                        arguments={
                            "args": sanitize(args),
                            "kwargs": sanitize(kwargs),
                        },
                    ).exception(
                        "Function failed"
                    )


                    # NODE FAILED
                    if job_id:
                        await events.emit(
                            job_id,
                            "node_failed",
                            node=operation_name,
                            label=label,
                            error=str(exc),
                        )

                    # Не поглощаем ошибку
                    raise

            return async_wrapper


        # SYNC
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):

            start = time.perf_counter()

            log = get_logger(
                event=event,
                operation=operation_name,
                function=func.__qualname__,
                module=func.__module__,
            )

            log.debug("Function started")

            try:

                # EXECUTE
                result = func(
                    *args,
                    **kwargs,
                )

                duration_ms = (
                    time.perf_counter() - start
                ) * 1000

                # LOG SUCCESS
                log.bind(
                    status="success",
                    severity="INFO",
                    duration_ms=round(
                        duration_ms,
                        2,
                    ),
                ).info(
                    "Function completed"
                )

                return result

            except Exception as exc:

                duration_ms = (
                    time.perf_counter() - start
                ) * 1000

                tb = traceback.extract_tb(
                    exc.__traceback__
                )

                last = tb[-1] if tb else None

                # ERROR DATA
                file = (
                    last.filename
                    if last
                    else None
                )

                line = (
                    last.lineno
                    if last
                    else None
                )

                function = (
                    last.name
                    if last
                    else None
                )

                error_data = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }

                # LOG ERROR
                log.bind(
                    status="error",
                    severity="ERROR",
                    duration_ms=round(
                        duration_ms,
                        2,
                    ),
                    file=file,
                    line=line,
                    function=function,
                    error=error_data,
                    arguments={
                        "args": sanitize(args),
                        "kwargs": sanitize(kwargs),
                    },
                ).exception(
                    "Function failed"
                )

                # Не поглощаем ошибку
                raise

        return sync_wrapper

    return decorator


def _summarize(
    operation: str,
    result: dict,
) -> dict:
    """
    Короткая сводка для FixOps events.

    Не отправляем большие блоки текста.
    """

    if operation == "error_analyzer":

        node = (
            result
            .get("analysis_result", {})
            .get("resolved_node")
        )

        return {
            "resolved": bool(node),
        }

    if operation == "apply_fix":

        return {
            "fixed_file": result.get(
                "fixed_file"
            ),
            "fix_applied": result.get(
                "fix_applied"
            ),
            "fix_error": result.get(
                "fix_error"
            ),
            "fix_diff": result.get(
                "fix_diff"
            ),
        }

    if operation == "run_tests":

        return {
            "tests_passed": result.get(
                "tests_passed"
            ),
            "reproduction_passed": result.get(
                "reproduction_passed"
            ),
            "return_code": result.get(
                "test_return_code"
            ),
            "result_type": result.get(
                "test_result_type"
            ),
            "stdout_tail": (
                result.get("test_stdout") or ""
            )[-500:],
            "stderr_tail": (
                result.get("test_stderr") or ""
            )[-500:],
        }

    return {}
