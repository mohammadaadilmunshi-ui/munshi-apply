from __future__ import annotations

import math
from typing import Any

from .database import Database

_JOB_SIGNAL_DIMENSIONS = {
    "ROLE_AMBIGUITY",
    "RESPONSIBILITY_BREADTH",
    "QUALIFICATION_INFLATION",
    "WORKLOAD_PRESSURE",
    "SCHEDULE_INTENSITY",
    "TRAVEL_BURDEN",
    "COMPENSATION_CLARITY",
    "SENIORITY_ALIGNMENT",
    "ROLE_STABILITY",
    "LOCATION_CONSTRAINTS",
    "WORK_AUTHORIZATION_RISK",
    "APPLICATION_FRICTION",
}
_OVERALL_SIGNALS = {"LOW", "MODERATE", "HIGH", "INSUFFICIENT_DATA"}
_SEVERITIES = {"LOW", "MODERATE", "HIGH"}


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _bounded_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ValueError(f"{label} must be null or an integer from 0 to 100")
    return value


def _confidence(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number from 0 to 1")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ValueError(f"{label} must be a finite number from 0 to 1")
    return result


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    result = [_required_text(item, label) for item in value]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def _parse_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("Job signal report payload must be an object")

    report_id = _required_text(payload.get("reportId"), "reportId")
    application_id = _required_text(payload.get("applicationId"), "applicationId")
    overall_signal = _required_text(payload.get("overallSignal"), "overallSignal")
    if overall_signal not in _OVERALL_SIGNALS:
        raise ValueError("overallSignal is invalid")
    overall_score = _bounded_integer(payload.get("overallScore"), "overallScore")
    source_fingerprint = _required_text(
        payload.get("sourceFingerprint"), "sourceFingerprint"
    )
    evaluated_at = _required_text(payload.get("evaluatedAt"), "evaluatedAt")

    raw_dimensions = payload.get("dimensions")
    if not isinstance(raw_dimensions, dict):
        raise ValueError("dimensions must be an object")
    if set(raw_dimensions) != _JOB_SIGNAL_DIMENSIONS:
        raise ValueError("dimensions must contain the complete canonical Job Signal ontology")

    dimensions: list[dict[str, object]] = []
    dimension_evidence: dict[str, list[str]] = {}
    for dimension in sorted(_JOB_SIGNAL_DIMENSIONS):
        raw = raw_dimensions.get(dimension)
        if not isinstance(raw, dict):
            raise ValueError(f"dimensions.{dimension} must be an object")
        if raw.get("dimension") != dimension:
            raise ValueError(f"dimensions.{dimension}.dimension must match its key")
        evidence_ids = _string_list(
            raw.get("evidenceIds"), f"dimensions.{dimension}.evidenceIds"
        )
        dimension_evidence[dimension] = evidence_ids
        dimensions.append(
            {
                "dimension": dimension,
                "score": _bounded_integer(
                    raw.get("score"), f"dimensions.{dimension}.score"
                ),
                "confidence": _confidence(
                    raw.get("confidence"), f"dimensions.{dimension}.confidence"
                ),
                "evidenceIds": evidence_ids,
            }
        )

    raw_signals = payload.get("signals")
    if not isinstance(raw_signals, list):
        raise ValueError("signals must be an array")
    signals: list[dict[str, str]] = []
    signal_ids: set[str] = set()
    signal_dimensions: dict[str, str] = {}
    for index, raw in enumerate(raw_signals):
        if not isinstance(raw, dict):
            raise ValueError(f"signals[{index}] must be an object")
        signal_id = _required_text(raw.get("signalId"), f"signals[{index}].signalId")
        if signal_id in signal_ids:
            raise ValueError("signals must not contain duplicate signalId values")
        signal_ids.add(signal_id)
        dimension = _required_text(raw.get("dimension"), f"signals[{index}].dimension")
        if dimension not in _JOB_SIGNAL_DIMENSIONS:
            raise ValueError(f"signals[{index}].dimension is invalid")
        severity = _required_text(raw.get("severity"), f"signals[{index}].severity")
        if severity not in _SEVERITIES:
            raise ValueError(f"signals[{index}].severity is invalid")
        signal_dimensions[signal_id] = dimension
        signals.append(
            {
                "signalId": signal_id,
                "dimension": dimension,
                "severity": severity,
                "evidence": _required_text(
                    raw.get("evidence"), f"signals[{index}].evidence"
                ),
                "explanation": _required_text(
                    raw.get("explanation"), f"signals[{index}].explanation"
                ),
            }
        )

    referenced_ids = {
        signal_id
        for evidence_ids in dimension_evidence.values()
        for signal_id in evidence_ids
    }
    if referenced_ids != signal_ids:
        raise ValueError("dimension evidenceIds must reference every signal exactly once")
    for dimension, evidence_ids in dimension_evidence.items():
        if any(signal_dimensions[signal_id] != dimension for signal_id in evidence_ids):
            raise ValueError("dimension evidenceIds must reference signals in the same dimension")

    return {
        "reportId": report_id,
        "applicationId": application_id,
        "overallSignal": overall_signal,
        "overallScore": overall_score,
        "sourceFingerprint": source_fingerprint,
        "evaluatedAt": evaluated_at,
        "dimensions": dimensions,
        "signals": signals,
    }


class JobSignalStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _read(self, connection: Any, report_id: str) -> dict[str, object] | None:
        row = connection.execute(
            "SELECT * FROM job_signal_reports WHERE report_id = ?", (report_id,)
        ).fetchone()
        if row is None:
            return None
        dimensions = connection.execute(
            """
            SELECT dimension, score, confidence
            FROM job_signal_dimensions
            WHERE report_id = ?
            ORDER BY dimension
            """,
            (report_id,),
        ).fetchall()
        signals = connection.execute(
            """
            SELECT signal_id, dimension, severity, evidence, explanation
            FROM job_signal_evidence
            WHERE report_id = ?
            ORDER BY dimension, signal_id
            """,
            (report_id,),
        ).fetchall()
        signal_ids_by_dimension: dict[str, list[str]] = {
            dimension: [] for dimension in _JOB_SIGNAL_DIMENSIONS
        }
        for signal in signals:
            signal_ids_by_dimension[signal["dimension"]].append(signal["signal_id"])
        dimension_payload = {
            item["dimension"]: {
                "dimension": item["dimension"],
                "score": item["score"],
                "confidence": item["confidence"],
                "evidenceIds": signal_ids_by_dimension[item["dimension"]],
            }
            for item in dimensions
        }
        return {
            "reportId": row["report_id"],
            "applicationId": row["application_id"],
            "overallSignal": row["overall_signal"],
            "overallScore": row["overall_score"],
            "sourceFingerprint": row["source_fingerprint"],
            "evaluatedAt": row["evaluated_at"],
            "dimensions": dimension_payload,
            "signals": [
                {
                    "signalId": signal["signal_id"],
                    "dimension": signal["dimension"],
                    "severity": signal["severity"],
                    "evidence": signal["evidence"],
                    "explanation": signal["explanation"],
                }
                for signal in signals
            ],
        }

    def save(self, payload: object) -> dict[str, object]:
        parsed = _parse_payload(payload)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            application = connection.execute(
                "SELECT application_id FROM applications WHERE application_id = ?",
                (parsed["applicationId"],),
            ).fetchone()
            if application is None:
                raise KeyError("Job signal report references an unknown application")
            existing = connection.execute(
                """
                SELECT report_id
                FROM job_signal_reports
                WHERE application_id = ? AND source_fingerprint = ?
                """,
                (parsed["applicationId"], parsed["sourceFingerprint"]),
            ).fetchone()
            report_id = existing["report_id"] if existing else parsed["reportId"]
            connection.execute(
                """
                INSERT INTO job_signal_reports (
                    report_id, application_id, overall_signal, overall_score,
                    source_fingerprint, evaluated_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    overall_signal = excluded.overall_signal,
                    overall_score = excluded.overall_score,
                    evaluated_at = excluded.evaluated_at,
                    updated_at = excluded.updated_at
                """,
                (
                    report_id,
                    parsed["applicationId"],
                    parsed["overallSignal"],
                    parsed["overallScore"],
                    parsed["sourceFingerprint"],
                    parsed["evaluatedAt"],
                    parsed["evaluatedAt"],
                    parsed["evaluatedAt"],
                ),
            )
            connection.execute(
                "DELETE FROM job_signal_dimensions WHERE report_id = ?", (report_id,)
            )
            connection.execute(
                "DELETE FROM job_signal_evidence WHERE report_id = ?", (report_id,)
            )
            connection.executemany(
                """
                INSERT INTO job_signal_dimensions (
                    report_id, dimension, score, confidence
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        report_id,
                        item["dimension"],
                        item["score"],
                        item["confidence"],
                    )
                    for item in parsed["dimensions"]
                ],
            )
            connection.executemany(
                """
                INSERT INTO job_signal_evidence (
                    signal_id, report_id, dimension, severity, evidence, explanation
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["signalId"],
                        report_id,
                        item["dimension"],
                        item["severity"],
                        item["evidence"],
                        item["explanation"],
                    )
                    for item in parsed["signals"]
                ],
            )
            connection.execute(
                """
                UPDATE applications
                SET job_signal_score = ?, updated_at = ?
                WHERE application_id = ?
                """,
                (
                    parsed["overallScore"],
                    parsed["evaluatedAt"],
                    parsed["applicationId"],
                ),
            )
            stored = self._read(connection, str(report_id))
            if stored is None:
                raise RuntimeError("Job signal report was not persisted")
            return stored

    def latest(self, application_id: object) -> dict[str, object] | None:
        normalized = _required_text(application_id, "applicationId")
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT report_id
                FROM job_signal_reports
                WHERE application_id = ?
                ORDER BY evaluated_at DESC, report_id DESC
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            return None if row is None else self._read(connection, row["report_id"])
