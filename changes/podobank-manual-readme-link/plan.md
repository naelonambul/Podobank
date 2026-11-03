# Implementation Plan

## Summary

Add a direct link to the existing Korean user manual from the root README's `모바일 웹 앱` section so readers can find it without browsing the docs directory. Keep the manual and its screenshots as the single version-controlled source.

## Files and components that change

- `README.md`: add one sentence linking to `docs/user-manual.md` beneath `## 모바일 웹 앱`.
- `changes/podobank-manual-readme-link/plan.md` and `change.json`: this plan and its declared write scope.

## Order of work

1. Add the manual link in `README.md` beneath the mobile web app heading. Proof: confirm the relative link resolves to the existing manual and `python3 scripts/repo.py status --change podobank-manual-readme-link` passes.
2. Run `python3 scripts/repo.py verify --change podobank-manual-readme-link --full`; the README path routes to the repository's registered checks. Proof: complete evidence with all registered checks passed.
3. Close with that evidence, review the staged diff, and open a pull request with `Change-ID: podobank-manual-readme-link`.

## Tests and proof

- Validate that the README link points to the existing `docs/user-manual.md` file.
- Run the full registered verification suite because `README.md` is included in the backend, observability and UI check paths.
- Run `python3 scripts/repo.py status --change podobank-manual-readme-link` before and after closure.

## Risks and mitigations

- A copied manual could drift from its screenshot source. Link to the existing document and do not duplicate its text or images.
- The README link could break if the document moves. A local target check and repository status catch this.

## Rollback or recovery

Remove the single README link. Keep the user manual and its screenshots unchanged.

## Open questions

None.
