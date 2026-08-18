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

export function answerMemoryKey(question: string): string {
  return normalizeQuestionForMemory(question);
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

export async function getRememberedAnswer(
  question: string,
): Promise<RememberedAnswer | null> {
  const memoryKey = answerMemoryKey(question);
  if (!memoryKey) return null;
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

export async function saveRememberedAnswer(input: {
  question: string;
  semanticType: string;
  value: string;
  sensitive: boolean;
  approvedAt?: string;
}): Promise<RememberedAnswer> {
  const question = cleanQuestion(input.question);
  const memoryKey = answerMemoryKey(question);
  const value = input.value.trim().slice(0, maxAnswerLength);
  if (!memoryKey) throw new Error("A question is required before an answer can be remembered");
  if (!value) throw new Error("An answer is required before it can be remembered");

  const existing = await getRememberedAnswer(question);
  const timestamp = new Date().toISOString();
  const record: RememberedAnswer = {
    memoryKey,
    normalizedQuestion: memoryKey,
    question,
    semanticType: input.semanticType,
    value,
    sensitive: Boolean(input.sensitive),
    approvedAt: input.approvedAt ?? timestamp,
    updatedAt: timestamp,
  };

  if (
    existing &&
    existing.value === record.value &&
    existing.semanticType === record.semanticType &&
    existing.sensitive === record.sensitive
  ) {
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
  return record;
}

export async function forgetRememberedAnswer(question: string): Promise<void> {
  const memoryKey = answerMemoryKey(question);
  if (!memoryKey) return;
  const database = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(answersStore, "readwrite");
    transaction.objectStore(answersStore).delete(memoryKey);
    transaction.onerror = () =>
      reject(transaction.error ?? new Error("Answer memory delete failed"));
    transaction.oncomplete = () => {
      database.close();
      resolve();
    };
  });
}
