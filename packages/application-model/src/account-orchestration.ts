import type { ApplicationPage } from "@munshi-apply/contracts";
import type { PreflightGateItem } from "./policies";

export type AccountFlow =
  | "NONE"
  | "AUTH_LOGIN"
  | "AUTH_CREATE"
  | "AUTH_RECOVERY"
  | "AUTH_VERIFY"
  | "AUTH_UNKNOWN";

export type AccountRecord = {
  accountId: string;
  employer: string | null;
  domain: string;
  scopeKey: string;
  portalUrl: string;
  email: string;
  exists: boolean;
  createdAt: string;
  lastUsed: string;
  applicationIds: readonly string[];
};

export type AccountOrchestrationState =
  | "NOT_REQUIRED"
  | "OWNER_ACTION_REQUIRED"
  | "DUPLICATE_RISK"
  | "READY_TO_CONTINUE";

export type AccountOrchestrationAction =
  | "CONTINUE_APPLICATION"
  | "USE_EXISTING_ACCOUNT"
  | "PREPARE_IDENTITY"
  | "SECURE_CREDENTIAL_HANDOFF"
  | "RECOVER_ACCOUNT"
  | "VERIFY_ACCOUNT"
  | "RECORD_ACCOUNT";

export type AccountOrchestrationPlan = {
  flow: AccountFlow;
  state: AccountOrchestrationState;
  scopeKey: string;
  knownAccount: AccountRecord | null;
  requiresOwner: boolean;
  canAutoAct: boolean;
  actions: readonly AccountOrchestrationAction[];
  reasons: readonly string[];
};

const sharedTenantHosts = [
  "myworkdayjobs.com",
  "myworkdaysite.com",
  "myworkday.com",
] as const;

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function accountSurfaceText(page: ApplicationPage): string {
  return compact(
    `${page.title} ${page.url} ${page.pageContext ?? ""}`,
  ).toLocaleLowerCase("en-US");
}

function hasSharedTenantHost(hostname: string): boolean {
  return sharedTenantHosts.some(
    (suffix) => hostname === suffix || hostname.endsWith(`.${suffix}`),
  );
}

/**
 * Credential/account scope is intentionally narrower than origin for shared
 * ATS hosts. A Workday tenant must not be treated as the same account merely
 * because another employer uses the same Workday hostname.
 */
export function portalScopeFromUrl(rawUrl: string): string {
  const url = new URL(rawUrl);
  const hostname = url.hostname.toLocaleLowerCase("en-US");
  if (!hasSharedTenantHost(hostname)) return hostname;

  const tenant = url.pathname
    .split("/")
    .map((part) => part.trim().toLocaleLowerCase("en-US"))
    .find(Boolean);
  return tenant ? `${hostname}/${tenant}` : hostname;
}

function hasAccountRoute(page: ApplicationPage): boolean {
  try {
    const url = new URL(page.url);
    return /\b(login|signin|sign-in|register|signup|sign-up|account|candidate|forgot|reset|verify)\b/i.test(
      `${url.pathname} ${url.search} ${url.hash}`,
    );
  } catch {
    return false;
  }
}

export function detectAccountFlow(page: ApplicationPage): AccountFlow {
  if (page.applicationState === "VERIFY_ACCOUNT") return "AUTH_VERIFY";
  if (page.applicationState === "ACCOUNT_CREATE") return "AUTH_CREATE";

  if (
    page.securityCheckpoint === "MFA" ||
    page.securityCheckpoint === "OTP" ||
    page.securityCheckpoint === "IDENTITY_VERIFICATION"
  ) {
    return "AUTH_VERIFY";
  }

  const text = accountSurfaceText(page);
  const accountContext =
    page.applicationState === "AUTH" ||
    page.securityCheckpoint === "AUTHENTICATION" ||
    hasAccountRoute(page);

  if (!accountContext) return "NONE";

  if (
    /\b(forgot (?:your )?(?:password|username)|reset (?:your )?password|recover (?:your )?account|account recovery)\b/.test(
      text,
    )
  ) {
    return "AUTH_RECOVERY";
  }

  if (
    /\b(verify (?:your )?(?:account|email|identity)|email verification|verification code|enter the code we sent)\b/.test(
      text,
    )
  ) {
    return "AUTH_VERIFY";
  }

  if (
    /\b(create (?:an? )?account|register(?: as)?(?: a)? candidate|new candidate|sign up|signup)\b/.test(
      text,
    )
  ) {
    return "AUTH_CREATE";
  }

  if (
    page.securityCheckpoint === "AUTHENTICATION" ||
    /\b(sign in|signin|log in|login|existing account|returning candidate)\b/.test(
      text,
    )
  ) {
    return "AUTH_LOGIN";
  }

  return page.applicationState === "AUTH" ? "AUTH_UNKNOWN" : "NONE";
}

export function selectKnownAccount(
  accounts: readonly AccountRecord[],
  pageUrl: string,
  preferredEmail?: string | null,
): AccountRecord | null {
  const scopeKey = portalScopeFromUrl(pageUrl);
  const preferred = compact(preferredEmail).toLocaleLowerCase("en-US");
  const candidates = accounts
    .filter((account) => account.exists && account.scopeKey === scopeKey)
    .filter(
      (account) =>
        !preferred || account.email.toLocaleLowerCase("en-US") === preferred,
    )
    .sort(
      (left, right) =>
        right.lastUsed.localeCompare(left.lastUsed) ||
        left.accountId.localeCompare(right.accountId),
    );
  return candidates[0] ?? null;
}

export function buildAccountOrchestrationPlan(input: {
  page: ApplicationPage;
  knownAccounts?: readonly AccountRecord[];
  preferredEmail?: string | null;
}): AccountOrchestrationPlan {
  const flow = detectAccountFlow(input.page);
  const scopeKey = portalScopeFromUrl(input.page.url);
  const knownAccount = selectKnownAccount(
    input.knownAccounts ?? [],
    input.page.url,
    input.preferredEmail,
  );

  if (flow === "NONE") {
    return {
      flow,
      state: "READY_TO_CONTINUE",
      scopeKey,
      knownAccount,
      requiresOwner: false,
      canAutoAct: true,
      actions: ["CONTINUE_APPLICATION"],
      reasons: ["No account or authentication boundary is active"],
    };
  }

  if (flow === "AUTH_CREATE" && knownAccount) {
    return {
      flow,
      state: "DUPLICATE_RISK",
      scopeKey,
      knownAccount,
      requiresOwner: true,
      canAutoAct: false,
      actions: ["USE_EXISTING_ACCOUNT", "SECURE_CREDENTIAL_HANDOFF"],
      reasons: [
        "A previously recorded account exists for this employer portal scope",
        "MUNSHI will not create a duplicate account or enter authentication secrets autonomously",
      ],
    };
  }

  if (flow === "AUTH_CREATE") {
    return {
      flow,
      state: "OWNER_ACTION_REQUIRED",
      scopeKey,
      knownAccount: null,
      requiresOwner: true,
      canAutoAct: false,
      actions: [
        "PREPARE_IDENTITY",
        "SECURE_CREDENTIAL_HANDOFF",
        "RECORD_ACCOUNT",
      ],
      reasons: [
        "A new candidate account is required",
        "Identity fields may be prepared, but password creation/storage and authentication remain owner/browser credential-manager actions",
      ],
    };
  }

  if (flow === "AUTH_LOGIN") {
    return {
      flow,
      state: "OWNER_ACTION_REQUIRED",
      scopeKey,
      knownAccount,
      requiresOwner: true,
      canAutoAct: false,
      actions: knownAccount
        ? ["USE_EXISTING_ACCOUNT", "SECURE_CREDENTIAL_HANDOFF"]
        : ["SECURE_CREDENTIAL_HANDOFF"],
      reasons: [
        knownAccount
          ? "A matching account record exists for this portal scope"
          : "No matching account record is available for this portal scope",
        "Authentication credentials are never stored in the application ledger or entered autonomously",
      ],
    };
  }

  if (flow === "AUTH_RECOVERY") {
    return {
      flow,
      state: "OWNER_ACTION_REQUIRED",
      scopeKey,
      knownAccount,
      requiresOwner: true,
      canAutoAct: false,
      actions: ["RECOVER_ACCOUNT", "SECURE_CREDENTIAL_HANDOFF"],
      reasons: [
        "Account recovery requires explicit owner control",
        "Recovery links, secrets, OTPs, and password-reset values are not persisted by MUNSHI",
      ],
    };
  }

  if (flow === "AUTH_VERIFY") {
    return {
      flow,
      state: "OWNER_ACTION_REQUIRED",
      scopeKey,
      knownAccount,
      requiresOwner: true,
      canAutoAct: false,
      actions: ["VERIFY_ACCOUNT"],
      reasons: [
        "Account verification is a human/security checkpoint",
        "MFA, OTP, identity verification, and verification links remain owner actions",
      ],
    };
  }

  return {
    flow,
    state: "OWNER_ACTION_REQUIRED",
    scopeKey,
    knownAccount,
    requiresOwner: true,
    canAutoAct: false,
    actions: ["SECURE_CREDENTIAL_HANDOFF"],
    reasons: [
      "An authentication surface is active but its exact account path is unresolved",
    ],
  };
}

export function accountPreflightItem(
  plan: AccountOrchestrationPlan,
): PreflightGateItem {
  return {
    id: `account:${plan.scopeKey}`,
    state: plan.requiresOwner ? "BLOCKED" : "READY",
  };
}
