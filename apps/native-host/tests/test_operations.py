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
        "007_ai_draft_reviews.sql",
        "008_progressive_memory.sql",
        "009_account_orchestration.sql",
        "010_job_signal_intelligence.sql",
        "011_job_signal_identity_and_analytics.sql",
        "012_resolution_tasks.sql",
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

    completed = subprocess.run(  # noqa: S603 - fixed repository script.
        [
            sys.executable,
            str(RELEASE_OPS),
            "package",
            "--repository-root",
            str(fixture_repository),
            "--output",
            str(output),
            "--version",
            "0.1.0-test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    manifest = json.loads((output / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.1.0-test"
    assert "munshi-apply-extension" in manifest["artifacts"]
    assert "munshi-apply-extension-mobile" in manifest["artifacts"]
    assert "munshi-apply-source" in manifest["artifacts"]
    assert "munshi-apply-runtime-migrations" in manifest["artifacts"]
    assert "Created release package" in completed.stdout


def test_release_manifest_hashes_match_artifact_bytes(tmp_path: Path) -> None:
    output = tmp_path / "release"
    fixture_repository = tmp_path / "repository"
    extension_dist = fixture_repository / "apps/extension/dist"
    extension_dist.mkdir(parents=True)
    (extension_dist / "manifest.json").write_text(
        '{"manifest_version": 3, "name": "MUNSHI Apply"}\n', encoding="utf-8"
    )
    (extension_dist / "service-worker.js").write_text("export {};\n", encoding="utf-8")
    mobile_extension_dist = fixture_repository / "apps/extension/dist-mobile"
    mobile_extension_dist.mkdir(parents=True)
    (mobile_extension_dist / "manifest.json").write_text(
        '{"manifest_version": 3, "name": "MUNSHI Apply Mobile"}\n',
        encoding="utf-8",
    )
    fixture_migrations = fixture_repository / "migrations"
    shutil.copytree(MIGRATIONS, fixture_migrations)

    subprocess.run(  # noqa: S603 - fixed repository script.
        [
            sys.executable,
            str(RELEASE_OPS),
            "package",
            "--repository-root",
            str(fixture_repository),
            "--output",
            str(output),
            "--version",
            "0.1.0-test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    manifest = json.loads((output / "release-manifest.json").read_text(encoding="utf-8"))
    for artifact_name, expected_hash in manifest["sha256"].items():
        artifact = output / manifest["artifacts"][artifact_name]
        actual_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert actual_hash == expected_hash


def test_release_source_archive_excludes_runtime_and_secret_material(tmp_path: Path) -> None:
    output = tmp_path / "release"
    fixture_repository = tmp_path / "repository"
    fixture_repository.mkdir()
    (fixture_repository / "README.md").write_text("hello\n", encoding="utf-8")
    runtime = fixture_repository / "private-runtime"
    runtime.mkdir()
    (runtime / "secret.txt").write_text("do-not-package\n", encoding="utf-8")
    git_directory = fixture_repository / ".git"
    git_directory.mkdir()
    (git_directory / "config").write_text("private\n", encoding="utf-8")

    subprocess.run(  # noqa: S603 - fixed repository script.
        [
            sys.executable,
            str(RELEASE_OPS),
            "package-source",
            "--repository-root",
            str(fixture_repository),
            "--output",
            str(output),
            "--version",
            "0.1.0-test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    archive = output / "munshi-apply-source-0.1.0-test.zip"
    with zipfile.ZipFile(archive) as packaged:
        members = set(packaged.namelist())
    assert "README.md" in members
    assert not any(member.startswith("private-runtime/") for member in members)
    assert not any(member.startswith(".git/") for member in members)
