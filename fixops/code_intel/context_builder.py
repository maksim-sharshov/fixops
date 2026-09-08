"""
context_builder.py — последний слой перед LLM.

Задача:
    Дать LLM минимальный и релевантный контекст для исправления ошибки.

Принцип:
    LLM отвечает за:
        - поиск root cause;
        - понимание существующей логики;
        - выбор минимального исправления;
        - regression-тест.

    FixOps отвечает за:
        - проверку SEARCH;
        - применение patch;
        - запуск тестов.

raw_source используется как источник истины для SEARCH.
LLM НЕ должна копировать весь raw_source в SEARCH.
"""

import os
import ast
import asyncio


class ContextBuilder:
    """Собирает контекст ошибки для LLM."""

    def __init__(self, project_root: str):
        self.project_root = project_root

    def _find_function_location(self, idx, qualname: str):
        """По qualname находит (file, lineno, end_lineno)."""
        for module in idx.modules:
            for fn in module.functions:
                if fn.qualname == qualname:
                    return module.file, fn.lineno, fn.end_lineno
        return None

    async def _read_smart_context(
        self,
        file: str,
        target_lineno: int,
        target_end_lineno: int,
    ) -> tuple[str, str]:
        """
        Читает целевую функцию и небольшой контекст вокруг неё.

        source:
            Код с номерами строк для анализа.

        raw_source:
            Точный исходный код целевой функции.
            Используется только для формирования SEARCH.
        """

        path = os.path.join(self.project_root, file)

        def _extract():
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # ---------------------------------------------------------
            # AST
            # ---------------------------------------------------------

            tree = None

            try:
                tree = ast.parse("".join(lines))
            except SyntaxError:
                pass

            # ---------------------------------------------------------
            # Целевая функция
            # ---------------------------------------------------------

            func_start = target_lineno - 1
            func_end = target_end_lineno

            # ---------------------------------------------------------
            # raw_source
            #
            # Только целевая функция.
            # Никаких импортов, классов и остального файла.
            # ---------------------------------------------------------

            raw_source = "".join(
                lines[func_start:func_end]
            ).rstrip()

            # ---------------------------------------------------------
            # source
            #
            # Показываем функцию целиком.
            # Это главный контекст для LLM.
            # ---------------------------------------------------------

            numbered = []

            for index in range(func_start, func_end):
                numbered.append(
                    f"{index + 1:>4} | {lines[index].rstrip()}"
                )

            source = "\n".join(numbered)

            return source, raw_source

        return await asyncio.to_thread(_extract)

    def _collect_chain_qualnames(self, analysis: dict) -> list[str]:
        """
        Собирает цепочку вызовов.

        Используется только как дополнительный контекст.
        """

        ordered = []

        def walk_callers(nodes):
            for node in nodes:
                walk_callers(node.get("callers", []))
                ordered.append(node["qualname"])

        walk_callers(analysis.get("callers_chain", []))

        resolved = analysis.get("resolved_node")
        if resolved:
            ordered.append(resolved)

        def walk_callees(nodes):
            for node in nodes:
                ordered.append(node["qualname"])
                walk_callees(node.get("callees", []))

        walk_callees(analysis.get("callees_chain", []))

        seen = set()
        result = []

        for qualname in ordered:
            if qualname not in seen:
                seen.add(qualname)
                result.append(qualname)

        return result

    def _confidence_tag(self, qualname: str, analysis: dict) -> str:
        """Возвращает степень уверенности источника."""

        def scan(nodes):
            for node in nodes:
                if node["qualname"] == qualname:
                    if node.get("from_runtime"):
                        return "runtime-confirmed"

                    if node.get("resolved"):
                        return "static-resolved"

                    return "static-unresolved"

                result = scan(node.get("callers", []))
                if result:
                    return result

                result = scan(node.get("callees", []))
                if result:
                    return result

            return None

        result = scan(analysis.get("callers_chain", []))

        if result:
            return result

        result = scan(analysis.get("callees_chain", []))

        if result:
            return result

        if qualname == analysis.get("resolved_node"):
            return "error-location"

        return "unknown"

    async def build_llm_context(self, idx, analysis: dict) -> dict:
        """
        Строит компактный контекст.

        Основной источник истины:
            error_location

        Дополнительный контекст:
            callers / callees
        """

        resolved_node = analysis.get("resolved_node")

        chain = self._collect_chain_qualnames(analysis)

        nodes_with_source = []

        for qualname in chain:
            location = self._find_function_location(idx, qualname)

            confidence = self._confidence_tag(
                qualname,
                analysis,
            )

            if location is None:
                nodes_with_source.append({
                    "qualname": qualname,
                    "file": None,
                    "source": None,
                    "raw_source": None,
                    "confidence": confidence,
                    "is_error_location": qualname == resolved_node,
                })
                continue

            file, lineno, end_lineno = location

            source, raw_source = await self._read_smart_context(
                file,
                lineno,
                end_lineno,
            )

            nodes_with_source.append({
                "qualname": qualname,
                "file": file,
                "lineno": lineno,
                "end_lineno": end_lineno,
                "source": source,
                "raw_source": raw_source,
                "confidence": confidence,
                "is_error_location": qualname == resolved_node,
            })

        return {
            "error": analysis["error"],
            "chain": nodes_with_source,
        }

    @staticmethod
    def render_llm_prompt(ctx: dict) -> str:
        """
        Формирует компактный prompt для LLM.

        Главный принцип:
            меньше инструкций;
            больше релевантного кода.
        """

        error = ctx["error"]

        lines = []

        # =============================================================
        # ERROR
        # =============================================================

        lines.append("# ОШИБКА")
        lines.append("")
        lines.append(
            f"Файл: {error['file']}"
        )
        lines.append(
            f"Строка: {error['line']}"
        )
        lines.append(
            f"Функция: {error['function']}"
        )
        lines.append(
            f"Ошибка: {error['error']}"
        )

        # =============================================================
        # TARGET
        # =============================================================

        error_node = None

        for node in ctx["chain"]:
            if node.get("is_error_location"):
                error_node = node
                break

        if error_node is not None:
            lines.append("")
            lines.append("# КОД С МЕСТОМ ОШИБКИ")
            lines.append("")
            lines.append(
                f"Файл: `{error_node['file']}`"
            )
            lines.append(
                f"Функция: `{error_node['qualname']}`"
            )
            lines.append("")

            lines.append("```python")
            lines.append(error_node["source"])
            lines.append("```")

            lines.append("")
            lines.append(
                "Точный исходный код функции для проверки SEARCH:"
            )
            lines.append("")

            lines.append("```python")
            lines.append(error_node["raw_source"])
            lines.append("```")

        # =============================================================
        # RELATED CODE
        # =============================================================

        related_nodes = [
            node
            for node in ctx["chain"]
            if not node.get("is_error_location")
            and node.get("source")
        ]

        if related_nodes:
            lines.append("")
            lines.append("# ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ")
            lines.append("")

            # Не отправляем всю цепочку.
            # Берём только несколько ближайших узлов.
            for node in related_nodes[:3]:
                lines.append(
                    f"## `{node['qualname']}`"
                )

                lines.append(
                    f"Файл: `{node['file']}`"
                )

                lines.append("```python")
                lines.append(node["source"])
                lines.append("```")
                lines.append("")

        # =============================================================
        # TASK
        # =============================================================

        lines.append("")
        lines.append("# ЗАДАЧА")
        lines.append("")

        lines.append(
            "Найди ROOT CAUSE ошибки и исправь её."
        )

        lines.append(
            "Сохрани существующую логику программы."
        )

        lines.append(
            "Не заменяй существующую переменную или выражение "
            "другим только для устранения исключения."
        )

        lines.append(
            "Не добавляй новую бизнес-логику, если она не нужна "
            "для устранения ROOT CAUSE."
        )

        lines.append(
            "Выбери минимальное изменение, которое устраняет "
            "ошибку и сохраняет смысл существующего кода."
        )

        lines.append("")

        lines.append(
            "ВАЖНО:"
        )

        lines.append(
            "Если исходный код использует `data['total']`, "
            "не заменяй его на `data['count']` без доказательства "
            "из контекста, что `count` должен использоваться вместо `total`."
        )

        lines.append("")

        lines.append(
            "Сначала выбери правильный PATCH."
        )

        lines.append(
            "После этого напиши regression-тест."
        )

        lines.append(
            "Тест должен проверять правильное поведение программы, "
            "а не заставлять PATCH соответствовать удобной реализации."
        )

        # =============================================================
        # PATCH RULES
        # =============================================================

        lines.append("")
        lines.append("# ПРАВИЛА PATCH")
        lines.append("")

        lines.append(
            "SEARCH должен содержать минимальный уникальный фрагмент "
            "исходного файла."
        )

        lines.append(
            "Если одной строки достаточно для однозначного поиска — "
            "используй одну строку."
        )

        lines.append(
            "Не включай в SEARCH всю функцию или весь файл."
        )

        lines.append(
            "REPLACE должен содержать только необходимый исправленный код."
        )

        lines.append(
            "Не переписывай соседний код без необходимости."
        )

        # =============================================================
        # TEST RULES
        # =============================================================

        lines.append("")
        lines.append("# ПРАВИЛА TEST")
        lines.append("")

        lines.append(
            "Тестируй исправленную функцию напрямую."
        )

        lines.append(
            "Для мокинга используй pytest monkeypatch."
        )

        lines.append(
            "Тест должен падать на исходной ошибочной реализации "
            "и проходить после исправления."
        )

        # =============================================================
        # OUTPUT
        # =============================================================

        lines.append("")
        lines.append("# ФОРМАТ ОТВЕТА")
        lines.append("")

        lines.append(
            "Верни строго два блока: `fix` и `test`."
        )

        lines.append(
            "Не добавляй текст вне этих блоков."
        )

        lines.append("")
        lines.append("```fix")
        lines.append(
            "FILE: <относительный_путь_к_файлу>"
        )
        lines.append("<<<<<<< SEARCH")
        lines.append(
            "<минимальный уникальный фрагмент>"
        )
        lines.append("=======")
        lines.append(
            "<минимально необходимое исправление>"
        )
        lines.append(">>>>>>> REPLACE")
        lines.append("```")

        lines.append("")
        lines.append("```test")
        lines.append(
            "FILE: tests/test_<name>.py"
        )
        lines.append(
            "<pytest regression test>"
        )
        lines.append("```")

        return "\n".join(lines)


async def build_llm_context(
    idx,
    project_root: str,
    analysis: dict,
) -> dict:
    """Обратно-совместимая обёртка."""

    return await ContextBuilder(
        project_root
    ).build_llm_context(
        idx,
        analysis,
    )


def render_llm_prompt(ctx: dict) -> str:
    """Обратно-совместимая обёртка."""

    return ContextBuilder.render_llm_prompt(ctx)
