import type { ProfileFact, SemanticType } from "@munshi-apply/contracts";
import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";

export type PermanentProfileTarget = Pick<
  ProfileFact,
  "key" | "category" | "protected"
>;

const permanentProfileTargets: Readonly<
  Partial<Record<SemanticType, PermanentProfileTarget>>
> = {
  PERSONAL: { key: "legal_name", category: "IDENTITY", protected: true },
  FIRST_NAME: { key: "first_name", category: "IDENTITY", protected: true },
  MIDDLE_NAME: { key: "middle_name", category: "IDENTITY", protected: true },
  LAST_NAME: { key: "last_name", category: "IDENTITY", protected: true },
  PREFERRED_NAME: {
    key: "preferred_name",
    category: "IDENTITY",
    protected: false,
  },
  HONORIFIC: { key: "honorific", category: "IDENTITY", protected: false },
  PRONOUNS: { key: "pronouns", category: "IDENTITY", protected: true },
  EMAIL: { key: "email", category: "CONTACT", protected: false },
  PHONE: { key: "phone", category: "CONTACT", protected: false },
  LINKEDIN: { key: "linkedin", category: "CONTACT", protected: false },
  GITHUB: { key: "github", category: "CONTACT", protected: false },
  PORTFOLIO: { key: "portfolio", category: "CONTACT", protected: false },
  WEBSITE: { key: "portfolio", category: "CONTACT", protected: false },
  CURRENT_LOCATION: {
    key: "current_location",
    category: "ADDRESS",
    protected: true,
  },
  STREET_ADDRESS: {
    key: "street_address",
    category: "ADDRESS",
    protected: true,
  },
  ADDRESS_LINE_2: {
    key: "address_line_2",
    category: "ADDRESS",
    protected: true,
  },
  CITY: { key: "city", category: "ADDRESS", protected: true },
  STATE_PROVINCE: { key: "state", category: "ADDRESS", protected: true },
  POSTAL_CODE: {
    key: "postal_code",
    category: "ADDRESS",
    protected: true,
  },
  COUNTRY: { key: "country", category: "ADDRESS", protected: true },
  SPONSORSHIP_CURRENT: {
    key: "current_sponsorship",
    category: "SPONSORSHIP",
    protected: true,
  },
  SPONSORSHIP_FUTURE: {
    key: "future_sponsorship",
    category: "SPONSORSHIP",
    protected: true,
  },
  IMMIGRATION_ASSISTANCE: {
    key: "immigration_assistance",
    category: "SPONSORSHIP",
    protected: true,
  },
  NOTICE_PERIOD: {
    key: "notice_period",
    category: "AVAILABILITY",
    protected: false,
  },
  RELOCATION: {
    key: "relocation_willingness",
    category: "WORK_PREFERENCE",
    protected: false,
  },
  TRAVEL: {
    key: "travel_willingness",
    category: "WORK_PREFERENCE",
    protected: false,
  },
  SECURITY_CLEARANCE: {
    key: "security_clearance",
    category: "SAVED_ANSWER",
    protected: true,
  },
  VETERAN_STATUS: {
    key: "veteran_status",
    category: "VOLUNTARY_DEMOGRAPHIC",
    protected: true,
  },
  PROTECTED_VETERAN_STATUS: {
    key: "protected_veteran_status",
    category: "VOLUNTARY_DEMOGRAPHIC",
    protected: true,
  },
  DISABILITY_STATUS: {
    key: "disability_status",
    category: "VOLUNTARY_DEMOGRAPHIC",
    protected: true,
  },
  GENDER: {
    key: "gender",
    category: "VOLUNTARY_DEMOGRAPHIC",
    protected: true,
  },
};

export function permanentProfileTarget(
  semanticType: string,
): PermanentProfileTarget | null {
  return permanentProfileTargets[semanticType as SemanticType] ?? null;
}

function comparableValue(value: ProfileFact["value"]): string {
  return Array.isArray(value) ? value.join(", ") : String(value);
}

export function promoteRememberedAnswerIntoProfile(
  profile: ProfileSnapshot,
  input: {
    semanticType: string;
    value: string;
    sensitive: boolean;
    approvedAt: string;
  },
): {
  profile: ProfileSnapshot;
  changed: boolean;
  key: string | null;
} {
  const target = permanentProfileTarget(input.semanticType);
  const value = input.value.trim();
  if (!target || !value) return { profile, changed: false, key: null };

  const existing = profile.facts.find((fact) => fact.key === target.key);
  if (
    existing &&
    comparableValue(existing.value).trim() === value &&
    existing.trustLevel !== "UNKNOWN" &&
    (!target.protected || Boolean(existing.confirmedAt))
  ) {
    return { profile, changed: false, key: target.key };
  }

  const timestamp = input.approvedAt;
  const fact: ProfileFact = {
    factId: existing?.factId ?? crypto.randomUUID(),
    key: target.key,
    value,
    category: target.category,
    trustLevel: "USER_CONFIRMED",
    source: "REMEMBERED_APPLICATION_ANSWER",
    confirmedAt: timestamp,
    updatedAt: timestamp,
    protected: target.protected || input.sensitive,
  };

  return {
    changed: true,
    key: target.key,
    profile: {
      ...profile,
      updatedAt: timestamp,
      facts: [
        ...profile.facts.filter((candidate) => candidate.key !== target.key),
        fact,
      ],
    },
  };
}
