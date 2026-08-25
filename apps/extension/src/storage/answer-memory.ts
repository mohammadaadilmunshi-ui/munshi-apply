import type { SemanticType } from "@munshi-apply/contracts";
import { parseProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import { classifyQuestion } from "@munshi-apply/semantic-engine";
import {
  permanentProfileTarget,
  promoteRememberedAnswerIntoProfile,
} from "./profile-answer-promotion";

export type RememberedAnswer = {
  memoryKey: string;
  normalizedQuestion: string;
  question: string;
  semanticType: string;
  value: string;
  sensitive: boolean;
  approvedAt: string;
  updatedAt: string;
};

const databaseName = "munshi-apply-answer-memory";
const databaseVersion = 1;
const answersStore = "answers";
const maxQuestionLength = 2_000;
const maxAnswerLength = 8_000;

const contextSpecificSemanticTypes = new Set([
  "WHY_COMPANY",
  "WHY_ROLE",
  "ROLE_UNDERSTANDING",
  "RELEVANT_EXPERIENCE",
  "CAREER_TRANSITION",
  "MOTIVATION",
  "BEHAVIORAL",
  "CAREER_GOALS",
  "BEHAVIORAL_EXAMPLE",
]);

const semanticReuseTypes = new Set<SemanticType>([
  "PERSONAL",
  "FIRST_NAME",
  "MIDDLE_NAME",
  "LAST_NAME",
  "PREFERRED_NAME",
  "PRONOUNS",
  "EMAIL",
  "PHONE",
  "LINKEDIN",
  "PORTFOLIO",
  "WEBSITE",
  "STREET_ADDRESS",
  "ADDRESS_LINE_2",
  "CITY",
  "STATE_PROVINCE",
  "POSTAL_CODE",
  "COUNTRY",
  "SPONSORSHIP_CURRENT",
  "SPONSORSHIP_FUTURE",
  "IMMIGRATION_ASSISTANCE",
  "NOTICE_PERIOD",
  "RELOCATION",
  "TRAVEL",
  "SECURITY_CLEARANCE",
  "VETERAN_STATUS",
  "PROTECTED_VETERAN_STATUS",
  "DISABILITY_STATUS",
  "GENDER",
]);

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, databaseVersion);
    request.onerror = () =>
      reject(request.error ?? new Error("Answer memory open failed"));
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(answersStore)) {
        database.createObjectStore(answersStore, { keyPath: "memoryKey" });
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

function cleanQuestion(value: string): string {
  return value.trim().slice(0, maxQuestionLength);
}

export function normalizeQuestionForMemory(value: string): string {
  return cleanQuestion(value)
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/[’‘]/g, "'")
    .replace(/\*/g, " ")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Legacy exact-question key kept for backwards-compatible lookup. */
export function answerMemoryKey(question: string): string {
  return normalizeQuestionForMemory(question);
}

function inferredSemanticType(question: string): string {
  const classification = classifyQuestion(question);
  return classification.matchedRule ? classification.semanticType : "UNKNOWN";
}

export function canonicalAnswerMemoryKey(
  question: string,
  semanticType?: string,
): string {
  const normalizedQuestion = answerMemoryKey(question);
  if (!normalizedQuestion) return "";
  const resolvedSemanticType = semanticType || inferredSemanticType(question);
  if (
    semanticReuseTypes.has(resolvedSemanticType as SemanticType) &&
    !contextSpecificSemanticTypes.has(resolvedSemanticType)
  ) {
    return `semantic:${resolvedSemanticType}`;
  }
  return `question:${normalizedQuestion}`;
}

function candidateMemoryKeys(question: string, semanticType?: string): string[] {
  const exact = answerMemoryKey(question);
  if (!exact) return [];
  return [
    canonicalAnswerMemoryKey(question, semanticType),
    `question:${exact}`,
    exact,
  ].filter((value, index, values) => Boolean(value) && values.indexOf(value) === index);
}

export function canAutoApproveRememberedAnswer(input: {
  semanticType: string;
  controlKind: string | null | undefined;
  value: string;
}): boolean {
  if (!input.value.trim()) return false;
  if (input.value.length > 500) return false;
  if (contextSpecificSemanticTypes.has(input.semanticType)) return false;
  if (["FILE", "BUTTON"].includes(input.controlKind ?? "")) return false;
  return true;
}

async function readRememberedAnswer(memoryKey: string): Promise<RememberedAnswer | null> {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(answersStore, "readonly");
    const request = transaction.objectStore(answersStore).get(memoryKey);
    request.onerror = () =>
      reject(request.error ?? new Error("Answer memory read failed"));
    request.onsuccess = () => {
      const value = request.result as RememberedAnswer | undefined;
      resolve(value ?? null);
    };
    transaction.oncomplete = () => database.close();
  });
}

export async function getRememberedAnswer(
  question: string,
  semanticType?: string,
): Promise<RememberedAnswer | null> {
  for (const memoryKey of candidateMemoryKeys(question, semanticType)) {
    const remembered = await readRememberedAnswer(memoryKey);
    if (remembered) return remembered;
  }
  return null;
}

type RuntimeResponse =
  | { ok: true; data?: unknown }
  | { ok: false; error: string };

async function promoteToPermanentProfile(input: {
  semanticType: string;
  value: string;
  sensitive: boolean;
  approvedAt: string;
}): Promise<void> {
  if (!permanentProfileTarget(input.semanticType)) return;
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return;
  try {
    const profileResponse = (await chrome.runtime.sendMessage({
      type: "GET_PROFILE",
    })) as RuntimeResponse | undefined;
    if (!profileResponse?.ok || profileResponse.data == null) return;
    const profile = parseProfileSnapshot(profileResponse.data);
    const promotion = promoteRememberedAnswerIntoProfile(profile, input);
    if (!promotion.changed) return;
    const saveResponse = (await chrome.runtime.sendMessage({
      type: "SAVE_PROFILE",
      payload: promotion.profile,
    })) as RuntimeResponse | undefined;
    if (!saveResponse?.ok) {
      throw new Error(saveResponse?.error ?? "Profile promotion failed");
    }
  } catch {
    // Browser answer memory remains available even when the profile authority is
    // temporarily unavailable. A later approved answer can retry promotion.
  }
}

export async function saveRememberedAnswer(input: {
  question: string;
  semanticType: string;
  value: string;
  sensitive: boolean;
  approvedAt?: string;
}): Promise<RememberedAnswer> {
  const question = cleanQuestion(input.question);
  const normalizedQuestion = answerMemoryKey(question);
  const memoryKey = canonicalAnswerMemoryKey(question, input.semanticType);
  const value = input.value.trim().slice(0, maxAnswerLength);
  if (!memoryKey)
    throw new Error(
      "A question is required before an answer can be remembered",
    );
  if (!value)
    throw new Error("An answer is required before it can be remembered");

  const existing = await getRememberedAnswer(question, input.semanticType);
  const timestamp = new Date().toISOString();
  const approvedAt = input.approvedAt ?? timestamp;
  const record: RememberedAnswer = {
    memoryKey,
    normalizedQuestion,
    question,
    semanticType: input.semanticType,
    value,
    sensitive: Boolean(input.sensitive),
    approvedAt,
    updatedAt: timestamp,
  };

  if (
    existing &&
    existing.memoryKey === record.memoryKey &&
    existing.value === record.value &&
    existing.semanticType === record.semanticType &&
    existing.sensitive === record.sensitive
  ) {
    void promoteToPermanentProfile({
      semanticType: record.semanticType,
      value: record.value,
      sensitive: record.sensitive,
      approvedAt: record.approvedAt,
    });
    return existing;
  }

  const database = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(answersStore, "readwrite");
    transaction.objectStore(answersStore).put(record);
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("Answer memory write failed"));
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
  });

  void promoteToPermanentProfile({
    semanticType: record.semanticType,
    value: record.value,
    sensitive: record.sensitive,
    approvedAt: record.approvedAt,
  });
  return record;
}

export async function forgetRememberedAnswer(question: string): Promise<void> {
  const keys = candidateMemoryKeys(question);
  if (keys.length === 0) return;
  const database = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(answersStore, "readwrite");
    const store = transaction.objectStore(answersStore);
    for (const memoryKey of keys) store.delete(memoryKey);
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("Answer memory delete failed"));
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
  });
}
