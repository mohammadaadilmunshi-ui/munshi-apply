import type { EvidenceGraph, EvidenceNode, TrustLevel } from "./evidence";
import type { JobResponsePlan } from "./job-response";

export type RetrievalHit = {
  node: EvidenceNode;
  score: number;
  reasons: string[];
};

export type HybridRetrievalOptions = {
  query: string;
  semanticType?: string;
  plan?: JobResponsePlan;
  maxResults?: number;
  includeProtected?: boolean;
  allowedTrustLevels?: readonly TrustLevel[];
};

const trustWeight: Record<TrustLevel, number> = {
  VERIFIED: 1,
  USER_CONFIRMED: 0.96,
  DOCUMENT_CONFIRMED: 0.94,
  IMPORTED: 0.62,
  GENERATED: 0.15,
};

const kindWeight: Record<string, number> = {
  JOB_REQUIREMENT: 1,
  COMPANY_CONTEXT: 0.98,
  RESUME_BULLET: 0.95,
  EMPLOYMENT: 0.92,
  PROJECT: 0.88,
  EDUCATION: 0.78,
  CERTIFICATION: 0.76,
  USER_CONFIRMED_ANSWER: 0.9,
  PROFILE_FACT: 0.72,
};

function tokens(value: string): Set<string> {
  return new Set(
    value
      .toLowerCase()
      .match(/[a-z0-9+#.-]{2,}/g)
      ?.filter(Boolean) ?? [],
  );
}

function phraseBonus(text: string, terms: readonly string[]): number {
  const lower = text.toLowerCase();
  const matches = terms.filter((term) => lower.includes(term.toLowerCase())).length;
  return Math.min(0.24, matches * 0.04);
}

export function retrieveEvidenceHybrid(
  graph: EvidenceGraph,
  options: HybridRetrievalOptions,
): RetrievalHit[] {
  const maxResults = Math.max(1, Math.min(options.maxResults ?? 7, 20));
  const allowedTrust = new Set<TrustLevel>(
    options.allowedTrustLevels ?? ["VERIFIED", "USER_CONFIRMED", "DOCUMENT_CONFIRMED"],
  );
  const planTerms = options.plan?.retrievalTerms ?? [];
  const queryTokens = tokens([options.query, ...planTerms].join(" "));
  const candidates: RetrievalHit[] = [];
  for (const node of graph.nodes) {
    if (node.protected && !options.includeProtected) continue;
    if (!allowedTrust.has(node.trustLevel)) continue;
    const nodeTokens = tokens(node.text);
    const overlapCount = [...queryTokens].filter((token) => nodeTokens.has(token)).length;
    const lexical = queryTokens.size > 0 ? overlapCount / queryTokens.size : 0;
    const semanticMatch = Boolean(
      options.semanticType && node.semanticTypes.includes(options.semanticType),
    );
    const intentBonus = phraseBonus(node.text, planTerms);
    const jobRequirementBonus =
      options.plan?.requiresJobContext && ["JOB_REQUIREMENT", "COMPANY_CONTEXT"].includes(node.kind)
        ? 0.18
        : 0;
    const candidateBonus =
      options.plan?.requiresCandidateEvidence &&
      ["RESUME_BULLET", "EMPLOYMENT", "PROJECT", "EDUCATION", "CERTIFICATION"].includes(node.kind)
        ? 0.14
        : 0;
    if (!semanticMatch && lexical === 0 && intentBonus === 0 && jobRequirementBonus === 0) continue;
    const score =
      (semanticMatch ? 0.42 : 0) +
      lexical * 0.28 +
      intentBonus +
      jobRequirementBonus +
      candidateBonus +
      (trustWeight[node.trustLevel] ?? 0.5) * 0.12 +
      (kindWeight[node.kind] ?? 0.5) * 0.08;
    const reasons = [
      semanticMatch ? "semantic-type" : "",
      lexical > 0 ? "lexical-overlap" : "",
      intentBonus > 0 ? "intent-term" : "",
      jobRequirementBonus > 0 ? "job-context" : "",
      candidateBonus > 0 ? "candidate-evidence" : "",
    ].filter(Boolean);
    candidates.push({ node, score, reasons });
  }
  candidates.sort((left, right) => right.score - left.score || right.node.updatedAt.localeCompare(left.node.updatedAt));

  const selected: RetrievalHit[] = [];
  const sources = new Map<string, number>();
  for (const candidate of candidates) {
    if (selected.length >= maxResults) break;
    const count = sources.get(candidate.node.source) ?? 0;
    if (count >= 3 && candidates.some((item) => (sources.get(item.node.source) ?? 0) === 0)) continue;
    const contradictory = graph.edges.some(
      (edge) =>
        edge.relation === "CONTRADICTS" &&
        ((edge.fromEvidenceId === candidate.node.evidenceId && selected.some((item) => item.node.evidenceId === edge.toEvidenceId)) ||
          (edge.toEvidenceId === candidate.node.evidenceId && selected.some((item) => item.node.evidenceId === edge.fromEvidenceId))),
    );
    if (contradictory) continue;
    if (selected.some((item) => item.node.text.trim().toLowerCase() === candidate.node.text.trim().toLowerCase())) continue;
    selected.push(candidate);
    sources.set(candidate.node.source, count + 1);
  }
  return selected;
}
