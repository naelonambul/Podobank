# HTTPS Nginx Proxy Manager Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing PodoBank demo available at `https://podobank.oci-dev.duckdns.org` through the server's Nginx Proxy Manager (NPM).

**Architecture:** Keep the default local Compose setup unchanged and add an opt-in overlay that joins only the API and frontend to NPM's existing external Docker network. In that preview build, the browser calls `/api`; NPM removes that prefix and forwards the request to FastAPI while serving all other routes from the Vue container.

**Tech Stack:** Docker Compose v2, Nginx Proxy Manager, Vue 3, FastAPI, MariaDB.

**Spec:** `changes/npm-podobank-preview/spec.md`

## Global Constraints

- The preview URL is `https://podobank.oci-dev.duckdns.org`.
- NPM forwards `/api/` to FastAPI after removing the `/api/` prefix and sends other routes to the frontend.
- Preview API cookies use `AUTH_COOKIE_SECURE=true` and remain HttpOnly and SameSite=Lax.
- NPM Access List authentication is enabled for the preview host.
- Only the API and frontend join the existing NPM Docker network; MariaDB remains on the PodoBank default network.
- The default local Compose setup continues to call FastAPI directly and remains loopback-bound.
- Preview signing keys and application passwords are non-default local secrets and are not committed.

## Review Focus

- A missing or misspelled external network must fail the documented startup clearly; the Compose model check confirms its declared name, and the operator checks the live Docker network before startup.
- API losing its default network would break MariaDB access; the Compose configuration check asserts the API stays on both networks.
- MariaDB joining the NPM network would expose it to unrelated proxy containers; the Compose configuration check asserts that it stays off that network.
- The preview bundle retaining `http://localhost:8000` would fail for remote browsers; the Compose configuration check asserts `VITE_API_ORIGIN=/api` only in the preview overlay and preserves the local origin in the base configuration.
- A path-prefix mismatch would return frontend HTML or a 404 for API requests; the live check requests `/api/health` through NPM and expects the API health response.

---

## Files and components that change

- `compose.npm-preview.yaml`: opt-in NPM network attachment and preview API base.
- `.env.npm-preview.example`: safe template for preview interpolation values and app secrets.
- `.env.npm-preview.db.example`: DB-only environment template used by the MariaDB `env_file` so app signing and login secrets are not passed to MariaDB.
- `scripts/verify_ui.py`: inspect both the unchanged local Compose model and merged preview model.
- `checks.json`: route the new overlay and env templates to the existing UI Compose configuration check.
- `docs/deployment/npm-preview.md`: secret setup, Compose command, NPM host/custom-location/TLS/Access List settings, live checks, and rollback.
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
- The overlay sets the frontend build argument `VITE_API_ORIGIN=/api`; it does not change the base Compose file.
- The app env template sets the preview HTTPS origin, secure-cookie flag, non-default key/password placeholders, and the API database URL. The DB env template carries only MariaDB initialization values and must match the existing development database credentials when the existing volume is reused.

- [ ] **Step 1: Create the overlay and both env templates**

Use the network and service aliases above. Keep `db` off `npm-proxy`; do not publish any new host ports.

- [ ] **Step 2: Render the merged preview Compose model**

Run: `COMPOSE_ENV_FILE=.env.npm-preview.db.example docker compose --env-file .env.npm-preview.example -f compose.yaml -f compose.npm-preview.yaml config --quiet`

Expected: exit status 0; no service attempts to read the default `.env` file.

### Task 2: Extend the existing UI Compose configuration check

**Files:**
- Modify: `scripts/verify_ui.py`
- Modify: `checks.json`

**Interfaces:**
- `verify_compose_config()` continues validating the current local model and additionally validates the model produced by merging `compose.npm-preview.yaml`.
- Preview assertions cover `VITE_API_ORIGIN=/api`, API/frontend membership on `default` and `npm-proxy`, stable aliases, external network name, and MariaDB exclusion from `npm-proxy`.
- The existing `podobank-ui-compose` check is routed when any preview overlay or env example changes.

- [ ] **Step 1: Add assertions for the merged preview model**

Add assertions in `verify_compose_config()` with diagnostic errors for an absent network, unexpected frontend API base, API losing its default network, or MariaDB joining the proxy network. Preserve the existing base-model assertions.

- [ ] **Step 2: Route preview config paths to the UI Compose check**

Add `compose.npm-preview.yaml`, `.env.npm-preview.example`, and `.env.npm-preview.db.example` to the `podobank-ui-compose` paths in `checks.json`.

- [ ] **Step 3: Run the configuration check**

Run: `python3 scripts/verify_ui.py --config-only`

Expected: `Compose UI configuration passed.` after it validates both models.

### Task 3: Document the server preview configuration

**Files:**
- Create: `docs/deployment/npm-preview.md`

**Interfaces:**
- The runbook uses the two ignored local env files and the approved Compose overlay.
- The NPM Proxy Host uses `podobank-frontend:80`; its `/api/` Custom Location uses `podobank-api:8000` with forward path `/`.
- The host uses an NPM Access List, a valid certificate for `podobank.oci-dev.duckdns.org`, and Force SSL.

- [ ] **Step 1: Document prerequisites and safe startup**

Document the DNS record and existing Docker network checks, copying example env files without changing the pre-existing `.env`, replacing all placeholders with strong values, matching DB credentials to the existing DB when reusing its volume, and starting only `api` and `frontend` with project name `podobank` and the preview overlay. State that Kakao OAuth needs separate provider credentials; the seeded local demo login is the preview path otherwise, and its password is shared outside Git.

- [ ] **Step 2: Document the NPM UI settings and rollback**

Record the exact Proxy Host, Custom Location, TLS, and Access List fields. Explain that NPM admin credentials stay out of chat and Git. Rollback first disables/removes the NPM host, then runs the base Compose file without deleting the database or any named volume.

### Task 4: Deploy the preview containers and configure NPM

**Files:**
- Runtime: existing PodoBank API and frontend Compose services.
- Runtime: existing NPM Proxy Host and Access List configuration.

**Interfaces:**
- Compose project name is `podobank`; the existing MariaDB named volume and DB credentials are preserved.
- NPM forwards to `podobank-frontend:80` and `podobank-api:8000` over the shared external network.
- NPM admin credentials stay in the owner's session. If the NPM UI or DNS is unavailable, stop and report the required owner action; do not change the administrator account or edit NPM storage directly.

- [ ] **Step 1: Confirm DNS and the existing proxy network**

Run: `docker network inspect nginx-proxy-manager` and `getent ahosts podobank.oci-dev.duckdns.org`

Expected: the Docker network exists and the chosen hostname resolves to this server before requesting a certificate. If either condition fails, stop before publishing the host.

- [ ] **Step 2: Start the API and frontend with the preview overlay**

Run: `COMPOSE_ENV_FILE=.env.npm-preview.db docker compose --project-name podobank --env-file .env.npm-preview -f compose.yaml -f compose.npm-preview.yaml up -d --build api frontend`

Expected: API and frontend are healthy, attached to the NPM network, and MariaDB retains the existing named volume and data.

- [ ] **Step 3: Create the protected HTTPS host in NPM**

In the NPM UI, create the Proxy Host and `/api/` Custom Location from Task 3, attach the Access List, request/attach a valid certificate, and enable Force SSL. Do not make the host public until HTTPS and authentication are active.

- [ ] **Step 4: Check the protected HTTPS routes**

Run: `curl -fsS --user "$NPM_ACCESS_USER" https://podobank.oci-dev.duckdns.org/api/health`

Expected: HTTP 200 with the FastAPI health response after the interactive Basic Auth password prompt. Also open a client-side route such as `/accounts` in a browser and confirm it renders the Vue application after NPM authentication.

## Tests and proof

- `python3 scripts/verify_ui.py --config-only` validates local and preview Compose configuration.
- `python3 scripts/repo.py status --change npm-podobank-preview` reports the approved plan as current and implementation ready before tracked files outside the packet are changed.
- `python3 scripts/repo.py verify --change npm-podobank-preview --full` is the repository-required complete check before closure; preserve its evidence path.
- Live proof is an authenticated HTTP 200 from `/api/health` through NPM plus a browser load of `/accounts` over HTTPS.

## Risks and mitigations

- The DuckDNS record or certificate may not exist yet; verify DNS before requesting the certificate and do not route the host until HTTPS is valid.
- The agent does not have NPM administrator credentials. The runbook will make the required UI action exact; do not reset credentials or mutate NPM storage to bypass this.
- The existing DB volume must keep its current credentials and data. Reuse the existing project name and DB values; do not run initialization or sample-data reset commands.
- Application defaults are unsafe for a public demo; require non-default app secrets plus NPM Access List authentication.

## Rollback or recovery

Disable the NPM Proxy Host and Custom Location, then re-run the original local `compose.yaml` configuration without `compose.npm-preview.yaml`. The API and frontend return to their local direct-call settings. Preserve the existing MariaDB volume and do not delete or recreate it. If the certificate request fails, leave the host unpublished until DNS and TLS work.

## Open questions

- Does `podobank.oci-dev.duckdns.org` resolve to this server, and can the existing NPM administrator add a Proxy Host and Access List? These are live server prerequisites; no credential or DNS change is inferred from the selected hostname.
