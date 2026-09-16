import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  accountPreflightItem,
  buildAccountOrchestrationPlan,
  type AccountRecord,
} from "./account-orchestration";

function page(overrides: Partial<ApplicationPage> = {}): ApplicationPage {
  return {
    pageId: "page-account-auto",
    tabId: 1,
    frameId: 0,
    documentId: "doc-account-auto",
    url: "https://example.com/candidate/login",
    title: "Candidate account",
    pageContext: "Sign in",
    observedAt: "2026-09-16T12:00:00.000Z",
    controls: [],
    questions: [],
    applicationState: "AUTH",
    pageFingerprint: "fingerprint",
    securityCheckpoint: "AUTHENTICATION",
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    ...overrides,
  };
}

function account(): AccountRecord {
  return {
    accountId: "account-1",
    employer: "Example",
    domain: "example.com",
    scopeKey: "example.com",
    portalUrl: "https://example.com/candidate/login",
    email: "u_abcdefghijklmnop@mail.munshi.systems",
    exists: true,
    createdAt: "2026-09-16T11:00:00.000Z",
    lastUsed: "2026-09-16T11:30:00.000Z",
    applicationIds: ["application-1"],
  };
}

describe("capability-gated account automation", () => {
  it("reuses an existing exact-scope account with a privileged password resolver", () => {
    const plan = buildAccountOrchestrationPlan({
      page: page(),
      knownAccounts: [account()],
      preferredEmail: "u_abcdefghijklmnop@mail.munshi.systems",
      capabilities: { secureCredentialResolver: true },
    });
    expect(plan.canAutoAct).toBe(true);
    expect(plan.actions).toEqual([
      "USE_EXISTING_ACCOUNT",
      "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
      "AUTHENTICATE_ACCOUNT",
      "CONTINUE_EXACT_APPLICATION",
    ]);
    expect(accountPreflightItem(plan).state).toBe("READY");
  });

  it("creates a new account only when identity, mail, and credential capabilities are all proven", () => {
    const registration = page({
      url: "https://example.com/candidate/register",
      applicationState: "ACCOUNT_CREATE",
      securityCheckpoint: "AUTHENTICATION",
      pageContext: "Create account",
    });
    const partial = buildAccountOrchestrationPlan({
      page: registration,
      capabilities: {
        automatedAccountCreation: true,
        secureCredentialResolver: true,
      },
    });
    expect(partial.canAutoAct).toBe(false);

    const ready = buildAccountOrchestrationPlan({
      page: registration,
      capabilities: {
        automatedAccountCreation: true,
        secureCredentialResolver: true,
        candidateMailAlias: true,
      },
    });
    expect(ready.canAutoAct).toBe(true);
    expect(ready.actions).toContain(
      "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
    );
    expect(ready.actions).toContain("RECORD_ACCOUNT");
  });

  it("never infers that a generic OTP screen is candidate-controlled email", () => {
    const verification = page({
      applicationState: "VERIFY_ACCOUNT",
      securityCheckpoint: "OTP",
      pageContext: "Enter verification code",
    });
    const ambiguous = buildAccountOrchestrationPlan({ page: verification });
    expect(ambiguous.canAutoAct).toBe(false);
    expect(accountPreflightItem(ambiguous).state).toBe("BLOCKED");

    const correlated = buildAccountOrchestrationPlan({
      page: verification,
      capabilities: {
        ordinaryEmailVerification: true,
        verificationKind: "EMAIL_CODE",
      },
    });
    expect(correlated.canAutoAct).toBe(true);
    expect(correlated.actions).toEqual([
      "WAIT_FOR_EMAIL_VERIFICATION",
      "CONSUME_ONE_TIME_VERIFICATION_CODE",
      "VERIFY_ACCOUNT",
      "CONTINUE_EXACT_APPLICATION",
    ]);
  });

  it("automates ordinary verification and reset links only with their required bindings", () => {
    const verifyLink = buildAccountOrchestrationPlan({
      page: page({
        url: "https://example.com/candidate/verify",
        applicationState: "VERIFY_ACCOUNT",
        pageContext: "Verify your email",
      }),
      capabilities: {
        ordinaryEmailVerification: true,
        verificationKind: "EMAIL_LINK",
      },
    });
    expect(verifyLink.canAutoAct).toBe(true);
    expect(verifyLink.actions).toContain("OPEN_VERIFICATION_LINK");

    const recoveryPage = page({
      url: "https://example.com/candidate/forgot-password",
      pageContext: "Forgot your password? Reset password",
    });
    const noResolver = buildAccountOrchestrationPlan({
      page: recoveryPage,
      knownAccounts: [account()],
      capabilities: {
        ordinaryEmailVerification: true,
        verificationKind: "PASSWORD_RESET_LINK",
      },
    });
    expect(noResolver.canAutoAct).toBe(false);
    expect(noResolver.actions).not.toContain(
      "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
    );

    const noKnownAccount = buildAccountOrchestrationPlan({
      page: recoveryPage,
      capabilities: {
        ordinaryEmailVerification: true,
        verificationKind: "PASSWORD_RESET_LINK",
        secureCredentialResolver: true,
      },
    });
    expect(noKnownAccount.canAutoAct).toBe(false);

    const recovery = buildAccountOrchestrationPlan({
      page: recoveryPage,
      knownAccounts: [account()],
      capabilities: {
        ordinaryEmailVerification: true,
        verificationKind: "PASSWORD_RESET_LINK",
        secureCredentialResolver: true,
      },
    });
    expect(recovery.canAutoAct).toBe(true);
    expect(recovery.actions).toContain("OPEN_VERIFICATION_LINK");
    expect(recovery.actions).toContain(
      "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
    );
  });

  it("automates an explicitly correlated candidate-controlled magic login link", () => {
    const magic = buildAccountOrchestrationPlan({
      page: page({
        url: "https://example.com/candidate/verify",
        applicationState: "VERIFY_ACCOUNT",
        pageContext: "Use the secure sign-in link sent to your email",
      }),
      capabilities: {
        ordinaryEmailVerification: true,
        verificationKind: "MAGIC_LOGIN_LINK",
      },
    });
    expect(magic.canAutoAct).toBe(true);
    expect(magic.actions).toEqual([
      "WAIT_FOR_EMAIL_VERIFICATION",
      "OPEN_VERIFICATION_LINK",
      "VERIFY_ACCOUNT",
      "CONTINUE_EXACT_APPLICATION",
    ]);
  });

  it("routes protected security challenges to ISSUE", () => {
    const protectedChallenge = buildAccountOrchestrationPlan({
      page: page({
        applicationState: "VERIFY_ACCOUNT",
        securityCheckpoint: "MFA",
      }),
      capabilities: { verificationKind: "SECURITY_INTERVENTION" },
    });
    expect(protectedChallenge.state).toBe("ISSUE");
    expect(protectedChallenge.canAutoAct).toBe(false);
    expect(protectedChallenge.actions).toEqual([]);
  });
});
