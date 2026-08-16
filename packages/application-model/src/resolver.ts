import type {
  MasterProfile,
  ProfileFact,
  Question,
  SemanticType,
  TrustLevel,
} from "@munshi-apply/contracts";
import type {
  ProfileRecordKind,
  ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";

export type ResolutionState = "READY" | "REVIEW" | "UNRESOLVED";

export type AnswerResolution = {
  state: ResolutionState;
  value: string | null;
  sourceFactId: string | null;
  sourceKey: string | null;
  trustLevel: TrustLevel | null;
  sensitive: boolean;
  protected: boolean;
  confidence: number;
  reasons: readonly string[];
};

const semanticFactKey: Readonly<Partial<Record<SemanticType, string>>> = {
  PERSONAL: "legal_name",
  FIRST_NAME: "first_name",
  MIDDLE_NAME: "middle_name",
  LAST_NAME: "last_name",
  PREFERRED_NAME: "preferred_name",
  PRONOUNS: "pronouns",
  CONTACT: "email",
  ADDRESS: "street_address",
  STREET_ADDRESS: "street_address",
  ADDRESS_LINE_2: "address_line_2",
  CITY: "city",
  STATE_PROVINCE: "state",
  POSTAL_CODE: "postal_code",
  COUNTRY: "country",
  EMAIL: "email",
  PHONE: "phone",
  LINKEDIN: "linkedin",
  PORTFOLIO: "portfolio",
  WEBSITE: "portfolio",
  SCHOOL_NAME: "school_name",
  DEGREE: "highest_degree",
  FIELD_OF_STUDY: "field_of_study",
  GRADUATION_DATE: "graduation_date",
  GPA: "gpa",
  EMPLOYER_NAME: "current_employer",
  JOB_TITLE: "current_title",
  RELEVANT_EXPERIENCE: "employment_summary",
  WORK_AUTHORIZATION_CURRENT: "work_authorization",
  SPONSORSHIP_CURRENT: "current_sponsorship",
  SPONSORSHIP_FUTURE: "future_sponsorship",
  IMMIGRATION_ASSISTANCE: "immigration_assistance",
  SALARY_EXPECTATION: "salary_expectation",
  START_DATE: "earliest_start_date",
  NOTICE_PERIOD: "notice_period",
  RELOCATION: "relocation_willingness",
  TRAVEL: "travel_willingness",
  SKILLS: "skills",
  CERTIFICATIONS: "certifications",
  LANGUAGES: "languages",
  VETERAN_STATUS: "veteran_status",
  DISABILITY_STATUS: "disability_status",
  GENDER: "gender",
  RACE_ETHNICITY: "race_ethnicity",
  REFERRAL: "referral_source",
  PREVIOUS_EMPLOYEE: "previous_employee",
  PREVIOUS_APPLICATION: "previous_application",
};

type RecordFactMapping = {
  kind: ProfileRecordKind;
  key: string;
};

const semanticRecordFact: Readonly<
  Partial<Record<SemanticType, RecordFactMapping>>
> = {
  EDUCATION: { kind: "EDUCATION", key: "school_name" },
  SCHOOL_NAME: { kind: "EDUCATION", key: "school_name" },
  DEGREE: { kind: "EDUCATION", key: "degree" },
  FIELD_OF_STUDY: { kind: "EDUCATION", key: "field_of_study" },
  GRADUATION_DATE: { kind: "EDUCATION", key: "graduation_date" },
  GPA: { kind: "EDUCATION", key: "gpa" },
  EMPLOYMENT: { kind: "EMPLOYMENT", key: "employer_name" },
  EMPLOYER_NAME: { kind: "EMPLOYMENT", key: "employer_name" },
  JOB_TITLE: { kind: "EMPLOYMENT", key: "job_title" },
  EMPLOYMENT_DATES: { kind: "EMPLOYMENT", key: "employment_start_date" },
  EMPLOYMENT_RESPONSIBILITIES: {
    kind: "EMPLOYMENT",
    key: "responsibilities",
  },
  RELEVANT_EXPERIENCE: { kind: "EMPLOYMENT", key: "responsibilities" },
  CERTIFICATIONS: { kind: "CERTIFICATION", key: "certification_name" },
  LICENSES: { kind: "CERTIFICATION", key: "certification_name" },
  LANGUAGES: { kind: "LANGUAGE", key: "language" },
};

const trustedFactLevels = new Set<TrustLevel>([
  "VERIFIED",
  "USER_CONFIRMED",
  "DOCUMENT_CONFIRMED",
]);

const confirmedProtectedAutofillTypes = new Set<SemanticType>([
  "WORK_AUTHORIZATION_CURRENT",
  "SPONSORSHIP_CURRENT",
  "SPONSORSHIP_FUTURE",
  "IMMIGRATION_ASSISTANCE",
]);

const recruitmentEvidencePattern =
  /\b(recruit(?:er|ing|ment)?|talent acquisition|candidate sourcing|candidate screening|sourcing|interview(?:ing|s)?)\b/i;

function stringifyFactValue(value: ProfileFact["value"]): string {
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function factIsAuthoritative(fact: ProfileFact): boolean {
  return trustedFactLevels.has(fact.trustLevel);
}

function factIsExplicitlyUsable(fact: ProfileFact): boolean {
  return (
    factIsAuthoritative(fact) && (!fact.protected || Boolean(fact.confirmedAt))
  );
}

function unresolved(
  question: Question,
  sourceKey: string | null,
  reason: string,
): AnswerResolution {
  return {
    state: "UNRESOLVED",
    value: null,
    sourceFactId: null,
    sourceKey,
    trustLevel: null,
    sensitive: question.sensitive,
    protected: false,
    confidence: question.confidence,
    reasons: [reason],
  };
}

function reviewWithoutFill(
  question: Question,
  fact: ProfileFact,
  reason: string,
): AnswerResolution {
  return {
    state: "REVIEW",
    value: null,
    sourceFactId: fact.factId,
    sourceKey: fact.key,
    trustLevel: fact.trustLevel,
    sensitive: question.sensitive || fact.protected,
    protected: fact.protected,
    confidence: question.confidence,
    reasons: [reason],
  };
}

export function factKeyForSemanticType(
  semanticType: SemanticType,
): string | null {
  return semanticFactKey[semanticType] ?? null;
}

function recordFactForSemanticType(
  semanticType: SemanticType,
  profile: MasterProfile | ProfileSnapshot,
): ProfileFact | undefined {
  const mapping = semanticRecordFact[semanticType];
  if (!mapping || !("records" in profile)) return undefined;
  return [...profile.records]
    .filter((record) => record.kind === mapping.kind)
    .sort(
      (left, right) =>
        left.sortOrder - right.sortOrder ||
        left.recordId.localeCompare(right.recordId),
    )
    .map((record) => record.facts.find((fact) => fact.key === mapping.key))
    .find((fact): fact is ProfileFact => fact !== undefined);
}

function ownerDefaultReferral(question: Question): AnswerResolution | null {
  if (question.semanticType !== "REFERRAL") return null;
  return {
    state: "READY",
    value: "LinkedIn",
    sourceFactId: null,
    sourceKey: "owner_default_referral",
    trustLevel: "USER_CONFIRMED",
    sensitive: false,
    protected: false,
    confidence: Math.max(question.confidence, 0.99),
    reasons: ["Owner default referral source is LinkedIn"],
  };
}

function salaryBoolean(value: string): "Yes" | "No" | null {
  const token = value.trim().toLocaleLowerCase("en-US");
  if (
    /^(yes|true|accept|acceptable|accepted|ok|okay|willing|agree)$/.test(token)
  )
    return "Yes";
  if (
    /^(no|false|decline|unacceptable|not acceptable|not willing|disagree)$/.test(
      token,
    )
  )
    return "No";
  return null;
}

function moneyValues(value: string): number[] {
  const values: number[] = [];
  for (const match of value.matchAll(
    /\$?\s*(\d{2,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?)\s*([kK])?/g,
  )) {
    const numeric = Number(match[1]!.replaceAll(",", ""));
    if (!Number.isFinite(numeric)) continue;
    const expanded = match[2] ? numeric * 1_000 : numeric;
    if (expanded >= 10_000) values.push(expanded);
  }
  return values;
}

function resolveSalaryAcceptance(
  question: Question,
  profile: MasterProfile | ProfileSnapshot,
): AnswerResolution | null {
  if (question.semanticType !== "SALARY_EXPECTATION") return null;
  if (!/\b(accept|happy|comfortable|agree|willing)\b/i.test(question.rawText))
    return null;
  const fact = profile.facts.find(
    (candidate) => candidate.key === "salary_expectation",
  );
  if (!fact || !factIsExplicitlyUsable(fact)) return null;
  const raw = stringifyFactValue(fact.value).trim();
  const direct = salaryBoolean(raw);
  if (direct) {
    return {
      state: "READY",
      value: direct,
      sourceFactId: fact.factId,
      sourceKey: fact.key,
      trustLevel: fact.trustLevel,
      sensitive: true,
      protected: fact.protected,
      confidence: Math.min(question.confidence, 0.96),
      reasons: ["Exact owner-confirmed salary acceptance preference"],
    };
  }
  const offered = moneyValues(question.rawText)[0];
  const expected = moneyValues(raw)[0];
  if (offered && expected && offered >= expected) {
    return {
      state: "READY",
      value: "Yes",
      sourceFactId: fact.factId,
      sourceKey: fact.key,
      trustLevel: fact.trustLevel,
      sensitive: true,
      protected: fact.protected,
      confidence: Math.min(question.confidence, 0.94),
      reasons: [
        "Advertised base salary meets the owner-confirmed minimum salary preference",
      ],
    };
  }
  return null;
}

function startAvailabilityDateFromQuestion(rawText: string): number | null {
  const match = rawText.match(/\bavailable to start on\s+(.+?)(?:\?|\*|$)/i);
  if (!match?.[1]) return null;
  const timestamp = Date.parse(match[1].trim());
  return Number.isNaN(timestamp) ? null : timestamp;
}

function resolveBooleanAvailabilityDate(
  question: Question,
  profile: MasterProfile | ProfileSnapshot,
): AnswerResolution | null {
  if (question.semanticType !== "START_DATE") return null;
  const requestedDate = startAvailabilityDateFromQuestion(question.rawText);
  if (requestedDate === null) return null;

  const fact = profile.facts.find(
    (candidate) => candidate.key === "earliest_start_date",
  );
  if (!fact) {
    return unresolved(
      question,
      "earliest_start_date",
      "Profile fact earliest_start_date is not available",
    );
  }
  if (!factIsAuthoritative(fact)) {
    return reviewWithoutFill(
      question,
      fact,
      `Profile fact ${fact.key} has non-authoritative trust level ${fact.trustLevel}`,
    );
  }
  if (fact.protected && !fact.confirmedAt) {
    return reviewWithoutFill(
      question,
      fact,
      "Protected start-date fact has not been explicitly confirmed",
    );
  }

  const earliestDate = Date.parse(stringifyFactValue(fact.value).trim());
  if (Number.isNaN(earliestDate)) {
    return unresolved(
      question,
      fact.key,
      "Earliest start date is not a parseable date",
    );
  }

  return {
    state: "READY",
    value: earliestDate <= requestedDate ? "Yes" : "No",
    sourceFactId: fact.factId,
    sourceKey: fact.key,
    trustLevel: fact.trustLevel,
    sensitive: false,
    protected: fact.protected,
    confidence: Math.min(
      question.confidence,
      fact.trustLevel === "VERIFIED" ? 1 : 0.96,
    ),
    reasons: [
      "Answer derived deterministically from the explicitly saved earliest start date",
    ],
  };
}

function isFirstRecruitmentRoleQuestion(rawText: string): boolean {
  return /(?:\bfirst experience\b.{0,100}\b(?:professional )?(?:recruitment|recruiting|recruiter|talent acquisition)\b|\bfirst\b.{0,80}\bprofessional recruitment role\b)/i.test(
    rawText,
  );
}

function recruitmentEvidence(
  profile: MasterProfile | ProfileSnapshot,
): ProfileFact | undefined {
  const legacyCandidates = profile.facts.filter((fact) =>
    [
      "current_title",
      "employment_summary",
      "job_title",
      "responsibilities",
    ].includes(fact.key),
  );
  const recordCandidates =
    "records" in profile
      ? [...profile.records]
          .filter((record) => record.kind === "EMPLOYMENT")
          .sort(
            (left, right) =>
              left.sortOrder - right.sortOrder ||
              left.recordId.localeCompare(right.recordId),
          )
          .flatMap((record) =>
            record.facts.filter((fact) =>
              ["job_title", "responsibilities", "achievements"].includes(
                fact.key,
              ),
            ),
          )
      : [];

  return [...recordCandidates, ...legacyCandidates].find(
    (fact) =>
      factIsExplicitlyUsable(fact) &&
      recruitmentEvidencePattern.test(stringifyFactValue(fact.value)),
  );
}

function resolveFirstRecruitmentRole(
  question: Question,
  profile: MasterProfile | ProfileSnapshot,
): AnswerResolution | null {
  if (
    question.semanticType !== "RELEVANT_EXPERIENCE" ||
    !isFirstRecruitmentRoleQuestion(question.rawText)
  ) {
    return null;
  }

  const evidence = recruitmentEvidence(profile);
  if (!evidence) {
    return unresolved(
      question,
      "employment_history",
      "No authoritative prior recruitment-work evidence is available; MUNSHI will not assume this is the first recruitment role",
    );
  }

  return {
    state: "READY",
    value: "No",
    sourceFactId: evidence.factId,
    sourceKey: evidence.key,
    trustLevel: evidence.trustLevel,
    sensitive: false,
    protected: evidence.protected,
    confidence: Math.min(
      question.confidence,
      evidence.trustLevel === "VERIFIED" ? 1 : 0.96,
    ),
    reasons: [
      "Confirmed prior recruitment experience exists in the employment profile",
    ],
  };
}

export function resolveProfileAnswer(
  question: Question,
  profile: MasterProfile | ProfileSnapshot,
): AnswerResolution {
  const referralResolution = ownerDefaultReferral(question);
  if (referralResolution) return referralResolution;

  const salaryResolution = resolveSalaryAcceptance(question, profile);
  if (salaryResolution) return salaryResolution;

  const availabilityResolution = resolveBooleanAvailabilityDate(
    question,
    profile,
  );
  if (availabilityResolution) return availabilityResolution;

  const recruitmentResolution = resolveFirstRecruitmentRole(question, profile);
  if (recruitmentResolution) return recruitmentResolution;

  const key = factKeyForSemanticType(question.semanticType);
  const recordMapping = semanticRecordFact[question.semanticType];
  if (!key && !recordMapping) {
    return unresolved(
      question,
      null,
      "No deterministic profile fact is mapped to this question",
    );
  }

  const fact =
    recordFactForSemanticType(question.semanticType, profile) ??
    profile.facts.find((candidate) => candidate.key === key);
  const sourceKey = fact?.key ?? recordMapping?.key ?? key;
  if (!fact) {
    return unresolved(
      question,
      sourceKey,
      `Profile fact ${sourceKey} is not available`,
    );
  }

  const value = stringifyFactValue(fact.value).trim();
  if (!value) {
    return {
      state: "UNRESOLVED",
      value: null,
      sourceFactId: fact.factId,
      sourceKey: fact.key,
      trustLevel: fact.trustLevel,
      sensitive: question.sensitive || fact.protected,
      protected: fact.protected,
      confidence: question.confidence,
      reasons: [`Profile fact ${fact.key} is empty`],
    };
  }

  if (!factIsAuthoritative(fact)) {
    return {
      state: "REVIEW",
      value,
      sourceFactId: fact.factId,
      sourceKey: fact.key,
      trustLevel: fact.trustLevel,
      sensitive: question.sensitive || fact.protected,
      protected: fact.protected,
      confidence: question.confidence,
      reasons: [
        `Profile fact ${fact.key} has non-authoritative trust level ${fact.trustLevel}`,
      ],
    };
  }

  const confirmedProtectedAutofill =
    fact.protected &&
    Boolean(fact.confirmedAt) &&
    confirmedProtectedAutofillTypes.has(question.semanticType);

  const reasons: string[] = [];
  if (question.requiresReview && !confirmedProtectedAutofill) {
    reasons.push("Question policy requires review");
  }
  if (question.sensitive && !confirmedProtectedAutofill) {
    reasons.push("Question is sensitive");
  }
  if (fact.protected) reasons.push("Source fact is protected");
  if (fact.protected && !fact.confirmedAt) {
    reasons.push("Protected source fact has not been explicitly confirmed");
  }
  if (confirmedProtectedAutofill) {
    reasons.push(
      "Explicit owner confirmation permits deterministic protected-fact autofill for this authorization/sponsorship question",
    );
  }

  const requiresReview =
    (!confirmedProtectedAutofill &&
      (question.requiresReview || question.sensitive)) ||
    (fact.protected && !fact.confirmedAt);

  return {
    state: requiresReview ? "REVIEW" : "READY",
    value,
    sourceFactId: fact.factId,
    sourceKey: fact.key,
    trustLevel: fact.trustLevel,
    sensitive: question.sensitive || fact.protected,
    protected: fact.protected,
    confidence: Math.min(
      question.confidence,
      fact.trustLevel === "VERIFIED" ? 1 : 0.96,
    ),
    reasons,
  };
}
