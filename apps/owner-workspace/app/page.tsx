const workflow = [
  {
    number: "01",
    title: "Understand the application",
    detail:
      "Map visible questions and required documents without changing the employer page.",
    state: "Available on desktop",
  },
  {
    number: "02",
    title: "Resolve every open question",
    detail:
      "Collect unresolved and protected answers in one pre-flight review.",
    state: "Available on phone",
  },
  {
    number: "03",
    title: "Fill and verify",
    detail:
      "Apply confirmed answers, select the approved résumé, and verify every action.",
    state: "Guarded",
  },
  {
    number: "04",
    title: "Approve the final step",
    detail:
      "Pause for your deliberate approval before any application is submitted.",
    state: "Always manual",
  },
];

const systems = [
  { label: "Mac native companion", value: "Verified", tone: "good" },
  { label: "Local SQLite ledger", value: "Healthy", tone: "good" },
  { label: "iPhone workspace", value: "Encrypted workspace", tone: "good" },
  { label: "Cloud synchronization", value: "Connected", tone: "good" },
];

export default async function Home() {
  const user = await getChatGPTUser();

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand-lockup" href="#top" aria-label="MUNSHI Apply home">
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          <span>
            <strong>MUNSHI Apply</strong>
            <small>Private application workspace</small>
          </span>
        </a>
        {user ? (
          <a className="privacy-pill" href={chatGPTSignOutPath("/")}>
            <i aria-hidden="true" /> {user.displayName}
          </a>
        ) : (
          <a className="privacy-pill" href={chatGPTSignInPath("/")}>
            <i aria-hidden="true" /> Owner sign in
          </a>
        )}
      </header>

      <div id="top" className="content">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">Cross-device application intelligence</p>
            <h1 id="hero-title">
              Continue the right application from any device.
            </h1>
            <p className="hero-summary">
              Review facts, choose the correct résumé, resolve open questions,
              and keep every application checkpoint visible before MUNSHI takes
              action.
            </p>
            <div className="hero-actions">
              <a
                className="button primary"
                href={user ? "/workspace" : chatGPTSignInPath("/workspace")}
              >
                {user ? "Open private workspace" : "Sign in to continue"}
              </a>
              <a className="button secondary" href="#systems">
                Check system status
              </a>
            </div>
          </div>

          <aside className="readiness-card" aria-label="Current readiness">
            <div className="readiness-heading">
              <span>Current release</span>
              <strong>Cross-device vault</strong>
            </div>
            <div className="readiness-score">
              <span>Desktop runtime</span>
              <strong>Verified</strong>
            </div>
            <div className="readiness-line">
              <span />
            </div>
            <dl>
              <div>
                <dt>Extension</dt>
                <dd>Guarded fill</dd>
              </div>
              <div>
                <dt>Phone</dt>
                <dd>Profile, résumés, reviews</dd>
              </div>
              <div>
                <dt>Final submit</dt>
                <dd>Your approval</dd>
              </div>
            </dl>
          </aside>
        </section>

        {user ? (
          <WorkspacePanel ownerName={user.displayName} />
        ) : (
          <section
            id="workspace"
            className="section-block locked-workspace"
            aria-labelledby="workspace-title"
          >
            <p className="eyebrow">Private by default</p>
            <h2 id="workspace-title">
              Your synchronized workspace requires owner sign-in.
            </h2>
            <p>
              Sign in before MUNSHI creates a cloud workspace, pairing
              challenge, or encrypted storage record. Résumés and protected
              facts are encrypted in your browser before cloud storage.
            </p>
            <a className="button primary" href={chatGPTSignInPath("/")}>
              Sign in with ChatGPT
            </a>
          </section>
        )}

        <section className="principles" aria-label="Safety guarantees">
          <article>
            <span className="principle-icon" aria-hidden="true">
              ✓
            </span>
            <div>
              <strong>Evidence first</strong>
              <p>Answers must trace back to confirmed facts.</p>
            </div>
          </article>
          <article>
            <span className="principle-icon" aria-hidden="true">
              ↺
            </span>
            <div>
              <strong>Recoverable</strong>
              <p>Every meaningful step gets a checkpoint.</p>
            </div>
          </article>
          <article>
            <span className="principle-icon" aria-hidden="true">
              ◉
            </span>
            <div>
              <strong>You stay in control</strong>
              <p>Security checks and submission remain yours.</p>
            </div>
          </article>
        </section>

        <section
          id="workflow"
          className="section-block"
          aria-labelledby="workflow-title"
        >
          <div className="section-heading">
            <div>
              <p className="eyebrow">One clear operating loop</p>
              <h2 id="workflow-title">
                From application page to final approval
              </h2>
            </div>
            <p>
              Questions are collected before action, not discovered halfway
              through filling.
            </p>
          </div>

          <div className="workflow-grid">
            {workflow.map((step) => (
              <article className="workflow-card" key={step.number}>
                <div className="workflow-topline">
                  <span className="step-number">{step.number}</span>
                  <span className="step-state">{step.state}</span>
                </div>
                <h3>{step.title}</h3>
                <p>{step.detail}</p>
              </article>
            ))}
          </div>
        </section>

        <section
          id="systems"
          className="section-block systems-block"
          aria-labelledby="systems-title"
        >
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Verified status</p>
              <h2 id="systems-title">What is working right now</h2>
            </div>
            <span className="last-check">Checked August 14, 2026</span>
          </div>

          <div className="system-list">
            {systems.map((system) => (
              <div className="system-row" key={system.label}>
                <span>{system.label}</span>
                <strong className={system.tone}>
                  <i aria-hidden="true" />
                  {system.value}
                </strong>
              </div>
            ))}
          </div>
          <p className="status-note">
            The iPhone workspace can manage encrypted profile facts, résumés,
            and application reviews while the Mac is off. Employer-page filling
            runs through the paired desktop Edge extension; final submission is
            always manual.
          </p>
        </section>
      </div>

      <nav className="mobile-nav" aria-label="Primary navigation">
        <a className="active" href="#top">
          <span aria-hidden="true">⌂</span>Home
        </a>
        <a href="/workspace">
          <span aria-hidden="true">◎</span>Workspace
        </a>
        <a href="#systems">
          <span aria-hidden="true">◌</span>Status
        </a>
      </nav>

      <footer className="site-footer">
        <span>MUNSHI Apply · Private cross-device workspace</span>
        <div>
          <a href="/privacy">Privacy</a>
          <a href="/support">Support</a>
        </div>
      </footer>
    </main>
  );
}
import {
  chatGPTSignInPath,
  chatGPTSignOutPath,
  getChatGPTUser,
} from "./chatgpt-auth";
import { WorkspacePanel } from "./workspace-panel";
