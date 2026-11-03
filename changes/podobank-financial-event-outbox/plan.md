# Implementation Plan

## Summary

Keep MariaDB as the source for structured financial data. After each successful API financial transaction commits, the API makes one direct, bounded-time best-effort write of its explicit event document to MongoDB. MongoDB failures never roll back or fail committed financial operations. Do not add an outbox, relay, projector, retry, or replay path. Preserve the existing JSONL → Alloy → Loki/Prometheus observation path.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `backend/podobank_api/schema.py` and `backend/tests/test_database.py`: remove the unmerged financial outbox table and its schema expectations.
- `backend/podobank_api/features/financial_events/**`: create privacy-safe event envelopes and write them directly to MongoDB with PyMongo; bound connection/operation time and contain failures as best-effort delivery errors.
- `backend/podobank_api/features/transactions/service.py` and `backend/podobank_api/features/loans/service.py`: attempt MongoDB event writes only after successful MariaDB commits. Failed service attempts remain JSONL-only. For repayment batches, write one event after each candidate transaction that changes state and preserve the existing aggregate JSONL event.
- `backend/podobank_api/cli.py`: remove the unmerged `project-events` CLI command; keep existing commands unchanged.
- `compose.yaml` and `.env.example`: keep MongoDB internal with its persistent volume; give `MONGO_URL` and `MONGO_DB_NAME` to the API. Do not make API startup or health depend on MongoDB.
- `pyproject.toml` and `uv.lock`: add and lock PyMongo for the API event writer.
- `backend/tests/**`: cover event shape/privacy, post-commit ordering, repayment candidate behavior, and MongoDB write failure isolation.
- `scripts/verify_mongodb_events.py` and `checks.json`: add an isolated Docker smoke check for direct API-to-MongoDB event writes and best-effort behavior during MongoDB outage.
- `README.md`: document the direct write path and that events can be lost; do not document replay or recovery commands.

## Order of work

1. Remove the unmerged outbox table and its database assertions from `backend/podobank_api/schema.py` and `backend/tests/test_database.py`. Remove outbox-specific tests that no longer apply. Proof: `python3 scripts/verify_backend.py --suite mariadb`.
2. Add `features/financial_events` with an allowlisted event envelope and a MongoDB writer that uses a finite timeout, logs a static failure code, and does not propagate Mongo errors to the business operation. Unit tests use a fake collection/client to verify safe fields and failure handling. Proof: `python3 scripts/verify_backend.py --suite mariadb`.
3. Instrument transaction and loan services. Capture the event for a successful state change, exit the MariaDB transaction successfully, then make one MongoDB write attempt. Do not write MongoDB events for failed service attempts or skipped repayment candidates. Verify a MongoDB error leaves the committed financial result successful and unchanged. Proof: `python3 scripts/verify_backend.py --suite mariadb`.
4. Remove the unmerged `project-events` CLI parser, keep the API's existing Mongo environment settings, add PyMongo to `pyproject.toml` and `uv.lock`, and document best-effort semantics in `README.md`. Proof: `docker compose --env-file .env.example config --quiet`.
5. Add `scripts/verify_mongodb_events.py` and register it in `checks.json`. The isolated smoke check must prove an API transaction writes a safe MongoDB event, MongoDB downtime does not fail the financial transaction, and no retry or replay later restores the missing event. Proof: `python3 scripts/verify_mongodb_events.py --smoke`.
6. Review the complete change against the approved spec and `REVIEW.md`, then run full repository verification. Proof: `python3 scripts/repo.py verify --change podobank-financial-event-outbox --full`.

## Tests and proof

The backend suite runs against the registered MariaDB target. Focused integration and unit cases verify:

- a successful transaction commits financial state before the event writer is called;
- a failed or rolled-back financial operation does not create a MongoDB event;
- a MongoDB connection/write error does not fail the already-committed operation or roll back its database state;
- events contain only approved static operation, outcome, reason, UTC timestamp, UUID, schema version, and repayment batch counts/ID;
- repayment batches attempt one event for each committed state-changing candidate, no event for skipped candidates, and keep one aggregate JSONL event;
- the API can start and serve financial operations while MongoDB is unavailable, and missed events remain absent after MongoDB recovers;
- the API and MongoDB remain internal Compose services without new public ports; no projector service or MariaDB outbox table is present.

The isolated smoke uses disposable Compose resources and example credentials. The final `repo.py verify --full` run must be complete, with every registered check passed and no `not-run`, `failed`, or `blocked` result. No test evidence is claimed until that command actually runs.

## Risks and mitigations

- A process failure after MariaDB commit but before the MongoDB write can lose the event. This is an accepted limitation; no durable relay or reconciliation is included.
- MongoDB outages may cause some or all event writes to be skipped. Bound each write attempt and contain its error so financial API availability does not depend on MongoDB.
- A synchronous post-commit write adds bounded latency to a successful API call. Use a short explicit timeout and record only a static local error code on failure.
- A client retry after an ambiguous response can produce another financial operation and a distinct event. API idempotency is outside this change.
- MongoDB volume loss cannot be recovered from MariaDB. The database contains no event backup or replay source.

## Rollback or recovery

- The prior application ignores MongoDB event documents, so reverting the application stops new event writes without changing financial data. Existing MongoDB event documents can remain in the MongoDB volume.
- MongoDB may be unavailable while API and MariaDB continue serving financial operations. Restore MongoDB for new event attempts; events missed during the outage are not recovered.
- No schema migration or event replay is required to roll back because this change adds no MariaDB table.

## Open questions

None. The owner explicitly removed the event-loss prevention requirement. Successful committed events are attempted once after commit; delivery is best-effort, and failed service attempts remain JSONL-only.
