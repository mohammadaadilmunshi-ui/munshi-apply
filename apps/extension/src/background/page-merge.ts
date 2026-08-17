import type {
  ApplicationPage,
  SecurityCheckpointKind,
} from "@munshi-apply/contracts";

const securityPriority: Record<SecurityCheckpointKind, number> = {
  AUTHENTICATION: 1,
  OTP: 2,
  MFA: 3,
  IDENTITY_VERIFICATION: 4,
  CAPTCHA: 5,
};

function hash(value: string): string {
  let result = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 0x01000193);
  }
  return (result >>> 0).toString(16).padStart(8, "0");
}

function strongestSecurityCheckpoint(
  pages: readonly ApplicationPage[],
): SecurityCheckpointKind | null {
  let strongest: SecurityCheckpointKind | null = null;
  for (const page of pages) {
    const candidate = page.securityCheckpoint;
    if (!candidate) continue;
    if (
      !strongest ||
      securityPriority[candidate] > securityPriority[strongest]
    ) {
      strongest = candidate;
    }
  }
  return strongest;
}

function mergedPageContext(
  pages: readonly ApplicationPage[],
): string | undefined {
  const chunks: string[] = [];
  const seen = new Set<string>();
  for (const page of [...pages].sort(
    (left, right) => left.frameId - right.frameId,
  )) {
    const value = (page.pageContext ?? "").replace(/\s+/g, " ").trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    chunks.push(value);
  }
  const merged = chunks.join(" ").slice(0, 20_000).trim();
  return merged || undefined;
}

function mergedFingerprint(pages: readonly ApplicationPage[]): string {
  const material = [...pages]
    .sort((left, right) => left.frameId - right.frameId)
    .map(
      (page) =>
        `${page.frameId}|${page.documentId}|${page.pageFingerprint}|${page.securityCheckpoint ?? ""}|${page.validationErrorCount}|${page.finalSubmissionBoundary}`,
    )
    .join("||");
  return `merged-${hash(material)}`;
}

export function mergeApplicationPages(
  pages: readonly ApplicationPage[],
): ApplicationPage | null {
  if (pages.length === 0) return null;
  const topLevel = pages.find((page) => page.frameId === 0);
  const base = topLevel ?? pages[0];
  if (!base) return null;

  const controls = pages.flatMap((page) => page.controls);
  const questions = pages.flatMap((page) => {
    const localControlIds = new Set(
      page.controls.map((control) => control.controlId),
    );
    return page.questions.filter((question) =>
      localControlIds.has(question.controlId),
    );
  });
  const navigationCandidates = pages.flatMap(
    (page) => page.navigationCandidates,
  );
  const atsFamily =
    base.atsFamily && base.atsFamily !== "GENERIC"
      ? base.atsFamily
      : (pages.find((page) => page.atsFamily && page.atsFamily !== "GENERIC")
          ?.atsFamily ?? base.atsFamily);

  return {
    ...base,
    controls,
    questions,
    pageContext: mergedPageContext(pages),
    observedAt:
      pages
        .map((page) => page.observedAt)
        .sort((left, right) => right.localeCompare(left))[0] ?? base.observedAt,
    pageFingerprint: mergedFingerprint(pages),
    securityCheckpoint: strongestSecurityCheckpoint(pages),
    validationErrorCount: pages.reduce(
      (total, page) => total + page.validationErrorCount,
      0,
    ),
    navigationCandidates,
    finalSubmissionBoundary: pages.some((page) => page.finalSubmissionBoundary),
    atsFamily,
  };
}
