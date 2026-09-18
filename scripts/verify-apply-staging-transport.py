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
    compose = read("deploy/staging/compose.yaml")

    require(
        workflow,
        (
            "workflow_dispatch:",
            "deploy_target:",
            "needs.validate-and-test.outputs.deploy_target",
            "inputs.deploy_target",
            "MUNSHI_DEPLOY_SSH_PRIVATE_KEY",
            "MUNSHI_DEPLOY_KNOWN_HOSTS",
            "MUNSHI_DEPLOY_HOST",
            "MUNSHI_DEPLOY_USER",
            "--target $DEPLOY_TARGET --commit $DEPLOY_SHA --branch $DEPLOY_BRANCH",
            "DEPLOYED_TARGET=$DEPLOY_TARGET",
            "git merge-base --is-ancestor",
            "git bundle create",
            "git bundle verify",
        ),
        "Apply target workflow",
    )
    forbid(
        workflow,
        (
            "NETCUP_APPLY_STAGING_SSH_PRIVATE_KEY",
            "NETCUP_APPLY_STAGING_DEPLOY_USER",
            "environment: staging",
            "group: munshi-apply-netcup-staging",
            "feat/apply-staging-transport-bootstrap",
            "munshi-apply-staging.bundle",
            "schedule:",
            "branches: [main]",
        ),
        "Apply target workflow",
    )

    require(
        gateway,
        (
            "SSH_ORIGINAL_COMMAND",
            "--target\\ ",
            "([0-9a-f]{40})",
            'APPLY_STAGING_DEPLOY="/opt/munshi/bin/deploy-apply-staging-release"',
            'exec "$APPLY_STAGING_DEPLOY" --target "$target" --commit "$commit" --branch "$branch"',
            "request rejected by MUNSHI Apply staging deployment gateway",
        ),
        "Apply forced-command gateway",
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
        "Apply forced-command gateway",
    )

    require(
        deploy,
        (
            "MUNSHI_APPLY_DEPLOY_TARGET_CONFIG_DIR",
            '--target) target="${2:-}"',
            'TARGET_CONFIG="$TARGET_CONFIG_DIR/apply-$target.env"',
            "MUNSHI_APPLY_DEPLOY_ROOT",
            "MUNSHI_APPLY_COMPOSE_PROJECT",
            "MUNSHI_APPLY_BIND_HOST",
            "MUNSHI_APPLY_PUBLISHED_PORT",
            "MUNSHI_HUNTER_NETWORK_NAME",
            "MUNSHI_APPLY_IMAGE_REPOSITORY",
            "MUNSHI_ENVIRONMENT",
            "MUNSHI_APPLY_RUNTIME_ENV_FILE",
            "MUNSHI_APPLY_PROTECTED_COMPOSE_PROJECTS",
            "MUNSHI_APPLY_PROTECTED_CONTAINER_NAMES",
            'flock -n 9',
            'timeout 120s cat > "$bundle_file"',
            'git bundle verify "$bundle_file"',
            'git merge-base --is-ancestor "$commit" "$deploy_ref"',
            'service in prepare-worker submit-worker',
            'source.backup(dest)',
            'PRAGMA quick_check',
            'rollback_tag="$IMAGE_REPOSITORY:rollback-$stamp"',
            '"$VERIFY" --target "$target" --expected-sha "$commit"',
            'hunter_snapshot_before="$(snapshot_hunter)"',
            '"environment": environment',
            '"deployment_target": target',
            '"production_deployment_performed": False',
            '"hunter_containers_recreated": False',
            '"final_submit_enabled": False',
            'echo "DEPLOYED_TARGET=$target"',
        ),
        "Apply target deploy wrapper",
    )

    require(
        verify,
        (
            "MUNSHI_APPLY_DEPLOY_TARGET_CONFIG_DIR",
            '--target) target="${2:-}"',
            'TARGET_CONFIG="$TARGET_CONFIG_DIR/apply-$target.env"',
            "MUNSHI_APPLY_RUNTIME_ENV_FILE",
            '[[ -r "$STAGING_ENV" ]]',
            'repo_head="$(git -C "$STAGING_REPO" rev-parse --verify HEAD',
            '[[ "$repo_head" == "$EXPECTED_SHA" ]]',
            "APPLY_STAGING_SOURCE_PROVENANCE=PASS",
            "APPLY_STAGING_COMPOSE_SAFETY=PASS",
            "APPLY_STAGING_SUBMIT_WORKER_ACTIVE=NO",
            "hosted-submit-proof",
            "MUNSHI_FINAL_SUBMIT_ENABLED",
            "MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED",
            '[[ "$port_binding" == "$BIND_HOST:$PUBLISHED_PORT" ]]',
            'grep -Fq "$HUNTER_NETWORK"',
            "org.opencontainers.image.revision",
            "APPLY_STAGING_DATABASE_HEALTH=PASS",
        ),
        "Apply target runtime verifier",
    )

    require(
        installer,
        (
            "--public-key-file",
            "--target",
            "--deploy-root",
            "--runtime-env-file",
            "--compose-project",
            "--bind-host",
            "--published-port",
            "--hunter-network",
            "--image-repository",
            "--environment",
            "--protected-compose-projects",
            "--protected-containers",
            "--source-root",
            "--source-sha",
            'TARGET_CONFIG="$TARGET_CONFIG_DIR/apply-$TARGET.env"',
            "MUNSHI_APPLY_RUNTIME_ENV_FILE=$RUNTIME_ENV_FILE",
            'restrict,command="/opt/munshi/bin/github-apply-staging-deploy-gateway"',
            "PRIVATE_KEY_INSTALLED_ON_SERVER=NO",
            "HUNTER_DEPLOY_KEY_CHANGED=NO",
            "PRODUCTION_DEPLOYMENT_PERFORMED=NO",
            "STAGING_DEPLOYMENT_PERFORMED=NO",
        ),
        "Apply target transport installer",
    )

    require(
        compose,
        (
            "$" + "{MUNSHI_APPLY_IMAGE_REPOSITORY:?MUNSHI_APPLY_IMAGE_REPOSITORY is required}",
            "$" + "{MUNSHI_APPLY_BIND_HOST:?MUNSHI_APPLY_BIND_HOST is required}",
            "$" + "{MUNSHI_APPLY_PUBLISHED_PORT:?MUNSHI_APPLY_PUBLISHED_PORT is required}",
            "$" + "{MUNSHI_HUNTER_NETWORK_NAME:?MUNSHI_HUNTER_NETWORK_NAME is required}",
            "$" + "{MUNSHI_ENVIRONMENT:?MUNSHI_ENVIRONMENT is required}",
        ),
        "Apply target compose",
    )

    forbidden_target_literals = (
        "munshi-apply-staging-v1",
        "munshi-apply-staging_apply_data",
        "munshi-netcup-staging_application",
        "127.0.0.1:19000",
        "munshi-netcup-shadow",
        "munshi-staging-edge-caddy",
    )
    for label, text in (
        ("workflow", workflow),
        ("gateway", gateway),
        ("deploy", deploy),
        ("verify", verify),
        ("installer", installer),
        ("compose", compose),
    ):
        forbid(text, forbidden_target_literals, label)

    for label, text in (("deploy", deploy), ("installer", installer)):
        forbid(
            text,
            (
                "docker compose down",
                "down -v",
                "docker volume rm",
                "MUNSHI_FINAL_SUBMIT_ENABLED=true",
                "MUNSHI_APPLY_PRODUCTION_SUBMIT_AUTHORITY_ENABLED=true",
            ),
            label,
        )

    print("APPLY_TARGET_TRANSPORT_STATIC_GUARD=PASS")


if __name__ == "__main__":
    main()
