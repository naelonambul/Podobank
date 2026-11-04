# Implementation Plan

## Summary

Render the existing ERD and system architecture HTML pages as PNG previews in the README. Keep the HTML files as the editable source and regenerate both PNGs with a repeatable Playwright script whenever either diagram changes.

### Approach

Use repository-local PNG snapshots. They render inline in GitHub Markdown and need no separate hosting setup. GitHub Pages would preserve interactive browsing, but adds a published site and repository configuration. The owner selected PNG previews in this session.

## Files and components that change

- `README.md`: replace the two source-file links with clickable inline PNG previews.
- `docs/architecture/podobank-current-erd.png`: full-page, high-resolution capture of the ERD HTML.
- `docs/architecture/podobank-current-architecture.png`: full-page, high-resolution capture of the architecture HTML.
- `frontend/scripts/render-diagram-previews.mjs`: render both existing HTML pages at fixed desktop viewport dimensions with the repository's pinned Playwright dependency; write the PNGs to `docs/architecture/`.
- `docs/architecture/README.md`: document the capture command and require updating the PNGs in the same change as either HTML diagram.

## Order of work

1. Add the Playwright capture script at `frontend/scripts/render-diagram-previews.mjs`. Use fixed wide viewports, device scale factor 2, and full-page screenshots so the output is repeatable and includes the complete diagrams. Proof: `cd frontend && node scripts/render-diagram-previews.mjs` completes after Chromium is installed.
2. Generate both PNG previews under `docs/architecture/`. Proof: `file docs/architecture/podobank-current-erd.png docs/architecture/podobank-current-architecture.png` reports two non-empty PNG images; inspect both captures visually.
3. Update `README.md` to display each PNG and link each preview to its full-size image. Add `docs/architecture/README.md` with the regeneration instructions: install frontend dependencies, install the pinned Playwright Chromium browser, and run the capture script after editing either HTML source. Proof: check both README image targets and the documented command against the files in the tree.
4. Review the complete diff and run `python3 scripts/repo.py verify --change podobank-diagram-previews --full`; require every registered check to pass and complete.

## Tests and proof

- Generate the captures with the committed script and inspect both PNGs.
- Verify the README references both existing PNGs and no longer presents the HTML source links as the diagram previews.
- Run `python3 scripts/repo.py status --change podobank-diagram-previews` before implementation and after the edits.
- Run `python3 scripts/repo.py verify --change podobank-diagram-previews --full` before closure and record its evidence path.

## Risks and mitigations

- A diagram may change without its preview: document the regeneration command next to the source pages and update the image in the same change.
- A viewport may clip wide content: choose a viewport wider than each page's maximum content width and inspect both full-page captures.
- Browser rendering may differ across environments: use the Playwright version pinned in `frontend/package-lock.json` and a fixed viewport and scale factor.

## Rollback or recovery

Before merge, remove the PNG previews and capture script and restore the original README links. After merge, make the correction in a new change packet.

## Open questions

None.
