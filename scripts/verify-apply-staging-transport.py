#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, tokens: tuple[str, ...], label: str) -> None:
    for token in tokens:
        assert token in text, f"{label} missing required transport token: {token}"


def forbid(text: str, tokens: tuple[str, ...], label: str) -> None:
    for token in tokens:
        assert token not in text, f"{label} contains forbidden transport token: {token}"


def main() -> None:
    workflow = read(".github/workflows/apply-netcup-staging-deploy.yml")
    gateway = read("deploy/netcup/github_apply_staging_deploy_gateway.sh")
    deploy = read("deploy/netcup/deploy_apply_staging_release.sh")
    verify = read("deploy/netcup/verify_apply_staging_runtime_contract.sh")
    installer = read("deploy/netcup/install_apply_staging_deploy_transport.sh")

    require(
        workflow,
        (
            "workflow_dispatch:",
            "Exact 40-character Git SHA",
            "git merge-base --is-ancestor",
            "git bundle create",
            "git bundle verify",
            "/opt/munshi/bin/deploy-apply-staging-release --commit $DEPLOY_SHA --branch $DEPLOY_BRANCH",
            "NETCUP_APPLY_STAGING_SSH_PRIVATE_KEY",
            "NETCUP_APPLY_STAGING_DEPLOY_USER",
            "StrictHostKeyChecking=yes",
            "environment: staging",
            "group: munshi-apply-netcup-staging",
            "RESULT=APPLY_STAGING_DEPLOYMENT_PASS",
        ),
        "Apply staging workflow",
    )
    forbid(
        workflow,
        (
            "deploy-production-release",
            "/opt/munshi/bin/deploy-staging-release",
            "NETCUP_SSH_PRIVATE_KEY",
            "schedule:",
            "branches: [main]",
        ),
        "Apply staging workflow",
    )

    require(
        gateway,
        (
            "SSH_ORIGINAL_COMMAND",
            "([0-9a-f]{40})",
            'APPLY_STAGING_DEPLOY="/opt/munshi/bin/deploy-apply-staging-release"',
            'exec "$APPLY_STAGING_DEPLOY" --commit "$commit" --branch "$branch"',
            "request rejected by MUNSHI Apply staging deployment gateway",
        ),
        "Apply staging forced-command gateway",
    )
    forbid(
        gateway,
        (
            "deploy-production-release",
            "/opt/munshi/bin/deploy-staging-release",
            "eval ",
            "bash -c",
            "sh -c",
        ),
        "Apply staging forced-command gateway",
    )

    require(
        deploy,
        (
            'PROJECT="${MUNSHI_APPLY_STAGING_PROJECT:-munshi-apply-staging-v1}"',
            'STAGING_ROOT="${MUNSHI_APPLY_STAGING_ROOT:-/home/munshi/munshi-apply-staging-v1}"',
            'HUNTER_NETWORK="munshi-netcup-staging_application"',
            'flock -n 9',
            'timeout 120s cat > "$bundle_file"',
            'git bundle verify "$bundle_file"',
            'git fetch --no-tags "$bundle_file" "+$bundle_ref:$deploy_ref"',
            'git merge-base --is-ancestor "$commit" "$deploy_ref"',
            'service in prepare-worker submit-worker',
            'source.backup(dest)',
            'PRAGMA quick_check',
            'rollback_tag="munshi-apply-staging:rollback-$stamp"',
            '"${compose[@]}" build apply',
            '"${compose[@]}" up -d --no-deps --force-recreate apply',
            '"$VERIFY" --expected-sha "$commit"',
            'hunter_snapshot_before="$(snapshot_hunter)"',
            '"production_deployment_performed": False',
            '"hunter_containers_recreated": False',
            '"final_submit_enabled": False',
            'RESULT=APPLY_STAGING_DEPLOYMENT_PASS',
        ),
        "Apply staging deploy wrapper",
    )
    forbid(
        deploy,
        (
            "git fetch --prune origin",
            'git fetch origin "$branch"',
            "docker compose down",
            "down -v",
            "docker volume rm",
            "MUNSHI_FINAL_SUBMIT_ENABLED=true",
            "MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=true",
        ),
        "Apply staging deploy wrapper",
    )

    require(
        verify,
        (
            "APPLY_STAGING_COMPOSE_SAFETY=PASS",
            "APPLY_STAGING_SUBMIT_WORKER_ACTIVE=NO",
            "hosted-submit-proof",
            "MUNSHI_FINAL_SUBMIT_ENABLED",
            "MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED",
            "127.0.0.1:19000",
            "org.opencontainers.image.revision",
            "munshi-netcup-staging_application",
            "APPLY_STAGING_DATABASE_HEALTH=PASS",
            "RESULT=APPLY_STAGING_RUNTIME_CONTRACT_PASS",
        ),
        "Apply staging runtime verifier",
    )

    require(
        installer,
        (
            "--public-key-file",
            "--source-root",
            "--source-sha",
            '[[ "$(git -C "$SOURCE_ROOT" rev-parse HEAD)" == "$SOURCE_SHA" ]]',
            'KEY_COMMENT="munshi-github-actions-apply-staging-deploy"',
            'restrict,command="/opt/munshi/bin/github-apply-staging-deploy-gateway"',
            "grep -v \" $KEY_COMMENT$\"",
            "ssh-keygen -l",
            "runuser -u \"$TARGET_USER\" -- docker info",
            "PRIVATE_KEY_INSTALLED_ON_SERVER=NO",
            "HUNTER_DEPLOY_KEY_CHANGED=NO",
            "PRODUCTION_DEPLOYMENT_PERFORMED=NO",
            "STAGING_DEPLOYMENT_PERFORMED=NO",
            "RESULT=APPLY_STAGING_TRANSPORT_INSTALLED",
        ),
        "Apply staging transport installer",
    )
    forbid(
        installer,
        (
            "deploy-production-release",
            "/opt/munshi/bin/deploy-staging-release",
            "PRIVATE_KEY_INSTALLED_ON_SERVER=YES",
            "docker compose up",
            "docker compose down",
        ),
        "Apply staging transport installer",
    )

    print("APPLY_STAGING_TRANSPORT_STATIC_GUARD=PASS")


if __name__ == "__main__":
    main()
