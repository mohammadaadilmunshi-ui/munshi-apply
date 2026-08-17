import {
  jobSignalDimensions,
  type JobSignalDimension,
  type JobSignalDimensionResult,
  type JobSignalEvidence,
  type JobSignalReport,
  type OverallJobSignal,
} from "@munshi-apply/application-model";

const nativeHostName = "systems.munshi.apply";
const dimensionSet = new Set<string>(jobSignalDimensions);
const overallSignals = new Set<OverallJobSignal>([
  "LOW",
  "MODERATE",
  "HIGH",
  "INSUFFICIENT_DATA",
]);
const severities = new Set<JobSignalEvidence["severity"]>([
  "LOW",
  "MODERATE",
  "HIGH",
]);

type NativeResponse =
  { ok: true; data?: unknown } | { ok: false; error: string };

export type PersistedJobSignalReport = Omit<JobSignalReport, "disclaimer"> & {
  reportId: string;
  applicationId: string;
  sourceFingerprint: string;
  evaluatedAt: string;
};

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

function timestamp(value: unknown, label: string): string {
  const result = requiredString(value, label);
  if (
    Number.isNaN(Date.parse(result)) ||
    !/(?:Z|[+-]\d{2}:\d{2})$/i.test(result)
  ) {
    throw new Error(`${label} must be a timezone-aware ISO timestamp`);
  }
  return result;
}

function boundedScore(value: unknown, label: string): number | null {
  if (value === null) return null;
  if (!Number.isInteger(value) || Number(value) < 0 || Number(value) > 100) {
    throw new Error(`${label} must be null or an integer from 0 to 100`);
  }
  return Number(value);
}

function confidence(value: unknown, label: string): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value < 0 ||
    value > 1
  ) {
    throw new Error(`${label} must be a finite number from 0 to 1`);
  }
  return value;
}

function stringArray(value: unknown, label: string): string[] {
  if (
    !Array.isArray(value) ||
    !value.every((item) => typeof item === "string" && item.trim())
  ) {
    throw new Error(`${label} must be an array of non-empty strings`);
  }
  const result = value.map((item) => String(item).trim());
  if (new Set(result).size !== result.length) {
    throw new Error(`${label} must not contain duplicates`);
  }
  return result;
}

function dimensionValue(value: unknown, label: string): JobSignalDimension {
  const result = requiredString(value, label);
  if (!dimensionSet.has(result)) {
    throw new Error(`${label} is not a canonical Job Signal dimension`);
  }
  return result as JobSignalDimension;
}

function parseDimensionResult(
  value: unknown,
  expectedDimension: JobSignalDimension,
): JobSignalDimensionResult {
  const candidate = objectValue(value, `Job Signal dimension ${expectedDimension}`);
  const dimension = dimensionValue(
    candidate.dimension,
    `Job Signal dimension ${expectedDimension}.dimension`,
  );
  if (dimension !== expectedDimension) {
    throw new Error(`Job Signal dimension ${expectedDimension} does not match its key`);
  }
  return {
    dimension,
    score: boundedScore(
      candidate.score,
      `Job Signal dimension ${expectedDimension}.score`,
    ),
    confidence: confidence(
      candidate.confidence,
      `Job Signal dimension ${expectedDimension}.confidence`,
    ),
    evidenceIds: stringArray(
      candidate.evidenceIds,
      `Job Signal dimension ${expectedDimension}.evidenceIds`,
    ),
  };
}

function parseDimensions(
  value: unknown,
): Record<JobSignalDimension, JobSignalDimensionResult> {
  const candidate = objectValue(value, "Job Signal dimensions");
  const keys = Object.keys(candidate);
  if (
    keys.length !== jobSignalDimensions.length ||
    keys.some((key) => !dimensionSet.has(key))
  ) {
    throw new Error("Job Signal dimensions must contain the complete canonical ontology");
  }
  return {
    ROLE_AMBIGUITY: parseDimensionResult(
      candidate.ROLE_AMBIGUITY,
      "ROLE_AMBIGUITY",
    ),
    RESPONSIBILITY_BREADTH: parseDimensionResult(
      candidate.RESPONSIBILITY_BREADTH,
      "RESPONSIBILITY_BREADTH",
    ),
    QUALIFICATION_INFLATION: parseDimensionResult(
      candidate.QUALIFICATION_INFLATION,
      "QUALIFICATION_INFLATION",
    ),
    WORKLOAD_PRESSURE: parseDimensionResult(
      candidate.WORKLOAD_PRESSURE,
      "WORKLOAD_PRESSURE",
    ),
    SCHEDULE_INTENSITY: parseDimensionResult(
      candidate.SCHEDULE_INTENSITY,
      "SCHEDULE_INTENSITY",
    ),
    TRAVEL_BURDEN: parseDimensionResult(
      candidate.TRAVEL_BURDEN,
      "TRAVEL_BURDEN",
    ),
    COMPENSATION_CLARITY: parseDimensionResult(
      candidate.COMPENSATION_CLARITY,
      "COMPENSATION_CLARITY",
    ),
    SENIORITY_ALIGNMENT: parseDimensionResult(
      candidate.SENIORITY_ALIGNMENT,
      "SENIORITY_ALIGNMENT",
    ),
    ROLE_STABILITY: parseDimensionResult(
      candidate.ROLE_STABILITY,
      "ROLE_STABILITY",
    ),
    LOCATION_CONSTRAINTS: parseDimensionResult(
      candidate.LOCATION_CONSTRAINTS,
      "LOCATION_CONSTRAINTS",
    ),
    WORK_AUTHORIZATION_RISK: parseDimensionResult(
      candidate.WORK_AUTHORIZATION_RISK,
      "WORK_AUTHORIZATION_RISK",
    ),
    APPLICATION_FRICTION: parseDimensionResult(
      candidate.APPLICATION_FRICTION,
      "APPLICATION_FRICTION",
    ),
  };
}

function parseSignals(value: unknown): JobSignalEvidence[] {
  if (!Array.isArray(value)) {
    throw new Error("Job Signal signals must be an array");
  }
  const signalIds = new Set<string>();
  return value.map((item, index) => {
    const candidate = objectValue(item, `Job Signal signal ${index}`);
    const signalId = requiredString(
      candidate.signalId,
      `Job Signal signal ${index}.signalId`,
    );
    if (signalIds.has(signalId)) {
      throw new Error("Job Signal signalId values must be unique");
    }
    signalIds.add(signalId);
    const severity = requiredString(
      candidate.severity,
      `Job Signal signal ${index}.severity`,
    );
    if (!severities.has(severity as JobSignalEvidence["severity"])) {
      throw new Error(`Job Signal signal ${index}.severity is invalid`);
    }
    return {
      signalId,
      dimension: dimensionValue(
        candidate.dimension,
        `Job Signal signal ${index}.dimension`,
      ),
      severity: severity as JobSignalEvidence["severity"],
      evidence: requiredString(
        candidate.evidence,
        `Job Signal signal ${index}.evidence`,
      ),
      explanation: requiredString(
        candidate.explanation,
        `Job Signal signal ${index}.explanation`,
      ),
    };
  });
}

function validateEvidenceLinks(
  dimensions: Record<JobSignalDimension, JobSignalDimensionResult>,
  signals: readonly JobSignalEvidence[],
): void {
  const byId = new Map(signals.map((signal) => [signal.signalId, signal]));
  const referenced = new Set<string>();
  for (const dimension of jobSignalDimensions) {
    for (const signalId of dimensions[dimension].evidenceIds) {
      const signal = byId.get(signalId);
      if (!signal || signal.dimension !== dimension || referenced.has(signalId)) {
        throw new Error("Job Signal evidence links are inconsistent");
      }
      referenced.add(signalId);
    }
  }
  if (referenced.size !== signals.length) {
    throw new Error("Every Job Signal evidence item must be referenced exactly once");
  }
}

export function parsePersistedJobSignalReport(
  value: unknown,
): PersistedJobSignalReport {
  const candidate = objectValue(value, "Persisted Job Signal report");
  const overallSignal = requiredString(
    candidate.overallSignal,
    "Job Signal overallSignal",
  ) as OverallJobSignal;
  if (!overallSignals.has(overallSignal)) {
    throw new Error("Job Signal overallSignal is invalid");
  }
  const overallScore = boundedScore(
    candidate.overallScore,
    "Job Signal overallScore",
  );
  if (overallSignal === "INSUFFICIENT_DATA" && overallScore !== null) {
    throw new Error("INSUFFICIENT_DATA Job Signal report must not include a score");
  }
  if (overallSignal !== "INSUFFICIENT_DATA" && overallScore === null) {
    throw new Error("Scored Job Signal report requires overallScore");
  }
  const dimensions = parseDimensions(candidate.dimensions);
  const signals = parseSignals(candidate.signals);
  validateEvidenceLinks(dimensions, signals);
  return {
    reportId: requiredString(candidate.reportId, "Job Signal reportId"),
    applicationId: requiredString(
      candidate.applicationId,
      "Job Signal applicationId",
    ),
    sourceFingerprint: requiredString(
      candidate.sourceFingerprint,
      "Job Signal sourceFingerprint",
    ),
    evaluatedAt: timestamp(candidate.evaluatedAt, "Job Signal evaluatedAt"),
    overallSignal,
    overallScore,
    dimensions,
    signals,
  };
}

async function sendNativeJobSignal<T>(
  message: Record<string, unknown>,
  timeoutMilliseconds = 5_000,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative(nativeHostName);
    const timeout = window.setTimeout(() => {
      port.disconnect();
      reject(new Error("Native Job Signal request timed out"));
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

export async function saveNativeJobSignalReport(input: {
  reportId: string;
  applicationId: string;
  sourceFingerprint: string;
  evaluatedAt: string;
  report: JobSignalReport;
}): Promise<PersistedJobSignalReport> {
  const response = await sendNativeJobSignal<unknown>({
    type: "SAVE_JOB_SIGNAL_REPORT",
    payload: {
      reportId: input.reportId.trim(),
      applicationId: input.applicationId.trim(),
      sourceFingerprint: input.sourceFingerprint.trim(),
      evaluatedAt: timestamp(input.evaluatedAt, "Job Signal evaluatedAt"),
      overallSignal: input.report.overallSignal,
      overallScore: input.report.overallScore,
      dimensions: input.report.dimensions,
      signals: input.report.signals,
    },
  });
  return parsePersistedJobSignalReport(response);
}

export async function getLatestNativeJobSignalReport(
  applicationId: string,
): Promise<PersistedJobSignalReport | null> {
  const normalizedApplicationId = applicationId.trim();
  if (!normalizedApplicationId) {
    throw new Error("applicationId must be a non-empty string");
  }
  const response = await sendNativeJobSignal<unknown>({
    type: "GET_LATEST_JOB_SIGNAL_REPORT",
    payload: { applicationId: normalizedApplicationId },
  });
  return response === null ? null : parsePersistedJobSignalReport(response);
}
