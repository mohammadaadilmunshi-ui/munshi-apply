from __future__ import annotations

import json

import pytest
import test_complete_application_loop as fixtures

loop = fixtures.loop
ready = fixtures.ready


@pytest.mark.parametrize("mutation", ["invalidate", "unapprove", "snapshot", "plan"])
def test_change_during_browser_inspection_cannot_submit(loop, mutation):
    service, db, browser, _, review = ready(loop)
    inspect = browser.inspect_submission

    def race(*, plan):
        observation = inspect(plan=plan)
        with db.connect() as connection:
            if mutation == "invalidate":
                connection.execute(
                    "UPDATE final_application_reviews SET invalidated_at='revoked' "
                    "WHERE review_id=?",
                    (review["review_id"],),
                )
            elif mutation == "unapprove":
                connection.execute(
                    "UPDATE final_application_reviews SET approved_at=NULL WHERE review_id=?",
                    (review["review_id"],),
                )
            elif mutation == "snapshot":
                altered = dict(review["review"])
                altered["answers"] = []
                connection.execute(
                    "UPDATE final_application_reviews SET review_json=? WHERE review_id=?",
                    (json.dumps(altered), review["review_id"]),
                )
            else:
                connection.execute(
                    "UPDATE career_os_application_plans SET plan_digest=? WHERE plan_id=?",
                    ("f" * 64, review["review"]["plan_id"]),
                )
        return observation

    browser.inspect_submission = race
    with pytest.raises(ValueError, match="changed|approved|integrity"):
        service.submit(review_id=review["review_id"], idempotency_key="race", adapter=browser)
    assert browser.calls == 0
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM final_submit_commands").fetchone()[0] == 0


def test_corrupted_review_snapshot_is_rejected_before_browser_access(loop):
    service, db, browser, _, review = ready(loop)
    with db.connect() as connection:
        changed = dict(review["review"])
        changed["answers"] = []
        connection.execute(
            "UPDATE final_application_reviews SET review_json=? WHERE review_id=?",
            (json.dumps(changed), review["review_id"]),
        )
    with pytest.raises(ValueError, match="integrity"):
        service.submit(review_id=review["review_id"], idempotency_key="corrupt", adapter=browser)
    assert browser.calls == 0
