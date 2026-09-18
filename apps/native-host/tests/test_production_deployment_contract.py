from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]


def test_production_compose_has_separate_api_prepare_submit_authority() -> None:
    source = (ROOT / "deploy/production/compose.yaml").read_text(encoding="utf-8")
    assert "prepare-worker:" in source
    assert "submit-worker:" in source
    assert 'profiles: ["hosted-prepare"]' in source
    assert 'profiles: ["hosted-submit"]' in source
    assert 'MUNSHI_FINAL_SUBMIT_ENABLED: "false"' in source
    assert 'MUNSHI_FINAL_SUBMIT_ENABLED: "true"' in source
    assert "MUNSHI_APPLY_COMMAND_SECRET" in source
    assert "MUNSHI_PRODUCTION_SUBMIT_AUTH_HMAC_SECRET" in source
    assert "MUNSHI_PRODUCTION_RECEIPT_HMAC_SECRET" in source
    assert "MUNSHI_PRODUCTION_INTERNAL_BRIDGE_ENABLED" in source
    assert "MUNSHI_HUNTER_INTERNAL_HTTP_BASE_URL" in source


def test_production_transport_is_rollback_guarded_and_staging_is_protected() -> None:
    deploy = (ROOT / "deploy/netcup/deploy_apply_production_release.sh").read_text(
        encoding="utf-8"
    )
    verify = (ROOT / "deploy/netcup/verify_apply_production_runtime_contract.sh").read_text(
        encoding="utf-8"
    )
    activate = (ROOT / "deploy/netcup/activate_apply_production_submit.sh").read_text(
        encoding="utf-8"
    )
    assert "APPLY_PRODUCTION_DB_BACKUP_QUICK_CHECK=PASS" in deploy
    assert "AUTOMATIC APPLY PRODUCTION ROLLBACK" in deploy
    assert "active SUBMITTING session" in deploy
    assert "munshi-apply-staging-apply-1" in deploy
    assert "munshi-netcup-shadow-n8n-1" in deploy
    assert "munshi-netcup-shadow-ollama-1" in deploy
    assert "--expect-submit" in verify
    assert "APPLY_PRODUCTION_SUBMIT_WORKER_ACTIVE=NO" in verify
    assert "APPLY_PRODUCTION_SUBMIT_WORKER_ACTIVE=YES" in verify
    assert "ROLLBACK APPLY FULL-SUBMIT ACTIVATION" in activate
    assert 'safe.directory=$REPO' in verify
    assert 'safe.directory=$REPO' in activate
    assert "APPLY_PRODUCTION_FINAL_SUBMIT=ENABLED" in activate


def test_hosted_submit_worker_delivers_verified_production_receipt() -> None:
    source = (
        ROOT
        / "apps/native-host/src/munshi_apply_native/hosted_submit_worker.py"
    ).read_text(encoding="utf-8")
    assert "ProductionReceiptClient" in source
    assert "ProductionReceiptClient.from_environment()" in source
    assert "production_receipt_client=" in source


def test_production_private_http_is_exact_and_default_denied() -> None:
    source = (
        ROOT
        / "apps/native-host/src/munshi_apply_native/internal_http_policy.py"
    ).read_text(encoding="utf-8")
    assert "MUNSHI_PRODUCTION_INTERNAL_BRIDGE_ENABLED" in source
    assert '"." not in host' in source
    assert "normalized != allowed" in source

def test_production_shell_scripts_parse() -> None:
    for relative in (
        "deploy/netcup/deploy_apply_production_release.sh",
        "deploy/netcup/verify_apply_production_runtime_contract.sh",
        "deploy/netcup/activate_apply_production_submit.sh",
    ):
        subprocess.run(["bash", "-n", str(ROOT / relative)], check=True)

def test_docker_python_heredocs_keep_stdin_open() -> None:
    # Without -i Docker gives Python EOF and returns success without executing
    # the health check, queue gate, backup, or restore supplied on stdin.
    import re
    import shlex
    for relative in ("deploy/netcup/activate_apply_production_submit.sh", "deploy/netcup/deploy_apply_production_release.sh"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        logical = source.replace("\\\n", " ")
        commands = re.findall(r"docker (?:exec|run) [^\n]*<<[^\n]*", logical)
        assert commands, relative
        for command in commands:
            args = shlex.split(command.split("<<", 1)[0])
            assert "-i" in args or "--interactive" in args, (relative, command)


def test_production_helpers_leave_inherited_directory_before_compose(tmp_path) -> None:
    import os

    root = tmp_path / "production"
    repo = root / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "deploy/production").mkdir(parents=True)
    (repo / "deploy/production/compose.yaml").write_text("services: {}\n")
    (root / "runtime").mkdir()
    (root / "runtime/production.env").write_text("")
    verifier = root / "verifier"
    verifier.write_text("#!/bin/sh\nexit 0\n")
    verifier.chmod(0o700)
    inherited = tmp_path / "unrelated-ssh-directory"
    inherited.mkdir()
    env = dict(os.environ, MUNSHI_APPLY_PRODUCTION_ROOT=str(root),
               MUNSHI_APPLY_PRODUCTION_VERIFY=str(verifier))
    for name in ("deploy_apply_production_release.sh",
                 "verify_apply_production_runtime_contract.sh",
                 "activate_apply_production_submit.sh"):
        source = (ROOT / "deploy/netcup" / name).read_text()
        anchor = 'cd -- "$REPO"'
        assert source.count(anchor) == 1
        assert source.index(anchor) < source.index('source "$ENV_FILE"')
        assert source.index(anchor) < source.index("docker ")
        # Execute the real argument/validation prefix from a foreign cwd.
        # No Docker, production state, or network is involved in this fixture.
        prefix = source.split(anchor, 1)[0] + anchor + '\nprintf "CWD=%s\\n" "$PWD"\n'
        args = ["--commit", "a" * 40, "--branch", "release/fixture"] if name.startswith("deploy_") else []
        result = subprocess.run(["bash", "-s", "--", *args], input=prefix,
                                text=True, capture_output=True, cwd=inherited,
                                env=env, check=True)
        assert f"CWD={repo}\n" in result.stdout
