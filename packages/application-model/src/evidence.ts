import type { SemanticType, TrustLevel } from "@munshi-apply/contracts";

export const evidenceKinds = [
  "PROFILE_FACT",
  "RESUME_BULLET",
  "EMPLOYMENT",
  "EDUCATION",
  "PROJECT",
  "CERTIFICATION",
  "JOB_REQUIREMENT",
  "COMPANY_CONTEXT",
  "USER_CONFIRMED_ANSWER",
] as const;

export type EvidenceKind = (typeof evidenceKinds)[number];

export type EvidenceNode = {
  evidenceId: string;
  kind: EvidenceKind;
  text: string;
  semanticTypes: readonly SemanticType[];
  trustLevel: TrustLevel;
  protected: boolean;
  source: string;
  updatedAt: string;
};

export type EvidenceEdge = {
  fromEvidenceId: string;
  toEvidenceId: string;
  relation: "SUPPORTS" | "DERIVED_FROM" | "CONTRADICTS" | "DUPLICATES";
};

export type EvidenceGraph = {
  nodes: readonly EvidenceNode[];
  edges: readonly EvidenceEdge[];
};

export type EvidenceRetrievalRequest = {
  query: string;
  semanticType: SemanticType;
  maxResults?: number;
  includeProtected?: boolean;
  allowedTrustLevels?: readonly TrustLevel[];
};

export type RetrievedEvidence = EvidenceNode & {
  score: number;
  semanticMatch: boolean;
  tokenOverlap: number;
};

export type EvidenceContext = {
  query: string;
  semanticType: SemanticType;
  items: readonly RetrievedEvidence[];
  blockedProtectedCount: number;
  excludedByTrustCount: number;
};

const defaultAllowedTrustLevels: readonly TrustLevel[] = [
  "VERIFIED",
  "USER_CONFIRMED",
  "DOCUMENT_CONFIRMED",
];

const trustWeight: Readonly<Partial<Record<TrustLevel, number>>> = {
  VERIFIED: 1,
  USER_CONFIRMED: 0.95,
  DOCUMENT_CONFIRMED: 0.92,
  DERIVED: 0.7,
  LEARNED: 0.55,
  GENERATED: 0.1,
  UNKNOWN: 0,
};

function normalize(value: string): string {
  return value
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function tokens(value: string): Set<string> {
  const normalized = normalize(value);
  if (!normalized) return new Set();
  return new Set(
    normalized
      .split(" ")
      .map((token) => token.trim())
      .filter((token) => token.length >= 2),
  );
}

function overlapRatio(query: Set<string>, evidence: Set<string>): number {
  if (query.size === 0 || evidence.size === 0) return 0;
  let overlap = 0;
  for (const token of query) {
    if (evidence.has(token)) overlap += 1;
  }
  return overlap / query.size;
}

function validateMaxResults(value: number | undefined): number {
  if (value === undefined) return 5;
  if (!Number.isSafeInteger(value) || value < 1 || value > 25) {
    throw new Error("maxResults must be an integer between 1 and 25");
  }
  return value;
}

function scoreNode(
  node: EvidenceNode,
  semanticType: SemanticType,
  queryTokens: Set<string>,
): RetrievedEvidence {
  const semanticMatch = node.semanticTypes.includes(semanticType);
  const tokenOverlap = overlapRatio(queryTokens, tokens(node.text));
  const trust = trustWeight[node.trustLevel] ?? 0;
  const score = Number(
    (semanticMatch ? 0.55 : 0.15 * tokenOverlap) +
      (semanticMatch ? 0.25 * tokenOverlap : 0) +
      0.2 * trust,
  );

  return {
    ...node,
    score: Math.min(1, Math.max(0, Number(score.toFixed(6)))),
    semanticMatch,
    tokenOverlap: Number(tokenOverlap.toFixed(6)),
  };
}

export function retrieveEvidence(
  graph: EvidenceGraph,
  request: EvidenceRetrievalRequest,
): EvidenceContext {
  const allowed = new Set(
    request.allowedTrustLevels ?? defaultAllowedTrustLevels,
  );
  const includeProtected = request.includeProtected ?? false;
  const maxResults = validateMaxResults(request.maxResults);
  const queryTokens = tokens(request.query);
  let blockedProtectedCount = 0;
  let excludedByTrustCount = 0;

  const scored: RetrievedEvidence[] = [];
  for (const node of graph.nodes) {
    if (node.protected && !includeProtected) {
      blockedProtectedCount += 1;
      continue;
    }
    if (!allowed.has(node.trustLevel)) {
      excludedByTrustCount += 1;
      continue;
    }

    const candidate = scoreNode(node, request.semanticType, queryTokens);
    if (!candidate.semanticMatch && candidate.tokenOverlap === 0) continue;
    scored.push(candidate);
  }

  scored.sort((left, right) => {
    if (right.score !== left.score) return right.score - left.score;
    if (left.updatedAt !== right.updatedAt) {
      return right.updatedAt.localeCompare(left.updatedAt);
    }
    return left.evidenceId.localeCompare(right.evidenceId);
  });

  return {
    query: request.query,
    semanticType: request.semanticType,
    items: scored.slice(0, maxResults),
    blockedProtectedCount,
    excludedByTrustCount,
  };
}

export function evidenceHasContradiction(
  graph: EvidenceGraph,
  evidenceIds: readonly string[],
): boolean {
  const selected = new Set(evidenceIds);
  return graph.edges.some(
    (edge) =>
      edge.relation === "CONTRADICTS" &&
      selected.has(edge.fromEvidenceId) &&
      selected.has(edge.toEvidenceId),
  );
}
