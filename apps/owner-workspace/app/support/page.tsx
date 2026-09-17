import Link from "next/link";

const checks = [
  {
    title: "No application detected",
    detail:
      "Open a normal HTTPS application page in a separate Edge tab. The MUNSHI interface itself is not an employer application page.",
  },
  {
    title: "Extension ready, native unavailable",
    detail:
      "On Mac, reload the unpacked extension after installation and verify the exact extension ID in the Native Messaging manifest. On iPhone, the native companion is intentionally unsupported; use cloud pairing.",
  },
  {
    title: "Cloud pairing failed",
    detail:
      "Install or reload the latest MUNSHI Apply extension first. Then open MUNSHI Apply → Diagnostics → Pair this Edge installation. Create a new one-time pairing code in the owner workspace, paste it only into that Diagnostics field, and choose Pair device within 10 minutes. A used or expired code cannot be reused.",
  },
  {
    title: "Security checkpoint shown",
    detail:
      "Complete CAPTCHA, MFA, OTP, identity verification, or authentication yourself. MUNSHI must remain paused until the page confirms success.",
  },
];

export default function SupportPage() {
  return (
    <main className="legal-shell">
      <header className="legal-header">
        <Link className="brand-lockup" href="/" aria-label="MUNSHI Apply home">
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          <span>
            <strong>MUNSHI Apply</strong>
            <small>Support</small>
          </span>
        </Link>
        <Link className="button secondary" href="/">
          Return home
        </Link>
      </header>

      <article className="legal-content support-content">
        <p className="eyebrow">Private release support</p>
        <h1>Start with the status that is actually failing.</h1>
        <p className="legal-lead">
          Diagnostics separate the Edge extension, Mac native companion, SQLite journal, scanner,
          and cloud workspace. “Extension ready” does not claim that every other component is
          connected.
        </p>

        <div className="support-grid">
          {checks.map((check) => (
            <section key={check.title}>
              <h2>{check.title}</h2>
              <p>{check.detail}</p>
            </section>
          ))}
        </div>

        <section className="support-boundary">
          <h2>Current release boundary</h2>
          <p>
            Desktop observation, Mac native health, local SQLite integrity, verified backup,
            separate desktop/mobile builds, and the private mobile workspace foundation are
            available. Full iPhone autofill, encrypted profile/résumé convergence, pre-flight,
            verified fill, and final-submit review remain gated until their release tests pass.
          </p>
        </section>

        <section>
          <h2>Privacy or deletion request</h2>
          <p>
            Do not send résumés, protected facts, credentials, recovery phrases, pairing bundles,
            or diagnostic exports through an unverified support channel. The private owner
            workspace will expose device revocation and workspace-deletion controls before real
            cloud data migration is enabled.
          </p>
          <p>
            Review the current <Link href="/privacy">privacy policy</Link> before connecting a
            device or enabling a new provider.
          </p>
        </section>
      </article>
    </main>
  );
}
