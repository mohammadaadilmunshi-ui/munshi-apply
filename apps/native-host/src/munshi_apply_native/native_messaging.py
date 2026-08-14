from __future__ import annotations

import json
import struct
import sys
from typing import BinaryIO

from .ai_settings import AIConfiguration, AISettingsStore
from .database import Database
from .models import EventEnvelope
from .settings import Settings


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


def handle(
    message: dict[str, object],
    database: Database,
    ai_store: AISettingsStore | None = None,
) -> dict[str, object]:
    message_type = message.get("type")
    if message_type == "PING":
        return {"ok": True, "data": database.health()}
    if message_type == "APPEND_EVENT":
        event = EventEnvelope.model_validate(message.get("payload"))
        database.append_event(event.database_record())
        return {"ok": True}

    if message_type in {
        "GET_AI_SETTINGS",
        "SAVE_AI_SETTINGS",
        "SET_OPENAI_API_KEY",
        "DELETE_OPENAI_API_KEY",
        "TEST_OPENAI_CONNECTION",
        "LIST_OPENAI_MODELS",
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

    return {"ok": False, "error": "Unsupported native message"}


def main() -> None:
    settings = Settings.from_environment()
    database = Database(settings.database_path, settings.migrations_path)
    database.migrate()
    ai_store = AISettingsStore(settings.runtime_root)
    while message := read_message(sys.stdin.buffer):
        try:
            write_message(sys.stdout.buffer, handle(message, database, ai_store))
        except Exception as error:  # The protocol must return structured failures.
            write_message(sys.stdout.buffer, {"ok": False, "error": str(error)})


if __name__ == "__main__":
    main()
