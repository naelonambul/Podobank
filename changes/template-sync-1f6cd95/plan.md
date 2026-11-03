# Template sync through 1f6cd95

## Summary

This change imports the template's changes `33e5064..1f6cd95` into PodoBank: #47 test-speedup, #48 parallel-tests, #49 ci-dedupe, #50 runner-integrity and #51 class-scheduling.

It is a `repository` change. It does not touch product code, `intent.md` or `spec.md`, and it imports no upstream `changes/` packets.

The template is https://github.com/naelonambul/sdlc-project-template-agent. It is read from its local clone at `/Users/ckh/repos/sdlc-project-template-agent` on this Mac, with `git show 1f6cd95:<file>`. Do not add a remote.

This change is worked on the Mac, in the worktree `/Users/ckh/repos/Podobank-template-sync-1f6cd95`. An earlier attempt on the `oracle` host was stopped and removed. Its `python3` is 3.14, which exposes a template harness defect: under `python3 -m unittest` the in-process `guard.py` names itself `python3 -m unittest`, which fails one test in the sequential path. The registered runner is unaffected. That defect is fixed separately in the template (change `harness-main-spec`) and reaches PodoBank in a later sync. This Mac's `python3` is 3.13, which does not have the defect.

What PodoBank gets:

- The control-plane tests run `repo.py` and `guard.py` in-process. Subprocess and equivalence modes are kept.
- A runner, `scripts/tests/run.py`, is registered as the `control-plane` check. It runs one process per test class. It cannot report success unless every discovered test ran.
- `approve` and `close` close their `git cat-file` child process.
- The CI job `control-plane-tests` runs the runner's own tests first, then the runner. A workflow invariant pins those two commands.

## Source check

Checked at `9121ff9` against the template at `33e5064`, the previous sync point (#10):

- Five files that this range changes are byte-identical in PodoBank at their old version: `scripts/repo.py`, `scripts/README.md`, `scripts/tests/support.py`, `scripts/tests/test_guard.py` and `scripts/tests/test_workflow.py`.
- Three files are new: `scripts/tests/run.py`, `scripts/tests/test_run.py` and `scripts/tests/test_support.py`.
- Only `checks.json` and `.github/workflows/repository.yml` carry PodoBank adaptations.

The template's new workflow invariant (`control_plane_job_findings`) reports no findings on PodoBank's workflow once the job's step is changed as below. The check covered the top-level keys, the top-level `env` keys and the `python-version: "3.13.18"` input.

## Decisions

- **Copy the eight script files byte for byte from `1f6cd95`.** Their PodoBank versions equal the template's old versions, so nothing needs merging.
- **`checks.json`:** change only the `control-plane` check's `argv`, to `["python3", "scripts/tests/run.py"]`. PodoBank's other checks stay as they are, and so do this check's `paths`, timeout and requires.
- **`.github/workflows/repository.yml`:** in `control-plane-tests`, replace the step `run: python3 -m unittest discover -s scripts/tests -t . -v` with two steps:
  - `run: python3 -m unittest scripts.tests.test_run`
  - `run: python3 scripts/tests/run.py`

  Nothing else changes. `python-version: "3.13.18"` stays, and so do the `verify-mariadb` and frontend jobs.
- **Workflow handoff** (`docs/host-setup.md`, "Workflow changes"): the owner's single push of the workflow commit, and nothing past it, is run from this worktree with the owner's plain `git`. The owner gave that instruction for this Mac on 2026-11-03. Everything else uses `agent-git` and `agent-gh`, and the agent pushes the closure last.
- **Known CI cost.** In the template, running one process per class made the CI `control-plane-tests` job slower on 4-vCPU runners: 18s to 29s in one sample. The local run got faster. The owner accepted this trade in the template for its structural benefits. PodoBank inherits it, and its CI durations are reported in the pull request.
- **Host tools for `verify --full`:**
  - PodoBank's `mariadb` and `frontend` groups need Docker. Colima is installed here but stopped. Start it for the run and stop it afterwards, which restores the host's prior state.
  - They also need exactly Node.js v26.13.0 (`scripts/verify_ui.py`, `docs/stack-versions.md`), and this Mac has v22. Download the official `node-v26.13.0-darwin-arm64.tar.gz` from nodejs.org into the session's scratch directory, check it against the release's `SHASUMS256.txt`, and prepend its `bin` to `PATH` for the verify run only. Nothing is installed system-wide.
  - If a check cannot run, report it as `blocked`, do not close, and ask the owner.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- Taken from the template at `1f6cd95` without changes:
  - `scripts/repo.py`
  - `scripts/README.md`
  - `scripts/tests/support.py`
  - `scripts/tests/test_guard.py`
  - `scripts/tests/test_workflow.py`
  - `scripts/tests/run.py`
  - `scripts/tests/test_run.py`
  - `scripts/tests/test_support.py`
- `checks.json`: the `control-plane` argv.
- `.github/workflows/repository.yml`: the `control-plane-tests` steps.

## Order of work

Each step is one coordinator edit, so the route is single agent.

1. Copy the eight files and edit `checks.json`, then commit with `agent-git`. Proof:
   - each of the eight files compares equal (`cmp`) to `git show 1f6cd95:<file>` in the template's local clone;
   - `python3 scripts/tests/run.py` and `python3 -m unittest discover -s scripts/tests -t .` report the same test count, with only `test_workflow`'s new invariant failing until step 2.
2. Edit the workflow and commit it on its own. Proof: `python3 scripts/tests/run.py` passes in full.
3. Start Colima. Run `python3 scripts/repo.py status --change template-sync-1f6cd95`, then `python3 scripts/repo.py verify --change template-sync-1f6cd95 --full` with the Node.js `PATH` above. Stop Colima. Then run `python3 scripts/repo.py close template-sync-1f6cd95 --evidence <path>`, and commit the closure on top. Push nothing yet.
4. Handoff:
   - run `git push origin <workflow sha>:refs/heads/change/template-sync-1f6cd95` with the owner's git;
   - confirm with `agent-gh ls-remote` that the branch head is that SHA;
   - `agent-gh push` the closure commit, and open the pull request with `Change-ID: template-sync-1f6cd95`.
5. Confirm with `agent-gh pr checks` that every check passes, and that the bot is the author and the last pusher. The owner reviews, approves and merges. After the merge, confirm the `push` run with `agent-gh run list`.

## Tests and proof

- **Byte identity:** each copied file equals the template's file at `1f6cd95`.
- **Same tests:** the runner and `unittest discover` pass with the same count. The runner also passes with `-W error::ResourceWarning`.
- **Speed:** the PodoBank control-plane suite before the change (`unittest discover` at `9121ff9`) and after it (the runner), on this Mac. Reported, not gated.
- `python3 scripts/repo.py status --change template-sync-1f6cd95` passes.
- `python3 scripts/repo.py verify --change template-sync-1f6cd95 --full` reports no `failed`, `blocked` or `not-run` check.
- **CI:** the pull request's `repository` run is `success`, and the `control-plane-tests` duration is reported.

## Risks and mitigations

- **Riskiest step: the handoff.** If the owner's push goes past the workflow SHA, the owner becomes the last pusher. Mitigations:
  - the refspec names exactly one SHA;
  - the remote head is checked before the agent pushes.
- **PodoBank's product checks need Docker and Node.js, and can take up to 25 minutes.** A check that cannot run is reported as `blocked`, never as passed.
- **`main` moves during the handoff.** The App cannot rebase the workflow commit. Either repeat steps 2–4, or the owner uses **Update branch**; in that case the agent reruns `verify --full` and `close` and pushes last.

## Rollback or recovery

- **Before merge:** drop the branch and the worktree `/Users/ckh/repos/Podobank-template-sync-1f6cd95`.
- **After merge:** open a new change that restores the ten files from `9121ff9`. Its workflow part needs the same handoff.

## Open questions

None.
