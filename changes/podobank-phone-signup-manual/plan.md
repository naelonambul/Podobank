# Implementation Plan

## Summary

Update the Korean user manual so a first-time customer can follow the new phone-number signup path from the signup-method screen through the completed form. The current text mentions phone signup, but its only signup image shows the Kakao profile form. Add annotated mobile screenshots for the signup choices and phone signup form, and make the number-format explanation match the implemented 3-4-4 digit pattern.

## Files and components that change

- `docs/user-manual.md`: explain the signup choice, phone signup fields, required password confirmation, lack of SMS verification, and automatic account creation in the order a customer sees them. Keep the existing Kakao profile screenshot and clarify that it documents the separate Kakao path.
- `docs/images/user-manual/11-signup-methods.png`: annotated 384 × 832 screenshot showing the phone and Kakao signup choices, with the phone path marked.
- `docs/images/user-manual/12-phone-signup-profile.png`: annotated 384 × 832 screenshot of the top of the phone signup form, including name, phone number and profile fields.
- `docs/images/user-manual/13-phone-signup-password.png`: annotated 384 × 832 screenshot of the lower form, including required password confirmation and the account-creation button.

The screenshots will use fabricated demo values. Browser API requests will be intercepted with local examples; the form will not be submitted and no service data will be written.

## Order of work

1. Drive the signup-choice and phone-signup screens from the local frontend in a 384 × 832 browser. Capture the two form scroll positions and signup-choice screen, then annotate the relevant controls in the manual's existing red callout style. Confirm the documented field labels, password requirement and signup result against `frontend/src/views/SignupStartView.vue` and `frontend/src/views/PhoneSignupView.vue`.
2. Update `docs/user-manual.md` to link the new images in the signup instructions and describe the phone pattern as `000-0000-0000` (three digits, four digits, four digits), with a realistic example. Preserve the separate Kakao signup instructions and state that phone signup does not verify number ownership by SMS.
3. Review every manual image link and each new screenshot at native resolution; confirm no API submission occurred and the new images are legible at mobile width.

## Tests and proof

- Run `python3 scripts/repo.py status --change podobank-phone-signup-manual` after the edits.
- Check that every `docs/user-manual.md` image reference resolves to a tracked image and inspect the three new screenshots at 384 × 832.
- Do not run the application test suite for this documentation-only change unless separately requested. If a full repository verification is required for closure, ask the owner before running it.

## Risks and mitigations

- A screenshot could imply that Kakao and phone signup share the same form. Keep the Kakao profile image and label it as the post-Kakao-authentication flow; add a distinct phone form image.
- Phone input accepts only the implemented 3-4-4 digit layout, with no SMS ownership check. Describe both facts plainly and use synthetic data only.
- Screenshot generation must not write to the deployed service. Intercept API calls and do not submit the form.

## Rollback or recovery

Revert only this change's manual edits and added screenshots. Do not touch the existing screenshots or unrelated local files.

## Open questions

None. The current implementation and the requested phone signup flow determine the manual content.
