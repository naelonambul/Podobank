# Account and ledger

Customers can review their account balance and persisted transaction entries.

## Sub-features

- account-balance: the account screen reflects the API balance.
- ledger-history: completed deposits, transfers, withdrawals, loan disbursements, and repayments appear in the ledger.

## How to get to it (user POV)

- Sign in and select `계좌` in the bottom navigation.
- After a transaction or loan decision, return to `계좌` to inspect its result.

## Driving it

- `frontend/e2e/01-transactions.spec.js` asserts the resulting balance and `입금`, `보낸 송금`, and `출금` ledger rows.
- `frontend/e2e/02-loan-approval.spec.js` asserts the approved principal and `대출 실행` ledger row.
- `frontend/e2e/04-overdue-repayment.spec.js` asserts the final balance and `대출 상환` ledger row.
- The scripts assert balance through the rendered `account-balance` test ID and its numeric `data-amount` attribute.

## Gotchas

- Ledger timestamps and the newest-first ordering can depend on the current time. Assert transaction types and persisted balances rather than exact timestamps.
- Each browser test uses a separate fixture account so its balance oracle does not depend on another test's transaction sequence.
