# Specification

## Summary

Podobank is an API-only bank simulator for an MLOps bootcamp. A FastAPI service generates synthetic customer, account, loan, and partner-payment activity and stores immutable business events in MariaDB for data-pipeline exercises. It exposes interactive API documentation and emits structured event and operational logs for Grafana Alloy to deliver to Loki; Prometheus collects service metrics, and Grafana provides operator dashboards. The deployment target is AWS. Nginx is reserved for serving a future frontend and does not proxy the MVP API.

No account, loan, payment, or recommendation in Podobank represents a real financial transaction, binding offer, credit decision, or bank relationship.

## Requirements

### Functional

1. **Synthetic sandbox and scenario generation**
   - Provide API operations to create or reuse synthetic customers, accounts, and merchants.
   - Provide seeded scenario generation for baseline activity, deposits, withdrawals, internal transfers, loan recommendations, simulated loan outcomes, and partner checkout flows.
   - A caller-supplied random seed makes generated business values and scenario choices reproducible. Generated record identifiers and timestamps may differ between runs.
   - Scenarios may include declined operations and unusual but valid activity for pipeline exercises. Podobank does not label activity as anomalous or fraudulent.

2. **Deposits, withdrawals, and transfers**
   - Support synthetic deposits and withdrawals on a simulated account and transfers between two Podobank accounts.
   - Amounts are positive integer Korean won (`KRW`); floating-point monetary values are not accepted.
   - A completed transfer debits the source and credits the destination atomically. A rejected operation does not change balances.
   - Insufficient funds and other valid business rejections produce a rejection event with a machine-readable reason. Malformed requests fail validation and do not create domain events.
   - Mutating requests support idempotency. A retry with the same key and same request returns the original result without appending duplicate business events. Reusing a key with a different request returns a conflict.

3. **First-tier bank loan-product catalog**
   - Periodically retrieve publicly displayed product facts from official pages for a curated allowlist of first-tier Korean banks. The default refresh cadence is weekly and is configurable; the service does not require real-time updates.
   - Store normalized, versioned snapshots with the institution name, product name, product category, published eligibility summary, published amount and term bounds, published rate type and range, repayment methods when available, source URL, retrieval timestamp, and source effective date when published.
   - A field not present in a source remains unknown; the service does not invent or infer product terms. Keep prior snapshots when a source changes or a product is no longer listed, and mark the latest snapshot accordingly.
   - Retrieve only publicly accessible pages, honor each source's published access conditions and request limits, and do not bypass authentication, bot controls, or other access restrictions. Store normalized product facts and attribution rather than a full copied page.
   - Expose current and historical snapshots through the API so a recommendation event can be reproduced against the catalog version it used.

4. **Synthetic loan comparison and recommendations**
   - Accept a synthetic profile containing only the features needed for comparison, such as requested amount, desired term, income band, employment category, and credit-score band. Do not accept real personal identifiers or account credentials.
   - Return a deterministic, rules-based ranking of catalog products with matched criteria, unmet criteria, unknown criteria, published rate range, source URL, and snapshot timestamp.
   - Exclude a product only when a published, known condition conflicts with the synthetic profile or requested amount/term. Unknown source data is surfaced as unknown and is not treated as a match.
   - Persist each request and result as a `loan.recommendation.generated` event referencing the exact catalog snapshot and synthetic input features. The result is an educational simulation, not an eligibility decision, rate quote, or financial advice.

5. **Simulated loan activity**
   - Allow a synthetic customer to create a simulated loan application using a catalog product and synthetic amount/term.
   - Support deterministic simulated outcomes for the scenario generator, including rejected and disbursed applications. A disbursement may credit a synthetic account; it creates corresponding loan and account events atomically.
   - Do not contact a bank, submit an application, create a real debt, or claim that a bank approved the simulated outcome.

6. **Partner bank-transfer payments**
   - Allow another bootcamp project, identified as a sandbox partner, to initiate a simulated account-transfer payment to a provisioned Podobank merchant.
   - Record the partner reference, merchant, synthetic payer account, amount, idempotency key reference, and correlation identifier. Return a payment identifier and current simulated status, and provide an API to retrieve that status.
   - Record payment initiation followed by completion or failure. A successful payment debits the payer and credits the merchant's synthetic account atomically. A failed payment leaves balances unchanged and includes a failure reason.
   - Never call a payment gateway, bank, or settlement rail.

7. **Append-only event access**
   - Append an immutable event for each successful or business-rejected operation, recommendation, loan outcome, and payment-flow transition. Corrections are represented by new compensating events; existing events are not edited or deleted through the API.
   - Events include a unique event ID, schema version, event type, occurrence and recording timestamps, related customer/account/merchant/loan/payment identifiers as applicable, correlation ID, and typed payload.
   - Provide a pull API with cursor pagination and filters for event type, entity identifiers, correlation ID, and time range. Clients can poll later; push delivery and message brokers are out of scope.
   - Preserve event ordering within a single operation and expose enough identifiers to join related events across a transfer, loan, recommendation, or checkout flow.

8. **Interactive API documentation**
   - Publish English OpenAPI documentation with an interactive request explorer, sandbox examples, schemas, response codes, and idempotency guidance.
   - The documentation examples use synthetic values and make the simulated nature of every operation clear.

9. **Operational telemetry and deployment**
   - Run the API service and MariaDB with the Loki, Grafana, Prometheus, and Grafana Alloy services in the AWS bootcamp environment.
   - Emit one structured JSON log record after each committed business event. Include its event ID, event type, correlation ID, outcome, and synthetic business payload so participants can follow related activity in Loki. MariaDB remains the authoritative event store; consumers can deduplicate log copies by event ID.
   - Expose a private Prometheus metrics endpoint for request latency and counts, operation outcomes, event appends, and catalog refresh results. Metric labels must not contain customer, account, payment, or other per-record identifiers.
   - Configure Alloy to collect FastAPI structured logs and deliver them to Loki, and configure Prometheus to collect service metrics. Grafana provides operator dashboards over Loki and Prometheus.
   - Keep the MVP API-only. Nginx is used only when a separate frontend is introduced; it serves that frontend and does not proxy or replace the FastAPI API.

### Non-functional

- The product has one FastAPI application service and one MariaDB transactional persistence boundary for synthetic state and append-only business events. Alloy, Loki, Grafana, and Prometheus are supporting telemetry services; they do not replace the event store. The product does not require business microservices, a message broker, or real-time event delivery.
- A state-changing business operation and its MariaDB events commit atomically. A failure cannot leave balances changed without the corresponding events, or events claiming a completed operation whose balances were not changed.
- Event and product snapshot reads are stable under cursor pagination: continuing from a cursor must not silently skip or repeat records in the same query view.
- All identifiers and event payloads represent synthetic bootcamp data. Real personal data, real account numbers, bank credentials, and API secrets are excluded from events and example requests.
- Product snapshots expose source attribution and retrieval time so participants can account for staleness and reproduce historical comparisons.
- The service and supporting telemetry stack are deployable in AWS. The MariaDB instance and telemetry administration endpoints are not publicly exposed.
- Operational event logs carry the same stable event ID as the MariaDB record. Loki delivery is for observability and pipeline exercises; the MariaDB event API remains authoritative if log delivery is delayed or duplicated.

## User experience and behavior

- All product interactions use JSON REST endpoints under `/v1`; there is no customer-facing dashboard.
- The interactive API documentation is available at `/docs` and uses an OpenAPI schema generated from the service contract.
- Sandbox partner credentials are configured for the bootcamp environment. Credentials are sent through an authorization header, are never returned by read endpoints, and are never written to event payloads.
- Standard errors use a stable JSON shape with a machine-readable code and message. Invalid input returns `400`, unknown resources return `404`, and business conflicts such as insufficient funds or idempotency-key reuse return `409`.
- Every accepted write returns its primary resource identifier and the event identifiers created by that operation. A repeated idempotent request returns the original result.
- Event consumers use polling and cursor pagination. The API does not promise streaming or immediate downstream delivery.
- Product responses identify the catalog snapshot timestamp. If a product source is unavailable or a field is not published, the API reports stale or unknown data rather than filling it with an estimate.
- Operators inspect service logs and metrics in authenticated Grafana dashboards. The Grafana, Loki, Prometheus, and MariaDB interfaces are private to the AWS bootcamp environment.
- FastAPI serves `/docs`, `/openapi.json`, `/healthz`, and a private `/metrics` endpoint. The MVP has no frontend and no Nginx API proxy.

## Architecture and design

- Implement one FastAPI application service backed by MariaDB. Persist current simulated account/loan/payment state alongside immutable business event records; state projections may be updated, but event records are append-only.
- Commit balance changes, primary resource state, idempotency results, and corresponding events in one MariaDB transaction.
- Keep a source adapter for each configured bank page. Run the refresh as a bounded scheduled batch in the AWS environment; prevent duplicate concurrent refreshes when the API is scaled. A source failure preserves the last known snapshot and records refresh health without deleting prior data.
- Store product snapshots immutably and reference a specific snapshot ID from each recommendation result.
- Emit structured FastAPI logs to stdout. Run Grafana Alloy as a collector that forwards application logs to Loki; expose application metrics for Prometheus scraping; configure Grafana dashboards over those data sources.
- Keep business-event retrieval through the MariaDB-backed pull API. No broker, webhook delivery, or separate business worker service is required by this specification.
- Deploy the API, database, and telemetry services in AWS with private networking for MariaDB and telemetry administration. Exact AWS service placement, region, and deployment automation are selected in the implementation plan after owner review.
- Nginx is out of the MVP request path. When a frontend is added in a later change, Nginx serves its static assets only and does not proxy API requests.

## Interfaces, data, and dependencies

### API resources

| Method and path | Purpose |
|---|---|
| `POST /v1/sandbox/seed` | Create or reuse synthetic customers, accounts, and merchants for a bootcamp sandbox. |
| `POST /v1/sandbox/generations` | Generate reproducible transaction, loan, recommendation, and checkout scenarios. |
| `GET /v1/accounts/{accountId}` | Read a synthetic account and its current simulated balance. |
| `POST /v1/accounts/{accountId}/deposits` | Simulate a deposit and append its event. |
| `POST /v1/accounts/{accountId}/withdrawals` | Simulate a withdrawal and append its event or rejection event. |
| `POST /v1/transfers` | Transfer simulated funds between Podobank accounts. |
| `GET /v1/loan-products` | Read current or historical product snapshots. |
| `POST /v1/loan-recommendations` | Compare products for a synthetic profile and append a recommendation event. |
| `POST /v1/loans` | Create a simulated application and deterministic outcome. |
| `POST /v1/payments` | Initiate a partner-requested simulated bank-transfer payment. |
| `GET /v1/payments/{paymentId}` | Read the payment's simulated status and partner reference. |
| `GET /v1/events` | Poll append-only events with filters and cursor pagination. |
| `GET /healthz` | Return service health for AWS health checks without exposing secrets or customer data. |
| `GET /metrics` | Expose service metrics for private Prometheus scraping; never include per-record identifiers as labels. |

### Event envelope

Each event contains `eventId`, `schemaVersion`, `eventType`, `occurredAt`, `recordedAt`, `correlationId`, applicable entity IDs, and a typed `data` object. Timestamps use UTC ISO 8601. Monetary values use integer minor units with an explicit currency; for the MVP, currency is `KRW` and the value is whole won.

Minimum event types are `customer.created`, `account.opened`, `deposit.completed`, `withdrawal.completed`, `transfer.completed`, `transaction.rejected`, `loan.recommendation.generated`, `loan.application.created`, `loan.application.rejected`, `loan.disbursement.completed`, `payment.initiated`, `payment.completed`, and `payment.failed`. Events belonging to one user-visible operation share a correlation ID.

### Product snapshot

Each product snapshot has an immutable snapshot ID, stable product reference when identifiable, institution and product names, normalized published fields, source URL, retrieved timestamp, optional effective date, and source status. Missing fields are nullable and accompanied by an availability status; recommendation code must distinguish unknown data from a negative match.

### Dependencies

- Official public product pages from the first-tier bank allowlist are the only source for actual bank product facts in the MVP.
- Product retrieval is periodic and may be stale between refreshes. No customer-specific bank API, FSS API storage, credit bureau, payment gateway, or real financial account is a dependency.
- The service requires MariaDB for transactional state and event persistence, Grafana Alloy for telemetry collection, Loki for logs, Prometheus for metrics, and Grafana for operator dashboards.
- AWS is the target runtime. The exact AWS deployment service, region, and infrastructure-as-code approach are selected in the implementation plan.
- Nginx is reserved for serving a future frontend and is not required to serve the MVP API or its FastAPI documentation.

## Security, privacy, and policy constraints

- Use synthetic profiles and credentials only. Do not collect or persist real customer identity, real credit reports, real account credentials, or production payment data.
- Do not expose secrets in OpenAPI examples, events, error responses, or logs.
- Keep MariaDB, Loki, Prometheus, and Grafana administration endpoints private within the AWS environment. Inject deployment secrets from an AWS-managed secret store rather than committing them.
- Avoid sensitive or high-cardinality metric labels. Structured Loki records contain only synthetic business data and operational diagnostics.
- Product retrieval is limited to public official pages and must honor source-specific access conditions. Do not bypass authentication, anti-bot controls, or access restrictions.
- Clearly label product comparisons, recommendations, balances, loan outcomes, and partner payments as simulated and non-binding.
- Do not implement fraud detection, anomaly classification, real credit underwriting, or real payment processing.

## Risks and concerns

- Bank pages may change structure or omit fields. Keep source-specific parsers, retain the last known snapshot, expose source freshness, and leave unavailable facts unknown.
- Publicly displayed loan rates and eligibility may depend on a real borrower's circumstances. Recommendations must show the published range and source time and must not imply a personalized bank quote or approval.
- Scenario-generated events can be mistaken for real activity if examples omit simulation labels. Mark the API documentation, event envelope, and generated records as synthetic.
- A partial failure during a transfer or payment could produce inconsistent state and logs. Atomic persistence is an acceptance requirement.
- Loki delivery can lag or duplicate a committed event log. Keep MariaDB authoritative and include stable event IDs in Loki records.
- The AWS telemetry stack adds hosting and storage cost. The implementation plan must define bounded retention and a bootcamp-sized deployment footprint.

## Acceptance criteria

1. A sandbox can create synthetic customers, accounts, and merchants, and the scenario API can produce each required event family with reproducible business inputs for a given seed.
2. Deposit, withdrawal, and transfer requests update simulated balances only on success and append matching immutable events atomically. Insufficient-funds requests leave balances unchanged and append a rejection event.
3. Repeating a successful mutation with the same idempotency key does not create a second operation or duplicate its business events; using the key for a different request returns a conflict.
4. The catalog contains normalized snapshots retrieved from the configured official first-tier bank pages. Every snapshot exposes source URL and retrieval time; historical snapshots remain addressable after refresh, and unavailable fields remain unknown.
5. A recommendation response is deterministic for the same profile and catalog snapshot, includes match/unknown explanations and source timestamps, and appends a `loan.recommendation.generated` event referencing that snapshot.
6. Simulated loan applications produce application and outcome events; a disbursement updates only a synthetic account and commits its account and loan events atomically.
7. A partner payment produces initiation and completion or failure events with a shared correlation ID. Successful payments move only synthetic balances; retries are idempotent; no external payment rail is called.
8. The event API supports cursor pagination and the specified filters, and related flow events can be joined by IDs and correlation ID.
9. `/docs` provides interactive English API documentation with working synthetic examples for every public endpoint in this specification.
10. No feature performs real anomaly detection, real credit decisions, real account access, real lending, or real payment settlement.
11. The API and telemetry stack run in the selected AWS environment with MariaDB as the persistent event and simulation store; MariaDB and telemetry administration endpoints are not publicly reachable.
12. Every committed domain event produces a structured log record with the same event ID and correlation ID; Alloy delivers it to Loki, where it can be queried in Grafana. Prometheus scrapes the private metrics endpoint, and Grafana displays the service metrics.
13. The MVP contains no frontend. Nginx does not serve or proxy the API; it is reserved for static frontend hosting in a later change.

## Open questions

- Which first-tier Korean banks should be included in the initial source allowlist? The implementation plan must select only sources with public product pages and a workable access policy.
- Which AWS deployment topology and region should the implementation use, and what bootcamp budget and retention period should bound the Loki/Prometheus/Grafana footprint?
