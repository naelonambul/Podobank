# Implementation Plan

## Summary

Implement authenticated deposits, withdrawals, account transfers, recipient
discovery, and account-scoped ledger history on the existing MariaDB backend.
Use the product baseline's balance, rollback, and reference-validation rules.
The owner selected monthly ledger partitions. Keep all ledger rows and do not
automatically drop or expire partitions until a retention policy is approved.

Money amounts are whole KRW integers. A simulated deposit credits the
authenticated user's own account; no external payment rail is introduced.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- backend/podobank_api/schema.py: create an InnoDB ledger table with no
  outgoing or incoming foreign keys. Store entry_id, UTC posted_at,
  transaction_id, account_id, user_id, entry type, and signed amount.
  Use (entry_id, posted_at) as the primary key and
  (account_id, posted_at, entry_id) for account/date reads. Group the two
  transfer entries with one transaction_id.
- backend/podobank_api/features/transactions/**: add request/response models,
  SQL, transaction orchestration, HTTP routes, and privacy-safe outcome logs.
- backend/podobank_api/features/accounts/**: add authenticated recipient lookup
  and the current user's ledger read endpoint.
- backend/podobank_api/app.py: construct and wire the transaction service and
  router.
- backend/tests/test_transactions.py and backend/tests/test_database.py:
  cover API behavior, atomicity, ledger structure, partitions, and rollback.
- README.md: document the transaction endpoints and local verification flow.

## Order of work

1. Add the ledger DDL in backend/podobank_api/schema.py and the SQL needed to
   inspect accounts and write/query ledger entries. Partition by
   RANGE COLUMNS(posted_at) in UTC monthly ranges. At table creation, include
   a partition for dates before the current UTC month, the current month and
   next eleven months, and a MAXVALUE catch-all for later dates. The catch-all
   must accept future entries; it must never be automatically dropped.
   Keep account and ledger tables on InnoDB. Declare no foreign keys to or
   from the ledger, and validate account/user references in application code.
   Verify schema engines, keys, partition metadata, and absence of foreign
   keys with the MariaDB backend verification command.
2. Implement deposits, withdrawals, and transfers in
   backend/podobank_api/features/transactions/service.py. Each successful
   balance change and its ledger writes must commit in one database
   transaction. Withdrawals lock the source account before checking funds.
   Transfers resolve the destination, lock both mutable account rows in
   ascending account ID order with the existing bounded lock wait, then write
   both balance changes and both signed ledger entries. Reject nonpositive
   amounts, self-transfers, and insufficient funds without partial changes or
   ledger rows. Exercise rollback and concurrent balance invariants with
   MariaDB integration tests.
3. Add authenticated endpoints in the accounts and transactions API modules:
   recipient listing/search by exact account number or normalized phone,
   POST deposit, POST withdrawal, POST transfer, and account-scoped ledger
   history with UTC date bounds and bounded pagination. Recipient results
   return the account ID, name, masked account number, and phone suffix; do
   not return full phone numbers. Emit success/failure log events containing
   operation and outcome/reason only, with no amounts, account IDs, phone
   numbers, or credentials. Update README.md with these contracts and the
   explicit database initialization steps.
4. Run the full registered verification against the disposable
   podobank_test database, review the complete diff against this plan and
   REVIEW.md, then close the packet with that full-run evidence.

## Tests and proof

- MariaDB schema tests verify InnoDB for accounts and ledger, the composite
  ledger primary key, the account/date index, monthly partition boundaries,
  the future catch-all, and no foreign keys in either direction.
- Integration tests verify deposit and withdrawal balances, positive-amount
  validation, insufficient-funds behavior, destination lookup, self-transfer
  rejection, paired transfer entries, transaction rollback, and concurrent
  withdrawals/transfers never producing a negative balance or one-sided
  transfer.
- API tests verify authentication, response status/body contracts, recipient
  masking, date filtering, pagination, and that outcome logs contain no
  personal or monetary data.
- Run python3 scripts/verify_backend.py --suite mariadb with APP_ENV=test and
  DATABASE_URL restricted to the disposable podobank_test database.
- Run python3 scripts/repo.py verify --change podobank-money-movement --full.
  Every registered check must pass; evidence must be complete with no
  blocked or not-run checks.
- Run python3 scripts/repo.py status --change podobank-money-movement before
  implementation and before closure.

## Risks and mitigations

- With no ledger foreign keys, incomplete application checks could create
  orphan entries. Validate both account references and their user ownership
  in the same transaction that changes balances; test forced failures and
  rollback.
- The MAXVALUE partition prevents future dates from being rejected, but rows
  beyond the pre-created monthly horizon share that partition. Extend monthly
  ranges through a later approved maintenance change; do not drop old
  partitions.
- The current API has no transaction idempotency contract. A client retry
  after an ambiguous timeout could repeat a simulated operation. Keep the
  operation ID in successful responses and record idempotency as a follow-up
  before connecting any real payment rail.
- Outcome logs are intended for later Alloy collection. Restrict them to
  operation and outcome/reason fields so personal, account, and monetary
  values are not emitted.

## Rollback or recovery

Disable the new routes through a reviewed follow-up change if the API behavior
is wrong. Never drop the ledger table or reset account balances as rollback:
committed ledger entries and balance changes are financial state and must be
preserved. No existing account rows are rewritten when the ledger table is
created.

## Open questions

- The ledger retention duration remains unspecified. This implementation keeps
  all rows and never drops partitions automatically. Any retention period or
  deletion behavior requires a later owner-approved change.
