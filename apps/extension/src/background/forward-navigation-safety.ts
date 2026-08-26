import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  resumeVerificationBlocksNavigation,
  verifySelectedResumeFile,
} from "./resume-file-verification";

export type ForwardNavigationSafety =
  { safe: true } | { safe: false; reason: string };

export function evaluateForwardNavigationSafety(input: {
  page: ApplicationPage;
  selectedResumeSha256: string | null;
}): ForwardNavigationSafety {
  if (input.page.applicationState === "REVIEW") {
    return {
      safe: false,
      reason:
        "This employer page is in application review state. Review the application before continuing.",
    };
  }

  const resumeVerification = verifySelectedResumeFile(input);
  if (resumeVerificationBlocksNavigation(resumeVerification)) {
    return {
      safe: false,
      reason: `${resumeVerification.reason}. Select the résumé chosen for this application, wait for verification to finish, then Resume AutoPilot.`,
    };
  }

  return { safe: true };
}
