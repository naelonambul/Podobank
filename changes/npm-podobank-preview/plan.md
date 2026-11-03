# HTTPS Nginx Proxy Manager Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing PodoBank demo available at `https://podobank.oci-dev.duckdns.org` and `https://podobank-api.oci-dev.duckdns.org` through the server's Nginx Proxy Manager (NPM), with usable seeded customer and employee logins.

**Architecture:** Keep the default local Compose setup unchanged and add an opt-in overlay that joins only the API and frontend to NPM's existing external Docker network. NPM has two HTTPS Proxy Hosts with no Access Lists: the UI host forwards to Vue and the API host forwards directly to FastAPI. The preview frontend calls the API host as a separate origin. Both hosts are publicly reachable without NPM authentication; UI screens require app login, and FastAPI allows only the exact UI origin with credentials while user financial endpoints require app JWT sessions and DB roles. The API exposes unauthenticated routes such as `/health` and `/auth/login`, so it serves synthetic development data only. An explicit development-only command rotates only the fixed demo employee and customer password hashes; the existing idempotent demo seed command adds the 10,000-customer dataset without resetting the database.

**Tech Stack:** Docker Compose v2, Nginx Proxy Manager, Vue 3, FastAPI, MariaDB, SQLAlchemy Core.

**Spec:** `changes/npm-podobank-preview/spec.md`

## Global Constraints

- The UI URL is `https://podobank.oci-dev.duckdns.org`; the API URL is `https://podobank-api.oci-dev.duckdns.org`.
- NPM forwards the UI host to `podobank-frontend:80` and the API host to `podobank-api:8000`, both using HTTP upstreams. There is no `/api/` custom location or prefix rewrite.
- Preview `VITE_API_ORIGIN` and `API_ORIGIN` use the API URL; `FRONTEND_ORIGINS` uses only the UI origin. The Kakao callback URL, if configured, remains the UI callback route.
- Preview API cookies use `AUTH_COOKIE_SECURE=true` and remain HttpOnly and SameSite=Lax.
- Neither NPM host uses an Access List; both hosts are internet-reachable without proxy authentication. Exact-origin CORS limits browser JavaScript access but is not client authentication. The UI's customer/employee features require app login, and user financial endpoints require the app JWT session and DB role.
- Only the API and frontend join the existing NPM Docker network; MariaDB remains on the PodoBank default network.
- The default local Compose setup continues to call FastAPI directly and remains loopback-bound.
- Preview signing keys and application passwords are non-default local secrets and are not committed.
- `set-demo-credentials` is an explicit development-only command; it changes only the configured bank employee and fixed demo customer's password hashes and never runs at API startup.
- `seed-demo-data` is explicitly run, additive, idempotent, and restricted to the local development database; never reset or delete the existing database for this setup.

## Review Focus

- A missing or misspelled external network must fail the documented startup clearly; the Compose model check confirms its declared name, and the operator checks the live Docker network before startup.
- API losing its default network would break MariaDB access; the Compose configuration check asserts the API stays on both networks.
- MariaDB joining the NPM network would expose it to unrelated proxy containers; the Compose configuration check asserts that it stays off that network.
- The preview bundle retaining `http://localhost:8000` or using the UI URL as the API origin would fail for remote browsers; the Compose configuration check asserts the exact API HTTPS URL only in the preview overlay and preserves the local origin in the base configuration.
- Credential rotation targeting the wrong users or environment could lock out users or change live accounts; MariaDB tests assert the development-only guard, the two allowed account identities, no partial updates, and unchanged unrelated balances/passwords.
- Incorrect CORS origins or methods would block browser API calls; the live check sends a preflight from the UI origin and expects the exact allowed origin and credential headers from the API host.
- Adding NPM Basic Auth to either host would conflict with the approved public access design; the runbook keeps both hosts publicly accessible and verifies app login plus JWT/DB-role protection for user financial routes.

---

## Files and components that change

- `compose.npm-preview.yaml`: opt-in NPM network attachment and preview API origin.
- `.env.npm-preview.example`: safe template for preview interpolation values and app secrets.
- `.env.npm-preview.db.example`: DB-only environment template used by MariaDB's `env_file`.
- `scripts/verify_ui.py`: inspect both the unchanged local Compose model and merged preview model.
- `checks.json`: route the new overlay and env templates to the existing UI Compose configuration check.
- `backend/podobank_api/demo_credentials.py`: safely rotate the two fixed demo password hashes in one transaction.
- `backend/podobank_api/cli.py`: explicit `set-demo-credentials` command with development database and password guards.
- `backend/tests/test_database.py`: MariaDB regression coverage for target restriction, hash changes, and unchanged unrelated data.
- `docs/deployment/npm-preview.md`: secret setup, commands, two public NPM host/TLS settings, live checks, and rollback.
- `changes/npm-podobank-preview/spec.md`: approved remote preview contract.

## Order of work

### Task 1: Add the preview-only Compose overlay and environment templates

**Files:**
- Create: `compose.npm-preview.yaml`
- Create: `.env.npm-preview.example`
- Create: `.env.npm-preview.db.example`

**Interfaces:**
- The overlay network is named `npm-proxy` and points to the external network selected by `NPM_DOCKER_NETWORK`, defaulting to `nginx-proxy-manager`.
- API and frontend retain their `default` network and gain stable NPM aliases `podobank-api` and `podobank-frontend` on `npm-proxy`.
- The overlay sets the frontend build argument `VITE_API_ORIGIN=https://podobank-api.oci-dev.duckdns.org`; it does not change the base Compose file.
- The app env template sets `API_ORIGIN` to the API host, `FRONTEND_ORIGINS` to the UI origin, `KAKAO_REDIRECT_URI` to the UI callback route, the secure-cookie flag, non-default key/password placeholders, and the API database URL. The DB env template carries only MariaDB initialization values and must match the existing development database credentials when the existing volume is reused.

- [ ] **Step 1: Create the overlay and both env templates**

Use the network and service aliases above. Keep `db` off `npm-proxy`; do not publish any new host ports.

- [ ] **Step 2: Render the merged preview Compose model**

Run: `env COMPOSE_ENV_FILE=.env.npm-preview.db.example docker compose --env-file .env.npm-preview.example -f compose.yaml -f compose.npm-preview.yaml config --quiet`

Expected: exit status 0; no service attempts to read the default `.env` file.

### Task 2: Extend the existing UI Compose configuration check

**Files:**
- Modify: `scripts/verify_ui.py`
- Modify: `checks.json`

**Interfaces:**
- `verify_compose_config()` continues validating the current local model and additionally validates the model produced by merging `compose.npm-preview.yaml` and `.env.npm-preview.example`.
- Preview assertions cover the exact API HTTPS value for `VITE_API_ORIGIN`, API/frontend membership on `default` and `npm-proxy`, stable aliases, configured external network name, and MariaDB exclusion from `npm-proxy`.
- The existing `podobank-ui-compose` check is routed when any preview overlay or env example changes.

- [ ] **Step 1: Add assertions for the merged preview model**

Add assertions in `verify_compose_config()` with diagnostic errors for an absent network, unexpected frontend API origin, API losing its default network, or MariaDB joining the proxy network. Preserve the existing base-model assertions.

- [ ] **Step 2: Route preview config paths to the UI Compose check**

Add `compose.npm-preview.yaml`, `.env.npm-preview.example`, and `.env.npm-preview.db.example` to the `podobank-ui-compose` paths in `checks.json`.

- [ ] **Step 3: Run the configuration check**

Run: `python3 scripts/verify_ui.py --config-only`

Expected: `Compose UI configuration passed.` after it validates both models.

### Task 3: Add explicit safe rotation for demo credentials

**Files:**
- Create: `backend/podobank_api/demo_credentials.py`
- Modify: `backend/podobank_api/cli.py`
- Modify: `backend/tests/test_database.py`

**Interfaces:**
- Add `rotate_demo_credentials(connection, *, employee_phone, employee_password, demo_customer_password) -> None` in `demo_credentials.py`.
- The helper updates `password_hash` only for the configured `bank_employee` phone and the fixed `DEMO_CUSTOMER_PHONE` customer, after confirming both records exist with the expected roles. Hashes use the existing `hash_password()` function; values are never printed.
- Add `podobank-api set-demo-credentials`. It requires `APP_ENV=development`, the local `podobank_dev` database via `validate_demo_seed_target()`, both passwords meeting the existing minimum length, and neither known local default password. It applies both updates in one transaction and runs only when explicitly invoked.
- A failure for either account rolls back both updates. No balance, account, ledger, loan, or other user row changes.

- [ ] **Step 1: Write MariaDB tests for the new command**

Add tests in `backend/tests/test_database.py` proving that the command rejects unsafe targets and default passwords before connecting; updates only the configured employee and fixed demo customer hashes; leaves unrelated user hashes and account balances unchanged; and rolls back if either fixed account is missing or has the wrong role.

- [ ] **Step 2: Run the new credential tests to verify they fail**

Run: `python3 scripts/verify_backend.py --suite mariadb`

Expected: the new tests fail because `set-demo-credentials` and `rotate_demo_credentials()` are not implemented.

- [ ] **Step 3: Implement the guarded helper and CLI command**

Use bound SQL parameters and one caller-owned transaction. Keep the allowlist limited to `BANK_EMPLOYEE_PHONE` with role `bank_employee` and `DEMO_CUSTOMER_PHONE` with role `customer`.

- [ ] **Step 4: Run the backend suite**

Run: `python3 scripts/verify_backend.py --suite mariadb`

Expected: Ruff lint/format checks and all MariaDB backend tests pass.

### Task 4: Document the server preview configuration

**Files:**
- Modify: `docs/deployment/npm-preview.md`

**Interfaces:**
- The runbook uses the two ignored local env files and the approved Compose overlay.
- The explicit command order is `init-db`, `set-demo-credentials`, then `seed-demo-data`; `init-db` creates any missing default schema and sample records without resetting existing data, and the final command is additive and safely reports already-present data.
- The UI NPM Proxy Host uses `podobank-frontend:80` and has no NPM Access List.
- The API NPM Proxy Host uses `podobank-api:8000` and has no NPM Access List. It relies on HTTPS, exact UI-origin CORS, and app JWT/DB-role authentication for user financial routes; both hosts are publicly reachable and the API serves synthetic development data only.
- Both hosts use valid certificates and Force SSL. Neither host uses a custom location or path rewrite.

- [ ] **Step 1: Document prerequisites, safe env setup, and data commands**

Document DNS and Docker network checks, copying example env files without changing `.env`, replacing placeholders with strong values, matching existing DB credentials, and starting `api` and `frontend` with project name `podobank`. Show `init-db`, `set-demo-credentials`, and `seed-demo-data` as explicit commands and state that none runs during API startup. Explain that `init-db` adds missing schema/default records and does not reset existing data.

- [ ] **Step 2: Document NPM UI settings, verification, and rollback**

Record the exact two publicly accessible Proxy Host and TLS settings. State that neither host uses an NPM Access List, explain the app-auth/CORS boundary and public unauthenticated API routes, and keep NPM admin credentials out of chat and Git. Rollback first disables/removes both NPM hosts, then runs the base Compose file without deleting the database or any named volume.

### Task 5: Deploy the preview containers and configure NPM

**Files:**
- Runtime: existing PodoBank API and frontend Compose services.
- Runtime: existing development database's fixed demo account password hashes and additive sample dataset.
- Runtime: existing publicly accessible NPM UI and API Proxy Host configuration.

**Interfaces:**
- Compose project name is `podobank`; the existing MariaDB named volume and DB credentials are preserved.
- The explicit credential command changes only the seeded employee and fixed demo customer password hashes; `seed-demo-data` adds the 10,000-customer dataset and does not reset the database.
- If read-only checks show the default schema is incomplete, `podobank-api init-db` may be run first to create missing tables and default records. It is not a reset and preserves existing balances and non-null password hashes.
- NPM forwards the UI host to `podobank-frontend:80` and the API host to `podobank-api:8000` over the shared external network.
- Neither host uses an NPM Access List. UI customer/employee screens require app login; API user financial routes require a valid app JWT session and DB role. CORS allows only the UI origin in browsers and does not prevent non-browser clients from reaching either host.
- NPM admin credentials stay in the owner's session. If the NPM UI or DNS is unavailable, stop and report the required owner action; do not change the administrator account or edit NPM storage directly.

- [ ] **Step 1: Confirm DNS and the existing proxy network**

Run: `docker network inspect nginx-proxy-manager && getent ahosts podobank.oci-dev.duckdns.org podobank-api.oci-dev.duckdns.org`

Expected: the Docker network exists and both hostnames resolve to this server before requesting certificates. If either condition fails, stop before publishing the hosts.

- [ ] **Step 2: Start the API and frontend with the preview overlay**

Run: `env COMPOSE_ENV_FILE=.env.npm-preview.db docker compose --project-name podobank --env-file .env.npm-preview -f compose.yaml -f compose.npm-preview.yaml up -d --build api frontend`

Expected: API and frontend are healthy, attached to the NPM network, and MariaDB retains the existing named volume and data. The frontend bundle uses the API HTTPS hostname.

- [ ] **Step 3: Rotate demo credentials and seed the requested sample data**

Run: `env COMPOSE_ENV_FILE=.env.npm-preview.db docker compose --project-name podobank --env-file .env.npm-preview -f compose.yaml -f compose.npm-preview.yaml exec -T api podobank-api set-demo-credentials`, then run the same command with `seed-demo-data` as the final argument.

Expected: `init-db` adds any missing schema/default records while retaining existing data and non-null credential hashes; credential rotation reports success without passwords; the final command reports counts and adds 10,000 demo customers plus their sample records without deleting existing DB contents. Do not run `init-db` unless the approved plan includes this bootstrap step.

- [ ] **Step 4: Create both HTTPS hosts in NPM**

In the NPM UI, create both Proxy Hosts without Access Lists. Select `Publicly Accessible` for each host. Use HTTP upstreams, request/attach valid certificates, and enable Force SSL. Do not publish either host until both certificates are valid. Both hosts are internet-reachable; the API must contain only synthetic demo data.

- [ ] **Step 5: Check both HTTPS hosts, CORS, and logins**

Run: `curl -fsS https://podobank.oci-dev.duckdns.org/` and `curl -fsS https://podobank-api.oci-dev.duckdns.org/health`, without NPM credentials. Send an `OPTIONS` preflight to `https://podobank-api.oci-dev.duckdns.org/auth/login` with `Origin: https://podobank.oci-dev.duckdns.org`, requested method `POST`, and requested header `content-type`.

Expected: the UI host and API `/health` return HTTP 200 without NPM authentication, and the preflight response allows only the UI origin with credentials. In a browser, open `/accounts` without an NPM prompt, sign in with the demo customer credentials from the protected local env file, and verify customer data and account views render through the separate API host. The employee login uses the configured non-default password.

## Tests and proof

- `python3 scripts/verify_ui.py --config-only` validates local and preview Compose configuration.
- `python3 scripts/verify_backend.py --suite mariadb` validates credential rotation guards and backend behavior against the isolated test database.
- `python3 scripts/repo.py status --change npm-podobank-preview` reports the approved plan as current and implementation ready before tracked files outside the packet are changed.
- `python3 scripts/repo.py verify --change npm-podobank-preview --full` is the repository-required complete check before closure; preserve its evidence path.
- Live proof is HTTP 200 from both public hosts, a valid exact-origin credentialed CORS preflight, and a browser app login plus load of `/accounts` over HTTPS without an NPM prompt.

## Risks and mitigations

- The DuckDNS record or certificate may not exist yet; verify DNS before requesting the certificate and do not route the host until HTTPS is valid.
- Credential rotation is a DB write; it is explicit, restricted to `podobank_dev`, transactionally updates only the fixed employee/customer hashes, and does not alter balances or financial records.
- Seeding adds a sizable synthetic dataset; the existing command is explicit and idempotent. Do not run `reset-db`, reinitialize the database, or delete volumes.
- The agent does not have NPM administrator credentials. The runbook will make the required UI action exact; do not reset credentials or mutate NPM storage to bypass this.
- The existing DB volume must keep its current credentials and data. Reuse the existing project name and DB values.
- Both hosts are public by owner decision. Require non-default app secrets and passwords, keep the preview limited to synthetic development data, and rely on app JWT/DB-role checks for financial routes. Unauthenticated health and login routes remain internet-reachable.

## Rollback or recovery

Disable both NPM Proxy Hosts, then re-run the original local `compose.yaml` configuration without `compose.npm-preview.yaml`. The API and frontend return to their local direct-call settings. Preserve the existing MariaDB volume and the additive sample records; do not delete or recreate them as part of rollback. If credentials must be restored, use the previous secured local credential source, not a default value. If either certificate request fails, leave that host unpublished until DNS and TLS work.

## Open questions

- Do both `podobank.oci-dev.duckdns.org` and `podobank-api.oci-dev.duckdns.org` resolve to this server, and can the existing NPM administrator create two publicly accessible Proxy Hosts with valid certificates? These are live server prerequisites; no credential or DNS change is inferred from the selected hostnames.
