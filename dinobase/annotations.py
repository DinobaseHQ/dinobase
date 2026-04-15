"""Shared Pydantic models and helpers for annotating tables, columns, and relationships."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from dinobase.db import DinobaseDB


_COLUMN_ONLY_KEYS: frozenset[str] = frozenset({"description", "note"})


class AnnotationInput(BaseModel):
    target: str  # "schema.table" or "schema.table.column"
    key: str
    value: str


class RelationshipInput(BaseModel):
    from_table: str  # "schema.table"
    from_column: str
    to_table: str  # "schema.table"
    to_column: str
    cardinality: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"] = "one_to_many"
    description: str = ""


class AnnotateBatchInput(BaseModel):
    items: list[AnnotationInput | RelationshipInput]


def apply_annotation(db: DinobaseDB, item: AnnotationInput) -> dict:
    parts = item.target.split(".")
    if len(parts) == 2:
        schema, tbl = parts
        if item.key == "description":
            db.set_table_description(schema, tbl, item.value)
        else:
            db.set_metadata(schema, tbl, item.key, item.value, column="")
    elif len(parts) == 3:
        schema, tbl, col = parts
        if item.key in _COLUMN_ONLY_KEYS:
            db.conn.execute(
                f"INSERT INTO _dinobase.columns "
                f"(connector_name, schema_name, table_name, column_name, {item.key}) "
                f"VALUES (?, ?, ?, ?, ?) "
                f"ON CONFLICT (connector_name, schema_name, table_name, column_name) "
                f"DO UPDATE SET {item.key} = excluded.{item.key}",
                [schema, schema, tbl, col, item.value],
            )
        else:
            db.set_metadata(schema, tbl, item.key, item.value, column=col)
    else:
        return {"error": f"Invalid target '{item.target}'. Use 'schema.table' or 'schema.table.column'"}
    return {"annotated": item.target, "key": item.key, "value": item.value}


def apply_relationship(db: DinobaseDB, item: RelationshipInput) -> dict:
    from_schema, from_tbl = item.from_table.split(".", 1)
    to_schema, to_tbl = item.to_table.split(".", 1)
    db.upsert_relationship(
        from_schema=from_schema, from_table=from_tbl, from_column=item.from_column,
        to_schema=to_schema, to_table=to_tbl, to_column=item.to_column,
        cardinality=item.cardinality, confidence=1.0, description=item.description,
    )
    return {"stored": 1, "relationship": f"{item.from_table}.{item.from_column} → {item.to_table}.{item.to_column}"}
