# Implementation Plan

## Summary

Add a MariaDB transactional outbox for committed financial events and a separate Compose event-projector that retries delivery to MongoDB. Keep the JSONL → Alloy → Loki/Prometheus service-call observation path unchanged. The API writes only to MariaDB; MongoDB outages create a retry backlog without failing committed financial operations.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `backend/podobank_api/schema.py`: create the InnoDB outbox table and indexes through the existing idempotent schema path.
- `backend/podobank_api/features/financial_outbox/**`: add event-envelope validation, SQLAlchemy Core insert/claim/ack/retry operations, MongoDB upsert, polling, and replay.
- `backend/podobank_api/features/transactions/service.py` and `backend/podobank_api/features/loans/service.py`: insert success events through the active SQL connection before each state-changing transaction commits. For scheduled repayments, attach one outbox event to each candidate transaction that changes state; keep the existing aggregate JSONL event.
- `backend/podobank_api/cli.py`: add a long-running `project-events` command, a one-pass mode for verification, and an explicit replay mode for rebuilding the MongoDB projection.
- `compose.yaml` and `.env.example`: run one internal event-projector service after MariaDB and MongoDB are healthy; pass Mongo settings to the projector, not the API; expose no new host ports.
- `pyproject.toml` and `uv.lock`: add and lock PyMongo for the projector.
- `backend/tests/**`: cover transaction atomicity, event privacy and shape, repayment candidate behavior, retry/idempotency, and replay.
- `scripts/verify_event_projection.py` and `checks.json`: add an isolated Docker smoke check for MongoDB delivery and recovery.
- `README.md`: document the projector and the explicit replay command.

## Order of work

1. Add the MariaDB outbox schema and database tests first. Change `backend/podobank_api/schema.py` and add focused cases under `backend/tests/test_financial_outbox.py`; verify schema creation is repeatable and all outbox fields use InnoDB. Proof: `python3 scripts/verify_backend.py --suite mariadb`.
2. Implement the `features/financial_outbox` package and its tests. Persist a stable UUID and privacy-safe event envelope, claim pending rows with a recoverable lease, upsert MongoDB documents by `_id` using acknowledged journaled writes, and mark rows projected only after MongoDB accepts them. Apply retry backoff without discarding rows. Replay must upsert retained rows without changing MariaDB business data. Proof: `python3 scripts/verify_backend.py --suite mariadb`.
3. Instrument transaction and loan services. Use the same SQLAlchemy Core connection as each successful business transaction so an outbox insert failure rolls the whole transaction back. Keep failure attempts on the existing JSONL path. Give each committed repayment candidate its own event and preserve one aggregate JSONL event per batch. Extend transaction and loan tests, including a forced outbox insert error and a partially completed repayment batch. Proof: `python3 scripts/verify_backend.py --suite mariadb`.
4. Add the CLI and Compose integration. Update `backend/podobank_api/cli.py`, `compose.yaml`, `.env.example`, `pyproject.toml`, `uv.lock`, and `README.md`. Keep the API dependent only on MariaDB; start the separate projector after both databases are healthy. Provide one-pass and replay controls for operators. Proof: `docker compose --env-file .env.example config --quiet`.
5. Register the projection smoke check. Add `scripts/verify_event_projection.py` and its `checks.json` entry; the isolated check must prove MongoDB downtime leaves outbox rows pending, recovery delivers them, a write-before-ack crash does not create duplicates, and replay restores a cleared projection. Proof: `python3 scripts/verify_event_projection.py --smoke`.
6. Review the complete change against the approved spec and `REVIEW.md`, then run the full repository verification. Proof: `python3 scripts/repo.py verify --change podobank-financial-event-outbox --full`.

## Tests and proof

The backend suite runs against the registered MariaDB target. Focused unit and integration cases verify:

- a successful operation commits its state and exactly one transaction-level outbox row together;
- a forced outbox insert failure rolls back the corresponding balance, ledger, or loan-state change;
- failed service attempts create no outbox row and still use the existing JSONL event path;
- repayment batches create one outbox row for each committed paid/overdue candidate, none for skipped candidates, and one unchanged aggregate JSONL event;
- MongoDB transient failures leave rows recoverable, retries use the same event UUID, and a MongoDB write followed by a lost MariaDB acknowledgement does not duplicate documents;
- replay repopulates MongoDB from retained outbox rows and does not change financial state;
- MongoDB documents contain only the approved event fields and technical event UUID metadata.

The isolated projection smoke uses disposable Compose resources and example credentials. The final `repo.py verify --full` run must be complete, with every registered check passed and no `not-run`, `failed`, or `blocked` result. No test evidence is claimed until that command actually runs.

## Risks and mitigations

- The API now depends on one extra MariaDB write per successful financial transaction. This is intentional: if the outbox cannot commit, the associated financial state must roll back.
- MongoDB downtime can grow the MariaDB backlog. Keep rows indefinitely, retry without dropping events, and document replay and volume monitoring.
- The existing development MongoDB is a single Compose service. This change provides durable retry and projection rebuild from MariaDB, not host-level disaster recovery if the MariaDB outbox volume is also lost.
- Repayment batches commit candidates independently. Write an outbox row inside each candidate transaction so a later batch failure cannot erase evidence for earlier committed candidates.

## Rollback or recovery

- Keep the new outbox table and all rows during application rollback; the prior application version ignores the additive table. Do not automatically drop the table or truncate event rows.
- If MongoDB or the projector is unavailable, leave the API and MariaDB running; restore the service and let retries resume. If the MongoDB data volume must be recreated, run the explicit replay mode against the retained outbox before treating the projection as rebuilt.
- Reverting to the prior application stops new outbox events, so rollback is temporary recovery only. Restore the approved implementation after diagnosis; do not delete committed outbox history.

## Open questions

None. The approved spec fixes the guaranteed scope to committed successful state changes; failed service attempts remain best-effort JSONL observations.
