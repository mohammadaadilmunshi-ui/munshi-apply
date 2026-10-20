import { describe, it, expect } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  buildAccountOrchestrationPlan,
  portalScopeFromUrl,
  type AccountRecord,
} from "./account-orchestration";

const assigned = "u_testcandidate123@mail.munshi.systems";

const providers = [
  {
    provider: "Workday",
    url: "https://stellaris.wd5.myworkdayjobs.com/en-US/External",
  },
  { provider: "iCIMS", url: "https://careers-demo.icims.com/jobs" },
  {
    provider: "Oracle",
    url: "https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
  },
] as const;

function page(
  url: string,
  context: string,
  state: ApplicationPage["applicationState"],
): ApplicationPage {
  return {
    pageId: "account-qa",
    tabId: 12,
    frameId: 0,
    documentId: "document-account-qa",
    title: "Candidate account",
    url,
    pageContext: context,
    observedAt: "2026-10-20T03:00:00.000Z",
    controls: [],
    questions: [],
    applicationState: state,
    pageFingerprint: "qa-account",
    securityCheckpoint: state === "VERIFY_ACCOUNT" ? "OTP" : "AUTHENTICATION",
    navigationCandidates: [],
    validationErrorCount: 0,
    finalSubmissionBoundary: false,
  };
}

function known(url: string): AccountRecord {
  return {
    accountId: "existing-managed-account",
    employer: "Example",
    domain: new URL(url).hostname,
    scopeKey: portalScopeFromUrl(url),
    portalUrl: url,
    email: assigned,
    exists: true,
    createdAt: "2026-10-20T01:00:00.000Z",
    lastUsed: "2026-10-20T02:00:00.000Z",
    applicationIds: ["application-1"],
  };
}

describe.each(providers)(
  "exact-account safe lifecycle: $provider",
  ({ url }) => {
    it("prepares a new account only with owner identity + mail + credential authority", () => {
      const target = page(
        url + "/register",
        "Create candidate account",
        "ACCOUNT_CREATE",
      );
      const unready = buildAccountOrchestrationPlan({
        page: target,
        preferredEmail: assigned,
      });
      expect(unready.canAutoAct).toBe(false);
      const prepared = buildAccountOrchestrationPlan({
        page: target,
        preferredEmail: assigned,
        capabilities: {
          automatedAccountCreation: true,
          secureCredentialResolver: true,
          candidateMailAlias: true,
          mailboxRuntimeAvailable: true,
        },
      });
      expect(prepared.canAutoAct).toBe(true);
      expect(prepared.actions).toContain("PREPARE_IDENTITY");
      expect(prepared.actions).toContain("RECORD_ACCOUNT");
      expect(prepared.actions).not.toContain("AUTHENTICATE_ACCOUNT");
    });

    it("reuses the same assigned email on subsequent login without duplicate registration", () => {
      const account = known(url);
      const target = page(
        url + "/login",
        "Returning candidate sign in",
        "AUTH",
      );
      const prepared = buildAccountOrchestrationPlan({
        page: target,
        knownAccounts: [account],
        preferredEmail: assigned,
        capabilities: { secureCredentialResolver: true },
      });
      expect(prepared.canAutoAct).toBe(true);
      expect(prepared.knownAccount?.email).toBe(assigned);
      expect(prepared.actions).toContain("AUTHENTICATE_ACCOUNT");
      expect(prepared.actions).not.toContain("RECORD_ACCOUNT");

      const wrongIdentity = buildAccountOrchestrationPlan({
        page: target,
        knownAccounts: [account],
        preferredEmail: "other@example.com",
        capabilities: { secureCredentialResolver: true },
      });
      expect(wrongIdentity.canAutoAct).toBe(false);
    });

    it("allows account-bound forgot-password only with secure reset-link provenance", () => {
      const target = page(
        url + "/forgot-password",
        "Forgot your password? Reset password",
        "AUTH",
      );
      const shared = {
        page: target,
        knownAccounts: [known(url)],
        preferredEmail: assigned,
        capabilities: {
          ordinaryEmailVerification: true,
          mailboxRuntimeAvailable: true,
          secureCredentialResolver: true,
          verificationKind: "PASSWORD_RESET_LINK" as const,
        },
      };
      const reset = buildAccountOrchestrationPlan(shared);
      expect(reset.canAutoAct).toBe(true);
      expect(reset.actions).toContain("RECOVER_ACCOUNT");
      expect(reset.actions).toContain(
        "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
      );
      const noAccount = buildAccountOrchestrationPlan({
        ...shared,
        knownAccounts: [],
      });
      expect(noAccount.canAutoAct).toBe(false);
    });

    it("consumes only explicitly correlated ordinary signup codes or links", () => {
      const target = page(
        url + "/verify",
        "Enter the emailed code to verify your account",
        "VERIFY_ACCOUNT",
      );
      for (const kind of ["EMAIL_CODE", "EMAIL_LINK"] as const) {
        const plan = buildAccountOrchestrationPlan({
          page: target,
          preferredEmail: assigned,
          capabilities: {
            ordinaryEmailVerification: true,
            mailboxRuntimeAvailable: true,
            verificationKind: kind,
          },
        });
        expect(plan.canAutoAct).toBe(true);
        expect(plan.actions).toContain("VERIFY_ACCOUNT");
        expect(plan.actions).toContain("CONTINUE_EXACT_APPLICATION");
      }
      for (const kind of [
        "PASSWORD_RESET_LINK",
        "MAGIC_LOGIN_LINK",
        "SECURITY_INTERVENTION",
      ] as const) {
        const plan = buildAccountOrchestrationPlan({
          page: target,
          preferredEmail: assigned,
          capabilities: {
            ordinaryEmailVerification: true,
            mailboxRuntimeAvailable: true,
            verificationKind: kind,
          },
        });
        expect(plan.canAutoAct).toBe(false);
      }
    });
  },
);

it("Workday language and career-site URL variations reuse one account within a tenant", () => {
  const first = portalScopeFromUrl(
    "https://acme.wd5.myworkdayjobs.com/en-US/External/job/1",
  );
  const second = portalScopeFromUrl(
    "https://acme.wd5.myworkdayjobs.com/fr-FR/External/login",
  );
  const third = portalScopeFromUrl(
    "https://acme.wd5.myworkdayjobs.com/External/verify",
  );
  expect(first).toBe(second);
  expect(second).toBe(third);
  const genericFirst = portalScopeFromUrl(
    "https://wd5.myworkdayjobs.com/en-US/CompanyOne/job/123",
  );
  const genericSecond = portalScopeFromUrl(
    "https://wd5.myworkdayjobs.com/fr-FR/CompanyOne/login",
  );
  expect(genericFirst).toBe(genericSecond);
  expect(
    portalScopeFromUrl("https://wd5.myworkdayjobs.com/CompanyTwo/login"),
  ).not.toBe(genericFirst);
});
