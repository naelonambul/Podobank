# Implementation Plan: Template vNext control plane

## Summary

Replace the documentation-only SDLC control plane with a small executable one. The design follows the owner-supplied Template vNext plan (Revision 9, sections 5 and 7, tranches T2 to T5). The prerequisite starter change (T0: Claude skill adapters, agent-surface smoke tests, and removal of the prototype workspace) lands separately first.

This is the bootstrap change. It is authorized under the pre-vNext process. Once the candidate `scripts/repo.py` exists, it validates this packet and its diff before merge. No runner authorizes its own creation.

## Files and components that change

- `changes/`: the `_template` skeleton (`change.json`, `plan.md`), `README.md` describing the change model, and this packet.
- Root `plan.md` and the duplicated `sdlc-artifacts/references/` skeletons are removed. Root `intent.md` and `spec.md` lose their editable acceptance front matter and carry a baseline-unestablished marker until a product-init change establishes them.
- `scripts/repo.py`: stdlib-only `status` and `verify`. `scripts/tests/`: `unittest` fixtures.
- `checks.json`: the check registry. The template registers only the `core` group, which needs Python 3 and Git and nothing else.
- `.github/workflows/repository.yml`, `.github/pull_request_template.md`: CI and a machine-readable `Change-ID`.
- `.gitattributes`: LF line endings for digest-bound artifacts.
- `AGENTS.md`, `README.md`, `REVIEW.md`, `.agents/skills/*`, `docs/`, `evals/README.md`, `scripts/*/README.md`: point to `repo.py` instead of restating the algorithms.

## Owner decisions (2026-09-23)

- **`repository` kind.** Keep it for repository, process, and tooling work. Once the product baseline is established, it must not modify root `intent.md` or `spec.md`.
- **Change-local `intent.md` and `spec.md`.** Only a change that actually modifies the baseline carries them, as complete candidate replacement snapshots. Changes that inherit the baseline carry no copies.
- **Unestablished-baseline marker.** It stays in the root placeholders. The first valid `product-init` change removes it.
- **Check groups.** They are execution and isolation units that keep stack-specific toolchains out of the generic control plane. They must never silently skip required checks:
  - every group needs a CI job, or `status` fails;
  - the CI summary requires every job to succeed;
  - a group-filtered `verify` run marks the unrun checks `not-run` and its evidence incomplete.
- **No Node/npm.** The template has no Node/npm dependency. `scripts/repo.py` and the core control plane are Python standard library plus Git only. Downstream projects register Node, Swift, Gradle, Rust, or other toolchains as their own checks and groups.

## Order of work

1. `repo.py status`: computed stage, freshness, approval and readiness; ordered chain; baseline inheritance; candidate and history-anchored closure; Change-ID resolution; write-scope enforcement; instruction-shadowing and skill-adapter checks. Include fixtures.
2. `checks.json` and `repo.py verify`: argv, cwd, timeout, requires and paths; PR-base routing; full suite on `main` and for unmapped paths; `not-applicable` with a reason; `blocked` for missing tools; raw log and SHA-256 evidence. Include fixtures.
3. CI workflow: no path filters; `edited` PR events; per-PR cancel-in-progress concurrency; SHA-pinned actions; `fetch-depth: 0`; every job runs; an `if: always()` summary requires every job to succeed.
4. Documentation and skills point at the control plane.

## Tests and proof

- `python3 -m unittest discover -s scripts/tests -t .` covers every fixture listed in plan sections T2 and T3 of the owner's Template vNext plan.
- `python3 scripts/repo.py status --change template-vnext-control-plane` validates this packet and its diff, once this plan's approval claim is recorded.
- `python3 scripts/repo.py verify` runs registered checks and writes evidence.
- GitHub-hosted CI proofs run in a disposable GitHub repository before the CI contract counts as proven:
  - edited-event reruns;
  - cancelled superseded runs;
  - child failure, blocked, and genuine not-applicable outcomes reaching the summary;
  - strict up-to-date merges;
  - the candidate closure before a squash merge and its authoritative anchor after.
- `main` on the template repository is protected, with the required `summary` check and review policy and a separate constrained agent identity, only after those proofs pass.
- The first stable release tag waits until both PRs are merged, the post-merge `main` verification and closure checks are green, and the baseline is stable.

## Risks and mitigations

- Digest-bound approval claims detect staleness only. They are not identity proof, and the documentation says so.
- Line-ending conversion would change digests. `.gitattributes` pins LF for artifacts.
- Stack-specific tooling creeping into the generic core. `checks.json` registers only the `core` group, and new toolchains must arrive as downstream groups with their own CI jobs.

## Rollback or recovery

Revert the squash commit. The previous documentation-only process is restored as a whole.

## Open questions

- None. The owner settled trust mode (T1) for this repository on 2026-09-23. Dogtailor's hosting and enforcement decision is separate and does not block this change.
