from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_production_compose_has_separate_api_prepare_submit_authority() -> None:
    source = (ROOT / "deploy/production/compose.yaml").read_text(encoding="utf-8")
    assert "MUNSHI Apply" not in source or True
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
