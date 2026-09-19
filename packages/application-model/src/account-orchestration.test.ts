import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  accountPreflightItem,
  buildAccountOrchestrationPlan,
  detectAccountFlow,
  portalScopeFromUrl,
  selectKnownAccount,
  type AccountRecord,
} from "./account-orchestration";

function page(overrides: Partial<ApplicationPage> = {}): ApplicationPage {
  return {
    pageId: "page-account",
    tabId: 1,
    frameId: 0,
    documentId: "doc-account",
    url: "https://example.com/careers/apply",
    title: "Apply",
    pageContext: "Application form",
    observedAt: "2026-08-17T19:00:00.000Z",
    controls: [],
    questions: [],
    applicationState: "QUESTIONS",
    pageFingerprint: "fingerprint",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    ...overrides,
  };
}

function account(overrides: Partial<AccountRecord> = {}): AccountRecord {
  return {
    accountId: "account-1",
    employer: "Example",
    domain: "example.com",
    scopeKey: "example.com",
    portalUrl: "https://example.com/candidate/login",
    email: "aadil@example.com",
    exists: true,
    createdAt: "2026-08-01T12:00:00.000Z",
    lastUsed: "2026-08-16T12:00:00.000Z",
    applicationIds: ["application-1"],
    ...overrides,
  };
}

describe("account orchestration", () => {
  it("does not treat ordinary application text as an account boundary", () => {
    const current = page({
      pageContext:
        "Complete your application. Existing employees should use the internal portal.",
    });
    expect(detectAccountFlow(current)).toBe("NONE");
    const plan = buildAccountOrchestrationPlan({ page: current });
    expect(plan.canAutoAct).toBe(true);
    expect(accountPreflightItem(plan).state).toBe("READY");
  });

  it("keeps new account creation fail-closed without verified capabilities", () => {
    const current = page({
      url: "https://example.com/candidate/register",
      applicationState: "AUTH",
      securityCheckpoint: "AUTHENTICATION",
      pageContext:
        "Create an account. New candidate registration. Already have an account? Sign in.",
    });
    expect(detectAccountFlow(current)).toBe("AUTH_CREATE");
    const plan = buildAccountOrchestrationPlan({ page: current });
    expect(plan.state).toBe("OWNER_ACTION_REQUIRED");
    expect(plan.actions).toContain("PREPARE_IDENTITY");
    expect(plan.actions).toContain("SECURE_CREDENTIAL_HANDOFF");
    expect(accountPreflightItem(plan).state).toBe("REVIEW");
  });

  it("automates new account creation only with mail identity and secure resolver", () => {
    const current = page({
      url: "https://example.com/candidate/register",
      applicationState: "ACCOUNT_CREATE",
      pageContext: "Create candidate account",
    });
    const plan = buildAccountOrchestrationPlan({
      page: current,
      capabilities: {
        automatedAccountCreation: true,
        secureCredentialResolver: true,
        candidateMailAlias: true,
        mailboxRuntimeAvailable: true,
      },
    });
    expect(plan.canAutoAct).toBe(true);
    expect(plan.state).toBe("READY_TO_CONTINUE");
    expect(plan.actions).toEqual([
      "PREPARE_IDENTITY",
      "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
      "RECORD_ACCOUNT",
      "CONTINUE_EXACT_APPLICATION",
    ]);
    expect(accountPreflightItem(plan).state).toBe("READY");
  });

  it("uses an exact portal-scope account for login without exposing credentials", () => {
    const current = page({
      url: "https://example.com/candidate/login",
      applicationState: "AUTH",
      securityCheckpoint: "AUTHENTICATION",
      pageContext: "Returning candidate sign in",
    });
    const known = account();
    expect(
      selectKnownAccount([known], current.url, "AADIL@EXAMPLE.COM")?.accountId,
    ).toBe("account-1");
    const plan = buildAccountOrchestrationPlan({
      page: current,
      knownAccounts: [known],
      preferredEmail: "aadil@example.com",
    });
    expect(plan.flow).toBe("AUTH_LOGIN");
    expect(plan.knownAccount?.accountId).toBe("account-1");
    expect(plan.actions).toEqual([
      "USE_EXISTING_ACCOUNT",
      "SECURE_CREDENTIAL_HANDOFF",
    ]);
    expect(plan.canAutoAct).toBe(false);
    expect(accountPreflightItem(plan).state).toBe("REVIEW");
  });

  it("reuses an existing account through the secure resolver instead of creating a duplicate", () => {
    const current = page({
      url: "https://example.com/candidate/register",
      applicationState: "ACCOUNT_CREATE",
      pageContext: "Create account",
    });
    const plan = buildAccountOrchestrationPlan({
      page: current,
      knownAccounts: [account()],
      preferredEmail: "aadil@example.com",
      capabilities: { secureCredentialResolver: true },
    });
    expect(plan.state).toBe("READY_TO_CONTINUE");
    expect(plan.actions).toEqual([
      "USE_EXISTING_ACCOUNT",
      "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
      "AUTHENTICATE_ACCOUNT",
      "CONTINUE_EXACT_APPLICATION",
    ]);
    expect(plan.actions).not.toContain("RECORD_ACCOUNT");
    expect(accountPreflightItem(plan).state).toBe("READY");
  });

  it("blocks duplicate account creation when a matching account exists without a resolver", () => {
    const current = page({
      url: "https://example.com/candidate/register",
      applicationState: "ACCOUNT_CREATE",
      pageContext: "Create account",
    });
    const plan = buildAccountOrchestrationPlan({
      page: current,
      knownAccounts: [account()],
      preferredEmail: "aadil@example.com",
    });
    expect(plan.state).toBe("DUPLICATE_RISK");
    expect(plan.actions).not.toContain("RECORD_ACCOUNT");
    expect(plan.requiresOwner).toBe(true);
    expect(accountPreflightItem(plan).state).toBe("BLOCKED");
  });

  it("does not infer ordinary email verification from an ambiguous OTP screen", () => {
    const verification = page({
      applicationState: "VERIFY_ACCOUNT",
      securityCheckpoint: "OTP",
      pageContext: "Enter the verification code we sent",
    });
    expect(detectAccountFlow(verification)).toBe("AUTH_VERIFY");
    const plan = buildAccountOrchestrationPlan({ page: verification });
    expect(plan.state).toBe("ISSUE");
    expect(plan.actions).toEqual([]);
    expect(plan.requiresOwner).toBe(false);
    expect(plan.canAutoAct).toBe(false);
    expect(accountPreflightItem(plan).state).toBe("BLOCKED");
  });

  it("automates an explicitly correlated candidate-controlled email code", () => {
    const verification = page({
      applicationState: "VERIFY_ACCOUNT",
      securityCheckpoint: "OTP",
      pageContext: "Enter the verification code we sent to your email",
    });
    const plan = buildAccountOrchestrationPlan({
      page: verification,
      capabilities: {
        ordinaryEmailVerification: true,
        mailboxRuntimeAvailable: true,
        verificationKind: "EMAIL_CODE",
      },
    });
    expect(plan.canAutoAct).toBe(true);
    expect(plan.actions).toEqual([
      "WAIT_FOR_EMAIL_VERIFICATION",
      "CONSUME_ONE_TIME_VERIFICATION_CODE",
      "VERIFY_ACCOUNT",
      "CONTINUE_EXACT_APPLICATION",
    ]);
    expect(accountPreflightItem(plan).state).toBe("READY");
  });

  it("automates candidate-controlled password reset links without persisting reset material", () => {
    const recovery = page({
      url: "https://example.com/account/forgot-password",
      applicationState: "AUTH",
      pageContext: "Forgot your password? Recover your account",
    });
    const plan = buildAccountOrchestrationPlan({
      page: recovery,
      knownAccounts: [account()],
      capabilities: {
        ordinaryEmailVerification: true,
        secureCredentialResolver: true,
        verificationKind: "PASSWORD_RESET_LINK",
      },
    });
    expect(plan.canAutoAct).toBe(true);
    expect(plan.actions).toEqual([
      "RECOVER_ACCOUNT",
      "WAIT_FOR_EMAIL_VERIFICATION",
      "OPEN_VERIFICATION_LINK",
      "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
      "AUTHENTICATE_ACCOUNT",
      "CONTINUE_EXACT_APPLICATION",
    ]);
    expect(accountPreflightItem(plan).state).toBe("READY");
  });

  it("routes ordinary email verification to ISSUE when mailbox runtime is unavailable", () => {
    const verification = page({
      applicationState: "VERIFY_ACCOUNT",
      securityCheckpoint: "OTP",
      pageContext: "Enter the verification code we sent to your email",
    });
    const plan = buildAccountOrchestrationPlan({
      page: verification,
      capabilities: {
        ordinaryEmailVerification: true,
        mailboxRuntimeAvailable: false,
        verificationKind: "EMAIL_CODE",
      },
    });
    expect(plan.state).toBe("ISSUE");
    expect(plan.requiresOwner).toBe(false);
    expect(plan.canAutoAct).toBe(false);
    expect(plan.actions).toEqual([]);
    expect(accountPreflightItem(plan).state).toBe("BLOCKED");
  });

  it("routes protected security challenges to ISSUE with continuation preserved", () => {
    const verification = page({
      applicationState: "VERIFY_ACCOUNT",
      securityCheckpoint: "IDENTITY_VERIFICATION",
      pageContext: "Security check",
    });
    const plan = buildAccountOrchestrationPlan({
      page: verification,
      capabilities: {
        ordinaryEmailVerification: true,
        mailboxRuntimeAvailable: true,
        verificationKind: "SECURITY_INTERVENTION",
      },
    });
    expect(plan.state).toBe("ISSUE");
    expect(plan.canAutoAct).toBe(false);
    expect(plan.actions).toEqual([]);
    expect(accountPreflightItem(plan).state).toBe("BLOCKED");
  });

  it("hard-blocks an unrecognized authentication surface", () => {
    const current = page({
      url: "https://example.com/candidate/session",
      applicationState: "AUTH",
      securityCheckpoint: "AUTHENTICATION",
      title: "Candidate access",
      pageContext: "Continue to your candidate workspace",
    });
    expect(detectAccountFlow(current)).toBe("AUTH_UNKNOWN");
    const plan = buildAccountOrchestrationPlan({ page: current });
    expect(plan.actions).toEqual(["SECURE_CREDENTIAL_HANDOFF"]);
    expect(accountPreflightItem(plan).state).toBe("BLOCKED");
  });

  it("separates Workday tenant accounts that share the same host", () => {
    const first = portalScopeFromUrl(
      "https://wd5.myworkdayjobs.com/CompanyOne/job/New-York/Role_123",
    );
    const second = portalScopeFromUrl(
      "https://wd5.myworkdayjobs.com/CompanyTwo/job/New-York/Role_123",
    );
    expect(first).toBe("wd5.myworkdayjobs.com/companyone");
    expect(second).toBe("wd5.myworkdayjobs.com/companytwo");
    expect(first).not.toBe(second);
  });
});
