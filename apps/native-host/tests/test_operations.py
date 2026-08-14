from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_OPS = REPOSITORY_ROOT / "scripts/runtime-ops.py"
RELEASE_OPS = REPOSITORY_ROOT / "scripts/release-ops.py"
MIGRATIONS = REPOSITORY_ROOT / "migrations"


def run_runtime(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and repository script.
        [sys.executable, str(RUNTIME_OPS), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def test_runtime_migration_health_and_backup_round_trip(tmp_path: Path) -> None:
    runtime_root = tmp_path / "private-runtime"
    database = runtime_root / "database/munshi-apply.sqlite"
    ai_settings = runtime_root / "settings/ai.json"

    first = run_runtime("migrate", "--database", str(database), "--migrations", str(MIGRATIONS))
    second = run_runtime("migrate", "--database", str(database), "--migrations", str(MIGRATIONS))
    health = run_runtime("health", "--database", str(database), "--migrations", str(MIGRATIONS))
    ai_settings.parent.mkdir(parents=True)
    ai_settings.write_text(
        '{"provider":"openai","model":"gpt-test","enabled":false}\n',
        encoding="utf-8",
    )
    backup = run_runtime("backup", "--runtime-root", str(runtime_root))
    backup_path = Path(backup.stdout.strip())
    verified = run_runtime("verify-backup", "--backup", str(backup_path))

    assert json.loads(first.stdout)["applied"] == [
        "001_initial.sql",
        "002_transactional_outbox.sql",
        "003_profile_evidence_checkpoints.sql",
        "004_learning_analytics.sql",
        "005_profile_snapshot_ordering.sql",
        "006_ai_budget_reservations.sql",
    ]
    assert json.loads(second.stdout)["applied"] == []
    assert json.loads(health.stdout)["status"] == "healthy"
    assert "Backup verified" in verified.stdout
    assert (backup_path / "settings/ai.json").read_text(encoding="utf-8") == (
        ai_settings.read_text(encoding="utf-8")
    )


def test_native_protocol_source_health_check(tmp_path: Path) -> None:
    database = tmp_path / "native.sqlite"
    run_runtime("migrate", "--database", str(database), "--migrations", str(MIGRATIONS))

    completed = run_runtime(
        "native-smoke",
        "--python",
        sys.executable,
        "--module-root",
        str(REPOSITORY_ROOT / "apps/native-host/src"),
        "--database",
        str(database),
        "--migrations",
        str(MIGRATIONS),
    )

    assert json.loads(completed.stdout)["ok"] is True


def test_operational_scripts_support_safe_dry_runs(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "MUNSHI_RUNTIME_ROOT": str(tmp_path / "runtime"),
        "MUNSHI_PYTHON": sys.executable,
    }
    install = subprocess.run(  # noqa: S603 - fixed repository script.
        [str(REPOSITORY_ROOT / "scripts/install.sh"), "--dry-run"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    rollback = subprocess.run(  # noqa: S603 - fixed repository script.
        [str(REPOSITORY_ROOT / "scripts/rollback.sh"), "HEAD", "--dry-run"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Would install" in install.stdout
    assert "Application history" not in rollback.stdout
    assert "preserve the database" in rollback.stdout


def test_updater_uses_installed_runtime_verification() -> None:
    update_script = (REPOSITORY_ROOT / "scripts/update.sh").read_text(encoding="utf-8")
    verify_script = (REPOSITORY_ROOT / "scripts/verify.sh").read_text(encoding="utf-8")

    assert 'verify.sh" --runtime-only' in update_script
    assert "runtime_only=false" in verify_script
    assert '"${runtime_only}" == false && "${skip_tests}" == false' in verify_script


def test_release_packaging_creates_required_verified_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "release"
    fixture_repository = tmp_path / "repository"
    extension_dist = fixture_repository / "apps/extension/dist"
    extension_dist.mkdir(parents=True)
    (extension_dist / "manifest.json").write_text(
        '{"manifest_version": 3, "name": "MUNSHI Apply"}\n', encoding="utf-8"
    )
    (extension_dist / "service-worker.js").write_text("export {};\n", encoding="utf-8")
    (extension_dist / "service-worker.js.map").write_text("{}\n", encoding="utf-8")
    mobile_extension_dist = fixture_repository / "apps/extension/dist-mobile"
    mobile_extension_dist.mkdir(parents=True)
    (mobile_extension_dist / "manifest.json").write_text(
        '{"manifest_version": 3, "name": "MUNSHI Apply Mobile"}\n',
        encoding="utf-8",
    )
    (mobile_extension_dist / "service-worker.js").write_text("export {};\n", encoding="utf-8")
    (mobile_extension_dist / "service-worker.js.map").write_text("{}\n", encoding="utf-8")
    fixture_migrations = fixture_repository / "migrations"
    shutil.copytree(MIGRATIONS, fixture_migrations)
    subprocess.run(  # noqa: S603 - fixed interpreter and repository script.
        [
            sys.executable,
            str(RELEASE_OPS),
            "--version",
            "v0.2.0",
            "--output",
            str(output),
            "--repository",
            str(fixture_repository),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    required = {
        "munshi-apply-edge-v0.2.0.zip",
        "munshi-apply-edge-mobile-v0.2.0.zip",
        "munshi-apply-native-macos-v0.2.0.tar.gz",
        "release-manifest.json",
        "migration-manifest.json",
        "checksums.sha256",
    }
    assert {path.name for path in output.iterdir()} == required
    for archive_name in (
        "munshi-apply-edge-v0.2.0.zip",
        "munshi-apply-edge-mobile-v0.2.0.zip",
    ):
        with zipfile.ZipFile(output / archive_name) as archive:
            assert not any(name.endswith(".map") for name in archive.namelist())
    for line in (output / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        expected, filename = line.split("  ", 1)
        assert hashlib.sha256((output / filename).read_bytes()).hexdigest() == expected
