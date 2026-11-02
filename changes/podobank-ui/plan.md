# Implementation Plan

## Summary

Build the Vue 3 banking UI and Nginx static-serving container described by the accepted root baseline. The owner chose a mobile-first responsive interface and excluded 16:9 layouts from this implementation. Use the accepted root `spec.md` viewport of 384 × 832 px as the reference and preserve its 16 px spacing grid. The owner-provided HTML export contains 13 prototype screens arranged on 1280 × 1120 px desktop canvases. Use compatible visual details (purple palette, typography, spacing, cards, and form styling) while adapting its navigation and layout to mobile.

The root `intent.md` and `spec.md` remain the product authority. The exported screens contain check-card/card issuance and arbitrary asset registration, which are outside the current product scope. They also show email/password signup instead of the required Kakao signup and profile flow, and flexible loan repayment instead of the approved employee review and scheduled repayment behavior. Implement the approved product flows, including deposits and withdrawals that are absent from the prototype. Do not add card, card-payment, or arbitrary asset-tracking behavior.

The browser calls FastAPI directly with credentialed requests. Nginx serves the built Vue files and does not proxy API requests.

## Files and components that change

- `frontend/**`: Vite/Vue app, locked npm dependencies, API client, router, customer and employee views, reusable form/navigation components, styles, unit and browser tests, and a multistage frontend container build.
- `frontend/nginx.conf`: serve static assets and route client-side paths to `index.html`; no API upstream or proxy locations.
- `compose.yaml`: add the Nginx frontend service and its loopback-only port, retaining direct browser-to-FastAPI traffic.
- `.env.example`: add the frontend port and set the default Kakao callback to the Nginx-served UI; retain explicit API and frontend origins.
- `docs/stack-versions.md`: record the selected UI toolchain and exact pinned container versions after upstream documentation review.
- `README.md`: document frontend development, Compose startup, demo login, and Kakao callback configuration.
- `checks.json` and `.github/workflows/repository.yml`: register a web-toolchain verification group that installs the pinned Node runtime and runs frontend quality and isolated browser smoke checks; add the group to the required summary dependencies.
- `scripts/verify_ui.py`: run the API, MariaDB, Nginx, and browser smoke checks with a unique Compose project and temporary credentials; clean up only its own project and keep evidence.
- `.agents/skills/verify-podobank-ui/**` and `.claude/skills/verify-podobank-ui`: add the user-facing feature map, executable browser-driving instructions, and the required Claude adapter symlink.

No API behavior, database schema, financial rules, or product requirements change in this implementation packet.

## Order of work

1. Map the compatible visual components from the 13 exported screens to the approved product flows; omit the card/card-issuance and arbitrary-asset screens. Build and verify the mobile layout at 384 × 832 px; 16:9 layouts are out of scope. Review current official Vue/Vite, Nginx, and browser-test documentation; pin the selected toolchain in the frontend manifests and `docs/stack-versions.md`. Establish npm lint, unit-test, and build commands. Prove them with `npm ci && npm run check && npm run build` from `frontend/`.
2. Add the Nginx multistage image, SPA fallback, and Compose UI service. Configure the browser API origin as FastAPI's host origin, keep Nginx free of API proxy routes, and set the Kakao redirect to the served UI callback. Prove the Compose model with `docker compose --env-file .env.example config --quiet`.
3. Implement the customer flows against existing API routes: Kakao login/callback and profile signup, local login/logout, account and ledger view, deposit/withdrawal/transfer with recipient search, loan product/application/status/overdue repayment, and one-time customer password setup. Implement the employee local-login and pending-loan approval/rejection view. Include loading, empty, validation, authorization, and API error states; send cookies with every API request.
4. Add a browser smoke path that provisions only isolated demo fixtures, launches the real Compose API and UI, and drives local customer and employee flows through the browser. Verify the rendered DOM/accessibility state and resulting account, ledger, and loan state; capture screenshots as reviewer evidence. Prove it with `python3 scripts/verify_ui.py --smoke`.
5. Add the `verify-podobank-ui` feature map and Claude adapter. Run Doctor and drive at least one mapped real user flow using the published procedure; record the evidence and clean up the isolated app.
6. Register the web checks and add the corresponding workflow job. This touches `.github/workflows/repository.yml`; follow the owner-push handoff in `docs/host-setup.md`. Then review all changed files against `REVIEW.md`, run `python3 scripts/repo.py status --change podobank-ui`, run `python3 scripts/repo.py verify --change podobank-ui --full`, and close only with complete passing evidence.

## Tests and proof

- Frontend lint, formatting check, unit tests, type-check if TypeScript is selected, and production build using the committed npm lockfile and pinned Node runtime.
- Browser layout check at the 384 × 832 px mobile reference, including navigation and horizontal-overflow checks.
- `docker compose --env-file .env.example config --quiet` to validate Compose interpolation and service wiring.
- Isolated browser smoke for served UI, direct API requests, credentialed cookies, customer/employee role paths, and persisted financial state. The smoke must use a unique project and temporary database/environment, and tear down only those resources.
- Project-local `verify-podobank-ui` Doctor and feature drives against the real running Compose app, with structured DOM/accessibility assertions as the pass oracle and screenshots as human evidence.
- Final `python3 scripts/repo.py verify --change podobank-ui --full` with complete `.evidence/` output.

## Risks and mitigations

- The exported prototype is available locally, so implementation can use its visual details without relying on automated access to the Claude Artifact page.
- The exported prototype has a 1280 × 1120 desktop canvas and persistent side navigation. Adapt these patterns to the owner-selected mobile 384 × 832 layout; do not copy the desktop canvas as a fixed-size UI. 16:9 layouts are excluded from this change.
- The prototype includes debit-card issuance, arbitrary asset tracking, email-based signup, and flexible loan repayment. Keep the accepted product rules authoritative and omit out-of-scope behavior.
- Local and production frontend/API origins differ. Configure exact origins, send cookies with `credentials: "include"`, and keep Nginx from proxying FastAPI.
- Kakao login depends on external provider credentials. Browser CI should exercise the real frontend and API boundary with isolated local credentials for customer and employee paths; test Kakao callback parsing separately without adding a production bypass.
- Browser runs can collide with developer data or ports. Give each smoke a unique Compose project, temporary environment, dynamically allocated loopback ports, bounded readiness checks, and project-scoped cleanup.
- The web CI workflow requires a workflow-file update. The repository GitHub App cannot push that path; use the documented owner handoff and leave the bot as the final pusher.

## Rollback or recovery

Run `docker compose down` to remove the Nginx UI service while preserving database and monitoring volumes. Revert the UI change to remove the frontend service and web assets. Do not use `down --volumes` on the normal developer project. The isolated smoke verifier may remove only the unique project and volumes it created.

## Open questions

- If Vue 3 can be covered by the selected lightweight verification setup without TypeScript, keep JavaScript; otherwise choose TypeScript only if its type-check adds useful coverage without expanding the toolchain unnecessarily.
