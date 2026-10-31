# GitHub-hosted CI proof

Evidence for the plan's "GitHub-hosted CI proofs" item. The proofs ran on 2026-09-23 in a disposable public repository, `naelonambul/sdlc-template-ci-proof`. That repository held a copy of this change's tree, including `.github/workflows/repository.yml`, `scripts/repo.py`, and `checks.json`.

That repository is a historical witness only. Nothing in the template depends on it at runtime or at release, and it may be deleted. The run IDs below will stop resolving once it is.

## Setup

`main` in the proof repository had these settings:

- `summary` was the required status check, with strict up-to-date merges;
- the protection applied to admins too;
- merges were squash-only.

Two fixture packets used synthetic `repository`-kind approvals. PR 1 also registered an extra check, `proof-extra`, whose paths were `proof-area/**`.

## Results

| # | Behavior | Run | Outcome |
|---|---|---|---|
| 1 | Push to `main`: full suite and no active change | 35854387249 | success |
| 2 | PR routing: the active change comes from the PR body's `Change-ID:` line. `proof-extra` is reported `not-applicable (no changed path matches…)`. Closure is a `candidate`. | 35854510021 | success |
| 3 | An `edited` PR body with the wrong Change-ID reruns the gate, and the gate fails. | 35854877624 | status, verify-core and summary failed |
| 4 | Restoring the body reruns the gate, and the gate passes. | 35854997273 | success; merge state CLEAN |
| 5 | A failing check (exit 3) reaches the summary. | 35855091308 | failed |
| 6 | A newer push cancels the superseded run. | 35855169327 | cancelled |
| 7 | A check with a missing required executable is blocked, not passed. | 35855192390 | failed (`blocked`); merge state BLOCKED |
| 8 | Strict up-to-date merging: merging a PR that fell behind `main` is refused. | (merge API) | HTTP 405 `Required status check "summary" is expected` |
| 9 | After the PR branch is updated from `main`, the rerun passes and the PR squash-merges. | 35855403300 | success; squash commit `6a853788fd9d6adc02cbbe2b3f8704e6f6db5ccb` |
| 10 | Post-merge push to `main` checks the authoritative closure. | 35855465649 | success; `closure=frozen` with anchor `6a853788fd9d6adc02cbbe2b3f8704e6f6db5ccb`, and the full suite passed |

PR 2 (rows 5–7) was closed without merging.

## Not covered by GitHub-hosted runs

- **Shallow checkout blocks closure resolution.** The workflow always uses `fetch-depth: 0`. A unit fixture in `scripts/tests/test_status.py` covers this case.
