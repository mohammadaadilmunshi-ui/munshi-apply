#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUNTIME_DIRECTORIES = (
    "database",
    "resumes/master",
    "resumes/tailored",
    "resumes/submitted",
    "evidence",
    "embeddings",
    "learning",
    "exports",
    "logs",
    "diagnostics",
    "backups",
    "secrets",
    "settings",
    "releases",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate(database_path: Path, migrations_path: Path) -> list[str]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    applied_now: list[str] = []
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row[0]
            for row in connection.execute("SELECT migration FROM schema_migrations")
        }
        for migration in sorted(migrations_path.glob("[0-9][0-9][0-9]_*.sql")):
            if migration.name in applied:
                continue
            connection.executescript(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (migration) VALUES (?)",
                (migration.name,),
            )
            applied_now.append(migration.name)
    return applied_now


def health(database_path: Path, migrations_path: Path) -> dict[str, Any]:
    expected = [
        path.name for path in sorted(migrations_path.glob("[0-9][0-9][0-9]_*.sql"))
    ]
    with sqlite3.connect(database_path) as connection:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        applied = [
            row[0]
            for row in connection.execute(
                "SELECT migration FROM schema_migrations ORDER BY migration"
            )
        ]
        outbox_exists = (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'outbox_events'"
            ).fetchone()
            is not None
        )
        outbox_pending = (
            connection.execute(
                """
                SELECT COUNT(*) FROM outbox_events
                WHERE delivery_status IN ('PENDING', 'RETRY', 'IN_FLIGHT')
                """
            ).fetchone()[0]
            if outbox_exists
            else None
        )
    status = (
        "healthy"
        if quick_check == "ok" and applied == expected and outbox_exists
        else "unhealthy"
    )
    return {
        "status": status,
        "database": str(database_path),
        "quick_check": quick_check,
        "expected_migrations": expected,
        "applied_migrations": applied,
        "schema_version": applied[-1] if applied else None,
        "outbox_exists": outbox_exists,
        "outbox_pending": outbox_pending,
    }


def create_backup(runtime_root: Path) -> Path:
    database_path = runtime_root / "database/munshi-apply.sqlite"
    if not database_path.is_file():
        raise FileNotFoundError(f"Runtime database does not exist: {database_path}")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = runtime_root / "backups" / timestamp
    destination.mkdir(parents=True, exist_ok=False)

    backup_database = destination / "database/munshi-apply.sqlite"
    backup_database.parent.mkdir(parents=True)
    with (
        sqlite3.connect(database_path) as source,
        sqlite3.connect(backup_database) as target,
    ):
        source.backup(target)

    included = [backup_database]
    for relative_directory in ("settings", "evidence", "learning"):
        source_directory = runtime_root / relative_directory
        if not source_directory.exists():
            continue
        for source_path in source_directory.rglob("*"):
            if not source_path.is_file() or source_path.suffix not in {
                ".json",
                ".toml",
            }:
                continue
            relative_path = source_path.relative_to(runtime_root)
            target_path = destination / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            included.append(target_path)

    manifest_path = destination / "manifest.json"
    manifest = {
        "schema_version": "1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "runtime_root": str(runtime_root),
        "contents": [str(path.relative_to(destination)) for path in sorted(included)],
        "note": "SQLite is authoritative; private resume files are not duplicated by this metadata backup.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    included.append(manifest_path)

    checksums_path = destination / "checksums.sha256"
    checksum_lines = [
        f"{sha256_file(path)}  {path.relative_to(destination)}"
        for path in sorted(included)
    ]
    checksums_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return destination


def verify_backup(backup_path: Path) -> None:
    checksums_path = backup_path / "checksums.sha256"
    if not checksums_path.is_file():
        raise FileNotFoundError(f"Backup checksum file is missing: {checksums_path}")
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        expected, relative_path = line.split("  ", 1)
        target = backup_path / relative_path
        if not target.is_file() or sha256_file(target) != expected:
            raise ValueError(f"Backup checksum mismatch: {relative_path}")


def write_native_manifest(extension_id: str, launcher: Path, destination: Path) -> None:
    manifest = {
        "name": "systems.munshi.apply",
        "description": "MUNSHI Apply local companion",
        "path": str(launcher.resolve()),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def native_smoke(
    command: list[str], database_path: Path, migrations_path: Path
) -> dict[str, Any]:
    payload = json.dumps({"type": "PING"}, separators=(",", ":")).encode()
    framed = struct.pack("<I", len(payload)) + payload
    environment = {
        **os.environ,
        "MUNSHI_DATABASE_PATH": str(database_path),
        "MUNSHI_MIGRATIONS_PATH": str(migrations_path),
    }
    completed = subprocess.run(
        command,
        input=framed,
        capture_output=True,
        check=True,
        timeout=10,
        env=environment,
    )
    if len(completed.stdout) < 4:
        raise ValueError("Native companion returned an incomplete response")
    length = struct.unpack("<I", completed.stdout[:4])[0]
    response = json.loads(completed.stdout[4 : 4 + length])
    if not response.get("ok") or response.get("data", {}).get("status") != "healthy":
        raise ValueError(f"Native companion health check failed: {response}")
    return response


def installation_report(
    runtime_root: Path, output: Path, extension_id: str | None
) -> None:
    report = {
        "schema_version": "1.0",
        "installed_at": datetime.now(UTC).isoformat(),
        "runtime_root": str(runtime_root),
        "extension_id": extension_id,
        "n8n_configured": bool(os.getenv("MUNSHI_N8N_WEBHOOK_URL")),
        "secrets_redacted": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MUNSHI Apply private-runtime operations"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--database", type=Path, required=True)
    migrate_parser.add_argument("--migrations", type=Path, required=True)

    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--database", type=Path, required=True)
    health_parser.add_argument("--migrations", type=Path, required=True)

    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--runtime-root", type=Path, required=True)

    verify_backup_parser = subparsers.add_parser("verify-backup")
    verify_backup_parser.add_argument("--backup", type=Path, required=True)

    manifest_parser = subparsers.add_parser("native-manifest")
    manifest_parser.add_argument("--extension-id", required=True)
    manifest_parser.add_argument("--launcher", type=Path, required=True)
    manifest_parser.add_argument("--output", type=Path, required=True)

    smoke_parser = subparsers.add_parser("native-smoke")
    smoke_parser.add_argument("--launcher", type=Path)
    smoke_parser.add_argument("--python")
    smoke_parser.add_argument("--module-root", type=Path)
    smoke_parser.add_argument("--database", type=Path, required=True)
    smoke_parser.add_argument("--migrations", type=Path, required=True)

    report_parser = subparsers.add_parser("installation-report")
    report_parser.add_argument("--runtime-root", type=Path, required=True)
    report_parser.add_argument("--output", type=Path, required=True)
    report_parser.add_argument("--extension-id")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "migrate":
        print(json.dumps({"applied": migrate(args.database, args.migrations)}))
    elif args.command == "health":
        result = health(args.database, args.migrations)
        print(json.dumps(result, indent=2))
        if result["status"] != "healthy":
            raise SystemExit(1)
    elif args.command == "backup":
        print(create_backup(args.runtime_root))
    elif args.command == "verify-backup":
        verify_backup(args.backup)
        print(f"Backup verified: {args.backup}")
    elif args.command == "native-manifest":
        write_native_manifest(args.extension_id, args.launcher, args.output)
        print(args.output)
    elif args.command == "native-smoke":
        if args.launcher:
            command = [str(args.launcher)]
        elif args.python and args.module_root:
            command = [args.python, "-m", "munshi_apply_native.native_messaging"]
            current = os.getenv("PYTHONPATH")
            os.environ["PYTHONPATH"] = (
                f"{args.module_root}{os.pathsep}{current}"
                if current
                else str(args.module_root)
            )
        else:
            raise ValueError("Provide --launcher or both --python and --module-root")
        print(
            json.dumps(native_smoke(command, args.database, args.migrations), indent=2)
        )
    elif args.command == "installation-report":
        installation_report(args.runtime_root, args.output, args.extension_id)
        print(args.output)


if __name__ == "__main__":
    try:
        main()
    except (
        FileNotFoundError,
        ValueError,
        sqlite3.Error,
        subprocess.SubprocessError,
    ) as error:
        print(f"runtime operation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
