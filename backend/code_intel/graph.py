"""
graph.py — построение графа вызовов (call graph) поверх резолвнутого индекса.

Узел графа = qualname функции/метода (напр. "services.discount.DiscountService.calculate").
Ребро A -> B  = "A вызывает B", с метаданными: строка вызова, файл, resolved/unresolved.

Это именно тот граф из шага 4 ("Строим граф вызовов") и основа для
шага 5-6 (поиск цепочки при ошибке).

Построение рёбер собрано в класс `GraphBuilder`: он умеет строить граф
по индексу (используя резолвер). Для обратной совместимости сохранена
модульная функция-обёртка `build_graph`.
"""

from dataclasses import dataclass, field


@dataclass
class Edge:
    source: str
    target: str
    file: str
    line: int
    resolved: bool
    reason: str


class CallGraph:
    def __init__(self):
        self.edges: list[Edge] = []
        self.out_edges: dict[str, list[Edge]] = {}
        self.in_edges: dict[str, list[Edge]] = {}
        self.nodes: set[str] = set()

    def add_node(self, qualname: str):
        self.nodes.add(qualname)
        self.out_edges.setdefault(qualname, [])
        self.in_edges.setdefault(qualname, [])

    def add_edge(self, edge: Edge):
        self.add_node(edge.source)
        self.add_node(edge.target)
        self.edges.append(edge)
        self.out_edges[edge.source].append(edge)
        self.in_edges[edge.target].append(edge)

    def callers(self, qualname: str) -> list[Edge]:
        return self.in_edges.get(qualname, [])

    def callees(self, qualname: str) -> list[Edge]:
        return self.out_edges.get(qualname, [])

    def to_dict(self) -> dict:
        return {
            "nodes": sorted(self.nodes),
            "edges": [
                {
                    "source": e.source, "target": e.target, "file": e.file,
                    "line": e.line, "resolved": e.resolved, "reason": e.reason,
                }
                for e in self.edges
            ],
        }


class GraphBuilder:
    """Строит граф вызовов по индексу."""

    def __init__(self, resolver=None):
        # resolver может быть как CallResolver-объектом (интерфейс
        # resolve_call(module_obj, fn, call)), так и legacy-функцией
        # resolve_call(idx, module_obj, fn, call).
        self.resolver = resolver

    def _resolve_one(self, idx, m, fn, call_dict, resolver):
        # We assume resolver is now always an object with async resolve_call
        return None 

    async def build(self, idx, resolver=None) -> CallGraph:
        # Resolver is expected to be an async resolve_call object
        resolved_resolver = resolver or self.resolver
        if resolved_resolver is None:
             raise ValueError("Resolver must be provided")
        
        g = CallGraph()
        
        for m in idx.modules:
            for fn in m.functions:
                g.add_node(fn.qualname)
                for call in fn.calls:
                    call_dict = {"line": call.line, "raw": call.raw, "kind": call.kind,
                                 "base": call.base, "attr": call.attr}
                    
                    # resolver.resolve_call is now async
                    res = await resolved_resolver.resolve_call(m, fn, call_dict)
                    
                    g.add_edge(Edge(
                        source=fn.qualname,
                        target=res["target"],
                        file=m.file,
                        line=call.line,
                        resolved=res["resolved"],
                        reason=res["reason"],
                    ))
        return g


async def build_graph(idx, resolve_call_func) -> CallGraph:
    """Обратно-совместимая обёртка над GraphBuilder.build (legacy-сигнатура резолвера)."""
    # Create a wrapper object that matches the CallResolver interface
    class LegacyResolver:
        def __init__(self, func, idx):
            self.func = func
            self.idx = idx
        async def resolve_call(self, m, fn, call_dict):
            return self.func(self.idx, m, fn, call_dict)
            
    return await GraphBuilder(LegacyResolver(resolve_call_func, idx)).build(idx)
