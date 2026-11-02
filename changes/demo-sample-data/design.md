# Design: Development sample banking dataset

## Intent and why

The owner wants roughly 10,000 sample people for PodoBank, with account activity and loan records, so the app can be demonstrated with a populated recipient list, account ledger, and employee loan queue. The fixed demo customer should also be usable to view customer account and loan screens.

The owner chose an explicit command. The existing `init-db` behavior and its small fixed seed remain unchanged. The command adds synthetic sample rows to an already initialized local development database.

## Goals

- Add a manual `podobank-api seed-demo-data` command for the local development database.
- Generate about 10,000 customer profiles and one account per customer, including the existing fixed demo customer in that total.
- Generate synthetic account activity and a smaller representative set of loan applications and repayment schedules.
- Make the fixed demo customer login-capable with a development-only local password so its ledger and loan screens can be viewed.
- Keep balances, paired transfers, loan states, repayments, and ledger rows internally consistent.
- Make repeated runs safe: a complete dataset is a no-op, and a failed run cannot leave a partial dataset that is mistaken for success.
- Keep the command out of test and production environments and avoid external data or new dependencies.

## Non-goals and anti-goals

- Do not add generated customers to the default `init-db` or `reset-db` seed.
- Do not make the other generated customers login-capable or change authentication behavior.
- Do not overwrite an already-set password for the fixed demo customer.
- Do not import real customer records or generate financial events as if these were live operations.
- Do not change banking APIs, the database schema, loan rules, or transaction behavior.
- Do not delete or reset existing development data when loading the samples.

## Approaches considered

1. **Add the population to the default seed.** This makes a fresh database immediately populated, but also enlarges normal initialization and test setup. The owner initially considered this, then selected a separate explicit command.
2. **Add a development-only command (chosen).** This keeps the existing default seed and tests small; developers opt into the larger dataset when they need it. The tradeoff is one extra command after database initialization.
3. **Commit a CSV or SQL dump.** This is easy to inspect as data, but makes the repository carry a large generated fixture and complicates consistent regeneration and idempotency.

## Chosen approach and proposed defaults

The owner selected a separate explicit command. The proposed command is `podobank-api seed-demo-data`; it requires the existing schema and default seed to be initialized first. It is additive and never runs automatically.

Proposed data volume is 10,000 customers total (including the fixed demo customer), one account each, and roughly 20 base ledger entries per account, or about 200,000 ledger rows before loan activity. Use deterministic synthetic profiles, identifiers, amounts, and timestamps so a fresh load is repeatable. Include deposits, withdrawals, and paired transfers. Add loan records for about 5% of customers, with pending, rejected, repaying, and repaid examples; some repayment rows should be overdue so the employee and customer views can show the supported states. These percentages and distributions are implementation proposals, not owner decisions.

Use a separate `DEMO_CUSTOMER_PASSWORD` environment value for the fixed customer. Provide a local-only example in `.env.example` and pass it to the API container through Compose. The command hashes this password and sets it only when the fixed customer's password is unset; it preserves any password a developer has already chosen. Other generated customers have no password and no Kakao identity.

Generated account balances must equal the sum of their ledger entries. Each transfer must have its matching incoming and outgoing entries under the same transaction ID. Loan applications must follow the current one-active-loan rule, and disbursement and repayment entries must agree with the account and repayment state.

The command must verify that it targets `APP_ENV=development` and the local `podobank_dev` database. It must reject test, production, remote hosts, and other database names. Re-running against a complete dataset reports that it is already loaded and inserts no duplicate rows. The README documents initialization, sample loading, and the fixed demo customer's local login.

## Constraints

- Use the existing MariaDB tables and SQLAlchemy Core conventions.
- Preserve the existing fixed employee, demo customer, and loan products.
- Generated names and profile values are synthetic; only the fixed demo customer receives a local login.
- The demo password is development-only, is stored as a password hash, is not logged, and does not replace an existing hash.
- Bulk insertion should use bounded batches rather than one SQL round trip per row.
- Seed operations do not emit financial-operation telemetry because they are fixture construction, not customer service operations.

## Success criteria

- A developer can initialize the normal database, run the explicit command, and find approximately 10,000 customers with accounts plus populated ledger and loan views.
- The fixed demo customer can log in locally and view its seeded ledger and loan record.
- The command is safe on the local development database only and does not duplicate or overwrite an existing sample dataset or customer password on repeated runs.
- Test setup continues to seed only the existing small fixture.
- Database checks prove account/ledger balance reconciliation, transfer pairing, loan/repayment consistency, and seeded row counts.

## Left to the builder

- Choose the exact deterministic identifier namespace and batching strategy.
- Choose a small loan status distribution that gives the employee queue useful coverage without excessive rows.
- Decide whether a partial pre-existing sample namespace should fail with a recovery message or be safely completed; do not duplicate or overwrite unrelated rows.
- Add no new runtime dependency.
