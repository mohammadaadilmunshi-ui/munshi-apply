"""Value-free, evidence-gated observations of MUNSHI Native form actions.

This module does not fill forms, learn applicant answers, promote recipes, or
authorize submission. Browser actions only become evidence after a subsequent
DOM scan independently confirms that the target field is committed.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .hunter_plan_semantic_bridge import logical_field_fingerprint

VERSION = "munshi-native-form-action-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_KINDS = frozenset(
    {
        "text",
        "textarea",
        "email",
        "tel",
        "phone",
        "date",
        "number",
        "checkbox",
        "radio",
        "select",
        "combobox",
        "search",
        "url",
        "single_select",
        "multi_select",
        "typeahead",
        "boolean",
    }
)
_SECURITY = frozenset(
    {
        "PASSWORD",
        "OTP",
        "TOTP",
        "SMS",
        "MFA",
        "CAPTCHA",
        "BIOMETRIC",
        "IDENTITY_VERIFICATION",
        "GOVERNMENT_ID",
        "LEGAL_ATTESTATION",
        "SUBMIT",
        "FINAL_SUBMIT",
        "LIVENESS",
    }
)
_STRATEGIES = frozenset(
    {
        "WORKDAY_PROVIDER_PROMPT",
        "WORKDAY_PHONE_CANONICAL_VARIANT",
        "WORKDAY_TRUSTED_PLAYWRIGHT",
        "WORKDAY_PROVIDER_CHOICE",
        "WORKDAY_PROMPT_SELECTED_ITEM",
        "ARIA_COMBOBOX",
        "ARIA_RADIO",
        "ARIA_BOOLEAN",
        "CUSTOM_DATE",
        "CUSTOM_MULTI_SELECT",
        "GENERIC_RUNTIME",
    }
)


def _token(value: Any, *, fallback: str = "UNKNOWN") -> str:
    text = str(value or "").strip().upper()
    return text if _TOKEN.fullmatch(text) else fallback


def observe_action(
    *,
    question: Mapping[str, Any],
    control: Mapping[str, Any],
    result: Mapping[str, Any],
    ats_family: str,
    sensitivity: str,
) -> dict[str, Any] | None:
    """Create only structural evidence, never labels, values, or DOM selectors."""
    semantic = _token(question.get("semanticType") or question.get("semantic_type"))
    if sensitivity.upper() != "NORMAL" or any(marker in semantic for marker in _SECURITY):
        return None
    fingerprint = logical_field_fingerprint(question, control)
    if not fingerprint or not _SHA256.fullmatch(fingerprint):
        return None
    kind = str(control.get("inputType") or control.get("role") or "").lower()
    strategy = _token(result.get("strategy"), fallback="GENERIC_RUNTIME")
    return {
        "version": VERSION,
        "field_fingerprint": fingerprint,
        "ats_family": _token(ats_family),
        "semantic_type": semantic,
        "control_kind": kind if kind in _KINDS else "unknown",
        "strategy": strategy if strategy in _STRATEGIES else "GENERIC_RUNTIME",
        "attempt_status": (
            str(result.get("status")) if result.get("status") in {"FILLED", "FAILED"} else "OTHER"
        ),
        "verification_status": "UNVERIFIED",
    }


def finalize_action(action: Mapping[str, Any], *, committed: bool) -> dict[str, Any]:
    """A fill is verified only when the later browser scan confirms it."""
    record = dict(action)
    if record.get("version") != VERSION:
        raise ValueError("Unsupported native learning observation")
    record["verification_status"] = (
        "POST_SCAN_COMMITTED"
        if committed and record.get("attempt_status") == "FILLED"
        else "UNVERIFIED"
    )
    return record


def summarize_actions(
    events: Iterable[Mapping[str, Any]],
    *,
    min_distinct_applications: int = 3,
) -> dict[str, Any]:
    """Aggregate held-back learning hypotheses; never create executable rules.

    Each input has an opaque ``session_id``, canonical ``application_id``, and
    an ``actions`` sequence. A replacement plan or retry for the same
    application cannot satisfy the cross-application evidence threshold.
    """
    if min_distinct_applications < 3:
        raise ValueError("Native learning needs at least three independent applications")
    support: dict[tuple[str, str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"verified": set(), "unverified": set()}
    )
    portable: dict[tuple[str, str, str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"verified": set(), "unverified": set()}
    )
    provider_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "attempts": 0,
            "verified": 0,
            "unverified": 0,
            "verified_applications": set(),
            "control_kinds": set(),
        }
    )
    examined = verified = 0
    for event in events:
        session_id = str(event.get("session_id") or "")
        application_id = str(event.get("application_id") or "")
        if not 1 <= len(session_id) <= 128 or not 1 <= len(application_id) <= 128:
            continue
        actions = event.get("actions")
        if not isinstance(actions, list):
            continue
        for action in actions[:120]:
            if not isinstance(action, Mapping) or action.get("version") != VERSION:
                continue
            fingerprint = str(action.get("field_fingerprint") or "")
            ats = _token(action.get("ats_family"))
            strategy = _token(action.get("strategy"))
            semantic = _token(action.get("semantic_type"))
            kind = str(action.get("control_kind") or "unknown")
            if not _SHA256.fullmatch(fingerprint) or strategy not in _STRATEGIES:
                continue
            examined += 1
            key = (ats, fingerprint, strategy)
            portable_key = (ats, semantic, kind, strategy)
            verified_commit = (
                action.get("verification_status") == "POST_SCAN_COMMITTED"
                and action.get("attempt_status") == "FILLED"
            )
            result_bucket = "verified" if verified_commit else "unverified"
            support[key][result_bucket].add(application_id)
            provider = provider_stats[ats]
            provider["attempts"] += 1
            provider["control_kinds"].add(kind if kind in _KINDS else "unknown")
            if result_bucket == "verified":
                provider["verified"] += 1
                provider["verified_applications"].add(application_id)
            else:
                provider["unverified"] += 1
            # A portable pattern must have a recognized ATS, semantic and
            # control type. It is a shadow hypothesis, never an executable rule.
            if ats != "UNKNOWN" and semantic != "UNKNOWN" and kind in _KINDS:
                portable[portable_key][result_bucket].add(application_id)
            if verified_commit:
                verified += 1
    hypotheses = [
        {
            "ats_family": ats,
            "field_fingerprint": fingerprint,
            "strategy": strategy,
            "verified_applications": len(counts["verified"]),
            "failed_or_unverified_applications": len(counts["unverified"]),
            "state": "SHADOW_ONLY",
        }
        for (ats, fingerprint, strategy), counts in sorted(support.items())
        if len(counts["verified"]) >= min_distinct_applications and not counts["unverified"]
    ]
    portable_hypotheses = [
        {
            "ats_family": ats,
            "semantic_type": semantic,
            "control_kind": kind,
            "strategy": strategy,
            "verified_applications": len(counts["verified"]),
            "failed_or_unverified_applications": len(counts["unverified"]),
            "state": "SHADOW_ONLY",
        }
        for (ats, semantic, kind, strategy), counts in sorted(portable.items())
        if len(counts["verified"]) >= min_distinct_applications and not counts["unverified"]
    ]
    held_out_queue = [
        {
            "ats_family": ats,
            "observed_action_attempts": stats["attempts"],
            "post_scan_verified_actions": stats["verified"],
            "unverified_action_attempts": stats["unverified"],
            "distinct_verified_applications": len(stats["verified_applications"]),
            "observed_control_kinds": sorted(stats["control_kinds"]),
            "next_self_test": (
                "CLASSIFY_PROVIDER_IN_ISOLATED_BROWSER"
                if ats == "UNKNOWN"
                else "REPLAY_UNVERIFIED_CONTROLS_IN_ISOLATED_BROWSER"
                if stats["unverified"]
                else "HELD_OUT_SHADOW_REPLAY_REQUIRED"
                if any(item["ats_family"] == ats for item in portable_hypotheses)
                else "COLLECT_DISTINCT_APPLICATION_FORM_EVIDENCE"
            ),
            "submission_authorized": False,
        }
        for ats, stats in sorted(
            provider_stats.items(),
            key=lambda item: (-item[1]["unverified"], -item[1]["attempts"], item[0]),
        )
    ]
    return {
        "version": VERSION,
        "observed_action_attempts": examined,
        "post_scan_verified_actions": verified,
        "shadow_hypotheses": hypotheses[:100],
        "portable_shadow_hypotheses": portable_hypotheses[:100],
        "cross_application_minimum": min_distinct_applications,
        "held_out_self_test_queue": held_out_queue[:44],
        "native_replay_verified": False,
        "executable_rules_promoted": 0,
        "submission_authorized": False,
        "answer_values_stored": False,
    }


def native_learning_snapshot(
    database: Any, *, tenant_id: str, user_id: str, max_events: int = 5000
) -> dict[str, Any]:
    """Read-only operational digest of Native actions and receipt verification.

    Does not export event evidence or application identifiers. Bounded reads
    prevent a large execution history from overwhelming dashboard workers.
    """
    if not 1 <= max_events <= 10000:
        raise ValueError("Native learning snapshot must be bounded")
    if not tenant_id or not user_id:
        raise PermissionError("Native learning requires an authenticated owner")
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT e.session_id,p.application_id,e.evidence_json,e.occurred_at
                 FROM complete_application_execution_events e
                 JOIN career_os_application_plans p ON p.plan_id=e.plan_id
                WHERE e.event_type='FORM_PREPARED'
                  AND p.tenant_id=? AND p.user_id=?
                ORDER BY e.occurred_at DESC,e.event_id DESC LIMIT ?""",
            (tenant_id, user_id, max_events),
        ).fetchall()
        receipts = connection.execute(
            """SELECT r.verification_status,COUNT(*)
                 FROM application_submission_receipts r
                 JOIN career_os_application_plans p ON p.plan_id=r.plan_id
                WHERE p.tenant_id=? AND p.user_id=?
                GROUP BY r.verification_status""",
            (tenant_id, user_id),
        ).fetchall()
        commands = connection.execute(
            """SELECT COUNT(*) FROM final_submit_commands c
                 JOIN career_os_application_plans p ON p.plan_id=c.plan_id
                WHERE p.tenant_id=? AND p.user_id=?""",
            (tenant_id, user_id),
        ).fetchone()[0]
    events = []
    latest = None
    for row in rows:
        try:
            evidence = json.loads(row["evidence_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(evidence, dict):
            continue
        actions = evidence.get("native_field_learning_evidence")
        if not isinstance(actions, list):
            continue
        events.append(
            {
                "session_id": str(row["session_id"]),
            "application_id": str(row["application_id"]),
                "actions": actions,
            }
        )
        observed = str(row["occurred_at"] or "")
        latest = max(latest or observed, observed) if observed else latest
    summary = summarize_actions(events)
    summary.update(
        {
            "form_preparation_events_checked": len(rows),
            "preparation_events_with_native_learning": len(events),
            "latest_native_form_evidence_at": latest,
            "native_final_submit_commands": int(commands),
            "native_employer_receipts_verified": sum(
                int(count) for status, count in receipts if status == "VERIFIED"
            ),
            "native_receipts_unverified_or_blocked": sum(
                int(count) for status, count in receipts if status != "VERIFIED"
            ),
            "provider_statuses_counted_as_receipts": False,
        }
    )
    return summary
