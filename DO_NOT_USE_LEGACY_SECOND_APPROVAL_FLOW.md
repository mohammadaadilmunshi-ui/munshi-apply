# HISTORICAL ONLY: legacy second-approval / browser-babysitting flow

Status: RETIRED. DO NOT REUSE, REVIVE, CHERRY-PICK, OR TREAT AS A PRODUCT DIRECTION.

Canonical rule:

`one pre-browser package review -> one Hunter Approve & Submit mandate -> unattended Apply execution -> internal integrity snapshot -> exactly-once submit -> independent verification`

Apply must never create a customer-facing approval after Hunter has recorded the one package mandate. Local `READY_FOR_REVIEW` / review rows are internal integrity state only. Hosted submit may advance them automatically only after it reads and verifies Hunter's canonical authority.

Historical browser-assisted/final-approval paths may remain only for archaeology, regression proof, deletion, or fail-closing.
