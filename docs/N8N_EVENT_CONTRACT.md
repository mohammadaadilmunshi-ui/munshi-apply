# n8n event contract

n8n is an optional downstream action consumer. SQLite remains authoritative, and webhook delivery never participates in the application-event transaction.

## Canonical envelope

Every request body is canonical compact JSON with lexicographically sorted keys:

```json
{
  "application_id": "APP-000001",
  "correlation_id": "COR-000001",
  "event_id": "EVT-000001",
  "event_type": "APPLICATION_SUBMITTED",
  "occurred_at": "2026-08-13T23:30:00-04:00",
  "payload": {},
  "schema_version": "1.0",
  "source": "munshi-apply"
}
```

## Authentication headers

| Header                    | Value                                                  |
| ------------------------- | ------------------------------------------------------ |
| `X-Munshi-Event-Id`       | Canonical `event_id`                                   |
| `X-Munshi-Timestamp`      | Unix timestamp in seconds                              |
| `X-Munshi-Content-SHA256` | Lowercase SHA-256 hex digest of the exact request body |
| `X-Munshi-Signature`      | `sha256=<lowercase HMAC hex>`                          |

The signed content is:

```text
event_id + "." + timestamp + "." + body_sha256
```

The signature is HMAC-SHA256 using `MUNSHI_N8N_WEBHOOK_SECRET`.

## Required n8n validation order

1. Require all four authentication headers.
2. Reject timestamps more than five minutes old or in the future beyond that tolerance.
3. Hash the exact body bytes and compare the digest in constant time.
4. Recompute and compare the HMAC in constant time.
5. Parse and validate the schema `1.0` event envelope.
6. Confirm the header and body `event_id` match.
7. Insert `event_id` into a downstream idempotency store with a unique constraint; reject duplicates without repeating actions.
8. Return a `2xx` response only after the event has been safely accepted.

Invalid, expired, malformed, or duplicate requests must not trigger downstream actions. A non-`2xx` response leaves the local event eligible for bounded retry and eventual dead-letter review.
