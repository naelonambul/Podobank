# Implementation Plan

## Summary

The first two real pilot cycles in `naelonambul/todo-cli-test` (`product-init`, PR #1; `list-summary`, PR #2) exposed one documentation gap that recurs on every change: the order of the closing steps, the state `repo.py status` reports at each step, and which evidence a closure may cite. The `product-init` plan needed four revisions on exactly this. The pilot also showed product intent picking up SDLC process goals.

This docs-only `repository` change:

- adds a "Lifecycle" section to `changes/README.md`, covering the ordered steps, the computed state at each step, and evidence rules;
- corrects the closure example there, which currently suggests citing a CI run;
- adds the `closure` field to "Computed state";
- mirrors the lifecycle briefly in the `sdlc-artifacts` skill;
- states there that product intent must not contain CI, PR, verification or closure goals.

It changes no behaviour. `scripts/repo.py`, `checks.json`, CI and the change model are untouched. Every documented state is the one `repo.py` already computes (`evaluate_change` and `check_closure`), as observed in both pilots.

Evidence: https://github.com/naelonambul/todo-cli-test/pull/2#issuecomment-5796486362, PRs naelonambul/todo-cli-test#1 and #2, and push runs 35869284471 and 35873444631.

## Files and components that change

`write_scope`: `["changes/README.md", ".agents/skills/sdlc-artifacts/SKILL.md"]`

| Path | Change |
|---|---|
| `changes/README.md` | Add a `closure:` line to "Computed state". Add a new "Lifecycle" section before "Closure". In "Closure", replace the `evidence` placeholder `<CI run or verify evidence reference>` with `<local verify evidence reference>`, and point to "Lifecycle" for ordering and evidence rules. |
| `.agents/skills/sdlc-artifacts/SKILL.md` | Intent bullet: add the product-only rule. Replace the "Close" section with the short ordered lifecycle and the evidence rules, deferring to `changes/README.md` for detail. |

Out of scope, for a later change:

- **Packet-creation guidance.** Baseline digests are currently filled in by hand. The pilot's malformed first attempt was caught by `repo.py status`. This change documents no `repo.py` internals, such as `file_digest` or `packet_digest`, as an interface. The second improvement change will first decide whether a stable public command (for example printing root baseline digests or the packet digest) or a small scaffolding command is the better interface.
- `docs/host-setup.md` (host ruleset and agent identity).
- `scripts/**`, `checks.json`, `.github/**`, `REVIEW.md`, `AGENTS.md`, and the frozen `changes/template-vnext-control-plane/`.

## Content to add

### `changes/README.md`, "Computed state" block

Add one line to the text block:

```text
closure:    none | candidate | invalid | frozen
```

Add one bullet after "Readiness":

- **Closure.** `closure.json` present on an unmerged branch is a `candidate` that CI validates. Once the baseline branch contains it, it is `frozen` at its anchor. Any error is `invalid`. Note that `stage` becomes `closed` as soon as `closure.json` exists, before merge.

### `changes/README.md`, new "Lifecycle" section (before "Closure")

The ordered path for every change, with what `repo.py status --change <id>` reports:

| Step | Action | Expected status |
|---|---|---|
| 1 | Create the packet; draft artifacts in chain order | `stage=<first unapproved artifact>`, `readiness=blocked` |
| 2 | The owner approves each artifact in order; record digest-bound claims | after the last: `stage=implementation readiness=ready` |
| 3 | Implement inside `write_scope`; run `repo.py verify --change <id>` (and `--full` before closing) | unchanged |
| 4 | Merge accepted change-local `intent.md`/`spec.md` into the root; verify again | unchanged |
| 5 | Add a candidate `closure.json` citing the step 4 evidence | `stage=closed freshness=current readiness=ready closure=candidate` |
| 6 | Commit, push, open one PR with `Change-ID: <id>` | CI `status` job validates the candidate |
| 7 | CI `summary` must pass on the head that contains `closure.json`; record the result in the PR | unchanged |
| 8 | Human review and approval on the provider; squash merge | — |
| 9 | Post-merge `push` run on the baseline branch passes; confirm the anchor | `stage=closed freshness=frozen closure=frozen`, anchor = the merge (squash) commit |

Evidence rules:

- **Cite only existing evidence.** A closure cites only evidence that exists when it is written, normally the local `verify` evidence from step 4. It never cites the CI run of its own PR, which cannot exist yet.
- **CI results go in the PR.** Record CI results in the pull request (description or comment), not in `closure.json`. The required `summary` check is the merge gate.
- **Fixes after closure.** If CI or review needs another commit after the closure exists, that same commit:
  - re-runs local verification;
  - replaces the closure's `evidence` with the new references;
  - recomputes `packet_sha256` only if a packet file changed, and `baseline` only if a carried root artifact changed.

  `packet_sha256` excludes `closure.json`, so updating `evidence` never changes it. No commit is made only to cite a CI run.
- **After merge.** The packet is frozen. Record follow-up work as a new change.

### `changes/README.md`, "Closure"

- In the example, replace `"<CI run or verify evidence reference>"` with `"<local verify evidence reference>"`.
- After step 2, add one sentence: "See Lifecycle for when to add the closure and which evidence it may cite."

### `.agents/skills/sdlc-artifacts/SKILL.md`

- Append to the **Intent** bullet: "The intent describes the product and its outcomes. Do not put SDLC process goals in it: CI, PR, verification, check registration, or closure criteria belong in the change's plan."
- Replace the body of **Close** with:

  1. Verify locally (`repo.py verify --change <id>`, and `--full`).
  2. Merge accepted change-local `intent.md`/`spec.md` into the root and verify again.
  3. Add a candidate `closure.json` citing only that existing local evidence. `status` then reports `stage=closed closure=candidate`.
  4. Commit, push and open the PR. CI `summary` must pass on the closure-containing head. Record CI results in the PR, never in the closure.
  5. After human review and a squash merge, confirm `status` on the baseline branch reports `freshness=frozen closure=frozen`.

  After this, keep the paragraph "Fixes after the closure exists refresh its `evidence` in the same commit; see `changes/README.md`, Lifecycle. After merge the packet is frozen: never edit it again. Record follow-up work as a new change."

The final wording may be tightened during implementation, provided it states exactly the rules above.

## Order of work

1. **Plan approval (owner).** The owner approves this plan's exact digest. The agent records the claim and confirms `stage=implementation readiness=ready`.
2. **Packet commit.** Commit the packet on `change/lifecycle-docs` as the `naelonambul-agent` App.
3. **Edit** the two files as specified above.
4. **Check against code.** Re-read `scripts/repo.py` (`evaluate_change`, `check_closure`, `validate_closure`) and confirm every documented state and rule matches computed behaviour. Also confirm the lifecycle table matches the two pilot transcripts.
5. **Local verification.**
   - Run `python3 scripts/repo.py verify --change lifecycle-docs` and `verify --full`. The `control-plane` check routes `changes/**` and `.agents/**`, and must pass with no `failed`, `blocked` or `not-run` check.
   - Run `status --change lifecycle-docs`, which must report `status: ok` with no out-of-scope path.
6. **Candidate closure.** Add `changes/lifecycle-docs/closure.json`:
   - `schema` 1;
   - `baseline` `{}`, because a `repository` change carries no root artifact;
   - `packet_sha256` computed by `repo.py`'s own closure logic;
   - `evidence` citing the step 5 local evidence paths.

   Confirm `stage=closed freshness=current readiness=ready closure=candidate`. This change follows its own documented lifecycle.
7. **Commit, push and PR.** Commit as the App, push with `agent-git`, and open a PR with `agent-gh` whose body starts with `Change-ID: lifecycle-docs`.
8. **CI.** `summary` must pass on the closure-containing head. Record the result in a PR comment. Any fix follows the evidence-refresh rule.
9. **Human review and merge (owner).** The owner reviews and squash-merges. The agent does not approve or merge.
10. **Post-merge.** The `push` run on `main` passes, and `status` reports `lifecycle-docs` as `freshness=frozen closure=frozen` at the squash commit, with `template-vnext-control-plane` still frozen.

## Tests and proof

- This is a docs-only change. Proof is `control-plane` passing (the existing `repo.py` unit tests, unchanged) plus the step 4 review of the text against the code.
- Every status string in the Lifecycle table was observed in the pilots:
  - `stage=closed freshness=current … closure=candidate` before merge (todo-cli-test PRs #1 and #2);
  - `freshness=frozen closure=frozen` after merge (anchors `2b60efb` and `4d0eea0`).

## Risks and mitigations

- **Docs drifting from code.** Mitigation: state only what `repo.py` computes today, and re-check at step 4. Document no `repo.py` internal function names.
- **Over-prescribing.** The lifecycle describes the path the control plane already enforces or expects. It adds no new gate.

## Rollback or recovery

- **Before merge:** close the PR.
- **After merge:** revert through a new `repository` change. The frozen packet is never edited.

## Open questions

None for this change. The packet-creation interface is intentionally deferred to the second improvement change.
