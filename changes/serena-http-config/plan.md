# PodoBank Serena HTTP MCP Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this single-task plan.

**Goal:** Keep the PodoBank Codex project config focused on its named Serena HTTP endpoint.

**Architecture:** `.codex/config.toml` will contain only `serena_podobank` at the existing local URL. This change does not manage the server process.

**Tech Stack:** TOML, Python 3 `tomllib`, and `scripts/repo.py` verification.

**Spec:** `changes/serena-http-config/design.md`

## Global Constraints

- Preserve `serena_podobank` and `http://127.0.0.1:9121/mcp` exactly.
- Do not change Serena startup, process management, application code, or `checks.json`.
- Keep the future global-server interaction risk documented in the design and PR.

## Review Focus

- TOML syntax, table count, server name, and URL: assert the parsed TOML equals the expected single-table value.
- Scope: status and diff checks must show `.codex/config.toml` as the only implementation path.

## Summary

Remove the generic `[mcp_servers.serena] enabled = false` table. Retain the project-specific HTTP server table unchanged.

## Files and components that change

- `.codex/config.toml`: remove only the generic disabled table.
- `changes/serena-http-config/`: retain design and plan; add the candidate closure after verification.

## Order of work

### Task 1: Keep only the project-specific Serena endpoint

**Files:**
- Modify: `.codex/config.toml`

**Interfaces:**
- Consumes the existing `serena_podobank` server name and URL.
- Produces a valid TOML file with exactly that one MCP server table.

- [ ] **Step 1: Run the TOML contract assertion against the base config.**

  Run:
  `python3 -c 'import pathlib, tomllib; cfg = tomllib.loads(pathlib.Path(".codex/config.toml").read_text()); assert cfg == {"mcp_servers": {"serena_podobank": {"url": "http://127.0.0.1:9121/mcp"}}}'`

  Expected: it fails with `AssertionError` because the current file also contains the disabled generic `serena` table.

- [ ] **Step 2: Remove only the generic disabled table from `.codex/config.toml`.**

  Preserve `[mcp_servers.serena_podobank]` and its URL exactly.

- [ ] **Step 3: Re-run the TOML contract assertion.**

  Run the same command as Step 1.

  Expected: exit 0; the parsed value contains only `serena_podobank` at `http://127.0.0.1:9121/mcp`.

- [ ] **Step 4: Check the diff and packet scope.**

  Run: `agent-git diff --check` and `python3 scripts/repo.py status --change serena-http-config`.

  Expected: no whitespace errors; status reports current approvals and no paths outside the packet and `.codex/config.toml`.

- [ ] **Step 5: Run complete repository verification and close the candidate.**

  Run: `python3 scripts/repo.py verify --change serena-http-config --full`.

  Expected: a complete run with every registered check passed. Then run `python3 scripts/repo.py close serena-http-config --evidence <evidence-path>` using the full-run evidence path.

- [ ] **Step 6: Confirm the candidate and commit.**

  Run: `python3 scripts/repo.py status --change serena-http-config`.

  Expected: `stage=closed freshness=current readiness=ready closure=candidate`. Commit the setting, approved packet, and closure with `agent-git`.

## Tests and proof

- No new test file or check-registration change is in scope.
- The `tomllib` contract assertion checks syntax and the exact endpoint; the full repository verification supplies closure evidence.

## Risks and mitigations

- A future user-level server named `serena` may load alongside `serena_podobank` after this override is removed. Document this effect; process-count management is outside scope.

## Rollback or recovery

Before merge, restore the disabled table in a revised, re-approved plan. After merge, use a separate repository change for reversal.

## Open questions

None.
