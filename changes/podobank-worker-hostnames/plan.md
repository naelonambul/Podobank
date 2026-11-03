# Implementation Plan

## Summary

Replace the remote preview's DuckDNS/NPM URLs with the already deployed Cloudflare Worker hostnames. Keep the two existing public origins and FastAPI paths unchanged: the UI Worker targets OCI HTTP `127.0.0.1:8081`, and the API Worker targets OCI HTTP `127.0.0.1:8000` through the existing Tunnel VPC Services. Do not edit Worker code, add `/api`, add a path rewrite, or change NPM, DB, volumes, or shared services. Update only the three requested URL values in the ignored runtime `.env.npm-preview`; preserve every other byte and file mode `0600`. Rebuild only `api` and `frontend` after the packet is ready.

## Files and components that change

- `changes/podobank-worker-hostnames/spec.md`: carry the approved Workers-based remote preview architecture and acceptance criteria into the product baseline when the change closes.
- `compose.npm-preview.yaml`: set the frontend image's `VITE_API_ORIGIN` to `https://podobank-api.i234.workers.dev`. Keep the existing external NPM network attachment and all host port mappings unchanged.
- `.env.npm-preview.example`: set `API_ORIGIN`, `FRONTEND_ORIGINS`, and `KAKAO_REDIRECT_URI` to the API Worker, UI Worker, and UI callback URLs. Keep `APP_ENV=development` and both Kakao placeholders unchanged.
- `scripts/verify_ui.py`: update the preview configuration oracle to require the two Worker origins while retaining loopback-only host ports, existing NPM network membership, and DB network isolation assertions.
- `docs/deployment/npm-preview.md`: replace NPM/DuckDNS routing instructions with the existing Workers/VPC route, limited Compose rebuild, health/CORS checks, and rollback steps. Document that the NPM service and shared containers remain untouched.
- The ignored runtime `.env.npm-preview` is not committed. Before editing it, confirm which Compose project uses it, re-check its ignore rule and file mode, then update only the same three URL keys without printing or diffing any secret values. The file was absent from the requested change worktree and primary checkout when this plan was drafted; it was found in the existing `npm-podobank-preview` worktree, where `.gitignore:23` ignores it and its mode is `0600`. Do not create a substitute if that is not the active deployment file.

## Order of work

1. After `readiness=ready`, edit `compose.npm-preview.yaml`, `.env.npm-preview.example`, and `scripts/verify_ui.py`. Set the frontend build API origin and expected preview origins to the approved Worker URLs. Preserve `127.0.0.1` host bindings, the external NPM network, NPM aliases, and DB isolation assertions. Preserve `APP_ENV=development` and Kakao placeholders in the example file. Prove the merged local and preview Compose models and expected Worker origins with `python3 scripts/verify_ui.py --config-only`.
2. Rewrite `docs/deployment/npm-preview.md` for the already deployed Worker/VPC routing. State the exact public URLs and internal loopback ports; retain existing root API paths; provide commands that validate configuration, rebuild only API/frontend with `--no-deps`, and check UI, API health, CORS preflight, and browser login. Include rollback to the previous DuckDNS URLs without stopping or recreating NPM, DB, observability, or other shared services. Review that no NPM admin or Cloudflare credentials are documented.
3. Locate the runtime Compose project and confirm it consumes the existing ignored `.env.npm-preview`. Re-run `agent-git status --short --ignored -- .env.npm-preview`, `agent-git check-ignore -v -- .env.npm-preview`, and `stat` on that exact path. Use a line-preserving edit that changes only `API_ORIGIN`, `FRONTEND_ORIGINS`, and `KAKAO_REDIRECT_URI`; keep all other bytes and mode `0600`. Verify those three keys and mode with a quiet assertion that emits no file contents. If the active file cannot be identified or is unavailable, stop before runtime edits rather than creating a new file.
4. Run `python3 scripts/repo.py status --change podobank-worker-hostnames`, then `python3 scripts/repo.py verify --change podobank-worker-hostnames --full`. Require complete, passing evidence before touching the running OCI Compose project. The UI config check must confirm the Worker origins, frontend/API loopback ports, the existing NPM external network, and DB isolation.
5. Using the active Compose project name and the existing environment files, run Compose with `up -d --build --no-deps api frontend`. The `--no-deps` flag must be present so Compose does not start, stop, or recreate MariaDB or another shared dependency. Do not run `down`, `down -v`, seed/reset commands, or any DB operation. Confirm the DB and other shared containers retain their prior container IDs and running state.
6. Verify `https://podobank.i234.workers.dev/` returns the Vue app, `https://podobank-api.i234.workers.dev/health` returns HTTP 200, and an API `OPTIONS` preflight from `https://podobank.i234.workers.dev` returns the exact allowed origin and credential support. Confirm the frontend build uses the API Worker origin and browser requests still use existing API paths. Do not attempt requests with `/api` or expect URI rewriting.

## Tests and proof

- `python3 scripts/verify_ui.py --config-only` proves both the default local Compose model and preview overlay configuration, including loopback bindings and the Worker URL constants.
- `python3 scripts/repo.py status --change podobank-worker-hostnames` proves the approved packet is current and in scope.
- `python3 scripts/repo.py verify --change podobank-worker-hostnames --full` is the repository completion gate and must report every registered check passed with no `not-run` checks.
- A quiet runtime-env assertion verifies only the three URL values and mode `0600`; never print `.env.npm-preview` or its diff.
- `docker compose ... up -d --build --no-deps api frontend` is the only deployment mutation. Capture and compare container IDs/state for MariaDB, MongoDB, observability, NPM, and other shared services before and after; they must remain unchanged and running.
- Public endpoint proof: UI root returns success, API `/health` returns success, and API credentialed CORS preflight allows only the UI Worker origin.

## Risks and mitigations

- A wrong VITE/API origin can render the UI while breaking all browser API calls. Check the frontend build argument, API health endpoint, exact CORS response, and browser login after rebuilding.
- API and frontend remain publicly reachable through their Workers, including unauthenticated API routes such as `/health` and `/auth/login`; this is a synthetic-data development preview. CORS is not API authentication.
- The `.env.npm-preview` file is ignored and belongs to the running deployment, not the requested change worktree. Confirm its active Compose project before changing it and never create or edit a duplicate.
- Compose may otherwise act on dependencies of `api`; `--no-deps` and before/after container ID checks prevent the requested deployment from disturbing DB or shared services.
- Cloudflare Workers, Tunnel, VPC Services, NPM, DB, volumes, and shared service definitions are already established and out of the implementation scope. A failed public health check is reported with its evidence; do not broaden scope by changing tunnel, NPM, firewall, or DB configuration.

## Rollback or recovery

- Revert tracked Worker URL changes in `compose.npm-preview.yaml`, `.env.npm-preview.example`, `scripts/verify_ui.py`, and `docs/deployment/npm-preview.md` to the previous DuckDNS values, then restore only the three corresponding URL keys in the runtime `.env.npm-preview`.
- Rebuild only `api` and `frontend` using the same active Compose project and `--no-deps`. Do not stop NPM, DB, monitoring, other shared services, or remove any volume.
- If the runtime file is inaccessible or its active use is uncertain, leave it unchanged and ask the owner for the correct path. Never print its secrets.

## Open questions

- The runtime `.env.npm-preview` was found in `/home/ckh/block/codex-home/worktrees/npm-podobank-preview/Podobank`, while it is absent from the specified change worktree and the primary checkout. The owner states the existing file is used by the running Compose project; before step 3, verify that the active project consumes this exact file. If not, stop before changing any runtime file.
