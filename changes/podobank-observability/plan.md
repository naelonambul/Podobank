# Implementation Plan

## Summary

Add the development observability stack defined in the approved specification. FastAPI and the repayment CLI will write privacy-safe JSONL financial events to a dedicated named volume. Grafana Alloy will tail the file, send events to Loki, derive a bounded-label Prometheus counter, and expose the counter on its internal metrics endpoint. Grafana will provision both data sources and a financial-operations dashboard. The change adds no database tables or Python runtime dependencies.

## Files and components that change

- `compose.yaml`: add Alloy, Loki, Prometheus, and Grafana; add isolated named volumes, health checks, internal-only monitoring ports, loopback-only Grafana binding, and a configurable Compose env-file path for isolated verification.
- `Dockerfile`: create the financial-event directory with write permissions for the existing non-root API user.
- `.env.example`: add local Grafana credentials and monitoring port settings.
- `docs/stack-versions.md`: recheck and record the exact supported image versions before implementation.
- `monitoring/**`: Alloy file-tail, JSON parsing, Loki forwarding, and metrics pipeline; Loki storage/retention; Prometheus scrape and retention; Grafana data-source/dashboard provisioning and dashboard JSON.
- `backend/podobank_api/features/observability/**`: add an idempotent JSONL event logger with a fixed event schema and best-effort behavior.
- `backend/podobank_api/app.py`, `backend/podobank_api/cli.py`: configure the event logger for API and scheduled repayment CLI processes.
- `backend/podobank_api/features/transactions/service.py`, `backend/podobank_api/features/loans/service.py`: emit one result event per service operation, using static operation/outcome/reason values and only repayment-batch counts as optional numeric fields.
- `backend/tests/test_observability.py`: cover event encoding, UTC timestamp, bounded field set, and exclusion of sensitive values.
- `scripts/verify_observability.py`: validate Compose configuration and run an isolated Compose smoke test that produces an API event and a repayment-CLI event, then verifies their presence in Loki, the derived Prometheus counter, and Grafana provisioning. The script must use a temporary env file and unique project name, and always tear down only that project and its volumes.
- `checks.json`: register the observability smoke test in the existing `mariadb` group, which already runs on a Docker-enabled CI job. Do not edit `.github/workflows/**` or create a new CI group.
- `README.md`: document startup, Grafana access, the dashboard, retention, event-file volume behavior, and the smoke-check command.

`pyproject.toml`, `uv.lock`, and `scripts/verify_backend.py` remain unchanged: event encoding uses the standard library, and the current backend test discovery already includes the new test module.

## Order of work

1. Recheck the selected Alloy, Loki, Prometheus, and Grafana releases against their upstream support/release pages. Add the Compose services, volumes, ports, and monitoring configuration in `compose.yaml`, `Dockerfile`, `.env.example`, `docs/stack-versions.md`, and `monitoring/**`. Keep the existing API and database behavior intact. Prove configuration resolution with `COMPOSE_ENV_FILE=.env.example docker compose --env-file .env.example config --quiet`.
2. Implement the event encoder/configuration in `backend/podobank_api/features/observability/**`; initialize it in `app.py` and the repayment CLI path in `cli.py`; instrument the two service `_run` paths without changing financial transaction behavior. Add focused privacy/schema tests in `backend/tests/test_observability.py`. Prove the backend suite with `APP_ENV=test DATABASE_URL=mysql+pymysql://podobank:podobank-test@127.0.0.1:3306/podobank_test python3 scripts/verify_backend.py --suite mariadb`.
3. Implement `scripts/verify_observability.py`, register its isolated runtime smoke check in `checks.json`, and document how to run the stack in `README.md`. The smoke must use only its generated project and volumes, create a demo event through the existing service and one batch event through `podobank-api process-repayments`, poll Loki and Prometheus until both are visible or time out, check the provisioned Grafana data sources/dashboard, and clean up in a `finally` path. Prove it with `python3 scripts/verify_observability.py --smoke`.
4. Review all changed files against `REVIEW.md`, confirm every touched file is within `write_scope`, then run `python3 scripts/repo.py status --change podobank-observability` and `python3 scripts/repo.py verify --change podobank-observability --full`. Record the complete `.evidence/` result; do not close the packet unless every routed check is complete and passes.

## Tests and proof

- Backend lint, format, and MariaDB suite through the existing `podobank-backend-quality` check; the new unit test is included by its current discovery command.
- `docker compose config --quiet` against `.env.example` to catch missing interpolation, env-file, and service configuration.
- Isolated Compose smoke: start the complete monitoring stack and API with a unique project name and temporary demo credentials; create one deposit event and one empty repayment-batch event; verify both Loki records and corresponding `podobank_financial_operations_total` samples; verify Grafana's provisioned Prometheus/Loki data sources and dashboard; tear down the unique project and its volumes.
- Required final gate: `python3 scripts/repo.py verify --change podobank-observability --full`, with complete evidence under `.evidence/`.

## Risks and mitigations

- The JSONL source volume is intentionally not auto-pruned and can grow. The configuration is development/demo only; document explicit volume cleanup and keep its contents free of personal and financial values.
- Monitoring may be unavailable or the event file may be unwritable. The recorder must contain telemetry errors so they cannot change a committed financial operation's return value or database transaction outcome; missing telemetry remains visible as a verification/runtime issue.
- The smoke test needs Docker Compose and downloads pinned images. Use a unique project name, temporary environment file, dynamically allocated loopback ports, bounded polling, and `finally` cleanup so it does not use or reset the developer's `.env`, database volume, or other Compose project.
- Alloy's derived metric label values must come only from the event's finite code-defined enums. Do not promote event counts, identifiers, amounts, or arbitrary exception strings to labels.

## Rollback or recovery

Run `docker compose down` to stop the added services; this preserves existing database data and monitoring volumes. Revert the change to remove the Compose services and application event configuration. Do not run `down --volumes` against the developer's normal project. The smoke verifier may remove volumes only for the unique project it created.

## Open questions

None for the approved development/demo behavior. Production retention, rotation, and high-availability requirements remain out of scope.
