# Development Sample Banking Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable, development-only command that creates a synthetic PodoBank dataset of about 10,000 customers, account activity, loan states, and one locally login-capable demo customer.

**Architecture:** Keep `init-db` and `reset-db` unchanged. Put deterministic fixture construction in a focused module that receives a SQLAlchemy Core `Connection`; expose it only through a guarded `podobank-api seed-demo-data` CLI command that runs the whole seed in one transaction. Configure a local demo password through the environment and preserve an existing demo customer password hash.

**Tech Stack:** Python 3.13, MariaDB, SQLAlchemy Core, PodoBank API CLI, unittest, Docker Compose.

**Spec:** `changes/demo-sample-data/design.md`

## Global Constraints

- Use MariaDB and SQLAlchemy Core with hand-written SQL; do not use the ORM.
- The command may write only to `APP_ENV=development` and local `podobank_dev`; allow the Compose database host `db` and loopback hosts `localhost` and `127.0.0.1`, on the default MariaDB port only.
- Keep the default test seed small and leave `init-db` and `reset-db` behavior unchanged.
- Generate synthetic records only; generated customers other than the fixed demo customer have no password or Kakao identity.
- Store the demo password only as a hash, do not log it, and never overwrite an existing hash.
- Use bounded insert batches inside a single transaction; do not emit financial-operation telemetry for fixtures.
- Add no runtime dependency and do not modify `.github/workflows/**`.

## Review Focus

1. **Wrong target environment or database:** reject test, production, remote hosts, and databases other than `podobank_dev` before creating an engine; pin in `test_seed_demo_data_rejects_unsafe_database_targets`.
2. **Missing or short demo password:** fail before opening a transaction and avoid printing the supplied value; pin in `test_seed_demo_data_requires_demo_password`.
3. **Existing sample namespace is partial or collides with unrelated data:** fail without deleting or overwriting rows; pin in `test_seed_demo_data_rejects_partial_or_conflicting_samples`.
4. **Repeated full seed:** report a no-op and keep customer, account, ledger, loan, and repayment counts unchanged; pin in `test_seed_demo_data_is_idempotent`.
5. **Financial state inconsistency:** balances equal ledger sums, transfers have paired rows with one transaction ID, and loan schedules match application states; pin in `test_seed_demo_data_keeps_financial_records_consistent`.

---

### Task 1: Deterministic Demo Dataset Builder

**Files:**
- Create: `backend/podobank_api/demo_seed.py`
- Create: `backend/tests/test_demo_seed.py`

**Interfaces:**
- Consumes: `Connection`, `DEMO_CUSTOMER_PHONE`, `DEMO_ACCOUNT_NUMBER`, and `LOAN_PRODUCTS` from `podobank_api.seed`; `repayment_due_dates` from `podobank_api.features.loans.service`.
- Produces: `DEMO_CUSTOMER_COUNT = 10_000`, `DEMO_LEDGER_ENTRIES_PER_CUSTOMER = 20`, `DEMO_LOAN_APPLICATION_COUNT = 500`, `DEMO_LOAN_STATUS_COUNTS = {pending: 100, rejected: 100, repaying: 250, repaid: 50}`, `DemoSeedSummary(already_present, customer_count, account_count, ledger_entry_count, loan_application_count, repayment_count)`, and
  `seed_demo_data(connection, *, demo_customer_password, customer_count=DEMO_CUSTOMER_COUNT, ledger_entries_per_customer=DEMO_LEDGER_ENTRIES_PER_CUSTOMER, loan_application_count=DEMO_LOAN_APPLICATION_COUNT) -> DemoSeedSummary`.
- Counts passed as function parameters are for small integration tests only; the CLI uses the fixed defaults.

- [ ] **Step 1: Write failing MariaDB integration tests** in `backend/tests/test_demo_seed.py` for:
  - a small seed creating the fixed demo customer plus generated customers and one account per customer;
  - deterministic account activity with non-negative balances, ledger reconciliation, and paired transfers;
  - the fixed demo customer receiving a hashed password only when its hash is unset;
  - one active application maximum and one example of every application state in a small seed, valid repayment schedules, and overdue installments;
  - a pure default-distribution test asserting 100 pending, 100 rejected, 250 repaying, and 50 repaid applications;
  - rerunning a complete small seed producing no duplicate rows;
  - a partial sample namespace failing without deleting or overwriting rows.
- [ ] **Step 2: Run `APP_ENV=test DATABASE_URL=mysql+pymysql://podobank:podobank-test@127.0.0.1:3306/podobank_test python3 scripts/verify_backend.py --suite mariadb` and confirm the new builder tests fail** because the builder is not implemented.
- [ ] **Step 3: Implement the constants, summary type, deterministic identifiers/profile values, and `seed_demo_data` in `demo_seed.py`.** Use bulk parameter execution in bounded batches inside the caller's transaction. Include the fixed demo customer in the requested customer count, ensure it has ledger activity and a repaying loan, and preserve any existing password hash.
- [ ] **Step 4: Run `APP_ENV=test DATABASE_URL=mysql+pymysql://podobank:podobank-test@127.0.0.1:3306/podobank_test python3 scripts/verify_backend.py --suite mariadb` and confirm all builder tests pass.**
- [ ] **Step 5: Commit the builder and its tests with `agent-git`.**

### Task 2: Guarded CLI, Demo Login Configuration, and Documentation

**Files:**
- Modify: `backend/podobank_api/cli.py`
- Modify: `backend/podobank_api/database.py`
- Modify: `backend/podobank_api/settings.py`
- Modify: `backend/tests/test_database.py`
- Modify: `backend/tests/test_settings.py`
- Modify: `.env.example`
- Modify: `compose.yaml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `seed_demo_data(connection, ...)` and `DemoSeedSummary` from Task 1.
- Produces: `validate_demo_seed_target(app_env: str, database_url: str) -> None` and `Settings.validate_demo_customer_seed() -> None`.
- CLI command: `podobank-api seed-demo-data`, with no arguments; it validates settings and target before opening the database, then invokes the builder inside one transaction and prints only row counts.

- [ ] **Step 1: Write failing settings and CLI tests** named `test_seed_demo_data_requires_demo_password`, `test_seed_demo_data_rejects_unsafe_database_targets`, `test_seed_demo_data_requires_initialized_database`, and `test_seed_demo_data_command_reports_counts_without_secrets`. Assert rejection occurs before engine creation for test, production, remote, and wrong-database targets; allow only `db`, `localhost`, and `127.0.0.1` with `podobank_dev`.
- [ ] **Step 2: Run `APP_ENV=test DATABASE_URL=mysql+pymysql://podobank:podobank-test@127.0.0.1:3306/podobank_test python3 scripts/verify_backend.py --suite mariadb` and confirm these tests fail** on the missing setting, validator, and command.
- [ ] **Step 3: Add `DEMO_CUSTOMER_PASSWORD` to `Settings`, validate it only for the seed command, pass it through Compose, and provide a local-only value in `.env.example`.** Add the guarded CLI command and development target validator; require the default schema and seed rows to exist; leave `init-db` and `reset-db` unchanged.
- [ ] **Step 4: Document initialization followed by `docker compose exec api podobank-api seed-demo-data`, the fixed customer's phone/password configuration, generated-user login limits, and that `reset-db` requires rerunning the sample command.**
- [ ] **Step 5: Run `APP_ENV=test DATABASE_URL=mysql+pymysql://podobank:podobank-test@127.0.0.1:3306/podobank_test python3 scripts/verify_backend.py --suite mariadb` and confirm lint, format, and all MariaDB backend tests pass.**
- [ ] **Step 6: Commit the CLI, configuration, documentation, and tests with `agent-git`.**

### Task 3: Full-Size and Product Verification

**Files:**
- No new product files; use the isolated verification environment and evidence generated by repository checks.

- [ ] **Step 1: Use the `verify-podobank-ui` skill to launch an isolated app environment, run `init-db` and `seed-demo-data`, and verify the fixed demo customer's local login, ledger, and loan screens plus the employee pending-loan queue.**
- [ ] **Step 2: Run `podobank-api seed-demo-data` a second time in that isolated database and verify the command reports the existing dataset without changing sample row counts or the configured demo password.**
- [ ] **Step 3: Run `python3 scripts/repo.py status --change demo-sample-data` and `python3 scripts/repo.py verify --change demo-sample-data --full`; require a complete run with every registered check passing.**
- [ ] **Step 4: Review the final diff against `REVIEW.md`; confirm no real personal data, credentials, generated analysis metadata, or unrelated changes are present.**
- [ ] **Step 5: Run `python3 scripts/repo.py close demo-sample-data --evidence <full-run-evidence>`, commit the closure with `agent-git`, push with `agent-gh`, and open a PR containing `Change-ID: demo-sample-data`.**

## Risks and mitigations

- A partial or colliding sample namespace could make a retry ambiguous. Detect it before inserts and fail without deleting existing rows; insert the dataset in one transaction.
- Large transactions can consume memory. Generate rows deterministically and send bounded parameter batches while keeping them in the same transaction.
- Fixture ledger and loan rows can diverge from the current service rules. Reuse the loan due-date helper and verify balances, transfer pairs, active-loan limits, and repayment statuses in MariaDB tests.
- A known local demo password could be reused outside development. The CLI refuses non-development and non-local targets; documentation labels the example development-only.

## Rollback or recovery

The command is additive and does not reset the database. If the dataset is incomplete because pre-existing rows conflict with the deterministic sample namespace, it fails without deleting them and provides a recovery message. To remove a successfully seeded dataset, use the existing development-only `reset-db` flow, then initialize normally; the bulk sample data is not recreated until `seed-demo-data` runs again.

## Open questions

None. The data volume is fixed for the first implementation; the command itself exposes no count overrides. The 500 loan records use 100 pending, 100 rejected, 250 repaying, and 50 repaid states.
