"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import Link from "next/link";
import {
  decryptLatestEntities,
  downloadEncryptedResume,
  encryptedHistoryNeedsRecovery,
  ensureWorkspaceKey,
  fetchSyncEvents,
  getWorkspaceKey,
  importWorkspaceKey,
  listEncryptedResumes,
  migrateLegacyProfileSnapshot,
  parseProfileSnapshot,
  putEncryptedEntity,
  reconcileProfileSnapshots,
  uploadEncryptedResume,
  workspaceKeyFingerprint,
  type ApplicationReview,
  type ApplicationSnapshot,
  type DecryptedEntity,
  type ProfileFact,
  type ProfileRecord,
  type ProfileRecordKind,
  type ProfileSnapshot,
  type ResumeRecord,
} from "../vault-client";
import {
  isEligibleApplicationSnapshot,
  pendingReviewCount,
} from "../application-eligibility";

type View =
  "overview" | "profile" | "resumes" | "applications" | "devices" | "security";

type WorkspaceStatus = {
  id: string;
  devices: number;
  encryptedObjects: number;
  events: number;
  conflicts: number;
};

type DeviceRecord = {
  id: string;
  platform: string;
  status: string;
  createdAt: string;
  lastSeenAt: string | null;
};

type ProfileField = {
  key: string;
  label: string;
  category: string;
  protected: boolean;
  section: string;
  inputType?: "text" | "email" | "tel" | "url" | "date";
};

// Keep this additive flat surface for legacy V1 consumers while repeatable
// education, employment, project, certification, and language data lives in
// canonical records below.
// prettier-ignore
const profileFields: readonly ProfileField[] = [
  { section: "Identity", key: "first_name", label: "First name", category: "IDENTITY", protected: true },
  { section: "Identity", key: "middle_name", label: "Middle name", category: "IDENTITY", protected: true },
  { section: "Identity", key: "last_name", label: "Last name", category: "IDENTITY", protected: true },
  { section: "Identity", key: "preferred_name", label: "Preferred name", category: "IDENTITY", protected: false },
  { section: "Identity", key: "legal_name", label: "Full legal name", category: "IDENTITY", protected: true },
  { section: "Contact", key: "email", label: "Primary email", category: "CONTACT", protected: false, inputType: "email" },
  { section: "Contact", key: "alternate_email", label: "Alternate email", category: "CONTACT", protected: false, inputType: "email" },
  { section: "Contact", key: "phone", label: "Phone", category: "CONTACT", protected: false, inputType: "tel" },
  { section: "Contact", key: "linkedin", label: "LinkedIn URL", category: "CONTACT", protected: false, inputType: "url" },
  { section: "Contact", key: "portfolio", label: "Portfolio URL", category: "CONTACT", protected: false, inputType: "url" },
  { section: "Address", key: "street_address", label: "Street address", category: "ADDRESS", protected: true },
  { section: "Address", key: "address_line_2", label: "Apartment / unit", category: "ADDRESS", protected: true },
  { section: "Address", key: "city", label: "City", category: "ADDRESS", protected: true },
  { section: "Address", key: "state", label: "State / province", category: "ADDRESS", protected: true },
  { section: "Address", key: "postal_code", label: "ZIP / postal code", category: "ADDRESS", protected: true },
  { section: "Address", key: "country", label: "Country", category: "ADDRESS", protected: true },
  { section: "Work authorization", key: "work_authorization", label: "Current work authorization", category: "WORK_AUTHORIZATION", protected: true },
  { section: "Work authorization", key: "current_sponsorship", label: "Current sponsorship requirement", category: "SPONSORSHIP", protected: true },
  { section: "Work authorization", key: "future_sponsorship", label: "Future sponsorship answer", category: "SPONSORSHIP", protected: true },
  { section: "Work authorization", key: "immigration_assistance", label: "Immigration assistance answer", category: "SPONSORSHIP", protected: true },
  { section: "Availability & mobility", key: "earliest_start_date", label: "Earliest start date", category: "AVAILABILITY", protected: false, inputType: "date" },
  { section: "Availability & mobility", key: "notice_period", label: "Notice period", category: "AVAILABILITY", protected: false },
  { section: "Availability & mobility", key: "full_time_available", label: "Full-time availability", category: "AVAILABILITY", protected: false },
  { section: "Availability & mobility", key: "preferred_work_mode", label: "Preferred work mode", category: "WORK_PREFERENCE", protected: false },
  { section: "Availability & mobility", key: "relocation_willingness", label: "Relocation willingness", category: "WORK_PREFERENCE", protected: false },
  { section: "Availability & mobility", key: "travel_willingness", label: "Travel willingness", category: "WORK_PREFERENCE", protected: false },
  { section: "Availability & mobility", key: "desired_locations", label: "Preferred locations", category: "WORK_PREFERENCE", protected: false },
  { section: "Skills", key: "skills", label: "Skills", category: "SKILL", protected: false },
  { section: "Application preferences", key: "salary_expectation", label: "Salary expectation / handling preference", category: "SAVED_ANSWER", protected: false },
  { section: "Application preferences", key: "referral_source", label: "Referral source", category: "SAVED_ANSWER", protected: false },
  { section: "Application preferences", key: "previous_employee", label: "Previous employee answer", category: "SAVED_ANSWER", protected: true },
  { section: "Application preferences", key: "previous_application", label: "Previous application answer", category: "SAVED_ANSWER", protected: true },
  { section: "Optional voluntary demographics", key: "veteran_status", label: "Veteran status", category: "VOLUNTARY_DEMOGRAPHIC", protected: true },
  { section: "Optional voluntary demographics", key: "disability_status", label: "Disability status", category: "VOLUNTARY_DEMOGRAPHIC", protected: true },
  { section: "Optional voluntary demographics", key: "gender", label: "Gender", category: "VOLUNTARY_DEMOGRAPHIC", protected: true },
  { section: "Optional voluntary demographics", key: "race_ethnicity", label: "Race / ethnicity", category: "VOLUNTARY_DEMOGRAPHIC", protected: true },
];

const profileSections = Array.from(
  new Set(profileFields.map((field) => field.section)),
);

type RecordField = Omit<ProfileField, "section"> & { multiline?: boolean };
type RecordDefinition = {
  kind: ProfileRecordKind;
  heading: string;
  addLabel: string;
  fallbackLabel: string;
  primaryKey: string;
  fields: readonly RecordField[];
};

// prettier-ignore
const recordDefinitions: readonly RecordDefinition[] = [
  { kind: "EDUCATION", heading: "Education", addLabel: "Add education", fallbackLabel: "New education", primaryKey: "school_name", fields: [
    { key: "school_name", label: "School / university", category: "EDUCATION", protected: true },
    { key: "degree", label: "Degree", category: "EDUCATION", protected: true },
    { key: "field_of_study", label: "Field of study", category: "EDUCATION", protected: true },
    { key: "education_location", label: "Location", category: "EDUCATION", protected: false },
    { key: "graduation_date", label: "Graduation date", category: "EDUCATION", protected: true, inputType: "date" },
    { key: "gpa", label: "GPA (optional)", category: "EDUCATION", protected: true },
  ] },
  { kind: "EMPLOYMENT", heading: "Employment", addLabel: "Add employment", fallbackLabel: "New employment", primaryKey: "employer_name", fields: [
    { key: "employer_name", label: "Employer", category: "EMPLOYMENT", protected: true },
    { key: "job_title", label: "Job title", category: "EMPLOYMENT", protected: true },
    { key: "employment_location", label: "Location", category: "EMPLOYMENT", protected: false },
    { key: "employment_start_date", label: "Start date", category: "EMPLOYMENT", protected: true, inputType: "date" },
    { key: "employment_end_date", label: "End date", category: "EMPLOYMENT", protected: true, inputType: "date" },
    { key: "responsibilities", label: "Responsibilities", category: "EMPLOYMENT", protected: false, multiline: true },
    { key: "achievements", label: "Verified achievements", category: "EMPLOYMENT", protected: false, multiline: true },
  ] },
  { kind: "PROJECT", heading: "Projects", addLabel: "Add project", fallbackLabel: "New project", primaryKey: "project_name", fields: [
    { key: "project_name", label: "Project name", category: "PROJECT", protected: false },
    { key: "project_role", label: "Role", category: "PROJECT", protected: false },
    { key: "project_url", label: "Project URL", category: "PROJECT", protected: false, inputType: "url" },
    { key: "project_summary", label: "Summary", category: "PROJECT", protected: false, multiline: true },
    { key: "project_technologies", label: "Skills / tools", category: "PROJECT", protected: false },
  ] },
  { kind: "CERTIFICATION", heading: "Certifications", addLabel: "Add certification", fallbackLabel: "New certification", primaryKey: "certification_name", fields: [
    { key: "certification_name", label: "Certification", category: "CERTIFICATION", protected: true },
    { key: "issuing_organization", label: "Issuing organization", category: "CERTIFICATION", protected: true },
    { key: "certification_issue_date", label: "Issue date", category: "CERTIFICATION", protected: true, inputType: "date" },
    { key: "certification_expiration_date", label: "Expiration date", category: "CERTIFICATION", protected: true, inputType: "date" },
    { key: "credential_id", label: "Credential ID", category: "CERTIFICATION", protected: true },
    { key: "credential_url", label: "Credential URL", category: "CERTIFICATION", protected: false, inputType: "url" },
  ] },
  { kind: "LANGUAGE", heading: "Languages", addLabel: "Add language", fallbackLabel: "New language", primaryKey: "language", fields: [
    { key: "language", label: "Language", category: "LANGUAGE", protected: false },
    { key: "proficiency", label: "Proficiency", category: "LANGUAGE", protected: false },
  ] },
];

const semanticFactKey: Record<string, string> = {
  PERSONAL: "legal_name",
  EMAIL: "email",
  PHONE: "phone",
  LINKEDIN: "linkedin",
  PORTFOLIO: "portfolio",
  WEBSITE: "portfolio",
  WORK_AUTHORIZATION_CURRENT: "work_authorization",
  SPONSORSHIP_CURRENT: "current_sponsorship",
  SPONSORSHIP_FUTURE: "future_sponsorship",
};

const recordSemanticFact: Record<
  string,
  { kind: ProfileRecordKind; key: string }
> = {
  SCHOOL_NAME: { kind: "EDUCATION", key: "school_name" },
  DEGREE: { kind: "EDUCATION", key: "degree" },
  FIELD_OF_STUDY: { kind: "EDUCATION", key: "field_of_study" },
  GRADUATION_DATE: { kind: "EDUCATION", key: "graduation_date" },
  GPA: { kind: "EDUCATION", key: "gpa" },
  EMPLOYER_NAME: { kind: "EMPLOYMENT", key: "employer_name" },
  JOB_TITLE: { kind: "EMPLOYMENT", key: "job_title" },
  EMPLOYMENT_RESPONSIBILITIES: {
    kind: "EMPLOYMENT",
    key: "responsibilities",
  },
  RELEVANT_EXPERIENCE: { kind: "EMPLOYMENT", key: "responsibilities" },
  CERTIFICATIONS: { kind: "CERTIFICATION", key: "certification_name" },
  LANGUAGES: { kind: "LANGUAGE", key: "language" },
};

function emptyProfile(ownerName: string): ProfileSnapshot {
  const now = new Date().toISOString();
  return {
    profileId: "profile-master",
    displayName: ownerName,
    facts: [],
    records: [],
    recordTombstones: [],
    createdAt: now,
    updatedAt: now,
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

function stringValue(value: ProfileFact["value"] | undefined): string {
  if (Array.isArray(value)) return value.join(", ");
  return value == null ? "" : String(value);
}

function valueOf(profile: ProfileSnapshot, key: string): string {
  return stringValue(profile.facts.find((fact) => fact.key === key)?.value);
}

function recordValue(record: ProfileRecord, key: string): string {
  return stringValue(record.facts.find((fact) => fact.key === key)?.value);
}

function protectedRecordDraftKey(recordId: string, key: string): string {
  return `record:${recordId}:${key}`;
}

function suggestedValue(
  profile: ProfileSnapshot,
  semanticType: string,
): string {
  const mapping = recordSemanticFact[semanticType];
  if (mapping) {
    const fact = [...profile.records]
      .filter((record) => record.kind === mapping.kind)
      .sort(
        (left, right) =>
          left.sortOrder - right.sortOrder ||
          left.recordId.localeCompare(right.recordId),
      )
      .map((record) =>
        record.facts.find((candidate) => candidate.key === mapping.key),
      )
      .find((candidate) => candidate !== undefined);
    if (fact) return stringValue(fact.value);
  }
  const factKey = semanticFactKey[semanticType];
  return factKey ? valueOf(profile, factKey) : "";
}

export function MobileWorkspace({ ownerName }: { ownerName: string }) {
  const [view, setView] = useState<View>("overview");
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [entities, setEntities] = useState<Map<string, DecryptedEntity>>(
    new Map(),
  );
  const [profile, setProfile] = useState<ProfileSnapshot>(() =>
    emptyProfile(ownerName),
  );
  const [profileVersion, setProfileVersion] = useState(0);
  const profileVersionRef = useRef(0);
  const profileRevision = useRef(0);
  const profileDirtyRef = useRef(false);
  const profileSaveInFlight = useRef(false);
  const retryTimer = useRef<number | null>(null);
  const conflictRemote = useRef<{
    snapshot: ProfileSnapshot;
    version: number;
  } | null>(null);
  const [profileDirty, setProfileDirty] = useState(false);
  const [retryTick, setRetryTick] = useState(0);
  const [protectedDrafts, setProtectedDrafts] = useState<
    Record<string, string>
  >({});
  const [protectedConflicts, setProtectedConflicts] = useState<string[]>([]);
  const [resumes, setResumes] = useState<ResumeRecord[]>([]);
  const [applications, setApplications] = useState<ApplicationSnapshot[]>([]);
  const [devices, setDevices] = useState<DeviceRecord[]>([]);
  const [workspace, setWorkspace] = useState<WorkspaceStatus | null>(null);
  const [selectedApplication, setSelectedApplication] =
    useState<ApplicationSnapshot | null>(null);
  const [reviewAnswers, setReviewAnswers] = useState<
    ApplicationReview["answers"]
  >([]);
  const [reviewResumeId, setReviewResumeId] = useState("");
  const [recoveryInput, setRecoveryInput] = useState("");
  const [showRecovery, setShowRecovery] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Opening encrypted workspace…");
  const [vaultFingerprint, setVaultFingerprint] = useState<string | null>(null);
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);

  const loadWorkspace = useCallback(async (quiet = false) => {
    if (!quiet) setStatus("Synchronizing encrypted workspace…");
    const existingKey = await getWorkspaceKey();
    const [workspaceResponse, devicesResponse, sync] = await Promise.all([
      fetch("/api/workspace", { headers: { accept: "application/json" } }),
      fetch("/api/devices", { headers: { accept: "application/json" } }),
      fetchSyncEvents(0),
    ]);
    const workspacePayload = (await workspaceResponse.json()) as {
      workspace?: WorkspaceStatus;
      error?: string;
    };
    const devicesPayload = (await devicesResponse.json()) as {
      devices?: DeviceRecord[];
      error?: string;
    };
    if (!workspaceResponse.ok || !workspacePayload.workspace) {
      throw new Error(
        workspacePayload.error ?? "Workspace status is unavailable.",
      );
    }
    if (!devicesResponse.ok || !devicesPayload.devices) {
      throw new Error(devicesPayload.error ?? "Device list is unavailable.");
    }
    if (sync.workspaceId && sync.workspaceId !== workspacePayload.workspace.id) {
      throw new Error(
        "Workspace identity mismatch. Do not save until the Site and Edge pairing are reconciled.",
      );
    }

    setWorkspace(workspacePayload.workspace);
    setDevices(devicesPayload.devices);

    if (
      encryptedHistoryNeedsRecovery({
        hasLocalKey: Boolean(existingKey),
        eventCount: sync.events.length,
        encryptedObjectCount: workspacePayload.workspace.encryptedObjects,
      })
    ) {
      setRawKey(null);
      setVaultFingerprint(null);
      setView("security");
      throw new Error(
        "Existing encrypted workspace detected. Restore the recovery key used by your paired Edge installation; MUNSHI will not create a replacement key.",
      );
    }

    const key = existingKey ?? (await ensureWorkspaceKey());
    const fingerprint = await workspaceKeyFingerprint(key);
    let nextEntities: Map<string, DecryptedEntity>;
    try {
      nextEntities = await decryptLatestEntities(key, sync.events);
    } catch {
      setRawKey(key);
      setVaultFingerprint(fingerprint);
      setView("security");
      throw new Error(
        `Encrypted history cannot be opened with vault ${fingerprint}. Restore the recovery key used by the paired Edge installation.`,
      );
    }
    const resumeRecords = await listEncryptedResumes(key);
    const cloudProfile = nextEntities.get("PROFILE.V1:profile-master") as
      | DecryptedEntity<unknown>
      | undefined;
    const snapshots = Array.from(nextEntities.entries())
      .filter(([entityKey]) => entityKey.startsWith("APPLICATION.V1:"))
      .map(([, entity]) => entity.value as ApplicationSnapshot)
      .filter((application) =>
        isEligibleApplicationSnapshot(application, window.location.origin),
      )
      .sort((left, right) => right.observedAt.localeCompare(left.observedAt));

    setRawKey(key);
    setVaultFingerprint(fingerprint);
    setEntities(nextEntities);
    setResumes(resumeRecords);
    setApplications(snapshots);
    setLastSyncAt(new Date().toISOString());
    if (cloudProfile && !profileDirtyRef.current) {
      const migrated = migrateLegacyProfileSnapshot(cloudProfile.value);
      setProfile(migrated.snapshot);
      setProfileVersion(cloudProfile.version);
      profileVersionRef.current = cloudProfile.version;
      profileRevision.current += 1;
      profileDirtyRef.current = migrated.migrated;
      setProfileDirty(migrated.migrated);
      setProtectedDrafts({});
      setRetryTick(0);
      setStatus(
        migrated.migrated
          ? "Legacy profile upgraded; encrypted synchronization pending"
          : "Encrypted workspace synchronized",
      );
    } else if (!cloudProfile && !profileDirtyRef.current) {
      setProfileVersion(0);
      profileVersionRef.current = 0;
      setStatus("Encrypted workspace synchronized");
    } else if (!quiet) {
      setStatus(
        "Workspace refreshed; local profile edits are still waiting to synchronize",
      );
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadWorkspace().catch((error: unknown) => {
        setStatus(
          error instanceof Error ? error.message : "Workspace unavailable",
        );
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadWorkspace]);

  useEffect(
    () => () => {
      if (retryTimer.current !== null) window.clearTimeout(retryTimer.current);
    },
    [],
  );

  useEffect(() => {
    if (
      !rawKey ||
      profileDirty ||
      Object.keys(protectedDrafts).length > 0 ||
      protectedConflicts.length > 0
    ) {
      return;
    }
    let cancelled = false;
    const pull = () => {
      if (
        cancelled ||
        document.visibilityState !== "visible" ||
        profileSaveInFlight.current
      ) {
        return;
      }
      void loadWorkspace(true).catch((error: unknown) => {
        setStatus(
          error instanceof Error ? error.message : "Workspace synchronization failed",
        );
      });
    };
    const interval = window.setInterval(pull, 15_000);
    const onFocus = () => pull();
    const onVisibility = () => {
      if (document.visibilityState === "visible") pull();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [
    loadWorkspace,
    profileDirty,
    protectedConflicts.length,
    protectedDrafts,
    rawKey,
  ]);

  useEffect(() => {
    if (!rawKey || !profileDirty || protectedConflicts.length > 0) {
      return;
    }
    const revision = profileRevision.current;
    const snapshot = parseProfileSnapshot(profile);
    const timer = window.setTimeout(
      () => {
        if (profileSaveInFlight.current) return;
        profileSaveInFlight.current = true;
        setStatus("Encrypting and synchronizing profile…");
        void (async () => {
          try {
            const version = await putEncryptedEntity({
              rawKey,
              entityType: "PROFILE.V1",
              entityId: "profile-master",
              baseVersion: profileVersionRef.current,
              value: snapshot,
            });
            profileVersionRef.current = version;
            setProfileVersion(version);
            if (profileRevision.current === revision) {
              profileDirtyRef.current = false;
              setProfileDirty(false);
              setRetryTick(0);
              setLastSyncAt(new Date().toISOString());
              setStatus("Profile encrypted and synchronized");
            }
          } catch (error) {
            const message =
              error instanceof Error ? error.message : "Profile save failed";
            if (message.includes("changed on another device")) {
              try {
                const sync = await fetchSyncEvents(0);
                const nextEntities = await decryptLatestEntities(
                  rawKey,
                  sync.events,
                );
                setEntities(nextEntities);
                const remoteEntity = nextEntities.get(
                  "PROFILE.V1:profile-master",
                );
                if (!remoteEntity) throw error;
                const remote = migrateLegacyProfileSnapshot(
                  remoteEntity.value,
                ).snapshot;
                try {
                  const reconciled = reconcileProfileSnapshots(
                    snapshot,
                    remote,
                  );
                  profileVersionRef.current = remoteEntity.version;
                  setProfileVersion(remoteEntity.version);
                  setProfile(
                    parseProfileSnapshot({
                      ...reconciled,
                      updatedAt: new Date().toISOString(),
                    }),
                  );
                  profileRevision.current += 1;
                  profileDirtyRef.current = true;
                  setProfileDirty(true);
                  setRetryTick((value) => value + 1);
                  setStatus(
                    "Concurrent profile changes were merged; synchronizing the result…",
                  );
                } catch (mergeError) {
                  if (
                    mergeError &&
                    typeof mergeError === "object" &&
                    "keys" in mergeError &&
                    Array.isArray(mergeError.keys)
                  ) {
                    conflictRemote.current = {
                      snapshot: remote,
                      version: remoteEntity.version,
                    };
                    setProtectedConflicts(
                      mergeError.keys.filter(
                        (key): key is string => typeof key === "string",
                      ),
                    );
                    setStatus(
                      "Protected facts changed on both devices; your confirmation is required",
                    );
                  } else {
                    throw mergeError;
                  }
                }
              } catch (refreshError) {
                setStatus(
                  refreshError instanceof Error
                    ? refreshError.message
                    : "Profile conflict refresh failed",
                );
              }
            } else {
              setStatus(message);
              retryTimer.current = window.setTimeout(
                () => setRetryTick((value) => value + 1),
                5_000,
              );
            }
          } finally {
            profileSaveInFlight.current = false;
            if (
              profileDirtyRef.current &&
              profileRevision.current !== revision &&
              protectedConflicts.length === 0
            ) {
              setRetryTick((value) => value + 1);
            }
          }
        })();
      },
      retryTick === 0 ? 800 : 0,
    );
    return () => window.clearTimeout(timer);
  }, [profile, profileDirty, protectedConflicts, rawKey, retryTick]);

  const openReviews = useMemo(
    () =>
      applications.reduce((total, application) => {
        const prior = entities.get(
          `APPLICATION.REVIEW.V1:review-${application.pageId}`,
        ) as DecryptedEntity<ApplicationReview> | undefined;
        return total + pendingReviewCount(application, prior?.value);
      }, 0),
    [applications, entities],
  );

  function markProfileDirty(): void {
    profileRevision.current += 1;
    profileDirtyRef.current = true;
    setProfileDirty(true);
    setRetryTick(0);
  }

  function updateFact(
    definition: ProfileField,
    value: string,
    confirmed: boolean,
  ) {
    const now = new Date().toISOString();
    setProfile((current) => {
      const existing = current.facts.find(
        (fact) => fact.key === definition.key,
      );
      const next: ProfileFact = {
        factId: existing?.factId ?? `fact-${crypto.randomUUID()}`,
        key: definition.key,
        value,
        category: definition.category,
        trustLevel: value && confirmed ? "USER_CONFIRMED" : "UNKNOWN",
        source: "MOBILE_WORKSPACE",
        confirmedAt: value && confirmed ? now : null,
        updatedAt: now,
        protected: definition.protected,
      };
      return {
        ...current,
        updatedAt: now,
        facts: [
          ...current.facts.filter((fact) => fact.key !== definition.key),
          next,
        ],
      };
    });
    if (!definition.protected || confirmed) markProfileDirty();
  }

  function confirmProtectedFact(definition: ProfileField): void {
    const draftKey = `profile:${definition.key}`;
    if (!(draftKey in protectedDrafts)) return;
    updateFact(definition, protectedDrafts[draftKey] ?? "", true);
    setProtectedDrafts((current) => {
      const next = { ...current };
      delete next[draftKey];
      return next;
    });
  }

  function addRecord(definition: RecordDefinition): void {
    const now = new Date().toISOString();
    const recordId = `record-${crypto.randomUUID()}`;
    setProfile((current) => ({
      ...current,
      updatedAt: now,
      records: [
        ...current.records,
        {
          recordId,
          kind: definition.kind,
          label: definition.fallbackLabel,
          facts: [],
          sortOrder: current.records.filter(
            (record) => record.kind === definition.kind,
          ).length,
          createdAt: now,
          updatedAt: now,
        },
      ],
      recordTombstones: current.recordTombstones.filter(
        (tombstone) => tombstone.recordId !== recordId,
      ),
    }));
    markProfileDirty();
  }

  function updateRecordFact(
    recordId: string,
    definition: RecordField,
    value: string,
    confirmed: boolean,
  ): void {
    const now = new Date().toISOString();
    setProfile((current) => ({
      ...current,
      updatedAt: now,
      records: current.records.map((record) => {
        if (record.recordId !== recordId) return record;
        const existing = record.facts.find(
          (fact) => fact.key === definition.key,
        );
        const fact: ProfileFact = {
          factId: existing?.factId ?? `fact-${crypto.randomUUID()}`,
          key: definition.key,
          value,
          category: definition.category,
          trustLevel: value && confirmed ? "USER_CONFIRMED" : "UNKNOWN",
          source: "MOBILE_WORKSPACE_RECORD",
          confirmedAt: value && confirmed ? now : null,
          updatedAt: now,
          protected: definition.protected,
        };
        const recordDefinition = recordDefinitions.find(
          (candidate) => candidate.kind === record.kind,
        );
        return {
          ...record,
          label:
            definition.key === recordDefinition?.primaryKey && value.trim()
              ? value.trim()
              : record.label,
          facts: [
            ...record.facts.filter(
              (candidate) => candidate.key !== definition.key,
            ),
            fact,
          ],
          updatedAt: now,
        };
      }),
    }));
    if (!definition.protected || confirmed) markProfileDirty();
  }

  function confirmProtectedRecordFact(
    recordId: string,
    definition: RecordField,
  ): void {
    const draftKey = protectedRecordDraftKey(recordId, definition.key);
    if (!(draftKey in protectedDrafts)) return;
    updateRecordFact(
      recordId,
      definition,
      protectedDrafts[draftKey] ?? "",
      true,
    );
    setProtectedDrafts((current) => {
      const next = { ...current };
      delete next[draftKey];
      return next;
    });
  }

  function removeRecord(record: ProfileRecord): void {
    if (
      !window.confirm(
        `Remove ${record.label}? This deletion will synchronize across devices.`,
      )
    ) {
      return;
    }
    const now = new Date().toISOString();
    setProfile((current) => ({
      ...current,
      updatedAt: now,
      records: current.records.filter(
        (candidate) => candidate.recordId !== record.recordId,
      ),
      recordTombstones: [
        ...current.recordTombstones.filter(
          (tombstone) => tombstone.recordId !== record.recordId,
        ),
        {
          recordId: record.recordId,
          kind: record.kind,
          deletedAt: now,
          confirmed: true,
        },
      ],
    }));
    setProtectedDrafts((current) =>
      Object.fromEntries(
        Object.entries(current).filter(
          ([key]) => !key.startsWith(`record:${record.recordId}:`),
        ),
      ),
    );
    markProfileDirty();
  }

  function moveRecord(record: ProfileRecord, direction: -1 | 1): void {
    const ordered = profile.records
      .filter((candidate) => candidate.kind === record.kind)
      .sort(
        (left, right) =>
          left.sortOrder - right.sortOrder ||
          left.recordId.localeCompare(right.recordId),
      );
    const index = ordered.findIndex(
      (candidate) => candidate.recordId === record.recordId,
    );
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ordered.length) return;
    [ordered[index], ordered[target]] = [ordered[target]!, ordered[index]!];
    const order = new Map(
      ordered.map((candidate, sortOrder) => [candidate.recordId, sortOrder]),
    );
    const now = new Date().toISOString();
    setProfile((current) => ({
      ...current,
      updatedAt: now,
      records: current.records.map((candidate) =>
        candidate.kind === record.kind
          ? {
              ...candidate,
              sortOrder: order.get(candidate.recordId) ?? candidate.sortOrder,
              updatedAt: now,
            }
          : candidate,
      ),
    }));
    markProfileDirty();
  }

  function resolveProtectedProfileConflict(winner: "local" | "remote"): void {
    const remote = conflictRemote.current;
    if (!remote) return;
    const reconciled = reconcileProfileSnapshots(
      profile,
      remote.snapshot,
      winner,
    );
    const updated = parseProfileSnapshot({
      ...reconciled,
      updatedAt: new Date().toISOString(),
    });
    profileVersionRef.current = remote.version;
    setProfileVersion(remote.version);
    setProfile(updated);
    setProtectedConflicts([]);
    conflictRemote.current = null;
    profileRevision.current += 1;
    profileDirtyRef.current = true;
    setProfileDirty(true);
    setRetryTick((value) => value + 1);
    setStatus("Conflict choice confirmed; synchronizing the merged profile…");
  }

  function syncProfileNow(): void {
    if (protectedConflicts.length > 0) {
      setStatus("Resolve the protected fact conflict before synchronizing.");
      return;
    }
    if (profileDirtyRef.current) {
      setRetryTick((value) => value + 1);
      return;
    }
    void loadWorkspace().catch((error: unknown) => {
      setStatus(
        error instanceof Error ? error.message : "Workspace unavailable",
      );
    });
  }

  async function addResume(file: File | null) {
    if (!rawKey || !file) return;
    setBusy(true);
    try {
      const record = await uploadEncryptedResume(rawKey, file);
      await putEncryptedEntity({
        rawKey,
        entityType: "RESUME.V1",
        entityId: record.resumeId,
        baseVersion: 0,
        value: record,
      });
      setStatus(`${record.name} encrypted and synchronized`);
      await loadWorkspace();
    } catch (error) {
      setStatus(
        error instanceof Error ? error.message : "Résumé upload failed",
      );
    } finally {
      setBusy(false);
    }
  }

  function beginReview(application: ApplicationSnapshot) {
    const previous = entities.get(
      `APPLICATION.REVIEW.V1:review-${application.pageId}`,
    ) as DecryptedEntity<ApplicationReview> | undefined;
    const answers = application.questions.map((question) => {
      const prior = previous?.value.answers.find(
        (answer) => answer.questionId === question.questionId,
      );
      const suggested = suggestedValue(profile, question.semanticType);
      return (
        prior ?? {
          questionId: question.questionId,
          controlId: question.controlId,
          value: suggested,
          approved: Boolean(suggested) && !question.sensitive,
          sensitive: question.sensitive,
        }
      );
    });
    setSelectedApplication(application);
    setReviewAnswers(answers);
    setReviewResumeId(
      previous?.value.resumeId &&
        resumes.some((resume) => resume.resumeId === previous.value.resumeId)
        ? previous.value.resumeId
        : (resumes[0]?.resumeId ?? ""),
    );
  }

  async function saveApplicationReview() {
    if (!rawKey || !selectedApplication) return;
    const reviewId = `review-${selectedApplication.pageId}`;
    const existing = entities.get(`APPLICATION.REVIEW.V1:${reviewId}`);
    const review: ApplicationReview = {
      reviewId,
      pageId: selectedApplication.pageId,
      resumeId: reviewResumeId || null,
      approvedAt: new Date().toISOString(),
      answers: reviewAnswers,
    };
    setBusy(true);
    try {
      await putEncryptedEntity({
        rawKey,
        entityType: "APPLICATION.REVIEW.V1",
        entityId: reviewId,
        baseVersion: existing?.version ?? 0,
        value: review,
      });
      setSelectedApplication(null);
      setStatus(
        "Approved answers synchronized to the paired Edge installation",
      );
      await loadWorkspace();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Review save failed");
    } finally {
      setBusy(false);
    }
  }

  async function revokeDevice(deviceId: string) {
    if (
      !window.confirm(
        "Revoke this Edge installation? It will lose cloud access.",
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(
        `/api/devices/${encodeURIComponent(deviceId)}`,
        {
          method: "DELETE",
        },
      );
      const payload = (await response.json()) as { error?: string };
      if (!response.ok)
        throw new Error(payload.error ?? "Device revocation failed.");
      setStatus("Device access revoked");
      await loadWorkspace();
    } catch (error) {
      setStatus(
        error instanceof Error ? error.message : "Device revocation failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function restoreRecoveryKey() {
    setBusy(true);
    try {
      await importWorkspaceKey(recoveryInput);
      setRecoveryInput("");
      setStatus("Recovery key imported; validating encrypted records…");
      await loadWorkspace();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Recovery failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="workspace-shell">
      <header className="workspace-topbar">
        <Link href="/" className="brand-lockup" aria-label="MUNSHI Apply home">
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          <span>
            <strong>MUNSHI Apply</strong>
            <small>Encrypted owner workspace</small>
          </span>
        </Link>
        <button
          type="button"
          className="sync-button"
          disabled={busy}
          onClick={syncProfileNow}
        >
          {profileDirty ? "Sync profile" : "Sync"}
        </button>
      </header>

      <div className="workspace-layout">
        <nav className="workspace-navigation" aria-label="Workspace sections">
          {(
            [
              ["overview", "Overview"],
              ["profile", "Profile"],
              ["resumes", "Résumés"],
              ["applications", "Applications"],
              ["devices", "Devices"],
              ["security", "Recovery"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={view === key ? "active" : ""}
              onClick={() => setView(key)}
            >
              {label}
            </button>
          ))}
        </nav>

        <section className="workspace-content" aria-live="polite">
          <div className="workspace-heading">
            <div>
              <p className="eyebrow">Private workspace</p>
              <h1>{view === "overview" ? `Welcome, ${ownerName}` : view}</h1>
            </div>
            <span className="vault-status">
              <i aria-hidden="true" />
              {status}
            </span>
          </div>

          {view === "overview" && (
            <>
              <div className="workspace-stat-grid">
                <article>
                  <strong>{workspace?.devices ?? "—"}</strong>
                  <span>paired devices</span>
                </article>
                <article>
                  <strong>
                    {profile.facts.filter((fact) => fact.value).length +
                      profile.records
                        .flatMap((record) => record.facts)
                        .filter((fact) => fact.value).length}
                  </strong>
                  <span>confirmed facts</span>
                </article>
                <article>
                  <strong>{resumes.length}</strong>
                  <span>encrypted résumés</span>
                </article>
                <article>
                  <strong>{openReviews}</strong>
                  <span>answers to review</span>
                </article>
              </div>
              <div className="workspace-card action-card">
                <div>
                  <p className="eyebrow">Continue securely</p>
                  <h2>
                    {applications[0]?.title ??
                      "Open an application on desktop Edge"}
                  </h2>
                  <p>
                    Profile facts, résumé files, and approved answers are
                    encrypted before leaving your device.
                  </p>
                </div>
                <button
                  className="button primary"
                  type="button"
                  onClick={() => setView("applications")}
                >
                  Review applications
                </button>
              </div>
              <div className="boundary-card">
                <strong>Final submission stays manual</strong>
                <span>
                  MUNSHI can prepare and fill approved fields on desktop Edge.
                  It never presses an employer’s final submit button.
                </span>
              </div>
            </>
          )}

          {view === "profile" && (
            <div className="workspace-card">
              <div className="profile-heading">
                <div>
                  <h2>Verified application profile</h2>
                  <span>
                    Cloud version {profileVersion} ·{" "}
                    {profileDirty ? "changes pending" : "synchronized"}
                  </span>
                  <span>
                    Workspace {workspace?.id.slice(0, 8) ?? "—"} · vault{" "}
                    {vaultFingerprint ?? "locked"} · last sync{" "}
                    {lastSyncAt ? new Date(lastSyncAt).toLocaleTimeString() : "never"}
                  </span>
                </div>
                <button
                  className="button secondary compact-button"
                  disabled={!rawKey || protectedConflicts.length > 0}
                  type="button"
                  onClick={syncProfileNow}
                >
                  Sync now
                </button>
              </div>
              <p>
                Protected facts require your explicit confirmation and remain
                local drafts until you leave the field. Confirmed changes save
                and synchronize automatically.
              </p>
              {protectedConflicts.length > 0 && (
                <div className="profile-conflict" role="alert">
                  <strong>Protected facts changed on two devices</strong>
                  <p>
                    Choose which device wins for these protected fields. All
                    non-conflicting changes will still be merged:{" "}
                    {protectedConflicts.join(", ")}.
                  </p>
                  <div>
                    <button
                      className="button primary"
                      type="button"
                      onClick={() => resolveProtectedProfileConflict("local")}
                    >
                      Keep this device
                    </button>
                    <button
                      className="button secondary"
                      type="button"
                      onClick={() => resolveProtectedProfileConflict("remote")}
                    >
                      Use other device
                    </button>
                  </div>
                </div>
              )}
              {profileSections.map((sectionName) => (
                <section className="profile-section" key={sectionName}>
                  <h3>{sectionName}</h3>
                  {sectionName === "Optional voluntary demographics" && (
                    <p>
                      Optional. MUNSHI never infers these answers and never uses
                      an unconfirmed value.
                    </p>
                  )}
                  <div className="vault-form">
                    {profileFields
                      .filter((field) => field.section === sectionName)
                      .map((field) => {
                        const draftKey = `profile:${field.key}`;
                        return (
                          <label key={field.key}>
                            <span>
                              {field.label}
                              {field.protected ? " · protected" : ""}
                            </span>
                            <input
                              type={field.inputType ?? "text"}
                              value={
                                field.protected
                                  ? (protectedDrafts[draftKey] ??
                                    valueOf(profile, field.key))
                                  : valueOf(profile, field.key)
                              }
                              onChange={(event) => {
                                if (field.protected) {
                                  setProtectedDrafts((current) => ({
                                    ...current,
                                    [draftKey]: event.target.value,
                                  }));
                                  setStatus(
                                    "Protected edit waiting for confirmation",
                                  );
                                } else {
                                  updateFact(field, event.target.value, true);
                                }
                              }}
                              onBlur={() =>
                                field.protected && confirmProtectedFact(field)
                              }
                            />
                          </label>
                        );
                      })}
                  </div>
                </section>
              ))}
              <section className="repeatable-profile">
                <div className="repeatable-intro">
                  <h3>Experience and qualifications</h3>
                  <p>
                    Add every relevant record. Order controls which record is
                    used first when an application asks for one item.
                  </p>
                </div>
                {recordDefinitions.map((definition) => {
                  const records = profile.records
                    .filter((record) => record.kind === definition.kind)
                    .sort(
                      (left, right) =>
                        left.sortOrder - right.sortOrder ||
                        left.recordId.localeCompare(right.recordId),
                    );
                  return (
                    <div
                      className="profile-record-section"
                      key={definition.kind}
                    >
                      <div className="profile-record-section-heading">
                        <div>
                          <h3>{definition.heading}</h3>
                          <span>
                            {records.length}{" "}
                            {records.length === 1 ? "record" : "records"}
                          </span>
                        </div>
                        <button
                          className="button secondary compact-button"
                          type="button"
                          onClick={() => addRecord(definition)}
                        >
                          {definition.addLabel}
                        </button>
                      </div>
                      {records.length === 0 && (
                        <p className="profile-record-empty">
                          No records added yet.
                        </p>
                      )}
                      <div className="profile-record-list">
                        {records.map((record, recordIndex) => (
                          <article
                            className="profile-record-card"
                            key={record.recordId}
                          >
                            <div className="profile-record-card-heading">
                              <div>
                                <strong>{record.label}</strong>
                                <span>
                                  {definition.heading} #{recordIndex + 1}
                                </span>
                              </div>
                              <div className="profile-record-actions">
                                <button
                                  type="button"
                                  aria-label={`Move ${record.label} up`}
                                  disabled={recordIndex === 0}
                                  onClick={() => moveRecord(record, -1)}
                                >
                                  ↑
                                </button>
                                <button
                                  type="button"
                                  aria-label={`Move ${record.label} down`}
                                  disabled={recordIndex === records.length - 1}
                                  onClick={() => moveRecord(record, 1)}
                                >
                                  ↓
                                </button>
                                <button
                                  className="destructive"
                                  type="button"
                                  aria-label={`Remove ${record.label}`}
                                  onClick={() => removeRecord(record)}
                                >
                                  ×
                                </button>
                              </div>
                            </div>
                            <div className="vault-form profile-record-fields">
                              {definition.fields.map((field) => {
                                const draftKey = protectedRecordDraftKey(
                                  record.recordId,
                                  field.key,
                                );
                                const value = field.protected
                                  ? (protectedDrafts[draftKey] ??
                                    recordValue(record, field.key))
                                  : recordValue(record, field.key);
                                const shared = {
                                  value,
                                  onChange: (
                                    event: ChangeEvent<
                                      HTMLInputElement | HTMLTextAreaElement
                                    >,
                                  ) => {
                                    if (field.protected) {
                                      setProtectedDrafts((current) => ({
                                        ...current,
                                        [draftKey]: event.target.value,
                                      }));
                                      setStatus(
                                        "Protected edit waiting for confirmation",
                                      );
                                    } else {
                                      updateRecordFact(
                                        record.recordId,
                                        field,
                                        event.target.value,
                                        true,
                                      );
                                    }
                                  },
                                  onBlur: () => {
                                    if (field.protected)
                                      confirmProtectedRecordFact(
                                        record.recordId,
                                        field,
                                      );
                                  },
                                };
                                return (
                                  <label key={field.key}>
                                    <span>
                                      {field.label}
                                      {field.protected ? " · protected" : ""}
                                    </span>
                                    {field.multiline ? (
                                      <textarea rows={3} {...shared} />
                                    ) : (
                                      <input
                                        type={field.inputType ?? "text"}
                                        {...shared}
                                      />
                                    )}
                                  </label>
                                );
                              })}
                            </div>
                          </article>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </section>
            </div>
          )}

          {view === "resumes" && (
            <div className="workspace-card">
              <h2>Encrypted résumé vault</h2>
              <p>
                PDF and Word files are encrypted on this iPhone before upload.
              </p>
              <label className="file-picker">
                <span>{busy ? "Uploading…" : "Add résumé"}</span>
                <input
                  type="file"
                  accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  disabled={busy || !rawKey}
                  onChange={(event) => {
                    void addResume(event.target.files?.[0] ?? null);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              <div className="record-list">
                {resumes.length === 0 && (
                  <p>No résumé has been synchronized yet.</p>
                )}
                {resumes.map((resume) => (
                  <article key={resume.resumeId}>
                    <div>
                      <strong>{resume.name}</strong>
                      <span>
                        {Math.ceil(resume.sizeBytes / 1024)} KB · encrypted
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        rawKey && void downloadEncryptedResume(rawKey, resume)
                      }
                    >
                      Download
                    </button>
                  </article>
                ))}
              </div>
            </div>
          )}

          {view === "applications" && !selectedApplication && (
            <div className="workspace-card">
              <h2>Application review queue</h2>
              <p>
                Only pages with verified application-form evidence appear here.
                Ordinary browsing pages are ignored.
              </p>
              <div className="record-list">
                {applications.length === 0 && (
                  <p>No verified application checkpoint has synchronized yet.</p>
                )}
                {applications.map((application) => {
                  const prior = entities.get(
                    `APPLICATION.REVIEW.V1:review-${application.pageId}`,
                  ) as DecryptedEntity<ApplicationReview> | undefined;
                  const pending = pendingReviewCount(application, prior?.value);
                  return (
                    <article key={application.pageId}>
                      <div>
                        <strong>{application.title}</strong>
                        <span>
                          {new URL(application.url).hostname} ·{" "}
                          {application.questions.length} questions · {pending}{" "}
                          pending
                        </span>
                      </div>
                      <button
                        type="button"
                        disabled={application.questions.length === 0}
                        onClick={() => beginReview(application)}
                      >
                        {pending > 0
                          ? "Review"
                          : application.questions.length > 0
                            ? "View"
                            : "Tracked"}
                      </button>
                    </article>
                  );
                })}
              </div>
            </div>
          )}

          {view === "applications" && selectedApplication && (
            <div className="workspace-card">
              <button
                className="text-button"
                type="button"
                onClick={() => setSelectedApplication(null)}
              >
                ← Back to applications
              </button>
              <h2>{selectedApplication.title}</h2>
              <p>
                Confirm each answer for this application. Sensitive answers are
                never pre-approved.
              </p>
              {resumes.length > 0 && (
                <label className="workspace-field review-resume">
                  <span>Résumé locked to this review</span>
                  <select
                    value={reviewResumeId}
                    onChange={(event) => setReviewResumeId(event.target.value)}
                  >
                    {resumes.map((resume) => (
                      <option key={resume.resumeId} value={resume.resumeId}>
                        {resume.name}
                      </option>
                    ))}
                  </select>
                  <small>
                    The paired desktop shows this exact selection. The employer
                    file picker still requires manual confirmation.
                  </small>
                </label>
              )}
              <div className="review-list">
                {selectedApplication.questions.map((question, index) => {
                  const answer = reviewAnswers[index];
                  if (!answer) return null;
                  return (
                    <article key={question.questionId}>
                      <label>
                        <span>
                          {question.rawText}
                          {question.sensitive ? " · sensitive" : ""}
                        </span>
                        <input
                          value={answer.value}
                          onChange={(event) =>
                            setReviewAnswers((current) =>
                              current.map((item, itemIndex) =>
                                itemIndex === index
                                  ? {
                                      ...item,
                                      value: event.target.value,
                                      approved: false,
                                    }
                                  : item,
                              ),
                            )
                          }
                        />
                      </label>
                      <label className="approval-check">
                        <input
                          type="checkbox"
                          checked={answer.approved}
                          disabled={!answer.value.trim()}
                          onChange={(event) =>
                            setReviewAnswers((current) =>
                              current.map((item, itemIndex) =>
                                itemIndex === index
                                  ? { ...item, approved: event.target.checked }
                                  : item,
                              ),
                            )
                          }
                        />
                        Approved for this application
                      </label>
                    </article>
                  );
                })}
              </div>
              <button
                className="button primary"
                disabled={
                  busy || reviewAnswers.every((answer) => !answer.approved)
                }
                type="button"
                onClick={() => void saveApplicationReview()}
              >
                {busy ? "Synchronizing…" : "Synchronize approved answers"}
              </button>
            </div>
          )}

          {view === "devices" && (
            <div className="workspace-card">
              <h2>Paired Edge installations</h2>
              <p>Revoke a lost or retired device immediately.</p>
              <div className="record-list">
                {devices.map((device) => (
                  <article key={device.id}>
                    <div>
                      <strong>{device.platform}</strong>
                      <span>
                        Paired {new Date(device.createdAt).toLocaleDateString()}
                      </span>
                    </div>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void revokeDevice(device.id)}
                    >
                      Revoke
                    </button>
                  </article>
                ))}
              </div>
            </div>
          )}

          {view === "security" && (
            <div className="workspace-card recovery-card">
              <h2>Encryption recovery</h2>
              <p>
                This recovery key decrypts your synchronized profile and
                résumés. MUNSHI’s server cannot recover it for you.
              </p>
              <p>
                Workspace {workspace?.id ?? "unknown"} · vault{" "}
                {vaultFingerprint ?? "not unlocked"}
              </p>
              <button
                className="button secondary"
                type="button"
                onClick={() => setShowRecovery((current) => !current)}
              >
                {showRecovery ? "Hide recovery key" : "Show recovery key"}
              </button>
              {showRecovery && rawKey && (
                <div className="recovery-secret">
                  <code>{rawKey}</code>
                  <button
                    type="button"
                    onClick={() => void navigator.clipboard.writeText(rawKey)}
                  >
                    Copy
                  </button>
                </div>
              )}
              <label className="recovery-import">
                <span>Restore an existing recovery key</span>
                <textarea
                  rows={3}
                  value={recoveryInput}
                  onChange={(event) => setRecoveryInput(event.target.value)}
                />
              </label>
              <button
                className="button primary"
                disabled={busy || !recoveryInput.trim()}
                type="button"
                onClick={() => void restoreRecoveryKey()}
              >
                Restore and validate
              </button>
            </div>
          )}
        </section>
      </div>

      <nav
        className="workspace-mobile-nav"
        aria-label="Mobile workspace navigation"
      >
        <button
          className={view === "overview" ? "active" : ""}
          type="button"
          onClick={() => setView("overview")}
        >
          Home
        </button>
        <button
          className={view === "applications" ? "active" : ""}
          type="button"
          onClick={() => setView("applications")}
        >
          Applications
        </button>
        <button
          className={view === "profile" ? "active" : ""}
          type="button"
          onClick={() => setView("profile")}
        >
          Profile
        </button>
        <button
          className={view === "resumes" ? "active" : ""}
          type="button"
          onClick={() => setView("resumes")}
        >
          Résumés
        </button>
      </nav>
    </main>
  );
}
