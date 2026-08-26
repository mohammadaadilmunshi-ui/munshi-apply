import {
  ApplicationPageSchema,
  type ApplicationPage,
  type Question,
} from "@munshi-apply/contracts";
import { parseProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import {
  permanentProfileTarget,
  promoteRememberedAnswerIntoProfile,
} from "../storage/profile-answer-promotion";
import { saveRememberedAnswer } from "../storage/answer-memory";
import { NativeHealthStabilizer } from "./native-health-stabilizer";
import {
  beginRecentContextRetention,
  classifyJobContext,
  humanizeSemanticType,
  recentContextIsVisible,
  remainingRecentContextMs,
  type RecentJobContextRecord,
} from "./reliability-core";

const RECENT_CONTEXT_STORAGE_KEY = "owner-recent-job-context-v1";
const NATIVE_HOST_NAME = "systems.munshi.apply";
const nativeHealth = new NativeHealthStabilizer();

type GenericRuntimeSend = (...args: unknown[]) => unknown;
type NativeRecipeSummary = {
  recipeId: string;
  semanticType: string;
  siteOrigin: string;
  state: "SHADOW" | "PROMOTED" | "ROLLED_BACK";
  version: number;
  verifiedAttempts: number;
  verifiedSuccesses: number;
  updatedAt: string;
};

type PendingTeachPromotion = {
  page: ApplicationPage;
  question: Question;
  controlId: string;
  frameId: number;
};

let installed = false;
let originalRuntimeSend: GenericRuntimeSend | null = null;
let recentContext: RecentJobContextRecord | null = null;
let latestApplicationPage: ApplicationPage | null = null;
let pendingTeachPromotion: PendingTeachPromotion | null = null;
let retentionTimer: number | null = null;
let observer: MutationObserver | null = null;

function hasNativeMessagingPermission(): boolean {
  return (chrome.runtime.getManifest().permissions ?? []).includes(
    "nativeMessaging",
  );
}

function extensionResponse(value: unknown): {
  ok: boolean;
  data?: unknown;
  error?: string;
} | null {
  if (!value || typeof value !== "object" || !("ok" in value)) return null;
  const candidate = value as { ok?: unknown; data?: unknown; error?: unknown };
  if (typeof candidate.ok !== "boolean") return null;
  return {
    ok: candidate.ok,
    data: candidate.data,
    error: typeof candidate.error === "string" ? candidate.error : undefined,
  };
}

function installNativeHealthStabilizer(): void {
  if (!hasNativeMessagingPermission()) return;
  const runtime = chrome.runtime as unknown as {
    sendMessage: GenericRuntimeSend;
  };
  const original = runtime.sendMessage.bind(
    chrome.runtime,
  ) as GenericRuntimeSend;
  originalRuntimeSend = original;
  try {
    runtime.sendMessage = (...args: unknown[]) => {
      const request = args.length === 1 ? args[0] : null;
      const isNativeHealth = Boolean(
        request &&
        typeof request === "object" &&
        (request as { type?: unknown }).type === "NATIVE_HEALTH",
      );
      if (!isNativeHealth) return original(...args);
      return nativeHealth.request(() => Promise.resolve(original(...args)));
    };
  } catch {
    originalRuntimeSend = original;
  }
}

function rawRuntimeRequest(message: unknown): Promise<unknown> {
  const send =
    originalRuntimeSend ??
    (chrome.runtime.sendMessage.bind(
      chrome.runtime,
    ) as unknown as GenericRuntimeSend);
  return Promise.resolve(send(message));
}

function parsePage(value: unknown, tabId?: number): ApplicationPage | null {
  if (!value || typeof value !== "object") return null;
  const candidate =
    tabId === undefined
      ? value
      : { ...(value as Record<string, unknown>), tabId };
  const parsed = ApplicationPageSchema.safeParse(candidate);
  return parsed.success ? parsed.data : null;
}

async function persistRecentContext(): Promise<void> {
  if (!recentContext) {
    await chrome.storage.session.remove(RECENT_CONTEXT_STORAGE_KEY);
    return;
  }
  await chrome.storage.session.set({
    [RECENT_CONTEXT_STORAGE_KEY]: recentContext,
  });
}

async function restoreRecentContext(): Promise<void> {
  const stored = await chrome.storage.session.get(RECENT_CONTEXT_STORAGE_KEY);
  const candidate = stored[RECENT_CONTEXT_STORAGE_KEY];
  if (!candidate || typeof candidate !== "object") return;
  const record = candidate as Partial<RecentJobContextRecord>;
  const page = parsePage(record.page);
  if (
    !page ||
    (record.kind !== "APPLICATION" && record.kind !== "LISTING") ||
    typeof record.capturedAt !== "number" ||
    (record.retainedUntil !== null && typeof record.retainedUntil !== "number")
  ) {
    return;
  }
  recentContext = {
    page,
    kind: record.kind,
    capturedAt: record.capturedAt,
    retainedUntil: record.retainedUntil ?? null,
  };
  if (record.kind === "APPLICATION") latestApplicationPage = page;
}

function applicationSection(): HTMLElement | null {
  return (
    Array.from(document.querySelectorAll<HTMLElement>("section")).find(
      (section) =>
        /current application/i.test(
          section.querySelector(".section-heading .eyebrow")?.textContent ?? "",
        ),
    ) ?? null
  );
}

function restoreRetainedHeading(): void {
  const heading = document.querySelector<HTMLElement>(
    "[data-munshi-retained-original-title]",
  );
  if (!heading) return;
  heading.textContent =
    heading.dataset.munshiRetainedOriginalTitle ?? "No application detected";
  delete heading.dataset.munshiRetainedOriginalTitle;
}

function removeRecentContextCard(): void {
  document.getElementById("munshi-recent-context-card")?.remove();
  restoreRetainedHeading();
  if (retentionTimer !== null) {
    window.clearInterval(retentionTimer);
    retentionTimer = null;
  }
}

function setRetainedHeading(title: string): void {
  const section = applicationSection();
  const heading = section?.querySelector<HTMLElement>(".section-heading h2");
  if (!heading) return;
  if (!heading.dataset.munshiRetainedOriginalTitle) {
    heading.dataset.munshiRetainedOriginalTitle =
      heading.textContent ?? "No application detected";
  }
  heading.textContent = title;
}

function contextHostname(page: ApplicationPage): string {
  try {
    return new URL(page.url).hostname;
  } catch {
    return page.url;
  }
}

async function jumpToQuestion(
  page: ApplicationPage,
  question: Question,
  statusTarget?: HTMLElement,
): Promise<void> {
  const control = page.controls.find(
    (candidate) => candidate.controlId === question.controlId,
  );
  if (!control || page.tabId < 0) return;
  try {
    await chrome.tabs.update(page.tabId, { active: true });
    const response = (await chrome.tabs.sendMessage(
      page.tabId,
      {
        type: "MUNSHI_OWNER_FOCUS_CONTROL",
        controlId: question.controlId,
      },
      { frameId: control.frameId },
    )) as { ok?: boolean; result?: { status?: string; reason?: string } };
    if (statusTarget) {
      statusTarget.textContent =
        response?.result?.status === "FOCUSED"
          ? "Opened"
          : response?.result?.reason || "Could not open field";
    }
  } catch {
    if (statusTarget) statusTarget.textContent = "Job tab is unavailable";
  }
}

function recentQuestionRow(
  page: ApplicationPage,
  question: Question,
): HTMLElement {
  const row = document.createElement("div");
  row.className = "munshi-recent-question";
  const text = document.createElement("span");
  text.textContent = question.rawText;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "munshi-question-jump";
  button.textContent = "Jump";
  button.addEventListener(
    "click",
    () => void jumpToQuestion(page, question, button),
  );
  row.append(text, button);
  return row;
}

function renderRecentContextCard(record: RecentJobContextRecord): void {
  if (record.retainedUntil !== null && !recentContextIsVisible(record)) {
    void expireRecentContext();
    return;
  }
  const section = applicationSection();
  if (!section) return;
  const existing = document.getElementById("munshi-recent-context-card");
  const card = existing ?? document.createElement("div");
  card.id = "munshi-recent-context-card";
  card.className = "munshi-recent-context-card";
  card.replaceChildren();

  setRetainedHeading(record.page.title || "Recent job context");

  const header = document.createElement("div");
  header.className = "munshi-recent-header";
  const title = document.createElement("strong");
  title.textContent =
    record.retainedUntil === null
      ? record.kind === "LISTING"
        ? "Job listing detected"
        : "Current job context"
      : "Recent job context retained";
  const countdown = document.createElement("span");
  countdown.className = "munshi-recent-countdown";
  header.append(title, countdown);

  const host = document.createElement("p");
  host.className = "munshi-recent-host";
  host.textContent = contextHostname(record.page);

  const detail = document.createElement("p");
  detail.textContent =
    record.retainedUntil === null
      ? "MUNSHI will keep this context while you review the listing."
      : "You opened another tab. MUNSHI is keeping the previous job context briefly instead of forgetting it immediately.";

  const actions = document.createElement("div");
  actions.className = "munshi-recent-actions";
  if (record.page.tabId >= 0) {
    const returnButton = document.createElement("button");
    returnButton.type = "button";
    returnButton.className = "munshi-return-job";
    returnButton.textContent = "Return to job tab";
    returnButton.addEventListener("click", () => {
      void chrome.tabs
        .update(record.page.tabId, { active: true })
        .catch(() => undefined);
    });
    actions.append(returnButton);
  }

  if (record.page.questions.length > 0) {
    const questions = document.createElement("div");
    questions.className = "munshi-recent-questions";
    for (const question of record.page.questions.slice(0, 8)) {
      questions.append(recentQuestionRow(record.page, question));
    }
    if (record.page.questions.length > 8) {
      const more = document.createElement("span");
      more.className = "munshi-recent-countdown";
      more.textContent = `+${record.page.questions.length - 8} more questions on the job tab`;
      questions.append(more);
    }
    actions.append(questions);
  }

  card.append(header, host, detail, actions);
  const heading = section.querySelector(".section-heading");
  if (heading) heading.insertAdjacentElement("afterend", card);
  else section.prepend(card);

  const updateCountdown = () => {
    if (!recentContext || recentContext.page.pageId !== record.page.pageId)
      return;
    if (record.retainedUntil === null) {
      countdown.textContent = "Active";
      card.classList.remove("fading");
      return;
    }
    const remaining = remainingRecentContextMs(record);
    if (remaining <= 0) {
      void expireRecentContext();
      return;
    }
    const seconds = Math.ceil(remaining / 1_000);
    countdown.textContent = `Fades in ${Math.floor(seconds / 60)}:${String(
      seconds % 60,
    ).padStart(2, "0")}`;
    card.classList.toggle("fading", remaining <= 30_000);
  };
  updateCountdown();
  if (record.retainedUntil !== null && retentionTimer === null) {
    retentionTimer = window.setInterval(updateCountdown, 1_000);
  }
}

async function expireRecentContext(): Promise<void> {
  removeRecentContextCard();
  recentContext = null;
  latestApplicationPage = null;
  await persistRecentContext();
}

async function rememberContext(
  page: ApplicationPage,
  kind: "APPLICATION" | "LISTING",
): Promise<void> {
  recentContext = {
    page,
    kind,
    capturedAt: Date.now(),
    retainedUntil: null,
  };
  if (kind === "APPLICATION") latestApplicationPage = page;
  await persistRecentContext();
  if (kind === "LISTING") renderRecentContextCard(recentContext);
  else removeRecentContextCard();
  decorateApplicationQuestions();
}

async function retainCurrentContext(): Promise<void> {
  if (!recentContext) return;
  if (recentContext.retainedUntil === null) {
    recentContext = beginRecentContextRetention(recentContext);
    await persistRecentContext();
  }
  if (recentContextIsVisible(recentContext))
    renderRecentContextCard(recentContext);
  else await expireRecentContext();
}

async function readPageContextFromTab(
  tabId: number,
): Promise<ApplicationPage | null> {
  try {
    const response = (await chrome.tabs.sendMessage(
      tabId,
      { type: "MUNSHI_OWNER_PAGE_CONTEXT" },
      { frameId: 0 },
    )) as { ok?: boolean; page?: unknown };
    return response?.ok ? parsePage(response.page, tabId) : null;
  } catch {
    return null;
  }
}

async function inspectTab(tabId: number): Promise<void> {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab || !/^https?:\/\//.test(tab.url ?? "")) {
    await retainCurrentContext();
    return;
  }
  const page = await readPageContextFromTab(tabId);
  if (!page) {
    await retainCurrentContext();
    return;
  }
  const kind = classifyJobContext(page);
  if (!kind) {
    await retainCurrentContext();
    return;
  }
  if (kind === "APPLICATION") {
    try {
      const response = extensionResponse(
        await rawRuntimeRequest({ type: "GET_ACTIVE_PAGE" }),
      );
      const canonical = response?.ok ? parsePage(response.data) : null;
      await rememberContext(canonical ?? page, kind);
      return;
    } catch {
      // Retain the direct scan as a continuity fallback while canonical recovery
      // proceeds on the next background/page event.
    }
  }
  await rememberContext(page, kind);
}

async function inspectActiveTab(): Promise<void> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined) {
    await retainCurrentContext();
    return;
  }
  await inspectTab(tab.id);
}

function decorateApplicationQuestions(): void {
  if (!latestApplicationPage) return;
  const section = applicationSection();
  if (!section) return;
  const cards = Array.from(
    section.querySelectorAll<HTMLElement>(".answer-list .answer-card"),
  );
  cards.forEach((card, index) => {
    if (card.querySelector(".munshi-question-jump")) return;
    const question = latestApplicationPage?.questions[index];
    if (!question) return;
    const heading = card.querySelector<HTMLElement>(".answer-heading");
    if (!heading) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "munshi-question-jump";
    button.textContent = "Jump to field";
    button.setAttribute("aria-label", `Jump to ${question.rawText}`);
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      void jumpToQuestion(latestApplicationPage!, question, button);
    });
    heading.append(button);
  });
}

function patchTeachCopy(): void {
  const copy = document.querySelector<HTMLElement>(".teach-panel .teach-copy");
  if (!copy || copy.dataset.munshiReliabilityCopy === "true") return;
  copy.dataset.munshiReliabilityCopy = "true";
  copy.textContent =
    "Use this when MUNSHI struggles with a field. Demonstrate the control once. MUNSHI learns the interaction mechanics, and when the field maps to a stable personal fact, your successfully demonstrated answer is also saved to your Personal Profile. Context-specific answers stay out of the permanent profile.";
}

function profileFactLabel(question: Question): string {
  const target = permanentProfileTarget(question.semanticType);
  return target
    ? humanizeSemanticType(target.key)
    : humanizeSemanticType(question.semanticType);
}

function appendTeachNote(result: HTMLElement, text: string): void {
  result.parentElement?.querySelector(".munshi-teach-profile-note")?.remove();
  const note = document.createElement("div");
  note.className = "munshi-teach-profile-note";
  note.textContent = text;
  result.insertAdjacentElement("afterend", note);
}

async function readTaughtControlValue(
  pending: PendingTeachPromotion,
): Promise<string> {
  try {
    const response = (await chrome.tabs.sendMessage(
      pending.page.tabId,
      {
        type: "MUNSHI_OWNER_READ_CONTROL_VALUE",
        controlId: pending.controlId,
      },
      { frameId: pending.frameId },
    )) as { ok?: boolean; value?: unknown };
    return response?.ok && typeof response.value === "string"
      ? response.value.trim()
      : "";
  } catch {
    return "";
  }
}

async function promoteSuccessfulTeach(
  pending: PendingTeachPromotion,
  result: HTMLElement,
): Promise<void> {
  const target = permanentProfileTarget(pending.question.semanticType);
  if (!target) {
    appendTeachNote(
      result,
      "Interaction lesson saved. This question is context-specific, so its answer was not added to your permanent Personal Profile.",
    );
    return;
  }
  const value = await readTaughtControlValue(pending);
  if (!value) {
    appendTeachNote(
      result,
      "Interaction lesson saved. The employer control did not expose a stable committed value, so MUNSHI did not guess what to save in your Personal Profile.",
    );
    return;
  }

  try {
    const profileResponse = extensionResponse(
      await rawRuntimeRequest({ type: "GET_PROFILE" }),
    );
    if (!profileResponse?.ok || profileResponse.data == null) {
      throw new Error(
        profileResponse?.error || "Personal Profile is unavailable",
      );
    }
    const profile = parseProfileSnapshot(profileResponse.data);
    const approvedAt = new Date().toISOString();
    const promotion = promoteRememberedAnswerIntoProfile(profile, {
      semanticType: pending.question.semanticType,
      value,
      sensitive: pending.question.sensitive,
      approvedAt,
    });
    if (promotion.changed) {
      const saveResponse = extensionResponse(
        await rawRuntimeRequest({
          type: "SAVE_PROFILE",
          payload: promotion.profile,
        }),
      );
      if (!saveResponse?.ok) {
        throw new Error(saveResponse?.error || "Personal Profile save failed");
      }
    }
    await saveRememberedAnswer({
      question: pending.question.rawText,
      semanticType: pending.question.semanticType,
      value,
      sensitive: pending.question.sensitive,
    });
    appendTeachNote(
      result,
      promotion.changed
        ? `Personal Profile updated: ${profileFactLabel(pending.question)}. The reusable interaction recipe still contains no answer value.`
        : `Personal Profile already contains this confirmed ${profileFactLabel(pending.question).toLocaleLowerCase("en-US")} value. The reusable interaction recipe contains no answer value.`,
    );
  } catch (error) {
    appendTeachNote(
      result,
      error instanceof Error
        ? `Interaction lesson saved, but Personal Profile promotion needs attention: ${error.message}`
        : "Interaction lesson saved, but Personal Profile promotion needs attention.",
    );
  }
}

function captureTeachTarget(event: Event): void {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const button = target.closest("button.teach-finish");
  if (!button) return;
  const panel = button.closest(".teach-panel");
  const select = panel?.querySelector<HTMLSelectElement>("select");
  const page = latestApplicationPage;
  if (!select || !page) return;
  const controlId = select.value;
  const question = page.questions.find(
    (candidate) => candidate.controlId === controlId,
  );
  const control = page.controls.find(
    (candidate) => candidate.controlId === controlId,
  );
  if (!question || !control) return;
  pendingTeachPromotion = {
    page,
    question,
    controlId,
    frameId: control.frameId,
  };
}

function lessonStateLabel(state: NativeRecipeSummary["state"]): string {
  if (state === "PROMOTED") return "Trusted";
  if (state === "ROLLED_BACK") return "Rolled back";
  return "Testing";
}

function nativeRequest(
  message: Record<string, unknown>,
  timeoutMs = 4_000,
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative(NATIVE_HOST_NAME);
    const timeout = window.setTimeout(() => {
      port.disconnect();
      reject(new Error("Native companion request timed out"));
    }, timeoutMs);
    let settled = false;
    port.onMessage.addListener((response: unknown) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeout);
      port.disconnect();
      resolve(response);
    });
    port.onDisconnect.addListener(() => {
      if (settled) return;
      const lastError = chrome.runtime.lastError;
      if (!lastError) return;
      settled = true;
      window.clearTimeout(timeout);
      reject(new Error(lastError.message));
    });
    port.postMessage(message);
  });
}

async function listLearnedRecipes(): Promise<NativeRecipeSummary[]> {
  if (!hasNativeMessagingPermission()) return [];
  let lastError: unknown;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const response = extensionResponse(
        await nativeRequest({ type: "LIST_INTERACTION_RECIPES" }),
      );
      if (!response?.ok) {
        throw new Error(response?.error || "Learned lessons are unavailable");
      }
      if (!Array.isArray(response.data)) return [];
      return response.data.filter((item): item is NativeRecipeSummary => {
        if (!item || typeof item !== "object") return false;
        const candidate = item as Partial<NativeRecipeSummary>;
        return (
          typeof candidate.recipeId === "string" &&
          typeof candidate.semanticType === "string" &&
          typeof candidate.siteOrigin === "string" &&
          ["SHADOW", "PROMOTED", "ROLLED_BACK"].includes(
            candidate.state ?? "",
          ) &&
          typeof candidate.version === "number" &&
          typeof candidate.verifiedAttempts === "number" &&
          typeof candidate.verifiedSuccesses === "number" &&
          typeof candidate.updatedAt === "string"
        );
      });
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => window.setTimeout(resolve, 180));
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error("Learned lessons are unavailable");
}

function renderLearnedItems(
  container: HTMLElement,
  items: NativeRecipeSummary[],
): void {
  container.replaceChildren();
  if (items.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No learned controls yet.";
    container.append(empty);
    return;
  }
  for (const lesson of items.slice(0, 50)) {
    const item = document.createElement("div");
    item.className = "munshi-learned-item";
    const title = document.createElement("strong");
    title.textContent = humanizeSemanticType(lesson.semanticType);
    const meta = document.createElement("div");
    meta.className = "munshi-learned-meta";
    let host = lesson.siteOrigin;
    try {
      host = new URL(lesson.siteOrigin).hostname;
    } catch {
      host = lesson.siteOrigin;
    }
    const attempts = document.createElement("span");
    attempts.textContent = `${lesson.verifiedSuccesses}/${lesson.verifiedAttempts} verified`;
    const state = document.createElement("span");
    state.textContent = `${lessonStateLabel(lesson.state)} · v${lesson.version}`;
    meta.append(document.createTextNode(host), attempts, state);
    item.append(title, meta);
    container.append(item);
  }
}

async function refreshLearnedPanel(panel: HTMLElement): Promise<void> {
  const list = panel.querySelector<HTMLElement>(".munshi-learned-list");
  if (!list) return;
  list.textContent = "Loading learned controls…";
  try {
    renderLearnedItems(list, await listLearnedRecipes());
  } catch (error) {
    list.textContent =
      error instanceof Error
        ? `Learned controls unavailable: ${error.message}`
        : "Learned controls are temporarily unavailable.";
  }
}

function ensureLearnedPanel(): void {
  const teach = document.querySelector<HTMLElement>(".teach-panel");
  if (!teach || teach.querySelector(".munshi-learned-panel")) return;
  const panel = document.createElement("section");
  panel.className = "munshi-learned-panel";
  const header = document.createElement("div");
  header.className = "munshi-learned-header";
  const heading = document.createElement("strong");
  heading.textContent = "Learned by MUNSHI";
  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.className = "munshi-learned-refresh";
  refresh.textContent = "Refresh";
  refresh.addEventListener("click", () => void refreshLearnedPanel(panel));
  header.append(heading, refresh);
  const copy = document.createElement("p");
  copy.textContent =
    "Shows learned control mechanics only. Answer values are never stored inside reusable recipes.";
  const list = document.createElement("div");
  list.className = "munshi-learned-list";
  panel.append(header, copy, list);
  teach.append(panel);
  if (hasNativeMessagingPermission()) void refreshLearnedPanel(panel);
  else
    list.textContent =
      "Learned controls are available on the desktop companion.";
}

function processTeachResult(): void {
  const result = document.querySelector<HTMLElement>(
    ".teach-result.success:not([data-munshi-reliability-processed])",
  );
  if (!result) return;
  result.dataset.munshiReliabilityProcessed = "true";
  const pending = pendingTeachPromotion;
  pendingTeachPromotion = null;
  if (pending) {
    void promoteSuccessfulTeach(pending, result).finally(() => {
      const panel = document.querySelector<HTMLElement>(
        ".munshi-learned-panel",
      );
      if (panel) void refreshLearnedPanel(panel);
    });
  }
}

function maintainEnhancements(): void {
  decorateApplicationQuestions();
  patchTeachCopy();
  ensureLearnedPanel();
  processTeachResult();
  if (
    recentContext &&
    recentContextIsVisible(recentContext) &&
    !document.getElementById("munshi-recent-context-card")
  ) {
    const [active] = Array.from(document.querySelectorAll(".answer-card"));
    if (!active || recentContext.kind === "LISTING") {
      renderRecentContextCard(recentContext);
    }
  }
}

function installRuntimeContextListener(): void {
  chrome.runtime.onMessage.addListener((message: unknown) => {
    if (!message || typeof message !== "object") return false;
    const candidate = message as { type?: unknown; payload?: unknown };
    if (candidate.type === "ACTIVE_PAGE_UPDATED") {
      const page = parsePage(candidate.payload);
      if (page) void rememberContext(page, "APPLICATION");
    } else if (candidate.type === "ACTIVE_PAGE_CLEARED") {
      void inspectActiveTab();
    }
    return false;
  });
}

function installTabListeners(): void {
  chrome.tabs.onActivated.addListener(({ tabId }) => {
    void inspectTab(tabId);
  });
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (!tab.active) return;
    if (changeInfo.status === "complete" || changeInfo.url) {
      void inspectTab(tabId);
    }
  });
}

export function installSidepanelReliability(): void {
  if (installed) return;
  installed = true;
  installNativeHealthStabilizer();
  installRuntimeContextListener();
  installTabListeners();
  document.addEventListener("click", captureTeachTarget, true);
  observer = new MutationObserver(() => maintainEnhancements());
  const root = document.getElementById("root") ?? document.documentElement;
  observer.observe(root, { childList: true, subtree: true });
  void restoreRecentContext()
    .then(() => inspectActiveTab())
    .finally(() => maintainEnhancements());
}
