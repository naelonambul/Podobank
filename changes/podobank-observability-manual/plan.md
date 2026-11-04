# Implementation Plan

## Summary

Add a Korean operator manual for the existing Grafana, Prometheus, Loki, and MongoDB event paths. Explain the three distinct flows so operators can locate the right record without treating a dashboard metric, a financial event, and a browser event as the same data.

## Files and components that change

- `docs/operations/observability-and-events.md`: access and query instructions for the pre-provisioned Grafana dashboard, Prometheus-backed metrics, Loki logs, and both MongoDB collections.
- `README.md`: add a link to the operator manual beside the existing architecture and user manual links.

## Order of work

1. Write `docs/operations/observability-and-events.md` from the checked-in Compose, Grafana, Alloy, Prometheus, Loki, API, repayment CLI, and frontend configuration. Cover: Grafana's loopback-only access and SSH tunnel; the PodoBank dashboard and its PromQL/LogQL panels; Prometheus and Loki retention; MongoDB's `financial_events` and `client_events` collections, example read-only `mongosh` queries, data shape, best-effort behavior, storage retention, and privacy guidance. Include a small flow diagram that distinguishes JSONL → Alloy → Loki/Prometheus → Grafana, successful API and repayment CLI operations → `financial_events`, and browser events → `/events` → `client_events`.
2. Add the manual link in `README.md`. Confirm the dashboard title, metric and log queries, port bindings, retention values, collection names, and event fields against the source files named in step 1.
3. Review Markdown links and commands, run `git diff --check`, and run `python3 scripts/repo.py status --change podobank-observability-manual`.

## Tests and proof

- Run the exact checks in order of work step 3 and inspect the final diff against `README.md`, `compose.yaml`, `monitoring/**`, and the two event features.
- This documentation-only change does not alter or restart services and does not query live MongoDB data.
- Do not run the application test suite unless separately requested. If full repository verification is required for closure, ask the owner before running it.

## Risks and mitigations

- The two MongoDB collections and the observability pipeline have different producers and guarantees. Give each a separate section and show them as separate paths; include the repayment CLI's successful batch events in `financial_events`.
- Client event properties can contain arbitrary bounded JSON. Tell operators not to add or export passwords, credentials, account identifiers, customer details, or real transaction data.
- Prometheus, Loki, and MongoDB have no published host ports. Keep examples inside the active Compose project and do not recommend exposing internal ports publicly.
- MongoDB event collections currently have no TTL retention policy. State that their data persists in `mongodb_data` and caution against volume-removal commands.

## Rollback or recovery

Remove the manual and its README link. There are no runtime, schema, dashboard, datasource, or service changes to roll back.

## Open questions

None. The current repository configuration defines the access boundaries, fields, and retention behavior.
