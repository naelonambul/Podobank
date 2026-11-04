# Frontend Event Collection Implementation Plan

> **For implementation:** Use `superpowers:executing-plans` and execute the approved tasks in order in this isolated worktree. Backend and frontend share one event contract; use one implementer and a final independent review.

**Goal:** Automatically collect successful frontend navigations and offer a common trackEvent function, with validated POST /events storage in MongoDB.

**Architecture:** A frontend telemetry module owns identifiers, sanitized event envelopes, and nonblocking transmission. One router hook emits page_view. A separate backend client_events feature validates bounded requests and writes directly to its own MongoDB collection without MariaDB or financial-event dependencies.

**Tech Stack:** Existing Vue Router, browser Fetch/Storage/Crypto, FastAPI/Pydantic, PyMongo, unittest, Playwright. No dependencies or deployment changes.

**Spec:** `changes/podobank-client-events/spec.md` (approved digest `b51846559a1a6da9cfe6aa3ff5752414e0ee6da5222d90fb2e6de2eda88faba0`).

## Global Constraints

- Preserve the approved schema_version 4 envelope, anonymous identifiers, URL sanitation, and absence of automatically captured profile/financial/form data.
- Only successful page transitions emit page_view; callback query strings, failed transitions and intermediate guard redirects must not leak events.
- Single JSON request <=32 KiB; props <=8 KiB, depth <=4, <=64 keys; page fields <=2048 characters; only the specified type pattern, UUIDs, UTC timestamps, and version 4 pass validation.
- Anonymous POST /events: 201 stored, 200 duplicate without overwrite, 413 oversized, 422 invalid, 503 events_unavailable on missing configuration or MongoDB failure.
- MongoDB client_events uses event_id as _id and adds received_at. Lazy connection, <=2 second operation deadline, shutdown cleanup. Financial events and MariaDB remain independent.
- Frontend failure is swallowed without auth redirects, banners, navigation delay or retries. Blocked Storage falls back to stable in-memory IDs.
- No queues, automatic expiration, new services, dependency changes, workflow edits, public port changes or production deployment.
- Stop only existing Podobank API/frontend before application verification. Preserve the existing DB, shared containers, configurations, and volumes; clean only this run's isolated stacks. Restore prior API/frontend running state afterward.
- Keep the original checkout's pre-existing .codex/config.toml untouched. Only packet files may change before plan approval and readiness=ready.

## Review Focus

- Forged/malformed or oversized requests, including chunked bodies without Content-Length, must be bounded before JSON parsing; no payload values should enter logs/errors.
- Duplicate UUID with different props must preserve the first document. Arbitrary MongoDB insertion errors must not be mistaken for duplicate success.
- Storage denial, network errors and MongoDB outage must leave browser navigation and existing financial APIs functional.
- Auth redirects, callback queries, reload/back navigation and anonymous IDs must not create duplicate intermediate events or leak credentials in URLs.
- Concurrent event writes and application shutdown must not leak Mongo clients or block the event loop; financial writer lifecycle remains intact.

### Task 1: Implement the validated event ingestion feature

**Files:** Create `backend/podobank_api/features/client_events/{__init__,schemas,mongodb,api}.py`, `backend/tests/test_client_events.py`; modify `backend/podobank_api/app.py`.

**Interfaces:**
- `ClientEvent` Pydantic request model: exactly the approved fields, strict primitive/JSON types, finite JSON numbers, UTC aware timestamp, bounded type/page/props. Page normalization strips query and fragment. Reject undeclared envelope/page fields.
- `store_event(event: ClientEvent) -> Literal['stored', 'duplicate']` creates a validated document and received_at, then one acknowledged insert to client_events. Catch only DuplicateKeyError as duplicate. Other Mongo errors/configuration gaps become a safe EventsUnavailable exception.
- `close_client_event_clients()` closes the feature's cached clients under a lock. Do not import financial_events private client state or restructure the existing writer.
- POST /events reads request.stream() with an accumulated 32 KiB cap (check declared length as an early optimization, never sole enforcement). Parse bounded JSON, validate, and call the synchronous writer through the framework thread pool. Return only status/error code, not raw exceptions or the submitted payload.
- app.py registers the router and closes the new feature clients alongside existing financial clients during lifespan shutdown.

- [ ] Add meaningful tests for valid envelope, strict version/type/UUID/time validation, unknown fields, malformed JSON, page query/fragment sanitation, nested props/key/byte limits, body bounds with and without Content-Length, anonymous access, duplicate/conflicting duplicate preservation, safe 503 mapping, missing configuration, lazy startup and shutdown cleanup. Stub Mongo at the feature boundary for deterministic API failure cases; real persistence is Task 3.
- [ ] Run `python3 scripts/repo.py verify --change podobank-client-events --group mariadb`; confirm new endpoint tests fail because /events is absent, preserving evidence. Supply APP_ENV=test and the isolated podobank_test URL without printing secrets; never use podobank_dev for backend tests.
- [ ] Implement the schemas, bounded ingestion, Mongo writer and app wiring above. Keep all errors privacy-safe and financial writer code unchanged.
- [ ] Rerun the same MariaDB group. Expected: all selected checks pass; outside groups are explicitly partial, not completion evidence.

### Task 2: Collect router navigations and expose trackEvent

**Files:** Create `frontend/src/telemetry.js`, `frontend/e2e/client-events.spec.js`; modify `frontend/src/router.js`.

**Interfaces:**
- `trackEvent(type, props = {})` builds the approved envelope for the current sanitized page context and sends a one-shot keepalive Fetch JSON POST to `${VITE_API_ORIGIN}/events` using the same default API origin as api.js. Do not use the financial API unauthorized handler. Swallow storage/network/response errors, contain synchronous errors, and never await transmission from navigation.
- The module owns event UUID generation, stable localStorage anonymous ID, sessionStorage tab ID and memory fallback. Validate pre-existing stored IDs before reuse. No cookies or login user identifiers.
- `trackPageView(to, from)` updates sanitized page context/referrer and calls trackEvent('page_view', {route_name}). One afterEach hook calls it only when no navigation failure exists. Route query/hash changes do not expose their values; successful navigations follow the spec, not additional click instrumentation.
- referrer keeps only HTTP(S) origin/path or empty; no userinfo, query, fragment, form data or raw errors. Bound outgoing properties to avoid sending known-invalid oversized payloads.

- [ ] Write browser tests proving initial/page/back page_view delivery, guard redirect final destination only, envelope/UUID/version correctness, ID stability/reload and tab-session behavior, callback query stripping, sanitized previous referrer, blocked Storage fallback, and rejected/network-failing /events not disrupting UI. Drive real routes and inspect outbound requests; mock external OAuth/session only where the tested flow needs it. Exercise common custom event emission through the real module without production test-only hooks.
- [ ] Run `python3 scripts/repo.py verify --change podobank-client-events --group frontend`. Expected: event assertions fail while baseline UI remains useful for regression diagnosis.
- [ ] Implement telemetry module and router hook, with no view edits or semantic financial event calls.
- [ ] Rerun frontend group. Expected: quality, Compose boundaries, existing UI flows and new event behavior pass.

### Task 3: Prove real persistence and complete the change

**Files:** Modify `scripts/verify_mongodb_events.py`, `checks.json`; replace root `spec.md` with the accepted packet spec; generate packet `closure.json` with repo.py.

- [ ] Extend the existing isolated MongoDB smoke script: before its Mongo outage stage POST one anonymous schema-v4 event, assert 201, repeat with same ID/different props and assert 200, query client_events with mongosh and assert exactly one sanitized original document and server received_at. After Mongo stops, assert /events returns safe 503 within the timeout budget while /health and the existing deposit flow still succeed. Restart Mongo, assert the failed event was not replayed. Preserve all existing financial-event assertions and cleanup.
- [ ] Extend only the existing podobank-mongodb-events check's paths with app.py, client_events/** and test_client_events.py, so the new backend feature routes to real persistence verification. Reuse current group/toolchains; no workflow edits or weakened checks.
- [ ] Run `python3 scripts/repo.py verify --change podobank-client-events --group mariadb`. Expected: real ingestion, uniqueness and outage checks pass along with backend and existing observability checks. Inspect assertions rather than accepting helper exit codes alone.
- [ ] Review the diff against REVIEW.md, approved spec/plan and write scope. Obtain the final independent review required by executing-plans, fix Important findings, and keep a record of any deferred minor findings. No new scope or material departure without fresh approval.
- [ ] Copy the accepted packet spec into root spec.md, then run `python3 scripts/repo.py verify --change podobank-client-events --full` with API/frontend stopped and the isolated test database environment. Expected: all registered checks passed, complete=true, no failed/blocked/not-run. Do not repeat complete runs absent changed source, failures or unresolved concerns.
- [ ] Run `python3 scripts/repo.py close podobank-client-events --evidence <full-evidence.json>` and `python3 scripts/repo.py status --change podobank-client-events`. Expected: readiness=ready and current closure=candidate. Refresh verification and closure after any later source edit.
- [ ] Restore only the previously running Podobank API/frontend containers. Confirm healthy API and unchanged shared services. This restores the existing images; deployment of the new feature is a separate operation.
- [ ] Commit the approved closed change as mini26-agent[bot] via agent-git, push with agent-gh push, open one PR with Change-ID: podobank-client-events, include evidence and review limitations, and leave review/merge to the owner.

## Recovery

Keep fixes inside approved scope and preserve failing evidence. Never reset shared work, erase DB data, delete original files, or modify deployment/secrets to make checks pass. If design or scope changes materially, revise the plan and request a new approval. Failed ingestion has no durable queue; MongoDB outages can lose frontend events by design.
