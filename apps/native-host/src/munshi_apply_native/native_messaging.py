from __future__ import annotations

import json
import struct
import sys
from datetime import UTC, datetime
from typing import BinaryIO

from .account_store import AccountStore
from .ai_draft_store import AIDraftStore
from .ai_governance import AIGovernanceService
from .ai_settings import AIConfiguration, AISettingsStore
from .application_analytics_store import ApplicationAnalyticsStore
from .application_store import ApplicationStore
from .checkpoint_store import ApplicationCheckpointStore
from .database import Database
from .document_ingestion import DocumentIngestionService
from .interaction_recipe_service import InteractionRecipeService
from .job_signal_store import JobSignalStore
from .models import ApplicationCheckpointPayload, EventEnvelope
from .profile_store import ProfileStore
from .settings import Settings
from .writing_style import WritingStyleStore

NATIVE_PROTOCOL_VERSION = 3
NATIVE_CAPABILITIES: dict[str, bool] = {
    "profile_vault": True,
    "application_checkpoints": True,
    "interaction_learning": True,
    "teach_munshi": True,
    "teach_munshi_state_capture": True,
    "ai_settings": True,
    "ai_governance": True,
    "ai_draft_lifecycle": True,
    "document_evidence_ingestion": True,
    "provider_routing": True,
    "ollama_fallback": True,
    "writing_style_learning": True,
    "account_orchestration": True,
    "job_signal_intelligence": True,
    "application_analytics": True,
}


def read_message(stream: BinaryIO) -> dict[str, object] | None:
    raw_length = stream.read(4)
    if not raw_length:
        return None
    if len(raw_length) != 4:
        raise ValueError("Incomplete native-message header")
    length = struct.unpack("<I", raw_length)[0]
    if length > 1_048_576:
        raise ValueError("Native message exceeds 1 MiB limit")
    payload = stream.read(length)
    if len(payload) != length:
        raise ValueError("Incomplete native-message payload")
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Native message must be a JSON object")
    return decoded


def write_message(stream: BinaryIO, payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    stream.write(struct.pack("<I", len(encoded)))
    stream.write(encoded)
    stream.flush()


def checkpoint_lookup_application_id(message: dict[str, object]) -> str:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Checkpoint lookup payload must be an object")
    application_id = payload.get("applicationId")
    if not isinstance(application_id, str) or not application_id.strip():
        raise ValueError("Checkpoint lookup requires applicationId")
    return application_id.strip()


def ensure_application_payload(message: dict[str, object]) -> tuple[str, str]:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Application ensure payload must be an object")
    application_id = payload.get("applicationId")
    observed_at = payload.get("observedAt")
    if not isinstance(application_id, str) or not application_id.strip():
        raise ValueError("Application ensure requires applicationId")
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise ValueError("Application ensure requires observedAt")
    normalized_observed_at = observed_at.strip()
    try:
        parsed = datetime.fromisoformat(normalized_observed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Application ensure observedAt must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("Application ensure observedAt must include a timezone")
    return application_id.strip(), normalized_observed_at


def job_signal_application_payload(message: dict[str, object]) -> tuple[str, str]:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Job signal payload must be an object")
    application_id = payload.get("applicationId")
    evaluated_at = payload.get("evaluatedAt")
    if not isinstance(application_id, str) or not application_id.strip():
        raise ValueError("Job signal report requires applicationId")
    if not isinstance(evaluated_at, str) or not evaluated_at.strip():
        raise ValueError("Job signal report requires evaluatedAt")
    normalized_evaluated_at = evaluated_at.strip()
    try:
        parsed = datetime.fromisoformat(normalized_evaluated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Job signal evaluatedAt must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("Job signal evaluatedAt must include a timezone")
    return application_id.strip(), normalized_evaluated_at


def job_signal_lookup_application_id(message: dict[str, object]) -> str:
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Job signal lookup payload must be an object")
    application_id = payload.get("applicationId")
    if not isinstance(application_id, str) or not application_id.strip():
        raise ValueError("Job signal lookup requires applicationId")
    return application_id.strip()


def handle(
    message: dict[str, object],
    database: Database,
    ai_store: AISettingsStore | None = None,
) -> dict[str, object]:
    message_type = message.get("type")
    if message_type == "PING":
        health = database.health()
        health["protocol_version"] = NATIVE_PROTOCOL_VERSION
        health["capabilities"] = dict(NATIVE_CAPABILITIES)
        return {"ok": True, "data": health}
    if message_type == "APPEND_EVENT":
        event = EventEnvelope.model_validate(message.get("payload"))
        database.append_event(event.database_record())
        return {"ok": True}
    if message_type == "GET_PROFILE_SNAPSHOT":
        return {"ok": True, "data": ProfileStore(database).latest()}
    if message_type == "SAVE_PROFILE_SNAPSHOT":
        payload = message.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("Profile snapshot payload must be an object")
        ProfileStore(database).save(payload)
        return {"ok": True}
    if message_type == "ENSURE_APPLICATION":
        application_id, observed_at = ensure_application_payload(message)
        created = ApplicationStore(database).ensure(application_id, observed_at)
        return {"ok": True, "data": {"created": created}}
    if message_type == "LOOKUP_ACCOUNTS":
        return {
            "ok": True,
            "data": AccountStore(database).lookup(message.get("payload")),
        }
    if message_type == "UPSERT_ACCOUNT":
        payload = message.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("Account upsert payload must be an object")
        application_id = payload.get("applicationId")
        if application_id is not None:
            normalized_application_id, observed_at = ensure_application_payload(message)
            ApplicationStore(database).ensure(normalized_application_id, observed_at)
        return {
            "ok": True,
            "data": AccountStore(database).upsert(payload),
        }
    if message_type == "SAVE_JOB_SIGNAL_REPORT":
        application_id, evaluated_at = job_signal_application_payload(message)
        ApplicationStore(database).ensure(application_id, evaluated_at)
        return {
            "ok": True,
            "data": JobSignalStore(database).save(message.get("payload")),
        }
    if message_type == "GET_LATEST_JOB_SIGNAL_REPORT":
        application_id = job_signal_lookup_application_id(message)
        return {
            "ok": True,
            "data": JobSignalStore(database).latest(application_id),
        }
    if message_type == "RECORD_APPLICATION_ANALYTICS_EVENT":
        created = ApplicationAnalyticsStore(database).record_event(message.get("payload"))
        return {"ok": True, "data": {"created": created}}
    if message_type == "RECORD_APPLICATION_ATTRIBUTION_CONTEXT":
        created = ApplicationAnalyticsStore(database).record_context(message.get("payload"))
        return {"ok": True, "data": {"created": created}}
    if message_type == "RECORD_APPLICATION_OUTCOME":
        created = ApplicationAnalyticsStore(database).record_outcome(message.get("payload"))
        return {"ok": True, "data": {"created": created}}
    if message_type == "GET_APPLICATION_ANALYTICS_SNAPSHOT":
        return {"ok": True, "data": ApplicationAnalyticsStore(database).snapshot()}
    if message_type == "SAVE_APPLICATION_CHECKPOINT":
        checkpoint = ApplicationCheckpointPayload.model_validate(message.get("payload"))
        created = ApplicationCheckpointStore(database).save(checkpoint.database_record())
        return {
            "ok": True,
            "data": {"created": created, "checkpoint": checkpoint.wire_payload()},
        }
    if message_type == "GET_LATEST_APPLICATION_CHECKPOINT":
        application_id = checkpoint_lookup_application_id(message)
        stored = ApplicationCheckpointStore(database).latest(application_id)
        if stored is None:
            return {"ok": True, "data": None}
        checkpoint = ApplicationCheckpointPayload.model_validate(stored)
        return {"ok": True, "data": checkpoint.wire_payload()}
    if message_type == "GET_INTERACTION_RECIPE":
        return {
            "ok": True,
            "data": InteractionRecipeService(database).lookup(message.get("payload")),
        }
    if message_type == "RECORD_INTERACTION_RECIPE_ATTEMPT":
        return {
            "ok": True,
            "data": InteractionRecipeService(database).record(message.get("payload")),
        }
    if message_type == "TEACH_INTERACTION_RECIPE":
        return {
            "ok": True,
            "data": InteractionRecipeService(database).teach(message.get("payload")),
        }
    if message_type == "RECORD_INTERACTION_RECIPE_OUTCOME":
        return {
            "ok": True,
            "data": InteractionRecipeService(database).record_outcome(message.get("payload")),
        }

    if message_type in {
        "BEGIN_DOCUMENT_INGESTION",
        "APPEND_DOCUMENT_CHUNK",
        "FINISH_DOCUMENT_INGESTION",
        "CANCEL_DOCUMENT_INGESTION",
    }:
        ingestion = DocumentIngestionService(database)
        if message_type == "BEGIN_DOCUMENT_INGESTION":
            return {"ok": True, "data": ingestion.begin(message.get("payload"))}
        if message_type == "APPEND_DOCUMENT_CHUNK":
            return {"ok": True, "data": ingestion.append(message.get("payload"))}
        if message_type == "FINISH_DOCUMENT_INGESTION":
            return {"ok": True, "data": ingestion.finish(message.get("payload"))}
        return {"ok": True, "data": ingestion.cancel(message.get("payload"))}

    if message_type in {
        "GET_AI_SETTINGS",
        "SAVE_AI_SETTINGS",
        "SET_OPENAI_API_KEY",
        "DELETE_OPENAI_API_KEY",
        "TEST_OPENAI_CONNECTION",
        "LIST_OPENAI_MODELS",
        "TEST_OLLAMA_CONNECTION",
        "LIST_OLLAMA_MODELS",
        "GET_AI_CONTROL_STATUS",
        "GET_WRITING_STYLE",
        "PREVIEW_AI_DRAFT",
        "GENERATE_AI_DRAFT",
        "LIST_AI_DRAFTS",
        "GET_APPROVED_AI_DRAFT",
        "UPDATE_AI_DRAFT",
        "APPROVE_AI_DRAFT",
        "REJECT_AI_DRAFT",
        "MARK_AI_DRAFT_USED",
    }:
        if ai_store is None:
            return {"ok": False, "error": "AI settings store is unavailable"}
        if message_type == "GET_AI_SETTINGS":
            return {"ok": True, "data": ai_store.status()}
        if message_type == "SAVE_AI_SETTINGS":
            config = AIConfiguration.from_payload(message.get("payload"))
            ai_store.save(config)
            return {"ok": True, "data": ai_store.status()}
        if message_type == "SET_OPENAI_API_KEY":
            payload = message.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("API key payload must be an object")
            ai_store.set_api_key(payload.get("apiKey"))
            return {"ok": True, "data": ai_store.status()}
        if message_type == "DELETE_OPENAI_API_KEY":
            ai_store.delete_api_key()
            return {"ok": True, "data": ai_store.status()}
        if message_type == "TEST_OPENAI_CONNECTION":
            models = ai_store.list_models()
            return {"ok": True, "data": {"modelCount": len(models)}}
        if message_type == "LIST_OPENAI_MODELS":
            return {"ok": True, "data": {"models": ai_store.list_models()}}
        if message_type == "TEST_OLLAMA_CONNECTION":
            models = ai_store.list_ollama_models()
            return {"ok": True, "data": {"modelCount": len(models)}}
        if message_type == "LIST_OLLAMA_MODELS":
            return {"ok": True, "data": {"models": ai_store.list_ollama_models()}}
        if message_type == "GET_WRITING_STYLE":
            return {"ok": True, "data": WritingStyleStore(ai_store.runtime_root).status()}
        if message_type in {
            "LIST_AI_DRAFTS",
            "GET_APPROVED_AI_DRAFT",
            "UPDATE_AI_DRAFT",
            "APPROVE_AI_DRAFT",
            "REJECT_AI_DRAFT",
            "MARK_AI_DRAFT_USED",
        }:
            payload = message.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("AI draft lifecycle payload must be an object")
            drafts = AIDraftStore(database)
            at = datetime.now(UTC).isoformat()
            if message_type == "LIST_AI_DRAFTS":
                application_id = payload.get("applicationId")
                page_id = payload.get("pageId")
                if not isinstance(application_id, str):
                    raise ValueError("AI draft list requires applicationId")
                if page_id is not None and not isinstance(page_id, str):
                    raise ValueError("AI draft pageId must be a string")
                return {
                    "ok": True,
                    "data": drafts.list_for_application(application_id, page_id),
                }
            if message_type == "GET_APPROVED_AI_DRAFT":
                return {"ok": True, "data": drafts.approved_for(payload)}
            draft_id = payload.get("draftId")
            if not isinstance(draft_id, str):
                raise ValueError("AI draft lifecycle request requires draftId")
            if message_type == "UPDATE_AI_DRAFT":
                return {
                    "ok": True,
                    "data": drafts.update_text(
                        draft_id,
                        payload.get("text"),
                        payload.get("expectedSha256"),
                        at,
                    ),
                }
            if message_type == "APPROVE_AI_DRAFT":
                before = drafts.get(draft_id)
                approved = drafts.approve(draft_id, payload.get("expectedSha256"), at)
                WritingStyleStore(ai_store.runtime_root).learn_from_approved_edit(
                    str(before["originalText"]), str(approved["currentText"])
                )
                return {"ok": True, "data": approved}
            if message_type == "REJECT_AI_DRAFT":
                return {"ok": True, "data": drafts.reject(draft_id, at)}
            return {"ok": True, "data": drafts.mark_used(draft_id, at)}
        governance = AIGovernanceService(database, ai_store)
        if message_type == "GET_AI_CONTROL_STATUS":
            return {"ok": True, "data": governance.control_status()}
        if message_type == "PREVIEW_AI_DRAFT":
            return {"ok": True, "data": governance.preview(message.get("payload"))}
        if message_type == "GENERATE_AI_DRAFT":
            return {"ok": True, "data": governance.generate(message.get("payload"))}

    return {"ok": False, "error": "Unsupported native message"}


def main() -> None:
    settings = Settings.from_environment()
    database = Database(settings.database_path, settings.migrations_path)
    database.migrate()
    ai_store = AISettingsStore(settings.runtime_root)
    while message := read_message(sys.stdin.buffer):
        try:
            write_message(sys.stdout.buffer, handle(message, database, ai_store))
        except Exception as error:
            write_message(sys.stdout.buffer, {"ok": False, "error": str(error)})


if __name__ == "__main__":
    main()
