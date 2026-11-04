# Phone-number Customer Signup Implementation Plan

> **For implementation:** Use `superpowers:executing-plans` and complete the tasks in order. Each task has a checkable test cycle.

**Goal:** Let customers sign up with a phone number or Kakao, giving phone signups a customer account, one default account, and an authenticated session.

**Architecture:** Add a public FastAPI phone-signup endpoint that validates the exact hyphenated phone format, stores its normalized digits, and creates the user and default account in one MariaDB transaction. Keep Kakao signup intact with the same phone format, and add a matching phone signup route and form to the Vue app.

**Tech Stack:** Vue 3, Vue Router, FastAPI, Pydantic, SQLAlchemy Core, MariaDB, Argon2, Playwright.

**Spec:** `changes/podobank-phone-signup/spec.md`

## Global Constraints

- The signup screen presents phone signup and Kakao signup at equal visual weight.
- Phone signup requires name, phone number, password, age, gender, marital status, and employment status.
- Both signup APIs accept phone numbers only in `000-0000-0000` form; normalize by removing hyphens before database lookup and storage.
- Phone signup does not send SMS or verify ownership. The UI states this plainly.
- Passwords are 8–128 characters and use the existing Argon2 password hash policy.
- Public signup always creates the `customer` role.
- User creation and one default account share a MariaDB transaction. Signup success returns the existing JWT HttpOnly session cookie.
- Existing Kakao signup, optional Kakao signup password, customer local login, and employee local login keep working.
- Keep MariaDB as the only financial database. No schema migration is expected because `users.kakao_subject` is already nullable.
- Keep the change within the packet's approved `write_scope`; do not edit deployment settings or shared services.

## Review Focus

- Malformed phone input, including missing or misplaced hyphens: backend rejects it on both signup routes; UI sends only the required format. Pin with `test_phone_signup_rejects_invalid_phone_format`, `test_kakao_signup_rejects_invalid_phone_format`, and Playwright format checks.
- A formatted number that matches an existing digits-only row: normalize before duplicate lookup and return the existing `phone_already_registered` conflict. Pin with `test_phone_signup_rejects_duplicate_normalized_phone`.
- Two simultaneous phone signups with the same number: the unique phone constraint leaves one user and one account, and the losing request is a conflict without a session. Pin with `test_concurrent_phone_signup_with_same_phone_creates_one_customer`.
- Default-account creation failure: roll back the new user so no half-created customer remains. Pin with `test_phone_signup_rolls_back_when_default_account_creation_fails`.
- Caller-supplied role or password disclosure: role remains `customer`, only an Argon2 hash is stored, and the response exposes no token. Pin with `test_phone_signup_cannot_create_employee_and_issues_http_only_session`.

---

### Task 1: Add transactional phone signup to the auth API

**Files:**
- Modify: `backend/podobank_api/features/auth/api.py`
- Modify: `backend/podobank_api/features/auth/schemas.py`
- Modify: `backend/podobank_api/features/auth/service.py`
- Modify: `backend/podobank_api/features/auth/models.py`
- Modify: `backend/podobank_api/features/auth/sql.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Add `PhoneSignupRequest` with non-empty `name` (maximum 120 characters, matching `users.name`), strict `phone_number`, required `password`, `age`, `gender`, `marital_status`, and `is_employed` fields.
- Add `PhoneSignupData` with the phone signup fields consumed by `AuthService.complete_phone_signup(*, signup: PhoneSignupData) -> AuthenticatedUser`.
- Add `POST /auth/phone/signup`; on success return `{"status":"authenticated"}` and set the existing session cookie. On a duplicate normalized phone return HTTP 409 with `detail.code == "phone_already_registered"`.
- Both `PhoneSignupRequest` and `KakaoSignupRequest` require `^[0-9]{3}-[0-9]{4}-[0-9]{4}$`; pass only the normalized digits to existing database lookup and write functions.
- Change `sql.insert_customer` to accept `kakao_subject: str | None`; keep Kakao signup passing its subject and phone signup passing `None`.

- [ ] **Step 1: Add failing MariaDB auth tests** named `test_phone_signup_creates_customer_account_and_session`, `test_phone_signup_rejects_invalid_phone_format`, `test_phone_signup_rejects_duplicate_normalized_phone`, `test_concurrent_phone_signup_with_same_phone_creates_one_customer`, `test_phone_signup_rolls_back_when_default_account_creation_fails`, `test_phone_signup_cannot_create_employee_and_issues_http_only_session`, and `test_kakao_signup_rejects_invalid_phone_format`. Update Kakao signup test fixtures to submit formatted phone numbers.
- [ ] **Step 2: Run the auth verification group and confirm the new tests fail** because the endpoint and format behavior are not implemented yet.

Run: `python3 scripts/repo.py verify --change podobank-phone-signup --group mariadb`

Expected: the new phone signup tests fail; existing tests continue to identify regressions. Before running tests, stop only the active Podobank API and frontend containers as directed by the owner; preserve MariaDB, NPM, MongoDB, observability services, and every shared volume.

- [ ] **Step 3: Implement strict request validation and phone normalization** for both signup requests. Reject anything other than three digits, a hyphen, four digits, a hyphen, and four digits before any database write.
- [ ] **Step 4: Implement the transactional service and API route.** Hash the required password with the existing Argon2 helper; create a `customer` with `kakao_subject=None`; create its default account in the same `engine.begin()` block; handle duplicate races as `DuplicatePhoneError`; set the session cookie only after success.
- [ ] **Step 5: Run the MariaDB verification group again and confirm all auth tests pass**, including preserved Kakao signup, local login, employee role checks, one-account creation, and rollback behavior.

Run: `python3 scripts/repo.py verify --change podobank-phone-signup --group mariadb`

Expected: all checks selected by the `mariadb` group pass with no failed or blocked checks.

### Task 2: Add the phone signup experience and update the guide

**Files:**
- Modify: `frontend/src/router.js`
- Modify: `frontend/src/views/SignupStartView.vue`
- Create: `frontend/src/views/PhoneSignupView.vue`
- Modify: `frontend/src/views/SignupView.vue`
- Modify: `frontend/src/views/LoginView.vue`
- Modify: `frontend/e2e/signup-entry.spec.js`
- Create: `frontend/e2e/phone-signup.spec.js`
- Modify: `docs/user-manual.md`

**Interfaces:**
- Register `/signup/phone` as the public phone signup route.
- The `/signup` screen shows phone and Kakao signup actions with the same full-width button sizing; preserve the current Kakao state and callback flow.
- Phone signup submits the formatted phone number to `/auth/phone/signup`, refreshes the session through `loadSession({ force: true })`, then routes to `home`.
- Kakao profile signup submits the same formatted phone number to `/auth/kakao/signup`; the server performs normalization.

- [ ] **Step 1: Add failing Playwright tests** named `test_signup_offers_phone_and_kakao_actions_with_equal_weight`, `test_phone_signup_submits_formatted_phone_and_redirects_home`, and `test_phone_signup_rejects_invalid_number_format`. Keep the existing “a first-time Kakao callback opens a signup profile form” test passing as a Kakao regression check.
- [ ] **Step 2: Run the frontend smoke check and confirm the new signup expectations fail.** Stop only the active Podobank API and frontend containers before the verification run; preserve MariaDB and shared services.

Run: `python3 scripts/repo.py verify --change podobank-phone-signup --group frontend`

Expected: new signup-flow assertions fail until the route and form are implemented.

- [ ] **Step 3: Implement the two equal signup choices and the phone form.** Collect name, formatted phone, required password and confirmation, and the four existing profile fields. Show that SMS verification is not used. Keep the Kakao CTA and callback intact.
- [ ] **Step 4: Update Kakao profile phone input** to display and submit the exact hyphenated format; retain its optional password behavior. Change the login-page signup link to a generic signup label.
- [ ] **Step 5: Update `docs/user-manual.md`** to describe both signup routes, the exact phone format, required password on phone signup, optional password on Kakao signup, and the absence of SMS verification.
- [ ] **Step 6: Run the frontend verification group and confirm the entry, form, callback, and existing UI smoke checks pass.**

Run: `python3 scripts/repo.py verify --change podobank-phone-signup --group frontend`

Expected: every check selected by the `frontend` group passes.

### Task 3: Complete repository verification and close the packet

**Files:**
- Replace root `intent.md` with `changes/podobank-phone-signup/intent.md` after implementation is complete.
- Replace root `spec.md` with `changes/podobank-phone-signup/spec.md` after implementation is complete.
- Create `changes/podobank-phone-signup/closure.json` using `repo.py close` after the final full verification.

- [ ] **Step 1: Review the final diff against `REVIEW.md` and the approved packet scope.** Confirm the schema needs no migration, the Kakao flow is intact, and no credentials, generated metadata, or unrelated changes were added.
- [ ] **Step 2: Run complete repository verification with application services stopped.** Stop only Podobank API and frontend containers, keep MariaDB and all shared services and volumes intact, then run:

Run: `python3 scripts/repo.py verify --change podobank-phone-signup --full`

Expected: every check in `checks.json` is `passed`; there are no `failed`, `blocked`, or `not-run` checks. Preserve the emitted `.evidence/<run>/evidence.json` path.

- [ ] **Step 3: Merge the accepted packet intent and spec into the root baseline**, then rerun full verification so its source tree matches the final root files.
- [ ] **Step 4: Close the packet** with `python3 scripts/repo.py close podobank-phone-signup --evidence <full-run-evidence.json>` and confirm `python3 scripts/repo.py status --change podobank-phone-signup` reports a current candidate closure and readiness is ready.
- [ ] **Step 5: Restore the Podobank API and frontend to the state they had before verification.** Do not restart, recreate, or modify MariaDB, NPM, MongoDB, observability services, or shared volumes.
- [ ] **Step 6: Commit the closed packet, push the feature branch with `agent-git`, and open one pull request with `Change-ID: podobank-phone-signup` using `agent-gh`.** Leave review and merge to the owner.

## Rollback or recovery

If implementation or verification fails, keep all work inside this packet's scope, fix the failure, and rerun the affected verification group. If the plan or spec must change, update the packet and obtain a fresh approval before proceeding. Never reset or discard the worktree or modify the running shared database to recover the change.
