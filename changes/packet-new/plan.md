# Implementation Plan

## Summary

Add `python3 scripts/repo.py new`, which creates a change packet mechanically. Today a packet is created by hand: copy `changes/_template/`, copy root artifacts, and fill `change.json` digests. That path already failed once in a pilot: a shell word-splitting slip put both digests into one field. `status` caught it, but the mistake should not be possible.

`new` only scaffolds. It creates no branch, commit or approval. It never overwrites anything, and it changes nothing outside the new `changes/<id>/` directory. `status` remains the only authority on the packet's state.

This is a `repository` change. It inherits no product baseline and does not touch the root `intent.md` or `spec.md`.

## Files and components that change

Final `write_scope`:

```json
["scripts/repo.py", "scripts/tests/test_new.py", "scripts/README.md", "changes/README.md", ".agents/skills/sdlc-artifacts/SKILL.md", "README.md", "AGENTS.md"]
```

| Path | Change |
|---|---|
| `scripts/repo.py` | New `new` subcommand (contract below). The existing `status` and `verify` behaviour is unchanged. |
| `scripts/tests/test_new.py` | New `unittest` fixtures using the existing `RepoCase` harness. |
| `scripts/README.md` | One line describing `new`. |
| `changes/README.md` | "Start from `changes/_template/`" becomes "Create a packet with `repo.py new`". The manual copy is described as the fallback. |
| `.agents/skills/sdlc-artifacts/SKILL.md` | "Start a change", steps 2–3, use `repo.py new`. The rest is unchanged. |
| `README.md` | Quick start step 2 uses `repo.py new`. |
| `AGENTS.md` | One line under "Canonical commands". |

Out of scope:

- `changes/_template/**` stays as it is and remains the single skeleton source;
- `checks.json` and `.github/**`: the existing `control-plane` check already routes `scripts/**`;
- `scripts/tests/support.py`, `status` and `verify` semantics, root `intent.md`/`spec.md`, and every other path.

## Command contract

```text
python3 scripts/repo.py new <id> --kind <kind> --title <text> [--scope <pattern>]... [--with-spec]
```

1. **Refusals.** Each exits 1 with a message on stderr, and nothing is written:
   - `<id>` does not match the existing id rule, or is `_template`;
   - `--kind` is not one of the kinds `status` knows;
   - `--title` is empty;
   - `changes/<id>` already exists, as a file or a directory;
   - a `--scope` pattern fails the existing write-scope pattern check (for example `..` or an absolute path);
   - `--with-spec` is given for a kind where `spec.md` is not optional (only `intent`, `incident` and `architecture` allow it);
   - for kinds that inherit the baseline (all except `product-init` and `repository`), the root `intent.md` or `spec.md` is missing or still unestablished. The message says to start with a `product-init` change;
   - for `product-init`, the root `intent.md` or `spec.md` is missing or already established;
   - no plan skeleton can be found (see 3).
2. **`change.json`**, written with 2-space indentation and a trailing newline:
   - `schema`: 1; `id`; `kind`; `title`;
   - `base`: `{"ref": <baseline_branch from checks.json, default "main">, "commit": <git rev-parse HEAD>}`;
   - `baseline`: the current root `intent.md` and `spec.md` digests for kinds that inherit the baseline, otherwise `{}`;
   - `write_scope`: the `--scope` patterns in the order given, duplicates removed;
   - `approvals`: `[]`.
3. **`plan.md`**: a byte copy of the repository's `changes/_template/plan.md`. If the repository has none (for example, a repository adopting the template runs the pinned release's `repo.py` from a separate checkout), the command uses the `changes/_template/plan.md` shipped beside the running `repo.py`. There is still one skeleton source, and no embedded copy.
4. **Change-local artifacts**: byte copies of the root file for every required artifact other than `plan.md` (`product-init`: `intent.md` and `spec.md`; `intent`: `intent.md`; `behavior`: `spec.md`), plus `spec.md` when `--with-spec` is given.
5. **No partial packet.** Files are written into a temporary directory under `changes/`, which is renamed to `changes/<id>` only when complete. It is removed on any failure.
6. **Output.** The created paths, followed by the next step: `python3 scripts/repo.py status --change <id>`. For `product-init`, also a reminder to remove the unestablished marker from the copied `intent.md` and `spec.md` while drafting them.
7. **Nothing else.** No branch, commit, approval, or file outside `changes/<id>/`.

## Order of work

1. **Plan approval (owner).** The owner approves the exact `plan.md` digest printed by `status`. The coordinator records the claim, confirms `readiness=ready`, and commits the packet as the App.
2. **Implement** `new` in `scripts/repo.py`, reusing the existing helpers: the id rule, the kind table, the scope-pattern check, `root_state`, `load_config` and `git`. Add no new dependency.
3. **Tests** in `scripts/tests/test_new.py`. Each refusal leaves `changes/` byte-for-byte unchanged. Cases:
   - `repository`: `baseline` `{}`, `plan.md` equals the skeleton, and `status --change` reports `stage=plan` with only the pending approval;
   - `behavior` on an established baseline: `baseline` holds the exact root digests, `spec.md` equals the root bytes, and `status` reports `stage=spec`;
   - `intent` with and without `--with-spec`;
   - `product-init` on an unestablished baseline copies both files; it is refused on an established baseline;
   - an inheriting kind is refused on an unestablished baseline;
   - an invalid id, `_template`, an unknown kind, an empty title, and a path-escaping `--scope` are refused;
   - an existing packet is refused and left byte-identical;
   - `--with-spec` on `behavior` is refused;
   - the skeleton fallback: with no `changes/_template/` in the target, the running `repo.py`'s skeleton is used;
   - duplicate `--scope` values are removed; `base.commit` equals `HEAD`.
4. **Docs**: the five documentation edits in the table above. Each points at `repo.py new` and does not restate its algorithm.
5. **Verification.**
   - `python3 -m unittest discover -s scripts/tests -t .` passes;
   - `python3 scripts/repo.py verify --change packet-new` and `verify --full` report no `failed`, `blocked` or `not-run`;
   - `status --change packet-new` shows `status: ok`.
6. **Selective review.** `repo.py` is the verification gate, so one read-only reviewer uses the `change-execution` review brief. Findings are sorted into act on, consider, noted, and dismissed with a reason.
7. **Candidate closure.**
   - `closure.json` with `baseline: {}`, `packet_sha256` and the step 5 local evidence;
   - `status` shows `stage=closed closure=candidate`.
8. **Pull request.**
   - Commit and push as the App, and open a PR whose body starts with `Change-ID: packet-new`.
   - CI `summary` must pass on the closure-containing head. The result is recorded in a PR comment.
   - Later fixes refresh the closure evidence in the same commit.
9. **Human review and merge (owner).** The agent does not approve or merge.
10. **Post-merge.** The `main` push run passes, and `packet-new` is `frozen`.

## Tests and proof

| Contract item | Proof |
|---|---|
| Refusals, and no write on refusal | the negative cases in `test_new.py`, each asserting stderr, exit 1 and an unchanged tree |
| Correct `base`, `baseline` and change-local copies | the positive cases, byte and digest equality against the root |
| The created packet is valid for `status` | each positive case runs `status --change <id>`, which shows the expected stage and no `error` |
| Single skeleton source | the fallback test, plus a code review that no skeleton text is embedded in `repo.py` |
| No regression | the full `control-plane` suite |

## Risks and mitigations

- **Scaffolding mistaken for approval.** `new` writes `approvals: []` and prints `status` as the next step. Approval stays owner-only.
- **Wrong base when run off the baseline branch.** `base.commit` is `HEAD`, which is where the change starts. The printed next step and `changes/README.md` say to run `new` on the change's branch point.
- **Copies drift before approval.** Freshness is already detected by `status` (`stale-baseline`), so `new` needs no extra logic.

## Rollback or recovery

Revert the squash commit. Packets created with `new` stay valid, because they are ordinary packets.

## Open questions

None.
