import type {
  MasterProfile,
  ProfileFact,
  Question,
  TrustLevel,
} from "@munshi-apply/contracts";
import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import {
  factKeyForSemanticType,
  resolveProfileAnswer as resolveBaseProfileAnswer,
  type AnswerResolution,
} from "./resolver";

const trustedFactLevels = new Set<TrustLevel>([
  "VERIFIED",
  "USER_CONFIRMED",
  "DOCUMENT_CONFIRMED",
]);

function profileFact(
  profile: MasterProfile | ProfileSnapshot,
  key: string,
): ProfileFact | undefined {
  return profile.facts.find((fact) => fact.key === key);
}

function confirmedAndUsable(
  fact: ProfileFact | undefined,
): fact is ProfileFact {
  if (!fact || !trustedFactLevels.has(fact.trustLevel)) return false;
  if (fact.protected && !fact.confirmedAt) return false;
  const value = Array.isArray(fact.value)
    ? fact.value.join(", ")
    : String(fact.value);
  return Boolean(value.trim());
}

function factText(fact: ProfileFact): string {
  return Array.isArray(fact.value) ? fact.value.join(", ") : String(fact.value);
}

function confirmedLegalNameResolution(
  question: Question,
  profile: MasterProfile | ProfileSnapshot,
  base: AnswerResolution,
): AnswerResolution | null {
  if (question.semanticType !== "PERSONAL") return null;

  const legalName = profileFact(profile, "legal_name");
  if (
    base.sourceKey === "legal_name" &&
    base.value?.trim() &&
    confirmedAndUsable(legalName)
  ) {
    return {
      ...base,
      state: "READY",
      sensitive: true,
      protected: true,
      reasons: [
        ...base.reasons.filter(
          (reason) =>
            reason !== "Question policy requires review" &&
            reason !== "Question is sensitive",
        ),
        "Explicit owner confirmation permits deterministic autofill of the protected legal-name fact",
      ],
    };
  }

  if (base.state !== "UNRESOLVED") return null;

  const firstName = profileFact(profile, "first_name");
  const middleName = profileFact(profile, "middle_name");
  const lastName = profileFact(profile, "last_name");
  if (!confirmedAndUsable(firstName) || !confirmedAndUsable(lastName)) {
    return null;
  }
  if (
    middleName &&
    factText(middleName).trim() &&
    !confirmedAndUsable(middleName)
  ) {
    return null;
  }

  const components = [firstName, middleName, lastName]
    .filter((fact): fact is ProfileFact => confirmedAndUsable(fact))
    .map((fact) => factText(fact).trim())
    .filter(Boolean);
  const value = components.join(" ").trim();
  if (!value) return null;

  return {
    state: "READY",
    value,
    sourceFactId: firstName.factId,
    sourceKey: "first_name+middle_name+last_name",
    trustLevel: "USER_CONFIRMED",
    sensitive: true,
    protected: true,
    confidence: Math.min(question.confidence, 0.96),
    reasons: [
      "Full name composed only from explicitly usable confirmed identity facts",
    ],
  };
}

export function resolveProfileAnswer(
  question: Question,
  profile: MasterProfile | ProfileSnapshot,
): AnswerResolution {
  const base = resolveBaseProfileAnswer(question, profile);
  return confirmedLegalNameResolution(question, profile, base) ?? base;
}

export { factKeyForSemanticType };
export type { AnswerResolution, ResolutionState } from "./resolver";
