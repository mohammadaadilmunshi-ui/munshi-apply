import { controlElementMap, scanDocument } from "./scanner";

export type NavigationResult = {
  status: "NAVIGATED" | "REFUSED" | "FAILED";
  reason: string;
};

export function applyNavigationAction(controlId: string): NavigationResult {
  const page = scanDocument();
  const candidate = page.navigationCandidates.find(
    (item) => item.controlId === controlId,
  );
  if (!candidate) {
    return {
      status: "FAILED",
      reason: "Navigation control is no longer recognized on the active page",
    };
  }
  if (candidate.action === "FINAL_SUBMIT") {
    return {
      status: "REFUSED",
      reason:
        "Final employer submission always requires deliberate owner action",
    };
  }
  if (candidate.action !== "NEXT" && candidate.action !== "REVIEW") {
    return {
      status: "REFUSED",
      reason: "Only verified forward next/review navigation is allowed",
    };
  }
  if (candidate.disabled) {
    return { status: "FAILED", reason: "Navigation control is disabled" };
  }

  const element = controlElementMap().get(controlId);
  if (!(element instanceof HTMLElement)) {
    return { status: "FAILED", reason: "Navigation control is unavailable" };
  }
  element.click();
  return {
    status: "NAVIGATED",
    reason: "Verified safe navigation control was activated",
  };
}
