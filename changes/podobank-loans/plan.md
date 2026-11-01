# Implementation Plan

## Summary

Implement the approved loan feature slice: preloaded products, customer
applications, employee approval or rejection, repayment schedules, automatic
installment collection, and manual repayment of overdue installments. All
loan, repayment, account, and ledger writes use MariaDB InnoDB transactions.

The owner chose a one-shot repayment CLI invoked daily by an external
scheduler. A run processes every still-scheduled installment due on or before
its UTC as-of date, oldest first. A missed scheduled run therefore catches up
in installment order. Each installment changes from `scheduled` to `paid` or
`overdue` exactly once in the same transaction as its balance and ledger
changes; overdue installments are paid only through the customer repayment
API. Repeated or concurrent CLI runs do not charge a processed installment
again.

Use the preloaded product terms from the root specification without accepting
principal or term values from customers. Snapshot those terms on each
application so a later product edit cannot alter an existing loan. The first
due date is the first UTC month start on or after one calendar month after
approval; when adding a calendar month to a date whose day does not exist in
the target month, clamp the anniversary to that month's last day. Subsequent
installments are due on the first of each following month.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `backend/podobank_api/schema.py`: add InnoDB `loan_products`,
  `loan_applications`, and `loan_repayments` tables and include the loan entry
  types in the ledger check constraint. Keep the ledger free of outgoing and
  incoming foreign keys. Use foreign keys among the non-partitioned loan
  tables for product, user, reviewer, and repayment ownership.
- `backend/podobank_api/seed.py`: idempotently insert the three approved loan
  products without changing terms on existing rows.
- `backend/podobank_api/features/loans/**`: add request/response models, SQL,
  service logic, customer and employee APIs, schedule generation, and
  privacy-safe outcome logs.
- `backend/podobank_api/app.py`: construct the loan service and include the
  loan router.
- `backend/podobank_api/cli.py`: add
  `podobank-api process-repayments [--as-of-date YYYY-MM-DD]`. Default the
  date to today in UTC. The host scheduler invokes this one-shot command daily;
  do not run an in-process scheduler in FastAPI or add a Compose worker.
- `backend/tests/test_database.py` and `backend/tests/test_loans.py`: verify
  schema, seed data, API behavior, transaction atomicity, schedule processing,
  missed-run catch-up, overdue repayment, and concurrent/repeated job runs.
- `README.md`: document loan endpoints, due-date rules, and an example daily
  external schedule invocation.

## Order of work

1. Add the InnoDB loan tables and loan ledger entry types in
   `backend/podobank_api/schema.py`; seed the approved products in
   `backend/podobank_api/seed.py`; extend `backend/tests/test_database.py` for
   table engines, keys, constraints, and product values. Prove the schema and
   seed with `python3 scripts/verify_backend.py --suite mariadb` using the
   isolated `podobank_test` database.
2. Implement application, approval/rejection, schedule generation, automatic
   and manual repayment transactions in `backend/podobank_api/features/loans/`
   and add service/integration coverage in `backend/tests/test_loans.py`.
   Apply the lock order: lock the loan/application row, then the relevant
   repayment rows in installment order, then the account row with `WAIT 3`.
   New application creation has no loan row to lock; serialize that operation
   on the user's account row and check for an active application without
   acquiring loan-row locks. Every balance and ledger write is in the same
   transaction as its loan and repayment state changes. Prove this step with
   `python3 scripts/verify_backend.py --suite mariadb`.
3. Add customer and bank-employee routes, wire them in
   `backend/podobank_api/app.py`, add the daily one-shot command in
   `backend/podobank_api/cli.py`, and document contracts in `README.md`.
   The command selects scheduled rows due through the UTC as-of date in
   `(due_date, loan_id, installment_number)` order. For each row, lock and
   process it in its own transaction. If the balance cannot cover a full
   installment, mark that installment overdue without a partial debit, then
   continue to the next due installment. Prove routes, authorization, catch-up,
   and idempotency with `python3 scripts/verify_backend.py --suite mariadb`.
4. Run `python3 scripts/repo.py status --change podobank-loans`, then
   `python3 scripts/repo.py verify --change podobank-loans --full`. Review the
   complete diff against this plan and `REVIEW.md`; close the packet using the
   complete full-run evidence.

## Tests and proof

- Schema tests verify InnoDB for loan products, applications, repayments,
  accounts, and ledger; valid foreign keys among non-partitioned loan tables;
  absence of foreign keys to or from the partitioned ledger; and the exact
  preloaded product principal, term, and monthly installment values.
- Customer tests verify product listing, application creation, one pending or
  repaying loan at a time, immutable product-term snapshots, and reapplication
  after rejection or full repayment. Employee tests verify only the employee
  role can review applications and approvals cannot change selected terms.
- Approval tests verify one atomic commit of the application state, account
  credit, repayment schedule, and positive `loan_disbursement` ledger entry;
  forced failures must roll back every write.
- Date tests cover first due dates at month boundaries, including approvals on
  the first and last days of a month, and a full schedule with the approved
  installment count and amount.
- Automatic repayment tests verify full installment debit, insufficient
  balance becomes overdue with no partial debit, missed dates catch up oldest
  first, prior overdue rows are not automatically charged, repeated runs do
  not duplicate payment, and concurrent runs produce one ledger debit per
  installment.
- Manual repayment tests verify only overdue rows can be cleared, amounts are
  positive multiples of the monthly installment, overpayment and partial
  installments fail without writes, and older overdue rows clear first.
- API tests verify customer ownership, employee-only review, authentication,
  response contracts, and outcome logs without names, phone numbers, IDs, or
  monetary values.
- Run `python3 scripts/verify_backend.py --suite mariadb` with `APP_ENV=test`
  and `DATABASE_URL` restricted to the isolated `podobank_test` database.
- Run `python3 scripts/repo.py verify --change podobank-loans --full`; require
  every registered check to pass with complete evidence and no blocked or
  not-run checks.
- Run `python3 scripts/repo.py status --change podobank-loans` before
  implementation and before closure.

## Risks and mitigations

- Scheduler outages can delay repayments. The daily command catches up
  scheduled installments oldest first and uses the current account balance
  when processing each due row. Paid or overdue rows transition once and are
  not automatically reprocessed.
- Concurrent API and scheduler operations can contend on loan, repayment, and
  account rows. Use one lock order for paths that lock all three kinds of rows,
  bound each lock wait with `WAIT 3`, and let MariaDB aborts roll back the
  entire installment transaction.
- A customer can apply while another request reviews or repays a loan. Lock
  the account when creating an application to serialize the active-loan check;
  review and repayment paths lock loan data before the account and never take
  an account lock before a loan-row lock.
- Repayment command retries are safe because only rows still marked
  `scheduled` are processed and the status transition, debit, and ledger write
  commit together. Do not retry an ambiguous client-facing application as a
  new request without first checking its stored state.

## Rollback or recovery

Disable loan routes and the scheduled command through a reviewed follow-up
change if behavior is incorrect. Preserve applications, repayment history,
balances, and ledger rows; never reset or delete committed financial state as
part of rollback. An operator can rerun the daily command safely to resume
scheduled installments after correcting a transient infrastructure problem.

## Open questions

None. The owner selected a daily one-shot CLI with an external scheduler and
oldest-first processing of installments missed while the scheduler was down.
