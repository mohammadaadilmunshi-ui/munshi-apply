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

  it("detects create-account flow before incidental sign-in text", () => {
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
    expect(accountPreflightItem(plan).state).toBe("BLOCKED");
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
  });

  it("blocks duplicate account creation when a matching account exists", () => {
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
  });

  it("treats recovery and verification as owner security checkpoints", () => {
    const recovery = page({
      url: "https://example.com/account/forgot-password",
      applicationState: "AUTH",
      pageContext: "Forgot your password? Recover your account",
    });
    expect(detectAccountFlow(recovery)).toBe("AUTH_RECOVERY");
    expect(buildAccountOrchestrationPlan({ page: recovery }).actions).toContain(
      "RECOVER_ACCOUNT",
    );

    const verification = page({
      applicationState: "VERIFY_ACCOUNT",
      securityCheckpoint: "OTP",
      pageContext: "Enter the verification code we sent",
    });
    expect(detectAccountFlow(verification)).toBe("AUTH_VERIFY");
    expect(
      buildAccountOrchestrationPlan({ page: verification }).actions,
    ).toEqual(["VERIFY_ACCOUNT"]);
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
