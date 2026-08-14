#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_files(root: Path, paths: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for relative in paths:
        candidate = root / relative
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(
                path
                for path in candidate.rglob("*")
                if path.is_file()
                and not any(
                    part in {"__pycache__", ".pytest_cache", ".ruff_cache"}
                    for part in path.parts
                )
            )
    return sorted(set(files))


def package(version: str, root: Path, output: Path) -> list[Path]:
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", version):
        raise ValueError("Release version must look like v1.2.3 or 1.2.3")
    tag_version = version if version.startswith("v") else f"v{version}"
    extension_root = root / "apps/extension/dist"
    if not (extension_root / "manifest.json").is_file():
        raise FileNotFoundError("Build the extension before packaging a release")
    output.mkdir(parents=True, exist_ok=True)
    edge_archive = output / f"munshi-apply-edge-{tag_version}.zip"
    native_archive = output / f"munshi-apply-native-macos-{tag_version}.tar.gz"
    for target in (edge_archive, native_archive):
        if target.exists():
            raise FileExistsError(f"Release artifact already exists: {target}")

    with zipfile.ZipFile(
        edge_archive, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for path in sorted(extension_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(extension_root))

    native_files = repository_files(
        root,
        (
            "apps/native-host/pyproject.toml",
            "apps/native-host/src",
            "migrations",
            "scripts/install.sh",
            "scripts/install-native-host.sh",
            "scripts/verify.sh",
            "scripts/backup.sh",
            "scripts/update.sh",
            "scripts/rollback.sh",
            "scripts/runtime-ops.py",
            "scripts/lib/common.sh",
        ),
    )
    with tarfile.open(native_archive, "w:gz") as archive:
        for path in native_files:
            archive.add(path, arcname=path.relative_to(root))

    migration_manifest = output / "migration-manifest.json"
    migration_records = [
        {"id": path.name, "sha256": sha256_file(path)}
        for path in sorted((root / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
    ]
    migration_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "release": tag_version,
                "migrations": migration_records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        commit = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        commit = "unknown"
    release_manifest = output / "release-manifest.json"
    release_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "version": tag_version,
                "commit": commit,
                "created_at": datetime.now(UTC).isoformat(),
                "artifacts": [
                    edge_archive.name,
                    native_archive.name,
                    migration_manifest.name,
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    checksummed = [edge_archive, native_archive, migration_manifest, release_manifest]
    checksums = output / "checksums.sha256"
    checksums.write_text(
        "\n".join(f"{sha256_file(path)}  {path.name}" for path in checksummed) + "\n",
        encoding="utf-8",
    )
    return [*checksummed, checksums]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create reproducible MUNSHI Apply release assets"
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args()
    for artifact in package(
        args.version, args.repository.resolve(), args.output.resolve()
    ):
        print(artifact)


if __name__ == "__main__":
    main()
