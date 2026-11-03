# Implementation Plan

## Summary

2026-11-03 `main` push run on merge commit `d760c68e9401622c8c56e3a9daac446f902f5ab2` reproduced a missing repayment event: the deposit event appeared in Loki and Prometheus, but `repayment_batch` appeared in neither and the smoke check timed out. The one-shot `process-repayments` CLI configures the queued logger with `wait_on_exit=False`; its registered exit hook then skips draining the queue. The repayment service returns after enqueueing the event, so the interpreter can stop the listener before it writes the JSONL line.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `changes/repayment-event-flush/spec.md`: clarify that service work stays asynchronous while the one-shot CLI drains its local event queue at process shutdown.
- `backend/podobank_api/cli.py`: enable queue draining when the CLI process exits.
- `backend/tests/test_observability.py`: replace the test that currently codifies skipping CLI shutdown with a regression test that invokes the CLI, queues a repayment event, simulates process shutdown, and verifies the JSONL event was flushed.

## Order of work

1. Use the failing GitHub Actions run on baseline commit `d760c68e9401622c8c56e3a9daac446f902f5ab2` as the real-stack reproduction: `python3 scripts/repo.py verify --group mariadb --full --ci --branch=`. Its output showed `deposit` as present in both sinks, `repayment_batch` absent from both, and the smoke check timing out.
2. In `backend/tests/test_observability.py`, replace `test_cli_process_exit_does_not_wait_for_event_sink` with a deterministic test that invokes the repayment CLI with a temporary event path and mocked database/service, queues a repayment event, simulates the registered process-exit hook, and checks the JSONL file. Run `python3 scripts/repo.py verify --change repayment-event-flush --group mariadb` and confirm the new test fails on the current CLI configuration.
3. In `backend/podobank_api/cli.py`, set `wait_on_exit=True` for `process-repayments` so interpreter shutdown drains the local queue after the service operation returns. Run `python3 scripts/repo.py verify --change repayment-event-flush --group mariadb`; the backend regression and real observability smoke must pass, including the repayment event in Loki and Prometheus.
4. Promote the approved packet spec to root `spec.md`, then run `python3 scripts/repo.py verify --change repayment-event-flush --full`. Close the packet with that complete evidence only when every registered check passes.

## Tests and proof

- Reproduction: the owner-provided CI log for `main` commit `d760c68e9401622c8c56e3a9daac446f902f5ab2` shows the deposit in both sinks and the repayment batch in neither.
- Regression: the backend quality check runs the CLI shutdown test; `podobank-observability-smoke` exercises the real CLI in Compose and confirms both events reach Loki and Prometheus.
- Final proof: `python3 scripts/repo.py verify --change repayment-event-flush --full`; record the resulting evidence file.

## Risks and mitigations

- Waiting for the local queue at process shutdown adds a small delay after the repayment transaction has completed. The service operation itself and its DB transaction remain non-blocking with respect to observability; the CLI does not contact Loki or Prometheus directly.

## Rollback or recovery

- Revert the CLI shutdown setting and the corresponding regression test/spec wording together. This restores the previous shutdown timing but can again drop the final queued repayment event.

## Open questions

- None. The approved spec defines the shutdown flush boundary.
