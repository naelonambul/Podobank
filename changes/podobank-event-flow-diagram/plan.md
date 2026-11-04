# PodoBank Event Flow Diagram Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task by task. Steps use checkbox syntax for tracking.

**Goal:** Make the operations manual's event-flow diagram show one MongoDB service/database with its two distinct event collections and accurately separated write paths.

**Architecture:** Update only the Mermaid flowchart in `docs/operations/observability-and-events.md`. Put plain `client_events` and `financial_events` collection nodes inside one `MongoDB · podobank_events` boundary. Keep browser ingestion, committed financial-event writes, and JSONL observability as separate flows.

**Tech Stack:** Markdown, GitHub Mermaid flowchart.

**Spec:** `changes/podobank-event-flow-diagram/design.md`

## Global Constraints

- There is one Compose MongoDB service named `mongo`, configured for the `podobank_events` database and persistent `mongodb_data` volume.
- Browser events use `POST /events` and are inserted into `client_events` by FastAPI.
- Successful financial API operations and state-changing repayment CLI operations are inserted into `financial_events` after their MariaDB commit, on a best-effort basis.
- JSONL observability is independent of MongoDB; Alloy reads JSONL, writes logs to Loki, exposes metrics scraped by Prometheus, and Grafana reads Loki and Prometheus.
- Change no application code, event schema, endpoint, collection, retention policy, guarantee, or service configuration.

## Review Focus

- **MongoDB instance count:** the Mermaid graph names MongoDB once and groups both collections under that single service/database boundary.
- **Collection identity:** `client_events` and `financial_events` remain separate and are labeled as collections, not database instances.
- **Browser event path:** Browser → `POST /events` → FastAPI → `client_events`; this path does not imply a MariaDB write.
- **Financial event path:** financial API and repayment CLI operations write to MariaDB; only after commit do they attempt one best-effort write to `financial_events`.
- **Observability path:** API/CLI JSONL events flow through Alloy to Loki and Prometheus; Grafana reads those two stores and has no MongoDB write edge.

---

## Files and components

- `docs/operations/observability-and-events.md`: replace the existing data-flow Mermaid block with the corrected single-MongoDB topology. Preserve the explanatory prose and collection table unless source verification identifies a factual error.
- `changes/podobank-event-flow-diagram/design.md`: approved representation and source facts.
- `changes/podobank-event-flow-diagram/closure.json`: candidate closure generated after complete verification.

## Order of work

### Task 1: Draw the shared MongoDB service and separate event flows

**Files:**
- Modify: `docs/operations/observability-and-events.md`

- [ ] Recheck the exact producer and storage facts in `compose.yaml`, `frontend/src/telemetry.js`, `backend/podobank_api/features/client_events/api.py`, `backend/podobank_api/features/client_events/mongodb.py`, `backend/podobank_api/features/financial_events/mongodb.py`, and the transaction/loan service callers. Confirm the single `mongo` service and `podobank_events` database.
- [ ] Replace only the Mermaid block under `## 데이터 흐름`. Render MongoDB once as a boundary labeled `MongoDB · podobank_events`; place two plain collection nodes inside it. Keep `Browser → POST /events → FastAPI → client_events` distinct from `FastAPI/repayment CLI → MariaDB commit → best-effort financial_events`. Keep the JSONL → Alloy → Loki/Prometheus → Grafana paths outside the MongoDB boundary.
- [ ] Run a focused source assertion that extracts the first Mermaid block and verifies one MongoDB label, both collection labels, the browser endpoint edge, the post-commit financial write labels, and the independent JSONL/Alloy/Loki/Prometheus/Grafana edges. Inspect the rendered diff with `agent-git diff -- docs/operations/observability-and-events.md`.
- [ ] Run `agent-git diff --check` and confirm `agent-git status --short` shows no changed product path except `docs/operations/observability-and-events.md` plus this packet.

### Task 2: Run full repository verification and close the packet

**Files:**
- Modify: `changes/podobank-event-flow-diagram/closure.json`

- [ ] Before MariaDB-backed verification, inspect the active Podobank Compose project and stop only its running API, frontend, database, and dedicated API tunnel services. Leave NPM, Jenkins, PostgreSQL, SonarQube, and other shared services running. Run the MariaDB checks against the disposable CI-equivalent `mariadb:12.3.3` test service bound to `127.0.0.1:3306`, with no data volume and the test SQL mode/credentials.
- [ ] Run `APP_ENV=test DATABASE_URL=mysql+pymysql://podobank:podobank-test@127.0.0.1:3306/podobank_test python3 scripts/repo.py verify --change podobank-event-flow-diagram --full`. Require every registered check to pass and record the evidence path.
- [ ] Stop and remove only the disposable test database, then restore only the Podobank services that were running before verification. Confirm the API health endpoint and frontend return successfully; do not change the shared services.
- [ ] Run `python3 scripts/repo.py status --change podobank-event-flow-diagram`, then `python3 scripts/repo.py close podobank-event-flow-diagram --evidence <full-evidence-path>`. Require `status: ok` and a current candidate closure.

## Tests and proof

- Focused Mermaid source assertions prove one MongoDB service/database label, two collection labels, and every intended event/observability path.
- `agent-git diff --check` passes.
- Full `repo.py verify --change podobank-event-flow-diagram --full` completes with all registered checks passing and no `not-run` checks.
- `repo.py status --change podobank-event-flow-diagram` reports `readiness=ready`, `closure=candidate`, and `status: ok`.
- The temporary MariaDB test service is removed and the previously running Podobank services are restored; shared services remain running.

## Risks and mitigations

- Mermaid subgraphs can still visually read as separate databases if both collection nodes use a database-cylinder shape. Use plain collection boxes inside the single MongoDB boundary and label only the outer service/database once.
- A shared FastAPI node serves both event paths. Keep edge labels explicit so the `POST /events` path is not confused with financial operations or MariaDB transactions.
- Full repository verification exercises database-backed checks. Stop the live Podobank components first, use only the disposable test database, and restore the prior Podobank state afterward.

## Rollback or recovery

- Before merge, restore only the original Mermaid block in `docs/operations/observability-and-events.md`, rerun full verification, and refresh the candidate closure.
- If a factual discrepancy appears during source review, stop and revise this plan before changing the prose or diagram; obtain fresh owner approval if the scope changes materially.

## Open questions

- None.
