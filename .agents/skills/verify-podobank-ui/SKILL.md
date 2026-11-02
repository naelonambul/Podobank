---
name: verify-podobank-ui
description: Launch, inspect, drive, and clean up an isolated Podobank mobile web application.
---

# Verify Podobank UI

The primary user surface is the mobile Vue application at 384 × 832 pixels. It calls the isolated FastAPI service directly; Nginx serves the application and its client-side routes.

## Launch

From the repository root, run:

```sh
python3 scripts/verify_ui.py --launch
```

The verifier creates a uniquely named Compose project, a temporary environment file, a new database, local customer and employee credentials, and an overdue repayment fixture. It chooses unused loopback ports, builds the API and frontend, initializes the database, and prints a private run-file path. The run file is needed for Doctor, Drive, and Cleanup. Do not copy it into the repository or share it; it contains temporary test credentials.

The command exits only after the API health endpoint and the served Vue application respond. It does not use the developer's normal Compose project or database.

## Doctor

Use the run-file path printed by Launch:

```sh
python3 scripts/verify_ui.py --doctor --run-file /tmp/podobank-ui-<id>-<suffix>/run.json
```

Doctor confirms that the run's `db`, `api`, and `frontend` services are running, that their published ports match the run file, and that the API health endpoint and frontend document respond.

## Drive

Run the mapped browser paths against the isolated instance:

```sh
python3 scripts/verify_ui.py --drive --run-file /tmp/podobank-ui-<id>-<suffix>/run.json
```

Playwright uses Chromium with a 384 × 832 viewport. On Linux, the runner uses the version-matched Playwright container and host networking. On other platforms, install Node.js 26.13.0 dependencies and Chromium, then set `PODOBANK_UI_TEST_RUNNER=host` for the command. The tests log in through the UI and assert the session cookie, DOM state, account balance, ledger rows, loan schedule and persisted review or repayment result. They check for horizontal overflow and save screenshots for each flow.

Run Doctor again after a failed or unexpected Drive before retrying.

## Evidence

The verifier keeps evidence under `.evidence/ui/<run-id>/`. It includes mobile screenshots, a sanitized fixture summary, and Playwright failure output, traces, or screenshots when a browser test fails. Cleanup does not remove this evidence.

## Cleanup

Stop only the isolated project identified by the run file:

```sh
python3 scripts/verify_ui.py --cleanup --run-file /tmp/podobank-ui-<id>-<suffix>/run.json
```

Cleanup removes that project's containers, network, volumes, and temporary environment and credentials. Do not use `docker compose down` without the verifier's project name and environment file. The one-command `python3 scripts/verify_ui.py --smoke` performs Launch, Doctor, Drive, and Cleanup in sequence.
