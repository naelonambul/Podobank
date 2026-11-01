# Implementation Plan

## Summary

Set the supported project runtime to Python 3.13 and pin CI and the API image to
Python 3.13.18, the latest 3.13 security release as of 2026-11-01. Keep the
dependency constraints unless a package cannot resolve on Python 3.13. Update
the two source files whose current annotation or exception syntax depends on
Python 3.15 behavior. This change does not alter API behavior or database data.

Python 3.13 receives security fixes through October 2029. Python 3.13.18 is a
source-only security release; official binary installers ended with 3.13.17.
The project accepts any Python 3.13 patch release for local development, while
the official Docker image and GitHub Actions use the exact 3.13.18 patch.
Version facts were checked against the [Python release page](https://www.python.org/downloads/release/python-31318/),
the [Python support schedule](https://devguide.python.org/versions/), the
[official Python image manifest](https://github.com/docker-library/official-images/blob/master/library/python),
and the [GitHub Actions Python manifest](https://github.com/actions/python-versions/blob/main/versions-manifest.json).

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `pyproject.toml`: accept Python `>=3.13,<3.14` and set Ruff's target to
  `py313`.
- `uv.lock`: regenerate the lock for the Python 3.13 constraint with uv
  `0.13.6` and Python `3.13.18`. Preserve the resolved package versions
  unless the resolver demonstrates a compatibility issue.
- `Dockerfile`: use the official `python:3.13.18-slim` image and retain the
  existing locked production install.
- `.github/workflows/repository.yml`: change each of the four
  setup-python pins to `3.13.18`. This path requires the owner push handoff
  described below; the App cannot push workflow files.
- `backend/podobank_api/settings.py`: quote the `Settings` return annotation
  so Python 3.13 can evaluate it.
- `backend/podobank_api/features/auth/passwords.py`: use tuple syntax for
  both multiple-exception handlers, which Python 3.13 supports.
- `docs/stack-versions.md`: record Python 3.13.18, its security-only support
  stage, and the local patch-version range.

## Order of work

1. Update `pyproject.toml`, `backend/podobank_api/settings.py`,
   `backend/podobank_api/features/auth/passwords.py`, and
   `docs/stack-versions.md`. Confirm the application and scripts parse under
   Python 3.13 with `python3.13 -m compileall -q backend scripts`.
2. Regenerate `uv.lock` with uv 0.13.6 and Python 3.13.18. The current host
   has uv 0.12.7, so use the project-pinned 0.13.6 tool image or an approved
   install rather than writing the lock with the older version. Confirm the
   resulting lock is current with `uv lock --check`; investigate any
   dependency that cannot resolve for Python 3.13 before changing package
   versions.
3. Change `Dockerfile` to Python 3.13.18 and build the image with
   `docker build --tag podobank-api:python313-check .`. This verifies the
   official image, lockfile, and installed runtime together.
4. Change the four Python pins in `.github/workflows/repository.yml`.
   Confirm the entries with
   `rg -n 'python-version: "3.13.18"' .github/workflows/repository.yml`.
   Commit the workflow change separately with `agent-git`, after the other
   implementation commits. Run full verification on that tree, create the
   closure, and commit the closure on top. Give the owner the workflow commit
   SHA and stop for the owner to push through that SHA. Afterward, confirm the
   remote branch points to that SHA, then push the closure and open the PR
   with `agent-gh`. The agent's closure push remains the last push.

## Tests and proof

- `python3.13 -m compileall -q backend scripts`
- Confirm `uv --version` reports `0.13.6` before lock operations.
- `uv lock --check`
- `docker build --tag podobank-api:python313-check .`
- Confirm all four setup-python entries use Python 3.13.18.
- Run `python3 scripts/repo.py verify --change podobank-python313-runtime --full`
  against the registered disposable MariaDB test database. All registered
  checks must pass with no blocked or not-run checks before closure.
- Run `python3 scripts/repo.py status --change podobank-python313-runtime`
  before implementation and again before closure.

## Risks and mitigations

- Python 3.13 is in security-only support and releases are irregular. Pin the
  newest patch for CI and the image, allow any 3.13 patch locally, and re-audit
  the patch when updating the stack matrix.
- Python 3.13.18 has no upstream Windows or macOS binary installer. Python
  3.13.17 was the last 3.13 release with those installers; local environments
  can use an installed 3.13 patch or a source-building version manager.
  Official manifests list Python 3.13.18 artifacts for GitHub Actions and
  Docker; the build and CI checks confirm those artifacts work for this
  repository.
- If locking exposes a dependency that does not support Python 3.13, report
  the required package change and its compatibility evidence before making a
  broader dependency update.
- The workflow permission boundary requires an owner push. Keep the workflow
  commit separate, follow the handoff order above, and do not ask the App to
  push that commit.

## Rollback or recovery

Revert the changes in this packet to restore the previous Python 3.15.2
configuration. The change introduces no database migration or persistent data
format change.

## Open questions

None.
