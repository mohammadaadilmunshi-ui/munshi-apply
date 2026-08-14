import type {
  ApplicationPage,
  MasterProfile,
  ProfileFact,
} from "@munshi-apply/contracts";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getActivePage,
  getHealth,
  getNativeHealth,
  getProfile,
  saveProfile,
  type ExtensionRuntimeHealth,
  type NativeRuntimeHealth,
} from "../messaging/client";
import {
  disconnectCloud,
  enrollCloudDevice,
  getCloudConnection,
  getCloudHealth,
  type CloudHealth,
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
  const [pairing, setPairing] = useState(false);
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
        setCloud({
          status: "connected",
          data: await getCloudHealth(connection),
        });
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

  const reviewCount = useMemo(
    () =>
      page?.questions.filter((question) => question.requiresReview).length ?? 0,
    [page],
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
    await saveProfile(profile);
    setNotice(
      cloud.status === "connected"
        ? "Profile saved to this device. Encrypted profile sync is not enabled yet."
        : "Profile saved to this device.",
    );
    window.setTimeout(() => setNotice(""), 2500);
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
              <h3>Question map</h3>
              <div className="question-list">
                {page.questions.length === 0 && (
                  <p>No visible questions found on this page.</p>
                )}
                {page.questions.map((question) => (
                  <article className="question" key={question.questionId}>
                    <div>
                      <strong>{question.rawText}</strong>
                      <span>{question.semanticType.replaceAll("_", " ")}</span>
                    </div>
                    <span
                      className={
                        question.requiresReview ? "badge review" : "badge"
                      }
                    >
                      {question.requiresReview
                        ? "review"
                        : `${Math.round(question.confidence * 100)}%`}
                    </span>
                  </article>
                ))}
              </div>
              <div className="safety-callout">
                <strong>Observe mode</strong>
                <span>Nothing is filled or submitted in this milestone.</span>
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
          <p className="eyebrow">Local profile vault</p>
          <h2>Verified application facts</h2>
          <p>Protected answers are stored locally and are never inferred.</p>
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
            Save locally
          </button>
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
              <dd>observe only</dd>
            </div>
            <div>
              <dt>AI provider</dt>
              <dd>not configured</dd>
            </div>
            <div>
              <dt>Cloud synchronization</dt>
              <dd>{cloud.status}</dd>
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
