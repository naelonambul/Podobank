# Implementation Plan

## Summary

Document the owner-approved GitHub App identity and the separate local and remote command paths used by Podobank agents. Preserve the two-person review gate: the bot authors the work, pushes last, and opens the pull request; the owner approves and merges it.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `AGENTS.md`: Add a short rule under Working rules that directs agents to `agent-git` for local Git operations and `agent-gh` for remote GitHub operations, requires the bot's final push, prohibits owner-credential substitution, and links to the detailed host guide.
- `docs/host-setup.md`: Document the two actors, the sole App account `mini26-agent`, its exact commit identity, command routing and denials, working-directory requirement, bot-last-push requirement, workflow permission limit, and unsupported issue/API operations. Retain the existing Now/Target trust-stage explanation. Clarify that the owner approves and merges in the current stage; keep the target stage description intact. Remove guidance that suggests an owner push can substitute for the bot's last push.
- `.agents/skills/sdlc-artifacts/SKILL.md`: Update the close instructions to stage and commit with `agent-git`, push and create the pull request with `agent-gh`, and retain the bot-last-push handoff to the owner.
- `docs/agent-surfaces.md`: Align the scratch-copy probe command with the wrapper policy, run the documented Claude Code and Codex probes after changing `AGENTS.md` and the skill, and record dated results without claiming untested support.

All paths are listed in `changes/github-app-workflow/change.json` `write_scope`.

## Order of work

1. Update `AGENTS.md` and `.agents/skills/sdlc-artifacts/SKILL.md` with concise local/remote command routing and the owner handoff. Confirm the packet remains in scope with `python3 scripts/repo.py status --change github-app-workflow`.
2. Update `docs/host-setup.md` with the approved `mini26-agent` identity and email, the command allow/deny matrix, first-token routing from the repository directory, and the App's missing `workflows` permission. Preserve the Now/Target trust stages and state that the owner approves and merges in the current stage. Confirm the final policy wording with `rg -n "mini26-agent|agent-git|agent-gh|Now|Target|last push|workflows|gh api" docs/host-setup.md`.
3. Update `docs/agent-surfaces.md` so the scratch probe does not invoke raw `git` for clone. Run the documented Claude Code and Codex smoke probes in a scratch copy, check the observed instruction and skill output, then append dated results. Run `python3 scripts/repo.py verify --change github-app-workflow --full` after the documentation and probes are complete.
4. Review all changed text against this plan and `REVIEW.md`, confirm no credentials or files outside `write_scope` are present, and run `python3 scripts/repo.py close github-app-workflow --evidence <full-run-evidence-path>`. Then run `python3 scripts/repo.py status --change github-app-workflow` and confirm the closure is a current candidate.
5. Create a commit with `agent-git`, push with `agent-gh`, and open the pull request with `agent-gh pr`. Verify the pull request author and its commit authors are `mini26-agent[bot]` using `agent-gh pr view`; report the PR link and observed identities. The owner reviews, approves, and merges. Stop if the App rejects a workflow-file push; the owner handles workflow changes.

## Tests and proof

- `python3 scripts/repo.py status --change github-app-workflow`: confirms packet readiness and write-scope compliance at each gate.
- `python3 scripts/repo.py verify --change github-app-workflow --full`: runs the registered repository checks and records evidence.
- Run the documented smoke probes from a scratch copy on Claude Code and Codex; record the actual `AGENTS.md` delivery and project-skill discovery results in `docs/agent-surfaces.md`.
- Before reporting publication, inspect the pull request with `agent-gh pr` and verify its author and commit authors are `mini26-agent[bot]`. If the observed names differ or cannot be checked, report that evidence without inferring identity.

## Risks and mitigations

- A command placed after `-C <path>` or invoked through the wrong wrapper may be rejected or use the wrong identity. Document the first-token rule and run commands from the repository directory.
- The App cannot push `.github/workflows/**`; keep that path outside this change and stop for owner action if it becomes necessary.
- The App has merge permission, but it cannot approve as the owner. In the current stage, the ruleset requires owner approval and repository policy reserves merging to the owner; document that the agent does not merge. The App cannot handle issues or use `gh api`.
- Never read or expose App keys or tokens. Do not inspect or change host helper files or GitHub settings.

## Rollback or recovery

Before merge, revert only the scoped documentation edits and rerun packet verification. After merge, use a new `repository` change to revise the policy; do not rewrite or revert a closed packet.

## Open questions

None. The owner supplied the account name, commit identity, command boundaries, permission limits, and approval/merge ownership on 2026-10-31.
