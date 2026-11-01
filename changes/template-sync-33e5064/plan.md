# Template sync through 33e5064

## Summary

Import the template's changes `80c1a73..33e5064` (#39, #40, #41, #44, #46) into PodoBank. This is a `repository` change. It does not touch product code, `intent.md`, `spec.md` or `checks.json`, and imports no upstream `changes/` packets.

The template is at https://github.com/naelonambul/sdlc-project-template-agent, read from a local clone. Do not add a remote.

This change edits `.github/workflows/repository.yml`, so it follows the workflow handoff it imports. It is that route's first full run.

### Decisions

- **Three PodoBank rules change, because the template now contradicts them.** The owner approves each by approving this plan:
  1. `AGENTS.md` and `docs/host-setup.md` forbid the owner's `git push` for agent work. Add one exception: the workflow commit in "Workflow changes".
  2. `docs/host-setup.md` says the agent cannot work on issues. It may now read them with `agent-gh issue list` and `issue view`. Writing to issues stays refused.
  3. `sdlc-artifacts` forbids `agent-gh run`. The agent may now use read-only `agent-gh run list` to confirm the post-merge `push` run. Logs stay with the owner.
- **PodoBank's wrapper table stays.** Do not import the template's host-state table of command paths: PodoBank has one fixed path, `agent-git` and `agent-gh`. The same goes for the template's `AGENTS.md` identity bullet; PodoBank's own bullet is stricter and stays, with the exception above.
- **`needs` keeps `verify-mariadb`.** `summary` needs `[control-plane-tests, status, verify-core, verify-mariadb, identity]`.
- **Measurements are PodoBank's own.** Do not paste the template's smoke rows into `docs/agent-surfaces.md`. Run the probes here and record what they show.
- **`AGENT_LOGIN` is an owner step.** Until it is set the `identity` job passes with a notice, so nothing fails, and nothing is checked either.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `AGENTS.md`: add the template's "Do not delete, overwrite, regenerate" bullet unchanged. Change the end of the `agent-git` bullet to: "Never substitute the owner's `git push` or `gh`, except the one workflow push in `docs/host-setup.md`; the owner approves and merges in the current stage."
- `.github/workflows/repository.yml`: add the template's `identity` job after `verify-mariadb`, and extend `needs` as decided above.
- `scripts/tests/test_workflow.py`: the template's patch applies cleanly.
- `.agents/skills/repository-quality/SKILL.md`: the template's patch applies cleanly.
- `.agents/skills/sdlc-artifacts/SKILL.md`:
  - Add the template's "Pre-existing local files" section. Its `git status` and `git check-ignore` commands become `agent-git` commands.
  - Add the template's workflow line to "Close", and its text to the `.github/workflows/**` bullet.
  - In "When CI is red", replace "Do not invoke `agent-gh run`, raw `gh`, or change wrappers to obtain logs" with "`agent-gh run list` shows run metadata, not logs. Do not use raw `gh` or change wrappers to obtain logs".
- `docs/host-setup.md`:
  - After the paragraph starting "Do not use the owner's `git push`", add the template's `identity` paragraph with the example login `mini26-agent[bot]`, and add "except the workflow push in \"Workflow changes\"" to the sentence on what the owner may not push.
  - In the wrapper table, the `agent-gh` row gains read-only `run list` and `issue list`/`issue view`, with the template's flag limits.
  - Replace "The agent cannot work on issues or use `gh api`." with "The agent reads issues only through `agent-gh issue`, and cannot use `gh api`."
  - In the Workflows bullet, replace "stop and tell the owner, who handles workflow changes" with "follow \"Workflow changes\"".
  - Add the template's `### Workflow changes` section before `## Read-only host check`, with `agent-git`/`agent-gh` in place of plain commands where the agent acts.
  - Add `gh variable get AGENT_LOGIN --repo OWNER/REPO` and the template's pull-request probes to the owner's read-only check, and the template's route-verification paragraph.
- `docs/agent-surfaces.md`: add a section "PodoBank template-sync probes (2026-11-01, 33e5064)" with this change's results.

## Order of work

Each step is one coordinator edit, so the route is single agent.

1. Edit `AGENTS.md`, the skills, `docs/host-setup.md` and `scripts/tests/test_workflow.py`. Proof: `grep -c '^### Workflow changes' docs/host-setup.md` prints `1`, and `grep -c 'Pre-existing local files' .agents/skills/sdlc-artifacts/SKILL.md` is at least `1`.
2. Run the probes from `docs/agent-surfaces.md` on a scratch copy, and record them. Proof: the new section names the versions and results.
3. Commit steps 1 and 2 with `agent-git`, and `agent-gh push` them. This commit has no workflow file. The test `test_identity_job_compares_the_author_with_the_variable` fails locally until step 4, so this push opens no pull request.
4. Edit `.github/workflows/repository.yml` and commit it alone. Proof: `python3 -m unittest scripts.tests.test_workflow` passes.
5. Run `python3 scripts/repo.py verify --change template-sync-33e5064 --full`, then `repo.py close`, and commit the closure on top. Push neither.
6. Give the owner the workflow commit's SHA, and stop. The owner runs `git push origin <sha>:refs/heads/change/template-sync-33e5064` from any checkout of this repository on the Mac. The owner also runs `gh variable set AGENT_LOGIN --body 'mini26-agent[bot]' --repo naelonambul/Podobank`.
7. Confirm with `agent-gh ls-remote` that the branch head is that SHA. Then `agent-gh push` the closure commit and open the pull request with `Change-ID: template-sync-33e5064`.
8. Confirm CI with `agent-gh pr checks`. The owner reviews, approves and merges.
9. Confirm the `push` run with `agent-gh run list`.

## Tests and proof

- `python3 scripts/repo.py status --change template-sync-33e5064` passes, which shows every changed path is inside `write_scope`.
- `python3 scripts/repo.py verify --change template-sync-33e5064 --full` reports no `failed`, `blocked`, or `not-run` check. This needs a local MariaDB if the `mariadb` group's checks require one; if it cannot run here, report it as `blocked`, do not close, and ask the owner.
- The `identity` job appears in the pull request's checks and passes with the bot as author.
- The handoff itself is proven when the pull request shows the bot as author, the closure commit as head, and the owner's approval is accepted.

## Risks and mitigations

- **The owner's push sends the closure too.** The refspec names one SHA, and step 7 checks the remote head first.
- **The branch falls behind `main` during the handoff.** The workflow commit cannot be rebased by the App. Repeat steps 4 to 7.
- **Step 3's commit fails CI.** It opens no pull request, so CI does not judge it alone.

## Rollback or recovery

Before merge, drop the branch and the worktree `/Users/ckh/repos/Podobank-template-sync`. After merge, open a new change that restores the files. The workflow part of that change needs the same handoff.

## Open questions

None.
