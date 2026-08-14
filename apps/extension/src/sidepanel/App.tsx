import type {
  ApplicationPage,
  FillInstruction,
  MasterProfile,
  ProfileFact,
} from "@munshi-apply/contracts";
import { useCallback, useEffect, useMemo, useState } from "react";
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

const starterFacts: readonly Pick<
  ProfileFact,
  "key" | "category" | "protected"
>[] = [
  { key: "legal_name", category: "IDENTITY", protected: true },
  { key: "email", category: "CONTACT", protected: false },
  { key: "phone", category: "CONTACT", protected: false },
  { key: "linkedin", category: "CONTACT", protected: false },
  { key: "portfolio", category: "CONTACT", protected: false },
  {
    key: "work_authorization",
    category: "WORK_AUTHORIZATION",
    protected: true,
  },
  { key: "future_sponsorship", category: "SPONSORSHIP", protected: true },
];

function valueOf(profile: MasterProfile, key: string): string {
  const value = profile.facts.find((fact) => fact.key === key)?.value;
  return typeof value === "string" ? value : "";
}

type AnswerDraft = {
  value: string;
  approved: boolean;
  sensitive: boolean;
};

const semanticFactKey: Readonly<Record<string, string>> = {
  PERSONAL: "legal_name",
  EMAIL: "email",
  PHONE: "phone",
  LINKEDIN: "linkedin",
  PORTFOLIO: "portfolio",
  WEBSITE: "portfolio",
  WORK_AUTHORIZATION_CURRENT: "work_authorization",
  SPONSORSHIP_CURRENT: "work_authorization",
  SPONSORSHIP_FUTURE: "future_sponsorship",
};

export function App() {
  const [view, setView] = useState<View>("application");
  const [page, setPage] = useState<ApplicationPage | null>(null);
  const [profile, setProfile] = useState<MasterProfile>(emptyProfile);
  const [health, setHealth] = useState("Connecting");
  const [runtime, setRuntime] = useState<ExtensionRuntimeHealth | null>(null);
  const [native, setNative] = useState<NativeState>({ status: "checking" });
  const [cloud, setCloud] = useState<CloudState>({ status: "checking" });
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

  const refresh = useCallback(async () => {
    const [activePage, savedProfile, runtime] = await Promise.all([
      getActivePage(),
      getProfile(),
      getHealth(),
    ]);
    setPage(activePage);
    if (savedProfile) setProfile(savedProfile);
    setHealth(runtime.status);
    setRuntime(runtime);

    setCloud({ status: "checking" });
    try {
      const connection = await getCloudConnection();
      if (!connection) {
        setCloud({ status: "disconnected" });
      } else {
        setWorkspaceUrl(connection.baseUrl);
        const cloudHealth = await getCloudHealth(connection);
        setCloud({
          status: "connected",
          data: cloudHealth,
        });
        if (cloudHealth.encryptionReady) {
          if (activePage) {
            await publishApplicationSnapshot(connection, activePage);
          }
          const snapshot = await getCloudSnapshot(connection);
          setCloudSnapshot(snapshot);
          if (snapshot.profile) setProfile(snapshot.profile);
          setSelectedResumeId(
            (current) => current || snapshot.resumes[0]?.resumeId || "",
          );
        } else {
          setCloudSnapshot(null);
        }
      }
    } catch (error) {
      setCloud({
        status: "unavailable",
        error: error instanceof Error ? error.message : "Cloud unavailable",
      });
    }

    if (!runtime.capabilities.nativeMessaging) {
      setNative({ status: "unsupported" });
      return;
    }

    setNative({ status: "checking" });
    try {
      const nativeHealth = await getNativeHealth();
      setNative({ status: "healthy", data: nativeHealth });
    } catch (error) {
      setNative({
        status: "unavailable",
        error:
          error instanceof Error
            ? error.message
            : "Native companion is unavailable",
      });
    }
  }, []);

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setHealth("unavailable");
      setNotice(
        error instanceof Error ? error.message : "Unable to load MUNSHI Apply",
      );
    });
    const listener = (message: {
      type?: string;
      payload?: ApplicationPage;
    }) => {
      if (message.type === "ACTIVE_PAGE_UPDATED" && message.payload) {
        setPage(message.payload);
      }
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => chrome.runtime.onMessage.removeListener(listener);
  }, [refresh]);

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
        const factKey = semanticFactKey[question.semanticType];
        const suggested = factKey ? valueOf(profile, factKey) : "";
        return [
          question.questionId,
          approved ?? {
            value: suggested,
            approved: Boolean(suggested) && !question.sensitive,
            sensitive: question.sensitive,
          },
        ];
      }),
    );
    setAnswers(next);
    setSelectedResumeId((current) => {
      const reviewedResume = review?.resumeId;
      if (
        reviewedResume &&
        cloudSnapshot?.resumes.some(
          (resume) => resume.resumeId === reviewedResume,
        )
      ) {
        return reviewedResume;
      }
      if (
        current &&
        cloudSnapshot?.resumes.some((resume) => resume.resumeId === current)
      ) {
        return current;
      }
      return cloudSnapshot?.resumes[0]?.resumeId ?? "";
    });
  }, [cloudSnapshot, page, profile]);

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
      : cloud.status === "connected" && runtime?.mobile
        ? "Cloud connected"
        : native.status === "healthy"
          ? "Connected"
          : native.status === "checking"
            ? "Checking"
            : runtime?.mobile
              ? "Cloud required"
              : "Extension ready";

  const connectionClass =
    native.status === "healthy" || cloud.status === "connected"
      ? "healthy"
      : health.toLowerCase() === "healthy"
        ? "partial"
        : "unavailable";

  function updateFact(key: string, value: string): void {
    const definition = starterFacts.find((item) => item.key === key);
    if (!definition) return;
    const timestamp = now();
    const existing = profile.facts.find((fact) => fact.key === key);
    const nextFact: ProfileFact = {
      factId: existing?.factId ?? crypto.randomUUID(),
      key,
      value,
      category: definition.category,
      trustLevel: value ? "USER_CONFIRMED" : "UNKNOWN",
      source: "SIDE_PANEL",
      confirmedAt: value ? timestamp : null,
      updatedAt: timestamp,
      protected: definition.protected,
    };
    setProfile((current) => ({
      ...current,
      updatedAt: timestamp,
      facts: [...current.facts.filter((fact) => fact.key !== key), nextFact],
    }));
  }

  async function persistProfile(): Promise<void> {
    try {
      await saveProfile(profile);
      setNotice(
        cloud.status === "connected" && cloud.data.encryptionReady
          ? "Profile encrypted and synchronized."
          : "Profile saved locally.",
      );
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Profile save failed");
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

  async function addResume(file: File | null): Promise<void> {
    if (!file) return;
    const connection = await getCloudConnection();
    if (
      !connection ||
      cloud.status !== "connected" ||
      !cloud.data.encryptionReady
    ) {
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
      setNotice(
        error instanceof Error ? error.message : "Résumé upload failed",
      );
    } finally {
      setPairing(false);
    }
  }

  async function fillApprovedFields(): Promise<void> {
    if (!page) return;
    const controls = new Map(
      page.controls.map((control) => [control.controlId, control]),
    );
    const instructions: FillInstruction[] = page.questions
      .map((question) => {
        const answer = answers[question.questionId];
        const control = controls.get(question.controlId);
        if (!answer || !control || !answer.value.trim()) return null;
        return {
          controlId: question.controlId,
          frameId: control.frameId,
          value: answer.value,
          sensitive: question.sensitive,
          approved: answer.approved,
        };
      })
      .filter(
        (instruction): instruction is FillInstruction => instruction !== null,
      );
    if (instructions.length === 0) {
      setNotice("No approved answers are ready to fill.");
      return;
    }
    setFilling(true);
    try {
      const connection = await getCloudConnection();
      if (
        connection &&
        cloud.status === "connected" &&
        cloud.data.encryptionReady
      ) {
        const review: ApplicationReview = {
          reviewId: `review-${page.pageId}`,
          pageId: page.pageId,
          resumeId: selectedResumeId || null,
          approvedAt: now(),
          answers: page.questions.map((question) => {
            const answer = answers[question.questionId] ?? {
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
      const results = await applyFillPlan({
        pageId: page.pageId,
        instructions,
      });
      const filled = results.filter(
        (result) => result.status === "FILLED",
      ).length;
      const skipped = results.length - filled;
      setNotice(
        `${filled} field${filled === 1 ? "" : "s"} filled and verified${skipped ? `; ${skipped} require manual interaction` : ""}. Final submission remains manual.`,
      );
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Verified fill failed",
      );
    } finally {
      setFilling(false);
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
        {(["application", "profile", "diagnostics"] as const).map((item) => (
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
                              },
                            }))
                          }
                        />
                        Approved for this application
                      </label>
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
                        {resume.name}
                      </option>
                    ))}
                  </select>
                  <small>
                    Browser security requires you to choose the file in the
                    employer’s upload control manually.
                  </small>
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

      {view === "profile" && (
        <section>
          <p className="eyebrow">Encrypted profile vault</p>
          <h2>Verified application facts</h2>
          <p>
            Protected answers are never inferred. When encrypted sync is active,
            confirmed facts are available on your iPhone and paired Edge
            installation.
          </p>
          <div className="form-grid">
            {starterFacts.map((fact) => (
              <label key={fact.key}>
                <span>
                  {fact.key.replaceAll("_", " ")}
                  {fact.protected ? " · protected" : ""}
                </span>
                <input
                  type="text"
                  value={valueOf(profile, fact.key)}
                  onChange={(event) => updateFact(fact.key, event.target.value)}
                />
              </label>
            ))}
          </div>
          <button
            className="primary"
            type="button"
            onClick={() => void persistProfile()}
          >
            {cloud.status === "connected" && cloud.data.encryptionReady
              ? "Encrypt and synchronize"
              : "Save locally"}
          </button>
          {cloud.status === "connected" && cloud.data.encryptionReady && (
            <div className="resume-vault">
              <h3>Résumé vault</h3>
              <label className="resume-upload">
                <span>{pairing ? "Uploading…" : "Add encrypted résumé"}</span>
                <input
                  type="file"
                  accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  disabled={pairing}
                  onChange={(event) => {
                    void addResume(event.target.files?.[0] ?? null);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              <div className="resume-list">
                {cloudSnapshot?.resumes.map((resume) => (
                  <div key={resume.resumeId}>
                    <strong>{resume.name}</strong>
                    <span>
                      {Math.ceil(resume.sizeBytes / 1024)} KB · encrypted
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
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
              <dd>{profile.facts.length} facts</dd>
            </div>
            <div>
              <dt>Automation</dt>
              <dd>guarded fill</dd>
            </div>
            <div>
              <dt>AI provider</dt>
              <dd>not configured</dd>
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
          </dl>
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
        </section>
      )}
    </main>
  );
}
