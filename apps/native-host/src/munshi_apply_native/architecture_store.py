from __future__ import annotations

import json
from typing import Any

from .database import Database, canonical_json


class ArchitectureStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_profile_record(self, record: dict[str, Any]) -> None:
        """Replace one repeatable profile record and its facts atomically."""
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO profile_records (
                    record_id, profile_id, kind, label, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    kind = excluded.kind,
                    label = excluded.label,
                    updated_at = excluded.updated_at
                """,
                (
                    record["record_id"],
                    record["profile_id"],
                    record["kind"],
                    record["label"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            connection.execute(
                "DELETE FROM profile_record_facts WHERE record_id = ?",
                (record["record_id"],),
            )
            for fact in record.get("facts", []):
                connection.execute(
                    """
                    INSERT INTO profile_record_facts (
                        fact_id, record_id, key, value_json, category,
                        trust_level, source, confirmed_at, updated_at, protected
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fact["fact_id"],
                        record["record_id"],
                        fact["key"],
                        canonical_json({"value": fact.get("value")}),
                        fact["category"],
                        fact["trust_level"],
                        fact["source"],
                        fact.get("confirmed_at"),
                        fact["updated_at"],
                        1 if fact.get("protected", False) else 0,
                    ),
                )

    def profile_records(
        self, profile_id: str, *, kind: str | None = None
    ) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            if kind is None:
                rows = connection.execute(
                    """
                    SELECT * FROM profile_records
                    WHERE profile_id = ?
                    ORDER BY kind, updated_at DESC, record_id
                    """,
                    (profile_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM profile_records
                    WHERE profile_id = ? AND kind = ?
                    ORDER BY updated_at DESC, record_id
                    """,
                    (profile_id, kind),
                ).fetchall()

            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                fact_rows = connection.execute(
                    """
                    SELECT * FROM profile_record_facts
                    WHERE record_id = ?
                    ORDER BY key, fact_id
                    """,
                    (row["record_id"],),
                ).fetchall()
                facts: list[dict[str, Any]] = []
                for fact_row in fact_rows:
                    fact = dict(fact_row)
                    fact["value"] = json.loads(fact.pop("value_json"))["value"]
                    fact["protected"] = bool(fact["protected"])
                    facts.append(fact)
                item["facts"] = facts
                result.append(item)
        return result

    def lock_resume_selection(self, selection: dict[str, Any]) -> bool:
        """Freeze the exact résumé bytes selected for one application."""
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            resume = connection.execute(
                "SELECT resume_id, sha256 FROM resumes WHERE resume_id = ?",
                (selection["resume_id"],),
            ).fetchone()
            if resume is None:
                raise ValueError("Cannot lock an unknown résumé")
            if resume["sha256"] != selection["resume_sha256"]:
                raise ValueError(
                    "Résumé selection hash does not match the authoritative résumé bytes"
                )

            existing = connection.execute(
                """
                SELECT * FROM application_resume_selections
                WHERE application_id = ?
                ORDER BY locked_at, selection_id
                LIMIT 1
                """,
                (selection["application_id"],),
            ).fetchone()
            if existing is not None:
                same_selection = (
                    existing["resume_id"] == selection["resume_id"]
                    and existing["resume_sha256"] == selection["resume_sha256"]
                )
                if same_selection:
                    return False
                raise ValueError(
                    "Application résumé selection is already locked to different bytes"
                )

            connection.execute(
                """
                INSERT INTO application_resume_selections (
                    selection_id, application_id, resume_id, resume_sha256, locked_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    selection["selection_id"],
                    selection["application_id"],
                    selection["resume_id"],
                    selection["resume_sha256"],
                    selection["locked_at"],
                ),
            )
        return True

    def locked_resume_selection(self, application_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM application_resume_selections
                WHERE application_id = ?
                ORDER BY locked_at, selection_id
                LIMIT 1
                """,
                (application_id,),
            ).fetchone()
        return None if row is None else dict(row)

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
                    canonical_json(
                        {"items": checkpoint.get("completed_control_ids", [])}
                    ),
                    canonical_json(
                        {"items": checkpoint.get("pending_control_ids", [])}
                    ),
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
