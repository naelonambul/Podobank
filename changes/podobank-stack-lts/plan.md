# Implementation Plan

## Summary

Align the versions currently configured for the API and MariaDB with the latest
upstream LTS line where one exists, otherwise use the current supported stable
release. Make the API image install the exact packages from `uv.lock`, and
record the project's whole-stack target versions, including UI and
observability tools that will be configured in later phases. This change does
not add Vue, Nginx, Alloy, Loki, Prometheus, or Grafana services before their
planned phases.

Version audit date: 2026-11-01. Exact version pins are intentional and should
be re-audited when a later phase adds or changes a service.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `docs/stack-versions.md`: record the formal LTS or stable-channel decision
  for every technology in the selected stack.
- `compose.yaml`: change the MariaDB image from `11.8.9` to `12.3.3`; preserve
  Oracle SQL mode and all current database settings.
- `Dockerfile`: change the Python base image from `3.13-slim` to
  `3.15.2-slim`, copy the pinned uv `0.13.6` binary from its official image,
  and install the API with `uv sync --locked --no-dev --no-editable` so the
  container uses `uv.lock` instead of resolving the open `pyproject.toml`
  ranges independently. Add `/app/.venv/bin` to `PATH` for the existing API
  command.
- `pyproject.toml`: require Python `>=3.15,<3.16` and set Ruff's target to
  `py315`. Keep dependency constraints unless the lock audit finds an
  incompatibility.
- `backend/podobank_api/settings.py`: remove quotes from the `Settings`
  self-reference return annotation; the `py315` target makes Ruff's UP037
  check require this syntax, and Python 3.15 lazily evaluates annotations.
- `backend/podobank_api/features/auth/passwords.py`: use Ruff's canonical
  Python 3.15 formatting for the existing multiple-exception `except`
  clauses. The `py315` target enables this syntax, which is supported by the
  project's minimum runtime and required for the registered format check.
- `uv.lock`: regenerate for the Python 3.15 constraint and update the one
  outdated resolved dependency found by `uv tree --outdated`, `anyio` from
  `4.15.1` to `4.16.0`, using uv `0.13.6` and Python `3.15.2`. The direct
  application dependencies already resolve to current stable versions and do
  not publish separate LTS lines.
- `.github/workflows/repository.yml`: use Python `3.15.2` in each setup-python
  step and MariaDB `12.3.3` in the service container. The owner must author or
  push this workflow change; the agent App cannot push this path.
- `docs/stack-versions.md`: include uv `0.13.6` as the current stable project
  tooling version and document that the API image consumes the lockfile.

## Order of work

1. Update `pyproject.toml`, `backend/podobank_api/settings.py`,
   `backend/podobank_api/features/auth/passwords.py`,
   `docs/stack-versions.md`, and `uv.lock`. Use uv `0.13.6` with Python
   `3.15.2`; prove the lock is current with `uv lock --check` and that no
   packages remain outdated with `uv tree --outdated`.
2. Update `Dockerfile` to use Python `3.15.2-slim`, copy uv `0.13.6` from its
   official image, and install the project with the locked production
   dependencies. Build the image to prove the lock and Python runtime work
   together.
3. Update `compose.yaml` to MariaDB `12.3.3`; preserve Oracle SQL mode and all
   current database settings. Keep the existing named volume intact. Before
   anyone starts 12.3.3 against an existing 11.8.9 volume, require a separate
   backup or an owner-approved development reset.
4. Hand off `.github/workflows/repository.yml` to the owner for the required
   workflow push, then confirm every Python and MariaDB pin matches the local
   runtime pins. Do not attempt an App push that touches this file.
5. Run the full registered verification against a disposable MariaDB 12.3.3
   test database with no persistent volume, then review the final diff before
   closing the change.

The later stack targets recorded in the version matrix are: Node.js `26.13.0`
LTS, Vue `3.5.44` stable, Nginx `1.30.6` stable, Grafana Alloy `1.21.3`, Loki
`3.7.9`, Prometheus `3.13.3` LTS, and Grafana `13.3.0` on its supported patch
line. Re-check upstream support and patch levels before creating those service
configs.

## Tests and proof

- `uv lock --check`
- `uv tree --outdated` (expected: no outdated packages)
- `docker build --tag podobank-api:lts-check .`
- `docker compose config --quiet`
- Confirm official image tags for Python `3.15.2-slim` and MariaDB `12.3.3`.
- Confirm CI pins match `Dockerfile`, `pyproject.toml`, and `compose.yaml`.
- Run `python3 scripts/repo.py verify --change podobank-stack-lts --full`
  against a disposable MariaDB `12.3.3` database after implementation; the
  change cannot close with blocked or not-run checks.

## Risks and mitigations

- Python `3.15.2` is a new stable release, not a separately named LTS line.
  Resolve and install the lock with uv `0.13.6` on Python `3.15.2`; retain the
  current constraints only when their package metadata supports that runtime.
- MariaDB `12.3.3` is a newer major LTS series. Compose uses a persistent named
  volume. A version-only rollback is unsafe after 12.3 has modified that data
  directory because major-version downgrades are not officially supported.
  Take a backup before upgrading an existing volume; if rollback is required,
  restore that backup to a fresh volume or recover forward. Never remove or
  reuse the upgraded volume as an 11.8 database as part of this change.
- The MariaDB image is currently already on LTS `11.8.9`; this change selects
  the newer `12.3.3` LTS, not an unsupported release.
- MariaDB documents `innodb_snapshot_isolation=ON` as the default from 11.6.2
  onward, so the current 11.8.9 and proposed 12.3.3 already share that default.
  This upgrade does not newly enable it; the transaction change still needs to
  follow and validate its lock-first design separately.
- Grafana, Vue, Nginx, Loki, Alloy, FastAPI, and the Python libraries do not
  publish a single formal LTS track. The version matrix labels their upstream
  stable/support policy instead of calling them LTS.

MariaDB's [major-version downgrade guidance](https://mariadb.com/docs/server/server-management/install-and-upgrade-mariadb/downgrading-between-major-versions-of-mariadb)
does not support in-place downgrades. The Docker installation follows uv's
[official Docker integration](https://docs.astral.sh/uv/guides/integration/docker/)
and locks production dependencies with `uv sync --locked`.

## Rollback or recovery

If the Python 3.15 runtime cannot be supported, revert its runtime image,
metadata, lock, Ruff target, and workflow pins together. If MariaDB 12.3 must
be rolled back after starting against an existing data directory, restore the
pre-upgrade backup into a fresh MariaDB 11.8 volume. Do not start MariaDB 11.8
on the modified 12.3 data directory. For disposable development data, use only
an owner-approved reset.

## Open questions

None. The approved policy is latest formal LTS where published, otherwise the
current supported stable release, with an explicit re-audit before later stack
phases.
