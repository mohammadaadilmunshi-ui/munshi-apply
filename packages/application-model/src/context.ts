import type { TrustLevel } from "@munshi-apply/contracts";
import type {
  EvidenceContext,
  EvidenceGraph,
  RetrievedEvidence,
} from "./evidence";
import { evidenceHasContradiction } from "./evidence";

export type ContextAssemblyPolicy = {
  maxItems: number;
  maxCharacters: number;
};

export type ContextItem = {
  evidenceId: string;
  source: string;
  text: string;
  trustLevel: TrustLevel;
  score: number;
};

export type AssembledContext = {
  query: string;
  semanticType: EvidenceContext["semanticType"];
  items: readonly ContextItem[];
  characterCount: number;
  truncated: boolean;
  excludedEvidenceCount: number;
};

export type GeneratedClaim = {
  claimId: string;
  text: string;
  evidenceIds: readonly string[];
};

export type GeneratedDraft = {
  text: string;
  claims: readonly GeneratedClaim[];
};

export type GeneratedDraftValidation = {
  valid: boolean;
  unsupportedClaimIds: readonly string[];
  contradictoryClaimIds: readonly string[];
  missingClaimStructure: boolean;
  exceedsWordLimit: boolean;
  wordCount: number;
};

function validatePolicy(policy: ContextAssemblyPolicy): void {
  if (!Number.isSafeInteger(policy.maxItems) || policy.maxItems < 1) {
    throw new Error("Context maxItems must be a positive integer");
  }
  if (!Number.isSafeInteger(policy.maxCharacters) || policy.maxCharacters < 1) {
    throw new Error("Context maxCharacters must be a positive integer");
  }
}

function toContextItem(item: RetrievedEvidence): ContextItem {
  return {
    evidenceId: item.evidenceId,
    source: item.source,
    text: item.text,
    trustLevel: item.trustLevel,
    score: item.score,
  };
}

export function assembleEvidenceContext(
  evidence: EvidenceContext,
  policy: ContextAssemblyPolicy,
): AssembledContext {
  validatePolicy(policy);
  const items: ContextItem[] = [];
  let characterCount = 0;
  let truncated = false;

  for (const candidate of evidence.items) {
    if (items.length >= policy.maxItems) {
      truncated = true;
      break;
    }
    const nextCharacters = characterCount + candidate.text.length;
    if (nextCharacters > policy.maxCharacters) {
      truncated = true;
      break;
    }
    items.push(toContextItem(candidate));
    characterCount = nextCharacters;
  }

  return {
    query: evidence.query,
    semanticType: evidence.semanticType,
    items,
    characterCount,
    truncated,
    excludedEvidenceCount: Math.max(0, evidence.items.length - items.length),
  };
}

function countWords(value: string): number {
  const normalized = value.trim();
  if (!normalized) return 0;
  return normalized.split(/\s+/).length;
}

export function validateGeneratedDraft(
  draft: GeneratedDraft,
  context: AssembledContext,
  graph: EvidenceGraph,
  options: { maxWords?: number } = {},
): GeneratedDraftValidation {
  const availableEvidence = new Set(
    context.items.map((item) => item.evidenceId),
  );
  const unsupportedClaimIds: string[] = [];
  const contradictoryClaimIds: string[] = [];

  for (const claim of draft.claims) {
    if (
      claim.evidenceIds.length === 0 ||
      claim.evidenceIds.some((evidenceId) => !availableEvidence.has(evidenceId))
    ) {
      unsupportedClaimIds.push(claim.claimId);
      continue;
    }
    if (evidenceHasContradiction(graph, claim.evidenceIds)) {
      contradictoryClaimIds.push(claim.claimId);
    }
  }

  const wordCount = countWords(draft.text);
  const exceedsWordLimit =
    options.maxWords !== undefined && wordCount > options.maxWords;
  const missingClaimStructure =
    draft.text.trim().length > 0 && draft.claims.length === 0;

  return {
    valid:
      !missingClaimStructure &&
      unsupportedClaimIds.length === 0 &&
      contradictoryClaimIds.length === 0 &&
      !exceedsWordLimit,
    unsupportedClaimIds,
    contradictoryClaimIds,
    missingClaimStructure,
    exceedsWordLimit,
    wordCount,
  };
}
