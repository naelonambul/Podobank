# Podobank MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. Keep the repository's `change-execution` gates; do not implement until this packet reports `readiness=ready`.

**Goal:** Build the synthetic banking API, append-only event feed, loan-product comparison, partner payment flow, and AWS deployment package in the approved specification.

**Architecture:** One FastAPI application writes synthetic state, immutable business events, and transactional telemetry-outbox rows to MariaDB. A dispatcher emits committed event records as structured stdout logs and mirrors them to a shared file that Alloy forwards to Loki; Prometheus scrapes metrics and Grafana presents operator dashboards. AWS deployment adds three EC2 roles in the owner's existing VPC: API+Alloy, database, and observability.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy Core with PyMySQL, MariaDB 11.4, Docker Compose, Grafana Alloy, Loki, Prometheus, Grafana, Terraform 1.14.5 with AWS provider 6.33.0, `uv`, pytest, Ruff, and mypy.

**Spec:** `changes/podobank-mvp/spec.md`

## Global Constraints

- All accounts, deposits, withdrawals, transfers, loans, and partner payments are fictional and remain inside the bootcamp environment.
- The application does not connect to real financial accounts, move real funds, or settle real payments.
- Amounts are positive integer Korean won (`KRW`); floating-point monetary values are not accepted.
- Retrieve only publicly accessible pages, honor each source's published access conditions and request limits, and do not bypass authentication, bot controls, or other access restrictions. Store normalized product facts and attribution rather than a full copied page.
- The FastAPI application and MariaDB are the source of truth for synthetic state and business events. Loki receives structured log copies; Prometheus stores service metrics.
- The target is the existing AWS VPC. Do not create or modify the VPC or existing instances. Do not expose MariaDB, Loki, Prometheus, or Grafana administration to the public Internet.
- Keep Loki and Prometheus retention bounded at 14 days. Preserve MariaDB data on encrypted EBS volumes and retain daily encrypted EBS snapshots for seven days.
- AWS deployment requires an owner-provided encrypted S3 bucket for Terraform remote state, a private OCI image registry, and existing VPC egress for SSM, image pulls, and public bank-page retrieval. Do not create these shared resources in this change.
- The MVP has no frontend. Nginx is reserved for serving a future frontend and does not proxy the MVP API.
- All identifiers and event payloads represent synthetic bootcamp data. Real personal data, real account numbers, bank credentials, and API secrets are excluded from events and examples.

## Review Focus

- Zero, negative, fractional, oversized, or malformed monetary amounts must not mutate balances; validation and domain rejection remain distinct.
- Concurrent MariaDB transfers and insufficient-funds races must preserve non-negative balances and atomic event/state writes.
- Replayed idempotency keys must not duplicate deposits, transfers, loans, or payments; changed payloads under the same key must conflict.
- Missing product fields, retired products, changed markup, timeouts, and blocked sources must preserve prior snapshots and expose unknown/stale status without fabricated terms or access-control bypass.
- Telemetry must retain event and correlation IDs without secrets or high-cardinality metric labels; event pagination must not silently skip or repeat records.

---

## Files and Components That Change

- `src/podobank/`: FastAPI application, routes, MariaDB repositories, event store and telemetry outbox, ledger, scenarios, catalog adapters, loan recommendations, payments, structured logging, and metrics.
- `tests/`: MariaDB-backed API and service tests plus sanitized bank-page fixtures.
- `pyproject.toml`, `uv.lock`, `.python-version`: locked Python 3.13 environment and canonical product tooling.
- `compose.yaml`: complete local API, MariaDB, Alloy, Loki, Prometheus, and Grafana stack. No Nginx frontend is included.
- `deploy/aws/{api,database,observability}/compose.yaml`: Compose definitions for the three EC2 roles.
- `deploy/observability/`: Alloy, Loki, Prometheus, and Grafana datasource/dashboard configuration.
- `infra/aws/`: Terraform for new EC2 instances, scoped security groups and instance profiles, encrypted persistent EBS volumes, seven-day EBS snapshot retention, and an S3 remote-state backend in the existing VPC; no VPC or existing-instance resources.
- `deploy/verify-deployment.sh`: offline Terraform, Compose, and deployment-configuration validation.
- `Dockerfile`, `.dockerignore`, `.env.example`, `.gitignore`: container build and safe local configuration.
- `checks.json`: `product` and `deployment` check groups.
- `.github/workflows/repository.yml`: MariaDB-backed product job and Terraform/Compose validation job, both required by `summary`. The owner must push this workflow file; the GitHub App cannot push it.
- `README.md`: local stack, API examples, event/log distinction, source refresh, existing-VPC deployment inputs, and operational runbook.
- `changes/podobank-mvp/change.json`: bind plan approval to this complete `write_scope`.

The initial loan catalog sources are the official [Hana Bank credit-loan disclosure index](https://www.kebhana.com/cont/mall/mall09/mall0903/mall090303/index.jsp) and the official [Woori Bank loan-product catalog](https://spot.wooribank.com/pot/Dream?withyou=POLON0102), with the related [Woori rate disclosure page](https://spot.wooribank.com/pot/jcc?PRD_CLF_DSCD=01&__ID=c012664&withyou=CQPNC0033). Keep the allowlist configurable. Confirm public access conditions before enabling either parser; if a source disallows retrieval or blocks it, stop and ask the owner before substituting a source.

The selected AWS topology adds three EC2 roles in the existing VPC: API+Alloy, MariaDB, and Loki+Prometheus+Grafana. Terraform inputs for region, VPC/subnets, existing project security groups, AMI, instance types, volume sizes, remote-state bucket, and image references remain deployment-time values; no account-specific values or secrets are committed.

## Order of Work

### Task 1: Establish the Python service and MariaDB persistence

**Files:**
- Create: `.python-version`, `pyproject.toml`, `uv.lock`, `.env.example`, `compose.yaml`
- Create: `src/podobank/__init__.py`, `src/podobank/config.py`, `src/podobank/db.py`, `src/podobank/schema.sql`
- Create: `tests/conftest.py`, `tests/test_storage.py`

**Interfaces:**
- Produces `Database(url: str)` with `transaction()` and repositories for accounts, catalog snapshots, idempotency records, events, and telemetry-outbox rows.
- Uses SQLAlchemy Core and a `mysql+pymysql` MariaDB URL. The local Compose database and CI service use MariaDB 11.4.

- [ ] **Step 1: Define project dependencies and local MariaDB service**

  Add Python 3.13, FastAPI, Uvicorn, SQLAlchemy, PyMySQL, Beautiful Soup, and Prometheus client dependencies; add pytest, HTTPX, Ruff, and mypy to the development group. Lock with uv. Add the local MariaDB service with a named data volume, health check, and credentials read from an ignored `.env` file.

  Run: `uv lock --check`

  Expected: the lockfile matches the project declaration.

- [ ] **Step 2: Write MariaDB storage tests first**

  In `tests/test_storage.py`, cover schema initialization, immutable event insertion, cursor ordering, event/outbox atomicity, and transaction rollback of both a balance update and its event/outbox rows. Use a real MariaDB service, not SQLite.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_storage.py -q`

  Expected: tests fail because the repository and schema have not been implemented.

- [ ] **Step 3: Implement the MariaDB transaction boundary**

  Add tables for customers, accounts, merchants, loans, payments, idempotency, product snapshots, events, catalog refresh state, and `telemetry_outbox`. Insert an outbox row in the same transaction as every business event; include attempt count, lease owner/expiry, and delivery timestamp fields. Use InnoDB transactions, foreign keys, integer won, UTC timestamps, and append-only event repository methods.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_storage.py -q`

  Expected: storage and rollback tests pass against MariaDB 11.4.

- [ ] **Step 4: Check, commit, and push the persistence foundation**

  Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src/podobank`

  Expected: source checks pass; commit and push with `agent-git` using the message `Add Podobank MariaDB foundation`.

### Task 2: Build API authentication, sandbox seed, and event reads

**Files:**
- Create: `src/podobank/main.py`, `src/podobank/auth.py`, `src/podobank/events.py`, `src/podobank/sandbox.py`
- Create: `src/podobank/routes/__init__.py`, `src/podobank/routes/sandbox.py`, `src/podobank/routes/events.py`
- Create: `tests/test_sandbox_api.py`, `tests/test_events_api.py`

**Interfaces:**
- Produces `create_app(database_url: str, settings: Settings) -> FastAPI` and `append_event(event_type, entity_refs, correlation_id, data) -> Event`; appending an event also enqueues its telemetry row in the same MariaDB transaction.
- Exposes `POST /v1/sandbox/seed` and `GET /v1/events` with partner-key authentication, filters, and cursor pagination.

- [ ] **Step 1: Write seed, event-envelope, auth, and pagination tests**

  Cover reusable synthetic seed data, rejected unauthenticated writes, secret exclusion, event schema version, filters, and high-water cursor traversal during concurrent appends.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_sandbox_api.py tests/test_events_api.py -q`

  Expected: tests fail because the app factory, routes, and event service are absent.

- [ ] **Step 2: Implement the API foundation**

  Add the FastAPI app factory, configured sandbox partner keys, synthetic seed operation, immutable event append/read methods, atomic event/outbox writes, and stable error responses. Encode a high-water event sequence in the first page cursor.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_sandbox_api.py tests/test_events_api.py -q`

  Expected: API contract and pagination tests pass.

- [ ] **Step 3: Commit and push the API foundation**

  Run: `agent-git add src/podobank tests && agent-git commit -m "Add Podobank API and event foundation" && agent-git push origin change/podobank-mvp`

  Expected: the feature branch advances on origin.

### Task 3: Implement ledger operations and reproducible scenarios

**Files:**
- Create: `src/podobank/ledger.py`, `src/podobank/scenarios.py`
- Create: `src/podobank/routes/accounts.py`, `src/podobank/routes/transfers.py`
- Create: `tests/test_ledger_api.py`, `tests/test_scenarios_api.py`
- Modify: `src/podobank/main.py`, `src/podobank/routes/__init__.py`, `src/podobank/routes/sandbox.py`

**Interfaces:**
- Produces `deposit(account_id: str, amount_won: int, key: str) -> OperationResult`, corresponding withdrawal and transfer operations, and `generate_scenario(name: str, count: int, seed: int) -> GeneratedScenario`.
- Exposes account reads, deposits, withdrawals, transfers, and `POST /v1/sandbox/generations`.

- [ ] **Step 1: Write ledger and scenario tests**

  Cover valid operations, insufficient funds, same-account transfer rejection, zero/negative/fractional amounts, idempotent replay, changed-payload conflict, concurrent debits, and fixed-seed business values.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_ledger_api.py tests/test_scenarios_api.py -q`

  Expected: tests fail until the ledger and scenario generator exist.

- [ ] **Step 2: Implement atomic MariaDB ledger operations**

  Lock affected account rows with `SELECT ... FOR UPDATE`; validate funds and update state, idempotency result, and events in one transaction. Rejections append `transaction.rejected` without changing balances. Generate synthetic activity without anomaly labels.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_ledger_api.py tests/test_scenarios_api.py -q`

  Expected: balance, event, idempotency, concurrency, and seed tests pass.

- [ ] **Step 3: Commit and push ledger and scenario generation**

  Run: `agent-git add src/podobank tests && agent-git commit -m "Add synthetic ledger and scenarios" && agent-git push origin change/podobank-mvp`

  Expected: the feature branch advances on origin.

### Task 4: Add official public loan-product snapshots

**Files:**
- Create: `src/podobank/catalog.py`, `src/podobank/catalog_refresh.py`, `src/podobank/source_adapters/__init__.py`, `src/podobank/source_adapters/hana.py`, `src/podobank/source_adapters/woori.py`
- Create: `src/podobank/routes/catalog.py`, `tests/test_catalog_api.py`, `tests/test_catalog_refresh.py`
- Create: `tests/fixtures/banks/hana.html`, `tests/fixtures/banks/woori.html`
- Modify: `src/podobank/main.py`, `src/podobank/routes/__init__.py`

**Interfaces:**
- Produces source parsers returning `ProductSnapshot`, `refresh_catalog() -> RefreshResult`, and current/historical snapshot reads.
- Exposes `GET /v1/loan-products`.

- [ ] **Step 1: Check source access and write fixture tests**

  Confirm public access conditions for the Hana and Woori pages. Use sanitized HTML fixtures to test normalized fields, missing values, rate ranges, source timestamps, product retirement, and failure preservation.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_catalog_api.py tests/test_catalog_refresh.py -q`

  Expected: tests fail because parsers and snapshot persistence are absent. If a source disallows retrieval, stop for owner direction rather than bypassing it.

- [ ] **Step 2: Implement bounded, versioned refresh**

  Add per-bank adapters, low-frequency requests, source URL and retrieval metadata, immutable snapshot IDs, weekly configurable refresh, and last-known snapshot retention. Use a MariaDB lease so concurrent API replicas cannot refresh the same catalog simultaneously. Missing terms remain unknown. Keep tests offline with fixtures and injected transport results.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_catalog_api.py tests/test_catalog_refresh.py -q`

  Expected: current and historical catalog tests pass without network access.

- [ ] **Step 3: Commit and push the catalog**

  Run: `agent-git add src/podobank tests && agent-git commit -m "Add public loan product snapshots" && agent-git push origin change/podobank-mvp`

  Expected: the feature branch advances on origin.

### Task 5: Implement recommendations and simulated loan outcomes

**Files:**
- Create: `src/podobank/recommendations.py`, `src/podobank/loans.py`, `src/podobank/routes/loans.py`, `tests/test_loan_api.py`
- Modify: `src/podobank/main.py`, `src/podobank/routes/__init__.py`, `src/podobank/schema.sql`

**Interfaces:**
- Produces `recommend(profile: RecommendationProfile, snapshot_id: str | None) -> RecommendationResult` and `create_simulated_loan(...) -> LoanResult`.
- Exposes `POST /v1/loan-recommendations` and `POST /v1/loans`.

- [ ] **Step 1: Write recommendation and loan tests**

  Cover known eligibility conflicts, unknown fields, amount/term bounds, deterministic tie-breaking, exact snapshot references, rejected applications, and atomic synthetic disbursement.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_loan_api.py -q`

  Expected: tests fail until the recommendation and loan services exist.

- [ ] **Step 2: Implement explainable matching and simulated loan lifecycle**

  Exclude products only for known conflicts; rank by explicit eligibility matches, published starting rate, then stable institution/product ID. Return match, unmet, and unknown criteria. Append recommendation and application outcome events; disbursement updates the synthetic account atomically.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_loan_api.py -q`

  Expected: the same profile and snapshot produce the same ranked response and event references.

- [ ] **Step 3: Commit and push loan features**

  Run: `agent-git add src/podobank tests && agent-git commit -m "Add synthetic loan recommendations" && agent-git push origin change/podobank-mvp`

  Expected: the feature branch advances on origin.

### Task 6: Implement partner bank-transfer payments

**Files:**
- Create: `src/podobank/payments.py`, `src/podobank/routes/payments.py`, `tests/test_payment_api.py`
- Modify: `src/podobank/main.py`, `src/podobank/routes/__init__.py`, `src/podobank/schema.sql`

**Interfaces:**
- Produces `create_payment(partner_id, merchant_id, payer_account_id, amount_won, partner_reference, idempotency_key) -> PaymentResult` and partner-scoped payment lookup.
- Exposes `POST /v1/payments` and `GET /v1/payments/{paymentId}`.

- [ ] **Step 1: Write payment-flow tests**

  Cover successful payer debit/merchant credit, insufficient-funds failure, unknown resources, partner-scoped reads, event ordering, shared correlation IDs, and idempotent retries.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_payment_api.py -q`

  Expected: tests fail because payment routes and state transitions are absent.

- [ ] **Step 2: Implement atomic simulated payment flow**

  Persist payment state, update only synthetic accounts, and append initiation plus completion or failure events in one MariaDB transaction. Do not call a payment gateway or bank.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_payment_api.py -q`

  Expected: balances, payment status, events, and retry behavior pass.

- [ ] **Step 3: Commit and push partner payments**

  Run: `agent-git add src/podobank tests && agent-git commit -m "Add sandbox partner payments" && agent-git push origin change/podobank-mvp`

  Expected: the feature branch advances on origin.

### Task 7: Add structured logs, metrics, and observability dashboards

**Files:**
- Create: `src/podobank/telemetry.py`, `tests/test_telemetry.py`, `tests/test_metrics_api.py`
- Create: `deploy/observability/alloy.alloy`, `deploy/observability/loki.yaml`, `deploy/observability/prometheus.yml`
- Create: `deploy/observability/grafana/provisioning/datasources.yml`, `deploy/observability/grafana/dashboards/podobank.json`
- Modify: `src/podobank/main.py`, route modules, `compose.yaml`

**Interfaces:**
- Produces structured JSON event logs containing stable event and correlation IDs, a private `/metrics` endpoint, and a health endpoint.
- A transactional outbox dispatcher emits each committed domain-event record as structured JSON to stdout and a shared NDJSON file. Alloy tails the file and forwards records to Loki. Prometheus scrapes the API metrics endpoint. Grafana is provisioned with Loki and Prometheus data sources and an operator dashboard.

- [ ] **Step 1: Write telemetry contract tests**

  Assert an outbox row is committed atomically with each event; assert the dispatcher emits event ID, correlation ID, outcome, and synthetic payload only after commit; assert delivery retries can duplicate but never lose records and secrets/record IDs are not metric labels; assert `/metrics` exposes request, operation, event, and catalog refresh metrics.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_telemetry.py tests/test_metrics_api.py -q`

  Expected: tests fail because structured logging and metrics are absent.

- [ ] **Step 2: Implement telemetry and local observability stack**

  Run an in-process leased outbox dispatcher: claim pending rows, emit one JSON record to stdout and the shared NDJSON file, then mark delivery complete. A crash between emission and marking may cause an at-least-once duplicate; preserve event IDs for downstream deduplication. Expose Prometheus metrics, configure Alloy file collection to Loki, and configure Grafana/Prometheus with persistent local volumes. Set Loki and Prometheus retention to 14 days; keep MariaDB as event source of truth.

  Run: `docker compose --env-file .env.example config --quiet`

  Expected: Compose configuration parses and all telemetry tests pass.

- [ ] **Step 3: Commit and push observability**

  Run: `agent-git add src/podobank tests compose.yaml deploy/observability && agent-git commit -m "Add Podobank observability pipeline" && agent-git push origin change/podobank-mvp`

  Expected: the feature branch advances on origin.

### Task 8: Package the AWS EC2 deployment, documentation, and quality gates

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `deploy/aws/api/compose.yaml`, `deploy/aws/database/compose.yaml`, `deploy/aws/observability/compose.yaml`, `deploy/verify-deployment.sh`
- Create: `infra/aws/main.tf`, `infra/aws/variables.tf`, `infra/aws/outputs.tf`, `infra/aws/versions.tf`, `infra/aws/backend.tf`, `infra/aws/backend.hcl.example`, `infra/aws/terraform.tfvars.example`
- Create: `tests/test_docs_api.py`
- Modify: `.gitignore`, `.env.example`, `README.md`, `checks.json`, `.github/workflows/repository.yml`

**Interfaces:**
- Terraform creates three new EC2 roles in supplied existing VPC subnets: API+Alloy, MariaDB, and Loki+Prometheus+Grafana. It creates only Podobank security groups, instance profiles, encrypted persistent data volumes, and a daily EBS snapshot policy retaining seven days; it does not create or modify the VPC, shared S3 state bucket, image registry, or existing instances.
- Inputs include AWS region, VPC/subnet IDs, bootcamp project security-group IDs, AMI, instance types, volume sizes, existing encrypted S3 state-bucket/key, private OCI image references, and SSM Parameter Store secret paths. API ingress on 8000 is limited to configured project security groups plus the observability security group for Prometheus scraping; MariaDB 3306 and Loki 3100 accept traffic only from the API security group. Grafana 3000 and Prometheus 9090 have no inbound rules and are accessed by SSM port forwarding. Instances use Systems Manager; no inbound SSH rule is added.
- The existing VPC must already provide outbound access to AWS Systems Manager endpoints, the configured image registry, and the allowlisted public bank pages. Terraform creates no NAT gateway, internet gateway, subnet, route, or endpoint.
- The API+Alloy EC2 role runs `deploy/aws/api/compose.yaml`, the MariaDB role runs `deploy/aws/database/compose.yaml`, and the observability role runs `deploy/aws/observability/compose.yaml`. Local development uses one `compose.yaml`. Runtime image tags and digests are pinned in deployment configuration. Nginx and frontend assets are not included.

- [ ] **Step 1: Write documentation and deployment contract tests**

  Assert `/docs`, `/openapi.json`, `/healthz`, and `/metrics` are described; README examples are synthetic; Terraform requires existing-VPC, remote-state, and private-image inputs; snapshot/log/metric retention is bounded; no public ingress is defined for MariaDB or telemetry administration.

  Run: `docker compose up -d mariadb && uv run pytest tests/test_docs_api.py -q`

  Expected: contract tests fail until documentation and deployment files are added.

- [ ] **Step 2: Add container definitions and AWS Terraform**

  Build the FastAPI image; define the three EC2 Compose roles; create Terraform resources for instances, scoped security groups, per-role SSM instance profiles, encrypted persistent EBS volumes with `delete_on_termination = false`, and daily EBS snapshots retained for seven days. Configure an S3 backend with native state locking using an owner-provided bucket; offline validation must use `terraform init -backend=false`. Read runtime secrets from narrowly scoped SSM Parameter Store `SecureString` paths; do not create secret values or place them in Terraform state, variables, user data, or logs. Ignore `.terraform/`, Terraform state, local backend files, and secret variable files. Do not include credentials or account-specific IDs.

  Run: `deploy/verify-deployment.sh`

  Expected: Terraform format/validation and all Compose configurations pass offline; no AWS `plan` or `apply` runs.

- [ ] **Step 3: Add operator and developer runbooks**

  Document local startup, API examples, event-vs-operational-log sources, catalog refresh, required AWS/VPC egress/state-bucket/image-registry inputs, SSM secret paths, role-specific Compose startup, private service ports, 14-day Loki/Prometheus retention, seven-day EBS snapshot retention, SSM access, and a manual deployment sequence. Explicitly state that Terraform validation does not create resources and that an AWS apply requires separate owner authorization.

  Run: `uv run pytest tests/test_docs_api.py -q`

  Expected: documentation and OpenAPI contract tests pass.

- [ ] **Step 4: Register product and deployment checks**

  Add a `product` group for pytest, Ruff lint, Ruff format-check, and mypy; add a `deployment` group for Terraform/Compose validation. Keep the generic control-plane check in `core`.

  Run: `python3 -m json.tool checks.json`

  Expected: valid registry JSON with paths routing source, tests, deployment files, and project metadata to the correct group.

- [ ] **Step 5: Add CI jobs and hand off the workflow push**

  Add `verify-product` with a MariaDB 11.4 service, Python 3.13, `astral-sh/setup-uv` v9.0.0 pinned to commit `c771a70e6277c0a99b617c7a806ffedaca235ff9`, uv 0.13.6, and `uv sync --locked`. Add `verify-deployment` with Terraform 1.14.5, `hashicorp/setup-terraform` v4.0.1 pinned to commit `dfe3c3f87815947d99a8997f908cb6525fc44e9e`, and `deploy/verify-deployment.sh`. Reuse the workflow's existing SHA-pinned checkout and setup-python actions. Upload group evidence and add both jobs to `summary.needs`.

  Run: `agent-git diff -- .github/workflows/repository.yml`

  Expected: the owner receives the exact workflow diff. Stop and wait for the owner to push it; do not push `.github/workflows/**` with the GitHub App. After the owner confirms, reconcile the branch with `agent-git` and require `python3 scripts/repo.py status --change podobank-mvp` to report no unwired groups.

- [ ] **Step 6: Run all product checks and full repository verification**

  Run: `uv sync --locked && docker compose up -d mariadb && uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src/podobank && deploy/verify-deployment.sh`

  Expected: all product and deployment checks pass. Then run `python3 scripts/repo.py verify --change podobank-mvp --full`; every registered check must pass in a complete run with evidence under `.evidence/`.

- [ ] **Step 7: Review, close, and open the PR**

  Review against `REVIEW.md`, confirm no credentials, database state, Terraform state, copied bank pages, caches, or unrelated changes are included, then replace root `intent.md` and `spec.md` with the accepted packet copies and rerun full verification.

  Run: `python3 scripts/repo.py close podobank-mvp --evidence <full-run-evidence-path>`

  Expected: current closure candidate. Commit and push via `agent-git`; open one English PR via `agent-gh` with `Change-ID: podobank-mvp`. Do not merge. Do not run Terraform apply or create AWS resources in this change without separate owner authorization.

## Tests and Proof

- Each service task has focused tests using a MariaDB 11.4 service; event and telemetry-outbox writes are atomic; dispatcher delivery is at least once with stable event IDs; all bank crawls use sanitized fixtures and injected responses, never live pages in automated tests.
- The `product` CI group runs pytest, Ruff lint, Ruff format-check, and mypy. The `deployment` group runs offline Terraform validation and Docker Compose config checks. The existing `core` group remains unchanged.
- Completion requires `python3 scripts/repo.py verify --change podobank-mvp --full`, current `repo.py status`, complete `.evidence/` output, and a `REVIEW.md` pass.
- The workflow change is an owner push handoff. Terraform validation is not a plan or apply and does not provision AWS resources.

## Risks and Mitigations

- **Bank pages change or block retrieval:** keep per-bank parsers and fixtures, retain snapshots, report freshness, and stop rather than bypassing access controls.
- **MariaDB transaction races:** lock account rows and test simultaneous debits and rollback.
- **Loki delivery lags or duplicates:** keep MariaDB authoritative, retry from the transactional outbox, and use event IDs for log deduplication.
- **AWS network and shared-service inputs are unknown:** parameterize the existing VPC/subnets and project security groups; require owner-provided egress, state bucket, image registry, AMI, and sizing before any AWS plan/apply. Create no network or cloud resources without separate owner authorization.
- **Stateful services can lose data if an instance is replaced:** attach encrypted EBS data volumes with deletion protection and document backup/restore steps.
- **Workflow policy:** stop at the exact workflow push gate and wait for the owner.

## Rollback or Recovery

- Before merge, change only this packet's scoped files in ordinary commits, preserve unrelated work, and rerun routed checks; do not reset or rewrite shared history.
- If a bank source fails, disable only that adapter while retaining product snapshots and business events; ask the owner before replacing the source.
- If an EC2 instance is replaced, reattach its preserved data volume and restore from the documented backup. Do not terminate or modify existing VPC instances.
- After merge, use a new repository change to restore or replace behavior; do not remove a frozen packet or revert its closure commit.

## Open Questions

- Before any AWS plan/apply, provide region, VPC/subnet IDs, project security-group IDs, approved AMI/instance types, data-volume sizes, existing encrypted S3 backend bucket/key, private image-registry references, and confirmation that existing VPC egress reaches SSM and the required public sources.
- Confirm the initial Hana/Woori source allowlist during public-access checks; pause if either source's published access conditions do not allow the planned retrieval.
- The plan sets Loki/Prometheus retention to 14 days and encrypted EBS snapshots to seven days; confirm these retention defaults before any AWS resource is provisioned.
