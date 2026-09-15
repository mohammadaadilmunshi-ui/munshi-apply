from __future__ import annotations

import hashlib

from conftest import build_authority_envelope, sign_authority_envelope
from test_complete_application_loop import loop  # noqa: F401

from munshi_apply_native.background_prepare_queue import DurablePreparationQueue
from munshi_apply_native.hosted_submit_worker import HostedSubmitRunner
from munshi_apply_native.submit_authority_inbox_v1 import expected_claim_digest


class _HunterAuthorityClient:
    def __init__(self, envelope):
        self.envelope = dict(envelope)
        self.read_calls = 0
        self.claim_calls = 0

    def read(self, binding):
        self.read_calls += 1
        for key in (
            "tenant_id",
            "user_id",
            "application_id",
            "plan_id",
            "session_id",
            "plan_digest",
        ):
            assert str(binding[key]) == str(self.envelope[key])
        return dict(self.envelope)

    def claim(self, envelope, *, claimant_id):
        self.claim_calls += 1
        assert envelope["authorization_id"] == self.envelope["authorization_id"]
        return {
            "status": "CLAIMED",
            "submission_authority": True,
            "authorization_id": envelope["authorization_id"],
            "authority_digest": envelope["authority_digest"],
            "generation": int(envelope["generation"]),
            "claim_digest": expected_claim_digest(
                authorization_id=envelope["authorization_id"],
                authority_digest=envelope["authority_digest"],
                claimant_id=claimant_id,
                generation=int(envelope["generation"]),
            ),
        }


def test_hunter_single_approval_reaches_guarded_submit_without_second_apply_approval(loop):
    service, database, browser = loop
    session = service.start_session(plan_id="application-plan-1")
    queue = DurablePreparationQueue(database)
    prepare_job = queue.enqueue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
    )

    pending = service.prepare_session(session_id=session.session_id, adapter=browser)
    task = service.resolutions.list(application_id=session.application_id)[0]
    service.resolve_task(task_id=task.task_id, value="https://example.test/portfolio")
    prepared = service.prepare_session(session_id=session.session_id, adapter=browser)
    assert pending.state == "NEEDS_INPUT"
    assert prepared.state == "READY_FOR_REVIEW"
    review = service.build_review(session_id=session.session_id)

    with database.connect() as connection:
        session_row = connection.execute(
            "SELECT * FROM complete_application_sessions WHERE session_id=?",
            (session.session_id,),
        ).fetchone()
        connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='READY_FOR_REVIEW',finished_at=CURRENT_TIMESTAMP,
                   lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL
               WHERE job_id=?""",
            (prepare_job["job_id"],),
        )
    plan_record = service._plan(session.plan_id)  # noqa: SLF001

    # Hunter has its own frozen review/approval ids and digests. The authority
    # still binds to the exact Apply plan/session/checkpoint/form/resume that
    # produced the customer-visible review.
    envelope = build_authority_envelope(
        authorization_id="hunter-auth-single-click-1",
        application_id=session.application_id,
        plan_id=session.plan_id,
        session_id=session.session_id,
        review_id="hunter-review-single-click-1",
        approval_id="hunter-approval-single-click-1",
        plan_digest=plan_record["plan_digest"],
        review_digest=hashlib.sha256(b"hunter-review").hexdigest(),
        approval_digest=hashlib.sha256(b"hunter-approval").hexdigest(),
        prepared_package_digest=hashlib.sha256(b"hunter-prepared-package").hexdigest(),
        browser_form_digest=str(session_row["browser_form_digest"]),
        resume_sha256=plan_record["plan"]["resume"]["artifact_sha256"],
        target_url=str(session_row["current_url"]),
        checkpoint_id=str(session_row["checkpoint_id"]),
    )
    envelope = sign_authority_envelope(envelope)
    hunter = _HunterAuthorityClient(envelope)
    runner = HostedSubmitRunner(
        database,
        adapter_factory=lambda _job: browser,
        authority_client=hunter,
    )

    result = runner.run_once()

    assert result is not None
    assert result.attempted is True
    assert result.verification_status == "VERIFIED"
    assert browser.calls == 1
    assert hunter.read_calls == 1
    assert hunter.claim_calls == 1

    with database.connect() as connection:
        local_review = connection.execute(
            "SELECT approved_at FROM final_application_reviews WHERE review_id=?",
            (review["review_id"],),
        ).fetchone()
        final_session = connection.execute(
            "SELECT state FROM complete_application_sessions WHERE session_id=?",
            (session.session_id,),
        ).fetchone()
        commands = connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands WHERE session_id=?",
            (session.session_id,),
        ).fetchone()[0]
    assert local_review["approved_at"] is not None
    assert final_session["state"] == "VERIFIED"
    assert commands == 1

    # Terminal sessions are no longer candidates, so a worker replay cannot
    # click the employer action a second time.
    assert runner.run_once() is None
    assert browser.calls == 1
