# MUNSHI Apply — Live ATS Deep Repair

**Date:** 2026-08-16  
**Branch:** `feat/v3-foundation-alignment`  
**Status:** **PHYSICAL EDGE RELEASE GATE FAILED — further runtime repair required**

## Why this report changed

The automated repair and CI suites passed, but a subsequent physical Microsoft Edge run of the unpacked `0.2.0` extension exposed additional live runtime failures. The Edge extensions page is showing an **Errors** control for MUNSHI Apply, and the owner reported many additional live bugs after installing the supposedly verified build.

This means automated CI success is **not** sufficient evidence that this build is release-ready. The current branch must remain draft/unmerged until the physical browser runtime is clean and the live ATS regression set passes again.

## Current physical findings

The attached Edge evidence shows MUNSHI Apply `0.2.0` enabled as an unpacked extension with recorded extension errors. The supplied copied text is compiled content-script/runtime source around scanner, security-checkpoint, application-state, native fill, radio/checkbox, date, and custom-combobox paths; it is not itself the exception header or stack trace.

A new runtime audit has therefore been opened across these boundaries:

- content-script lifecycle and reinjection/idempotence
- scanner and prompt/control identity
- native and ARIA radio/checkbox behavior
- custom/portaled combobox discovery and verification
- employer-format date handling
- page/step identity on dynamic single-page ATS forms
- service-worker promise/error handling
- side-panel snapshot churn and answer preservation
- native-companion/AI request path

## Release rule

Do **not** merge PR #11 and do **not** call this build release-ready merely because CI is green. The next accepted release candidate must satisfy both:

1. automated repository/extension/native-host verification; and
2. a clean physical Edge run with no current extension errors plus live ATS smoke coverage.

The physical browser result is authoritative for this gate.
