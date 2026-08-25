import {
  expireRecentApplicationContext,
  jumpToQuestion,
} from "../messaging/client";

type RetainedContextPayload = {
  expiresAt?: number;
};

let installed = false;
let retainedUntil: number | null = null;
let expiryTimer: number | null = null;
let observer: MutationObserver | null = null;

function applicationSection(): HTMLElement | null {
  const heading = Array.from(document.querySelectorAll<HTMLElement>(".section-heading h2")).find(
    (candidate) =>
      candidate.closest("section")?.querySelector(".answer-list") !== null,
  );
  return heading?.closest("section") ?? null;
}

function removeRetentionBanner(): void {
  document.getElementById("munshi-retained-context")?.remove();
}

function renderRetentionBanner(): void {
  removeRetentionBanner();
  if (retainedUntil === null || retainedUntil <= Date.now()) return;
  const section = applicationSection();
  const heading = section?.querySelector(".section-heading");
  if (!section || !heading) return;
  const remainingMinutes = Math.max(
    1,
    Math.ceil((retainedUntil - Date.now()) / 60_000),
  );
  const banner = document.createElement("div");
  banner.id = "munshi-retained-context";
  banner.className = "inline-note munshi-retained-context";
  banner.setAttribute("role", "status");
  banner.textContent = `Keeping your last application context for about ${remainingMinutes} more minute${remainingMinutes === 1 ? "" : "s"} while you browse another tab. Click any question to return directly to its field.`;
  heading.insertAdjacentElement("afterend", banner);
}

function clearExpiryTimer(): void {
  if (expiryTimer !== null) window.clearTimeout(expiryTimer);
  expiryTimer = null;
}

function scheduleExpiry(): void {
  clearExpiryTimer();
  if (retainedUntil === null) return;
  const delay = Math.max(0, retainedUntil - Date.now());
  expiryTimer = window.setTimeout(() => {
    retainedUntil = null;
    removeRetentionBanner();
    void expireRecentApplicationContext().catch(() => undefined);
  }, delay + 25);
}

function showJumpStatus(message: string, error = false): void {
  document.getElementById("munshi-question-jump-status")?.remove();
  const section = applicationSection();
  const heading = section?.querySelector(".section-heading");
  if (!heading) return;
  const status = document.createElement("div");
  status.id = "munshi-question-jump-status";
  status.className = error ? "inline-note warning" : "inline-note";
  status.setAttribute("role", "status");
  status.textContent = message;
  heading.insertAdjacentElement("afterend", status);
  window.setTimeout(() => status.remove(), 3_000);
}

function answerHeadings(): HTMLElement[] {
  return Array.from(
    document.querySelectorAll<HTMLElement>(".answer-list > .answer-card .answer-heading"),
  );
}

function decorateQuestionHeadings(): void {
  for (const heading of answerHeadings()) {
    if (heading.dataset.munshiJumpReady === "true") continue;
    heading.dataset.munshiJumpReady = "true";
    heading.tabIndex = 0;
    heading.setAttribute("role", "button");
    heading.setAttribute("title", "Jump to this field on the employer page");
    const question = heading.querySelector("strong")?.textContent?.trim();
    heading.setAttribute(
      "aria-label",
      question ? `Jump to employer field: ${question}` : "Jump to employer field",
    );
  }
}

function questionIndex(heading: HTMLElement): number {
  const card = heading.closest<HTMLElement>(".answer-card");
  if (!card) return -1;
  const cards = Array.from(
    document.querySelectorAll<HTMLElement>(".answer-list > .answer-card"),
  );
  return cards.indexOf(card);
}

async function jumpFromHeading(heading: HTMLElement): Promise<void> {
  const index = questionIndex(heading);
  if (index < 0 || heading.dataset.munshiJumpBusy === "true") return;
  heading.dataset.munshiJumpBusy = "true";
  heading.setAttribute("aria-busy", "true");
  try {
    const result = await jumpToQuestion(index);
    showJumpStatus(result.reason, result.status !== "FOCUSED");
  } catch (error) {
    showJumpStatus(
      error instanceof Error ? error.message : "Unable to jump to this employer field.",
      true,
    );
  } finally {
    delete heading.dataset.munshiJumpBusy;
    heading.removeAttribute("aria-busy");
  }
}

function handleClick(event: MouseEvent): void {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (target.closest("input, textarea, select, button, label, a")) return;
  const heading = target.closest<HTMLElement>(".answer-heading[data-munshi-jump-ready='true']");
  if (!heading) return;
  void jumpFromHeading(heading);
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== "Enter" && event.key !== " ") return;
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.matches(".answer-heading[data-munshi-jump-ready='true']")) return;
  event.preventDefault();
  void jumpFromHeading(target);
}

function handleRuntimeMessage(message: {
  type?: string;
  payload?: RetainedContextPayload;
}): void {
  if (message.type === "ACTIVE_PAGE_RETAINED") {
    const expiresAt = Number(message.payload?.expiresAt);
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) return;
    retainedUntil = expiresAt;
    renderRetentionBanner();
    scheduleExpiry();
    return;
  }
  if (
    message.type === "ACTIVE_PAGE_UPDATED" ||
    message.type === "ACTIVE_PAGE_CLEARED"
  ) {
    retainedUntil = null;
    clearExpiryTimer();
    removeRetentionBanner();
  }
}

export function installRuntimeReliabilityUi(): void {
  if (installed) return;
  installed = true;
  decorateQuestionHeadings();
  observer = new MutationObserver(() => {
    decorateQuestionHeadings();
    if (retainedUntil !== null) renderRetentionBanner();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("click", handleClick);
  document.addEventListener("keydown", handleKeydown);
  chrome.runtime.onMessage.addListener(handleRuntimeMessage);
}
