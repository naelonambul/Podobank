# Implementation Plan

## Summary

Add one self-contained Korean HTML page showing the current MariaDB physical schema as an ERD. The six MariaDB tables and their constraints come from `backend/podobank_api/schema.py` at the packet base; the diagram is documentation and does not alter application behavior or database objects.

The page will use Crow’s Foot cardinality, identify primary and foreign keys, nullable and unique columns, composite keys, and the principal check constraints. The `ledger_entries` account and user identifiers will be drawn as dashed logical references because the schema does not declare foreign-key constraints for them. MongoDB event documents are outside this MariaDB-only ERD.

## Files and components that change

- `docs/architecture/podobank-current-erd.html`
  - Standalone responsive page with inline CSS, SVG relationship lines, and small inline JavaScript for useful diagram navigation/filtering.
  - Six entity cards: `users`, `accounts`, `loan_products`, `loan_applications`, `loan_repayments`, and `ledger_entries`.
  - Show the actual column names, MariaDB types, nullability, PK/FK/UNIQUE markers, compound keys, and selected CHECK/index/partition notes.
  - Show declared FK relationships as solid lines with cardinality; show the `ledger_entries.account_id` and `ledger_entries.user_id` associations as dashed, explicitly labeled logical references that are not enforced by MariaDB.
  - Include a note that `transaction_id` groups ledger rows and has no transaction master table.
  - List Korean-language ERD references and state that notation informs presentation while the repository schema remains authoritative:
    - YourERD 사용자 매뉴얼: https://yourerd.com/manual.html
    - ERDCloud로 관계도를 그리는 한국어 사례: https://blog.chichoon.com/738

No root baseline, database schema, runtime configuration, MongoDB model, or other documentation file changes are in scope.

## Order of work

1. Cross-check each displayed table and relationship against `backend/podobank_api/schema.py` at the packet base.
2. Build the standalone HTML with an accessible legend, clear physical/optional relationship styling, responsive layout, and references.
3. Review every edge against declared SQL foreign keys. In particular, keep `ledger_entries` references visually distinct and do not invent a `transactions` entity.
4. Inspect the page and packet diff, then run the repository’s change status and required full verification before closure.

## Tests and proof

- No application tests or schema changes are planned; this is a documentation-only change.
- Run `python3 scripts/repo.py status --change podobank-erd-html` after authoring the plan and after implementation.
- Before closing, run `python3 scripts/repo.py verify --change podobank-erd-html --full` as required by the repository definition of done, and confirm the run is complete with no failed, blocked, or not-run checks.
- Inspect the generated HTML source and rendered page for all six tables, relationship labels, narrow-screen layout, and source links. Record the verification evidence path in the closure.

## Risks and mitigations

- **Schema drift:** a hand-authored diagram could become stale. Mitigation: identify `schema.py` as the source of truth in the page and review the diagram against it before closing.
- **Misstated relationships:** application-level IDs can look like database constraints. Mitigation: distinguish enforced foreign keys from the two logical ledger references in both line style and legend.
- **Dense columns:** six full physical schemas may be difficult to read at once. Mitigation: use a wide desktop canvas, responsive stacking, readable zoom/navigation controls, and searchable/highlightable entity names.
- **Notation references:** external references describe diagram conventions, not this product’s schema. Mitigation: keep the repository DDL authoritative and label references as presentation guidance.

## Rollback or recovery

The page is an isolated documentation artifact. Before merge, remove it by revising the change and regenerating the required verification/closure evidence. After merge, correct or replace it in a new change packet so the closed packet remains immutable.

## Open questions

None. The owner chose to include MariaDB only; MongoDB event storage is excluded.
