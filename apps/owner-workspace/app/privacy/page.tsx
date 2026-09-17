import Link from "next/link";

export default function PrivacyPage() {
  return (
    <main className="legal-shell">
      <header className="legal-header">
        <Link className="brand-lockup" href="/" aria-label="MUNSHI Apply home">
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          <span>
            <strong>MUNSHI Apply</strong>
            <small>Privacy policy</small>
          </span>
        </Link>
        <Link className="button secondary" href="/">
          Return home
        </Link>
      </header>

      <article className="legal-content">
        <p className="eyebrow">Effective August 14, 2026</p>
        <h1>Privacy is part of the workflow, not an afterthought.</h1>
        <p className="legal-lead">
          MUNSHI Apply is a private, owner-controlled job-application workspace. This policy
          explains the data the extension and workspace use, why they use it, and the controls
          that must exist before real private data is synchronized.
        </p>

        <section>
          <h2>Data MUNSHI may process</h2>
          <ul>
            <li>
              Application-page context, including page URLs, visible question labels, control
              structure, and validation state needed to understand a legitimate application.
            </li>
            <li>
              Owner-confirmed profile facts, protected answers, selected résumé versions,
              evidence records, application state, and review decisions.
            </li>
            <li>
              Résumé and evidence files that the owner deliberately adds to the encrypted vault.
            </li>
            <li>
              Device enrollment records, public device keys, hashed device credentials, sync
              event identifiers, checksums, conflict records, and bounded operational diagnostics.
            </li>
            <li>
              The signed-in owner email supplied by ChatGPT authentication to isolate the private
              workspace.
            </li>
          </ul>
        </section>

        <section>
          <h2>Data MUNSHI does not collect</h2>
          <p>
            MUNSHI does not ask for or store passwords, MFA codes, OTPs, CAPTCHA solutions,
            identity-verification secrets, payment-card data, or employer account credentials. It
            pauses for those user-controlled security checkpoints.
          </p>
        </section>

        <section>
          <h2>How data is used</h2>
          <p>
            Data is used only to understand application questions, present one pre-flight review,
            prepare owner-approved answers and documents, synchronize checkpoints, detect
            conflicts, verify supported interactions, and recover the owner-controlled workspace.
            MUNSHI
            does not sell personal data, run advertising, or use application data for unrelated
            profiling.
          </p>
        </section>

        <section>
          <h2>Storage and encryption</h2>
          <p>
            The Mac companion uses a private SQLite journal outside the source repository. The
            cloud control plane stores structured ownership and sync metadata separately from file
            bytes. Résumé, evidence, and protected-fact payloads must be encrypted by the client
            before cloud storage. The server stores ciphertext, wrapped keys, checksums, and the
            minimum metadata needed for integrity and recovery.
          </p>
          <p>
            The current release is a foundation candidate. Real résumés and protected facts must
            not be migrated until authenticated storage, device revocation, encryption-key
            recovery, backup, restore, and physical-iPhone tests pass.
          </p>
        </section>

        <section>
          <h2>Sharing and external providers</h2>
          <p>
            MUNSHI does not send private application content to AI providers by default. AI and
            optional orchestration providers are not configured in the foundation release. A new
            provider may be enabled only after the owner reviews its purpose, data boundary, and
            cost. Hosting providers process encrypted or operational data only to deliver the
            private workspace.
          </p>
        </section>

        <section>
          <h2>Owner controls and retention</h2>
          <p>
            The owner can revoke a paired device and remove its local credential. Application
            history and protected facts are versioned so consequential changes are not silently
            overwritten. The functional release must include an owner-confirmed workspace deletion
            path that removes cloud metadata and encrypted objects. Until that path passes its
            recovery and deletion tests, real private data remains blocked from migration.
          </p>
        </section>

        <section>
          <h2>Security and final submission</h2>
          <p>
            MUNSHI does not bypass CAPTCHA, MFA, OTP, identity verification, authentication, or
            anti-abuse controls. It requires deliberate owner approval before final application
            submission and does not silently change protected facts.
          </p>
        </section>

        <section>
          <h2>Questions and updates</h2>
          <p>
            Use the <Link href="/support">MUNSHI Apply support page</Link> for current
            troubleshooting, release status, and privacy requests. Material policy changes must be
            published before the related feature begins processing real data.
          </p>
        </section>
      </article>
    </main>
  );
}
