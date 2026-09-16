from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

from test_complete_application_loop import (
    _seed_authority,
    loop as _complete_application_loop_fixture,
)

from munshi_apply_native.background_prepare_queue import DurablePreparationQueue
from munshi_apply_native.hosted_submit_worker import HostedSubmitRunner
from munshi_apply_native.hunter_submit_authority_client_v1 import (
    SubmitAuthorizationClientError,
)
from munshi_apply_native.submit_authority_inbox_v1 import (
    SubmitAuthorityInbox,
    expected_claim_digest,
)

loop = _complete_application_loop_fixture


class _AuthorityBackend:
    def __init__(
        self,
        envelope: dict,
        *,
        lose_first_claim_response: bool = False,
    ) -> None:
        self.envelope = dict(envelope)
        self.lose_first_claim_response = lose_first_claim_response
        self.lock = Lock()
        self.claimant_id: str | None = None
        self.claim_calls = 0
        self.read_calls = 0
        self.consumed = False

    def read(self, binding: dict) -> dict:
        with self.lock:
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

    def claim(self, envelope: dict, *, claimant_id: str) -> dict:
        with self.lock:
            self.claim_calls += 1
            if self.claimant_id is None:
                self.claimant_id = claimant_id
            assert claimant_id == self.claimant_id
            claim_digest = expected_claim_digest(
                authorization_id=str(envelope["authorization_id"]),
                authority_digest=str(envelope["authority_digest"]),
                claimant_id=claimant_id,
                generation=int(envelope["generation"]),
            )
            if self.lose_first_claim_response and self.claim_calls == 1:
                # Model Hunter consuming the authority before its response is
                # lost. A retry with the same claimant must converge.
                self.consumed = True
                raise SubmitAuthorizationClientError(
                    "synthetic claim response lost"
                )
            replayed = self.consumed
            self.consumed = True
            return {
                "status": "CONSUMED" if replayed else "CLAIMED",
                "submission_authority": True,
                "authorization_id": envelope["authorization_id"],
                "authority_digest": envelope["authority_digest"],
                "generation": int(envelope["generation"]),
                "claim_digest": claim_digest,
                **({"replayed": True} if replayed else {}),
            }


class _AuthorityClient:
    def __init__(self, backend: _AuthorityBackend) -> None:
        self.backend = backend

    def read(self, binding: dict) -> dict:
        return self.backend.read(binding)

    def claim(self, envelope: dict, *, claimant_id: str) -> dict:
        return self.backend.claim(envelope, claimant_id=claimant_id)


class _FailReceiptClient:
    def __init__(self) -> None:
        self.calls = 0

    def ingest(self, receipt: dict) -> dict:
        self.calls += 1
        raise RuntimeError("synthetic receipt response lost")


class _SuccessReceiptClient:
    def __init__(self) -> None:
        self.calls = 0
        self.lock = Lock()

    def ingest(self, receipt: dict) -> dict:
        with self.lock:
            self.calls += 1
        return {"receipt_id": receipt["receipt_id"], "accepted": True}


class _BarrierAdapter:
    def __init__(self, browser, barrier: Barrier) -> None:
        self.browser = browser
        self.barrier = barrier

    def prepare_form(self, *, plan, checkpoint, resolved_values):
        prepared = self.browser.prepare_form(
            plan=plan,
            checkpoint=checkpoint,
            resolved_values=resolved_values,
        )
        self.barrier.wait(timeout=10)
        return prepared

    def inspect_submission(self, *, plan):
        return self.browser.inspect_submission(plan=plan)

    def submit(self, *, plan, review):
        return self.browser.submit(plan=plan, review=review)

    def close(self) -> None:
        return None


def _ready_hosted(loop):
    service, database, browser = loop
    session = service.start_session(plan_id="application-plan-1")
    queue = DurablePreparationQueue(database)
    prepare_job = queue.enqueue_session(
        session_id=session.session_id,
        tenant_id="tenant-a",
        user_id="member-a",
    )

    pending = service.prepare_session(
        session_id=session.session_id,
        adapter=browser,
    )
    assert pending.state == "NEEDS_INPUT"
    task = service.resolutions.list(application_id=session.application_id)[0]
    service.resolve_task(
        task_id=task.task_id,
        value="https://example.test/portfolio",
    )
    prepared = service.prepare_session(
        session_id=session.session_id,
        adapter=browser,
    )
    assert prepared.state == "READY_FOR_REVIEW"
    review = service.build_review(session_id=session.session_id)

    with database.connect() as connection:
        connection.execute(
            """UPDATE complete_application_prepare_jobs
               SET state='READY_FOR_REVIEW',finished_at=CURRENT_TIMESTAMP,
                   lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL
               WHERE job_id=?""",
            (prepare_job["job_id"],),
        )

    service.approve_review(review_id=str(review["review_id"]))
    envelope = _seed_authority(loop, review, session, accept=False)
    accepted = SubmitAuthorityInbox(database).accept(
        dict(envelope),
        now=str(envelope["issued_at"]),
    )
    assert accepted.accepted is True
    return service, database, browser, session, review, envelope


def test_lost_hunter_claim_response_converges_after_fresh_runner(loop):
    _service, database, browser, _session, _review, envelope = _ready_hosted(loop)
    backend = _AuthorityBackend(envelope, lose_first_claim_response=True)
    first_runner = HostedSubmitRunner(
        database,
        adapter_factory=lambda _job: browser,
        authority_client=_AuthorityClient(backend),
        production_receipt_client=_SuccessReceiptClient(),
    )

    first = first_runner.run_once()

    assert first is None
    assert browser.calls == 0
    assert backend.claim_calls == 1
    with database.connect() as connection:
        claim = connection.execute(
            "SELECT state,claimant_id FROM production_submit_authority_claims"
        ).fetchone()
    assert claim["state"] == "CLAIM_IN_FLIGHT"
    assert str(claim["claimant_id"]) == str(backend.claimant_id)

    # A fresh worker instance reuses the durable claimant. Hunter responds
    # CONSUMED/replayed for that same claimant, so Apply finalizes the claim and
    # crosses the employer boundary exactly once.
    second_runner = HostedSubmitRunner(
        database,
        adapter_factory=lambda _job: browser,
        authority_client=_AuthorityClient(backend),
        production_receipt_client=_SuccessReceiptClient(),
    )
    second = second_runner.run_once()

    assert second is not None
    assert second.verification_status == "VERIFIED"
    assert browser.calls == 1
    assert backend.claim_calls == 2
    with database.connect() as connection:
        assert connection.execute(
            "SELECT state FROM production_submit_authority_claims"
        ).fetchone()[0] == "CLAIMED"
        assert connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands"
        ).fetchone()[0] == 1


def test_pending_receipt_survives_fresh_runner_without_resubmit(loop):
    _service, database, browser, _session, _review, envelope = _ready_hosted(loop)
    backend = _AuthorityBackend(envelope)
    failed_receipt = _FailReceiptClient()
    first_runner = HostedSubmitRunner(
        database,
        adapter_factory=lambda _job: browser,
        authority_client=_AuthorityClient(backend),
        production_receipt_client=failed_receipt,
    )

    first = first_runner.run_once()

    assert first is not None
    assert first.verification_status == "VERIFIED"
    assert browser.calls == 1
    assert failed_receipt.calls == 1

    delivered_receipt = _SuccessReceiptClient()

    def _must_not_rebuild_adapter(_job):
        raise AssertionError(
            "receipt recovery must not re-enter browser execution"
        )

    second_runner = HostedSubmitRunner(
        database,
        adapter_factory=_must_not_rebuild_adapter,
        authority_client=_AuthorityClient(backend),
        production_receipt_client=delivered_receipt,
    )
    second = second_runner.run_once()

    assert second is not None
    assert second.state == "RECEIPT_DELIVERED"
    assert second.attempted is False
    assert second.verification_status == "VERIFIED"
    assert browser.calls == 1
    assert delivered_receipt.calls == 1
    with database.connect() as connection:
        receipt = connection.execute(
            "SELECT state,attempt_count FROM production_receipt_outbox"
        ).fetchone()
    assert receipt["state"] == "DELIVERED"
    assert receipt["attempt_count"] == 2


def test_two_hosted_workers_racing_one_session_submit_once(loop):
    _service, database, browser, _session, _review, envelope = _ready_hosted(loop)
    backend = _AuthorityBackend(envelope)
    receipt_client = _SuccessReceiptClient()
    barrier = Barrier(2)

    def _adapter_factory(_job):
        return _BarrierAdapter(browser, barrier)

    runners = [
        HostedSubmitRunner(
            database,
            adapter_factory=_adapter_factory,
            authority_client=_AuthorityClient(backend),
            production_receipt_client=receipt_client,
        )
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda runner: runner.run_once(), runners))

    assert browser.calls == 1
    assert any(
        result is not None and result.verification_status == "VERIFIED"
        for result in results
    )
    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM final_submit_commands"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM production_submit_authority_executions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM application_submission_receipts"
        ).fetchone()[0] == 1
