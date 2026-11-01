# Implementation Plan

## Summary

Implement the first MariaDB-backed feature slice: Kakao signup/login, optional customer password login, employee local login, JWT HttpOnly sessions, and automatic default-account issuance. Run MariaDB with `SQL_MODE=ORACLE` while retaining strict data validation modes. Organize the source by feature under `backend/podobank_api/features/`, using `api.py`, `service.py`, and `sql.py` where each feature needs them. Authentication-specific provider, dependency, and password-hashing code stays within `features/auth/`; account provisioning and account reads stay within `features/accounts/`.

This implements requirements already present in the root specification. The change does not set event fields, Prometheus metrics, or dashboard panels.

For the later transaction and loan feature slices, retain the root specification's money-movement invariant: use InnoDB and one explicit transaction for balance updates and ledger writes. The current product scope has no account close, suspend, or delete operation, and account IDs/numbers are not changed by application flows. Therefore recipient lookup by phone/account number may resolve the destination account ID before opening the money-movement transaction; mutable account rows must still be locked inside that transaction. If account lifecycle or ownership changes are added later, revisit this assumption and include those rows in the transaction and lock order.

Withdrawals lock the account by primary key with `SELECT ... FOR UPDATE WAIT 3` before checking funds and debiting. Transfers lock the two account rows with separate primary-key lookups in ascending account ID order before checking funds or changing either balance. `WAIT 3` limits each locking statement's lock wait; it is not an end-to-end request timeout. Deposits use `balance = balance + :amount` and write the ledger record in the same transaction. A separate locking read is unnecessary if the ledger stores only the amount and the application does not first read the balance. If a later ledger design stores `balance_after`, lock the account first, then update and record the resulting balance within the same transaction. Decide ledger fields in the transaction feature slice.

Loan transactions use one documented lock order across every code path that touches the same rows: lock the loan/application and relevant repayment rows in deterministic order, then lock the account. Do not introduce a path that takes these locks in the reverse order. Commit only after every related balance, state, and ledger write succeeds; otherwise roll back. Read-only requests do not take these locks. Consistent lock order reduces deadlock risk but does not guarantee that deadlocks or MariaDB 11.8 `ER_CHECKREAD` conflicts cannot occur. Treat `ER_CHECKREAD` (1020) and deadlock (1213) as whole-transaction rollback cases; treat lock timeout (1205) as a transaction failure by allowing the exception to escape the `Engine.begin()` block or explicitly rolling back. Any retry must start a fresh transaction, be bounded, and preserve request idempotency. Oracle SQL mode does not replace or alter this locking requirement.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `backend/podobank_api/app.py`: compose and mount feature routers, retain `/health`, and configure explicit credentialed CORS origins.
- `backend/podobank_api/features/auth/`: implement request/response API, current-user and role dependencies, Kakao authorization-code exchange, password hashing, JWT issue/validation, and authentication use cases. SQL statements live in `sql.py` and use SQLAlchemy Core `text()` with bound parameters.
- `backend/podobank_api/features/accounts/`: implement account read and idempotent default-account provisioning, with SQL in `sql.py`. Account-number generation must respect the unique database constraint and retry collisions.
- `backend/podobank_api/database.py`, `schema.py`, `seed.py`, `settings.py`: wire configuration and make the initial employee seed idempotent. The employee password is read from local environment configuration and stored only as a password hash.
- `backend/tests/`: add MariaDB-backed auth/account tests; mock Kakao HTTP responses so tests do not depend on Kakao availability or real credentials.
- `compose.yaml`, `Dockerfile`, `.env.example`, `README.md`: configure MariaDB Oracle SQL mode, pass local auth configuration to the API, keep schema initialization out of API startup, and document the explicit initialization command. Never commit live provider keys, JWT secrets, or employee passwords.
- `pyproject.toml`, `uv.lock`: add only the dependencies needed for JWTs, password hashing, and the Kakao HTTP client.

## Order of work

1. Configure the MariaDB service with `--sql-mode=ORACLE,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION`. Keep strict validation enabled because Oracle mode alone does not include `STRICT_TRANS_TABLES`. Add and validate settings for Kakao REST API credentials and fixed redirect URI, JWT signing secret and lifetime, employee seed credentials, and allowed frontend origins. Wire them through Compose. Keep local sample values in `.env.example`; production startup must reject placeholder signing secrets and insecure cookie settings. Prove Compose interpolation with `docker compose config --quiet` without printing resolved secrets.
2. Add `features/auth/` and `features/accounts/` following the existing feature-slice convention. `app.py` composes routers; each feature's `api.py` owns HTTP parsing and responses, `service.py` owns use cases and transaction orchestration, and `sql.py` owns bound SQLAlchemy Core statements. `auth` may call the public account-provisioning operation with the same open connection; `accounts` must not import `auth`. Feature modules must not import `app.py`. Shared `database.py` and `settings.py` provide infrastructure; `schema.py` owns DDL and indexes; `seed.py` owns explicit initial data. The API layer never contains SQL, and no ORM is introduced.
3. Implement Kakao authorization-code exchange on the server. Existing Kakao subjects sign in; first-time subjects must supply phone number, age, gender, marital status, and employment status, with the display name taken from Kakao's profile response. Create the customer and exactly one default account in a single MariaDB transaction. Reject duplicate phone numbers without linking an unverified phone to another user. Repeated callbacks must not create duplicate users or accounts.
4. Implement customer local login only when a password hash exists, authenticated one-time password setup for customers without one, employee local login, logout, and authenticated current-user/account reads. Hash passwords with Argon2id. Sign JWTs with HS256 using the internal numeric user ID as `sub` and `iat`/`exp` claims; make the lifetime configurable with a 120-minute development default. Issue and clear the JWT only through an HttpOnly cookie; never return it in a response body. Set `Secure` according to environment and `SameSite=Lax` for the local browser/API setup. Read user role from MariaDB for authorization. Reject invalid credentials without exposing whether a phone number exists.
5. Seed one bank employee idempotently from `BANK_EMPLOYEE_PHONE` and `BANK_EMPLOYEE_PASSWORD`, hashing the password before storage. Require those values for explicit development initialization and document them in `.env.example` as replaceable demo values. Keep the existing demo customer/account seed idempotent. Database initialization must not reset existing MariaDB data. Change the Dockerfile command to start only Uvicorn; schema and seed creation remain an explicit `docker compose exec api podobank-api init-db` action documented in the README.
6. Add endpoint and database tests for the effective global and session SQL modes, MariaDB schema/seed statements under Oracle mode, Kakao signup/login (provider mocked), duplicate phone rejection, one-account issuance under repeat login, optional customer password behavior, employee login and role, cookie flags, logout, and allowed-origin credentialed CORS. Run these only against the isolated `podobank_test` database.
7. Update the README with required environment values and the explicit database initialization command. Run the registered backend checks and full change verification, review the complete diff, and close the packet with the resulting evidence.

## Tests and proof

- `docker compose config --quiet` succeeds with the documented local `.env` values, without emitting resolved secrets in captured output. Starting the API does not create or reset schema/data; the explicit `init-db` command creates them idempotently.
- MariaDB integration coverage proves database-backed identity, idempotent account issuance, role enforcement, and seed behavior against `podobank_test`.
- HTTP tests prove JWT cookie attributes and CORS behavior; Kakao provider calls are mocked and no live token or personal data is recorded.
- `python3 scripts/repo.py verify --change podobank-auth-account-foundation --full` completes every registered check and writes evidence under `.evidence/`.

## Risks and mitigations

- Kakao provider failure could block first login. Keep the provider call behind `features/auth/kakao.py`, translate provider failures to stable API errors, and test them with mocked responses.
- Concurrent first logins could create duplicate accounts. Use a single DB transaction, unique constraints on Kakao subject, phone, and account owner, and re-read the winning row on uniqueness conflicts.
- Credentialed cookies require a narrow CORS policy. Configure explicit origins, methods, and headers; never use wildcard origins with credentials.
- Oracle SQL mode changes parsing and some SQL behavior, including `SIMULTANEOUS_ASSIGNMENT`; it does not change InnoDB's storage layout or row-locking rules. Keep SQL literals unambiguous, retain strict mode, and run the MariaDB integration suite under the configured mode.
- Employee seed credentials and JWT signing keys are secrets. Load them from the ignored local `.env`, validate required values, and ensure logs and API responses never include them.

## Rollback or recovery

- Revert the feature change through a reviewed follow-up change if login or account provisioning is incorrect; do not rewrite shared history.
- Keep the MariaDB volume. Use the existing explicit development reset command only when an owner intentionally chooses to discard local development data.

## Open questions

None in the approved product behavior. Provider credentials and employee seed credentials are local environment configuration, not values committed to the repository.
