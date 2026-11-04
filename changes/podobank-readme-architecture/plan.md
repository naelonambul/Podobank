# Implementation Plan

## Summary

Add a prominent README link to the existing current-system architecture diagram, alongside the existing ERD link near the top of the README. The architecture HTML itself remains unchanged.

## Files and components that change

<!-- Must be covered by change.json write_scope. -->

- `README.md`: add a short architecture section linking to `docs/architecture/podobank-current-architecture.html`.

## Order of work

1. Edit `README.md` immediately after the database ERD section to link to the current architecture HTML. Proof: `test -f docs/architecture/podobank-current-architecture.html` and inspect the rendered Markdown link in the README.
2. Run `python3 scripts/repo.py verify --change podobank-readme-architecture --full` and confirm every registered check completes successfully.
3. Run `python3 scripts/repo.py status --change podobank-readme-architecture`, then close the change using the full verification evidence.

## Tests and proof

- The README link uses a repository-relative path and points to the existing architecture diagram.
- `python3 scripts/repo.py verify --change podobank-readme-architecture --full` completes with no failed, blocked, or not-run checks.
- `python3 scripts/repo.py status --change podobank-readme-architecture` reports the change packet as valid before and after implementation.

## Risks and mitigations

- A path typo would make the link unusable. Check that the referenced HTML file exists and inspect the README link before closing.

## Rollback or recovery

Remove the README link before closing if it points to the wrong or outdated diagram. After merge, restore the previous README through a new change packet.

## Open questions

None.
