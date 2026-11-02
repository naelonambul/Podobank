# Loan application and employee review

Customers can apply for a loan, and an employee can approve or reject a pending application.

## Sub-features

- application: a customer submits an available product through the loan screen.
- approval: an employee approves the pending application, disbursing the principal and creating a monthly schedule.
- rejection: an employee rejects the pending application, which appears in the customer's history.

## How to get to it (user POV)

- A customer signs in, selects `대출`, chooses a product, and selects `선택한 상품 신청하기`.
- An employee signs in and reviews the application in `대출 심사`.
- The customer returns to `대출` or `계좌` to inspect the decision.

## Driving it

- `frontend/e2e/02-loan-approval.spec.js` asserts a pending application, employee approval, `상환 중`, the first installment, the disbursed account balance, and a `대출 실행` ledger row.
- `frontend/e2e/03-loan-rejection.spec.js` asserts employee rejection and the customer's `거절` history.
- Employee actions accept the application's confirmation dialog and assert the resulting status message.

## Gotchas

- Approval and rejection use separate customer accounts so the single-active-loan rule is preserved.
- Kakao login and staff access-control failures need provider or role-specific setup beyond these local success paths.
