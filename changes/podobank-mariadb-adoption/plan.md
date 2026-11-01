# Implementation Plan

## Summary

Use MariaDB as the sole database for development and verification from the backend foundation onward. Keep FastAPI with SQLAlchemy Core and hand-written SQL. Run MariaDB in Compose with persistent storage, make backend verification connect to a disposable MariaDB database, and wire that check into its own CI job. This change establishes the database foundation; banking API behavior remains in its later implementation change.

## Files and components that change

- `backend/podobank_api/settings.py`, `database.py`, `schema.py`, `seed.py`, and `cli.py`: MariaDB connection, DDL, idempotent seed, and guarded development reset.
- `backend/tests/**`: initialization, seed, reset safeguards, and MariaDB integration coverage against a dedicated test database.
- `pyproject.toml`, `uv.lock`: add the pure-Python PyMySQL driver and lock it with existing dependencies.
- `compose.yaml`, `.env.example`, `Dockerfile`: MariaDB 11.8 LTS service, health check, credentials from ignored local environment, persistent volume, and API readiness dependency.
- `scripts/verify_backend.py`, `checks.json`, `.github/workflows/repository.yml`: a MariaDB verification group, a CI database service, and a summary dependency for that job.
- `README.md`: MariaDB development setup, initialization, reset, and validation commands.
- `changes/podobank-mariadb-adoption/intent.md` and `spec.md`: the approved next product baseline, installed at closure.

## Order of work

1. Update `pyproject.toml`, `uv.lock`, `.env.example`, `compose.yaml`, and `Dockerfile` for a pinned MariaDB 11.8 image and the PyMySQL connection URL. The API waits for the database health check before startup. Prove the Compose model with `docker compose config --quiet`.
2. Port `backend/podobank_api/settings.py`, `database.py`, `schema.py`, `seed.py`, `cli.py`, and `backend/tests/**` to MariaDB. Use SQLAlchemy Core `text()` statements with named bind parameters so SQLAlchemy applies the active DBAPI parameter style. Keep numeric `users.id` and `accounts.id` primary keys, unique phone/Kakao/account-number lookup keys, and the owner/account foreign keys. Reset only the explicitly named development database with `APP_ENV=development`; tests use a separate `podobank_test` database. Prove initialization, seed idempotency, reset guards, and schema behavior with `DATABASE_URL=mysql+pymysql://podobank:podobank-test@127.0.0.1:3306/podobank_test APP_ENV=test python3 scripts/verify_backend.py --suite mariadb` while the test service is healthy.
3. Update `scripts/verify_backend.py` and `checks.json` so the backend check uses the `mariadb` group and connects only to the test database. Update `.github/workflows/repository.yml` with a MariaDB 11.8 service, health check, test credentials, `repo.py verify --group mariadb`, and add that job to `summary.needs`. Prove group wiring with `python3 scripts/repo.py status --change podobank-mariadb-adoption`.
4. Update `README.md` for the MariaDB workflow. Run `docker compose config --quiet`, start the Compose services, confirm `/health`, restart the API and database containers, and confirm seeded data remains in the named volume. Run `python3 scripts/repo.py verify --change podobank-mariadb-adoption --full` after all edits.

## Tests and proof

- MariaDB integration tests cover connection setup, table creation, foreign keys, unique keys, seed idempotency, reset restrictions, and persistence across API restarts.
- The CI MariaDB job uses a dedicated test database; it never connects to the developer database.
- `python3 scripts/repo.py status --change podobank-mariadb-adoption` must report current approvals, valid write scope, and all check groups wired.
- `python3 scripts/repo.py verify --change podobank-mariadb-adoption --full` must complete every registered check and write evidence under `.evidence/`.
- Review active source, baseline, README, Compose, and CI files to confirm they describe MariaDB as the initial database. Closed change packets remain immutable history.

## Risks and mitigations

- Resetting the wrong database could destroy data. Restrict reset to `APP_ENV=development`, the Compose development host, and the `podobank_dev` database name. Require tests to use the separately named `podobank_test` database.
- API startup can race the database. Gate API startup on the MariaDB health check and retain application health reporting.
- InnoDB deadlocks can abort concurrent transfers. The approved spec requires locking both account rows in ascending account ID order inside one transaction; a later transaction change must preserve this order and roll back all balance and ledger writes together.
- The GitHub App token lacks permission to push `.github/workflows/**`. Prepare the workflow change locally as authorized by the owner; if the App push is rejected, hand that file to the owner for the push.
- MariaDB and SQLAlchemy may differ from the earlier development SQL dialect. Use MariaDB integration tests as the source of truth and keep SQL parameter binding in SQLAlchemy Core `text()` statements.

## Rollback or recovery

- Keep the current merged baseline unchanged until this change is approved, implemented, verified, and merged.
- If the MariaDB service or schema cannot be recovered, stop the Compose stack and revert the adoption change through its reviewed change branch. Do not remove the named database volume as part of rollback; delete it only through an explicit development reset.
- If CI rejects the workflow change because of token permissions, leave the branch unpushed and hand the workflow file to the owner; do not use owner credentials or force-push.

## Open questions

None. The selected driver is PyMySQL, the container uses the MariaDB 11.8 LTS line, and the test database is isolated from the development database.
