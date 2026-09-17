import type { AccountRecord } from "@munshi-apply/application-model";

const nativeHostName = "systems.munshi.apply";

type NativeResponse =
  { ok: true; data?: unknown } | { ok: false; error: string };

function objectValue(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value.trim();
}

function nullableString(value: unknown, label: string): string | null {
  if (value === null) return null;
  return requiredString(value, label);
}

function timestamp(value: unknown, label: string): string {
  const result = requiredString(value, label);
  if (Number.isNaN(Date.parse(result))) {
    throw new Error(`${label} must be an ISO timestamp`);
  }
  return result;
}

export function parseAccountRecord(value: unknown): AccountRecord {
  const candidate = objectValue(value, "Account record");
  if (typeof candidate.exists !== "boolean") {
    throw new Error("Account record exists must be boolean");
  }
  if (
    !Array.isArray(candidate.applicationIds) ||
    !candidate.applicationIds.every(
      (item) => typeof item === "string" && item.trim(),
    )
  ) {
    throw new Error("Account record applicationIds are invalid");
  }
  return {
    accountId: requiredString(candidate.accountId, "Account record accountId"),
    employer: nullableString(candidate.employer, "Account record employer"),
    domain: requiredString(candidate.domain, "Account record domain"),
    scopeKey: requiredString(candidate.scopeKey, "Account record scopeKey"),
    portalUrl: requiredString(candidate.portalUrl, "Account record portalUrl"),
    email: requiredString(candidate.email, "Account record email"),
    exists: candidate.exists,
    createdAt: timestamp(candidate.createdAt, "Account record createdAt"),
    lastUsed: timestamp(candidate.lastUsed, "Account record lastUsed"),
    applicationIds: candidate.applicationIds.map((item) => String(item).trim()),
  };
}

export function parseAccountRecords(value: unknown): AccountRecord[] {
  if (!Array.isArray(value)) {
    throw new Error("Account lookup response must be an array");
  }
  return value.map(parseAccountRecord);
}

async function sendNativeAccount<T>(
  message: Record<string, unknown>,
  timeoutMilliseconds = 5_000,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative(nativeHostName);
    const timeout = window.setTimeout(() => {
      port.disconnect();
      reject(new Error("Native account registry request timed out"));
    }, timeoutMilliseconds);

    const finish = (): void => window.clearTimeout(timeout);
    port.onMessage.addListener((response: NativeResponse) => {
      finish();
      port.disconnect();
      if (!response.ok) {
        reject(new Error(response.error));
        return;
      }
      resolve(response.data as T);
    });
    port.onDisconnect.addListener(() => {
      const lastError = chrome.runtime.lastError;
      if (!lastError) return;
      finish();
      reject(new Error(lastError.message));
    });
    port.postMessage(message);
  });
}

export async function lookupNativeAccounts(input: {
  portalUrl: string;
  email?: string | null;
}): Promise<AccountRecord[]> {
  const portalUrl = input.portalUrl.trim();
  if (!portalUrl) throw new Error("portalUrl must be a non-empty string");
  const response = await sendNativeAccount<unknown>({
    type: "LOOKUP_ACCOUNTS",
    payload: {
      portalUrl,
      ...(input.email?.trim() ? { email: input.email.trim() } : {}),
    },
  });
  return parseAccountRecords(response);
}

export async function upsertNativeAccount(input: {
  accountId?: string | null;
  employer?: string | null;
  portalUrl: string;
  email: string;
  exists?: boolean;
  applicationId?: string | null;
  observedAt: string;
}): Promise<AccountRecord> {
  const portalUrl = input.portalUrl.trim();
  const email = input.email.trim();
  if (!portalUrl) throw new Error("portalUrl must be a non-empty string");
  if (!email) throw new Error("email must be a non-empty string");
  if (Number.isNaN(Date.parse(input.observedAt))) {
    throw new Error("observedAt must be an ISO timestamp");
  }
  const response = await sendNativeAccount<unknown>({
    type: "UPSERT_ACCOUNT",
    payload: {
      ...(input.accountId?.trim() ? { accountId: input.accountId.trim() } : {}),
      ...(input.employer?.trim() ? { employer: input.employer.trim() } : {}),
      portalUrl,
      email,
      exists: input.exists ?? true,
      ...(input.applicationId?.trim()
        ? { applicationId: input.applicationId.trim() }
        : {}),
      observedAt: input.observedAt,
    },
  });
  return parseAccountRecord(response);
}
