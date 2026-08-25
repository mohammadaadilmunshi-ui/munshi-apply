import type {
  ApplicationPage,
  FillInstruction,
  ProfileFact,
} from "@munshi-apply/contracts";
import type {
  ProfileRecord,
  ProfileRecordKind,
  ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";
import { resolveProfileAnswer } from "@munshi-apply/application-model";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import {
  getActivePage,
  applyFillPlan,
  getHealth,
  getNativeHealth,
  getProfile,
  getProfileSyncStatus,
  nativeRuntimeCompatibility,
  requestFilePickerAssist,
  resolveProfileSyncConflict,
  saveProfile,
  type AutoPilotControllerStatus,
  type ExtensionRuntimeHealth,
  type NativeRuntimeHealth,
  type ProfileSyncStatus,
} from "../messaging/client";
import {
  deleteOpenAIKey,
  getAISettings,
  getNativeProfileSnapshot,
  listOpenAIModels,
  markAIDraftUsed,
  saveAISettings,
  setOpenAIKey,
  testOpenAIConnection,
  type AISettings,
} from "../messaging/native";
import {
  activateCloudEncryption,
  disconnectCloud,
  enrollCloudDevice,
  getCloudConnection,
  getCloudHealth,
  getCloudSnapshot,
  publishApplicationReview,
  type ApplicationReview,
  type CloudHealth,
  type CloudSnapshot,
} from "../storage/cloud";
import { AIControlCenter } from "./AIControlCenter";
import { AIDraftReview } from "./AIDraftReview";
import { AutoPilotControlCenter } from "./AutoPilotControlCenter";
import { ResumeVaultPanel } from "./ResumeVaultPanel";
import {
  canAutoApproveRememberedAnswer,
  getRememberedAnswer,
  saveRememberedAnswer,
} from "../storage/answer-memory";

type View = "application" | "profile" | "autopilot" | "ai" | "diagnostics";
type SaveState =
  "idle" | "editing" | "saving" | "synced" | "local" | "conflict" | "error";

type NativeState =
  | { status: "checking" }
  | { status: "unsupported" }
  | { status: "upgrade_required"; data: NativeRuntimeHealth; reason: string }
  | { status: "unavailable"; error: string }
  | { status: "healthy"; data: NativeRuntimeHealth };

type CloudState =
  | { status: "checking" }
  | { status: "disconnected" }
  | { status: "unavailable"; error: string }
  | { status: "connected"; data: CloudHealth };

type ProfileField = Pick<ProfileFact, "key" | "category" | "protected"> & {
  label: string;
  section: string;
  inputType?: "text" | "email" | "tel" | "url" | "date";
};

const defaultWorkspaceUrl =
  "https://munshi-apply-mobile.mohammadaadilmunshi.chatgpt.site";
const now = (): string => new Date().toISOString();

function emptyProfile(): ProfileSnapshot {
  const timestamp = now();
  return {
    profileId: crypto.randomUUID(),
    displayName: "My application profile",
    facts: [],
    records: [],
    recordTombstones: [],
    createdAt: timestamp,
    updatedAt: timestamp,
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

// prettier-ignore
const profileFields: readonly ProfileField[] = [
  { section: "Identity", key: "first_name", label: "First name", category: "IDENTITY", protected: true },
  { section: "Identity", key: "middle_name", label: "Middle name", category: "IDENTITY", protected: true },
  { section: "Identity", key: "last_name", label: "Last name", category: "IDENTITY", protected: true },
  { section: "Identity", key: "preferred_name", label: "Preferred name", category: "IDENTITY", protected: false },
  { section: "Identity", key: "honorific", label: "Title / honorific", category: "IDENTITY", protected: false },
  { section: "Identity", key: "pronouns", label: "Preferred pronouns", category: "IDENTITY", protected: true },
  { section: "Identity", key: "legal_name", label: "Full legal name", category: "IDENTITY", protected: true },
  { section: "Contact", key: "email", label: "Primary email", category: "CONTACT", protected: false, inputType: "email" },
  { section: "Contact", key: "alternate_email", label: "Alternate email", category: "CONTACT", protected: false, inputType: "email" },
  { section: "Contact", key: "phone", label: "Phone", category: "CONTACT", protected: false, inputType: "tel" },
  { section: "Contact", key: "linkedin", label: "LinkedIn URL", category: "CONTACT", protected: false, inputType: "url" },
  { section: "Contact", key: "github", label: "GitHub URL", category: "CONTACT", protected: false, inputType: "url" },
  { section: "Contact", key: "portfolio", label: "Portfolio URL", category: "CONTACT", protected: false, inputType: "url" },
  { section: "Address", key: "current_location", label: "Current location", category: "ADDRESS", protected: true },
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
  { section: "Application preferences", key: "security_clearance", label: "Security clearance", category: "SAVED_ANSWER", protected: true },
  { section: "Application preferences", key: "conflict_of_interest", label: "Conflict-of-interest answer", category: "SAVED_ANSWER", protected: true },
  { section: "Application preferences", key: "non_compete", label: "Non-compete / restrictive covenant answer", category: "SAVED_ANSWER", protected: true },
  { section: "Application preferences", key: "background_check", label: "Background-check answer", category: "SAVED_ANSWER", protected: true },
  { section: "Application preferences", key: "drug_screening", label: "Drug-screening answer", category: "SAVED_ANSWER", protected: true },
  { section: "Optional voluntary demographics", key: "veteran_status", label: "Veteran status", category: "VOLUNTARY_DEMOGRAPHIC", protected: true },
  { section: "Optional voluntary demographics", key: "protected_veteran_status", label: "Protected veteran status", category: "VOLUNTARY_DEMOGRAPHIC", protected: true },
  { section: "Optional voluntary demographics", key: "eeo_self_id", label: "EEO self-identification", category: "VOLUNTARY_DEMOGRAPHIC", protected: true },
  { section: "Optional voluntary demographics", key: "disability_status", label: "Disability status", category: "VOLUNTARY_DEMOGRAPHIC", protected: true },
  { section: "Optional voluntary demographics", key: "gender", label: "Gender", category: "VOLUNTARY_DEMOGRAPHIC", protected: true },
  { section: "Optional voluntary demographics", key: "race_ethnicity", label: "Race / ethnicity", category: "VOLUNTARY_DEMOGRAPHIC", protected: true },
];

const profileSections = Array.from(
  new Set(profileFields.map((field) => field.section)),
);

type RecordField = Pick<ProfileFact, "key" | "category" | "protected"> & {
  label: string;
  inputType?: "text" | "url" | "date";
  multiline?: boolean;
};

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
    { key: "education_start_date", label: "Start date", category: "EDUCATION", protected: true, inputType: "date" },
    { key: "graduation_date", label: "Graduation date", category: "EDUCATION", protected: true, inputType: "date" },
    { key: "gpa", label: "GPA (optional)", category: "EDUCATION", protected: true },
  ] },
  { kind: "EMPLOYMENT", heading: "Employment", addLabel: "Add employment", fallbackLabel: "New employment", primaryKey: "employer_name", fields: [
    { key: "employer_name", label: "Employer", category: "EMPLOYMENT", protected: true },
    { key: "job_title", label: "Job title", category: "EMPLOYMENT", protected: true },
    { key: "employment_location", label: "Location", category: "EMPLOYMENT", protected: false },
    { key: "company_industry", label: "Company industry", category: "EMPLOYMENT", protected: false },
    { key: "position_function", label: "Position function", category: "EMPLOYMENT", protected: false },
    { key: "employment_type", label: "Employment type", category: "EMPLOYMENT", protected: false },
    { key: "currently_employed", label: "Currently employed here", category: "EMPLOYMENT", protected: false },
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

function fieldDefinition(key: string): ProfileField | undefined {
  return profileFields.find((field) => field.key === key);
}

function valueOf(profile: ProfileSnapshot, key: string): string {
  const value = profile.facts.find((fact) => fact.key === key)?.value;
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function recordValue(record: ProfileRecord, key: string): string {
  const value = record.facts.find((fact) => fact.key === key)?.value;
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function recordDraftKey(recordId: string, key: string): string {
  return `record:${recordId}:${key}`;
}

type AnswerDraft = {
  value: string;
  approved: boolean;
  sensitive: boolean;
  sourceDraftId?: string | null;
  ownerEdited?: boolean;
  remembered?: boolean;
};

const defaultAISettings: AISettings = {
  provider: "auto",
  enabled: false,
  model: "",
  cheapModel: "",
  strongModel: "",
  ollamaModel: "",
  preferLocalFallback: true,
  monthlyBudgetUsd: 0,
  warningBudgetUsd: 0,
  hardStop: true,
  allowApplicationDrafts: false,
  allowProfileEvidence: true,
  allowResumeEvidence: true,
  keyConfigured: false,
  keySource: "none",
};

function sameOrigin(left: string, right: string): boolean {
  try {
    return new URL(left).origin === new URL(right).origin;
  } catch {
    return false;
  }
}

function profileConflictLabel(key: string): string {
  const field = fieldDefinition(key);
  if (field) return field.label;
  if (key.startsWith("record:")) {
    return key.split(":").at(-1)?.replaceAll("_", " ") ?? key;
  }
  return key.replaceAll("_", " ");
}

export function App() {
  const [view, setView] = useState<View>("application");
  const [page, setPage] = useState<ApplicationPage | null>(null);
  const [profile, setProfile] = useState<ProfileSnapshot>(emptyProfile);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [profileRecoveryIssue, setProfileRecoveryIssue] = useState<
    string | null
  >(null);
  const [profileDirty, setProfileDirty] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [retryTick, setRetryTick] = useState(0);
  const retryTimer = useRef<number | null>(null);
  const profileRevision = useRef(0);
  const [protectedDrafts, setProtectedDrafts] = useState<
    Record<string, string>
  >({});
  const [health, setHealth] = useState("Connecting");
  const [runtime, setRuntime] = useState<ExtensionRuntimeHealth | null>(null);
  const [native, setNative] = useState<NativeState>({ status: "checking" });
  const [cloud, setCloud] = useState<CloudState>({ status: "checking" });
  const [profileSyncStatus, setProfileSyncStatus] = useState<ProfileSyncStatus>(
    {
      conflict: null,
    },
  );
  const [profileConflictBusy, setProfileConflictBusy] = useState(false);
  const [workspaceUrl, setWorkspaceUrl] = useState(defaultWorkspaceUrl);
  const [pairingBundle, setPairingBundle] = useState("");
  const [activationBundle, setActivationBundle] = useState("");
  const [pairing, setPairing] = useState(false);
  const [cloudSnapshot, setCloudSnapshot] = useState<CloudSnapshot | null>(
    null,
  );
  const [answers, setAnswers] = useState<Record<string, AnswerDraft>>({});
  const [selectedResumeId, setSelectedResumeId] = useState("");
  const [filling, setFilling] = useState(false);
  const [notice, setNotice] = useState("");
  const [aiSettings, setAiSettings] = useState<AISettings>(defaultAISettings);
  const [apiKey, setApiKey] = useState("");
  const [aiModels, setAiModels] = useState<string[]>([]);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiMessage, setAiMessage] = useState("");
  const [autoPilotStatus, setAutoPilotStatus] =
    useState<AutoPilotControllerStatus | null>(null);
  const [lastCloudPullAt, setLastCloudPullAt] = useState<string | null>(null);

  const refreshAI = useCallback(async () => {
    try {
      setAiSettings(await getAISettings());
    } catch {
      // The updated native companion may not be installed yet.
    }
  }, []);

  const refresh = useCallback(async () => {
    const extensionRuntime = await getHealth();
    setHealth(extensionRuntime.status);
    setRuntime(extensionRuntime);

    if (!extensionRuntime.capabilities.nativeMessaging) {
      setNative({ status: "unsupported" });
    } else {
      setNative({ status: "checking" });
      void (async () => {
        try {
          const nativeHealth = await getNativeHealth();
          const compatibility = nativeRuntimeCompatibility(nativeHealth);
          if (!compatibility.compatible) {
            setNative({
              status: "upgrade_required",
              data: nativeHealth,
              reason: compatibility.reason,
            });
            return;
          }
          setNative({ status: "healthy", data: nativeHealth });
          void refreshAI();
        } catch (error) {
          setNative({
            status: "unavailable",
            error:
              error instanceof Error
                ? error.message
                : "Native companion is unavailable",
          });
        }
      })();
    }

    const activePage = await getActivePage().catch((error: unknown) => {
      setNotice(
        error instanceof Error
          ? `Application detection is recovering: ${error.message}`
          : "Application detection is recovering.",
      );
      return null;
    });
    setPage(activePage);

    let savedProfile: ProfileSnapshot | null = null;
    let profileLoadError: string | null = null;
    try {
      savedProfile = await getProfile();
    } catch (error) {
      profileLoadError =
        error instanceof Error ? error.message : "Unable to load profile";
      try {
        const nativeRecovery = await getNativeProfileSnapshot();
        if (nativeRecovery) {
          savedProfile = nativeRecovery;
          profileLoadError = null;
          setNotice(
            "Recovered your saved profile from the local encrypted desktop vault.",
          );
        }
      } catch (nativeError) {
        const nativeMessage =
          nativeError instanceof Error
            ? nativeError.message
            : "Native profile recovery failed";
        profileLoadError = `${profileLoadError}. ${nativeMessage}`;
      }
    }
    const syncStatus = await getProfileSyncStatus().catch(() => ({
      conflict: null,
    }));
    setProfileSyncStatus(syncStatus);
    if (savedProfile) setProfile(savedProfile);
    setProtectedDrafts({});
    profileRevision.current += 1;
    setProfileDirty(false);
    if (profileLoadError && !savedProfile) {
      setProfileRecoveryIssue(profileLoadError);
      setProfileLoaded(false);
      setSaveState("error");
    } else {
      setProfileRecoveryIssue(null);
      setProfileLoaded(true);
      setSaveState(syncStatus.conflict ? "conflict" : "idle");
    }

    setCloud({ status: "checking" });
    void (async () => {
      try {
        const connection = await getCloudConnection();
        if (!connection) {
          setCloud({ status: "disconnected" });
          return;
        }
        setWorkspaceUrl(connection.baseUrl);
        const cloudHealth = await getCloudHealth(connection);
        setCloud({ status: "connected", data: cloudHealth });
        if (!cloudHealth.encryptionReady) {
          setCloudSnapshot(null);
          return;
        }
        const snapshot = await getCloudSnapshot(connection);
        setCloudSnapshot(snapshot);
        setLastCloudPullAt(now());
        setSelectedResumeId(
          (current) => current || snapshot.resumes[0]?.resumeId || "",
        );
      } catch (error) {
        setCloud({
          status: "unavailable",
          error: error instanceof Error ? error.message : "Cloud unavailable",
        });
      }
    })();
  }, [refreshAI]);

  const pullCloudChanges = useCallback(async () => {
    if (profileDirty || Object.keys(protectedDrafts).length > 0) return;
    const connection = await getCloudConnection();
    if (!connection) return;
    const cloudHealth = await getCloudHealth(connection);
    setCloud({ status: "connected", data: cloudHealth });
    if (!cloudHealth.encryptionReady) return;
    const syncedProfile = await getProfile();
    const syncStatus = await getProfileSyncStatus();
    const snapshot = await getCloudSnapshot(connection);
    setCloudSnapshot(snapshot);
    setProfileSyncStatus(syncStatus);
    if (syncedProfile) {
      setProfile(syncedProfile);
      setProfileRecoveryIssue(null);
      setProfileLoaded(true);
      setProfileDirty(false);
      profileRevision.current += 1;
      setSaveState(syncStatus.conflict ? "conflict" : "synced");
    }
    setLastCloudPullAt(now());
  }, [profileDirty, protectedDrafts]);

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setHealth("unavailable");
      setNotice(
        error instanceof Error ? error.message : "Unable to load MUNSHI Apply",
      );
    });
    const listener = (message: {
      type?: string;
      payload?: ApplicationPage | null;
    }) => {
      if (message.type === "ACTIVE_PAGE_UPDATED" && message.payload) {
        setPage(message.payload);
      } else if (message.type === "ACTIVE_PAGE_CLEARED") {
        setPage(null);
      }
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => {
      chrome.runtime.onMessage.removeListener(listener);
      if (retryTimer.current !== null) window.clearTimeout(retryTimer.current);
    };
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    const pull = () => {
      if (cancelled || document.visibilityState !== "visible") return;
      void pullCloudChanges().catch((error: unknown) => {
        setNotice(
          error instanceof Error
            ? error.message
            : "Cloud profile refresh failed",
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
  }, [pullCloudChanges]);

  useEffect(() => {
    if (!profileLoaded || !profileDirty) return;
    const revision = profileRevision.current;
    setSaveState("editing");
    const timer = window.setTimeout(
      () => {
        setSaveState("saving");
        void saveProfile(profile)
          .then((acknowledgement) => {
            const status: ProfileSyncStatus = {
              conflict: acknowledgement.conflict,
            };
            setProfileSyncStatus(status);
            if (profileRevision.current !== revision) return;
            setProfileDirty(false);
            setSaveState(
              status.conflict
                ? "conflict"
                : acknowledgement.cloudSynced
                  ? "synced"
                  : "local",
            );
          })
          .catch(() => {
            void getProfileSyncStatus().then((status) => {
              setProfileSyncStatus(status);
              setSaveState(status.conflict ? "conflict" : "error");
              if (!status.conflict) {
                retryTimer.current = window.setTimeout(
                  () => setRetryTick((value) => value + 1),
                  5_000,
                );
              }
            });
          });
      },
      retryTick === 0 ? 800 : 0,
    );
    return () => window.clearTimeout(timer);
  }, [profile, profileDirty, profileLoaded, retryTick]);

  useEffect(() => {
    if (!page) {
      setAnswers({});
      return;
    }
    const review = cloudSnapshot?.reviews.find(
      (candidate: ApplicationReview) => candidate.pageId === page.pageId,
    );
    const next = Object.fromEntries(
      page.questions.map((question) => {
        const approved = review?.answers.find(
          (answer) => answer.questionId === question.questionId,
        );
        const resolution = resolveProfileAnswer(question, profile);
        const suggested = resolution.value ?? "";
        return [
          question.questionId,
          approved ?? {
            value: suggested,
            approved: resolution.state === "READY",
            sensitive: resolution.sensitive,
          },
        ];
      }),
    );
    setAnswers((current) =>
      Object.fromEntries(
        page.questions.map((question) => [
          question.questionId,
          current[question.questionId]?.ownerEdited
            ? current[question.questionId]!
            : next[question.questionId]!,
        ]),
      ),
    );
    setSelectedResumeId((current) => {
      const reviewedResume = review?.resumeId;
      if (
        reviewedResume &&
        cloudSnapshot?.resumes.some(
          (resume) => resume.resumeId === reviewedResume,
        )
      )
        return reviewedResume;
      if (
        current &&
        cloudSnapshot?.resumes.some((resume) => resume.resumeId === current)
      )
        return current;
      return cloudSnapshot?.resumes[0]?.resumeId ?? "";
    });
  }, [cloudSnapshot, page, profile]);

  useEffect(() => {
    let cancelled = false;
    if (!page) return () => undefined;

    void Promise.all(
      page.questions.map(
        async (question) =>
          [
            question.questionId,
            await getRememberedAnswer(question.rawText).catch(() => null),
          ] as const,
      ),
    ).then((entries) => {
      if (cancelled) return;
      const memories = new Map(entries);
      setAnswers((current) => {
        const next = { ...current };
        for (const question of page.questions) {
          const existing = next[question.questionId];
          if (existing?.ownerEdited || existing?.value.trim()) continue;
          const remembered = memories.get(question.questionId);
          if (!remembered?.value.trim()) continue;
          const control = page.controls.find(
            (candidate) => candidate.controlId === question.controlId,
          );
          next[question.questionId] = {
            value: remembered.value,
            approved: canAutoApproveRememberedAnswer({
              semanticType: question.semanticType,
              controlKind: control?.kind,
              value: remembered.value,
            }),
            sensitive: Boolean(question.sensitive || remembered.sensitive),
            remembered: true,
          };
        }
        return next;
      });
    });

    return () => {
      cancelled = true;
    };
  }, [page]);

  useEffect(() => {
    if (!page) return;
    for (const question of page.questions) {
      const answer = answers[question.questionId];
      if (!answer?.ownerEdited || !answer.approved || !answer.value.trim()) {
        continue;
      }
      void saveRememberedAnswer({
        question: question.rawText,
        semanticType: question.semanticType,
        value: answer.value,
        sensitive: Boolean(question.sensitive || answer.sensitive),
      }).catch((error: unknown) => {
        setNotice(
          error instanceof Error
            ? `Answer memory unavailable: ${error.message}`
            : "Answer memory is temporarily unavailable.",
        );
      });
    }
  }, [answers, page]);

  const selectedResume = useMemo(
    () =>
      cloudSnapshot?.resumes.find(
        (resume) => resume.resumeId === selectedResumeId,
      ) ?? null,
    [cloudSnapshot, selectedResumeId],
  );
  const employerFileControl = useMemo(
    () =>
      page?.controls.find(
        (control) =>
          control.kind === "FILE" &&
          /\b(resume|résumé|cv)\b/i.test(`${control.label} ${control.name}`),
      ) ??
      page?.controls.find((control) => control.kind === "FILE") ??
      null,
    [page],
  );
  const runtimeOwnsCurrentPage = Boolean(
    autoPilotStatus &&
    page &&
    autoPilotStatus.session.status !== "STOPPED" &&
    sameOrigin(autoPilotStatus.lastUrl, page.url),
  );
  const activeApplicationId = runtimeOwnsCurrentPage
    ? autoPilotStatus!.session.applicationId
    : (page?.pageId ?? "");

  const reviewCount = useMemo(
    () =>
      page?.questions.filter(
        (question) => !answers[question.questionId]?.approved,
      ).length ?? 0,
    [answers, page],
  );
  const connectionLabel =
    health.toLowerCase() !== "healthy"
      ? "Unavailable"
      : native.status === "healthy"
        ? "Connected"
        : native.status === "upgrade_required"
          ? "Companion update"
          : native.status === "checking"
            ? "Checking"
            : "Extension ready";
  const connectionClass =
    native.status === "healthy" || cloud.status === "connected"
      ? "healthy"
      : health.toLowerCase() === "healthy"
        ? "partial"
        : "unavailable";
  const saveLabel = !profileLoaded
    ? profileRecoveryIssue
      ? "Recovery mode"
      : "Loading profile…"
    : saveState === "editing"
      ? "Editing…"
      : saveState === "saving"
        ? "Saving…"
        : saveState === "synced"
          ? "Encrypted & synced"
          : saveState === "local"
            ? "Saved locally"
            : saveState === "conflict"
              ? "Profile review required"
              : saveState === "error"
                ? "Waiting to sync"
                : cloud.status === "connected" && cloud.data.encryptionReady
                  ? "Auto-sync ready"
                  : "Auto-save ready";

  function markProfileDirty(): void {
    if (!profileLoaded) return;
    profileRevision.current += 1;
    setProfileDirty(true);
    setRetryTick(0);
  }

  function updateFact(key: string, value: string, confirmed: boolean): void {
    const definition = fieldDefinition(key);
    if (!definition) return;
    const timestamp = now();
    setProfile((current) => {
      const existing = current.facts.find((fact) => fact.key === key);
      const nextFact: ProfileFact = {
        factId: existing?.factId ?? crypto.randomUUID(),
        key,
        value,
        category: definition.category,
        trustLevel: value && confirmed ? "USER_CONFIRMED" : "UNKNOWN",
        source: "SIDE_PANEL",
        confirmedAt: value && confirmed ? timestamp : null,
        updatedAt: timestamp,
        protected: definition.protected,
      };
      return {
        ...current,
        updatedAt: timestamp,
        facts: [...current.facts.filter((fact) => fact.key !== key), nextFact],
      };
    });
    if (!definition.protected || confirmed) markProfileDirty();
  }

  function confirmProtectedFact(key: string): void {
    if (!fieldDefinition(key)?.protected) return;
    const draftKey = `profile:${key}`;
    if (!(draftKey in protectedDrafts)) return;
    updateFact(key, protectedDrafts[draftKey] ?? "", true);
    setProtectedDrafts((current) => {
      const next = { ...current };
      delete next[draftKey];
      return next;
    });
  }

  function addRecord(definition: RecordDefinition): void {
    const timestamp = now();
    const recordId = crypto.randomUUID();
    setProfile((current) => {
      const sortOrder = current.records.filter(
        (record) => record.kind === definition.kind,
      ).length;
      return {
        ...current,
        updatedAt: timestamp,
        records: [
          ...current.records,
          {
            recordId,
            kind: definition.kind,
            label: definition.fallbackLabel,
            facts: [],
            sortOrder,
            createdAt: timestamp,
            updatedAt: timestamp,
          },
        ],
        recordTombstones: current.recordTombstones.filter(
          (tombstone) => tombstone.recordId !== recordId,
        ),
      };
    });
    markProfileDirty();
  }

  function updateRecordFact(
    recordId: string,
    field: RecordField,
    value: string,
    confirmed: boolean,
  ): void {
    const timestamp = now();
    setProfile((current) => ({
      ...current,
      updatedAt: timestamp,
      records: current.records.map((record) => {
        if (record.recordId !== recordId) return record;
        const existing = record.facts.find((fact) => fact.key === field.key);
        const fact: ProfileFact = {
          factId: existing?.factId ?? crypto.randomUUID(),
          key: field.key,
          value,
          category: field.category,
          trustLevel: value && confirmed ? "USER_CONFIRMED" : "UNKNOWN",
          source: "SIDE_PANEL_RECORD",
          confirmedAt: value && confirmed ? timestamp : null,
          updatedAt: timestamp,
          protected: field.protected,
        };
        const definition = recordDefinitions.find(
          (candidate) => candidate.kind === record.kind,
        );
        return {
          ...record,
          label:
            field.key === definition?.primaryKey && value.trim()
              ? value.trim()
              : record.label,
          facts: [
            ...record.facts.filter((candidate) => candidate.key !== field.key),
            fact,
          ],
          updatedAt: timestamp,
        };
      }),
    }));
    if (!field.protected || confirmed) markProfileDirty();
  }

  function confirmProtectedRecordFact(
    recordId: string,
    field: RecordField,
  ): void {
    const draftKey = recordDraftKey(recordId, field.key);
    if (!(draftKey in protectedDrafts)) return;
    updateRecordFact(recordId, field, protectedDrafts[draftKey] ?? "", true);
    setProtectedDrafts((current) => {
      const next = { ...current };
      delete next[draftKey];
      return next;
    });
  }

  function removeRecord(record: ProfileRecord): void {
    if (
      !window.confirm(
        `Remove ${record.label}? This change will synchronize across devices.`,
      )
    )
      return;
    const timestamp = now();
    setProfile((current) => ({
      ...current,
      updatedAt: timestamp,
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
          deletedAt: timestamp,
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
    const sameKind = profile.records
      .filter((candidate) => candidate.kind === record.kind)
      .sort(
        (left, right) =>
          left.sortOrder - right.sortOrder ||
          left.recordId.localeCompare(right.recordId),
      );
    const index = sameKind.findIndex(
      (candidate) => candidate.recordId === record.recordId,
    );
    const target = index + direction;
    if (index < 0 || target < 0 || target >= sameKind.length) return;
    [sameKind[index], sameKind[target]] = [sameKind[target]!, sameKind[index]!];
    const order = new Map(
      sameKind.map((candidate, sortOrder) => [candidate.recordId, sortOrder]),
    );
    const timestamp = now();
    setProfile((current) => ({
      ...current,
      updatedAt: timestamp,
      records: current.records.map((candidate) =>
        candidate.kind === record.kind
          ? {
              ...candidate,
              sortOrder: order.get(candidate.recordId) ?? candidate.sortOrder,
              updatedAt: timestamp,
            }
          : candidate,
      ),
    }));
    markProfileDirty();
  }

  async function resolveProfileConflict(
    winner: "local" | "remote",
  ): Promise<void> {
    setProfileConflictBusy(true);
    setNotice("");
    try {
      const resolved = await resolveProfileSyncConflict(winner);
      setProfile(resolved);
      setProtectedDrafts({});
      profileRevision.current += 1;
      setProfileDirty(false);
      setProfileSyncStatus({ conflict: null });
      setSaveState("synced");
      setNotice(
        winner === "local"
          ? "Protected profile conflict resolved using this Mac's confirmed values."
          : "Protected profile conflict resolved using the encrypted workspace values.",
      );
    } catch (error) {
      setSaveState("conflict");
      setNotice(
        error instanceof Error
          ? error.message
          : "Protected profile conflict resolution failed",
      );
    } finally {
      setProfileConflictBusy(false);
    }
  }

  async function syncNow(): Promise<void> {
    if (profileSyncStatus.conflict) {
      setSaveState("conflict");
      setNotice("Resolve the protected profile conflict before synchronizing.");
      return;
    }
    setSaveState("saving");
    const revision = profileRevision.current;
    try {
      const acknowledgement = await saveProfile(profile);
      const syncStatus: ProfileSyncStatus = {
        conflict: acknowledgement.conflict,
      };
      setProfileSyncStatus(syncStatus);
      if (profileRevision.current === revision) {
        setProfileDirty(false);
        setSaveState(
          syncStatus.conflict
            ? "conflict"
            : acknowledgement.cloudSynced
              ? "synced"
              : "local",
        );
        if (!syncStatus.conflict) {
          setNotice(
            acknowledgement.cloudSynced
              ? "Profile saved locally and acknowledged by the encrypted workspace."
              : "Profile saved locally. The encrypted workspace has not acknowledged this save yet.",
          );
        }
      }
    } catch (error) {
      const syncStatus = await getProfileSyncStatus().catch(() => ({
        conflict: null,
      }));
      setProfileSyncStatus(syncStatus);
      setSaveState(syncStatus.conflict ? "conflict" : "error");
      if (!syncStatus.conflict) {
        setNotice(
          error instanceof Error ? error.message : "Profile sync failed",
        );
      }
    }
  }

  async function pairCloud(): Promise<void> {
    if (!runtime) return;
    setPairing(true);
    setNotice("");
    try {
      const connection = await enrollCloudDevice({
        baseUrl: workspaceUrl,
        pairingBundle,
        platform: runtime.platform,
      });
      setCloud({ status: "connected", data: await getCloudHealth(connection) });
      setPairingBundle("");
      setNotice("This Edge installation is paired with the private workspace.");
    } catch (error) {
      setCloud({
        status: "unavailable",
        error: error instanceof Error ? error.message : "Pairing failed",
      });
    } finally {
      setPairing(false);
    }
  }

  async function unpairCloud(): Promise<void> {
    await disconnectCloud();
    setCloud({ status: "disconnected" });
    setNotice(
      "Local cloud credential removed. Revoke the device in the workspace too.",
    );
  }

  async function enableEncryptedSync(): Promise<void> {
    const connection = await getCloudConnection();
    if (!connection) return;
    setPairing(true);
    setNotice("");
    try {
      await activateCloudEncryption(connection, activationBundle);
      setActivationBundle("");
      setNotice("End-to-end encrypted synchronization is active.");
      await refresh();
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Encryption activation failed",
      );
    } finally {
      setPairing(false);
    }
  }

  async function fillApprovedFields(): Promise<void> {
    if (!page) return;
    setFilling(true);
    try {
      const workingAnswers: Record<string, AnswerDraft> = { ...answers };
      const attemptedControlIds = new Set<string>();
      const allResults: Awaited<ReturnType<typeof applyFillPlan>> = [];
      const usedDraftIds = new Set<string>();
      let currentPage: ApplicationPage = page;
      let dynamicRounds = 0;

      const connection = await getCloudConnection();
      if (
        connection &&
        cloud.status === "connected" &&
        cloud.data.encryptionReady
      ) {
        const selectedResume = cloudSnapshot?.resumes.find(
          (resume) => resume.resumeId === selectedResumeId,
        );
        const review: ApplicationReview = {
          reviewId: `review-${page.pageId}`,
          pageId: page.pageId,
          resumeId: selectedResumeId || null,
          resumeSha256: selectedResume?.sha256 ?? null,
          approvedAt: now(),
          answers: page.questions.map((question) => {
            const answer = workingAnswers[question.questionId] ?? {
              value: "",
              approved: false,
              sensitive: question.sensitive,
            };
            return {
              questionId: question.questionId,
              controlId: question.controlId,
              value: answer.value,
              approved: answer.approved,
              sensitive: question.sensitive,
            };
          }),
        };
        await publishApplicationReview(connection, review);
      }

      for (let round = 0; round < 4; round += 1) {
        const controls = new Map(
          currentPage.controls.map((control) => [control.controlId, control]),
        );
        const memories = await Promise.all(
          currentPage.questions.map(
            async (question) =>
              [
                question.questionId,
                await getRememberedAnswer(question.rawText).catch(() => null),
              ] as const,
          ),
        );
        const memoryByQuestion = new Map(memories);

        for (const question of currentPage.questions) {
          const existing = workingAnswers[question.questionId];
          if (existing?.value.trim()) continue;
          const resolution = resolveProfileAnswer(question, profile);
          if (resolution.value != null && String(resolution.value).trim()) {
            workingAnswers[question.questionId] = {
              value: String(resolution.value),
              approved: resolution.state === "READY",
              sensitive: resolution.sensitive,
            };
            continue;
          }
          const remembered = memoryByQuestion.get(question.questionId);
          if (!remembered?.value.trim()) continue;
          const control = controls.get(question.controlId);
          workingAnswers[question.questionId] = {
            value: remembered.value,
            approved: canAutoApproveRememberedAnswer({
              semanticType: question.semanticType,
              controlKind: control?.kind,
              value: remembered.value,
            }),
            sensitive: Boolean(question.sensitive || remembered.sensitive),
            remembered: true,
          };
        }

        setAnswers((current) => ({ ...current, ...workingAnswers }));

        const instructions: FillInstruction[] = currentPage.questions
          .map((question) => {
            const answer = workingAnswers[question.questionId];
            const control = controls.get(question.controlId);
            if (
              !answer ||
              !control ||
              !answer.value.trim() ||
              !answer.approved ||
              attemptedControlIds.has(question.controlId)
            ) {
              return null;
            }
            return {
              controlId: question.controlId,
              frameId: control.frameId,
              value: answer.value,
              sensitive: question.sensitive,
              approved: true,
            };
          })
          .filter(
            (instruction): instruction is FillInstruction =>
              instruction !== null,
          );

        if (instructions.length === 0) break;
        instructions.forEach((instruction) =>
          attemptedControlIds.add(instruction.controlId),
        );

        const results = await applyFillPlan({
          pageId: currentPage.pageId,
          instructions,
        });
        allResults.push(...results);
        for (const result of results) {
          if (result.status !== "FILLED") continue;
          const question = currentPage.questions.find(
            (candidate) => candidate.controlId === result.controlId,
          );
          const draftId = question
            ? workingAnswers[question.questionId]?.sourceDraftId
            : null;
          if (draftId) usedDraftIds.add(draftId);
        }

        await new Promise((resolve) => window.setTimeout(resolve, 450));
        const latest = await getActivePage();
        if (!latest || !sameOrigin(latest.url, currentPage.url)) break;
        const previousQuestionIds = new Set(
          currentPage.questions.map((question) => question.questionId),
        );
        const revealed = latest.questions.filter(
          (question) => !previousQuestionIds.has(question.questionId),
        ).length;
        if (revealed > 0) dynamicRounds += 1;
        currentPage = latest;
      }

      await Promise.allSettled(
        [...usedDraftIds].map((draftId) => markAIDraftUsed(draftId)),
      );
      const filled = allResults.filter(
        (result) => result.status === "FILLED",
      ).length;
      const skipped = allResults.length - filled;
      if (allResults.length === 0) {
        setNotice("No approved answers are ready to fill.");
        return;
      }
      setNotice(
        `${filled} field${filled === 1 ? "" : "s"} filled and verified${dynamicRounds ? ` across ${dynamicRounds + 1} dynamic form passes` : ""}${skipped ? `; ${skipped} require manual interaction` : ""}. Newly revealed unresolved questions stay visible for your review. Final submission remains manual.`,
      );
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Verified fill failed",
      );
    } finally {
      setFilling(false);
    }
  }

  async function storeApiKey(): Promise<void> {
    if (!apiKey.trim()) return;
    setAiBusy(true);
    setAiMessage("");
    try {
      setAiSettings(await setOpenAIKey(apiKey.trim()));
      setApiKey("");
      setAiMessage(
        "API key stored in macOS Keychain. It is not stored in the extension or cloud sync.",
      );
    } catch (error) {
      setAiMessage(
        error instanceof Error ? error.message : "Unable to store API key",
      );
    } finally {
      setAiBusy(false);
    }
  }

  async function removeApiKey(): Promise<void> {
    setAiBusy(true);
    try {
      setAiSettings(await deleteOpenAIKey());
      setAiModels([]);
      setAiMessage("Keychain credential removed.");
    } catch (error) {
      setAiMessage(
        error instanceof Error ? error.message : "Unable to remove API key",
      );
    } finally {
      setAiBusy(false);
    }
  }

  async function persistAISettings(): Promise<void> {
    setAiBusy(true);
    try {
      setAiSettings(await saveAISettings(aiSettings));
      setAiMessage("AI controls saved locally. No model call was made.");
    } catch (error) {
      setAiMessage(
        error instanceof Error ? error.message : "Unable to save AI controls",
      );
    } finally {
      setAiBusy(false);
    }
  }

  async function testAI(): Promise<void> {
    setAiBusy(true);
    setAiMessage("Testing OpenAI connection…");
    try {
      const result = await testOpenAIConnection();
      const models = await listOpenAIModels();
      setAiModels(models);
      setAiMessage(
        `Connected to OpenAI. ${result.modelCount} models are visible to this key.`,
      );
    } catch (error) {
      setAiMessage(
        error instanceof Error
          ? error.message
          : "OpenAI connection test failed",
      );
    } finally {
      setAiBusy(false);
    }
  }

  return (
    <main>
      <header className="brand">
        <div>
          <p className="eyebrow">Universal application intelligence</p>
          <h1>MUNSHI Apply</h1>
        </div>
        <span className={`status ${connectionClass}`}>{connectionLabel}</span>
      </header>
      <nav aria-label="MUNSHI Apply sections">
        {(
          ["application", "profile", "autopilot", "ai", "diagnostics"] as const
        ).map((item) => (
          <button
            className={view === item ? "active" : ""}
            key={item}
            onClick={() => setView(item)}
            type="button"
          >
            {item}
          </button>
        ))}
      </nav>
      {profileSyncStatus.conflict && (
        <div className="notice review profile-conflict-banner">
          <div>
            <strong>Profile review required.</strong>{" "}
            {profileSyncStatus.conflict.keys
              .map(profileConflictLabel)
              .join(", ")}
            {profileSyncStatus.conflict.keys.length === 1
              ? " differs"
              : " differ"}
            {" between this Mac and the encrypted workspace."}
          </div>
          {view !== "profile" && (
            <button
              className="quiet"
              type="button"
              onClick={() => setView("profile")}
            >
              Review profile
            </button>
          )}
        </div>
      )}
      {notice && <div className="notice">{notice}</div>}

      {view === "application" && (
        <section>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current application</p>
              <h2>{page?.title || "No application detected"}</h2>
            </div>
            <button
              type="button"
              className="quiet"
              onClick={() => void refresh()}
            >
              Refresh
            </button>
          </div>
          {page ? (
            <>
              <p className="url">{new URL(page.url).hostname}</p>
              <div className="metrics">
                <article>
                  <strong>{page.controls.length}</strong>
                  <span>controls</span>
                </article>
                <article>
                  <strong>{page.questions.length}</strong>
                  <span>questions</span>
                </article>
                <article>
                  <strong>{reviewCount}</strong>
                  <span>review</span>
                </article>
              </div>
              <h3>Pre-flight answers</h3>
              <div className="answer-list">
                {page.questions.length === 0 && (
                  <p>No visible questions found on this page.</p>
                )}
                {page.questions.map((question) => {
                  const answer = answers[question.questionId] ?? {
                    value: "",
                    approved: false,
                    sensitive: question.sensitive,
                  };
                  return (
                    <article className="answer-card" key={question.questionId}>
                      <div className="answer-heading">
                        <div>
                          <strong>{question.rawText}</strong>
                          <span>
                            {question.semanticType.replaceAll("_", " ")}
                          </span>
                        </div>
                        <span
                          className={
                            question.sensitive ? "badge review" : "badge"
                          }
                        >
                          {question.sensitive
                            ? "sensitive"
                            : `${Math.round(question.confidence * 100)}%`}
                        </span>
                      </div>
                      <input
                        type="text"
                        value={answer.value}
                        placeholder="Enter or confirm the answer"
                        onChange={(event) =>
                          setAnswers((current) => ({
                            ...current,
                            [question.questionId]: {
                              ...answer,
                              value: event.target.value,
                              approved: false,
                              sourceDraftId: null,
                              ownerEdited: true,
                            },
                          }))
                        }
                      />
                      <label className="answer-approval">
                        <input
                          type="checkbox"
                          checked={answer.approved}
                          disabled={!answer.value.trim()}
                          onChange={(event) =>
                            setAnswers((current) => ({
                              ...current,
                              [question.questionId]: {
                                ...answer,
                                approved: event.target.checked,
                                ownerEdited: true,
                              },
                            }))
                          }
                        />
                        Approved · remember for matching questions
                      </label>
                      {answer.remembered && (
                        <span className="answer-memory-note">
                          Remembered from a previous approved answer.
                        </span>
                      )}
                      <AIDraftReview
                        applicationId={activeApplicationId || page.pageId}
                        pageId={page.pageId}
                        question={question}
                        nativeAvailable={native.status === "healthy"}
                        pageContext={page.pageContext ?? ""}
                        onApproved={(value, draftId) =>
                          setAnswers((current) => ({
                            ...current,
                            [question.questionId]: {
                              value,
                              approved: true,
                              sensitive: question.sensitive,
                              sourceDraftId: draftId,
                              ownerEdited: true,
                            },
                          }))
                        }
                      />
                    </article>
                  );
                })}
              </div>
              {cloudSnapshot?.resumes.length ? (
                <label className="resume-select">
                  <span>Résumé selected for this application</span>
                  <select
                    value={selectedResumeId}
                    onChange={(event) =>
                      setSelectedResumeId(event.target.value)
                    }
                  >
                    {cloudSnapshot.resumes.map((resume) => (
                      <option key={resume.resumeId} value={resume.resumeId}>
                        {resume.source === "MASTER"
                          ? "Master · "
                          : resume.source === "TAILORED"
                            ? `Tailored${resume.roleFamily ? ` (${resume.roleFamily})` : ""} · `
                            : ""}
                        {resume.name}
                      </option>
                    ))}
                  </select>
                  <small>
                    Browser security requires you to choose the file in the
                    employer’s upload control manually.
                  </small>
                  {employerFileControl && (
                    <button
                      className="quiet"
                      type="button"
                      onClick={() =>
                        void requestFilePickerAssist(
                          employerFileControl.frameId,
                          employerFileControl.controlId,
                        )
                          .then(() =>
                            setNotice(
                              "Employer file handoff opened. Choose the matching résumé file; MUNSHI will verify it after selection.",
                            ),
                          )
                          .catch((error: unknown) =>
                            setNotice(
                              error instanceof Error
                                ? error.message
                                : "Unable to open employer file handoff",
                            ),
                          )
                      }
                    >
                      Open employer file picker
                    </button>
                  )}
                </label>
              ) : null}
              <button
                className="primary fill-button"
                type="button"
                disabled={filling || page.questions.length === 0}
                onClick={() => void fillApprovedFields()}
              >
                {filling ? "Filling and verifying…" : "Fill approved fields"}
              </button>
              <div className="safety-callout">
                <strong>Guarded action</strong>
                <span>
                  Only approved answers are filled. CAPTCHA, MFA, file
                  selection, and final submission stay manual.
                </span>
              </div>
            </>
          ) : (
            <p>
              Open a browser-based application page. The universal scanner will
              map visible controls without changing the page.
            </p>
          )}
        </section>
      )}

      {view === "autopilot" && (
        <AutoPilotControlCenter
          page={page}
          answers={answers}
          applicationId={activeApplicationId || page?.pageId || ""}
          selectedResumeId={selectedResumeId || null}
          selectedResumeSha256={selectedResume?.sha256 ?? null}
          nativeAvailable={native.status === "healthy"}
          onStatusChange={setAutoPilotStatus}
        />
      )}

      {view === "profile" && (
        <section>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Encrypted profile vault</p>
              <h2>Complete application profile</h2>
            </div>
            <span
              className={
                saveState === "error" || saveState === "conflict"
                  ? "badge review"
                  : "badge"
              }
            >
              {saveLabel}
            </span>
          </div>
          <p>
            Regular facts save automatically after you stop typing. Protected
            facts become confirmed only after you leave the field, and are
            encrypted before cloud synchronization.
          </p>
          {!profileLoaded && (
            <div className="profile-conflict-panel">
              <strong>Profile recovery mode</strong>
              <p>
                Autosave is disabled and profile fields are locked until MUNSHI
                confirms a stored snapshot. No empty profile will be written
                over your saved data.
              </p>
              {profileRecoveryIssue && <p>{profileRecoveryIssue}</p>}
              <button
                className="quiet"
                type="button"
                onClick={() => void refresh()}
              >
                Retry profile recovery
              </button>
            </div>
          )}
          {profileSyncStatus.conflict && (
            <div className="profile-conflict-panel">
              <strong>Choose the authoritative protected value</strong>
              <p>
                Both sides contain confirmed protected information, so MUNSHI
                will not choose automatically. Review every difference below,
                then explicitly keep one side for all listed conflicts.
              </p>
              <div className="profile-conflict-list">
                {profileSyncStatus.conflict.keys.map((key) => {
                  const detail = profileSyncStatus.conflict?.details.find(
                    (candidate) => candidate.key === key,
                  );
                  return (
                    <article key={key}>
                      <strong>{profileConflictLabel(key)}</strong>
                      <span>
                        This Mac: {String(detail?.localValue ?? "(empty)")}
                      </span>
                      <span>
                        Workspace: {String(detail?.remoteValue ?? "(empty)")}
                      </span>
                    </article>
                  );
                })}
              </div>
              <div className="profile-conflict-actions">
                <button
                  className="primary"
                  type="button"
                  disabled={profileConflictBusy}
                  onClick={() => void resolveProfileConflict("local")}
                >
                  Keep this Mac's values
                </button>
                <button
                  className="quiet"
                  type="button"
                  disabled={profileConflictBusy}
                  onClick={() => void resolveProfileConflict("remote")}
                >
                  Use workspace values
                </button>
              </div>
            </div>
          )}
          {profileSections.map((sectionName) => (
            <div key={sectionName}>
              <h3>{sectionName}</h3>
              {sectionName === "Optional voluntary demographics" && (
                <p>
                  Optional. MUNSHI never infers these answers and never uses an
                  unconfirmed value.
                </p>
              )}
              <div className="form-grid">
                {profileFields
                  .filter((field) => field.section === sectionName)
                  .map((field) => (
                    <label key={field.key}>
                      <span>
                        {field.label}
                        {field.protected ? " · protected" : ""}
                      </span>
                      <input
                        disabled={!profileLoaded}
                        type={field.inputType ?? "text"}
                        value={
                          field.protected
                            ? (protectedDrafts[`profile:${field.key}`] ??
                              valueOf(profile, field.key))
                            : valueOf(profile, field.key)
                        }
                        onChange={(event) => {
                          if (field.protected) {
                            const draftKey = `profile:${field.key}`;
                            setProtectedDrafts((current) => ({
                              ...current,
                              [draftKey]: event.target.value,
                            }));
                            setSaveState("editing");
                          } else {
                            updateFact(field.key, event.target.value, true);
                          }
                        }}
                        onBlur={() =>
                          field.protected && confirmProtectedFact(field.key)
                        }
                      />
                    </label>
                  ))}
              </div>
            </div>
          ))}
          <div className="repeatable-profile">
            <div className="repeatable-intro">
              <h3>Experience and qualifications</h3>
              <p>
                Add every relevant record. Order controls which record is used
                first when an application asks for one item.
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
                <div className="record-section" key={definition.kind}>
                  <div className="record-section-heading">
                    <div>
                      <h3>{definition.heading}</h3>
                      <span>
                        {records.length}{" "}
                        {records.length === 1 ? "record" : "records"}
                      </span>
                    </div>
                    <button
                      className="quiet"
                      type="button"
                      disabled={!profileLoaded}
                      onClick={() => addRecord(definition)}
                    >
                      {definition.addLabel}
                    </button>
                  </div>
                  {records.length === 0 && (
                    <p className="record-empty">No records added yet.</p>
                  )}
                  <div className="record-list">
                    {records.map((record, recordIndex) => (
                      <article className="record-card" key={record.recordId}>
                        <div className="record-card-heading">
                          <div>
                            <strong>{record.label}</strong>
                            <span>
                              {definition.heading} #{recordIndex + 1}
                            </span>
                          </div>
                          <div className="record-actions">
                            <button
                              className="icon-button"
                              type="button"
                              aria-label={`Move ${record.label} up`}
                              title="Move up"
                              disabled={!profileLoaded || recordIndex === 0}
                              onClick={() => moveRecord(record, -1)}
                            >
                              ↑
                            </button>
                            <button
                              className="icon-button"
                              type="button"
                              aria-label={`Move ${record.label} down`}
                              title="Move down"
                              disabled={
                                !profileLoaded ||
                                recordIndex === records.length - 1
                              }
                              onClick={() => moveRecord(record, 1)}
                            >
                              ↓
                            </button>
                            <button
                              className="icon-button destructive"
                              type="button"
                              aria-label={`Remove ${record.label}`}
                              title="Remove record"
                              disabled={!profileLoaded}
                              onClick={() => removeRecord(record)}
                            >
                              ×
                            </button>
                          </div>
                        </div>
                        <div className="form-grid record-fields">
                          {definition.fields.map((field) => {
                            const draftKey = recordDraftKey(
                              record.recordId,
                              field.key,
                            );
                            const value = field.protected
                              ? (protectedDrafts[draftKey] ??
                                recordValue(record, field.key))
                              : recordValue(record, field.key);
                            const shared = {
                              disabled: !profileLoaded,
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
                                  setSaveState("editing");
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
          </div>
          <div className="cloud-connection">
            <strong>{saveLabel}</strong>
            <span>
              Profile autosave is enabled. Manual sync remains available as a
              fallback.
            </span>
            <button
              className="quiet"
              type="button"
              disabled={!profileLoaded}
              onClick={() => void syncNow()}
            >
              Sync now
            </button>
          </div>
          {cloud.status === "connected" && cloud.data.encryptionReady && (
            <ResumeVaultPanel
              snapshot={cloudSnapshot}
              selectedResumeId={selectedResumeId}
              currentRole={page?.title ?? null}
              nativeAvailable={native.status === "healthy"}
              applicationId={activeApplicationId || null}
              onSelected={setSelectedResumeId}
              onRefresh={refresh}
              onNotice={setNotice}
            />
          )}
        </section>
      )}

      {view === "ai" && (
        <AIControlCenter
          nativeAvailable={native.status === "healthy"}
          nativeIssue={
            native.status === "upgrade_required" ? native.reason : undefined
          }
        />
      )}

      {view === "diagnostics" && (
        <section>
          <p className="eyebrow">Runtime diagnostics</p>
          <h2>Foundation health</h2>
          <dl className="diagnostics">
            <div>
              <dt>Extension runtime</dt>
              <dd>{health}</dd>
            </div>
            <div>
              <dt>Device platform</dt>
              <dd>{runtime?.platform ?? "checking"}</dd>
            </div>
            <div>
              <dt>Native companion</dt>
              <dd>{native.status}</dd>
            </div>
            <div>
              <dt>Native protocol</dt>
              <dd>
                {native.status === "healthy" ||
                native.status === "upgrade_required"
                  ? (native.data.protocol_version ?? "legacy")
                  : "not available"}
              </dd>
            </div>
            <div>
              <dt>SQLite database</dt>
              <dd>
                {native.status === "healthy"
                  ? native.data.database
                  : native.status === "unsupported"
                    ? "cloud path required"
                    : native.status}
              </dd>
            </div>
            <div>
              <dt>Schema version</dt>
              <dd>
                {native.status === "healthy"
                  ? native.data.schema_version
                  : "not available"}
              </dd>
            </div>
            <div>
              <dt>Outbox pending</dt>
              <dd>
                {native.status === "healthy"
                  ? (native.data.outbox.PENDING ?? 0)
                  : "not available"}
              </dd>
            </div>
            <div>
              <dt>Universal scanner</dt>
              <dd>{page ? "active" : "waiting"}</dd>
            </div>
            <div>
              <dt>Profile vault</dt>
              <dd>
                {profileLoaded ? (
                  <>
                    {profile.facts.filter(
                      (fact) => fact.trustLevel !== "UNKNOWN",
                    ).length +
                      profile.records
                        .flatMap((record) => record.facts)
                        .filter((fact) => fact.trustLevel !== "UNKNOWN")
                        .length}{" "}
                    confirmed facts · {profile.records.length} records
                  </>
                ) : (
                  "recovery mode · autosave disabled"
                )}
              </dd>
            </div>
            <div>
              <dt>Profile sync</dt>
              <dd>{saveLabel}</dd>
            </div>
            <div>
              <dt>Automation</dt>
              <dd>guarded fill</dd>
            </div>
            <div>
              <dt>AI provider</dt>
              <dd>
                {aiSettings.keyConfigured
                  ? `OpenAI · ${aiSettings.enabled ? "enabled" : "configured"}`
                  : "not configured"}
              </dd>
            </div>
            <div>
              <dt>Cloud synchronization</dt>
              <dd>
                {cloud.status === "connected"
                  ? cloud.data.encryptionReady
                    ? "encrypted"
                    : "paired only"
                  : cloud.status}
              </dd>
            </div>
            <div>
              <dt>Cloud workspace</dt>
              <dd>
                {cloud.status === "connected"
                  ? (cloud.data.workspaceId ?? "unknown")
                  : "not connected"}
              </dd>
            </div>
            <div>
              <dt>Vault fingerprint</dt>
              <dd>
                {cloud.status === "connected"
                  ? (cloud.data.vaultFingerprint ?? "not unlocked")
                  : "not connected"}
              </dd>
            </div>
            <div>
              <dt>Last cloud pull</dt>
              <dd>
                {lastCloudPullAt
                  ? new Date(lastCloudPullAt).toLocaleTimeString()
                  : "not yet"}
              </dd>
            </div>
          </dl>
          {native.status === "upgrade_required" && (
            <p className="diagnostic-error">
              Native companion update required: {native.reason}
            </p>
          )}
          {native.status === "unavailable" && (
            <p className="diagnostic-error">
              Native connection failed: {native.error}
            </p>
          )}
          {cloud.status === "unavailable" && (
            <p className="diagnostic-error">
              Cloud connection failed: {cloud.error}
            </p>
          )}
          {cloud.status === "connected" ? (
            <div className="cloud-connection">
              <strong>Private workspace paired</strong>
              <span>{new URL(cloud.data.baseUrl).hostname}</span>
              {cloud.data.encryptionReady ? (
                <span className="encryption-active">
                  End-to-end encrypted synchronization active
                </span>
              ) : (
                <div className="encryption-upgrade">
                  <strong>Enable encrypted synchronization</strong>
                  <p>
                    Create a new one-time code in the updated private workspace,
                    paste it below, then activate encryption. Your existing
                    pairing remains intact.
                  </p>
                  <textarea
                    rows={4}
                    value={activationBundle}
                    onChange={(event) =>
                      setActivationBundle(event.target.value)
                    }
                    placeholder="Paste the new one-time code"
                  />
                  <button
                    className="primary"
                    type="button"
                    disabled={pairing || !activationBundle.trim()}
                    onClick={() => void enableEncryptedSync()}
                  >
                    {pairing ? "Activating…" : "Activate encrypted sync"}
                  </button>
                </div>
              )}
              <button
                type="button"
                className="quiet"
                onClick={() =>
                  void chrome.tabs.create({
                    url: cloud.data.baseUrl + "/workspace",
                  })
                }
              >
                Open private workspace
              </button>
              <button
                type="button"
                className="quiet"
                onClick={() => void unpairCloud()}
              >
                Remove local pairing
              </button>
            </div>
          ) : (
            <div className="cloud-pairing">
              <h3>Pair this Edge installation</h3>
              <p>
                Sign in to the private mobile workspace, create a one-time
                bundle, and paste it here. The bundle expires after 10 minutes.
              </p>
              <label>
                <span>Private workspace URL</span>
                <input
                  type="url"
                  value={workspaceUrl}
                  onChange={(event) => setWorkspaceUrl(event.target.value)}
                />
              </label>
              <label>
                <span>One-time pairing bundle</span>
                <textarea
                  rows={4}
                  value={pairingBundle}
                  onChange={(event) => setPairingBundle(event.target.value)}
                  placeholder={'{"challengeId":"…","secret":"…"}'}
                />
              </label>
              <button
                className="primary"
                type="button"
                disabled={pairing || !pairingBundle.trim()}
                onClick={() => void pairCloud()}
              >
                {pairing ? "Pairing…" : "Pair device"}
              </button>
            </div>
          )}

          <div hidden>
            <h3>AI & API control center</h3>
            <p>
              The OpenAI API key is stored only in macOS Keychain by the native
              companion. It is never written to GitHub, browser storage, profile
              sync, or cloud workspace data.
            </p>
            {native.status === "healthy" ? (
              <>
                <label>
                  <span>
                    OpenAI API key ·{" "}
                    {aiSettings.keyConfigured
                      ? `configured (${aiSettings.keySource})`
                      : "not configured"}
                  </span>
                  <input
                    type="password"
                    autoComplete="off"
                    value={apiKey}
                    placeholder="Paste your OpenAI API key"
                    onChange={(event) => setApiKey(event.target.value)}
                  />
                </label>
                <button
                  className="primary"
                  type="button"
                  disabled={aiBusy || !apiKey.trim()}
                  onClick={() => void storeApiKey()}
                >
                  Store key in macOS Keychain
                </button>
                <button
                  className="quiet"
                  type="button"
                  disabled={aiBusy || !aiSettings.keyConfigured}
                  onClick={() => void removeApiKey()}
                >
                  Delete stored key
                </button>
                <label>
                  <span>Selected model</span>
                  <input
                    type="text"
                    list="munshi-openai-models"
                    value={aiSettings.model}
                    placeholder="Test connection, then choose a model"
                    onChange={(event) =>
                      setAiSettings((current) => ({
                        ...current,
                        model: event.target.value,
                      }))
                    }
                  />
                  <datalist id="munshi-openai-models">
                    {aiModels.map((model) => (
                      <option key={model} value={model} />
                    ))}
                  </datalist>
                </label>
                <label>
                  <span>
                    Monthly budget in USD (0 means no paid usage approved)
                  </span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={aiSettings.monthlyBudgetUsd}
                    onChange={(event) =>
                      setAiSettings((current) => ({
                        ...current,
                        monthlyBudgetUsd: Number(event.target.value),
                      }))
                    }
                  />
                </label>
                <label>
                  <span>Warning threshold in USD</span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={aiSettings.warningBudgetUsd}
                    onChange={(event) =>
                      setAiSettings((current) => ({
                        ...current,
                        warningBudgetUsd: Number(event.target.value),
                      }))
                    }
                  />
                </label>
                <button
                  className="quiet"
                  type="button"
                  onClick={() =>
                    setAiSettings((current) => ({
                      ...current,
                      enabled: !current.enabled,
                    }))
                  }
                >
                  AI features: {aiSettings.enabled ? "Enabled" : "Disabled"}
                </button>
                <button
                  className="quiet"
                  type="button"
                  onClick={() =>
                    setAiSettings((current) => ({
                      ...current,
                      hardStop: !current.hardStop,
                    }))
                  }
                >
                  Hard budget stop: {aiSettings.hardStop ? "On" : "Off"}
                </button>
                <button
                  className="quiet"
                  type="button"
                  disabled={aiBusy || !aiSettings.keyConfigured}
                  onClick={() => void testAI()}
                >
                  Test connection & load models
                </button>
                <button
                  className="primary"
                  type="button"
                  disabled={aiBusy}
                  onClick={() => void persistAISettings()}
                >
                  Save AI controls
                </button>
                {aiMessage && <span>{aiMessage}</span>}
                <div className="safety-callout">
                  <strong>Generation remains gated</strong>
                  <span>
                    Connecting OpenAI does not authorize MUNSHI to invent
                    application answers. Evidence retrieval, contradiction
                    checks, and budget enforcement remain required before
                    generated answers can be used.
                  </span>
                </div>
              </>
            ) : (
              <span>
                Install the updated native companion before managing API
                credentials.
              </span>
            )}
          </div>
        </section>
      )}
    </main>
  );
}
