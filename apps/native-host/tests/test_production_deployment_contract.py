# ruff: noqa: I001
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BASH = "/bin/bash"


def test_staging_compose_wires_complete_loop_control_plane_fail_closed() -> None:
    source = (ROOT / "deploy/staging/compose.yaml").read_text(encoding="utf-8")
    assert (
        'MUNSHI_APPLY_COMMAND_SECRET: '
        '"${MUNSHI_APPLY_COMMAND_SECRET:?MUNSHI_APPLY_COMMAND_SECRET is required}"'
        in source
    )
    assert (
        'MUNSHI_APPLY_PLAN_SUPERSESSION_ENABLED: '
        '"${MUNSHI_APPLY_PLAN_SUPERSESSION_ENABLED:-false}"'
        in source
    )
    # Immutable staging flags: no runtime env may grant submit authority.
    required_occurrences = {
        "MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED": 2,
        "MUNSHI_FINAL_REVIEW_ENABLED": 3,
        "MUNSHI_FINAL_SUBMIT_ENABLED": 3,
    }
    for name, expected in required_occurrences.items():
        assert source.count(name + ': "false"') == expected
    assert source.count('MUNSHI_APPLY_HOSTED_SUBMIT_WORKER_ENABLED: "false"') == 1
    assert source.count('MUNSHI_APPLY_BROWSER_HEADLESS: "true"') == 2
    assert source.count(
        "MUNSHI_APPLY_BROWSER_HEALTH_PATH: /data/browser-runtime-health.json"
    ) == 2
    for name in (
        "MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED",
        "MUNSHI_FINAL_SUBMIT_ENABLED",
        "MUNSHI_FINAL_REVIEW_ENABLED",
        "MUNSHI_APPLY_HOSTED_SUBMIT_WORKER_ENABLED",
    ):
        for line in source.splitlines():
            if line.strip().startswith(name + ":"):
                assert line.strip() == name + ': "false"'


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
    verify = (
        ROOT / "deploy/netcup/verify_apply_production_runtime_contract.sh"
    ).read_text(encoding="utf-8")
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
    assert "APPLY_PRODUCTION_BROWSER_RUNTIME_HEALTH=PASS" in verify
    assert 'payload.get("executable") != "/usr/bin/chromium"' in verify
    assert 'payload.get("headless") is not True' in verify
    assert "ROLLBACK APPLY FULL-SUBMIT ACTIVATION" in activate
    assert "safe.directory=$REPO" in verify
    assert "safe.directory=$REPO" in activate
    assert "APPLY_PRODUCTION_FINAL_SUBMIT=ENABLED" in activate


def test_hosted_submit_worker_delivers_verified_production_receipt() -> None:
    source = (
        ROOT / "apps/native-host/src/munshi_apply_native/hosted_submit_worker.py"
    ).read_text(encoding="utf-8")
    assert "ProductionReceiptClient" in source
    assert "ProductionReceiptClient.from_environment()" in source
    assert "production_receipt_client=" in source


def test_production_private_http_is_exact_and_default_denied() -> None:
    source = (
        ROOT / "apps/native-host/src/munshi_apply_native/internal_http_policy.py"
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
        subprocess.run(  # noqa: S603 - fixed local shell syntax-check command
            [BASH, "-n", str(ROOT / relative)],
            check=True,
        )


def test_staging_verifier_proves_optional_netcup_browser_worker() -> None:
    source = (
        ROOT / "deploy/netcup/verify_apply_staging_runtime_contract.sh"
    ).read_text(encoding="utf-8")
    assert "--require-prepare" in source
    assert "APPLY_STAGING_PREPARE_WORKER_ACTIVE=YES" in source
    assert "APPLY_STAGING_BROWSER_RUNTIME_HEALTH=PASS" in source
    assert 'payload.get("executable") != "/usr/bin/chromium"' in source
    assert 'payload.get("headless") is not True' in source


def test_docker_python_heredocs_keep_stdin_open() -> None:
    # Without -i Docker gives Python EOF and returns success without executing
    # the health check, queue gate, backup, or restore supplied on stdin.
    for relative in (
        "deploy/netcup/activate_apply_production_submit.sh",
        "deploy/netcup/deploy_apply_production_release.sh",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        logical = source.replace("\\\n", " ")
        commands = re.findall(r"docker (?:exec|run) [^\n]*<<[^\n]*", logical)
        assert commands, relative
        for command in commands:
            args = shlex.split(command.split("<<", 1)[0])
            assert "-i" in args or "--interactive" in args, (relative, command)


def test_production_helpers_leave_inherited_directory_before_compose(tmp_path) -> None:
    root = tmp_path / "production"
    repo = root / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "deploy/production").mkdir(parents=True)
    (repo / "deploy/production/compose.yaml").write_text("services: {}\n")
    (root / "runtime").mkdir()
    (root / "runtime/production.env").write_text("")
    # /tmp may be mounted noexec in the deployment's read-only test container.
    # This fixture only checks that the helper validates an executable verifier;
    # it never invokes the verifier, so use the existing harmless system binary.
    verifier = Path(shutil.which("true") or "/usr/bin/true")
    inherited = tmp_path / "unrelated-ssh-directory"
    inherited.mkdir()
    env = dict(
        os.environ,
        MUNSHI_APPLY_PRODUCTION_ROOT=str(root),
        MUNSHI_APPLY_PRODUCTION_VERIFY=str(verifier),
    )
    for name in (
        "deploy_apply_production_release.sh",
        "verify_apply_production_runtime_contract.sh",
        "activate_apply_production_submit.sh",
    ):
        source = (ROOT / "deploy/netcup" / name).read_text()
        anchor = 'cd -- "$REPO"'
        assert source.count(anchor) == 1
        assert source.index(anchor) < source.index('source "$ENV_FILE"')
        assert source.index(anchor) < source.index("docker ")
        # Execute the real argument/validation prefix from a foreign cwd.
        # No Docker, production state, or network is involved in this fixture.
        prefix = (
            source.split(anchor, 1)[0]
            + anchor
            + '\nprintf "CWD=%s\\n" "$PWD"\n'
        )
        args = (
            ["--commit", "a" * 40, "--branch", "release/fixture"]
            if name.startswith("deploy_")
            else []
        )
        result = subprocess.run(  # noqa: S603 - fixed local test harness command
            [BASH, "-s", "--", *args],
            input=prefix,
            text=True,
            capture_output=True,
            cwd=inherited,
            env=env,
            check=True,
        )
        assert f"CWD={repo}\n" in result.stdout


def test_deploy_time_regression_uses_disposable_writable_data() -> None:
    deploy = (ROOT / "deploy/netcup/deploy_apply_production_release.sh").read_text()
    command = deploy.split('echo "=== RUN EXACT-IMAGE APPLY', 1)[1].split(
        'echo "APPLY_PRODUCTION_EXACT_IMAGE_TESTS=PASS"',
        1,
    )[0]
    assert "--network none" in command
    assert "--read-only" in command
    assert (
        "--tmpfs /data:rw,nosuid,nodev,size=256m,uid=10001,gid=10001,mode=0700"
        in command
    )
    assert "--mount" not in command and "--volume" not in command
