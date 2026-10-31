# Intent

## Problem

MLOps bootcamp participants need a controllable source of finance-related activity for building and validating data pipelines. Without a realistic event-producing application, they lack connected examples for money movement, loan-product recommendations, and partner checkout flows. Using real accounts or payment rails is outside the camp's purpose.

## Proposed outcome

Podobank is a bank simulator for use inside the bootcamp. It creates synthetic customer, account, loan, and merchant activity and records traceable events for participants' pipelines. The simulated flows cover deposits, withdrawals, transfers between accounts, loan activity and customer-fit loan-product comparisons, and bank-transfer checkout initiated by other camp projects such as a shop.

The product helps participants build their own pipelines for transaction anomaly analysis, loan-recommendation use cases, and payment-flow analysis. Podobank supplies the application flows and event data, provides a synthetic comparison and recommendation result for loan products, and does not perform transaction anomaly detection.

## Affected users and systems

- MLOps bootcamp participants who build and operate pipelines from Podobank events.
- Developers of other camp projects who initiate and inspect simulated bank-transfer payments through an API.
- Bootcamp participants who use Podobank's API and interactive API documentation to generate and inspect event data.
- Synthetic customers, bank accounts, merchants, and loan-product records represented in the simulator.
- Participant-built data pipelines for transaction analysis, loan recommendations, and checkout-flow analysis.

## Constraints

- All accounts, deposits, withdrawals, transfers, loans, and partner payments are fictional and remain inside the bootcamp environment.
- The application does not connect to real financial accounts, move real funds, or settle real payments.
- Synthetic customer data is used for generated activity and recommendation scenarios.
- Actual first-tier Korean bank loan-product information is needed for product comparison and synthetic customer-fit recommendations. The MVP will periodically collect publicly displayed product facts from official bank pages, store normalized snapshots with source URLs and retrieval timestamps, and honor source-specific access conditions. It will not use customer-specific eligibility or quote flows.
- The first version exposes an API with interactive API documentation and has no human-facing dashboard.
- The service is a single application with append-only event records; it does not use a message broker or microservices.
- Useful, traceable event data is a primary product outcome. Fraud or anomaly detection itself is not part of Podobank.

## Out of scope

- Real banking, payment, or settlement integrations.
- Real customer onboarding, credit decisions, loan disbursement, or repayment.
- Implementing transaction anomaly or fraud detection in Podobank.
- Building the participants' downstream data pipelines.

## Success criteria

- Participants can generate synthetic deposit, withdrawal, account-transfer, loan, recommendation-related, and partner-payment activity.
- A camp project can initiate a simulated bank-transfer payment through an API and follow its outcome within the simulated flow.
- Generated events are traceable across related operations and contain the information needed to build pipelines for transaction analysis, loan recommendations, and payment-flow analysis.
- The simulator can generate useful activity without real accounts, real funds, or real payment processing.
- Participants can retrieve generated events and their relationships through the API for non-real-time pipeline ingestion.
- Synthetic loan comparison and recommendation responses identify the actual public product snapshot and the synthetic profile inputs used.

## Open questions

- Which first-tier banks will be included in the initial catalog, and what periodic refresh cadence is appropriate?
