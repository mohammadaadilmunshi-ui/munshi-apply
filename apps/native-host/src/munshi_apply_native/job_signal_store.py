from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from .database import Database, canonical_json

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
_DIRECTIONS = {"POSITIVE", "CONCERN", "NEUTRAL"}
_EVIDENCE_SOURCES = {"JOB_POSTING", "APPLICATION_OBSERVATION"}


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


def _timestamp(value: object, label: str) -> str:
    normalized = _required_text(value, label)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return normalized


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
    job_id = _required_text(payload.get("jobId"), "jobId")
    source_identity = _required_text(payload.get("sourceIdentity"), "sourceIdentity")
    overall_signal = _required_text(payload.get("overallSignal"), "overallSignal")
    if overall_signal not in _OVERALL_SIGNALS:
        raise ValueError("overallSignal is invalid")
    overall_score = _bounded_integer(payload.get("overallScore"), "overallScore")
    if overall_signal == "INSUFFICIENT_DATA" and overall_score is not None:
        raise ValueError("INSUFFICIENT_DATA reports must not include overallScore")
    if overall_signal != "INSUFFICIENT_DATA" and overall_score is None:
        raise ValueError("Scored Job Signal reports require overallScore")
    source_fingerprint = _required_text(payload.get("sourceFingerprint"), "sourceFingerprint")
    evaluated_at = _timestamp(payload.get("evaluatedAt"), "evaluatedAt")

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
        evidence_ids = _string_list(raw.get("evidenceIds"), f"dimensions.{dimension}.evidenceIds")
        score = _bounded_integer(raw.get("score"), f"dimensions.{dimension}.score")
        confidence = _confidence(raw.get("confidence"), f"dimensions.{dimension}.confidence")
        if score is None and (confidence != 0 or evidence_ids):
            raise ValueError(f"Unknown dimension {dimension} cannot claim confidence or evidence")
        if score is not None and (confidence <= 0 or not evidence_ids):
            raise ValueError(f"Scored dimension {dimension} requires evidence and confidence")
        dimension_evidence[dimension] = evidence_ids
        dimensions.append(
            {
                "dimension": dimension,
                "score": score,
                "confidence": confidence,
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
        direction = _required_text(raw.get("direction"), f"signals[{index}].direction")
        if direction not in _DIRECTIONS:
            raise ValueError(f"signals[{index}].direction is invalid")
        source = _required_text(raw.get("source"), f"signals[{index}].source")
        if source not in _EVIDENCE_SOURCES:
            raise ValueError(f"signals[{index}].source is invalid")
        signal_dimensions[signal_id] = dimension
        signals.append(
            {
                "signalId": signal_id,
                "dimension": dimension,
                "severity": severity,
                "direction": direction,
                "source": source,
                "evidence": _required_text(raw.get("evidence"), f"signals[{index}].evidence"),
                "explanation": _required_text(
                    raw.get("explanation"), f"signals[{index}].explanation"
                ),
            }
        )

    referenced_ids = {
        signal_id for evidence_ids in dimension_evidence.values() for signal_id in evidence_ids
    }
    if referenced_ids != signal_ids:
        raise ValueError("dimension evidenceIds must reference every signal exactly once")
    for dimension, evidence_ids in dimension_evidence.items():
        if any(signal_dimensions[signal_id] != dimension for signal_id in evidence_ids):
            raise ValueError("dimension evidenceIds must reference signals in the same dimension")

    return {
        "reportId": report_id,
        "applicationId": application_id,
        "jobId": job_id,
        "sourceIdentity": source_identity,
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
            SELECT signal_id, dimension, severity, direction, source, evidence, explanation
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
            "jobId": row["job_id"],
            "sourceIdentity": row["source_identity"],
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
                    "direction": signal["direction"],
                    "source": signal["source"],
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
                "SELECT application_id, job_id FROM applications WHERE application_id = ?",
                (parsed["applicationId"],),
            ).fetchone()
            if application is None:
                raise KeyError("Job signal report references an unknown application")
            job = connection.execute(
                "SELECT job_id, job_url, application_url FROM jobs WHERE job_id = ?",
                (parsed["jobId"],),
            ).fetchone()
            if job is None:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        job_id, company, role, requisition_id, job_url,
                        application_url, location, work_arrangement,
                        employment_type, compensation, description,
                        created_at, updated_at
                    ) VALUES (?, NULL, NULL, NULL, ?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        parsed["jobId"],
                        parsed["sourceIdentity"],
                        parsed["sourceIdentity"],
                        parsed["evaluatedAt"],
                        parsed["evaluatedAt"],
                    ),
                )
            else:
                existing_source = job["application_url"] or job["job_url"]
                if existing_source and existing_source != parsed["sourceIdentity"]:
                    known_source = connection.execute(
                        """
                        SELECT 1
                        FROM job_signal_reports
                        WHERE job_id = ? AND source_identity = ?
                        """,
                        (parsed["jobId"], parsed["sourceIdentity"]),
                    ).fetchone()
                    if known_source is None:
                        connection.execute(
                            "UPDATE jobs SET updated_at = ? WHERE job_id = ?",
                            (parsed["evaluatedAt"], parsed["jobId"]),
                        )
            if application["job_id"] is None:
                connection.execute(
                    "UPDATE applications SET job_id = ? WHERE application_id = ?",
                    (parsed["jobId"], parsed["applicationId"]),
                )
            elif application["job_id"] != parsed["jobId"]:
                raise ValueError(
                    "Job signal report jobId conflicts with the durable application identity"
                )
            existing = connection.execute(
                """
                SELECT report_id
                FROM job_signal_reports
                WHERE application_id = ? AND job_id = ?
                  AND source_identity = ? AND source_fingerprint = ?
                """,
                (
                    parsed["applicationId"],
                    parsed["jobId"],
                    parsed["sourceIdentity"],
                    parsed["sourceFingerprint"],
                ),
            ).fetchone()
            if existing is None:
                conflicting_identity = connection.execute(
                    """
                    SELECT application_id, job_id, source_identity, source_fingerprint
                    FROM job_signal_reports
                    WHERE report_id = ?
                    """,
                    (parsed["reportId"],),
                ).fetchone()
                if conflicting_identity is not None:
                    raise ValueError(
                        "reportId is already bound to another application/source fingerprint"
                    )
            report_id = existing["report_id"] if existing else parsed["reportId"]
            connection.execute(
                """
                INSERT INTO job_signal_reports (
                    report_id, application_id, job_id, overall_signal, overall_score,
                    source_identity, source_fingerprint, evaluated_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    overall_signal = excluded.overall_signal,
                    overall_score = excluded.overall_score,
                    evaluated_at = excluded.evaluated_at,
                    updated_at = excluded.updated_at
                """,
                (
                    report_id,
                    parsed["applicationId"],
                    parsed["jobId"],
                    parsed["overallSignal"],
                    parsed["overallScore"],
                    parsed["sourceIdentity"],
                    parsed["sourceFingerprint"],
                    parsed["evaluatedAt"],
                    parsed["evaluatedAt"],
                    parsed["evaluatedAt"],
                ),
            )
            connection.execute(
                "DELETE FROM job_signal_dimensions WHERE report_id = ?", (report_id,)
            )
            connection.execute("DELETE FROM job_signal_evidence WHERE report_id = ?", (report_id,))
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
                    signal_id, report_id, dimension, severity, direction, source,
                    evidence, explanation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["signalId"],
                        report_id,
                        item["dimension"],
                        item["severity"],
                        item["direction"],
                        item["source"],
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
            analytics_metadata = {
                "reportId": report_id,
                "jobId": parsed["jobId"],
                "sourceIdentity": parsed["sourceIdentity"],
                "sourceFingerprint": parsed["sourceFingerprint"],
                "overallSignal": parsed["overallSignal"],
                "overallScore": parsed["overallScore"],
                "knownDimensionCount": sum(
                    1 for item in parsed["dimensions"] if item["score"] is not None
                ),
                "statisticalNote": (
                    "This Job Signal report is observational context and does not "
                    "establish that a posting signal caused an application outcome."
                ),
            }
            analytics_event_id = f"job-signals:{report_id}:{parsed['evaluatedAt']}"
            analytics_json = canonical_json(analytics_metadata)
            existing_event = connection.execute(
                "SELECT * FROM application_events WHERE event_id = ?",
                (analytics_event_id,),
            ).fetchone()
            if existing_event is None:
                connection.execute(
                    """
                    INSERT INTO application_events (
                        event_id, application_id, event_type, occurred_at,
                        source, metadata_json
                    ) VALUES (?, ?, 'JOB_SIGNALS_ANALYZED', ?, 'extension', ?)
                    """,
                    (
                        analytics_event_id,
                        parsed["applicationId"],
                        parsed["evaluatedAt"],
                        analytics_json,
                    ),
                )
            elif not (
                existing_event["application_id"] == parsed["applicationId"]
                and existing_event["event_type"] == "JOB_SIGNALS_ANALYZED"
                and existing_event["occurred_at"] == parsed["evaluatedAt"]
                and existing_event["source"] == "extension"
                and existing_event["metadata_json"] == analytics_json
            ):
                raise ValueError(
                    "Job Signal analytics event identity conflicts with immutable history"
                )
            stored = self._read(connection, str(report_id))
            if stored is None:
                raise RuntimeError("Job signal report was not persisted")
            return stored

    def latest(
        self,
        application_id: object,
        job_id: object,
        source_identity: object | None = None,
    ) -> dict[str, object] | None:
        normalized = _required_text(application_id, "applicationId")
        normalized_job_id = _required_text(job_id, "jobId")
        normalized_source = (
            None if source_identity is None else _required_text(source_identity, "sourceIdentity")
        )
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT report_id
                FROM job_signal_reports
                WHERE application_id = ? AND job_id = ?
                  AND (? IS NULL OR source_identity = ?)
                ORDER BY evaluated_at DESC, report_id DESC
                LIMIT 1
                """,
                (
                    normalized,
                    normalized_job_id,
                    normalized_source,
                    normalized_source,
                ),
            ).fetchone()
            return None if row is None else self._read(connection, row["report_id"])
