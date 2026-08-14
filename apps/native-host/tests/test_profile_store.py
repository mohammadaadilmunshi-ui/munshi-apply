from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from munshi_apply_native.database import Database
from munshi_apply_native.profile_store import ProfileStore


def create_store(tmp_path: Path) -> ProfileStore:
    migrations = Path(__file__).resolve().parents[3] / "migrations"
    database = Database(tmp_path / "profile.sqlite", migrations)
    database.migrate()
    return ProfileStore(database)


def test_profile_snapshot_round_trip_includes_repeatable_records(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    profile = {
        "profileId": "profile-1",
        "displayName": "Application profile",
        "facts": [
            {
                "factId": "fact-email",
                "key": "email",
                "value": "candidate@example.com",
                "category": "CONTACT",
                "trustLevel": "USER_CONFIRMED",
                "source": "test",
                "confirmedAt": now,
                "updatedAt": now,
                "protected": False,
            }
        ],
        "records": [
            {
                "recordId": "employment-1",
                "kind": "EMPLOYMENT",
                "label": "Employer A",
                "facts": [
                    {
                        "factId": "fact-employer",
                        "key": "employer_name",
                        "value": "Employer A",
                        "category": "EMPLOYMENT",
                        "trustLevel": "USER_CONFIRMED",
                        "source": "test",
                        "confirmedAt": now,
                        "updatedAt": now,
                        "protected": False,
                    }
                ],
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "createdAt": now,
        "updatedAt": now,
        "schemaVersion": 1,
    }

    store.save(profile)
    restored = store.latest()

    assert restored == profile


def test_profile_snapshot_replace_removes_stale_facts_and_records(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    original = {
        "profileId": "profile-1",
        "displayName": "Application profile",
        "facts": [
            {
                "factId": "fact-email",
                "key": "email",
                "value": "old@example.com",
                "category": "CONTACT",
                "trustLevel": "USER_CONFIRMED",
                "source": "test",
                "confirmedAt": now,
                "updatedAt": now,
                "protected": False,
            },
            {
                "factId": "fact-phone",
                "key": "phone",
                "value": "555-0100",
                "category": "CONTACT",
                "trustLevel": "USER_CONFIRMED",
                "source": "test",
                "confirmedAt": now,
                "updatedAt": now,
                "protected": False,
            },
        ],
        "records": [
            {
                "recordId": "education-1",
                "kind": "EDUCATION",
                "label": "School A",
                "facts": [],
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "createdAt": now,
        "updatedAt": now,
        "schemaVersion": 1,
    }
    store.save(original)

    replacement = {
        **original,
        "facts": [
            {
                **original["facts"][0],
                "value": "new@example.com",
            }
        ],
        "records": [],
    }
    store.save(replacement)

    restored = store.latest()
    assert restored is not None
    assert [fact["key"] for fact in restored["facts"]] == ["email"]
    assert restored["facts"][0]["value"] == "new@example.com"
    assert restored["records"] == []


def test_legacy_flat_profile_without_records_remains_readable(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    now = datetime.now(UTC).isoformat()
    profile = {
        "profileId": "profile-legacy",
        "displayName": "Legacy profile",
        "facts": [],
        "createdAt": now,
        "updatedAt": now,
        "schemaVersion": 1,
    }

    store.save(profile)
    restored = store.latest()

    assert restored is not None
    assert restored["profileId"] == "profile-legacy"
    assert restored["records"] == []
