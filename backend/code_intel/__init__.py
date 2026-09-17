"""
code_intel — FixOps Code Intelligence.

Публичный ООП-интерфейс пайплайна:

  indexer           ProjectIndexer   — AST-индексация проекта
  resolver          ProjectIndex, CallResolver — резолвинг вызовов
  graph             CallGraph, GraphBuilder — граф вызовов
  error_analyzer    ErrorAnalyzer   — ошибка из лога -> цепочка причинности
  context_builder   ContextBuilder  — координаты -> реальный код -> промпт LLM
"""

from .context_builder import ContextBuilder, build_llm_context, render_llm_prompt
from .error_analyzer import ErrorAnalyzer, analyze_error, render_chain_text
from .graph import (
    CallGraph,
    Edge,
    GraphBuilder,
    build_graph,
)
from .indexer import (
    CallSite,
    ClassInfo,
    FunctionInfo,
    ModuleInfo,
    ProjectIndexer,
    scan_project,
    to_dict,
)
from .resolver import (
    CallResolver,
    ProjectIndex,
    resolve_call,
)

__all__ = [
    "CallGraph",
    "CallResolver",
    "CallSite",
    "ClassInfo",
    "ContextBuilder",
    "Edge",
    "ErrorAnalyzer",
    "FunctionInfo",
    "GraphBuilder",
    "ModuleInfo",
    "ProjectIndex",
    "ProjectIndexer",
    "analyze_error",
    "build_graph",
    "build_llm_context",
    "render_chain_text",
    "render_llm_prompt",
    "resolve_call",
    "scan_project",
    "to_dict",
]
