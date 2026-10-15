"""Base-relation schemas for the RA translator.

Relations are the tables of a question's SQLite file, so staff keep authoring schemas
in SQL exactly as for SQL questions. Lookups are case-insensitive, like SQLite.
"""
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Column:
    name: str
    type: str        # TEXT | INTEGER | REAL | NUMERIC (SQLite affinity)


class Schema:
    def __init__(self, tables: Dict[str, List[Column]]):
        self._tables = {name.casefold(): (name, cols) for name, cols in tables.items()}

    def lookup(self, name: str) -> Optional[Tuple[str, List[Column]]]:
        """Return (canonical table name, columns) or None."""
        return self._tables.get(name.casefold())

    @property
    def table_names(self) -> List[str]:
        return sorted(name for name, _ in self._tables.values())

    @classmethod
    def from_dict(cls, tables: Dict[str, List]) -> "Schema":
        """Build from {"Student": ["sid", "name"], …} or {"Student": [("sid", "INTEGER"), …]}."""
        return cls({
            t: [Column(c, "NUMERIC") if isinstance(c, str) else Column(c[0], affinity(c[1]))
                for c in cols]
            for t, cols in tables.items()
        })

    @classmethod
    def from_sqlite(cls, db_path: str) -> "Schema":
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            names = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            tables = {}
            for name in names:
                info = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
                tables[name] = [Column(row[1], affinity(row[2])) for row in info]
            return cls(tables)
        finally:
            conn.close()


def affinity(declared: Optional[str]) -> str:
    """SQLite's column-affinity rules (https://sqlite.org/datatype3.html §3.1)."""
    t = (declared or "").upper()
    if "INT" in t:
        return "INTEGER"
    if any(k in t for k in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"
