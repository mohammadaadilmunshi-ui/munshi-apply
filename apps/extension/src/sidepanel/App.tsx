import type {
  ApplicationPage,
  MasterProfile,
  ProfileFact,
} from "@munshi-apply/contracts";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getActivePage,
  getHealth,
  getProfile,
  saveProfile,
} from "../messaging/client";

type View = "application" | "profile" | "diagnostics";

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
    setNotice("Profile saved locally.");
    window.setTimeout(() => setNotice(""), 2500);
  }

  return (
    <main>
      <header className="brand">
        <div>
          <p className="eyebrow">Universal application intelligence</p>
          <h1>MUNSHI Apply</h1>
        </div>
        <span className={`status ${health}`}>{health}</span>
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
              <dt>Native host</dt>
              <dd>optional, not connected</dd>
            </div>
          </dl>
        </section>
      )}
    </main>
  );
}
