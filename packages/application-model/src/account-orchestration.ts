import type { ApplicationPage } from "@munshi-apply/contracts";
import type { PreflightGateItem } from "./policies";

export type AccountFlow =
  | "NONE"
  | "AUTH_LOGIN"
  | "AUTH_CREATE"
  | "AUTH_RECOVERY"
  | "AUTH_VERIFY"
  | "AUTH_UNKNOWN";

export type AccountVerificationKind =
  | "EMAIL_LINK"
  | "EMAIL_CODE"
  | "PASSWORD_RESET_LINK"
  | "MAGIC_LOGIN_LINK"
  | "SECURITY_INTERVENTION"
  | null;

export type AccountAutomationCapabilities = {
  automatedAccountCreation?: boolean;
  secureCredentialResolver?: boolean;
  candidateMailAlias?: boolean;
  ordinaryEmailVerification?: boolean;
  mailboxRuntimeAvailable?: boolean;
  verificationKind?: AccountVerificationKind;
};

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
  | "READY_TO_CONTINUE"
  | "ISSUE";

export type AccountOrchestrationAction =
  | "CONTINUE_APPLICATION"
  | "CONTINUE_EXACT_APPLICATION"
  | "USE_EXISTING_ACCOUNT"
  | "PREPARE_IDENTITY"
  | "SECURE_CREDENTIAL_HANDOFF"
  | "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER"
  | "RECOVER_ACCOUNT"
  | "VERIFY_ACCOUNT"
  | "WAIT_FOR_EMAIL_VERIFICATION"
  | "CONSUME_ONE_TIME_VERIFICATION_CODE"
  | "OPEN_VERIFICATION_LINK"
  | "AUTHENTICATE_ACCOUNT"
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
  )
    return "AUTH_VERIFY";

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
  )
    return "AUTH_RECOVERY";
  if (
    /\b(verify (?:your )?(?:account|email|identity)|email verification|verification code|enter the code we sent)\b/.test(
      text,
    )
  )
    return "AUTH_VERIFY";
  if (
    /\b(create (?:an? )?account|register(?: as)?(?: a)? candidate|new candidate|sign up|signup)\b/.test(
      text,
    )
  )
    return "AUTH_CREATE";
  if (
    /\b(sign in|signin|log in|login|existing account|returning candidate)\b/.test(
      text,
    )
  )
    return "AUTH_LOGIN";
  return "AUTH_UNKNOWN";
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

function canUseResolvedPassword(
  capabilities?: AccountAutomationCapabilities,
): boolean {
  return capabilities?.secureCredentialResolver === true;
}

function canCreateAutomatically(
  capabilities?: AccountAutomationCapabilities,
): boolean {
  return (
    capabilities?.automatedAccountCreation === true &&
    capabilities.secureCredentialResolver === true &&
    capabilities.candidateMailAlias === true &&
    capabilities.mailboxRuntimeAvailable === true
  );
}

function canConsumeOrdinaryEmailVerification(
  capabilities?: AccountAutomationCapabilities,
): boolean {
  return (
    capabilities?.ordinaryEmailVerification === true &&
    capabilities?.mailboxRuntimeAvailable === true &&
    capabilities.verificationKind !== null &&
    capabilities.verificationKind !== undefined &&
    capabilities.verificationKind !== "SECURITY_INTERVENTION"
  );
}

function emailVerificationActions(
  kind: AccountVerificationKind,
): readonly AccountOrchestrationAction[] {
  if (kind === "EMAIL_CODE") {
    return [
      "WAIT_FOR_EMAIL_VERIFICATION",
      "CONSUME_ONE_TIME_VERIFICATION_CODE",
      "VERIFY_ACCOUNT",
      "CONTINUE_EXACT_APPLICATION",
    ];
  }
  return [
    "WAIT_FOR_EMAIL_VERIFICATION",
    "OPEN_VERIFICATION_LINK",
    "VERIFY_ACCOUNT",
    "CONTINUE_EXACT_APPLICATION",
  ];
}

export function buildAccountOrchestrationPlan(input: {
  page: ApplicationPage;
  knownAccounts?: readonly AccountRecord[];
  preferredEmail?: string | null;
  capabilities?: AccountAutomationCapabilities;
}): AccountOrchestrationPlan {
  const flow = detectAccountFlow(input.page);
  const scopeKey = portalScopeFromUrl(input.page.url);
  const knownAccount = selectKnownAccount(
    input.knownAccounts ?? [],
    input.page.url,
    input.preferredEmail,
  );
  const capabilities = input.capabilities;

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

  if (capabilities?.verificationKind === "SECURITY_INTERVENTION") {
    return {
      flow,
      state: "ISSUE",
      scopeKey,
      knownAccount,
      requiresOwner: true,
      canAutoAct: false,
      actions: [],
      reasons: [
        "A protected security challenge requires external user/security intervention",
        "The exact application continuation must be preserved and no challenge bypass may be attempted",
      ],
    };
  }

  if (flow === "AUTH_CREATE" && knownAccount) {
    if (canUseResolvedPassword(capabilities)) {
      return {
        flow,
        state: "READY_TO_CONTINUE",
        scopeKey,
        knownAccount,
        requiresOwner: false,
        canAutoAct: true,
        actions: [
          "USE_EXISTING_ACCOUNT",
          "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
          "AUTHENTICATE_ACCOUNT",
          "CONTINUE_EXACT_APPLICATION",
        ],
        reasons: [
          "A previously recorded account exists for this exact employer portal scope",
          "Secure credential resolution allows reuse without duplicate account creation",
        ],
      };
    }
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
        "MUNSHI will not create a duplicate account without a secure credential resolver",
      ],
    };
  }

  if (flow === "AUTH_CREATE") {
    if (canCreateAutomatically(capabilities)) {
      return {
        flow,
        state: "READY_TO_CONTINUE",
        scopeKey,
        knownAccount: null,
        requiresOwner: false,
        canAutoAct: true,
        actions: [
          "PREPARE_IDENTITY",
          "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
          "RECORD_ACCOUNT",
          "CONTINUE_EXACT_APPLICATION",
        ],
        reasons: [
          "All account-creation automation capabilities are verified",
          "Password material is resolved only at execution time and never enters the application or Teach ledgers",
        ],
      };
    }
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
        "Automatic creation remains fail-closed until mail identity and secure credential resolution are available",
      ],
    };
  }

  if (flow === "AUTH_LOGIN") {
    if (knownAccount && canUseResolvedPassword(capabilities)) {
      return {
        flow,
        state: "READY_TO_CONTINUE",
        scopeKey,
        knownAccount,
        requiresOwner: false,
        canAutoAct: true,
        actions: [
          "USE_EXISTING_ACCOUNT",
          "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
          "AUTHENTICATE_ACCOUNT",
          "CONTINUE_EXACT_APPLICATION",
        ],
        reasons: [
          "A matching account exists and its password can be resolved through the privileged credential boundary",
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
      actions: knownAccount
        ? ["USE_EXISTING_ACCOUNT", "SECURE_CREDENTIAL_HANDOFF"]
        : ["SECURE_CREDENTIAL_HANDOFF"],
      reasons: [
        knownAccount
          ? "A matching account record exists for this portal scope"
          : "No matching account record is available for this portal scope",
        "A privileged secure credential reference is required before login may be automated",
      ],
    };
  }

  if (flow === "AUTH_RECOVERY") {
    if (
      knownAccount &&
      capabilities?.ordinaryEmailVerification === true &&
      capabilities.mailboxRuntimeAvailable === true &&
      capabilities.verificationKind === "PASSWORD_RESET_LINK" &&
      capabilities.secureCredentialResolver === true
    ) {
      return {
        flow,
        state: "READY_TO_CONTINUE",
        scopeKey,
        knownAccount,
        requiresOwner: false,
        canAutoAct: true,
        actions: [
          "RECOVER_ACCOUNT",
          "WAIT_FOR_EMAIL_VERIFICATION",
          "OPEN_VERIFICATION_LINK",
          "FILL_PASSWORD_FROM_SECURE_CREDENTIAL_RESOLVER",
          "AUTHENTICATE_ACCOUNT",
          "CONTINUE_EXACT_APPLICATION",
        ],
        reasons: [
          "Password recovery is bound to a candidate-controlled MUNSHI mail alias and an exact known portal account",
          "The reset link and replacement password remain one-time/resolver-controlled values",
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
      actions: ["RECOVER_ACCOUNT", "SECURE_CREDENTIAL_HANDOFF"],
      reasons: [
        "Account recovery is not fully bound to an exact known account, candidate-controlled email flow, and secure credential resolver",
        "Recovery remains fail-closed rather than guessing the challenge channel or password source",
      ],
    };
  }

  if (flow === "AUTH_VERIFY") {
    if (capabilities?.mailboxRuntimeAvailable !== true) {
      return {
        flow,
        state: "ISSUE",
        scopeKey,
        knownAccount,
        requiresOwner: false,
        canAutoAct: false,
        actions: [],
        reasons: [
          "Mailbox automation is a mandatory runtime dependency for email verification",
          "The account continuation must enter ISSUE rather than silently falling back to manual verification",
        ],
      };
    }
    if (canConsumeOrdinaryEmailVerification(capabilities)) {
      return {
        flow,
        state: "READY_TO_CONTINUE",
        scopeKey,
        knownAccount,
        requiresOwner: false,
        canAutoAct: true,
        actions: emailVerificationActions(
          capabilities?.verificationKind ?? null,
        ),
        reasons: [
          "The verification challenge is explicitly correlated to a candidate-controlled MUNSHI mail alias",
          "One-time verification material is consumed through the mail resolver and is not persisted in recipes or account state",
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
      actions: ["VERIFY_ACCOUNT"],
      reasons: [
        "The authentication page does not have trusted ordinary-email verification provenance",
        "SMS, TOTP, passkeys, CAPTCHA, identity checks, and ambiguous OTP challenges remain external intervention cases",
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
  if (plan.canAutoAct) {
    return { id: `account:${plan.scopeKey}`, state: "READY" };
  }
  const hardBlocked =
    plan.state === "ISSUE" ||
    plan.state === "DUPLICATE_RISK" ||
    plan.flow === "AUTH_RECOVERY" ||
    plan.flow === "AUTH_VERIFY" ||
    plan.flow === "AUTH_UNKNOWN";
  return {
    id: `account:${plan.scopeKey}`,
    state: hardBlocked ? "BLOCKED" : !plan.requiresOwner ? "READY" : "REVIEW",
  };
}
