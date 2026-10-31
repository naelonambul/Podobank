# Implementation Plan

## Summary

Add `docs/adoption.md`: how an **existing** repository adopts a pinned template release, and how it later moves to a newer release. Today the template documents only the greenfield path (create from template, then `product-init`). An existing product such as Dogtailor would have to invent the adoption steps, and could do so in ways that fabricate approval or overwrite existing authority.

The guide rests on one property of the current control plane, which the rehearsal below re-proves: a root `intent.md` or `spec.md` **without** the unestablished marker already counts as an established baseline. So an existing product that already has those root files adopts **without** a `product-init`:

- their bytes stay unchanged;
- no approval claims are created for them;
- earlier acceptance records stay as history;
- later changes inherit them through ordinary `baseline` digests.

This is a `repository` change: documentation only, with no `scripts/**`, `checks.json` or `.github/**` change. It is implemented after `packet-new` merges, because the guide and its rehearsal use `repo.py new`. Before implementing, `main` is merged into this branch so the scope diff stays clean.

## Files and components that change

Final `write_scope`:

```json
["docs/adoption.md", "README.md", "changes/README.md", ".agents/skills/sdlc-artifacts/SKILL.md"]
```

| Path | Change |
|---|---|
| `docs/adoption.md` | New guide (outline below). |
| `README.md` | "Project initialization" and "Template releases" each gain one sentence pointing at `docs/adoption.md` for existing repositories and upgrades. |
| `changes/README.md` | The paragraph on the unestablished marker gains one sentence: an existing product with root `intent.md`/`spec.md` adopts through `docs/adoption.md`, not `product-init`. |
| `.agents/skills/sdlc-artifacts/SKILL.md` | "Start a change", step 1 gains the same pointer. |

Out of scope: `scripts/**` (no new adoption command), `checks.json`, `.github/**`, `changes/_template/**`, `docs/host-setup.md` (linked, not changed), and any Dogtailor repository or Dogtailor-specific content.

## Guide outline (`docs/adoption.md`)

1. **Choose the path.**
   - If the repository has root `intent.md` and `spec.md` that the owner treats as the product authority, use the existing-product path.
   - If it has neither, or they are not authoritative, create the unestablished placeholders and use the greenfield `product-init` path.
   - If requirements live in several files, only the root `intent.md` and `spec.md` are digest-tracked. The guide says so, and says the owner decides whether to fold the other files in through a later `behavior` change.
2. **Pin a release.**
   - Adopt a release tag, never a moving `main`.
   - Keep a separate checkout of the tag.
   - Record the tag and its commit in the adoption packet's `plan.md`. No new metadata file.
3. **Create the adoption packet before installing anything.**
   - From the target repository root, run the tag's `repo.py` from its checkout: `python3 <tag-checkout>/scripts/repo.py new adopt-sdlc-template --kind repository --title ... --scope ...`. The skeleton fallback from `packet-new` makes this work before `changes/_template/` exists.
   - Draft the plan, get the owner's digest approval, and check readiness with the same external `repo.py status --change adopt-sdlc-template`.
   - Like the template's own bootstrap change, the adoption is authorized by the owner's approval of its plan. Once installed, the local `repo.py` re-validates the packet.
4. **Install.** Three groups of files:
   - **Copy verbatim from the tag:** `scripts/repo.py`, `scripts/__init__.py`, `scripts/tests/`, `changes/README.md`, `changes/_template/`, `.github/workflows/repository.yml`, and the core skills with their `.claude/skills/` adapters (`sdlc-artifacts`, `change-execution`, `verification-map`, `repository-quality`; the optional tool skills only if wanted).
   - **Merge by hand, keeping the project's content:** `AGENTS.md` (add the SDLC gates and canonical commands; resolve any `CLAUDE.md` shadowing, as `status` reports it), `REVIEW.md`, `.gitignore` (`.evidence/`), `.gitattributes` (LF for digest-bound artifacts), `.github/pull_request_template.md` (a `Change-ID:` first line).
   - **Never copy:** the template's root `intent.md`, `spec.md`, `README.md`, `LICENSE`, its own `changes/<id>/` packets, `docs/`, and `evals/`.
   - The root `intent.md` and `spec.md` are **not edited**. That includes any legacy acceptance front matter, which stays as a historical record.
5. **Retire the root plan.**
   - `git mv` a root `plan.md` and any migration ledgers into `docs/history/`, byte-unchanged.
   - Active plans live only in change packets from now on.
6. **Register existing checks.**
   - Put the project's existing commands in `checks.json` with exact argv, cwd, timeout, paths and requires, alongside the template's `control-plane` check. Reuse the native entry points; do not rewrite them.
   - Each toolchain gets its own group, and each group its own `repository.yml` job in the summary's `needs`. `status` fails when they disagree.
   - Existing workflows may stay.
   - A check must itself fail when it discovers zero tests; `repo.py` cannot see test counts.
7. **Verify and close.**
   - Run `status --change adopt-sdlc-template` and `verify --full`.
   - Add a candidate closure with `baseline: {}` (a `repository` change), then open a PR with a `Change-ID`.
   - Do the host setup per `docs/host-setup.md`. On a private repository without rulesets, CI is advisory and the post-merge `main` run is the first authoritative gate.
8. **After adoption.**
   - Create the first product change with `repo.py new <id> --kind behavior|intent|...`. It records the current root digests.
   - Legacy acceptance front matter may be removed only inside an owner-approved change to that file.
9. **Upgrade to a newer release.**
   - Create one `repository` change, `template-upgrade-<tag>`.
   - Diff the verbatim-copied files between the old and new tags, and apply the diff.
   - Re-merge the hand-merged files.
   - Run the control-plane tests and `verify --full`, and record the new tag in its plan.
   - There is no upgrade automation until real upgrades justify it.

## Order of work

1. **Plan approval (owner).** The owner approves the exact `plan.md` digest. The coordinator records the claim and commits the packet as the App. Implementation waits until `packet-new` has merged.
2. **Refresh the base.** Merge `main` (with `packet-new`) into `change/brownfield-adoption`. Confirm `status --change brownfield-adoption` is `ready` with a clean scope.
3. **Write** `docs/adoption.md` and the three one-sentence pointers.
4. **Rehearsal (proof).** Follow the guide literally in a disposable local fixture repository in the coordinator's scratch space, never in Dogtailor. The fixture has:
   - root `intent.md`/`spec.md` with legacy `status: accepted` front matter and no marker;
   - a root `plan.md`;
   - a project `AGENTS.md`;
   - a `unittest` suite with an existing command;
   - an existing CI workflow.

   It uses this branch's tree as the "release checkout". The rehearsal must show:
   - the adoption packet is created with the external `repo.py new` before `changes/_template/` exists;
   - after installation, `status --change adopt-sdlc-template` gives `status: ok`, and `verify --full` passes both `control-plane` and the registered existing test check;
   - the candidate closure is valid;
   - after a local squash commit on the fixture's `main`, the adoption packet is `frozen`;
   - root `intent.md` and `spec.md` are byte-identical to before adoption at every step;
   - `repo.py new first-change --kind behavior` then records the root digests and reaches `stage=spec`;
   - `repo.py new x --kind product-init` is refused, because the baseline is established.

   Any step that fails, or that the guide does not state exactly, is fixed in the guide and rehearsed again. The rehearsal script and its transcript stay outside the repository and are summarised in the PR.
5. **Verification.** `verify --change brownfield-adoption` and `verify --full` report no `failed`, `blocked` or `not-run`.
6. **Review.** One read-only reviewer uses the `change-execution` review brief, because this is new process guidance for adopting repositories. It checks the guide against `repo.py`'s actual behaviour and the rehearsal transcript.
7. **Candidate closure, PR and CI**, as in the lifecycle:
   - `closure.json` with local evidence;
   - a PR starting `Change-ID: brownfield-adoption`;
   - CI `summary` passing on the closure-containing head, recorded in a PR comment.
8. **Human review and merge (owner).** The agent does not approve or merge.
9. **Post-merge.** The `main` push run passes, and `brownfield-adoption` is `frozen`.

## Tests and proof

| Claim in the guide | Proof |
|---|---|
| Existing root files are an established baseline, with no `product-init` | rehearsal: `new --kind behavior` reaches `stage=spec`, and `new --kind product-init` is refused |
| Adoption creates no approvals for, and makes no edits to, `intent.md`/`spec.md` | rehearsal: byte equality at every step; the adoption packet is a `repository` kind, which `status` forbids from editing an established baseline |
| Packet created before installation | rehearsal: external `repo.py new` and `status` |
| Existing commands run through the registry | rehearsal: `verify --full` passes the registered existing check |
| Closure lifecycle works after adoption | rehearsal: candidate, then frozen after a local squash |

## Risks and mitigations

- **Guide drifts from `repo.py`.** The guide points at commands and does not restate algorithms. The rehearsal pins its current behaviour.
- **Adopter overwrites project files.** The guide lists files to copy, merge and never copy. `status` enforces write scope on the adoption diff.
- **False sense of enforcement in private repositories.** The guide points at advisory mode in `docs/host-setup.md`.

## Rollback or recovery

Revert the squash commit. There is no behaviour change.

## Open questions

None.
