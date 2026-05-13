from __future__ import annotations

from dataclasses import dataclass

from doris_lineage.config import Settings
from doris_lineage.graph.nx_graph import LineageGraph
from doris_lineage.store.db import Database
from doris_lineage.store.reader import LineageReader
from doris_lineage.store.writer import LineageWriter


@dataclass
class AppContext:
    settings: Settings
    db: Database
    reader: LineageReader
    writer: LineageWriter
    graph: LineageGraph
