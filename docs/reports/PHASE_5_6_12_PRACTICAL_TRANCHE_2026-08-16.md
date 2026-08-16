# MUNSHI Apply — Phase 5 / Phase 6 / Phase 12 Practical Tranche

**Date:** 2026-08-16  
**Candidate:** 0.2.4  
**Functional implementation commit:** `515f916738c069ef191cf3a3b52795a789f73ef8`  
**Verified implementation + cleanup head:** `5419b61c1f0b1de1b92d4551ef6fd6ba0bab9141`  
**This report commit:** `a4c1e453702c78c08351d85bdb66f0c9ebbadd73` (verified by the normal PR workflow set)  
**Architecture source:** Complete Master Architecture Plan 2.0

## Goal

Advance Universal Autofill, Multi-Page AutoPilot, and Teach-MUNSHI together so that real application work stays usable. Safety rules remain around truthful facts, security checkpoints, and final submission; ordinary incomplete fields, optional questions, unfamiliar widgets, and recoverable interaction failures should not unnecessarily stop the application.

## Phase 5 — Universal Autofill

- Existing native/ARIA/custom/date/multi-select filling remains the default engine.
- A taught interaction recipe can now be executed before the normal fallback interaction.
- If a taught recipe does not verify, MUNSHI falls back to its normal universal fill strategy instead of blindly trusting the recipe.
- Every taught-recipe attempt is verified and fed back into recipe confidence.
- Consequential questions may reuse learned _widget mechanics_ because no answer value is stored in the recipe; authentication/security controls remain excluded.

## Phase 6 — Multi-Page AutoPilot

- Required review/unresolved items still stop navigation, but optional review items no longer block page progress.
- Required-field validation shown on an incomplete form no longer stops the entire session before approved fills are attempted.
- A normal fill-verification failure becomes a durable review pause rather than a fatal AutoPilot error. The owner can fix or teach the control and Resume.
- A forward-navigation interaction that cannot be verified becomes a recoverable review pause rather than destroying the session.
- Interrupted fills and ordinary verification timeouts preserve state and surface a resume path when the application page is still available.
- CAPTCHA/MFA/OTP/identity/authentication boundaries and final employer submission remain explicit owner checkpoints.

## Phase 12 — Teach-MUNSHI

Teach-MUNSHI is visible directly inside AutoPilot rather than hidden in Settings.

Flow:

1. Select a visible control.
2. Click **Teach selected control**.
3. Perform that one interaction on the employer page.
4. Click **Learn this interaction**.
5. MUNSHI stores a value-free action recipe in SHADOW state.
6. On the next matching control, MUNSHI tries the taught recipe and verifies the result.
7. One owner demonstration plus one verified automatic success promotes the recipe.
8. Two consecutive verified failures roll a promoted recipe back.

The capture stores interaction mechanics and event classes, not the selected answer text. Recipe actions can reference the future resolved `ANSWER`, but cannot embed the demonstrated value.

## Practical operating principle

Guardrails should prevent incorrect claims, irreversible submission, credential/security abuse, and silent changes to protected facts. They should not turn routine application friction into a dead end. Recoverable form failures therefore pause with an obvious next action: correct manually, Teach MUNSHI, or Resume.

## Automated verification

The implementation and subsequent report-only commit were verified by the normal PR workflow set:

- CI ✅
- Browser tests ✅
- Security ✅
- Migration tests ✅
- Owner workspace ✅

The verification stack included:

- TypeScript/JavaScript: **46 test files / 286 tests passed**
- Native companion: Ruff passed / **92 Pytest tests passed**
- Prettier ✅
- ESLint ✅
- TypeScript type checking ✅
- Production extension build ✅
- Desktop/mobile artifact verification ✅
- Repository safety and secret scan ✅

Fresh unpacked Edge artifact from CI at `a4c1e453702c78c08351d85bdb66f0c9ebbadd73`:

- name: `munshi-apply-edge-unpacked`
- artifact ID: `9260614215`
- SHA-256: `854bf481529defb8e0618f5ab24e2859d319c2054d6a292b206657ca6f2c0112`

## Release gate

Automated verification establishes source/build integrity; it does not replace the physical Edge acceptance gate. Candidate 0.2.4 must still be exercised on real multi-page applications to validate practical page progression, recoverable pauses, taught recipe capture/reuse, and the existing broad universal-fill interactions under real employer runtime behavior.
