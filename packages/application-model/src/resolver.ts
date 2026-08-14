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

function stringifyFactValue(value: ProfileFact["value"]): string {
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
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

export function resolveProfileAnswer(
  question: Question,
  profile: MasterProfile | ProfileSnapshot,
): AnswerResolution {
  const key = factKeyForSemanticType(question.semanticType);
  const recordMapping = semanticRecordFact[question.semanticType];
  if (!key && !recordMapping) {
    return {
      state: "UNRESOLVED",
      value: null,
      sourceFactId: null,
      sourceKey: null,
      trustLevel: null,
      sensitive: question.sensitive,
      protected: false,
      confidence: question.confidence,
      reasons: ["No deterministic profile fact is mapped to this question"],
    };
  }

  const fact =
    recordFactForSemanticType(question.semanticType, profile) ??
    profile.facts.find((candidate) => candidate.key === key);
  const sourceKey = fact?.key ?? recordMapping?.key ?? key;
  if (!fact) {
    return {
      state: "UNRESOLVED",
      value: null,
      sourceFactId: null,
      sourceKey,
      trustLevel: null,
      sensitive: question.sensitive,
      protected: false,
      confidence: question.confidence,
      reasons: [`Profile fact ${sourceKey} is not available`],
    };
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

  if (!trustedFactLevels.has(fact.trustLevel)) {
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

  const reasons: string[] = [];
  if (question.requiresReview) reasons.push("Question policy requires review");
  if (question.sensitive) reasons.push("Question is sensitive");
  if (fact.protected) reasons.push("Source fact is protected");
  if (fact.protected && !fact.confirmedAt) {
    reasons.push("Protected source fact has not been explicitly confirmed");
  }

  const requiresReview =
    question.requiresReview ||
    question.sensitive ||
    fact.protected ||
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
