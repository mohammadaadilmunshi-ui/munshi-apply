import type { ProfileFact } from "@munshi-apply/contracts";
import {
  parseProfileSnapshot,
  type ProfileRecord,
  type ProfileRecordKind,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";

type LegacyRecordMapping = {
  kind: ProfileRecordKind;
  primaryKey: string;
  fallbackLabel: string;
  keys: Record<string, string>;
};

const legacyMappings: readonly LegacyRecordMapping[] = [
  {
    kind: "EDUCATION",
    primaryKey: "school_name",
    fallbackLabel: "Imported education",
    keys: {
      school_name: "school_name",
      highest_degree: "degree",
      field_of_study: "field_of_study",
      graduation_date: "graduation_date",
      gpa: "gpa",
    },
  },
  {
    kind: "EMPLOYMENT",
    primaryKey: "employer_name",
    fallbackLabel: "Imported employment",
    keys: {
      current_employer: "employer_name",
      current_title: "job_title",
      employment_summary: "responsibilities",
    },
  },
  {
    kind: "PROJECT",
    primaryKey: "project_summary",
    fallbackLabel: "Imported project",
    keys: { project_summary: "project_summary" },
  },
  {
    kind: "CERTIFICATION",
    primaryKey: "certification_name",
    fallbackLabel: "Imported certification",
    keys: { certifications: "certification_name" },
  },
  {
    kind: "LANGUAGE",
    primaryKey: "language",
    fallbackLabel: "Imported language",
    keys: { languages: "language" },
  },
];

function hasValue(fact: ProfileFact): boolean {
  return Array.isArray(fact.value)
    ? fact.value.length > 0
    : String(fact.value).trim().length > 0;
}

function legacyRecord(
  snapshot: ProfileSnapshot,
  mapping: LegacyRecordMapping,
): ProfileRecord | null {
  const facts = Object.entries(mapping.keys)
    .map(([legacyKey, recordKey]) => {
      const fact = snapshot.facts.find(
        (candidate) => candidate.key === legacyKey && hasValue(candidate),
      );
      if (!fact) return null;
      return {
        ...fact,
        factId: `${fact.factId}:record:${mapping.kind.toLowerCase()}`,
        key: recordKey,
        source: `${fact.source}:LEGACY_MIGRATION`,
      };
    })
    .filter((fact): fact is ProfileFact => fact !== null);
  if (facts.length === 0) return null;
  const primary = facts.find((fact) => fact.key === mapping.primaryKey);
  const label =
    primary && typeof primary.value === "string" && primary.value.trim()
      ? primary.value.trim()
      : mapping.fallbackLabel;
  const updatedAt = facts
    .map((fact) => fact.updatedAt)
    .sort((left, right) => right.localeCompare(left))[0]!;
  return {
    recordId: `legacy-${mapping.kind.toLowerCase()}-${snapshot.profileId}`,
    kind: mapping.kind,
    label,
    facts,
    sortOrder: 0,
    createdAt: snapshot.createdAt,
    updatedAt,
  };
}

export function migrateLegacyProfileSnapshot(value: unknown): {
  snapshot: ProfileSnapshot;
  migrated: boolean;
} {
  const snapshot = parseProfileSnapshot(value);
  const records = [...snapshot.records];
  let migrated = false;
  for (const mapping of legacyMappings) {
    if (records.some((record) => record.kind === mapping.kind)) continue;
    const record = legacyRecord(snapshot, mapping);
    if (!record) continue;
    records.push(record);
    migrated = true;
  }
  if (!migrated) return { snapshot, migrated: false };
  return {
    snapshot: parseProfileSnapshot({ ...snapshot, records }),
    migrated: true,
  };
}
