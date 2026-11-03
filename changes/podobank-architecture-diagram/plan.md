# PodoBank Current Architecture Diagram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one interactive, self-contained HTML diagram that explains the current PodoBank preview, data stores, event recording, and observability paths.

**Architecture:** Use a single standalone HTML document with inline semantic HTML, CSS, SVG, and small JavaScript controls. Draw separate public-edge, OCI Compose, financial-data, and observability boundaries; draw the browser-to-API Worker call as a browser request, not an internal frontend proxy. AWS material informs the visual grouping only; it does not describe a proposed AWS deployment.

**Tech Stack:** HTML, CSS, inline SVG, vanilla JavaScript; no added packages, downloaded icons, or external runtime assets.

**Spec:** `changes/podobank-architecture-diagram/design.md`

## Global Constraints

- Public UI: `https://podobank.i234.workers.dev`; public API: `https://podobank-api.i234.workers.dev`.
- Existing VPC Service/Tunnel paths terminate at OCI HTTP loopback `127.0.0.1:8081` (frontend) and `127.0.0.1:8000` (API).
- Preserve API root paths such as `/health`, `/auth/login`, and `/accounts/me`; show no `/api` prefix or URI rewrite.
- MariaDB is the structured financial source of truth. MongoDB receives successful API event documents by a direct best-effort API write after the MariaDB commit; there is no outbox, relay, retry, or replay.
- JSONL events flow separately through Alloy to Loki and Prometheus; Grafana reads those observability stores.
- MariaDB publishes `127.0.0.1:${DB_PORT:-3306}:3306`, which is host-loopback-only and not a public binding. MongoDB, Loki, Prometheus, and Alloy have no host-published ports. Grafana is bound to host loopback only.
- Mark the app as a synthetic-data development preview, not a production banking system.
- Keep the artifact self-contained and do not alter runtime configuration or services.

## Review Focus

- Browser API requests must go from the Vue app in the browser to the API Worker with credentials, not through the frontend container.
- MongoDB must appear after a successful MariaDB commit, with best-effort/loss possible called out.
- The JSONL observability path must remain distinct from the MongoDB event path.
- Keep the diagram scoped to PodoBank; omit NPM, Jenkins, and unrelated shared-host context.
- Distinguish the loopback-published MariaDB port from MongoDB and monitoring ports that are not host-published.
- Flow labels must remain visible outside node cards and not collide with labels for other paths.

---

### Task 1: Create the interactive system diagram

**Files:**
- Create: `docs/architecture/podobank-current-architecture.html`
- Reference: `compose.yaml`
- Reference: `compose.npm-preview.yaml`
- Reference: `docs/deployment/npm-preview.md`
- Reference: `backend/podobank_api/features/financial_events/mongodb.py`
- Reference: `monitoring/alloy/config.alloy`
- Reference: `monitoring/prometheus/prometheus.yml`
- Reference: `README.md`

**Interfaces:**
- The HTML file is the complete deliverable and opens directly from disk or the repository browser; it has no build step or external runtime dependency.
- Three path controls show or dim request traffic, financial data/events, and observability. All diagram paths are visible by default.
- Pointer selection or keyboard focus/activation exposes a short explanation and, where useful, its source-config path in the details panel below the map.

- [ ] **Step 1: Build the page and architecture map in the single HTML file.**

  Group the browser and Cloudflare Workers outside an OCI host boundary. Draw UI delivery through the existing Worker VPC Service/Tunnel to host loopback `:8081` and the Nginx frontend. Draw Vue's credentialed browser requests to the separate API Worker and onward through its VPC Service/Tunnel to host loopback `:8000` and FastAPI. Label the API's existing root routes and exact CORS origin.

  Expand the OCI/Compose boundary into the space previously reserved for unrelated shared-host services; omit NPM, Jenkins, and other shared-host nodes. Show API-to-MariaDB transactional writes; successful commit followed by one best-effort MongoDB event insert; and the independent JSONL → Alloy → Loki and Alloy metrics → Prometheus paths. Place Prometheus and Grafana at the right end of the expanded Compose area, with Grafana furthest right. Draw dashboard query data flowing from Loki and Prometheus into Grafana, and state that Grafana displays results without writing logs or metrics. Show named volumes, MariaDB's `127.0.0.1:${DB_PORT:-3306}:3306` host-loopback mapping, Grafana's host-loopback mapping, and which other service ports are not host-published.

  Add controls for the three path groups, native hover titles, and service-node pointer selection plus keyboard focus/activation that updates the details panel below the map. Keep flow labels outside node cards and separate labels for distinct monitoring edges. Add an always-visible legend, responsive horizontal scrolling for the expanded map, and keyboard-visible focus styles. Use inline SVG glyphs and labels rather than AWS product icons. Add a compact research note linking the AWS icon guidance and the January 2026 AWS payment event architecture reference, explicitly saying they are visual references only.

- [ ] **Step 2: Review the diagram against the source configuration and this design.**

  Check every URL, route, port binding, database/event relationship, and monitoring edge against the listed reference files. Confirm controls work with keyboard and pointer, focus updates component details, all paths are visible by default, monitoring arrows point toward their data sinks and Grafana, the shared-host group is absent, and arrow labels do not overlap nodes or each other. Correct any discrepancy in the HTML.

- [ ] **Step 3: Check the change packet state.**

  Run: `python3 scripts/repo.py status --change podobank-architecture-diagram`

  Expected: `status: ok`, the approved plan remains current, and all implementation changes are within the declared scope.

## Tests and proof

This is a documentation-only artifact; it adds no application code or automated test. The source-by-source diagram review in Task 1 is the content proof. Repository-wide `repo.py verify --change podobank-architecture-diagram --full` remains the repository's required pre-closure check and is not run as part of this plan without an explicit request to run checks.

## Risks and mitigations

- A diagram that conflates the two event sinks could imply MongoDB is loss-proof or feeds Loki; draw and label the paths independently.
- Dashboard query requests originate at Grafana, while query results are displayed there; label and direct arrows to make clear that Grafana consumes results and does not write logs or metrics.
- AWS icon assets would misidentify the actual providers; use provider labels and simple local glyphs instead.
- Browser-width SVG text may become unreadable; place the map in a horizontal scroll container and keep controls/legend responsive.

## Rollback or recovery

Delete `docs/architecture/podobank-current-architecture.html` and close the change with the applicable repository lifecycle. No deployment, container, database, secret, or service state is touched.

## Open questions

None. The user allowed either interactive HTML or ASCII, and the agent selected interactive HTML for path exploration and readability.
