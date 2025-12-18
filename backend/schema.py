from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pyodbc


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool
    max_length: int | None
    precision: int | None
    scale: int | None


@dataclass(frozen=True)
class TableInfo:
    schema: str
    name: str
    table_type: str  # BASE TABLE or VIEW
    columns: List[ColumnInfo]


@dataclass(frozen=True)
class DatabaseSchema:
    tables: List[TableInfo]

    def to_prompt_string(self) -> str:
        """A compact, deterministic schema string for LLM prompting."""
        lines: List[str] = []
        for t in self.tables:
            lines.append(f"[{t.schema}].[{t.name}] ({t.table_type})")
            for c in t.columns:
                nullable = "NULL" if c.is_nullable else "NOT NULL"
                type_details = c.data_type
                if c.data_type.lower() in {"varchar", "nvarchar", "char", "nchar", "varbinary", "binary"}:
                    if c.max_length is not None:
                        # SQL Server uses -1 for MAX.
                        if c.max_length == -1:
                            type_details = f"{c.data_type}(MAX)"
                        else:
                            type_details = f"{c.data_type}({c.max_length})"
                elif c.data_type.lower() in {"decimal", "numeric"}:
                    if c.precision is not None and c.scale is not None:
                        type_details = f"{c.data_type}({c.precision},{c.scale})"
                lines.append(f"  - {c.name}: {type_details} {nullable}")
            lines.append("")
        return "\n".join(lines).strip()


def load_schema(conn: pyodbc.Connection) -> DatabaseSchema:
    """Loads the schema (tables + columns) for the current database."""
    tables = _load_tables(conn)
    columns_by_table = _load_columns(conn)

    table_infos: List[TableInfo] = []
    for (table_schema, table_name, table_type) in tables:
        cols = columns_by_table.get((table_schema, table_name), [])
        table_infos.append(
            TableInfo(
                schema=table_schema,
                name=table_name,
                table_type=table_type,
                columns=cols,
            )
        )

    # Deterministic ordering for stable prompts / testing.
    table_infos.sort(key=lambda t: (t.schema.lower(), t.name.lower()))
    return DatabaseSchema(tables=table_infos)


def _load_tables(conn: pyodbc.Connection) -> List[tuple[str, str, str]]:
    sql = """
    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        TABLE_TYPE
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
    ORDER BY TABLE_SCHEMA, TABLE_NAME
    """.strip()

    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def _load_columns(conn: pyodbc.Connection) -> Dict[tuple[str, str], List[ColumnInfo]]:
    sql = """
    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME,
        DATA_TYPE,
        IS_NULLABLE,
        CHARACTER_MAXIMUM_LENGTH,
        NUMERIC_PRECISION,
        NUMERIC_SCALE,
        ORDINAL_POSITION
    FROM INFORMATION_SCHEMA.COLUMNS
    ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
    """.strip()

    cur = conn.cursor()
    cur.execute(sql)

    out: Dict[tuple[str, str], List[ColumnInfo]] = {}
    for r in cur.fetchall():
        table_schema = r[0]
        table_name = r[1]
        col_name = r[2]
        data_type = r[3]
        is_nullable = str(r[4]).upper() == "YES"
        max_length = r[5]
        precision = r[6]
        scale = r[7]

        key = (table_schema, table_name)
        out.setdefault(key, []).append(
            ColumnInfo(
                name=col_name,
                data_type=data_type,
                is_nullable=is_nullable,
                max_length=max_length,
                precision=precision,
                scale=scale,
            )
        )

    return out
