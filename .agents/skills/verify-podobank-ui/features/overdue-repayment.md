# Overdue repayment

Customers can pay one or more whole overdue installments after adding funds to their account.

## Sub-features

- scheduled-overdue-state: an approved loan has a scheduled installment marked overdue after its due date is processed with insufficient funds.
- manual-payment: a customer funds the account, pays the overdue amount, and sees the installment marked paid.

## How to get to it (user POV)

- Sign in and select `대출` to view the overdue installment.
- Select `거래`, deposit enough funds, return to `대출`, and submit the overdue payment.

## Driving it

- `frontend/e2e/04-overdue-repayment.spec.js` asserts the initial overdue state, deposits the installment amount through the transaction screen, and pays through the repayment form.
- It then asserts `납부 완료`, no remaining overdue installments, a zero balance, and a `대출 상환` ledger entry.

## Gotchas

- The verifier prepares the overdue state through the real loan and transaction services in the temporary database; it does not update repayment rows directly.
- The fixture's processing date is the first installment's due date so the test is independent of the machine's calendar date.
