# Implementation Plan

## Summary

Separate customer signup discovery from existing-account login while retaining Kakao as the required customer signup identity provider. `/signup` becomes a Kakao signup start screen and the existing profile form moves to `/signup/profile` after a first-time Kakao callback.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `frontend/src/router.js`: define signup start and profile routes.
- `frontend/src/views/LandingView.vue`: send the new-customer action to signup; retain a distinct existing-customer login action.
- `frontend/src/views/LoginView.vue`: keep Kakao and phone/password login; add a clear link to signup.
- `frontend/src/views/SignupStartView.vue`: new signup start screen that explains Kakao-based signup and starts the existing OAuth flow.
- `frontend/src/views/SignupView.vue`: keep profile capture and account creation at `/signup/profile`.
- `frontend/src/views/KakaoCallbackView.vue`: route only `registration_required` callbacks to `/signup/profile`; successful returning users continue to their authenticated home.
- `frontend/e2e/signup-entry.spec.js`: cover signup navigation, the separate login path, and the new-user callback using mocked OAuth/API responses.
- `spec.md`: promote the approved change spec to the root product baseline before closure; the close gate requires the root copy to match the accepted spec exactly.

## Order of work

1. Add `frontend/e2e/signup-entry.spec.js` first. It must demonstrate the current failure on the base commit: the landing signup action routes to `/login`, and no dedicated signup start screen is available. Use `python3 scripts/verify_ui.py --smoke` with the isolated app; do not use live accounts or Kakao credentials. Before the run, stop only the currently running Podobank API, frontend, and DB containers as the owner requested for tests. Preserve their volumes and leave NPM, cloudflared, and other shared containers untouched; restart the original DB, API, and frontend after the smoke run. The expected red result is recorded as the before-fix reproduction.
2. Implement the routes and views in `frontend/src/router.js`, `frontend/src/views/LandingView.vue`, `frontend/src/views/LoginView.vue`, `frontend/src/views/SignupStartView.vue`, `frontend/src/views/SignupView.vue`, and `frontend/src/views/KakaoCallbackView.vue`. Prove the signup entry and callback behavior with `python3 scripts/verify_ui.py --smoke` using the same isolated and restored-service procedure.
3. Run `npm run check` from `frontend/` to cover lint, format, and unit tests. Promote the approved `changes/podobank-signup-entry/spec.md` to root `spec.md` exactly as required by the close gate. Then stop the same Podobank containers for full verification, provide a disposable CI-equivalent MariaDB on `127.0.0.1:3306`, and run `APP_ENV=test DATABASE_URL=mysql+pymysql://podobank:podobank-test@127.0.0.1:3306/podobank_test python3 scripts/repo.py verify --change podobank-signup-entry --full`. Remove only the temporary test DB and restart the original DB, API, and frontend; confirm original API `/health` and frontend `/` return HTTP 200. Never remove or reset existing named volumes.
4. Run `python3 scripts/repo.py status --change podobank-signup-entry` and close with the full verification evidence.

## Tests and proof

- Before implementation, the new end-to-end assertion fails on the current landing-to-login path.
- After implementation, the end-to-end flow confirms: landing signup opens `/signup`; the signup page has a clear Kakao signup action; the login path remains `/login` with phone/password login; a mocked `registration_required` Kakao callback opens `/signup/profile`; returning authenticated users do not see the profile form.
- The tests intercept OAuth/API responses and never create real Kakao accounts or use live customer data.
- `npm run check` passes.
- `python3 scripts/repo.py verify --change podobank-signup-entry --full` completes with no failed, blocked, or not-run checks.
- Existing services are restored after every verification run, and only the original API and frontend health endpoints are checked after restart.

## Risks and mitigations

- The existing Kakao callback and signup-session cookie are required for profile completion. Keep the current server flow and change only frontend navigation; do not bypass backend signup-session validation. Test `registration_required` and returning-user responses separately with mocked callbacks.
- Landing and login actions can be confused if labels are vague. Keep signup and login actions visibly distinct and verify both by accessible role/name in Playwright.
- Browser smoke and full verification can collide with the live preview. Stop only the named Podobank app containers, preserve the database volume, use isolated UI projects and a disposable test database, then restore and check the original services.

## Rollback or recovery

Before merge, revert the new signup-start route and return the profile form to `/signup`; keep the existing Kakao callback and login behavior intact. After merge, restore the prior user-visible flow through a new change packet.

## Open questions

None. Customer signup remains Kakao-based as specified by the approved baseline; phone-only signup is out of scope.
