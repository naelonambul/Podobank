# Implementation Plan

## Summary

Add a small execution layer that lets a strong coordinator hand routine implementation to cheaper worker agents under Claude Code or Codex. Its governing assumption, from the owner's direction:

- **the worker is weak and interchangeable;**
- **reliability comes from the contract, not the model.**

So the layer is built from:

- closed, self-contained unit briefs with literal acceptance values;
- explicit stop conditions instead of improvisation;
- protected oracle tests: acceptance tests, regression witnesses and other oracle tests that the coordinator supplies, which the worker must not change;
- acceptance by mechanical re-verification, never by the worker's self-report.

The boundary stays as it is:

- **Template v2 owns authority.** That means the packet, approvals, `write_scope`, `repo.py status/verify`, `checks.json`, closure, CI `summary`, and human PR review.
- **Skills own the method.** Two new canonical skills live in `.agents/skills/`.
- **Harness adapters own the mechanics.** That means spawning, and optionally mapping each abstract tier to a real model. The repository names roles and tiers, never models, and relies on no harness configuration path.

This change adds no runtime, queue, store, plan format, approval path, ledger, or merge behaviour. It changes no `scripts/**`, `checks.json`, `.github/**` or lifecycle semantics.

Did studying the sources change the design? Yes, in two ways:

1. The design reuses pstack's **brief contract**, its **verify-the-real-artifact** rule and its **selective multi-model review**. It drops pstack's runtime and state (`orch`, ledgers, inboxes, stack tooling), its mandatory delegation, and its autonomy defaults.
2. Codex already discovers `.agents/skills/`, the template's canonical skill location. So Codex needs **no adapter files**, and Claude Code needs only the existing symlink pattern.

## Evidence

### Primary references

Both were inspected directly.

**`poteto/verification-skill-example`** at `d5abe70`, 2026-07-30:

- It contains no license file, so it is used **only as a structural reference**. No text is copied.
- It has one project-local skill, `SKILL.md`, with sections for launch, doctor, drive, proof bar and cleanup, plus a `references/features/` map.
- The map has a `README.md` index. It covers baseline preconditions, proof and skip reporting, a full-sweep order and an entry contract.
- It has one file per feature area. Each has the same four sections: sub-features, how the user reaches it, how to drive it, and gotchas.
- Its README gives the rationale: a map is scoped, actionable, sweepable, and maintained as code, because "agents pay for every token they reread".

**`cursor/plugins` `pstack`** at `b42effe`, 2026-09-23, version 0.15.3, MIT:

- **README.** A coordinator mode routes each task to a playbook. It routes by role, for example "code delegates … go to grok, … judgment to opus". The coordinator owns every subagent's diff.
- **`playbooks/orchestrate.md`.** The brief has GOAL, SCOPE, CONTEXT, ACCEPTANCE, VERIFY, TIMEBOX, FORBIDDEN, REPORT and STANDING. It warns that "a worker cannot ask you a question", so missing fields are a reason to refuse to spawn. Other rules:
  - size the brief to the unit;
  - respawn fresh rather than resume-chaining;
  - retry by failure mode, and abandon after two retries;
  - scale verification to the unit;
  - CI green "is not a verdict";
  - a single cheap VERIFY command needs no separate verifier.
- **`playbooks/feature.md`.** Name the data shape before code. Write a throughput checkpoint: blocking first steps, independent workstreams, shared mutable state, and the smallest safe decomposition. It makes delegation mandatory even for small apps; this design rejects that.
- **`skills/interrogate`.** A read-only reviewer on each of several model families. A lead sorts findings into act on, consider, noted and dismissed, and nothing is applied automatically.
- **`skills/create-verification-skill` and `skills/maintain-verification-skill`.** Interview the repo, not the user. Generate launch, doctor, drive, evidence and cleanup sections plus a seeded feature map, and prove the generated skill once before handing it over. The upkeep pass changes only the verification skill's own directory, and separates doc drift, harness gaps and product gaps.
- **Principles.**
  - `prove-it-works`: verify against the real artifact, not self-report.
  - `sequence-verifiable-units`.
  - `guard-the-context-window`: route bulk to subagents and keep summaries.
  - `encode-lessons-in-structure`.
- **Portability.**
  - It depends on Cursor: `environment: "cloud"`, `readonly`, `AskQuestion`, `~/.cursor/rules/pstack-models.mdc`, and the `cursor-team-kit` plugin.
  - Its runtime needs Bun and Graphite.
  - It hard-codes model slugs.
  - None of this is adopted.

### Pilot evidence (this template)

- **A worker's claim was false.** In `todo-cli-test` `product-init`, a delegated worker said it had escaped U+2028/U+2029 when it hadn't. The coordinator's own diff review caught it. So self-report can't be accepted.
- **Delegation would have cost more than the fix.** `list-summary` changed about five lines in one module. A brief, worker and review would have cost more than the edit, so small tasks need a bypass.
- **The scope gate worked.** A malformed baseline in that same packet was caught at once by `repo.py status`. Mechanical gates beat prose.

### Harness facts

These are from the official docs, fetched 2026-09-24, and kept separate from the design references. They are **observations, not part of the contract**. Only repository-local discovery (`AGENTS.md`, `.agents/skills/`, `.claude/skills/`) is relied on, and step 5 smoke-tests it. The subagent and model-configuration paths below are documented but **unverified here**. The repository does not depend on them.

**Codex:**

- **Skills.** Codex scans `.agents/skills` in every directory from the working directory up to the repository root. It follows symlinks. `SKILL.md` needs only `name` and `description`, and optional metadata goes in `agents/openai.yaml`. Skills are invoked explicitly with `$skill` or implicitly by description.
- **Subagents.** These are enabled by default. Custom agents are defined in `.codex/agents/` or `~/.codex/agents/*.toml`, with `name`, `description` and `developer_instructions` required. The optional fields include `model`, `model_reasoning_effort` and `sandbox_mode` (`read-only`, `workspace-write`). The global setting is `agents.default_subagent_model`.
- **Local CLI.** `codex-cli 0.156.1` is installed here.

**Claude Code:**

- **Subagents.** These live in `.claude/agents/` or `~/.claude/agents/`, with a `model` field that takes an alias, a full ID or `inherit`.
- **Model precedence.** In order: the per-invocation `model`, the file's `model`, `CLAUDE_CODE_SUBAGENT_MODEL`, then the parent's model. Subagents can use `tools`/`disallowedTools`, `isolation: worktree` and `skills` preload.
- **Skills.** Discovery is through `.claude/skills/`, which the template already covers with symlink adapters checked by `repo.py`.

### Baseline at packet creation

- `origin/main` is `8a3394481c818c9f50883e0c69ab169560200074`.
- The worktree was clean apart from ignored `.evidence/` and `__pycache__/`.
- `host-setup-docs`, `lifecycle-docs` and `template-vnext-control-plane` are all `closure=frozen`.
- The push run 35879011895 on `8a33944` succeeded.

## Overlap inventory

| Capability | Decision |
|---|---|
| Authority chain, packets, approvals, `write_scope`, `status`, `verify`, `checks.json`, closure, `Change-ID`, CI `summary`, required human review | **Keep in Template v2 governance.** Unchanged. |
| The approved `plan.md` as the implementation plan | **Governance.** The executor derives units from its Order of work. No second plan format or plan checker. |
| Coordinator/worker split, brief contract, stop conditions, report shape | **Portable skill** (`change-execution`), adapted from pstack's orchestrate brief and feature playbook |
| Small-task bypass, unit decomposition, parallel only with disjoint files | **Portable skill** (`change-execution`) |
| Accept work by re-running verification and checking diff scope; never self-report | **Portable skill.** Uses existing `repo.py status/verify` and `git`; no new tool. |
| Selective independent review with act-on/consider/noted/dismissed | **Portable skill** (`change-execution` reference), adapted from `interrogate`. Advisory; the human PR review stays the gate. |
| Context protection: short fixed reports, no raw logs in the coordinator thread | **Portable skill** (`change-execution`) |
| Project-local verification skill and feature map, drift upkeep | **Portable skill** (`verification-map`), adapted from pstack's create/maintain skills, with structure only from the verification example |
| Roles and cost tiers (`coordinator`, `worker`, `reviewer`; `high`, `standard`, `economy`) | **Portable contract**, named in `change-execution` |
| Mapping tiers to real models; how to spawn; read-only sandboxing | **Harness adapter only, and optional.** It is an optimization, not an authority or correctness dependency. Without it, the coordinator or the owner picks a worker model manually. `docs/agent-surfaces.md` records only observed integration, clearly labelled. No model names and no required configuration paths in the repository. |
| Skill discovery | **Harness adapter.** Codex needs nothing, because it scans `.agents/skills`. Claude Code needs two new `.claude/skills` symlinks. |
| Project `.claude/agents/*.md` or `.codex/agents/*.toml` role files | **Do not build now.** They would either hard-code models or be empty shells repeating the brief. Revisit only if the pilot shows that a read-only reviewer can't be reliably held to read-only without them. |
| `orch` runtime, inbox, queue, units/frontier/ledger store, gates file, Graphite stacking, cloud agents, `setup-pstack` rule file, playbook router, 23 principle skills, PR babysit/ship/auto-merge, decision-trail logger, `check-plan.mjs` | **Unnecessary: do not build** |

## Files and components that change

`write_scope`:

```json
[".agents/skills/change-execution/", ".agents/skills/verification-map/",
 ".claude/skills/change-execution", ".claude/skills/verification-map",
 ".agents/skills/sdlc-artifacts/SKILL.md", "AGENTS.md", "README.md", "docs/agent-surfaces.md"]
```

| Path | Change |
|---|---|
| `.agents/skills/change-execution/SKILL.md` | New. The coordinator's procedure (below). |
| `.agents/skills/change-execution/references/worker-brief.md` | New. The brief template, pasted as-is into every worker prompt. |
| `.agents/skills/change-execution/references/review-brief.md` | New. The read-only reviewer brief and its output shape. |
| `.agents/skills/verification-map/SKILL.md` | New. How to create and maintain a project-local `verify-<app>` skill with a feature map. |
| `.agents/skills/verification-map/references/feature-file.md` | New. A short feature-file skeleton, written independently. |
| `.claude/skills/change-execution`, `.claude/skills/verification-map` | New relative symlinks to `../../.agents/skills/<name>`, the existing adapter pattern |
| `.agents/skills/sdlc-artifacts/SKILL.md` | Plan bullet: each Order-of-work step names its files and one verify command, so a weak worker can take it as a unit. Implement section: points to `change-execution`. |
| `AGENTS.md` | One working-rule line on delegation (below). No gate changes. |
| `README.md` | Add the two skills to the list. Say that Codex discovers `.agents/skills` natively. |
| `docs/agent-surfaces.md` | Restructured into three clearly separated parts: the repository-owned portable contract, currently observed harness integration (including Codex, with smoke-test rows), and optional user-local model/tier mapping. Details below. |

Out of scope: `scripts/**`, `checks.json`, `.github/**`, `changes/**` outside this packet, `REVIEW.md`, root `intent.md`/`spec.md`, `evals/`, host settings, and packet-creation automation, which is still deferred.

## Content: `change-execution` skill

Frontmatter `name: change-execution`. The description says to use it to implement a change whose `status --change <id>` reports `readiness=ready`, and to decide whether and how to delegate to worker agents.

1. **Preconditions.**
   - `status --change <id>` must report `readiness=ready`.
   - The coordinator reads the approved packet and upstream artifacts. Workers don't: they act only from their brief.
2. **Roles and tiers.**
   - Roles: `coordinator`, `worker` and `reviewer`.
   - Tiers: `high`, `standard` and `economy`, where `economy` means the cheapest available.
   - The skill never names a model or a configuration path. Which model serves a tier is chosen outside the repository: by an optional user-local mapping if the harness offers one, or manually, by the coordinator or owner, when spawning. Either way the contract is the same. Model routing is an optimization; correctness never depends on it.
   - Any model that follows the brief can fill any role. The contract must hold when the worker is `economy`.
3. **Route.** Choose one route and record it.

   | Task shape | Route |
   |---|---|
   | Trivial or local, where the brief would be about as long as the diff (for example one step, one or two files) | **Single agent.** The coordinator implements. No workers. |
   | Bounded normal change | Coordinator (or the approved plan) plus **one** worker |
   | Large, independent workstreams with disjoint `FILES` and no ordering dependency | Coordinator plus a **small** number of parallel workers. Otherwise run them in sequence. |
   | Risky, ambiguous, or wide-reaching (see triggers in step 8) | Add **one** independent reviewer. Use more than one only when the reviewers disagree or a finding is disputed. |
   | Verification failed | Retry **only the failed unit** (step 7) |

4. **Units.**
   - Derive units from the plan's Order of work. A unit is not a new plan.
   - A unit is ready to delegate only if the coordinator can fill every brief field, including ACCEPTANCE with literal expected values and a VERIFY command that runs in minutes.
   - If a field can't be filled, don't delegate that unit: implement it yourself, or get a plan revision if the plan is actually unclear.
   - Each unit's `FILES` is a subset of `write_scope`. Parallel units never share a file.
5. **Protected oracle tests.**
   - When the coordinator supplies explicit acceptance tests, regression witnesses, or other oracle tests with a brief, it lists those exact files under PROTECTED. The coordinator may write them itself, or have them written as a separate earlier unit.
   - The worker must not weaken, delete, or modify a PROTECTED file. This keeps the pass/fail oracle out of the weak worker's hands.
   - The worker may create or modify ordinary implementation tests within its FILES when the approved plan calls for them. Normal test-driven implementation stays allowed.
   - A worker's own tests are supporting evidence only. Acceptance always rests on the coordinator independently re-running ACCEPTANCE and VERIFY (step 7), never on the worker's report.
6. **Brief.**
   - Every worker gets `references/worker-brief.md`, filled in. The fields are:
     - GOAL
     - FILES (writable, exhaustive)
     - PROTECTED (oracle test files supplied by the coordinator, read and run only; may be empty)
     - READ (paths, with line ranges when useful; spec lines quoted verbatim, not paraphrased)
     - ACCEPTANCE (numbered, observable, literal values)
     - VERIFY (exact commands and their expected result)
     - FORBIDDEN
     - STOP
     - REPORT
   - The standing FORBIDDEN items:
     - editing `changes/**`, `approvals`, `closure.json`, root `intent.md` or `spec.md`, CI, `checks.json`, or any path outside FILES;
     - weakening, deleting, or modifying any PROTECTED file;
     - committing or pushing;
     - installing dependencies or using the network unless the brief allows it;
     - weakening or skipping a check.
   - STOP means return `BLOCKED` with the reason instead of improvising. It applies when:
     - anything is ambiguous;
     - a needed change falls outside FILES, or would touch a PROTECTED file;
     - VERIFY fails for a reason outside FILES;
     - the brief conflicts with the code;
     - two attempts at the same failure have failed.
   - REPORT has a fixed shape:
     - `STATUS: PASS | ISSUES | BLOCKED`;
     - the files changed;
     - each command run, with its exit code;
     - deviations;
     - at most about ten lines, with no raw logs.
   - Always spawn fresh; never resume-chain.
7. **Accept, mechanically first.** A worker's report is a claim, not evidence. The coordinator does four things:
   1. checks that the changed paths (`git status --porcelain`) are within the unit's FILES and that every PROTECTED file is byte-for-byte unchanged;
   2. re-runs every VERIFY command itself;
   3. runs `repo.py status --change <id>` and `repo.py verify --change <id>`;
   4. reads the diff for what tests can't see, such as escapes, encodings, hidden edge cases, and whether the worker's own tests actually assert the required behaviour.

   On failure:
   - respawn a fresh worker with the same brief plus the concrete failure evidence;
   - after two failed retries, move up a tier or have the coordinator implement it;
   - never loosen ACCEPTANCE or PROTECTED tests to make a unit pass.

   The coordinator commits accepted work under the repository's normal identity.
8. **Selective review.**
   - Add a read-only reviewer (`references/review-brief.md`: REVIEW.md, the packet, the diff) only when one of these triggers applies:
     - security or privacy;
     - persisted data or format;
     - concurrency;
     - a public interface;
     - a change to verification or checks;
     - an ambiguous spec;
     - a unit that needed a retry;
     - a diff clearly larger than planned.
   - Prefer a different model family. Otherwise use a fresh context.
   - The reviewer's output is sorted into act on, consider, noted and dismissed. It is advisory.
   - The required human PR review remains the merge gate.
9. **Context economy.**
   - Keep only fixed-shape reports and the coordinator's own checks in the coordinator's thread.
   - Point workers at file paths instead of pasting file contents, except the spec lines they must obey.
10. **Close.**
    - Continue with the `sdlc-artifacts` Close steps unchanged.
    - In the PR's Verification section, record the route, each unit with its tier and status, and which commands the coordinator re-ran.
    - Nothing is written to the repository beyond that.

The skill carries a one-line attribution: it adapts ideas from pstack (MIT, Lauren Tan). The wording is new.

## Content: `verification-map` skill

Frontmatter `name: verification-map`. The description says to use it when a project has a user-visible surface but no scripted way for an agent to prove behaviour, or when an existing verify skill's feature map has drifted.

- **Create.**
  - Interview the repository, not the owner. Work out:
    - the surface a user touches;
    - how to run it;
    - how to drive it programmatically, preferring existing harnesses;
    - what can be observed;
    - whether it can be isolated.
  - Write a project-local `.agents/skills/verify-<app>/` with Launch, Doctor, Drive, Evidence and Cleanup sections, plus a `.claude/skills` symlink, which `repo.py` checks.
  - Seed `features/README.md`, covering preconditions, the proof and skip rules and a full-sweep order, plus 3–5 feature files in the four-section shape.
  - Prove the skill once, end to end: launch, doctor, drive one feature, capture evidence, clean up, and confirm the evidence survived cleanup.
  - The skill is added through a normal change packet whose `write_scope` covers it.
- **Use.**
  - Match the change to feature files and read only those.
  - Exercise every reachable entry point, and the success, cancel, error, empty and persistence paths the change can affect.
  - Name any unreachable path and its prerequisite.
  - The verify skill's feature files are what the `change-execution` brief's READ and VERIFY fields point a weak worker or reviewer to.
- **Maintain.**
  - Only in a change whose `write_scope` covers the verify skill's directory. Never edit product code in the same pass.
  - Sort findings into doc drift (fix the map), harness gap (fix the harness, then re-drive it), or product gap (report it; keep it out of this change).
- **When the checks run.** Behaviour proven through a verify skill counts as evidence only when it is cited as local evidence. Registered `checks.json` checks remain the only automatic gate.

This skill also carries a one-line attribution to pstack (MIT) for the ideas, and states that the verification example was used only as a structural reference.

## Content: other edits

- **`AGENTS.md`** (Working rules), one line: "When delegating implementation, follow the `change-execution` skill. The delegating agent stays responsible for the change: workers act only from a closed brief within `write_scope`, never approve, commit, merge or edit the packet, and their reports are accepted only after the delegating agent re-runs verification itself."
- **`sdlc-artifacts`.**
  - Plan bullet, appended: "Make each Order-of-work step name the files it changes and one command that proves it, so it can become a unit brief."
  - Implement, one bullet: "To delegate, follow the `change-execution` skill."
- **`docs/agent-surfaces.md`.**
  - Three clearly separated parts:
    1. **Repository-owned portable contract.** `AGENTS.md`, canonical skills in `.agents/skills/`, the `change-execution` roles, tiers and brief, and `repo.py`. This is the only part the repository promises.
    2. **Currently observed harness integration.** Dated observations, backed by smoke tests: Claude Code through `.claude/skills` symlinks, and Codex reading `AGENTS.md` and `.agents/skills/` natively, with the step 5 rows. Anything not smoke-tested is marked "not verified".
    3. **Optional user-local model/tier mapping.** Mapping `high`, `standard` and `economy` to models is an optimization, done outside the repository by whatever mechanism the installed harness offers. It names no configuration path as a required or stable interface; a path is described only if step 5 actually proved it in the installed harness, and then only as observed. When no stable per-role mapping exists, select the worker model manually when spawning; the contract is unchanged. No model names.
- **`README.md`.** Add the two skills to the list. Add one sentence saying Codex discovers `.agents/skills` natively.

## Order of work

Each step names its files and its proving command, following the rule this change adds.

1. **Plan approval (owner).** The owner approves the exact digest. The agent records the claim and confirms `stage=implementation readiness=ready`.
2. **Packet commit.** Commit the approved packet on `change/portable-execution` as the App.
3. **Skills.** Write the two skill directories and their references. Add the two `.claude/skills` symlinks.
   - Proof: `python3 scripts/repo.py status --change portable-execution` shows no `adapter-broken` or `adapter-missing` finding for the new skills, and `status: ok`.
4. **Edits.** Edit `AGENTS.md`, `sdlc-artifacts`, `README.md` and `docs/agent-surfaces.md` (the parts that don't depend on the smoke test).
   - Proof: `status --change portable-execution` shows no path outside `write_scope`.
5. **Discovery smoke tests, read-only, in a scratch clone.** Never run these in the working checkout, and don't change any harness setting.
   - **Claude Code:** the existing procedure in `docs/agent-surfaces.md`, confirming both new skills are listed.
   - **Codex:** the same questions through `codex exec` with a `read-only` sandbox, asking whether `AGENTS.md` is in context and which skills are available.
   - Record one row per harness in `docs/agent-surfaces.md`. A failure is recorded as a failure, not hidden.
6. **Dry run of the contract, not a feature.**
   - Fill `worker-brief.md` for a tiny, throwaway, docs-only unit in a scratch clone. Hand it to an `economy`-tier worker in each harness that is available, where Codex is used only if step 5 passed.
   - Apply step 7 of the skill to each result.
   - This checks that a cheap worker can follow the brief and return the fixed REPORT shape. Nothing from the scratch clone is committed.
   - Only the outcome, with harness, tier, and whether the report shape was followed, goes into the PR description.
   - If the contract fails on a cheap worker, fix the brief template first, within this change.
7. **Local verification.**
   - `python3 scripts/repo.py verify --change portable-execution` and `verify --full`: `control-plane` must pass, with no `failed`, `blocked` or `not-run`.
   - `status --change portable-execution` must report `status: ok`.
8. **Self-review** against `REVIEW.md`. Check that the repository gained no model name, Cursor file, runtime or state store, with `grep -rniE 'cursor|opus|sonnet|haiku|fable|luna|sol\b|grok|gpt-' .agents/ AGENTS.md README.md`. The only allowed hits are the attribution line and harness mechanism field names.
9. **Candidate closure.** Add `closure.json` with:
   - `schema`: 1;
   - `baseline`: `{}`;
   - `packet_sha256`: from `repo.py`'s closure logic;
   - `evidence`: the step 7 local evidence only.

   Confirm `stage=closed freshness=current readiness=ready closure=candidate`.
10. **Commit, push and PR** as the App, with a body that starts `Change-ID: portable-execution`.
11. **CI.** `summary` passes on the head that contains the closure, and the result is recorded in a PR comment. Any fix commit refreshes the closure evidence in the same commit.
12. **Owner review and squash merge.** The agent does not approve or merge.
13. **Post-merge.** The `push` run passes. `portable-execution` is frozen at the squash commit, and the earlier closures stay frozen.

## Tests and proof

- **Automated.** `control-plane`, the existing `repo.py` tests, covers the adapter symlinks, scope and packet validity. No test is changed.
- **Discovery.** Step 5, with a recorded row per harness.
- **Contract usability.** The step 6 dry run with an economy-tier worker. This is a smoke check, not a benchmark.
- **Behaviour on a real feature is not claimed here.** The first real `behavior` change in `todo-cli-test` after merge is the falsifying experiment. Measure:
  - the route taken;
  - worker tier;
  - retries;
  - scope violations caught;
  - defects the coordinator found in the diff versus defects the owner found;
  - cost per role, against the single-agent `list-summary` baseline.

## Risks and mitigations

- **Contract too heavy for small work.** The single-agent route is the default for trivial changes, and pstack's mandatory delegation is rejected.
- **Weak worker improvises.** Mitigated by a closed FILES list, STOP conditions, PROTECTED oracle tests, and mechanical acceptance. Scope escapes are caught by `git status` and `repo.py`/CI regardless.
- **Harness drift.** Discovery facts are dated and smoke-tested. The contract names no models and depends on no harness configuration path, so a harness or model change touches, at most, the optional user-local mapping or the manual model choice.
- **Codex smoke test needs the owner's Codex account.** It runs read-only in a scratch clone. If it can't run, that is recorded, and the Codex row stays "not verified" without blocking the change.
- **Duplicate authority creeping in.** Units come from the approved plan, and records go only to the PR. The self-review grep and the Overlap inventory guard against this.

## Rollback or recovery

- **Before merge:** close the PR.
- **After merge:** remove or revise through a new `repository` change. The frozen packet is never edited.

## Open questions

None blocking.

- Project-level role files (`.claude/agents`, `.codex/agents`) and an eval for the "false worker report" failure are deliberately deferred until the first real delegated change produces evidence.
- The packet-creation interface stays deferred.
