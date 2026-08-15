# Live ATS reliability repair — 2026-08-15

## Trigger

A physical Edge smoke test on a Levin application exposed independent failures not covered by the earlier synthetic gate: a hidden/passive anti-bot frame could still be classified as an active CAPTCHA; an extension reload could leave the already-open application tab without a valid content-script receiver; continuously mutating ATS DOM could starve a forced post-fill snapshot until AutoPilot timed out after filling only email; and visible required markers (`First Name *`, `Last Name *`, `Preferred Pronouns *`) prevented deterministic identity classification.

## Repair

- Desktop `scripting` permission is used only to re-inject MUNSHI's own content runtime when Chromium reports that the receiving end does not exist. The active-page read, AutoPilot start, guarded fill, navigation, and file handoff all use the recovery path.
- The content runtime supports health ping and forced scan commands. Forced post-action scans are immediate and serialized; ordinary mutation scans have a maximum debounce horizon so persistent page animation cannot starve state publication.
- CAPTCHA detection now evaluates ancestor visibility and passive/invisible exclusions before treating a challenge frame as active. Genuine visible CAPTCHA remains an owner checkpoint.
- Semantic normalization removes visible required markers before deterministic classification. `PRONOUNS` is now a first-class semantic type with desktop/hosted profile storage.
- A protected ordinary fact can be ready after explicit owner confirmation. Unconfirmed protected data and sensitive/high-risk questions remain review-gated. Sponsorship/authorization safety policy remains unchanged.
- Hosted deterministic profile lookup was aligned with desktop identity, address, availability, and referral keys.

## Security boundary

This change does not solve, bypass, suppress, or evade CAPTCHA or other anti-bot controls. Final submission, CAPTCHA, MFA, OTP, identity verification, authentication, security challenges, and operating-system file selection remain owner actions.
