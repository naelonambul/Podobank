# Implementation Plan

## Summary

Add a Korean user manual for the deployed PodoBank demo at `docs/user-manual.md`, with annotated mobile screenshots of the main customer and bank employee tasks. This change does not alter application behavior.

## Files and components that change

- `docs/user-manual.md`: Korean instructions with the screenshots embedded beside the related steps.
- `docs/images/user-manual/01-start.png`, `02-login.png`, `03-signup.png`, `04-home.png`, `05-transfer-recipient.png`, `06-transfer-confirm.png`, `07-loan-product.png`, `08-loan-pending.png`, `09-staff-review.png`, and `10-overdue-repayment.png`: ten annotated screenshots captured at the mobile touch layout.
- `changes/podobank-user-manual/plan.md` and `change.json`: this plan and its declared write scope.

## Order of work

1. `docs/images/user-manual/*.png`: capture the landing page, login, signup, home, recipient search, transfer confirmation, loan product selection, pending loan state, employee review, and overdue repayment screens at a 384 × 832 mobile viewport. Use Playwright against the deployed frontend bundle. Intercept every request to the deployed API and answer it with synthetic fixture data; do not send account, transfer, loan, login, or review mutations to the live API. Draw a red rounded outline and numbered red badge around each relevant touch target. Proof: inspect the resulting screenshots and run `python3 scripts/repo.py status --change podobank-user-manual` to confirm each new image path is in scope.
2. `docs/user-manual.md`: embed each image under the matching task section with Korean alt text and a short caption. Explain that red numbers mark the touch order. Proof: review the Markdown and run `python3 scripts/repo.py status --change podobank-user-manual` to confirm the document and all assets remain in scope.

## Tests and proof

This is documentation-only and changes no application behavior. Playwright is used to capture the deployed frontend's visible screens; all API-host requests are intercepted and use synthetic data, so the live service is read-only. Review the screenshot callouts against visible controls and the guide against `frontend/src/views/SignupView.vue`, `LoginView.vue`, `HomeView.vue`, `AccountView.vue`, `TransactionsView.vue`, `LoansView.vue`, and `EmployeeLoansView.vue`, plus the loan rules in `spec.md`. Confirm the manual links to the owner-supplied frontend URL and exposes no deployment credentials.

## Risks and mitigations

- The deployed interface may change after capture. Keep screenshot filenames and captions tied to current visible controls, and recapture them when those screens change.
- Screenshots could be mistaken for real customer data. Use only synthetic fixtures and retain the demo notice in the guide.
- Staff credentials are deployment configuration. Do not show credential values in text or screenshots.

## Rollback or recovery

If screenshots or instructions are inaccurate, update only `docs/user-manual.md` and `docs/images/user-manual/` within this change. If the change is withdrawn before merge, remove only the new manual and its new screenshot assets; preserve all pre-existing user files and repository state.

## Open questions

None. The screenshots use the deployed frontend with synthetic API responses and are annotated with red numbered touch points.
