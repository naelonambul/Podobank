# Authentication and session

Customers and bank employees sign in with a phone number and local password; the API session cookie controls access to role-specific screens.

## Sub-features

- customer-login: customer login opens the home screen and uses the HTTP-only API session cookie.
- employee-login: employee login opens the loan review screen; customer routes remain role-protected.
- mobile-layout: the login and authenticated screens fit the 384 × 832 viewport without horizontal overflow.

## How to get to it (user POV)

- Open `/login` and sign in with the customer credentials created for the isolated run.
- Log out, return to `/login`, and sign in with the isolated employee credentials.

## Driving it

- `frontend/e2e/01-transactions.spec.js` and the loan review specs use the login form labels `휴대전화번호`, `비밀번호`, and button `로그인`.
- The tests assert `/home` for a customer, `/staff/loans` for an employee, and an HTTP-only `podobank_session` cookie on the API origin.
- Run `python3 scripts/verify_ui.py --drive --run-file <run-file>`; screenshots are saved under the run's evidence directory.

## Gotchas

- Kakao provider exchange requires external credentials and is not part of the local browser smoke. Callback parsing has a separate unit test.
- Customer and employee fixtures use independent browser sessions and passwords generated for each isolated run.
