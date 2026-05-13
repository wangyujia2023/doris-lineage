from __future__ import annotations

from typing import Any

import networkx as nx

from doris_lineage.store.reader import LineageReader


class LineageGraph:
    def __init__(self) -> None:
        self.g = nx.DiGraph()

    async def load_from_db(self, reader: LineageReader) -> None:
        self.g.clear()
        for edge in await reader.confirmed_edges():
            self.g.add_edge(
                edge["source_field"],
                edge["target_field"],
                edge_type=edge["edge_type"],
                confidence=edge["confidence"],
                transform_expr=edge.get("transform_expr"),
                query_id=edge.get("query_id"),
            )

    def upstream(self, field_id: str, depth: int | None = 5) -> list[dict[str, Any]]:
        return self._reachable_edges(field_id, direction="upstream", depth=depth)

    def downstream(self, field_id: str, depth: int | None = 5) -> list[dict[str, Any]]:
        return self._reachable_edges(field_id, direction="downstream", depth=depth)

    def table_lineage(self, asset_id: str, direction: str, depth: int | None = 3) -> list[dict[str, Any]]:
        fields = [node for node in self.g.nodes if node.startswith(f"{asset_id}.")]
        seen: set[tuple[str, str]] = set()
        results: list[dict[str, Any]] = []
        for field in fields:
            rows = self.upstream(field, depth) if direction == "upstream" else self.downstream(field, depth)
            for row in rows:
                source_asset = row["source"].rsplit(".", 1)[0]
                target_asset = row["target"].rsplit(".", 1)[0]
                key = (source_asset, target_asset)
                if key not in seen:
                    seen.add(key)
                    results.append({"source_asset": source_asset, "target_asset": target_asset, "depth": row["depth"]})
        return results

    def full_graph(self) -> dict[str, Any]:
        return {
            "nodes": sorted(self.g.nodes),
            "edges": [
                {"source": source, "target": target, **attrs}
                for source, target, attrs in self.g.edges(data=True)
            ],
        }

    def impact(self, field_id: str) -> dict[str, Any]:
        if field_id not in self.g:
            return {"affected_count": 0, "paths": {}}
        descendants = nx.descendants(self.g, field_id)
        paths = {node: nx.shortest_path(self.g, field_id, node) for node in descendants}
        return {"affected_count": len(descendants), "paths": paths}

    def sync_edge(self, source: str, target: str, **attrs: Any) -> None:
        self.g.add_edge(source, target, **attrs)

    def remove_edge(self, source: str, target: str) -> None:
        if self.g.has_edge(source, target):
            self.g.remove_edge(source, target)

    def _reachable_edges(self, start: str, direction: str, depth: int | None) -> list[dict[str, Any]]:
        if start not in self.g:
            return []
        max_depth = depth if depth is not None and depth > 0 else None
        frontier = {start}
        visited_nodes = {start}
        seen_edges: set[tuple[str, str]] = set()
        results: list[dict[str, Any]] = []
        current_depth = 0
        while frontier and (max_depth is None or current_depth < max_depth):
            current_depth += 1
            next_frontier: set[str] = set()
            for node in frontier:
                if direction == "upstream":
                    edges = [(pred, node) for pred in self.g.predecessors(node)]
                else:
                    edges = [(node, succ) for succ in self.g.successors(node)]
                for source, target in edges:
                    key = (source, target)
                    if key not in seen_edges:
                        seen_edges.add(key)
                        attrs = self.g.get_edge_data(source, target, default={})
                        results.append({"source": source, "target": target, "depth": current_depth, **attrs})
                    next_node = source if direction == "upstream" else target
                    if next_node not in visited_nodes:
                        visited_nodes.add(next_node)
                        next_frontier.add(next_node)
            frontier = next_frontier
        return results
