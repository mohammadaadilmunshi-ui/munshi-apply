import {
  parseAutoPilotCheckpoint,
  type AutoPilotCheckpoint,
} from "@munshi-apply/application-model";
import {
  parseProfileSnapshot,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";

const nativeHostName = "systems.munshi.apply";

type NativeResponse =
  { ok: true; data?: unknown } | { ok: false; error: string };

export type AISettings = {
  provider: "openai";
  enabled: boolean;
  model: string;
  monthlyBudgetUsd: number;
  warningBudgetUsd: number;
  hardStop: boolean;
  allowApplicationDrafts: boolean;
  allowProfileEvidence: boolean;
  allowResumeEvidence: boolean;
  keyConfigured: boolean;
  keySource: "keychain" | "environment" | "none";
};

export type AIUsageSummary = {
  month: string;
  spentUsd: number;
  reservedUsd: number;
  projectedUsd: number;
  remainingUsd: number;
  requestCount: number;
  inputTokens: number;
  outputTokens: number;
  estimatedCostUsd: number;
};

export type AIPricingStatus = {
  provider: "openai";
  model: string;
  inputUsdPerMillionTokens: number;
  outputUsdPerMillionTokens: number;
  verifiedAt: string;
  source: string;
  ageDays: number;
  stale: boolean;
};

export type AIControlStatus = {
  settings: AISettings;
  usage: AIUsageSummary;
  pricing: AIPricingStatus | null;
  guardrails: {
    safeDraftSemanticTypes: string[];
    consequentialQuestionsManual: true;
    protectedEvidenceExcluded: true;
    ownerReviewRequired: true;
    finalSubmissionManual: true;
  };
};

export type AIDraftRequest = {
  applicationId: string;
  pageId: string;
  questionId: string;
  controlId: string;
  question: string;
  semanticType: string;
  correlationId: string;
  maxWords?: number;
  maxOutputTokens?: number;
};

export type AIDraftPreview = {
  state: "READY_FOR_PROVIDER";
  providerCallMade: false;
  model: string;
  evidenceIds: string[];
  estimatedInputTokens: number;
  plannedCostUsd: number;
  budget: {
    state: "ALLOW" | "WARN";
    month: string;
    spentUsd: number;
    reservedUsd: number;
    plannedCostUsd: number;
    projectedUsd: number;
    remainingUsd: number;
    reason: string;
  };
  reviewRequired: true;
};

export type AIDraftStatus =
  "DRAFT" | "APPROVED" | "REJECTED" | "SUPERSEDED" | "USED";

export type AIDraftRecord = {
  draftId: string;
  applicationId: string;
  pageId: string;
  questionId: string;
  controlId: string;
  questionFingerprint: string;
  semanticType: string;
  provider: "openai";
  model: string;
  responseId: string;
  originalText: string;
  currentText: string;
  contentSha256: string;
  status: AIDraftStatus;
  evidenceIds: string[];
  claims: { claimId: string; text: string; evidenceIds: string[] }[];
  usage: {
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
    costUsd: number;
    estimated?: boolean;
  };
  generatedAt: string;
  updatedAt: string;
  approvedAt: string | null;
  usedAt: string | null;
};

export type AIDraftResult = {
  status: "DRAFT_REVIEW_REQUIRED";
  draftId: string;
  draft: AIDraftRecord;
  provider: "openai";
  model: string;
  responseId: string;
  text: string;
  claims: { claimId: string; text: string; evidenceIds: string[] }[];
  evidenceIds: string[];
  usage: {
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
    costUsd: number;
    estimated: false;
  };
  budgetState: "ALLOW" | "WARN";
  reviewRequired: true;
  approved: false;
};

export type NativeCheckpointSaveResult = {
  created: boolean;
  checkpoint: AutoPilotCheckpoint;
};

async function sendNative<T>(
  message: Record<string, unknown>,
  timeoutMilliseconds = 10_000,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative(nativeHostName);
    const timeout = setTimeout(() => {
      port.disconnect();
      reject(new Error("Native companion request timed out"));
    }, timeoutMilliseconds);

    port.onMessage.addListener((response: NativeResponse) => {
      clearTimeout(timeout);
      port.disconnect();
      if (!response.ok) {
        reject(
          new Error(
            "error" in response ? response.error : "Native companion failed",
          ),
        );
        return;
      }
      resolve(response.data as T);
    });
    port.onDisconnect.addListener(() => {
      const lastError = chrome.runtime.lastError;
      if (!lastError) return;
      clearTimeout(timeout);
      reject(new Error(lastError.message));
    });
    port.postMessage(message);
  });
}

function objectValue(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function stringValue(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value.trim();
}

function finiteNumber(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`${label} must be a non-negative finite number`);
  }
  return value;
}

function integerValue(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value) || Number(value) < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
  return Number(value);
}

export function parseAISettings(value: unknown): AISettings {
  const candidate = objectValue(value, "AI settings");
  if (candidate.provider !== "openai") {
    throw new Error("AI settings provider is invalid");
  }
  const keySource = candidate.keySource;
  if (
    keySource !== "keychain" &&
    keySource !== "environment" &&
    keySource !== "none"
  ) {
    throw new Error("AI key source is invalid");
  }
  const booleans = [
    "enabled",
    "hardStop",
    "allowApplicationDrafts",
    "allowProfileEvidence",
    "allowResumeEvidence",
    "keyConfigured",
  ] as const;
  for (const field of booleans) {
    if (typeof candidate[field] !== "boolean") {
      throw new Error(`AI settings ${field} must be boolean`);
    }
  }
  const monthlyBudgetUsd = finiteNumber(
    candidate.monthlyBudgetUsd,
    "monthlyBudgetUsd",
  );
  const warningBudgetUsd = finiteNumber(
    candidate.warningBudgetUsd,
    "warningBudgetUsd",
  );
  if (monthlyBudgetUsd > 0 && warningBudgetUsd > monthlyBudgetUsd) {
    throw new Error("AI warning budget cannot exceed the monthly budget");
  }
  return {
    provider: "openai",
    enabled: candidate.enabled as boolean,
    model: typeof candidate.model === "string" ? candidate.model : "",
    monthlyBudgetUsd,
    warningBudgetUsd,
    hardStop: candidate.hardStop as boolean,
    allowApplicationDrafts: candidate.allowApplicationDrafts as boolean,
    allowProfileEvidence: candidate.allowProfileEvidence as boolean,
    allowResumeEvidence: candidate.allowResumeEvidence as boolean,
    keyConfigured: candidate.keyConfigured as boolean,
    keySource,
  };
}

function parseUsage(value: unknown): AIUsageSummary {
  const candidate = objectValue(value, "AI usage summary");
  return {
    month: stringValue(candidate.month, "AI usage month"),
    spentUsd: finiteNumber(candidate.spentUsd, "AI spentUsd"),
    reservedUsd: finiteNumber(candidate.reservedUsd, "AI reservedUsd"),
    projectedUsd: finiteNumber(candidate.projectedUsd, "AI projectedUsd"),
    remainingUsd: finiteNumber(candidate.remainingUsd, "AI remainingUsd"),
    requestCount: integerValue(candidate.requestCount, "AI requestCount"),
    inputTokens: integerValue(candidate.inputTokens, "AI inputTokens"),
    outputTokens: integerValue(candidate.outputTokens, "AI outputTokens"),
    estimatedCostUsd: finiteNumber(
      candidate.estimatedCostUsd,
      "AI estimatedCostUsd",
    ),
  };
}

function parsePricing(value: unknown): AIPricingStatus | null {
  if (value === null) return null;
  const candidate = objectValue(value, "AI pricing status");
  if (candidate.provider !== "openai") {
    throw new Error("AI pricing provider is invalid");
  }
  if (typeof candidate.stale !== "boolean") {
    throw new Error("AI pricing stale status is invalid");
  }
  const verifiedAt = stringValue(candidate.verifiedAt, "AI pricing verifiedAt");
  if (Number.isNaN(Date.parse(verifiedAt))) {
    throw new Error("AI pricing verifiedAt must be a timestamp");
  }
  return {
    provider: "openai",
    model: stringValue(candidate.model, "AI pricing model"),
    inputUsdPerMillionTokens: finiteNumber(
      candidate.inputUsdPerMillionTokens,
      "AI input pricing",
    ),
    outputUsdPerMillionTokens: finiteNumber(
      candidate.outputUsdPerMillionTokens,
      "AI output pricing",
    ),
    verifiedAt,
    source: stringValue(candidate.source, "AI pricing source"),
    ageDays: integerValue(candidate.ageDays, "AI pricing ageDays"),
    stale: candidate.stale,
  };
}

export function parseAIControlStatus(value: unknown): AIControlStatus {
  const candidate = objectValue(value, "AI control status");
  const guardrails = objectValue(candidate.guardrails, "AI guardrails");
  const lockedFlags = [
    "consequentialQuestionsManual",
    "protectedEvidenceExcluded",
    "ownerReviewRequired",
    "finalSubmissionManual",
  ] as const;
  for (const field of lockedFlags) {
    if (guardrails[field] !== true) {
      throw new Error(`AI guardrail ${field} must remain locked on`);
    }
  }
  if (
    !Array.isArray(guardrails.safeDraftSemanticTypes) ||
    !guardrails.safeDraftSemanticTypes.every(
      (item) => typeof item === "string" && item.trim(),
    )
  ) {
    throw new Error("AI safe draft semantic types are invalid");
  }
  return {
    settings: parseAISettings(candidate.settings),
    usage: parseUsage(candidate.usage),
    pricing: parsePricing(candidate.pricing),
    guardrails: {
      safeDraftSemanticTypes: [
        ...guardrails.safeDraftSemanticTypes,
      ] as string[],
      consequentialQuestionsManual: true,
      protectedEvidenceExcluded: true,
      ownerReviewRequired: true,
      finalSubmissionManual: true,
    },
  };
}

function parseAIDraftRecord(value: unknown): AIDraftRecord {
  const candidate = objectValue(value, "AI draft");
  const statuses = new Set([
    "DRAFT",
    "APPROVED",
    "REJECTED",
    "SUPERSEDED",
    "USED",
  ]);
  if (typeof candidate.status !== "string" || !statuses.has(candidate.status)) {
    throw new Error("AI draft status is invalid");
  }
  if (candidate.provider !== "openai") {
    throw new Error("AI draft provider is invalid");
  }
  const contentSha256 = stringValue(
    candidate.contentSha256,
    "AI draft contentSha256",
  );
  if (!/^[a-f0-9]{64}$/.test(contentSha256)) {
    throw new Error("AI draft content digest is invalid");
  }
  if (
    !Array.isArray(candidate.evidenceIds) ||
    !candidate.evidenceIds.every(
      (item) => typeof item === "string" && item.trim(),
    )
  ) {
    throw new Error("AI draft evidenceIds are invalid");
  }
  if (!Array.isArray(candidate.claims)) {
    throw new Error("AI draft claims are invalid");
  }
  const claims = candidate.claims.map((item) => {
    const claim = objectValue(item, "AI draft claim");
    if (
      !Array.isArray(claim.evidenceIds) ||
      !claim.evidenceIds.every(
        (entry) => typeof entry === "string" && entry.trim(),
      )
    ) {
      throw new Error("AI draft claim evidence is invalid");
    }
    return {
      claimId: stringValue(claim.claimId, "AI draft claimId"),
      text: stringValue(claim.text, "AI draft claim text"),
      evidenceIds: [...claim.evidenceIds] as string[],
    };
  });
  const usage = objectValue(candidate.usage, "AI draft usage");
  const timestamp = (input: unknown, label: string): string => {
    const result = stringValue(input, label);
    if (Number.isNaN(Date.parse(result)))
      throw new Error(`${label} is invalid`);
    return result;
  };
  const nullableTimestamp = (input: unknown, label: string): string | null =>
    input === null ? null : timestamp(input, label);
  return {
    draftId: stringValue(candidate.draftId, "AI draftId"),
    applicationId: stringValue(candidate.applicationId, "AI applicationId"),
    pageId: stringValue(candidate.pageId, "AI pageId"),
    questionId: stringValue(candidate.questionId, "AI questionId"),
    controlId: stringValue(candidate.controlId, "AI controlId"),
    questionFingerprint: stringValue(
      candidate.questionFingerprint,
      "AI question fingerprint",
    ),
    semanticType: stringValue(candidate.semanticType, "AI semantic type"),
    provider: "openai",
    model: stringValue(candidate.model, "AI model"),
    responseId: stringValue(candidate.responseId, "AI responseId"),
    originalText: stringValue(candidate.originalText, "AI original text"),
    currentText: stringValue(candidate.currentText, "AI current text"),
    contentSha256,
    status: candidate.status as AIDraftStatus,
    evidenceIds: [...candidate.evidenceIds] as string[],
    claims,
    usage: {
      inputTokens: integerValue(usage.inputTokens, "AI draft inputTokens"),
      outputTokens: integerValue(usage.outputTokens, "AI draft outputTokens"),
      totalTokens: integerValue(usage.totalTokens, "AI draft totalTokens"),
      costUsd: finiteNumber(usage.costUsd, "AI draft costUsd"),
      estimated: usage.estimated === true,
    },
    generatedAt: timestamp(candidate.generatedAt, "AI generatedAt"),
    updatedAt: timestamp(candidate.updatedAt, "AI updatedAt"),
    approvedAt: nullableTimestamp(candidate.approvedAt, "AI approvedAt"),
    usedAt: nullableTimestamp(candidate.usedAt, "AI usedAt"),
  };
}

function parseCheckpointSaveResult(value: unknown): NativeCheckpointSaveResult {
  const candidate = objectValue(value, "Native checkpoint save response");
  if (typeof candidate.created !== "boolean") {
    throw new Error(
      "Native checkpoint save response is missing created status",
    );
  }
  return {
    created: candidate.created,
    checkpoint: parseAutoPilotCheckpoint(candidate.checkpoint),
  };
}

function parseCreatedResult(
  value: unknown,
  label: string,
): { created: boolean } {
  const candidate = objectValue(value, label);
  if (typeof candidate.created !== "boolean") {
    throw new Error(`${label} response is missing created status`);
  }
  return { created: candidate.created };
}

export async function getNativeHealth(
  timeoutMilliseconds = 3_000,
): Promise<unknown> {
  return sendNative({ type: "PING" }, timeoutMilliseconds);
}

export async function getNativeProfileSnapshot(): Promise<ProfileSnapshot | null> {
  const candidate = await sendNative<unknown>({
    type: "GET_PROFILE_SNAPSHOT",
  });
  return candidate === null ? null : parseProfileSnapshot(candidate);
}

export async function saveNativeProfileSnapshot(
  snapshot: ProfileSnapshot,
): Promise<void> {
  await sendNative({
    type: "SAVE_PROFILE_SNAPSHOT",
    payload: parseProfileSnapshot(snapshot),
  });
}

export async function ensureNativeApplication(
  applicationId: string,
  observedAt: string,
): Promise<{ created: boolean }> {
  const normalizedApplicationId = applicationId.trim();
  if (!normalizedApplicationId) {
    throw new Error("applicationId must be a non-empty string");
  }
  if (
    !/^\d{4}-\d{2}-\d{2}T/.test(observedAt) ||
    Number.isNaN(Date.parse(observedAt))
  ) {
    throw new Error("observedAt must be an ISO timestamp");
  }
  const result = await sendNative<unknown>({
    type: "ENSURE_APPLICATION",
    payload: {
      applicationId: normalizedApplicationId,
      observedAt,
    },
  });
  return parseCreatedResult(result, "Native application ensure");
}

export async function saveNativeApplicationCheckpoint(
  checkpoint: AutoPilotCheckpoint,
): Promise<NativeCheckpointSaveResult> {
  const canonical = parseAutoPilotCheckpoint(checkpoint);
  const result = await sendNative<unknown>({
    type: "SAVE_APPLICATION_CHECKPOINT",
    payload: canonical,
  });
  return parseCheckpointSaveResult(result);
}

export async function getLatestNativeApplicationCheckpoint(
  applicationId: string,
): Promise<AutoPilotCheckpoint | null> {
  const normalizedApplicationId = applicationId.trim();
  if (!normalizedApplicationId) {
    throw new Error("applicationId must be a non-empty string");
  }
  const result = await sendNative<unknown>({
    type: "GET_LATEST_APPLICATION_CHECKPOINT",
    payload: { applicationId: normalizedApplicationId },
  });
  return result === null ? null : parseAutoPilotCheckpoint(result);
}

export async function getAISettings(): Promise<AISettings> {
  return parseAISettings(
    await sendNative<unknown>({ type: "GET_AI_SETTINGS" }),
  );
}

export async function saveAISettings(
  settings: AISettings,
): Promise<AISettings> {
  return parseAISettings(
    await sendNative<unknown>({
      type: "SAVE_AI_SETTINGS",
      payload: {
        provider: settings.provider,
        enabled: settings.enabled,
        model: settings.model,
        monthlyBudgetUsd: settings.monthlyBudgetUsd,
        warningBudgetUsd: settings.warningBudgetUsd,
        hardStop: settings.hardStop,
        allowApplicationDrafts: settings.allowApplicationDrafts,
        allowProfileEvidence: settings.allowProfileEvidence,
        allowResumeEvidence: settings.allowResumeEvidence,
      },
    }),
  );
}

export async function setOpenAIKey(apiKey: string): Promise<AISettings> {
  return parseAISettings(
    await sendNative<unknown>({
      type: "SET_OPENAI_API_KEY",
      payload: { apiKey },
    }),
  );
}

export async function deleteOpenAIKey(): Promise<AISettings> {
  return parseAISettings(
    await sendNative<unknown>({ type: "DELETE_OPENAI_API_KEY" }),
  );
}

export async function testOpenAIConnection(): Promise<{ modelCount: number }> {
  return sendNative<{ modelCount: number }>(
    { type: "TEST_OPENAI_CONNECTION" },
    15_000,
  );
}

export async function listOpenAIModels(): Promise<string[]> {
  const result = await sendNative<{ models: string[] }>(
    { type: "LIST_OPENAI_MODELS" },
    15_000,
  );
  return result.models;
}

export async function getAIControlStatus(): Promise<AIControlStatus> {
  return parseAIControlStatus(
    await sendNative<unknown>({ type: "GET_AI_CONTROL_STATUS" }),
  );
}

export async function previewAIDraft(
  request: AIDraftRequest,
): Promise<AIDraftPreview> {
  return sendNative<AIDraftPreview>({
    type: "PREVIEW_AI_DRAFT",
    payload: request,
  });
}

export async function generateAIDraft(
  request: AIDraftRequest,
): Promise<AIDraftResult> {
  return sendNative<AIDraftResult>(
    { type: "GENERATE_AI_DRAFT", payload: request },
    60_000,
  );
}

export async function listAIDrafts(
  applicationId: string,
  pageId?: string,
): Promise<AIDraftRecord[]> {
  const result = await sendNative<unknown>({
    type: "LIST_AI_DRAFTS",
    payload: { applicationId, pageId },
  });
  if (!Array.isArray(result)) throw new Error("AI draft list is invalid");
  return result.map(parseAIDraftRecord);
}

export async function getApprovedAIDraft(
  request: AIDraftRequest,
): Promise<AIDraftRecord | null> {
  const result = await sendNative<unknown>({
    type: "GET_APPROVED_AI_DRAFT",
    payload: request,
  });
  return result === null ? null : parseAIDraftRecord(result);
}

export async function updateAIDraft(
  draftId: string,
  text: string,
  expectedSha256: string,
): Promise<AIDraftRecord> {
  return parseAIDraftRecord(
    await sendNative<unknown>({
      type: "UPDATE_AI_DRAFT",
      payload: { draftId, text, expectedSha256 },
    }),
  );
}

export async function approveAIDraft(
  draftId: string,
  expectedSha256: string,
): Promise<AIDraftRecord> {
  return parseAIDraftRecord(
    await sendNative<unknown>({
      type: "APPROVE_AI_DRAFT",
      payload: { draftId, expectedSha256 },
    }),
  );
}

export async function rejectAIDraft(draftId: string): Promise<AIDraftRecord> {
  return parseAIDraftRecord(
    await sendNative<unknown>({
      type: "REJECT_AI_DRAFT",
      payload: { draftId },
    }),
  );
}

export async function markAIDraftUsed(draftId: string): Promise<AIDraftRecord> {
  return parseAIDraftRecord(
    await sendNative<unknown>({
      type: "MARK_AI_DRAFT_USED",
      payload: { draftId },
    }),
  );
}

export type InteractionRecipeStrategy =
  | "ARIA_COMBOBOX"
  | "ARIA_RADIO"
  | "ARIA_BOOLEAN"
  | "CUSTOM_DATE"
  | "CUSTOM_MULTI_SELECT";

export type InteractionRecipeStatus = {
  recipeId: string;
  componentFingerprint: string;
  semanticType: string;
  siteOrigin: string;
  strategy: InteractionRecipeStrategy;
  state: "SHADOW" | "PROMOTED" | "ROLLED_BACK";
  version: number;
  actions: unknown[];
  attemptInserted?: boolean;
  verifiedAttempts?: number;
  verifiedSuccesses?: number;
};

function parseInteractionRecipe(
  value: unknown,
): InteractionRecipeStatus | null {
  if (value === null) return null;
  const candidate = objectValue(value, "Interaction recipe");
  const strategies = new Set([
    "ARIA_COMBOBOX",
    "ARIA_RADIO",
    "ARIA_BOOLEAN",
    "CUSTOM_DATE",
    "CUSTOM_MULTI_SELECT",
  ]);
  const states = new Set(["SHADOW", "PROMOTED", "ROLLED_BACK"]);
  if (
    typeof candidate.strategy !== "string" ||
    !strategies.has(candidate.strategy)
  ) {
    throw new Error("Interaction recipe strategy is invalid");
  }
  if (typeof candidate.state !== "string" || !states.has(candidate.state)) {
    throw new Error("Interaction recipe state is invalid");
  }
  if (!Array.isArray(candidate.actions)) {
    throw new Error("Interaction recipe actions are invalid");
  }
  const result: InteractionRecipeStatus = {
    recipeId: stringValue(candidate.recipeId, "Interaction recipeId"),
    componentFingerprint: stringValue(
      candidate.componentFingerprint,
      "Interaction component fingerprint",
    ),
    semanticType: stringValue(
      candidate.semanticType,
      "Interaction semantic type",
    ),
    siteOrigin: stringValue(candidate.siteOrigin, "Interaction site origin"),
    strategy: candidate.strategy as InteractionRecipeStrategy,
    state: candidate.state as InteractionRecipeStatus["state"],
    version: integerValue(candidate.version, "Interaction recipe version"),
    actions: [...candidate.actions],
  };
  if (typeof candidate.attemptInserted === "boolean") {
    result.attemptInserted = candidate.attemptInserted;
  }
  if (candidate.verifiedAttempts !== undefined) {
    result.verifiedAttempts = integerValue(
      candidate.verifiedAttempts,
      "Interaction verified attempts",
    );
  }
  if (candidate.verifiedSuccesses !== undefined) {
    result.verifiedSuccesses = integerValue(
      candidate.verifiedSuccesses,
      "Interaction verified successes",
    );
  }
  return result;
}

export async function getPromotedInteractionRecipe(input: {
  siteOrigin: string;
  componentFingerprint: string;
  semanticType: string;
}): Promise<InteractionRecipeStatus | null> {
  return parseInteractionRecipe(
    await sendNative<unknown>({
      type: "GET_INTERACTION_RECIPE",
      payload: input,
    }),
  );
}

export async function recordInteractionRecipeAttempt(input: {
  attemptId: string;
  applicationId?: string | null;
  siteOrigin: string;
  componentFingerprint: string;
  semanticType: string;
  strategy: InteractionRecipeStrategy;
  success: boolean;
  verified: boolean;
  failureReason: string | null;
}): Promise<InteractionRecipeStatus> {
  const result = parseInteractionRecipe(
    await sendNative<unknown>({
      type: "RECORD_INTERACTION_RECIPE_ATTEMPT",
      payload: input,
    }),
  );
  if (!result) throw new Error("Native recipe attempt returned no recipe");
  return result;
}
