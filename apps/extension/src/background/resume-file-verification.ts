import type { ApplicationPage, Control } from "@munshi-apply/contracts";

export type ResumeFileVerification =
  | { state: "NOT_APPLICABLE"; reason: string; controlIds: string[] }
  | { state: "OPTIONAL_EMPTY"; reason: string; controlIds: string[] }
  | { state: "REQUIRED_MISSING"; reason: string; controlIds: string[] }
  | { state: "PENDING"; reason: string; controlIds: string[] }
  | { state: "MATCH"; reason: string; controlIds: string[] }
  | { state: "MISMATCH"; reason: string; controlIds: string[] };

const resumePattern = /\b(resume|résumé|cv|curriculum vitae)\b/i;
const nonResumeAttachmentPattern =
  /\b(cover letter|portfolio|transcript|reference|work sample|writing sample|certificate|certification|license|licence)\b/i;

function fileContext(control: Control): string {
  return [
    control.label,
    control.name,
    control.ariaLabel,
    control.placeholder,
    control.accept,
  ]
    .filter((value): value is string => Boolean(value))
    .join(" ");
}

export function isResumeFileControl(control: Control): boolean {
  if (control.kind !== "FILE" || control.disabled) return false;
  const context = fileContext(control);
  return (
    resumePattern.test(context) && !nonResumeAttachmentPattern.test(context)
  );
}

export function verifySelectedResumeFile(input: {
  page: ApplicationPage;
  selectedResumeSha256: string | null;
}): ResumeFileVerification {
  const expected = input.selectedResumeSha256;
  if (!expected) {
    return {
      state: "NOT_APPLICABLE",
      reason:
        "No application résumé digest is selected for this AutoPilot session",
      controlIds: [],
    };
  }

  const controls = input.page.controls.filter(isResumeFileControl);
  const controlIds = controls.map((control) => control.controlId);
  if (controls.length === 0) {
    return {
      state: "NOT_APPLICABLE",
      reason: "No résumé upload control is present on this page",
      controlIds,
    };
  }

  const missingRequired = controls.filter(
    (control) => control.required && control.fileSelected !== true,
  );
  if (missingRequired.length > 0) {
    return {
      state: "REQUIRED_MISSING",
      reason: "A required résumé upload field has no selected file",
      controlIds: missingRequired.map((control) => control.controlId),
    };
  }

  const selected = controls.filter((control) => control.fileSelected === true);
  if (selected.length === 0) {
    return {
      state: "OPTIONAL_EMPTY",
      reason: "The résumé upload field is optional and no file is selected",
      controlIds,
    };
  }

  const ready = selected.filter(
    (control) =>
      control.fileFingerprintState === "READY" && Boolean(control.fileSha256),
  );
  if (ready.length !== selected.length) {
    return {
      state: "PENDING",
      reason:
        "The selected résumé file has not finished browser-side SHA-256 verification",
      controlIds: selected.map((control) => control.controlId),
    };
  }

  if (ready.some((control) => control.fileSha256 !== expected)) {
    return {
      state: "MISMATCH",
      reason:
        "The résumé file selected in the employer form does not match the résumé chosen for this application",
      controlIds: ready.map((control) => control.controlId),
    };
  }

  return {
    state: "MATCH",
    reason: "The employer résumé field matches the selected application résumé",
    controlIds: ready.map((control) => control.controlId),
  };
}

export function resumeVerificationBlocksNavigation(
  verification: ResumeFileVerification,
): boolean {
  return ["REQUIRED_MISSING", "PENDING", "MISMATCH"].includes(
    verification.state,
  );
}
