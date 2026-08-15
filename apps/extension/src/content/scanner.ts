import type {
  ApplicationPage,
  ApplicationState,
  Control,
  ControlKind,
  NavigationAction,
  NavigationCandidate,
  Question,
  SecurityCheckpointKind,
  SemanticType,
} from "@munshi-apply/contracts";
import { componentFingerprint } from "@munshi-apply/application-model";
import { classifyQuestion } from "@munshi-apply/semantic-engine";
import {
  classifyValidationMessage,
  detectAtsFamily,
  fileFingerprintFor,
  interactionConfidenceFor,
  isAriaBooleanControl,
  isAriaRadioControl,
  isCustomDateControl,
  isPopupChoiceControl,
  repeatMetadataFor,
  validationMessageFor,
} from "./adaptive";

const selector = [
  "input",
  "select",
  "textarea",
  "button",
  "[role='button']",
  "[role='combobox']",
  "[role='checkbox']",
  "[role='switch']",
  "[role='radio']",
  "[role='spinbutton']",
  "[aria-haspopup='listbox']",
  "[aria-haspopup='tree']",
  "[aria-haspopup='grid']",
  "[aria-haspopup='dialog']",
  "[contenteditable='true']",
].join(",");

function collectInteractiveElements(root: Document | ShadowRoot): Element[] {
  const collected: Element[] = [];
  for (const element of Array.from(root.querySelectorAll(selector))) {
    collected.push(element);
    if (element.shadowRoot) {
      collected.push(...collectInteractiveElements(element.shadowRoot));
    }
  }

  for (const host of Array.from(root.querySelectorAll("*"))) {
    if (
      host.shadowRoot &&
      !collected.some((element) => element.getRootNode() === host.shadowRoot)
    ) {
      collected.push(...collectInteractiveElements(host.shadowRoot));
    }
  }
  return [...new Set(collected)];
}

function compactText(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function normalized(value: string | null | undefined): string {
  return compactText(value).toLocaleLowerCase("en-US");
}

function isVisible(element: Element): boolean {
  if (!(element instanceof HTMLElement)) return false;
  const style = window.getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  if (
    element.hidden ||
    element.getAttribute("aria-hidden") === "true" ||
    style.display === "none" ||
    style.visibility === "hidden" ||
    style.opacity === "0" ||
    rect.width <= 0 ||
    rect.height <= 0
  ) {
    return false;
  }
  const explicitlyPositioned =
    style.position === "absolute" || style.position === "fixed";
  return !explicitlyPositioned || (rect.right > 0 && rect.bottom > 0);
}

function hash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

function inputLabel(element: HTMLInputElement): string {
  return Array.from(element.labels ?? [])
    .map((label) => compactText(label.textContent))
    .filter(Boolean)
    .join(" ");
}

function radioGroup(element: HTMLInputElement): HTMLInputElement[] {
  const root = element.getRootNode();
  const candidates =
    root instanceof Document || root instanceof ShadowRoot
      ? Array.from(root.querySelectorAll("input[type='radio']"))
      : [];
  if (!element.name) return [element];
  return candidates.filter(
    (candidate): candidate is HTMLInputElement =>
      candidate instanceof HTMLInputElement && candidate.name === element.name,
  );
}

function radioOptionLabel(element: HTMLInputElement): string {
  return (
    inputLabel(element) ||
    compactText(element.getAttribute("aria-label")) ||
    compactText(element.value)
  );
}

function groupLegend(element: Element): string {
  const fieldset = element.closest("fieldset");
  return compactText(fieldset?.querySelector(":scope > legend")?.textContent);
}

function labelledByText(element: Element): string {
  const labelledBy = element.getAttribute("aria-labelledby");
  if (!labelledBy) return "";
  const root = element.getRootNode();
  return labelledBy
    .split(/\s+/)
    .map((id) => {
      const labelledElement =
        root instanceof Document
          ? root.getElementById(id)
          : root instanceof ShadowRoot
            ? root.querySelector(`#${CSS.escape(id)}`)
            : null;
      return compactText(labelledElement?.textContent);
    })
    .filter(Boolean)
    .join(" ");
}

function labelFor(element: Element): string {
  const ariaLabel = compactText(element.getAttribute("aria-label"));
  if (ariaLabel) return ariaLabel;

  const labelled = labelledByText(element);
  if (labelled) return labelled;

  if (element instanceof HTMLInputElement) {
    if (element.type === "radio") {
      const legend = groupLegend(element);
      if (legend) return legend;
    }
    const labels = inputLabel(element);
    if (labels) return labels;
    if (["button", "submit", "reset"].includes(element.type)) {
      return compactText(element.value);
    }
  }

  if (
    element instanceof HTMLSelectElement ||
    element instanceof HTMLTextAreaElement
  ) {
    const labels = Array.from(element.labels)
      .map((label) => compactText(label.textContent))
      .filter(Boolean)
      .join(" ");
    if (labels) return labels;
  }

  if (
    element instanceof HTMLButtonElement ||
    element.getAttribute("role") === "button"
  ) {
    const text = compactText(element.textContent);
    if (text) return text;
  }

  const container = element.closest("fieldset, [role='group'], .form-group");
  return compactText(container?.querySelector("legend")?.textContent);
}

function kindFor(element: Element): ControlKind {
  if (isCustomDateControl(element) || isPopupChoiceControl(element)) {
    return "COMBOBOX";
  }
  if (isAriaBooleanControl(element)) return "CHECKBOX";
  if (isAriaRadioControl(element)) return "RADIO";
  if (element.getAttribute("role") === "spinbutton") return "NUMBER";
  if (element instanceof HTMLTextAreaElement) return "TEXTAREA";
  if (element instanceof HTMLSelectElement) return "SELECT";
  if (
    element instanceof HTMLButtonElement ||
    element.getAttribute("role") === "button"
  ) {
    return "BUTTON";
  }
  if (element instanceof HTMLInputElement) {
    const mapping: Partial<Record<string, ControlKind>> = {
      button: "BUTTON",
      checkbox: "CHECKBOX",
      date: "DATE",
      email: "EMAIL",
      file: "FILE",
      number: "NUMBER",
      radio: "RADIO",
      reset: "BUTTON",
      submit: "BUTTON",
      tel: "TEL",
      text: "TEXT",
    };
    return mapping[element.type] ?? "UNKNOWN";
  }
  return element.getAttribute("contenteditable") === "true"
    ? "TEXTAREA"
    : "UNKNOWN";
}

function controlledComboboxOptions(element: Element): string[] {
  const root = element.getRootNode();
  if (!(root instanceof Document || root instanceof ShadowRoot)) return [];
  const ids = [
    element.getAttribute("aria-controls"),
    element.getAttribute("aria-owns"),
  ]
    .filter((value): value is string => Boolean(value))
    .flatMap((value) => value.split(/\s+/))
    .filter(Boolean);
  const labels: string[] = [];
  for (const id of ids) {
    const container =
      root instanceof Document
        ? root.getElementById(id)
        : root.querySelector(`#${CSS.escape(id)}`);
    if (!container) continue;
    const candidates = [
      ...(["option", "treeitem", "gridcell"].includes(
        container.getAttribute("role") ?? "",
      )
        ? [container]
        : []),
      ...Array.from(
        container.querySelectorAll(
          "[role='option'], [role='treeitem'], [role='gridcell']",
        ),
      ),
    ];
    for (const candidate of candidates) {
      const label =
        compactText(candidate.getAttribute("aria-label")) ||
        compactText(candidate.textContent) ||
        compactText(candidate.getAttribute("data-value"));
      if (label) labels.push(label);
    }
  }
  return [...new Set(labels)];
}

function optionsFor(element: Element): string[] {
  if (element instanceof HTMLSelectElement) {
    return Array.from(element.options).map((option) =>
      compactText(option.text),
    );
  }
  if (element instanceof HTMLInputElement && element.type === "radio") {
    return radioGroup(element).map(radioOptionLabel).filter(Boolean);
  }
  if (element.getAttribute("role") === "combobox") {
    return controlledComboboxOptions(element);
  }
  return [];
}

function validationState(element: Element): {
  invalid: boolean;
  validationMessage: string;
} {
  const ariaInvalid = element.getAttribute("aria-invalid") === "true";
  const candidate =
    element instanceof HTMLInputElement ||
    element instanceof HTMLSelectElement ||
    element instanceof HTMLTextAreaElement
      ? compactText(element.validationMessage)
      : "";
  let ariaMessage = "";
  if (ariaInvalid) {
    const describedBy = element.getAttribute("aria-describedby");
    const root = element.getRootNode();
    if (
      describedBy &&
      (root instanceof Document || root instanceof ShadowRoot)
    ) {
      ariaMessage = describedBy
        .split(/\s+/)
        .map((id) => {
          const node =
            root instanceof Document
              ? root.getElementById(id)
              : root.querySelector(`#${CSS.escape(id)}`);
          return compactText(node?.textContent);
        })
        .filter(Boolean)
        .join(" ");
    }
  }
  return {
    invalid: ariaInvalid || Boolean(candidate),
    validationMessage: ariaMessage || candidate,
  };
}

function stableControlSignature(element: Element): string {
  const url = new URL(window.location.href);
  const type = element instanceof HTMLInputElement ? element.type : "";
  const optionValue =
    element instanceof HTMLInputElement &&
    (element.type === "radio" ||
      element.type === "checkbox" ||
      ["button", "submit", "reset"].includes(element.type))
      ? element.value
      : "";
  return [
    url.origin,
    url.pathname,
    element.tagName,
    element.id,
    compactText(element.getAttribute("name")),
    type,
    labelFor(element),
    compactText(element.getAttribute("placeholder")),
    compactText(element.getAttribute("aria-label")),
    compactText(element.getAttribute("autocomplete")),
    compactText(optionValue),
  ].join("|");
}

function controlSatisfied(element: Element): boolean {
  if (
    ("disabled" in element &&
      Boolean((element as HTMLInputElement).disabled)) ||
    element.getAttribute("aria-disabled") === "true"
  ) {
    return true;
  }
  if (element instanceof HTMLInputElement) {
    if (element.type === "file") return Boolean(element.files?.length);
    if (element.type === "checkbox") return element.checked;
    if (element.type === "radio") {
      return radioGroup(element).some((candidate) => candidate.checked);
    }
    return Boolean(compactText(element.value)) && element.validity.valid;
  }
  if (element instanceof HTMLSelectElement) {
    return Boolean(compactText(element.value)) && element.validity.valid;
  }
  if (element instanceof HTMLTextAreaElement) {
    return Boolean(compactText(element.value)) && element.validity.valid;
  }
  if (isAriaBooleanControl(element) || isAriaRadioControl(element)) {
    return element.getAttribute("aria-checked") === "true";
  }
  if (element instanceof HTMLElement && element.isContentEditable) {
    return Boolean(compactText(element.textContent));
  }
  return Boolean(
    compactText(element.getAttribute("aria-valuetext")) ||
    compactText(element.getAttribute("data-value")) ||
    compactText(element.getAttribute("aria-activedescendant")),
  );
}

function createControl(element: Element): Control | null {
  const visible = isVisible(element);
  const fileInput =
    element instanceof HTMLInputElement && element.type === "file";
  if (!visible && !fileInput) return null;
  if (
    element instanceof HTMLInputElement &&
    ["hidden", "password"].includes(element.type)
  ) {
    return null;
  }

  const validation = validationState(element);
  const validationMessage =
    validationMessageFor(element) || validation.validationMessage;
  const repeat = repeatMetadataFor(element);
  const fileFingerprint =
    element instanceof HTMLInputElement && element.type === "file"
      ? fileFingerprintFor(element)
      : null;
  const kind = kindFor(element);
  const options = optionsFor(element);
  return {
    controlId: `ctl-${hash(stableControlSignature(element))}`,
    frameId: 0,
    kind,
    tagName: element.tagName.toLowerCase(),
    name: compactText(element.getAttribute("name")),
    label: labelFor(element),
    placeholder: compactText(element.getAttribute("placeholder")),
    ariaLabel: compactText(element.getAttribute("aria-label")),
    required:
      element.hasAttribute("required") ||
      element.getAttribute("aria-required") === "true",
    disabled:
      ("disabled" in element &&
        Boolean((element as HTMLInputElement).disabled)) ||
      element.getAttribute("aria-disabled") === "true",
    visible,
    options,
    multiple:
      (element instanceof HTMLSelectElement && element.multiple) ||
      (element instanceof HTMLInputElement && element.multiple),
    autocomplete: compactText(element.getAttribute("autocomplete")),
    invalid:
      validation.invalid || element.getAttribute("aria-invalid") === "true",
    validationMessage,
    fileSelected: fileFingerprint ? fileFingerprint.count > 0 : undefined,
    role: compactText(element.getAttribute("role")),
    inputType: element instanceof HTMLInputElement ? element.type : "",
    hasPopup: compactText(element.getAttribute("aria-haspopup")),
    readOnly:
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement
        ? element.readOnly
        : element.getAttribute("aria-readonly") === "true",
    maxLength:
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement
        ? element.maxLength
        : undefined,
    minLength:
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement
        ? element.minLength
        : undefined,
    pattern: element instanceof HTMLInputElement ? element.pattern : undefined,
    accept:
      element instanceof HTMLInputElement && element.type === "file"
        ? element.accept
        : undefined,
    satisfied: controlSatisfied(element),
    validationCode: classifyValidationMessage(validationMessage),
    interactionConfidence: interactionConfidenceFor(element),
    repeatGroupId: repeat.groupId,
    repeatIndex: repeat.index,
    componentFingerprint: componentFingerprint({
      kind,
      tagName: element.tagName.toLowerCase(),
      role: element.getAttribute("role"),
      inputType: element instanceof HTMLInputElement ? element.type : null,
      optionCount: options.length,
      ariaAutocomplete: element.getAttribute("aria-autocomplete"),
      hasPopup: element.getAttribute("aria-haspopup"),
    }),
    fileFingerprintState: fileFingerprint?.state,
    fileSha256: fileFingerprint?.sha256,
    fileCount: fileFingerprint?.count,
    fileSize: fileFingerprint?.size,
    fileMimeType: fileFingerprint?.mimeType,
  };
}

type ControlEntry = { element: Element; control: Control };

const controlHints = new Map<string, Control>();

function scanControlEntries(): ControlEntry[] {
  const duplicateCounts = new Map<string, number>();
  const entries: ControlEntry[] = [];
  for (const element of collectInteractiveElements(document)) {
    const control = createControl(element);
    if (!control) continue;
    const count = duplicateCounts.get(control.controlId) ?? 0;
    duplicateCounts.set(control.controlId, count + 1);
    const finalControl =
      count === 0
        ? control
        : { ...control, controlId: `${control.controlId}-${count + 1}` };
    entries.push({ element, control: finalControl });
    controlHints.set(finalControl.controlId, finalControl);
  }
  return entries;
}

function createQuestion(control: Control): Question | null {
  if (control.kind === "BUTTON") return null;
  const rawText =
    control.label || control.ariaLabel || control.placeholder || control.name;
  if (!rawText) return null;
  const classification = classifyQuestion(rawText);
  return {
    questionId: `q-${control.controlId}`,
    controlId: control.controlId,
    rawText,
    semanticType: classification.semanticType,
    confidence: classification.confidence,
    sensitive: classification.sensitive,
    requiresReview: classification.requiresReview,
  };
}

function questionIdentity(entry: ControlEntry, question: Question): string {
  if (
    entry.control.kind === "RADIO" &&
    entry.element instanceof HTMLInputElement &&
    entry.element.name
  ) {
    return `radio|${entry.element.name}|${question.rawText}`;
  }
  return entry.control.controlId;
}

function navigationActionFor(label: string): NavigationAction | null {
  const value = normalized(label);
  if (!value) return null;
  if (
    /^(submit|submit application|send application|complete application|finish application|apply now|review and submit)$/.test(
      value,
    ) ||
    /\bsubmit (my |this )?application\b/.test(value)
  ) {
    return "FINAL_SUBMIT";
  }
  if (/^(back|previous|go back)$/.test(value)) return "BACK";
  if (
    /^(review|review application|preview application|save and review)$/.test(
      value,
    )
  ) {
    return "REVIEW";
  }
  if (
    /^(next|continue|continue application|save and continue|save & continue|proceed)$/.test(
      value,
    )
  ) {
    return "NEXT";
  }
  return null;
}

function navigationCandidates(
  entries: readonly ControlEntry[],
): NavigationCandidate[] {
  return entries.flatMap((entry) => {
    if (entry.control.kind !== "BUTTON") return [];
    const action = navigationActionFor(entry.control.label);
    if (!action) return [];
    if (
      entry.element instanceof HTMLInputElement &&
      entry.element.type === "reset"
    ) {
      return [];
    }
    return [
      {
        controlId: entry.control.controlId,
        frameId: entry.control.frameId,
        action,
        label: entry.control.label,
        disabled: entry.control.disabled,
      },
    ];
  });
}

function detectSecurityCheckpoint(): SecurityCheckpointKind | null {
  const body = normalized(document.body?.textContent).slice(0, 120_000);
  if (
    document.querySelector(
      "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='challenges.cloudflare.com'], [class*='captcha' i], [id*='captcha' i]",
    ) ||
    /\b(recaptcha|hcaptcha|captcha|verify you are human|human verification)\b/.test(
      body,
    )
  ) {
    return "CAPTCHA";
  }
  if (
    /\b(identity verification|verify your identity|proof of identity)\b/.test(
      body,
    )
  ) {
    return "IDENTITY_VERIFICATION";
  }
  if (/\b(multi[- ]factor|two[- ]factor|2fa|authenticator app)\b/.test(body)) {
    return "MFA";
  }
  if (
    /\b(one[- ]time (passcode|password|code)|verification code|security code|enter the code we sent|otp)\b/.test(
      body,
    )
  ) {
    return "OTP";
  }
  if (document.querySelector("input[type='password']")) return "AUTHENTICATION";
  return null;
}

const personalTypes = new Set<SemanticType>([
  "PERSONAL",
  "FIRST_NAME",
  "MIDDLE_NAME",
  "LAST_NAME",
  "PREFERRED_NAME",
  "CONTACT",
  "ADDRESS",
  "STREET_ADDRESS",
  "ADDRESS_LINE_2",
  "CITY",
  "STATE_PROVINCE",
  "POSTAL_CODE",
  "COUNTRY",
  "EMAIL",
  "PHONE",
]);
const educationTypes = new Set<SemanticType>([
  "EDUCATION",
  "SCHOOL_NAME",
  "DEGREE",
  "FIELD_OF_STUDY",
  "GRADUATION_DATE",
  "GPA",
]);
const experienceTypes = new Set<SemanticType>([
  "EMPLOYMENT",
  "EMPLOYER_NAME",
  "JOB_TITLE",
  "EMPLOYMENT_DATES",
  "EMPLOYMENT_RESPONSIBILITIES",
]);
const eeoTypes = new Set<SemanticType>([
  "VETERAN_STATUS",
  "PROTECTED_VETERAN_STATUS",
  "DISABILITY_STATUS",
  "GENDER",
  "RACE_ETHNICITY",
  "EEO_SELF_ID",
]);
const disclosureTypes = new Set<SemanticType>([
  "CONFLICT_OF_INTEREST",
  "NON_COMPETE",
  "BACKGROUND_CHECK",
  "DRUG_SCREENING",
]);

function hasQuestionType(
  questions: readonly Question[],
  types: ReadonlySet<SemanticType>,
): boolean {
  return questions.some((question) => types.has(question.semanticType));
}

function inferApplicationState(input: {
  questions: readonly Question[];
  controls: readonly Control[];
  navigation: readonly NavigationCandidate[];
  securityCheckpoint: SecurityCheckpointKind | null;
  finalSubmissionBoundary: boolean;
}): ApplicationState {
  const context = normalized(
    `${document.title} ${window.location.pathname} ${document.body?.textContent ?? ""}`,
  ).slice(0, 120_000);

  if (
    /\b(thank you for applying|application received|application has been submitted|application submitted successfully)\b/.test(
      context,
    )
  ) {
    return "CONFIRMATION";
  }
  if (input.securityCheckpoint === "AUTHENTICATION") return "AUTH";
  if (
    input.securityCheckpoint === "MFA" ||
    input.securityCheckpoint === "OTP" ||
    input.securityCheckpoint === "IDENTITY_VERIFICATION"
  ) {
    return "VERIFY_ACCOUNT";
  }
  if (input.finalSubmissionBoundary) return "SUBMISSION";
  if (
    input.navigation.some((candidate) => candidate.action === "REVIEW") ||
    /\breview (your |my )?application\b/.test(context)
  ) {
    return "REVIEW";
  }
  if (hasQuestionType(input.questions, eeoTypes)) return "EEO";
  if (hasQuestionType(input.questions, disclosureTypes)) return "DISCLOSURES";
  if (
    input.controls.some(
      (control) =>
        control.kind === "FILE" &&
        /\b(resume|résumé|cv)\b/i.test(control.label),
    ) ||
    /\b(upload (your )?(resume|résumé|cv))\b/.test(context)
  ) {
    return "RESUME";
  }
  if (hasQuestionType(input.questions, educationTypes)) return "EDUCATION";
  if (hasQuestionType(input.questions, experienceTypes)) return "EXPERIENCE";
  if (hasQuestionType(input.questions, personalTypes)) return "PERSONAL";
  return "QUESTIONS";
}

export function scanDocument(): ApplicationPage {
  const entries = scanControlEntries();
  const controls = entries.map((entry) => entry.control);
  const questions: Question[] = [];
  const seenQuestions = new Set<string>();
  for (const entry of entries) {
    const question = createQuestion(entry.control);
    if (!question) continue;
    const identity = questionIdentity(entry, question);
    if (seenQuestions.has(identity)) continue;
    seenQuestions.add(identity);
    questions.push(question);
  }
  const url = new URL(window.location.href);
  const pageSignature = `${url.origin}${url.pathname}|${document.title}`;
  const navigation = navigationCandidates(entries);
  const securityCheckpoint = detectSecurityCheckpoint();
  const finalSubmissionBoundary = navigation.some(
    (candidate) => candidate.action === "FINAL_SUBMIT" && !candidate.disabled,
  );
  const applicationState = inferApplicationState({
    questions,
    controls,
    navigation,
    securityCheckpoint,
    finalSubmissionBoundary,
  });
  const page: ApplicationPage = {
    pageId: `page-${hash(pageSignature)}`,
    tabId: -1,
    frameId: 0,
    documentId: `doc-${hash(pageSignature)}`,
    url: url.href,
    title: document.title,
    observedAt: new Date().toISOString(),
    controls,
    questions,
    applicationState,
    pageFingerprint: "",
    securityCheckpoint,
    validationErrorCount: controls.filter((control) => control.invalid).length,
    navigationCandidates: navigation,
    finalSubmissionBoundary,
    atsFamily: detectAtsFamily(),
  };
  return { ...page, pageFingerprint: snapshotFingerprint(page) };
}

export function controlElementMap(): Map<string, Element> {
  return new Map(
    scanControlEntries().map((entry) => [
      entry.control.controlId,
      entry.element,
    ]),
  );
}

function sameText(
  left: string | undefined,
  right: string | undefined,
): boolean {
  return normalized(left) !== "" && normalized(left) === normalized(right);
}

function reboundScore(hint: Control, candidate: Control): number {
  if (hint.kind !== candidate.kind) return -1;
  if (
    hint.repeatIndex !== null &&
    hint.repeatIndex !== undefined &&
    candidate.repeatIndex !== hint.repeatIndex
  ) {
    return -1;
  }
  let score = 4;
  if (sameText(hint.label, candidate.label)) score += 5;
  if (sameText(hint.name, candidate.name)) score += 4;
  if (sameText(hint.ariaLabel, candidate.ariaLabel)) score += 4;
  if (sameText(hint.placeholder, candidate.placeholder)) score += 2;
  if (sameText(hint.autocomplete, candidate.autocomplete)) score += 2;
  if (hint.tagName === candidate.tagName) score += 1;
  if (hint.repeatGroupId && candidate.repeatGroupId === hint.repeatGroupId) {
    score += 3;
  }
  if (
    hint.componentFingerprint &&
    candidate.componentFingerprint === hint.componentFingerprint
  ) {
    score += 2;
  }
  return score;
}

export function resolveControlElement(
  controlId: string,
): { element: Element; control: Control; rebound: boolean } | null {
  const hint = controlHints.get(controlId);
  const entries = scanControlEntries();
  const exact = entries.find((entry) => entry.control.controlId === controlId);
  if (exact) return { ...exact, rebound: false };
  if (!hint) return null;

  const ranked = entries
    .map((entry) => ({ entry, score: reboundScore(hint, entry.control) }))
    .filter((item) => item.score >= 9)
    .sort((left, right) => right.score - left.score);
  if (ranked.length === 0) return null;
  if (ranked.length > 1 && ranked[0]!.score === ranked[1]!.score) return null;
  return { ...ranked[0]!.entry, rebound: true };
}

export function snapshotFingerprint(page: ApplicationPage): string {
  return hash(
    JSON.stringify({
      pageId: page.pageId,
      controls: page.controls,
      questions: page.questions,
      applicationState: page.applicationState,
      securityCheckpoint: page.securityCheckpoint,
      validationErrorCount: page.validationErrorCount,
      navigationCandidates: page.navigationCandidates,
      finalSubmissionBoundary: page.finalSubmissionBoundary,
      atsFamily: page.atsFamily,
    }),
  );
}
