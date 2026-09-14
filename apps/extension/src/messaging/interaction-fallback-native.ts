import { createNativeRequestBroker } from "./native-transport";

const nativeHostName = "systems.munshi.apply";
const broker = createNativeRequestBroker({
  connect: () => chrome.runtime.connectNative(nativeHostName),
  getLastErrorMessage: () => chrome.runtime.lastError?.message,
  idleDisconnectMilliseconds: 2_000,
});

const recoveryKeys = [
  "ArrowDown",
  "ArrowUp",
  "Enter",
  "Tab",
  "Escape",
] as const;
type RecoveryKey = (typeof recoveryKeys)[number];

export type RecoveryAction =
  | { type: "FOCUS" }
  | { type: "CLICK" }
  | { type: "TYPE"; valueSource: "ANSWER" }
  | { type: "SELECT_EXACT_OPTION" }
  | { type: "KEY"; key: RecoveryKey }
  | {
      type: "WAIT_FOR_STATE";
      state: "OPTIONS_VISIBLE" | "VALUE_COMMITTED";
    };

export type InteractionRecoveryProposal = {
  actions: RecoveryAction[];
  reason: string;
  provider: string;
  model: string;
  teacherKind: "MODEL" | "LOCAL_MODEL";
  sourceLane: "AUTOAPPLY_FALLBACK";
  providerCallMade: true;
  valueBearingInputSent: false;
};

export type InteractionRecoveryRequest = {
  siteOrigin: string;
  componentFingerprint: string;
  semanticType: string;
  controlKind: string;
  label?: string;
  role?: string;
  hasPopup?: string;
  atsFamily?: string;
  options?: string[];
  failureReason?: string;
  reversible: true;
  sensitive: false;
  authenticationBoundary: false;
  finalSubmit: false;
};

export type TeachCaptureRequest = {
  observationId: string;
  applicationId?: string | null;
  siteOrigin: string;
  componentFingerprint: string;
  semanticType: string;
  atsFamily?: string | null;
  tenantKey?: string | null;
  uiFingerprint?: string | null;
  questionFingerprint?: string | null;
  teacherKind: "MODEL" | "LOCAL_MODEL" | "DETERMINISTIC_RECOVERY";
  teacherProvider?: string | null;
  sourceLane: string;
  actions: RecoveryAction[];
  verifiedSuccess: true;
};

function objectValue(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function textValue(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value.trim();
}

function isRecoveryKey(value: unknown): value is RecoveryKey {
  return (
    typeof value === "string" && recoveryKeys.includes(value as RecoveryKey)
  );
}

function parseAction(value: unknown): RecoveryAction {
  const action = objectValue(value, "recovery action");
  switch (action.type) {
    case "FOCUS":
    case "CLICK":
    case "SELECT_EXACT_OPTION":
      return { type: action.type };
    case "TYPE":
      if (action.valueSource !== "ANSWER") {
        throw new Error("Recovery TYPE must use ANSWER");
      }
      return { type: "TYPE", valueSource: "ANSWER" };
    case "KEY":
      if (!isRecoveryKey(action.key)) {
        throw new Error("Recovery key is not allowed");
      }
      return { type: "KEY", key: action.key };
    case "WAIT_FOR_STATE": {
      const state = action.state;
      if (state !== "OPTIONS_VISIBLE" && state !== "VALUE_COMMITTED") {
        throw new Error("Recovery wait state is not allowed");
      }
      return { type: "WAIT_FOR_STATE", state };
    }
    default:
      throw new Error("Recovery action is not allowed");
  }
}

function parseProposal(value: unknown): InteractionRecoveryProposal {
  const candidate = objectValue(value, "interaction recovery proposal");
  if (
    !Array.isArray(candidate.actions) ||
    candidate.actions.length < 1 ||
    candidate.actions.length > 16
  ) {
    throw new Error("Recovery proposal actions are invalid");
  }
  if (
    candidate.providerCallMade !== true ||
    candidate.valueBearingInputSent !== false
  ) {
    throw new Error(
      "Recovery proposal violated the value-free provider contract",
    );
  }
  const teacherKind = candidate.teacherKind;
  if (teacherKind !== "MODEL" && teacherKind !== "LOCAL_MODEL") {
    throw new Error("Recovery teacher kind is invalid");
  }
  if (candidate.sourceLane !== "AUTOAPPLY_FALLBACK") {
    throw new Error("Recovery source lane is invalid");
  }
  return {
    actions: candidate.actions.map(parseAction),
    reason: textValue(candidate.reason, "recovery reason"),
    provider: textValue(candidate.provider, "recovery provider"),
    model: textValue(candidate.model, "recovery model"),
    teacherKind,
    sourceLane: "AUTOAPPLY_FALLBACK",
    providerCallMade: true,
    valueBearingInputSent: false,
  };
}

export async function proposeInteractionRecovery(
  input: InteractionRecoveryRequest,
): Promise<InteractionRecoveryProposal> {
  const response = await broker.request<unknown>(
    { type: "PROPOSE_INTERACTION_RECOVERY", payload: input },
    40_000,
  );
  return parseProposal(response);
}

export async function captureTeachMunshiLesson(
  input: TeachCaptureRequest,
): Promise<void> {
  await broker.request<unknown>(
    { type: "CAPTURE_TEACH_MUNSHI_LESSON", payload: input },
    5_000,
  );
}
