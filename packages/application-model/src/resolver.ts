import type {
  MasterProfile,
  ProfileFact,
  Question,
  SemanticType,
  TrustLevel,
} from "@munshi-apply/contracts";
import type {
  ProfileRecord,
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
  REMOTE: "preferred_work_mode",
  HYBRID: "preferred_work_mode",
  ONSITE: "preferred_work_mode",
  SKILLS: "skills",
  CERTIFICATIONS: "certifications",
  LANGUAGES: "languages",
  SECURITY_CLEARANCE: "security_clearance",
  VETERAN_STATUS: "veteran_status",
  PROTECTED_VETERAN_STATUS: "protected_veteran_status",
  DISABILITY_STATUS: "disability_status",
  GENDER: "gender",
  RACE_ETHNICITY: "race_ethnicity",
  EEO_SELF_ID: "eeo_self_id",
  REFERRAL: "referral_source",
  PREVIOUS_EMPLOYEE: "previous_employee",
  PREVIOUS_APPLICATION: "previous_application",
  CONFLICT_OF_INTEREST: "conflict_of_interest",
  NON_COMPETE: "non_compete",
  BACKGROUND_CHECK: "background_check",
  DRUG_SCREENING: "drug_screening",
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
  EDUCATION_LOCATION: { kind: "EDUCATION", key: "education_location" },
  EDUCATION_START_DATE: { kind: "EDUCATION", key: "education_start_date" },
  GRADUATION_DATE: { kind: "EDUCATION", key: "graduation_date" },
  GPA: { kind: "EDUCATION", key: "gpa" },
  EMPLOYMENT: { kind: "EMPLOYMENT", key: "employer_name" },
  EMPLOYER_NAME: { kind: "EMPLOYMENT", key: "employer_name" },
  JOB_TITLE: { kind: "EMPLOYMENT", key: "job_title" },
  EMPLOYMENT_LOCATION: { kind: "EMPLOYMENT", key: "employment_location" },
  EMPLOYMENT_START_DATE: {
    kind: "EMPLOYMENT",
    key: "employment_start_date",
  },
  EMPLOYMENT_END_DATE: { kind: "EMPLOYMENT", key: "employment_end_date" },
  EMPLOYMENT_DATES: { kind: "EMPLOYMENT", key: "employment_start_date" },
  EMPLOYMENT_TYPE: { kind: "EMPLOYMENT", key: "employment_type" },
  CURRENTLY_EMPLOYED: { kind: "EMPLOYMENT", key: "currently_employed" },
  COMPANY_INDUSTRY: { kind: "EMPLOYMENT", key: "company_industry" },
  POSITION_FUNCTION: { kind: "EMPLOYMENT", key: "position_function" },
  EMPLOYMENT_RESPONSIBILITIES: {
    kind: "EMPLOYMENT",
    key: "responsibilities",
  },
  RELEVANT_EXPERIENCE: { kind: "EMPLOYMENT", key: "responsibilities" },
  CERTIFICATIONS: { kind: "CERTIFICATION", key: "certification_name" },
  LICENSES: { kind: "CERTIFICATION", key: "certification_name" },
  CERTIFICATION_ISSUER: {
    kind: "CERTIFICATION",
    key: "issuing_organization",
  },
  CERTIFICATION_ISSUE_DATE: {
    kind: "CERTIFICATION",
    key: "certification_issue_date",
  },
  CERTIFICATION_EXPIRATION_DATE: {
    kind: "CERTIFICATION",
    key: "certification_expiration_date",
  },
  CREDENTIAL_ID: { kind: "CERTIFICATION", key: "credential_id" },
  CREDENTIAL_URL: { kind: "CERTIFICATION", key: "credential_url" },
  LANGUAGES: { kind: "LANGUAGE", key: "language" },
  LANGUAGE_PROFICIENCY: { kind: "LANGUAGE", key: "proficiency" },
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

function recordsOfKind(
  profile: MasterProfile | ProfileSnapshot,
  kind: ProfileRecordKind,
): ProfileRecord[] {
  if (!("records" in profile)) return [];
  return [...profile.records]
    .filter((record) => record.kind === kind)
    .sort(
      (left, right) =>
        left.sortOrder - right.sortOrder ||
        left.recordId.localeCompare(right.recordId),
    );
}

function recordForQuestion(
  profile: MasterProfile | ProfileSnapshot,
  kind: ProfileRecordKind,
  question: Question,
): ProfileRecord | undefined {
  const records = recordsOfKind(profile, kind);
  if (records.length === 0) return undefined;
  const requested = question.repeatIndex;
  if (
    requested !== null &&
    requested !== undefined &&
    requested >= 0 &&
    requested < records.length
  ) {
    return records[requested];
  }
  return records[0];
}

function recordMappingForQuestion(question: Question): RecordFactMapping | undefined {
  const mapping = semanticRecordFact[question.semanticType];
  if (!mapping) return undefined;
  if (
    question.semanticType === "EMPLOYMENT_DATES" &&
    /\b(end|ended|through|to)\s*(date|month|year)?\b/i.test(
      `${question.contextText ?? ""} ${question.rawText}`,
    )
  ) {
    return { kind: "EMPLOYMENT", key: "employment_end_date" };
  }
  return mapping;
}

function recordFactForQuestion(
  question: Question,
  profile: MasterProfile | ProfileSnapshot,
): ProfileFact | undefined {
  const mapping = recordMappingForQuestion(question);
  if (!mapping) return undefined;
  return recordForQuestion(profile, mapping.kind, question)?.facts.find(
    (fact) => fact.key === mapping.key,
  );
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

function derivedRecordResolution(
  question: Question,
  fact: ProfileFact,
  value: string,
  reason: string,
): AnswerResolution {
  return {
    state: "READY",
    value,
    sourceFactId: fact.factId,
    sourceKey: fact.key,
    trustLevel: fact.trustLevel,
    sensitive: question.sensitive || fact.protected,
    protected: fact.protected,
    confidence: Math.min(question.confidence, 0.93),
    reasons: [reason],
  };
}

function classifyIndustry(value: string): string | null {
  const text = value.toLocaleLowerCase("en-US");
  if (
    /\b(toyota|lexus|scion|honda|acura|ford|general motors|chevrolet|gm\b|bmw|mercedes|volkswagen|audi|hyundai|kia|nissan|infiniti|mazda|subaru|stellantis|chrysler|jeep|tesla|rivian|lucid)\b/.test(
      text,
    )
  ) {
    return "Automotive & Mobility";
  }
  if (/\b(deloitte|mckinsey|bain|bcg|boston consulting|accenture|kearney)\b/.test(text)) {
    return "Consulting";
  }
  if (/\b(jpmorgan|chase|goldman sachs|morgan stanley|bank of america|citibank|citi|wells fargo|capital one)\b/.test(text)) {
    return "Financial Services";
  }
  if (/\b(hospital|healthcare|health care|medical center|clinic)\b/.test(text)) {
    return "Healthcare";
  }
  if (/\b(microsoft|google|alphabet|amazon web services|aws\b|oracle|salesforce|adobe|cloudflare|sap\b|software|technology)\b/.test(text)) {
    return "Technology";
  }
  return null;
}

function classifyPositionFunction(value: string): string | null {
  const text = value.toLocaleLowerCase("en-US");
  if (
    /\b(human resources?|hr\b|recruit(?:er|ing|ment)?|talent acquisition|people operations?|people analytics|human capital|total rewards|compensation)\b/.test(
      text,
    )
  ) {
    return "Human Capital";
  }
  if (/\b(finance|financial|accounting|accountant|controller|audit)\b/.test(text)) {
    return "Finance/Accounting";
  }
  if (/\b(legal|lawyer|attorney|paralegal|counsel)\b/.test(text)) return "Legal";
  if (/\b(marketing|brand|communications?|public relations|\bpr\b)\b/.test(text)) {
    return "Marketing";
  }
  if (/\b(product manager|product management)\b/.test(text)) {
    return "Product Management";
  }
  if (/\b(sales|account executive|business development)\b/.test(text)) {
    return "Sales";
  }
  if (/\b(supply chain|logistics|procurement|purchasing)\b/.test(text)) {
    return "Supply Chain";
  }
  if (/\b(strategy|strategic planning)\b/.test(text)) return "Strategy";
  if (/\b(research and development|research & development|\br&d\b)\b/.test(text)) {
    return "Research & Development";
  }
  if (/\b(information technology|\bit\b|software engineer|systems engineer|developer)\b/.test(text)) {
    return "Information Technology";
  }
  if (/\b(operations?|operational)\b/.test(text)) return "Operations";
  return null;
}

function resolveDerivedEmploymentTaxonomy(
  question: Question,
  profile: MasterProfile | ProfileSnapshot,
): AnswerResolution | null {
  if (
    question.semanticType !== "COMPANY_INDUSTRY" &&
    question.semanticType !== "POSITION_FUNCTION"
  ) {
    return null;
  }
  const record = recordForQuestion(profile, "EMPLOYMENT", question);
  if (!record) return null;

  const explicitKey =
    question.semanticType === "COMPANY_INDUSTRY"
      ? "company_industry"
      : "position_function";
  if (record.facts.some((fact) => fact.key === explicitKey)) return null;

  const sourceKeys =
    question.semanticType === "COMPANY_INDUSTRY"
      ? ["employer_name"]
      : ["job_title", "responsibilities", "achievements"];
  for (const sourceKey of sourceKeys) {
    const source = record.facts.find((fact) => fact.key === sourceKey);
    if (!source || !factIsExplicitlyUsable(source)) continue;
    const raw = stringifyFactValue(source.value).trim();
    const value =
      question.semanticType === "COMPANY_INDUSTRY"
        ? classifyIndustry(raw)
        : classifyPositionFunction(raw);
    if (!value) continue;
    return derivedRecordResolution(
      question,
      source,
      value,
      question.semanticType === "COMPANY_INDUSTRY"
        ? "Industry category derived from authoritative employer identity using a high-confidence taxonomy rule"
        : "Position function derived from authoritative role evidence using a high-confidence taxonomy rule",
    );
  }
  return null;
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

  const taxonomyResolution = resolveDerivedEmploymentTaxonomy(question, profile);
  if (taxonomyResolution) return taxonomyResolution;

  const key = factKeyForSemanticType(question.semanticType);
  const recordMapping = recordMappingForQuestion(question);
  if (!key && !recordMapping) {
    return unresolved(
      question,
      null,
      "No deterministic profile fact is mapped to this question",
    );
  }

  const fact =
    recordFactForQuestion(question, profile) ??
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
