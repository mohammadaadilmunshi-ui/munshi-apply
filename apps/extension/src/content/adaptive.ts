export type AdaptiveTiming = {
  optionTimeoutMs: number;
  pollIntervalMs: number;
  verificationTimeoutMs: number;
  stabilityQuietMs: number;
  stabilityTimeoutMs: number;
};

export type ValidationCode =
  | "NONE"
  | "REQUIRED"
  | "FORMAT"
  | "TOO_LONG"
  | "TOO_SHORT"
  | "RANGE"
  | "PATTERN"
  | "FILE_TYPE"
  | "FILE_SIZE"
  | "UNKNOWN";

export type FileFingerprintState = "NONE" | "PENDING" | "READY" | "ERROR";

export type FileFingerprint = {
  state: FileFingerprintState;
  count: number;
  sha256: string | null;
  size: number | null;
  mimeType: string | null;
};

const fileFingerprints = new WeakMap<HTMLInputElement, FileFingerprint>();

export function compactText(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

export function normalizedText(value: string | null | undefined): string {
  return compactText(value).toLocaleLowerCase("en-US");
}

function normalizedToken(value: string): string {
  return normalizedText(value)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[.]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

const booleanYes = new Set(["yes", "true", "1", "checked"]);
const booleanNo = new Set(["no", "false", "0", "unchecked"]);

const statePairs = [
  ["AL", "Alabama"],
  ["AK", "Alaska"],
  ["AZ", "Arizona"],
  ["AR", "Arkansas"],
  ["CA", "California"],
  ["CO", "Colorado"],
  ["CT", "Connecticut"],
  ["DE", "Delaware"],
  ["DC", "District of Columbia"],
  ["FL", "Florida"],
  ["GA", "Georgia"],
  ["HI", "Hawaii"],
  ["ID", "Idaho"],
  ["IL", "Illinois"],
  ["IN", "Indiana"],
  ["IA", "Iowa"],
  ["KS", "Kansas"],
  ["KY", "Kentucky"],
  ["LA", "Louisiana"],
  ["ME", "Maine"],
  ["MD", "Maryland"],
  ["MA", "Massachusetts"],
  ["MI", "Michigan"],
  ["MN", "Minnesota"],
  ["MS", "Mississippi"],
  ["MO", "Missouri"],
  ["MT", "Montana"],
  ["NE", "Nebraska"],
  ["NV", "Nevada"],
  ["NH", "New Hampshire"],
  ["NJ", "New Jersey"],
  ["NM", "New Mexico"],
  ["NY", "New York"],
  ["NC", "North Carolina"],
  ["ND", "North Dakota"],
  ["OH", "Ohio"],
  ["OK", "Oklahoma"],
  ["OR", "Oregon"],
  ["PA", "Pennsylvania"],
  ["RI", "Rhode Island"],
  ["SC", "South Carolina"],
  ["SD", "South Dakota"],
  ["TN", "Tennessee"],
  ["TX", "Texas"],
  ["UT", "Utah"],
  ["VT", "Vermont"],
  ["VA", "Virginia"],
  ["WA", "Washington"],
  ["WV", "West Virginia"],
  ["WI", "Wisconsin"],
  ["WY", "Wyoming"],
] as const;

const stateKey = new Map<string, string>();
for (const [code, name] of statePairs) {
  stateKey.set(normalizedToken(code), `state:${code}`);
  stateKey.set(normalizedToken(name), `state:${code}`);
}

const monthPairs = [
  ["01", "January", "Jan"],
  ["02", "February", "Feb"],
  ["03", "March", "Mar"],
  ["04", "April", "Apr"],
  ["05", "May", "May"],
  ["06", "June", "Jun"],
  ["07", "July", "Jul"],
  ["08", "August", "Aug"],
  ["09", "September", "Sep"],
  ["10", "October", "Oct"],
  ["11", "November", "Nov"],
  ["12", "December", "Dec"],
] as const;

const monthKey = new Map<string, string>();
for (const [number, longName, shortName] of monthPairs) {
  monthKey.set(normalizedToken(number), `month:${number}`);
  monthKey.set(normalizedToken(String(Number(number))), `month:${number}`);
  monthKey.set(normalizedToken(longName), `month:${number}`);
  monthKey.set(normalizedToken(shortName), `month:${number}`);
}

const degreeClasses: ReadonlyArray<readonly [string, readonly string[]]> = [
  ["degree:bs", ["BS", "B.S.", "Bachelor of Science"]],
  ["degree:ba", ["BA", "B.A.", "Bachelor of Arts"]],
  ["degree:ms", ["MS", "M.S.", "Master of Science"]],
  ["degree:ma", ["MA", "M.A.", "Master of Arts"]],
  ["degree:mba", ["MBA", "M.B.A.", "Master of Business Administration"]],
  ["degree:phd", ["PhD", "Ph.D.", "Doctor of Philosophy"]],
];

const degreeKey = new Map<string, string>();
for (const [key, values] of degreeClasses) {
  for (const value of values) degreeKey.set(normalizedToken(value), key);
}

function contextualKey(value: string, context: string): string | null {
  const token = normalizedToken(value);
  const normalizedContext = normalizedText(context);
  if (booleanYes.has(token)) return "boolean:yes";
  if (booleanNo.has(token)) return "boolean:no";

  if (/\b(country|nation|location country)\b/.test(normalizedContext)) {
    if (
      new Set([
        "us",
        "usa",
        "u s",
        "u s a",
        "united states",
        "united states of america",
      ]).has(token)
    ) {
      return "country:US";
    }
  }

  if (/\b(state|province|region)\b/.test(normalizedContext)) {
    return stateKey.get(token) ?? null;
  }

  if (/\b(month|date|graduat|start|end|available)\b/.test(normalizedContext)) {
    const month = monthKey.get(token);
    if (month) return month;
  }

  if (/\b(degree|qualification|education)\b/.test(normalizedContext)) {
    return degreeKey.get(token) ?? null;
  }

  return null;
}

export function optionEquivalent(
  candidate: string,
  requested: string,
  context = "",
): boolean {
  const left = normalizedText(candidate);
  const right = normalizedText(requested);
  if (!left || !right) return false;
  if (left === right) return true;
  const leftKey = contextualKey(candidate, context);
  const rightKey = contextualKey(requested, context);
  return leftKey !== null && leftKey === rightKey;
}

export function parseRequestedOptionValues(value: string): string[] | null {
  const trimmed = value.trim();
  if (!trimmed) return [];
  if (trimmed.startsWith("[")) {
    try {
      const parsed: unknown = JSON.parse(trimmed);
      if (!Array.isArray(parsed) || parsed.some((item) => typeof item !== "string")) {
        return null;
      }
      return parsed.map((item) => compactText(item)).filter(Boolean);
    } catch {
      return null;
    }
  }
  return trimmed
    .split(/\r?\n|[;|,]/)
    .map(compactText)
    .filter(Boolean);
}

export function uniqueOptionCandidate<T>(
  requested: string,
  candidates: readonly { item: T; values: readonly string[] }[],
  context = "",
): T | null {
  const matches = candidates.filter((candidate) =>
    candidate.values.some((value) => optionEquivalent(value, requested, context)),
  );
  return matches.length === 1 ? matches[0]!.item : null;
}

export function booleanRequest(value: string): boolean | null {
  const normalized = normalizedToken(value);
  if (booleanYes.has(normalized)) return true;
  if (booleanNo.has(normalized)) return false;
  return null;
}

export function interactionContext(element: Element): string {
  const pieces = [
    element.getAttribute("aria-label"),
    element.getAttribute("name"),
    element.getAttribute("placeholder"),
    element.getAttribute("autocomplete"),
  ];
  if (element instanceof HTMLInputElement) {
    pieces.push(
      ...Array.from(element.labels ?? []).map((label) => label.textContent),
    );
  }
  if (element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) {
    pieces.push(...Array.from(element.labels).map((label) => label.textContent));
  }
  const labelledBy = element.getAttribute("aria-labelledby");
  if (labelledBy) {
    const root = element.getRootNode();
    if (root instanceof Document || root instanceof ShadowRoot) {
      for (const id of labelledBy.split(/\s+/).filter(Boolean)) {
        const node =
          root instanceof Document
            ? root.getElementById(id)
            : root.querySelector(`#${CSS.escape(id)}`);
        pieces.push(node?.textContent ?? "");
      }
    }
  }
  const group = element.closest("fieldset, [role='group'], [role='radiogroup']");
  pieces.push(group?.querySelector("legend")?.textContent ?? "");
  pieces.push(group?.getAttribute("aria-label") ?? "");
  return compactText(pieces.filter(Boolean).join(" "));
}

export function defaultAdaptiveTiming(): AdaptiveTiming {
  const hostname = window.location.hostname.toLocaleLowerCase("en-US");
  const workdayLike =
    hostname.includes("myworkdayjobs") || Boolean(document.querySelector("[data-automation-id]"));
  const dynamicAts =
    workdayLike ||
    hostname.includes("greenhouse") ||
    hostname.includes("lever.co") ||
    hostname.includes("ashbyhq") ||
    hostname.includes("smartrecruiters") ||
    hostname.includes("icims");
  return {
    optionTimeoutMs: workdayLike ? 3_000 : dynamicAts ? 2_000 : 1_500,
    pollIntervalMs: 25,
    verificationTimeoutMs: workdayLike ? 1_200 : 750,
    stabilityQuietMs: 90,
    stabilityTimeoutMs: dynamicAts ? 1_800 : 1_100,
  };
}

export function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export async function waitForCondition(
  verify: () => boolean,
  timeoutMilliseconds: number,
  pollIntervalMilliseconds: number,
): Promise<boolean> {
  const deadline = Date.now() + Math.max(0, timeoutMilliseconds);
  while (Date.now() <= deadline) {
    if (verify()) return true;
    await delay(Math.max(1, pollIntervalMilliseconds));
  }
  return verify();
}

export async function waitForDomStability(
  quietMilliseconds: number,
  timeoutMilliseconds: number,
): Promise<boolean> {
  const root = document.documentElement;
  if (!root || typeof MutationObserver === "undefined") {
    await delay(Math.max(0, quietMilliseconds));
    return true;
  }
  const quietMs = Math.max(0, quietMilliseconds);
  const timeoutMs = Math.max(quietMs, timeoutMilliseconds);
  return new Promise((resolve) => {
    let settled = false;
    let quietTimer = 0;
    let timeoutTimer = 0;
    const finish = (stable: boolean) => {
      if (settled) return;
      settled = true;
      observer.disconnect();
      window.clearTimeout(quietTimer);
      window.clearTimeout(timeoutTimer);
      resolve(stable);
    };
    const armQuiet = () => {
      window.clearTimeout(quietTimer);
      quietTimer = window.setTimeout(() => finish(true), quietMs);
    };
    const observer = new MutationObserver(() => armQuiet());
    observer.observe(root, {
      attributes: true,
      childList: true,
      characterData: true,
      subtree: true,
      attributeFilter: [
        "aria-activedescendant",
        "aria-busy",
        "aria-checked",
        "aria-disabled",
        "aria-expanded",
        "aria-hidden",
        "aria-invalid",
        "aria-selected",
        "class",
        "disabled",
        "hidden",
        "style",
      ],
    });
    timeoutTimer = window.setTimeout(() => finish(false), timeoutMs);
    armQuiet();
  });
}

function describedText(element: Element): string {
  const ids = [
    element.getAttribute("aria-errormessage"),
    element.getAttribute("aria-describedby"),
  ]
    .filter((value): value is string => Boolean(value))
    .flatMap((value) => value.split(/\s+/))
    .filter(Boolean);
  if (ids.length === 0) return "";
  const root = element.getRootNode();
  if (!(root instanceof Document || root instanceof ShadowRoot)) return "";
  return compactText(
    ids
      .map((id) =>
        root instanceof Document
          ? root.getElementById(id)?.textContent
          : root.querySelector(`#${CSS.escape(id)}`)?.textContent,
      )
      .filter(Boolean)
      .join(" "),
  );
}

export function validationMessageFor(element: Element): string {
  const native =
    element instanceof HTMLInputElement ||
    element instanceof HTMLSelectElement ||
    element instanceof HTMLTextAreaElement
      ? compactText(element.validationMessage)
      : "";
  return describedText(element) || native;
}

export function classifyValidationMessage(message: string): ValidationCode {
  const normalized = normalizedText(message);
  if (!normalized) return "NONE";
  if (/\b(required|must (be )?completed|please (enter|select|choose|provide))\b/.test(normalized)) {
    return "REQUIRED";
  }
  if (/\b(max(imum)?|no more than|too long|characters? or fewer)\b/.test(normalized)) {
    return "TOO_LONG";
  }
  if (/\b(min(imum)?|at least|too short)\b/.test(normalized)) return "TOO_SHORT";
  if (/\b(file type|unsupported file|pdf only|docx? only)\b/.test(normalized)) return "FILE_TYPE";
  if (/\b(file size|too large|maximum upload|upload limit)\b/.test(normalized)) return "FILE_SIZE";
  if (/\b(pattern|format|invalid (email|phone|date|url)|valid (email|phone|date|url))\b/.test(normalized)) {
    return "FORMAT";
  }
  if (/\b(range|between|greater than|less than|minimum value|maximum value)\b/.test(normalized)) {
    return "RANGE";
  }
  return "UNKNOWN";
}

export function validationFailureReason(element: Element, value?: string): string {
  if (
    value !== undefined &&
    (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) &&
    element.maxLength >= 0 &&
    value.length > element.maxLength
  ) {
    return `Value exceeds the employer's ${element.maxLength}-character limit`;
  }
  const message = validationMessageFor(element);
  if (message) return `Employer validation rejected the value: ${message}`;
  return "Control did not preserve the requested value after browser validation";
}

export function isPopupChoiceControl(element: Element): boolean {
  const role = normalizedText(element.getAttribute("role"));
  const hasPopup = normalizedText(element.getAttribute("aria-haspopup"));
  return (
    role === "combobox" ||
    hasPopup === "listbox" ||
    hasPopup === "tree" ||
    hasPopup === "grid"
  );
}

export function isAriaBooleanControl(element: Element): boolean {
  const role = normalizedText(element.getAttribute("role"));
  return role === "checkbox" || role === "switch";
}

export function isAriaRadioControl(element: Element): boolean {
  return normalizedText(element.getAttribute("role")) === "radio";
}

export function isCustomDateControl(element: Element): boolean {
  if (normalizedText(element.getAttribute("aria-haspopup")) !== "dialog") return false;
  return /\b(date|day|month|year|graduat|available|start|end)\b/.test(
    normalizedText(interactionContext(element)),
  );
}

function canonicalDate(value: string): string | null {
  const requested = value.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(requested)) return null;
  const parsed = new Date(`${requested}T00:00:00.000Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString().slice(0, 10) === requested ? requested : null;
}

function collectShadowRoots(root: Document | ShadowRoot): ShadowRoot[] {
  const result: ShadowRoot[] = [];
  for (const item of Array.from(root.querySelectorAll("*"))) {
    if (!(item instanceof HTMLElement) || !item.shadowRoot) continue;
    result.push(item.shadowRoot);
    result.push(...collectShadowRoots(item.shadowRoot));
  }
  return result;
}

function calendarSearchRoots(element: Element): Array<Document | ShadowRoot> {
  const roots: Array<Document | ShadowRoot> = [];
  const ownRoot = element.getRootNode();
  if (ownRoot instanceof Document || ownRoot instanceof ShadowRoot) roots.push(ownRoot);
  if (!roots.includes(document)) roots.push(document);
  for (const root of collectShadowRoots(document)) if (!roots.includes(root)) roots.push(root);
  return roots;
}

const monthByName = new Map<string, number>([
  ["january", 1],
  ["february", 2],
  ["march", 3],
  ["april", 4],
  ["may", 5],
  ["june", 6],
  ["july", 7],
  ["august", 8],
  ["september", 9],
  ["october", 10],
  ["november", 11],
  ["december", 12],
]);

function naturalDate(value: string): string | null {
  const text = normalizedText(value).replace(/,/g, "");
  let match = text.match(
    /^(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})\s+(\d{4})$/,
  );
  let month: number | undefined;
  let day: number | undefined;
  let year: number | undefined;
  if (match) {
    month = monthByName.get(match[1]!);
    day = Number(match[2]);
    year = Number(match[3]);
  } else {
    match = text.match(
      /^(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})$/,
    );
    if (!match) return null;
    day = Number(match[1]);
    month = monthByName.get(match[2]!);
    year = Number(match[3]);
  }
  if (!month || !day || !year) return null;
  const date = `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  return canonicalDate(date);
}

function dateForCandidate(element: Element): string | null {
  for (const attribute of ["data-date", "data-value", "datetime"]) {
    const value = element.getAttribute(attribute);
    if (!value) continue;
    const direct = canonicalDate(value.slice(0, 10));
    if (direct) return direct;
  }
  const aria = element.getAttribute("aria-label");
  if (aria) {
    const parsed = naturalDate(aria);
    if (parsed) return parsed;
  }
  return canonicalDate(compactText(element.textContent));
}

function candidateAvailable(element: HTMLElement): boolean {
  return (
    !element.hidden &&
    element.getAttribute("aria-hidden") !== "true" &&
    element.getAttribute("aria-disabled") !== "true" &&
    !element.hasAttribute("disabled")
  );
}

export async function fillCustomDateControl(
  element: HTMLElement,
  value: string,
  timing: AdaptiveTiming,
): Promise<boolean | null> {
  if (!isCustomDateControl(element)) return null;
  const requested = canonicalDate(value);
  if (!requested) return false;
  const originalValue = element instanceof HTMLInputElement ? element.value : null;
  element.focus();
  element.click();
  const deadline = Date.now() + timing.optionTimeoutMs;
  let match: HTMLElement | null = null;
  while (Date.now() <= deadline) {
    const candidates: HTMLElement[] = [];
    for (const root of calendarSearchRoots(element)) {
      for (const candidate of Array.from(
        root.querySelectorAll(
          "[role='gridcell'], [role='option'], [data-date], [data-value], time[datetime]",
        ),
      )) {
        if (
          candidate instanceof HTMLElement &&
          candidateAvailable(candidate) &&
          dateForCandidate(candidate) === requested
        ) {
          candidates.push(candidate);
        }
      }
    }
    const unique = [...new Set(candidates)];
    if (unique.length > 1) return false;
    if (unique.length === 1) {
      match = unique[0]!;
      break;
    }
    await delay(timing.pollIntervalMs);
  }
  if (!match) return false;
  match.click();
  const verified = await waitForCondition(
    () => {
      if (match?.getAttribute("aria-selected") === "true") return true;
      if (element instanceof HTMLInputElement) {
        if (element.value === requested) return true;
        if (naturalDate(element.value) === requested) return true;
      }
      return false;
    },
    timing.verificationTimeoutMs,
    timing.pollIntervalMs,
  );
  if (!verified && element instanceof HTMLInputElement && originalValue !== null) {
    element.value = originalValue;
    element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  }
  return verified;
}

export async function fillAriaBooleanControl(
  element: HTMLElement,
  value: string,
  timing: AdaptiveTiming,
): Promise<boolean | null> {
  if (!isAriaBooleanControl(element)) return null;
  if (element.getAttribute("aria-disabled") === "true") return false;
  const requested = booleanRequest(value);
  if (requested === null) return false;
  const original = element.getAttribute("aria-checked") === "true";
  if (original === requested) return true;
  element.focus();
  element.click();
  const verified = await waitForCondition(
    () => (element.getAttribute("aria-checked") === "true") === requested,
    timing.verificationTimeoutMs,
    timing.pollIntervalMs,
  );
  if (!verified && (element.getAttribute("aria-checked") === "true") !== original) {
    element.click();
  }
  return verified;
}

function ariaRadioCandidates(element: HTMLElement): HTMLElement[] {
  const group = element.closest("[role='radiogroup']");
  const root = group ?? element.getRootNode();
  if (!(root instanceof Element || root instanceof Document || root instanceof ShadowRoot)) {
    return [element];
  }
  return Array.from(root.querySelectorAll("[role='radio']")).filter(
    (item): item is HTMLElement => item instanceof HTMLElement,
  );
}

function ariaChoiceValues(element: HTMLElement): string[] {
  return [
    compactText(element.textContent),
    compactText(element.getAttribute("aria-label")),
    compactText(element.getAttribute("data-value")),
    compactText(element.getAttribute("value")),
  ].filter(Boolean);
}

export async function fillAriaRadioControl(
  element: HTMLElement,
  value: string,
  timing: AdaptiveTiming,
): Promise<boolean | null> {
  if (!isAriaRadioControl(element)) return null;
  const candidates = ariaRadioCandidates(element).filter(
    (item) => item.getAttribute("aria-disabled") !== "true",
  );
  const context = interactionContext(element);
  const match = uniqueOptionCandidate(
    value,
    candidates.map((item) => ({ item, values: ariaChoiceValues(item) })),
    context,
  );
  if (!match) return false;
  const original = candidates.find((item) => item.getAttribute("aria-checked") === "true") ?? null;
  match.focus();
  match.click();
  const verified = await waitForCondition(
    () => match.getAttribute("aria-checked") === "true",
    timing.verificationTimeoutMs,
    timing.pollIntervalMs,
  );
  if (!verified && original && original !== match) original.click();
  return verified;
}

function hex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes), (value) => value.toString(16).padStart(2, "0")).join("");
}

export function fileFingerprintFor(element: HTMLInputElement): FileFingerprint {
  const stored = fileFingerprints.get(element);
  if (stored) return stored;
  const count = element.files?.length ?? 0;
  return {
    state: count === 0 ? "NONE" : "PENDING",
    count,
    sha256: null,
    size: count === 1 ? element.files?.[0]?.size ?? null : null,
    mimeType: count === 1 ? element.files?.[0]?.type || null : null,
  };
}

export async function refreshFileFingerprint(element: HTMLInputElement): Promise<FileFingerprint> {
  if (element.type !== "file") {
    throw new Error("File fingerprinting requires a file input");
  }
  const files = Array.from(element.files ?? []);
  if (files.length === 0) {
    const empty: FileFingerprint = {
      state: "NONE",
      count: 0,
      sha256: null,
      size: null,
      mimeType: null,
    };
    fileFingerprints.set(element, empty);
    return empty;
  }
  const pending: FileFingerprint = {
    state: "PENDING",
    count: files.length,
    sha256: null,
    size: files.length === 1 ? files[0]!.size : null,
    mimeType: files.length === 1 ? files[0]!.type || null : null,
  };
  fileFingerprints.set(element, pending);
  if (files.length !== 1 || !globalThis.crypto?.subtle) {
    const unsupported: FileFingerprint = { ...pending, state: "ERROR" };
    fileFingerprints.set(element, unsupported);
    return unsupported;
  }
  try {
    const digest = await globalThis.crypto.subtle.digest("SHA-256", await files[0]!.arrayBuffer());
    const ready: FileFingerprint = {
      ...pending,
      state: "READY",
      sha256: hex(digest),
    };
    fileFingerprints.set(element, ready);
    return ready;
  } catch {
    const failed: FileFingerprint = { ...pending, state: "ERROR" };
    fileFingerprints.set(element, failed);
    return failed;
  }
}

export function interactionConfidenceFor(element: Element): number {
  if (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement
  ) {
    if (element instanceof HTMLInputElement && element.type === "file") return 1;
    if (element.getAttribute("role") === "combobox") return element.getAttribute("aria-controls") ? 0.97 : 0.9;
    return 0.99;
  }
  if (isAriaBooleanControl(element) || isAriaRadioControl(element)) return 0.94;
  if (isPopupChoiceControl(element)) return element.getAttribute("aria-controls") ? 0.93 : 0.84;
  if (element instanceof HTMLElement && element.isContentEditable) return 0.9;
  return 0.55;
}

export function repeatMetadataFor(element: Element): {
  groupId: string | null;
  index: number | null;
} {
  const source = [
    element.getAttribute("name"),
    element.id,
    element.getAttribute("data-testid"),
  ]
    .filter((value): value is string => Boolean(value))
    .join("|");
  const match = source.match(/(?:\[|[_.-])(\d{1,3})(?:\]|[_.-]|$)/);
  if (!match) return { groupId: null, index: null };
  const index = Number(match[1]);
  if (!Number.isSafeInteger(index) || index < 0) return { groupId: null, index: null };
  const groupId = source.replace(match[0], "[#]");
  return { groupId: groupId || null, index };
}

export type AtsFamily =
  | "WORKDAY"
  | "GREENHOUSE"
  | "LEVER"
  | "ASHBY"
  | "SMARTRECRUITERS"
  | "ICIMS"
  | "TALEO"
  | "GENERIC";

export function detectAtsFamily(): AtsFamily {
  const hostname = window.location.hostname.toLocaleLowerCase("en-US");
  if (hostname.includes("myworkdayjobs") || document.querySelector("[data-automation-id]")) return "WORKDAY";
  if (hostname.includes("greenhouse") || document.querySelector("[data-mapped='true']")) return "GREENHOUSE";
  if (hostname.includes("lever.co")) return "LEVER";
  if (hostname.includes("ashbyhq")) return "ASHBY";
  if (hostname.includes("smartrecruiters")) return "SMARTRECRUITERS";
  if (hostname.includes("icims")) return "ICIMS";
  if (hostname.includes("taleo")) return "TALEO";
  return "GENERIC";
}
