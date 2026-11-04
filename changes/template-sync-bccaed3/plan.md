# Template sync through bccaed3

## Summary

This change imports the template's change `1f6cd95..bccaed3` into PodoBank: #52 fixture-git-maintenance.

PodoBank's post-merge `main` run 41743584316 failed once in `verify-core`. `RepoCase.setUp` copied the fixture template while a detached `git maintenance run --auto`, started by the template's `git commit`, removed `.git/objects/maintenance.lock`, and `shutil.copytree` raised `FileNotFoundError`. A rerun passed. The template now runs every fixture Git command with `maintenance.auto=false`, through `GIT_ENV` and the template repository's local config, and the shallow-clone test passes `GIT_ENV` as well.

It is a `repository` change. It does not touch product code, `intent.md`, `spec.md`, `checks.json` or `.github/workflows/**`, and it imports no upstream `changes/` packets.

The template is https://github.com/naelonambul/sdlc-project-template-agent. It is read from the worktree `/Users/ckh/repos/tmp/template-fixture-git-maintenance` on this Mac, with `git show bccaed3:<file>`. Do not add a remote.

This change is edited, committed and pushed on the Mac, in the worktree `/Users/ckh/repos/Podobank-template-sync-bccaed3`. Its full verification runs on the `oracle` host, which has the product toolchain; see Decisions.

## Source check

Checked at `b22cf0a` against the template at `1f6cd95`, the previous sync point (#29): the three files this range changes, `scripts/tests/support.py`, `scripts/tests/test_status.py` and `scripts/tests/test_support.py`, are byte-identical in PodoBank at their old version. Nothing needs merging.

## Decisions

- **Copy the three files byte for byte from `bccaed3`.**
- **No workflow handoff.** `.github/workflows/**` is not touched, so the agent makes every commit and push.
- **`verify --full` runs on `oracle`.** A first run on the Mac (`.evidence/20261104T011714113927Z`) could not run the product checks: the Mac's Docker CLI has no Compose v2 plugin, and no isolated MariaDB was provided. That run is not used as evidence. `oracle` has Docker Compose v5.1.4 and Node.js v26.13.0.
  - Push this branch first, then on `oracle` add a worktree of it at `/home/ckh/block/codex-home/worktrees/template-sync-bccaed3/Podobank` and run verify there. Commit, close and push stay on the Mac, because `oracle` has no `agent-git`/`agent-gh`.
  - The `mariadb` group needs the CI-equivalent MariaDB (`mariadb:12.3.3`, the same `--sql-mode`, database `podobank_test`, user `podobank`/`podobank-test`) on `127.0.0.1:3306`, with `APP_ENV=test` and the CI `DATABASE_URL`. The running PodoBank preview (Compose project of `/home/ckh/block/codex-home/worktrees/npm-podobank-preview/Podobank`) holds that port. The owner has said the preview may be taken down for tests. Run `docker compose -p <project> stop` on it before verify and `docker compose -p <project> start` after, which restarts the same containers and volumes. Remove the temporary MariaDB container afterwards. Nothing else on `oracle` (NPM, `cloudflared`, other stacks) is stopped or changed.
  - Copy the evidence directory back into the Mac worktree's `.evidence/`, and close with it.
  - If a check cannot run, report it as `blocked`, do not close, and ask the owner.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- Taken from the template at `bccaed3` without changes:
  - `scripts/tests/support.py`
  - `scripts/tests/test_status.py`
  - `scripts/tests/test_support.py`

## Order of work

Single agent.

1. Copy the three files. Proof: each compares equal (`cmp`) to `git show bccaed3:<file>` in the template worktree, and `python3 -m unittest scripts.tests.test_support.NoAutoMaintenance -v` passes.
2. Run `python3 scripts/tests/run.py` and `SDLC_TEST_EQUIVALENCE=1 python3 -m unittest discover -s scripts/tests -t .`. Both pass.
3. On the Mac, commit the packet and the three files with `agent-git` and push the branch with `agent-gh push`.
4. On `oracle`, add the worktree, stop the preview, start the temporary MariaDB, and run `python3 scripts/repo.py status --change template-sync-bccaed3`, then `APP_ENV=test DATABASE_URL=mysql+pymysql://podobank:podobank-test@127.0.0.1:3306/podobank_test python3 scripts/repo.py verify --change template-sync-bccaed3 --full`. Remove the temporary MariaDB, start the preview again and confirm its API `/health` and frontend `/` return HTTP 200.
5. On the Mac, copy the evidence back, run `python3 scripts/repo.py close template-sync-bccaed3 --evidence <path>`, commit, `agent-gh push`, and open the pull request with `Change-ID: template-sync-bccaed3`.
6. Confirm with `agent-gh pr checks` that every check passes. The owner reviews, approves and merges. After the merge, confirm the `push` run on `main` with `agent-gh run list`.

## Tests and proof

- **Byte identity:** each copied file equals the template's file at `bccaed3`.
- **Regression:** `NoAutoMaintenance` asserts that a fixture commit's `GIT_TRACE` has no `maintenance run` and that the template's local config says `maintenance.auto=false`. In the template, both failed on the old files and pass on the new ones.
- `python3 scripts/repo.py status --change template-sync-bccaed3` passes.
- `python3 scripts/repo.py verify --change template-sync-bccaed3 --full` reports no `failed`, `blocked` or `not-run` check.
- **CI:** the pull request's `repository` run and the post-merge `push` run are `success`. The race depends on timing, so one green run does not prove it gone; the regression tests prove that maintenance no longer starts.

## Risks and mitigations

- **PodoBank's product checks need Docker and Node.js, and can take up to 25 minutes.** A check that cannot run is reported as `blocked`, never as passed.
- **The preview is down during verify on `oracle`.** It is stopped, not removed, and started again right after, with its health checked. PodoBank's verify stacks use their own Compose project names, so no other container is touched.
- **`main` moves before merge.** Rerun `verify --full` and `close` on the updated branch, and the agent pushes last.

## Rollback or recovery

- **Before merge:** drop the branch and the worktree `/Users/ckh/repos/Podobank-template-sync-bccaed3`.
- **After merge:** open a new change that restores the three files from `b22cf0a`.

## Open questions

None.
