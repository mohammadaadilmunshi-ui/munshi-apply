from __future__ import annotations

import json
from typing import Any

from .database import Database, canonical_json


class ArchitectureStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO application_checkpoints (
                    checkpoint_id, application_id, sequence, state, page_id,
                    page_fingerprint, completed_control_ids_json,
                    pending_control_ids_json, selected_resume_id,
                    selected_resume_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint["checkpoint_id"],
                    checkpoint["application_id"],
                    checkpoint["sequence"],
                    checkpoint["state"],
                    checkpoint.get("page_id"),
                    checkpoint["page_fingerprint"],
                    canonical_json({"items": checkpoint.get("completed_control_ids", [])}),
                    canonical_json({"items": checkpoint.get("pending_control_ids", [])}),
                    checkpoint.get("selected_resume_id"),
                    checkpoint.get("selected_resume_sha256"),
                    checkpoint["created_at"],
                ),
            )

    def latest_checkpoint(self, application_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM application_checkpoints
                WHERE application_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (application_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["completed_control_ids"] = json.loads(
            item.pop("completed_control_ids_json")
        )["items"]
        item["pending_control_ids"] = json.loads(item.pop("pending_control_ids_json"))[
            "items"
        ]
        return item

    def upsert_evidence_node(self, node: dict[str, Any]) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence_nodes (
                    evidence_id, application_id, kind, text, semantic_types_json,
                    trust_level, protected, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(evidence_id) DO UPDATE SET
                    application_id = excluded.application_id,
                    kind = excluded.kind,
                    text = excluded.text,
                    semantic_types_json = excluded.semantic_types_json,
                    trust_level = excluded.trust_level,
                    protected = excluded.protected,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    node["evidence_id"],
                    node.get("application_id"),
                    node["kind"],
                    node["text"],
                    canonical_json({"items": node.get("semantic_types", [])}),
                    node["trust_level"],
                    1 if node.get("protected", False) else 0,
                    node["source"],
                    node["updated_at"],
                ),
            )

    def add_evidence_edge(self, edge: dict[str, Any]) -> bool:
        with self.database.connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO evidence_edges (
                    from_evidence_id, to_evidence_id, relation
                ) VALUES (?, ?, ?)
                """,
                (
                    edge["from_evidence_id"],
                    edge["to_evidence_id"],
                    edge["relation"],
                ),
            )
        return result.rowcount == 1

    def evidence_graph(self, application_id: str | None = None) -> dict[str, Any]:
        with self.database.connect() as connection:
            if application_id is None:
                nodes = connection.execute(
                    "SELECT * FROM evidence_nodes ORDER BY evidence_id"
                ).fetchall()
            else:
                nodes = connection.execute(
                    """
                    SELECT * FROM evidence_nodes
                    WHERE application_id IS NULL OR application_id = ?
                    ORDER BY evidence_id
                    """,
                    (application_id,),
                ).fetchall()
            node_ids = [row["evidence_id"] for row in nodes]
            if not node_ids:
                edge_rows = []
            else:
                placeholders = ",".join("?" for _ in node_ids)
                edge_rows = connection.execute(
                    f"""
                    SELECT * FROM evidence_edges
                    WHERE from_evidence_id IN ({placeholders})
                      AND to_evidence_id IN ({placeholders})
                    ORDER BY from_evidence_id, to_evidence_id, relation
                    """,  # noqa: S608 - placeholders are generated, not user-controlled
                    (*node_ids, *node_ids),
                ).fetchall()

        parsed_nodes: list[dict[str, Any]] = []
        for row in nodes:
            item = dict(row)
            item["semantic_types"] = json.loads(item.pop("semantic_types_json"))["items"]
            item["protected"] = bool(item["protected"])
            parsed_nodes.append(item)
        return {
            "nodes": parsed_nodes,
            "edges": [dict(row) for row in edge_rows],
        }

    def record_ai_usage(self, usage: dict[str, Any]) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_usage (
                    usage_id, provider, model, occurred_at, input_tokens,
                    output_tokens, cost_usd, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage["usage_id"],
                    usage["provider"],
                    usage["model"],
                    usage["occurred_at"],
                    usage["input_tokens"],
                    usage["output_tokens"],
                    usage["cost_usd"],
                    usage.get("correlation_id"),
                ),
            )

    def monthly_ai_spend(self, year_month: str) -> float:
        if len(year_month) != 7 or year_month[4] != "-":
            raise ValueError("year_month must use YYYY-MM")
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(cost_usd), 0) AS total
                FROM ai_usage
                WHERE substr(occurred_at, 1, 7) = ?
                """,
                (year_month,),
            ).fetchone()
        return round(float(row["total"]), 6)
