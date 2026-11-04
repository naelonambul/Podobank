# Implementation Plan

## Summary

Make the current MariaDB ERD easy to find from the top of the project README. This is a documentation-only link; it does not change application behavior or schema.

## Files and components that change

- `README.md`
  - Add a short Korean `데이터베이스 ERD` section immediately after the opening project description and before `모바일 웹 앱`.
  - Link to `docs/architecture/podobank-current-erd.html` with a brief note that it shows the current MariaDB schema.

## Order of work

1. Update `README.md` with the ERD section and relative link. Prove the section, exact link, and target file are present with `python3 -c "from pathlib import Path; r=Path('README.md').read_text(); target=Path('docs/architecture/podobank-current-erd.html'); assert '## 데이터베이스 ERD' in r and '(docs/architecture/podobank-current-erd.html)' in r and target.is_file()"`.
2. Review the README diff and run the complete repository verification for this change with `python3 scripts/repo.py verify --change podobank-readme-erd --full`.

## Tests and proof

- No application tests or runtime changes are needed.
- Run `python3 scripts/repo.py status --change podobank-readme-erd` after drafting this plan and after the README edit.
- Run `python3 scripts/repo.py verify --change podobank-readme-erd --full` before closure; require a complete run with no failed, blocked, or not-run checks.
- Record the full verification evidence path in `closure.json`.

## Risks and mitigations

- **Broken or stale link:** use a repository-relative path and verify the target exists in the same tree.
- **Poor discoverability:** place the link directly below the opening project description, before the longer setup instructions.

## Rollback or recovery

Before merge, remove the README section and regenerate verification and closure evidence. After merge, update the README through a new change packet so the closed packet remains immutable.

## Open questions

None.
