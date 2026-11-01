# Implementation Plan

## Summary

Configure the CI `verify-mariadb` service to start MariaDB with the SQL mode `ORACLE,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION`, matching the mode required by backend verification.

## Files and components that change

- `.github/workflows/repository.yml`: add the matching `--sql-mode=...` argument under `jobs.verify-mariadb.services.mariadb.command`.

## Order of work

1. Add `command: --sql-mode=ORACLE,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION` to `jobs.verify-mariadb.services.mariadb` in `.github/workflows/repository.yml`.
2. Run `docker compose config --quiet`.
3. Run `APP_ENV=test DATABASE_URL=mysql+pymysql://podobank:podobank-test@127.0.0.1:3306/podobank_test python3 scripts/repo.py verify --change ci-mariadb-oracle-sql-mode --full` and require a complete run with every registered check passed.

## Tests and proof

- `docker compose config --quiet` validates the Compose configuration without starting services.
- The full registered verification above must pass. Its backend validator requires `APP_ENV=test` and the isolated `podobank_test` database.
- Inspect the changed files, run `python3 scripts/repo.py status --change ci-mariadb-oracle-sql-mode`, and close the packet with the full-run evidence.

## Risks and mitigations

- The SQL mode argument must be passed to the MariaDB server at service startup. Keep it on the `mariadb` service's `command` and confirm the backend verification succeeds.

## Rollback or recovery

Remove the added `command` line from `.github/workflows/repository.yml`, then rerun the applicable registered verification before closing a replacement packet.

## Open questions

None.
