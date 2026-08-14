import type {
  ApplicationPage,
  FillInstruction,
  MasterProfile,
  ProfileFact,
} from "@munshi-apply/contracts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getActivePage,
  applyFillPlan,
  getHealth,
  getNativeHealth,
  getProfile,
  saveProfile,
  type ExtensionRuntimeHealth,
  type NativeRuntimeHealth,
} from "../messaging/client";
import {
  deleteOpenAIKey,
  getAISettings,
  listOpenAIModels,
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
  publishApplicationSnapshot,
  uploadEncryptedResume,
  type ApplicationReview,
  type CloudHealth,
  type CloudSnapshot,
} from "../storage/cloud";

type View = "application" | "profile" | "diagnostics";
type SaveState = "idle" | "editing" | "saving" | "synced" | "local" | "error";

type NativeState =
  | { status: "checking" }
  | { status: "unsupported" }
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

function emptyProfile(): MasterProfile {
  const timestamp = now();
  return {
    profileId: crypto.randomUUID(),
    displayName: "My application profile",
    facts: [],
    createdAt: timestamp,
    updatedAt: timestamp,
    schemaVersion: 1,
  };
}

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
  { section: "Education", key: "school_name", label: "School / university", category: "EDUCATION", protected: false },
  { section: "Education", key: "highest_degree", label: "Degree", category: "EDUCATION", protected: false },
  { section: "Education", key: "field_of_study", label: "Field of study", category: "EDUCATION", protected: false },
  { section: "Education", key: "graduation_date", label: "Graduation date", category: "EDUCATION", protected: false, inputType: "date" },
  { section: "Education", key: "gpa", label: "GPA (optional)", category: "EDUCATION", protected: false },
  { section: "Experience", key: "current_employer", label: "Current / most recent employer", category: "EMPLOYMENT", protected: false },
  { section: "Experience", key: "current_title", label: "Current / most recent title", category: "EMPLOYMENT", protected: false },
  { section: "Experience", key: "employment_summary", label: "Experience summary", category: "EMPLOYMENT", protected: false },
  { section: "Experience", key: "project_summary", label: "Project summary", category: "PROJECT", protected: false },
  { section: "Skills & credentials", key: "skills", label: "Skills", category: "SKILL", protected: false },
  { section: "Skills & credentials", key: "certifications", label: "Certifications", category: "CERTIFICATION", protected: false },
  { section: "Skills & credentials", key: "languages", label: "Languages", category: "LANGUAGE", protected: false },
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

function fieldDefinition(key: string): ProfileField | undefined {
  return profileFields.find((field) => field.key === key);
}

function valueOf(profile: MasterProfile, key: string): string {
  const value = profile.facts.find((fact) => fact.key === key)?.value;
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

type AnswerDraft = {
  value: string;
  approved: boolean;
  sensitive: boolean;
};

const semanticFactKey: Readonly<Record<string, string>> = {
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

const defaultAISettings: AISettings = {
  provider: "openai",
  enabled: false,
  model: "",
  monthlyBudgetUsd: 0,
  warningBudgetUsd: 0,
  hardStop: true,
  keyConfigured: false,
  keySource: "none",
};

// prettier-ignore
export function App() {
  const [view, setView] = useState<View>("application");
  const [page, setPage] = useState<ApplicationPage | null>(null);
  const [profile, setProfile] = useState<MasterProfile>(emptyProfile);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [profileDirty, setProfileDirty] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [retryTick, setRetryTick] = useState(0);
  const retryTimer = useRef<number | null>(null);
  const [health, setHealth] = useState("Connecting");
  const [runtime, setRuntime] = useState<ExtensionRuntimeHealth | null>(null);
  const [native, setNative] = useState<NativeState>({ status: "checking" });
  const [cloud, setCloud] = useState<CloudState>({ status: "checking" });
  const [workspaceUrl, setWorkspaceUrl] = useState(defaultWorkspaceUrl);
  const [pairingBundle, setPairingBundle] = useState("");
  const [activationBundle, setActivationBundle] = useState("");
  const [pairing, setPairing] = useState(false);
  const [cloudSnapshot, setCloudSnapshot] = useState<CloudSnapshot | null>(null);
  const [answers, setAnswers] = useState<Record<string, AnswerDraft>>({});
  const [selectedResumeId, setSelectedResumeId] = useState("");
  const [filling, setFilling] = useState(false);
  const [notice, setNotice] = useState("");
  const [aiSettings, setAiSettings] = useState<AISettings>(defaultAISettings);
  const [apiKey, setApiKey] = useState("");
  const [aiModels, setAiModels] = useState<string[]>([]);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiMessage, setAiMessage] = useState("");

  const refreshAI = useCallback(async () => {
    try {
      setAiSettings(await getAISettings());
    } catch {
      // The updated native companion may not be installed yet.
    }
  }, []);

  const refresh = useCallback(async () => {
    const [activePage, savedProfile, extensionRuntime] = await Promise.all([
      getActivePage(), getProfile(), getHealth(),
    ]);
    setPage(activePage);
    if (savedProfile) setProfile(savedProfile);
    setProfileLoaded(true);
    setProfileDirty(false);
    setSaveState("idle");
    setHealth(extensionRuntime.status);
    setRuntime(extensionRuntime);

    setCloud({ status: "checking" });
    try {
      const connection = await getCloudConnection();
      if (!connection) {
        setCloud({ status: "disconnected" });
      } else {
        setWorkspaceUrl(connection.baseUrl);
        const cloudHealth = await getCloudHealth(connection);
        setCloud({ status: "connected", data: cloudHealth });
        if (cloudHealth.encryptionReady) {
          if (activePage) await publishApplicationSnapshot(connection, activePage);
          const snapshot = await getCloudSnapshot(connection);
          setCloudSnapshot(snapshot);
          if (snapshot.profile) setProfile(snapshot.profile);
          setSelectedResumeId((current) => current || snapshot.resumes[0]?.resumeId || "");
        } else {
          setCloudSnapshot(null);
        }
      }
    } catch (error) {
      setCloud({ status: "unavailable", error: error instanceof Error ? error.message : "Cloud unavailable" });
    }

    if (!extensionRuntime.capabilities.nativeMessaging) {
      setNative({ status: "unsupported" });
      return;
    }
    setNative({ status: "checking" });
    try {
      const nativeHealth = await getNativeHealth();
      setNative({ status: "healthy", data: nativeHealth });
      await refreshAI();
    } catch (error) {
      setNative({ status: "unavailable", error: error instanceof Error ? error.message : "Native companion is unavailable" });
    }
  }, [refreshAI]);

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setHealth("unavailable");
      setNotice(error instanceof Error ? error.message : "Unable to load MUNSHI Apply");
    });
    const listener = (message: { type?: string; payload?: ApplicationPage }) => {
      if (message.type === "ACTIVE_PAGE_UPDATED" && message.payload) setPage(message.payload);
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => {
      chrome.runtime.onMessage.removeListener(listener);
      if (retryTimer.current !== null) window.clearTimeout(retryTimer.current);
    };
  }, [refresh]);

  useEffect(() => {
    if (!profileLoaded || !profileDirty) return;
    setSaveState("editing");
    const timer = window.setTimeout(() => {
      setSaveState("saving");
      void saveProfile(profile)
        .then(() => {
          setProfileDirty(false);
          setSaveState(cloud.status === "connected" && cloud.data.encryptionReady ? "synced" : "local");
        })
        .catch(() => {
          setSaveState("error");
          retryTimer.current = window.setTimeout(() => setRetryTick((value) => value + 1), 5_000);
        });
    }, retryTick === 0 ? 800 : 0);
    return () => window.clearTimeout(timer);
  }, [cloud, profile, profileDirty, profileLoaded, retryTick]);

  useEffect(() => {
    if (!page) {
      setAnswers({});
      return;
    }
    const review = cloudSnapshot?.reviews.find((candidate: ApplicationReview) => candidate.pageId === page.pageId);
    const next = Object.fromEntries(page.questions.map((question) => {
      const approved = review?.answers.find((answer) => answer.questionId === question.questionId);
      const factKey = semanticFactKey[question.semanticType];
      const fact = factKey ? profile.facts.find((candidate) => candidate.key === factKey) : undefined;
      const suggested = fact && fact.trustLevel !== "UNKNOWN" && factKey ? valueOf(profile, factKey) : "";
      return [question.questionId, approved ?? { value: suggested, approved: Boolean(suggested) && !question.sensitive, sensitive: question.sensitive }];
    }));
    setAnswers(next);
    setSelectedResumeId((current) => {
      const reviewedResume = review?.resumeId;
      if (reviewedResume && cloudSnapshot?.resumes.some((resume) => resume.resumeId === reviewedResume)) return reviewedResume;
      if (current && cloudSnapshot?.resumes.some((resume) => resume.resumeId === current)) return current;
      return cloudSnapshot?.resumes[0]?.resumeId ?? "";
    });
  }, [cloudSnapshot, page, profile]);

  const reviewCount = useMemo(() => page?.questions.filter((question) => !answers[question.questionId]?.approved).length ?? 0, [answers, page]);
  const connectionLabel = health.toLowerCase() !== "healthy" ? "Unavailable" : native.status === "healthy" ? "Connected" : native.status === "checking" ? "Checking" : "Extension ready";
  const connectionClass = native.status === "healthy" || cloud.status === "connected" ? "healthy" : health.toLowerCase() === "healthy" ? "partial" : "unavailable";
  const saveLabel = saveState === "editing" ? "Editing…" : saveState === "saving" ? "Saving…" : saveState === "synced" ? "Encrypted & synced" : saveState === "local" ? "Saved locally" : saveState === "error" ? "Waiting to sync" : cloud.status === "connected" && cloud.data.encryptionReady ? "Auto-sync ready" : "Auto-save ready";

  function updateFact(key: string, value: string, confirmed: boolean): void {
    const definition = fieldDefinition(key);
    if (!definition) return;
    const timestamp = now();
    setProfile((current) => {
      const existing = current.facts.find((fact) => fact.key === key);
      const nextFact: ProfileFact = {
        factId: existing?.factId ?? crypto.randomUUID(), key, value,
        category: definition.category,
        trustLevel: value && confirmed ? "USER_CONFIRMED" : "UNKNOWN",
        source: "SIDE_PANEL", confirmedAt: value && confirmed ? timestamp : null,
        updatedAt: timestamp, protected: definition.protected,
      };
      return { ...current, updatedAt: timestamp, facts: [...current.facts.filter((fact) => fact.key !== key), nextFact] };
    });
    if (!definition.protected || confirmed) {
      setProfileDirty(true);
      setRetryTick(0);
    }
  }

  function confirmProtectedFact(key: string): void {
    if (!fieldDefinition(key)?.protected) return;
    updateFact(key, valueOf(profile, key), true);
  }

  async function syncNow(): Promise<void> {
    setSaveState("saving");
    try {
      await saveProfile(profile);
      setProfileDirty(false);
      setSaveState(cloud.status === "connected" && cloud.data.encryptionReady ? "synced" : "local");
    } catch (error) {
      setSaveState("error");
      setNotice(error instanceof Error ? error.message : "Profile sync failed");
    }
  }

  async function pairCloud(): Promise<void> {
    if (!runtime) return;
    setPairing(true);
    setNotice("");
    try {
      const connection = await enrollCloudDevice({ baseUrl: workspaceUrl, pairingBundle, platform: runtime.platform });
      setCloud({ status: "connected", data: await getCloudHealth(connection) });
      setPairingBundle("");
      setNotice("This Edge installation is paired with the private workspace.");
    } catch (error) {
      setCloud({ status: "unavailable", error: error instanceof Error ? error.message : "Pairing failed" });
    } finally {
      setPairing(false);
    }
  }

  async function unpairCloud(): Promise<void> {
    await disconnectCloud();
    setCloud({ status: "disconnected" });
    setNotice("Local cloud credential removed. Revoke the device in the workspace too.");
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
      setNotice(error instanceof Error ? error.message : "Encryption activation failed");
    } finally {
      setPairing(false);
    }
  }

  async function addResume(file: File | null): Promise<void> {
    if (!file) return;
    const connection = await getCloudConnection();
    if (!connection || cloud.status !== "connected" || !cloud.data.encryptionReady) {
      setNotice("Enable encrypted synchronization before adding a résumé.");
      return;
    }
    setPairing(true);
    try {
      const resume = await uploadEncryptedResume(connection, file);
      setSelectedResumeId(resume.resumeId);
      setNotice(`${resume.name} encrypted and synchronized.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Résumé upload failed");
    } finally {
      setPairing(false);
    }
  }

  async function fillApprovedFields(): Promise<void> {
    if (!page) return;
    const controls = new Map(page.controls.map((control) => [control.controlId, control]));
    const instructions: FillInstruction[] = page.questions.map((question) => {
      const answer = answers[question.questionId];
      const control = controls.get(question.controlId);
      if (!answer || !control || !answer.value.trim()) return null;
      return { controlId: question.controlId, frameId: control.frameId, value: answer.value, sensitive: question.sensitive, approved: answer.approved };
    }).filter((instruction): instruction is FillInstruction => instruction !== null);
    if (instructions.length === 0) {
      setNotice("No approved answers are ready to fill.");
      return;
    }
    setFilling(true);
    try {
      const connection = await getCloudConnection();
      if (connection && cloud.status === "connected" && cloud.data.encryptionReady) {
        const review: ApplicationReview = {
          reviewId: `review-${page.pageId}`, pageId: page.pageId,
          resumeId: selectedResumeId || null, approvedAt: now(),
          answers: page.questions.map((question) => {
            const answer = answers[question.questionId] ?? { value: "", approved: false, sensitive: question.sensitive };
            return { questionId: question.questionId, controlId: question.controlId, value: answer.value, approved: answer.approved, sensitive: question.sensitive };
          }),
        };
        await publishApplicationReview(connection, review);
      }
      const results = await applyFillPlan({ pageId: page.pageId, instructions });
      const filled = results.filter((result) => result.status === "FILLED").length;
      const skipped = results.length - filled;
      setNotice(`${filled} field${filled === 1 ? "" : "s"} filled and verified${skipped ? `; ${skipped} require manual interaction` : ""}. Final submission remains manual.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Verified fill failed");
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
      setAiMessage("API key stored in macOS Keychain. It is not stored in the extension or cloud sync.");
    } catch (error) {
      setAiMessage(error instanceof Error ? error.message : "Unable to store API key");
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
      setAiMessage(error instanceof Error ? error.message : "Unable to remove API key");
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
      setAiMessage(error instanceof Error ? error.message : "Unable to save AI controls");
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
      setAiMessage(`Connected to OpenAI. ${result.modelCount} models are visible to this key.`);
    } catch (error) {
      setAiMessage(error instanceof Error ? error.message : "OpenAI connection test failed");
    } finally {
      setAiBusy(false);
    }
  }

  return (
    <main>
      <header className="brand"><div><p className="eyebrow">Universal application intelligence</p><h1>MUNSHI Apply</h1></div><span className={`status ${connectionClass}`}>{connectionLabel}</span></header>
      <nav aria-label="MUNSHI Apply sections">{(["application", "profile", "diagnostics"] as const).map((item) => <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">{item}</button>)}</nav>
      {notice && <div className="notice">{notice}</div>}

      {view === "application" && <section>
        <div className="section-heading"><div><p className="eyebrow">Current application</p><h2>{page?.title || "No application detected"}</h2></div><button type="button" className="quiet" onClick={() => void refresh()}>Refresh</button></div>
        {page ? <><p className="url">{new URL(page.url).hostname}</p><div className="metrics"><article><strong>{page.controls.length}</strong><span>controls</span></article><article><strong>{page.questions.length}</strong><span>questions</span></article><article><strong>{reviewCount}</strong><span>review</span></article></div><h3>Pre-flight answers</h3><div className="answer-list">{page.questions.length === 0 && <p>No visible questions found on this page.</p>}{page.questions.map((question) => { const answer = answers[question.questionId] ?? { value: "", approved: false, sensitive: question.sensitive }; return <article className="answer-card" key={question.questionId}><div className="answer-heading"><div><strong>{question.rawText}</strong><span>{question.semanticType.replaceAll("_", " ")}</span></div><span className={question.sensitive ? "badge review" : "badge"}>{question.sensitive ? "sensitive" : `${Math.round(question.confidence * 100)}%`}</span></div><input type="text" value={answer.value} placeholder="Enter or confirm the answer" onChange={(event) => setAnswers((current) => ({ ...current, [question.questionId]: { ...answer, value: event.target.value, approved: false } }))} /><label className="answer-approval"><input type="checkbox" checked={answer.approved} disabled={!answer.value.trim()} onChange={(event) => setAnswers((current) => ({ ...current, [question.questionId]: { ...answer, approved: event.target.checked } }))} />Approved for this application</label></article>; })}</div>{cloudSnapshot?.resumes.length ? <label className="resume-select"><span>Résumé selected for this application</span><select value={selectedResumeId} onChange={(event) => setSelectedResumeId(event.target.value)}>{cloudSnapshot.resumes.map((resume) => <option key={resume.resumeId} value={resume.resumeId}>{resume.name}</option>)}</select><small>Browser security requires you to choose the file in the employer’s upload control manually.</small></label> : null}<button className="primary fill-button" type="button" disabled={filling || page.questions.length === 0} onClick={() => void fillApprovedFields()}>{filling ? "Filling and verifying…" : "Fill approved fields"}</button><div className="safety-callout"><strong>Guarded action</strong><span>Only approved answers are filled. CAPTCHA, MFA, file selection, and final submission stay manual.</span></div></> : <p>Open a browser-based application page. The universal scanner will map visible controls without changing the page.</p>}
      </section>}

      {view === "profile" && <section>
        <div className="section-heading"><div><p className="eyebrow">Encrypted profile vault</p><h2>Complete application profile</h2></div><span className={saveState === "error" ? "badge review" : "badge"}>{saveLabel}</span></div>
        <p>Regular facts save automatically after you stop typing. Protected facts become confirmed only after you leave the field, and are encrypted before cloud synchronization.</p>
        {profileSections.map((sectionName) => <div key={sectionName}><h3>{sectionName}</h3>{sectionName === "Optional voluntary demographics" && <p>Optional. MUNSHI never infers these answers and never uses an unconfirmed value.</p>}<div className="form-grid">{profileFields.filter((field) => field.section === sectionName).map((field) => <label key={field.key}><span>{field.label}{field.protected ? " · protected" : ""}</span><input type={field.inputType ?? "text"} value={valueOf(profile, field.key)} onChange={(event) => updateFact(field.key, event.target.value, !field.protected)} onBlur={() => field.protected && confirmProtectedFact(field.key)} /></label>)}</div></div>)}
        <div className="cloud-connection"><strong>{saveLabel}</strong><span>Profile autosave is enabled. Manual sync remains available as a fallback.</span><button className="quiet" type="button" onClick={() => void syncNow()}>Sync now</button></div>
        {cloud.status === "connected" && cloud.data.encryptionReady && <div className="resume-vault"><h3>Résumé vault</h3><label className="resume-upload"><span>{pairing ? "Uploading…" : "Add encrypted résumé"}</span><input type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={pairing} onChange={(event) => { void addResume(event.target.files?.[0] ?? null); event.currentTarget.value = ""; }} /></label><div className="resume-list">{cloudSnapshot?.resumes.map((resume) => <div key={resume.resumeId}><strong>{resume.name}</strong><span>{Math.ceil(resume.sizeBytes / 1024)} KB · encrypted</span></div>)}</div></div>}
      </section>}

      {view === "diagnostics" && <section>
        <p className="eyebrow">Runtime diagnostics</p><h2>Foundation health</h2>
        <dl className="diagnostics"><div><dt>Extension runtime</dt><dd>{health}</dd></div><div><dt>Device platform</dt><dd>{runtime?.platform ?? "checking"}</dd></div><div><dt>Native companion</dt><dd>{native.status}</dd></div><div><dt>SQLite database</dt><dd>{native.status === "healthy" ? native.data.database : native.status === "unsupported" ? "cloud path required" : native.status}</dd></div><div><dt>Schema version</dt><dd>{native.status === "healthy" ? native.data.schema_version : "not available"}</dd></div><div><dt>Outbox pending</dt><dd>{native.status === "healthy" ? (native.data.outbox.PENDING ?? 0) : "not available"}</dd></div><div><dt>Universal scanner</dt><dd>{page ? "active" : "waiting"}</dd></div><div><dt>Profile vault</dt><dd>{profile.facts.filter((fact) => fact.trustLevel !== "UNKNOWN").length} confirmed facts</dd></div><div><dt>Profile sync</dt><dd>{saveLabel}</dd></div><div><dt>Automation</dt><dd>guarded fill</dd></div><div><dt>AI provider</dt><dd>{aiSettings.keyConfigured ? `OpenAI · ${aiSettings.enabled ? "enabled" : "configured"}` : "not configured"}</dd></div><div><dt>Cloud synchronization</dt><dd>{cloud.status === "connected" ? cloud.data.encryptionReady ? "encrypted" : "paired only" : cloud.status}</dd></div></dl>
        {native.status === "unavailable" && <p className="diagnostic-error">Native connection failed: {native.error}</p>}{cloud.status === "unavailable" && <p className="diagnostic-error">Cloud connection failed: {cloud.error}</p>}
        {cloud.status === "connected" ? <div className="cloud-connection"><strong>Private workspace paired</strong><span>{new URL(cloud.data.baseUrl).hostname}</span>{cloud.data.encryptionReady ? <span className="encryption-active">End-to-end encrypted synchronization active</span> : <div className="encryption-upgrade"><strong>Enable encrypted synchronization</strong><p>Create a new one-time code in the updated private workspace, paste it below, then activate encryption. Your existing pairing remains intact.</p><textarea rows={4} value={activationBundle} onChange={(event) => setActivationBundle(event.target.value)} placeholder="Paste the new one-time code" /><button className="primary" type="button" disabled={pairing || !activationBundle.trim()} onClick={() => void enableEncryptedSync()}>{pairing ? "Activating…" : "Activate encrypted sync"}</button></div>}<button type="button" className="quiet" onClick={() => void chrome.tabs.create({ url: cloud.data.baseUrl + "/workspace" })}>Open private workspace</button><button type="button" className="quiet" onClick={() => void unpairCloud()}>Remove local pairing</button></div> : <div className="cloud-pairing"><h3>Pair this Edge installation</h3><p>Sign in to the private mobile workspace, create a one-time bundle, and paste it here. The bundle expires after 10 minutes.</p><label><span>Private workspace URL</span><input type="url" value={workspaceUrl} onChange={(event) => setWorkspaceUrl(event.target.value)} /></label><label><span>One-time pairing bundle</span><textarea rows={4} value={pairingBundle} onChange={(event) => setPairingBundle(event.target.value)} placeholder={'{"challengeId":"…","secret":"…"}'} /></label><button className="primary" type="button" disabled={pairing || !pairingBundle.trim()} onClick={() => void pairCloud()}>{pairing ? "Pairing…" : "Pair device"}</button></div>}

        <div className="cloud-pairing"><h3>AI & API control center</h3><p>The OpenAI API key is stored only in macOS Keychain by the native companion. It is never written to GitHub, browser storage, profile sync, or cloud workspace data.</p>{native.status === "healthy" ? <><label><span>OpenAI API key · {aiSettings.keyConfigured ? `configured (${aiSettings.keySource})` : "not configured"}</span><input type="password" autoComplete="off" value={apiKey} placeholder="Paste your OpenAI API key" onChange={(event) => setApiKey(event.target.value)} /></label><button className="primary" type="button" disabled={aiBusy || !apiKey.trim()} onClick={() => void storeApiKey()}>Store key in macOS Keychain</button><button className="quiet" type="button" disabled={aiBusy || !aiSettings.keyConfigured} onClick={() => void removeApiKey()}>Delete stored key</button><label><span>Selected model</span><input type="text" list="munshi-openai-models" value={aiSettings.model} placeholder="Test connection, then choose a model" onChange={(event) => setAiSettings((current) => ({ ...current, model: event.target.value }))} /><datalist id="munshi-openai-models">{aiModels.map((model) => <option key={model} value={model} />)}</datalist></label><label><span>Monthly budget in USD (0 means no paid usage approved)</span><input type="number" min="0" step="1" value={aiSettings.monthlyBudgetUsd} onChange={(event) => setAiSettings((current) => ({ ...current, monthlyBudgetUsd: Number(event.target.value) }))} /></label><label><span>Warning threshold in USD</span><input type="number" min="0" step="1" value={aiSettings.warningBudgetUsd} onChange={(event) => setAiSettings((current) => ({ ...current, warningBudgetUsd: Number(event.target.value) }))} /></label><button className="quiet" type="button" onClick={() => setAiSettings((current) => ({ ...current, enabled: !current.enabled }))}>AI features: {aiSettings.enabled ? "Enabled" : "Disabled"}</button><button className="quiet" type="button" onClick={() => setAiSettings((current) => ({ ...current, hardStop: !current.hardStop }))}>Hard budget stop: {aiSettings.hardStop ? "On" : "Off"}</button><button className="quiet" type="button" disabled={aiBusy || !aiSettings.keyConfigured} onClick={() => void testAI()}>Test connection & load models</button><button className="primary" type="button" disabled={aiBusy} onClick={() => void persistAISettings()}>Save AI controls</button>{aiMessage && <span>{aiMessage}</span>}<div className="safety-callout"><strong>Generation remains gated</strong><span>Connecting OpenAI does not authorize MUNSHI to invent application answers. Evidence retrieval, contradiction checks, and budget enforcement remain required before generated answers can be used.</span></div></> : <span>Install the updated native companion before managing API credentials.</span>}</div>
      </section>}
    </main>
  );
}
