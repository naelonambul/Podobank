# MongoDB Event Flow Diagram Design

## Intent

Clarify the event-flow diagram in `docs/operations/observability-and-events.md`. It currently draws `client_events` and `financial_events` as two MongoDB cylinders, which can be read as two MongoDB deployments even though both collections use the same `mongo` service and `podobank_events` database.

## Goals

- Show one MongoDB service/database boundary.
- Keep `client_events` and `financial_events` visibly distinct as collections with different producers and write timing.
- Keep the JSONL observability path visually independent from MongoDB writes.
- Make Grafana's read-only relationship to Loki and Prometheus explicit.

## Proposed approach

Draw one MongoDB boundary labeled `MongoDB · podobank_events`, with two plain collection nodes inside it: `client_events` and `financial_events`. Route browser events through `POST /events` and FastAPI to `client_events`. Route successful API and repayment CLI financial operations from their MariaDB commit to `financial_events`, labeled as one best-effort write. Keep API/CLI JSONL output on a separate path through Alloy to Loki and Prometheus, with Grafana reading those two observability stores.

## Alternatives considered

1. **One MongoDB boundary with two collection nodes (proposed):** shows the shared service/database while preserving the two event contracts and producers.
2. **Two collection cylinders inside a shared MongoDB boundary:** requires a smaller edit, but still repeats the database-shaped symbol and may retain the visual confusion.
3. **Separate diagrams for browser and financial events:** gives each flow more space but makes it harder to compare the two MongoDB collections and the independent observability path together.

## Constraints and non-goals

- Treat `compose.yaml`, backend event writers, frontend router/telemetry, and the observability configuration as the source of truth.
- Do not change event schemas, collection names, write timing, best-effort guarantees, data retention, or runtime behavior.
- Do not add another MongoDB service, combine the collections, or route browser events through the financial-event writer.
- Keep the change limited to the Mermaid diagram in the operations manual unless source review proves another documentation statement is materially misleading.

## Source facts checked

- `compose.yaml` configures one `mongo` service, `MONGO_DB_NAME=podobank_events`, and one persistent `mongodb_data` volume.
- `backend/podobank_api/features/client_events/api.py` handles `POST /events`; its MongoDB writer inserts into `client_events`.
- `frontend/src/router.js` sends automatic `page_view` events through the shared telemetry module.
- `backend/podobank_api/features/financial_events/mongodb.py` inserts into `financial_events`; transaction and loan services call it after their MariaDB work has committed. The repayment CLI uses the loan service path.
- API and CLI operational events also go to JSONL; Alloy reads JSONL and sends logs to Loki while exposing metrics for Prometheus. Grafana reads Loki and Prometheus.
