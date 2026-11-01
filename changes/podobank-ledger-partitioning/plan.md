# Implementation Plan

## Summary

Update the product baseline so the future MariaDB ledger can use date-range partitions without database foreign keys. The approved specification keeps internal user/account identifiers as ledger values, requires application checks plus atomic balance-and-ledger writes, and requires every table modified by those transactions to use InnoDB. This packet changes the baseline specification only; it does not create or migrate the ledger table. Implement the transaction feature in a later approved packet after this baseline change is closed.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `changes/podobank-ledger-partitioning/spec.md`: approved carried copy of the proposed product specification.
- `spec.md`: replace the root baseline byte-for-byte with the approved packet copy when readiness is `ready`.
- `changes/podobank-ledger-partitioning/plan.md`: this packet-local plan; it is lifecycle documentation, not product scope.

No backend source, database schema, migration, or tests change in this packet.

## Order of work

1. After the plan is approved and `status` reports `readiness=ready`, copy `changes/podobank-ledger-partitioning/spec.md` to root `spec.md` without editing its contents. Prove the carried baseline and write scope with `python3 scripts/repo.py status --change podobank-ledger-partitioning`.
2. Run all registered checks and capture complete evidence with `python3 scripts/repo.py verify --change podobank-ledger-partitioning --full`.
3. Close the packet using the full-run evidence from step 2 with `python3 scripts/repo.py close podobank-ledger-partitioning --evidence .evidence/<run>/evidence.json`.

## Tests and proof

- `repo.py status` must report current approvals, the carried root `spec.md` merged byte-for-byte, no out-of-scope paths, and a ready candidate before closure.
- `repo.py verify --full` must complete every registered check with no `failed`, `blocked`, or `not-run` checks. The evidence must identify the current source commit and tree.
- `repo.py close` must accept that full-run evidence and create a current candidate closure.
- No runtime behavior is claimed by this documentation change. The later ledger implementation must test partition routing, absence of foreign keys in both directions, application reference checks, transfer rollback, atomic balance-plus-ledger writes, and InnoDB engines for every modified table against MariaDB.

## Risks and mitigations

- Removing database foreign keys allows orphan ledger references if application checks are incomplete. The spec requires reference validation and atomic writes; the later implementation packet must prove these cases in MariaDB tests.
- MariaDB transactions only provide rollback for transactional storage engines. The spec requires every table modified by a balance-and-ledger transaction to use InnoDB, so a rollback cannot leave a balance change committed without its ledger record.
- MariaDB also requires the partition key in every unique key and prevents other tables from referencing the partitioned ledger by foreign key. The spec records a composite `(entry_id, posted_at)` primary key and prohibits incoming ledger foreign keys.
- Partition interval and retention policy are not finalized. Monthly partitions are a proposal; the later implementation must resolve the interval before DDL and must not delete partitions automatically without an approved retention policy.

## Rollback or recovery

This packet changes only the root product specification. If the owner changes the design after merge, use a new behavior packet to revise the baseline; do not rewrite or remove the frozen packet. No ledger data exists to migrate or restore in this change.

## Open questions

- Confirm monthly versus another date-partition interval before the ledger DDL is approved.
- Define whether and when old partitions may be archived or deleted. Until then, retain all partitions.
