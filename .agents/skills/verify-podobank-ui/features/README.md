# Podobank UI feature map

## Shared preconditions

- Work from the Podobank repository root and use the verifier's run file from Launch.
- The isolated database is seeded with a local-login customer, recipient, employee, separate loan applicants, and one overdue loan. Kakao requires external credentials and is checked separately by the frontend unit tests.
- Doctor must pass before Drive. After an unexpected result, run Doctor again before retrying.
- The browser proof is the real Vue app and FastAPI API with an isolated MariaDB database. Assertions cover rendered state and persisted balances, ledger rows, application decisions, and repayment status; screenshots are reviewer evidence.
- The browser viewport is 384 × 832. 16:9 layouts are outside this change.
- Cleanup stops only the verifier's Compose project. Evidence remains under `.evidence/ui/<run-id>/`.

## Full sweep order

1. Authentication and customer session
2. Account and ledger
3. Deposit, withdrawal, recipient search, and transfer
4. Loan application and employee approval or rejection
5. Overdue repayment

Drive all registered browser paths with:

```sh
python3 scripts/verify_ui.py --drive --run-file /tmp/podobank-ui-<id>-<suffix>/run.json
```

## Features

- [Authentication](auth.md): local login, role routing, credentialed session cookie, and mobile layout.
- [Account and ledger](account-ledger.md): account balance and persisted transaction history.
- [Money movement](money-movement.md): deposits, withdrawals, recipient search, transfer confirmation, and resulting balances.
- [Loan review](loan-review.md): customer application, employee approval and rejection, disbursement, and schedule.
- [Overdue repayment](overdue-repayment.md): scheduled overdue state and customer repayment from a funded account.
