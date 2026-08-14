from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content)


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    if content.count(old) != 1:
        raise RuntimeError(f"Expected exactly one match in {path}: {old[:120]!r}")
    write(path, content.replace(old, new, 1))


# Contracts: preserve backward compatibility by making the richer metadata optional.
replace_once(
    "packages/contracts/src/index.ts",
    '''export type FillResult = {\n  controlId: string;\n  status: "FILLED" | "SKIPPED" | "FAILED";\n  reason: string;\n};''',
    '''export type FillResult = {\n  controlId: string;\n  status: "FILLED" | "SKIPPED" | "FAILED";\n  reason: string;\n  strategy?: string;\n  verification?: string;\n  rebound?: boolean;\n  stabilized?: boolean;\n  componentFingerprint?: string;\n  recipeId?: string;\n  recipeAttempted?: boolean;\n  recipeSucceeded?: boolean;\n};''',
)
replace_once(
    "packages/contracts/src/index.ts",
    '''  validationMessage: z.string().default(""),\n  fileSelected: z.boolean().optional(),\n});''',
    '''  validationMessage: z.string().default(""),\n  fileSelected: z.boolean().optional(),\n  role: z.string().optional(),\n  inputType: z.string().optional(),\n  hasPopup: z.string().optional(),\n  readOnly: z.boolean().optional(),\n  maxLength: z.number().int().optional(),\n  minLength: z.number().int().optional(),\n  pattern: z.string().optional(),\n  accept: z.string().optional(),\n  satisfied: z.boolean().optional(),\n  validationCode: z\n    .enum([\n      "NONE",\n      "REQUIRED",\n      "FORMAT",\n      "TOO_LONG",\n      "TOO_SHORT",\n      "RANGE",\n      "PATTERN",\n      "FILE_TYPE",\n      "FILE_SIZE",\n      "UNKNOWN",\n    ])\n    .optional(),\n  interactionConfidence: z.number().min(0).max(1).optional(),\n  repeatGroupId: z.string().nullable().optional(),\n  repeatIndex: z.number().int().nonnegative().nullable().optional(),\n  componentFingerprint: z.string().optional(),\n  fileFingerprintState: z\n    .enum(["NONE", "PENDING", "READY", "ERROR"])\n    .optional(),\n  fileSha256: z.string().regex(/^[a-f0-9]{64}$/).nullable().optional(),\n  fileCount: z.number().int().nonnegative().optional(),\n  fileSize: z.number().int().nonnegative().nullable().optional(),\n  fileMimeType: z.string().nullable().optional(),\n});''',
)
replace_once(
    "packages/contracts/src/index.ts",
    '''  finalSubmissionBoundary: z.boolean().default(false),\n});''',
    '''  finalSubmissionBoundary: z.boolean().default(false),\n  atsFamily: z\n    .enum([\n      "WORKDAY",\n      "GREENHOUSE",\n      "LEVER",\n      "ASHBY",\n      "SMARTRECRUITERS",\n      "ICIMS",\n      "TALEO",\n      "GENERIC",\n    ])\n    .optional(),\n});''',
)

# Scanner: richer widget discovery, stable metadata, file fingerprints, and self-healing rebinding.
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''import { classifyQuestion } from "@munshi-apply/semantic-engine";''',
    '''import { componentFingerprint } from "@munshi-apply/application-model";\nimport { classifyQuestion } from "@munshi-apply/semantic-engine";\nimport {\n  classifyValidationMessage,\n  detectAtsFamily,\n  fileFingerprintFor,\n  interactionConfidenceFor,\n  isAriaBooleanControl,\n  isAriaRadioControl,\n  isCustomDateControl,\n  isPopupChoiceControl,\n  repeatMetadataFor,\n  validationMessageFor,\n} from "./adaptive";''',
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''  "[role='combobox']",\n  "[contenteditable='true']",''',
    '''  "[role='combobox']",\n  "[role='checkbox']",\n  "[role='switch']",\n  "[role='radio']",\n  "[role='spinbutton']",\n  "[aria-haspopup='listbox']",\n  "[aria-haspopup='tree']",\n  "[aria-haspopup='grid']",\n  "[aria-haspopup='dialog']",\n  "[contenteditable='true']",''',
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''  return collected;\n}\n\nfunction compactText''',
    '''  return [...new Set(collected)];\n}\n\nfunction compactText''',
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''  if (element.getAttribute("role") === "combobox") return "COMBOBOX";\n  if (element instanceof HTMLTextAreaElement) return "TEXTAREA";''',
    '''  if (isCustomDateControl(element) || isPopupChoiceControl(element)) {\n    return "COMBOBOX";\n  }\n  if (isAriaBooleanControl(element)) return "CHECKBOX";\n  if (isAriaRadioControl(element)) return "RADIO";\n  if (element.getAttribute("role") === "spinbutton") return "NUMBER";\n  if (element instanceof HTMLTextAreaElement) return "TEXTAREA";''',
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''      ...(container.getAttribute("role") === "option" ? [container] : []),\n      ...Array.from(container.querySelectorAll("[role='option']")),''',
    '''      ...(["option", "treeitem", "gridcell"].includes(\n        container.getAttribute("role") ?? "",\n      )\n        ? [container]\n        : []),\n      ...Array.from(\n        container.querySelectorAll(\n          "[role='option'], [role='treeitem'], [role='gridcell']",\n        ),\n      ),''',
)
insert_before_create = '''function controlSatisfied(element: Element): boolean {\n  if (\n    ("disabled" in element && Boolean((element as HTMLInputElement).disabled)) ||\n    element.getAttribute("aria-disabled") === "true"\n  ) {\n    return true;\n  }\n  if (element instanceof HTMLInputElement) {\n    if (element.type === "file") return Boolean(element.files?.length);\n    if (element.type === "checkbox") return element.checked;\n    if (element.type === "radio") {\n      return radioGroup(element).some((candidate) => candidate.checked);\n    }\n    return Boolean(compactText(element.value)) && element.validity.valid;\n  }\n  if (element instanceof HTMLSelectElement) {\n    return Boolean(compactText(element.value)) && element.validity.valid;\n  }\n  if (element instanceof HTMLTextAreaElement) {\n    return Boolean(compactText(element.value)) && element.validity.valid;\n  }\n  if (isAriaBooleanControl(element) || isAriaRadioControl(element)) {\n    return element.getAttribute("aria-checked") === "true";\n  }\n  if (element instanceof HTMLElement && element.isContentEditable) {\n    return Boolean(compactText(element.textContent));\n  }\n  return Boolean(\n    compactText(element.getAttribute("aria-valuetext")) ||\n      compactText(element.getAttribute("data-value")) ||\n      compactText(element.getAttribute("aria-activedescendant")),\n  );\n}\n\n'''
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''function createControl(element: Element): Control | null {''',
    insert_before_create + '''function createControl(element: Element): Control | null {''',
)
old_create_start = '''  const validation = validationState(element);\n  return {\n    controlId: `ctl-${hash(stableControlSignature(element))}`,'''
new_create_start = '''  const validation = validationState(element);\n  const validationMessage = validationMessageFor(element) || validation.validationMessage;\n  const repeat = repeatMetadataFor(element);\n  const fileFingerprint =\n    element instanceof HTMLInputElement && element.type === "file"\n      ? fileFingerprintFor(element)\n      : null;\n  const kind = kindFor(element);\n  const options = optionsFor(element);\n  return {\n    controlId: `ctl-${hash(stableControlSignature(element))}`,'''
replace_once("apps/extension/src/content/scanner.ts", old_create_start, new_create_start)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''    kind: kindFor(element),''',
    '''    kind,''',
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''    options: optionsFor(element),''',
    '''    options,''',
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''    invalid: validation.invalid,\n    validationMessage: validation.validationMessage,\n    fileSelected:\n      element instanceof HTMLInputElement && element.type === "file"\n        ? Boolean(element.files?.length)\n        : undefined,\n  };''',
    '''    invalid: validation.invalid || element.getAttribute("aria-invalid") === "true",\n    validationMessage,\n    fileSelected: fileFingerprint ? fileFingerprint.count > 0 : undefined,\n    role: compactText(element.getAttribute("role")),\n    inputType: element instanceof HTMLInputElement ? element.type : "",\n    hasPopup: compactText(element.getAttribute("aria-haspopup")),\n    readOnly:\n      (element instanceof HTMLInputElement ||\n        element instanceof HTMLTextAreaElement)\n        ? element.readOnly\n        : element.getAttribute("aria-readonly") === "true",\n    maxLength:\n      element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement\n        ? element.maxLength\n        : undefined,\n    minLength:\n      element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement\n        ? element.minLength\n        : undefined,\n    pattern: element instanceof HTMLInputElement ? element.pattern : undefined,\n    accept:\n      element instanceof HTMLInputElement && element.type === "file"\n        ? element.accept\n        : undefined,\n    satisfied: controlSatisfied(element),\n    validationCode: classifyValidationMessage(validationMessage),\n    interactionConfidence: interactionConfidenceFor(element),\n    repeatGroupId: repeat.groupId,\n    repeatIndex: repeat.index,\n    componentFingerprint: componentFingerprint({\n      kind,\n      tagName: element.tagName.toLowerCase(),\n      role: element.getAttribute("role"),\n      inputType: element instanceof HTMLInputElement ? element.type : null,\n      optionCount: options.length,\n      ariaAutocomplete: element.getAttribute("aria-autocomplete"),\n      hasPopup: element.getAttribute("aria-haspopup"),\n    }),\n    fileFingerprintState: fileFingerprint?.state,\n    fileSha256: fileFingerprint?.sha256,\n    fileCount: fileFingerprint?.count,\n    fileSize: fileFingerprint?.size,\n    fileMimeType: fileFingerprint?.mimeType,\n  };''',
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''type ControlEntry = { element: Element; control: Control };\n\nfunction scanControlEntries(): ControlEntry[] {''',
    '''type ControlEntry = { element: Element; control: Control };\n\nconst controlHints = new Map<string, Control>();\n\nfunction scanControlEntries(): ControlEntry[] {''',
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''    entries.push({\n      element,\n      control:\n        count === 0\n          ? control\n          : { ...control, controlId: `${control.controlId}-${count + 1}` },\n    });''',
    '''    const finalControl =\n      count === 0\n        ? control\n        : { ...control, controlId: `${control.controlId}-${count + 1}` };\n    entries.push({ element, control: finalControl });\n    controlHints.set(finalControl.controlId, finalControl);''',
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''    finalSubmissionBoundary,\n  };''',
    '''    finalSubmissionBoundary,\n    atsFamily: detectAtsFamily(),\n  };''',
)
resolve_code = '''\nfunction sameText(left: string | undefined, right: string | undefined): boolean {\n  return normalized(left) !== "" && normalized(left) === normalized(right);\n}\n\nfunction reboundScore(hint: Control, candidate: Control): number {\n  if (hint.kind !== candidate.kind) return -1;\n  if (\n    hint.repeatIndex !== null &&\n    hint.repeatIndex !== undefined &&\n    candidate.repeatIndex !== hint.repeatIndex\n  ) {\n    return -1;\n  }\n  let score = 4;\n  if (sameText(hint.label, candidate.label)) score += 5;\n  if (sameText(hint.name, candidate.name)) score += 4;\n  if (sameText(hint.ariaLabel, candidate.ariaLabel)) score += 4;\n  if (sameText(hint.placeholder, candidate.placeholder)) score += 2;\n  if (sameText(hint.autocomplete, candidate.autocomplete)) score += 2;\n  if (hint.tagName === candidate.tagName) score += 1;\n  if (\n    hint.repeatGroupId &&\n    candidate.repeatGroupId === hint.repeatGroupId\n  ) {\n    score += 3;\n  }\n  if (\n    hint.componentFingerprint &&\n    candidate.componentFingerprint === hint.componentFingerprint\n  ) {\n    score += 2;\n  }\n  return score;\n}\n\nexport function resolveControlElement(controlId: string):\n  | { element: Element; control: Control; rebound: boolean }\n  | null {\n  const hint = controlHints.get(controlId);\n  const entries = scanControlEntries();\n  const exact = entries.find((entry) => entry.control.controlId === controlId);\n  if (exact) return { ...exact, rebound: false };\n  if (!hint) return null;\n\n  const ranked = entries\n    .map((entry) => ({ entry, score: reboundScore(hint, entry.control) }))\n    .filter((item) => item.score >= 9)\n    .sort((left, right) => right.score - left.score);\n  if (ranked.length === 0) return null;\n  if (ranked.length > 1 && ranked[0]!.score === ranked[1]!.score) return null;\n  return { ...ranked[0]!.entry, rebound: true };\n}\n'''
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''export function snapshotFingerprint(page: ApplicationPage): string {''',
    resolve_code + '''\nexport function snapshotFingerprint(page: ApplicationPage): string {''',
)
replace_once(
    "apps/extension/src/content/scanner.ts",
    '''      finalSubmissionBoundary: page.finalSubmissionBoundary,\n    }),''',
    '''      finalSubmissionBoundary: page.finalSubmissionBoundary,\n      atsFamily: page.atsFamily,\n    }),''',
)

# Native multi-select: deterministic semantic equivalence and duplicate rejection.
write(
    "apps/extension/src/content/multi-select.ts",
    '''import {\n  interactionContext,\n  optionEquivalent,\n  parseRequestedOptionValues,\n} from "./adaptive";\n\nexport function fillNativeMultiSelect(\n  element: HTMLSelectElement,\n  value: string,\n): boolean {\n  if (!element.multiple || element.disabled) return false;\n  const requested = parseRequestedOptionValues(value);\n  if (!requested || requested.length === 0) return false;\n\n  const previous = Array.from(element.options).map((option) => option.selected);\n  const context = interactionContext(element);\n  const matches = new Set<HTMLOptionElement>();\n\n  for (const requestedValue of requested) {\n    const candidates = Array.from(element.options).filter(\n      (option) =>\n        !option.disabled &&\n        (optionEquivalent(option.value, requestedValue, context) ||\n          optionEquivalent(option.text, requestedValue, context)),\n    );\n    if (candidates.length !== 1) {\n      Array.from(element.options).forEach((option, index) => {\n        option.selected = previous[index] ?? false;\n      });\n      return false;\n    }\n    matches.add(candidates[0]!);\n  }\n\n  if (matches.size !== requested.length) return false;\n  Array.from(element.options).forEach((option) => {\n    option.selected = matches.has(option);\n  });\n  element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));\n  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));\n  element.dispatchEvent(new Event("blur", { bubbles: true, composed: true }));\n\n  const selected = Array.from(element.selectedOptions);\n  const verified =\n    selected.length === matches.size && selected.every((option) => matches.has(option));\n  if (!verified) {\n    Array.from(element.options).forEach((option, index) => {\n      option.selected = previous[index] ?? false;\n    });\n  }\n  return verified;\n}\n''',
)

# Fill runtime: semantic option mapping, custom widgets, adaptive waits, rebinding, and explainability.
replace_once(
    "apps/extension/src/content/fill.ts",
    '''import { fillNativeMultiSelect } from "./multi-select";\nimport { controlElementMap } from "./scanner";''',
    '''import { fillNativeMultiSelect } from "./multi-select";\nimport { resolveControlElement } from "./scanner";\nimport {\n  defaultAdaptiveTiming,\n  fillAriaBooleanControl,\n  fillAriaRadioControl,\n  fillCustomDateControl,\n  interactionContext,\n  isPopupChoiceControl,\n  optionEquivalent,\n  validationFailureReason,\n  waitForDomStability,\n} from "./adaptive";''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''  verificationTimeoutMs?: number;\n};''',
    '''  verificationTimeoutMs?: number;\n  stabilityQuietMs?: number;\n  stabilityTimeoutMs?: number;\n};''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''function radioCandidateValues(element: HTMLInputElement): string[] {\n  return [\n    normalized(element.value),\n    normalized(inputLabel(element)),\n    normalized(element.getAttribute("aria-label") ?? ""),\n  ].filter(Boolean);\n}\n\nfunction radioMatches(candidate: HTMLInputElement, requested: string): boolean {\n  const values = radioCandidateValues(candidate);\n  if (values.includes(requested)) return true;\n  if (["true", "yes", "1", "checked"].includes(requested)) {\n    return values.some((value) => ["true", "yes", "1"].includes(value));\n  }\n  if (["false", "no", "0", "unchecked"].includes(requested)) {\n    return values.some((value) => ["false", "no", "0"].includes(value));\n  }\n  return false;\n}\n\nfunction fillRadio(element: HTMLInputElement, value: string): boolean {\n  const requested = normalized(value);\n  const candidates = radioCandidates(element).filter((candidate) =>\n    radioMatches(candidate, requested),\n  );''',
    '''function radioCandidateValues(element: HTMLInputElement): string[] {\n  return [\n    compactText(element.value),\n    compactText(inputLabel(element)),\n    compactText(element.getAttribute("aria-label")),\n  ].filter(Boolean);\n}\n\nfunction radioMatches(candidate: HTMLInputElement, requested: string): boolean {\n  const context = interactionContext(candidate);\n  return radioCandidateValues(candidate).some((value) =>\n    optionEquivalent(value, requested, context),\n  );\n}\n\nfunction fillRadio(element: HTMLInputElement, value: string): boolean {\n  const candidates = radioCandidates(element).filter((candidate) =>\n    radioMatches(candidate, value),\n  );''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''function comboboxOptionValues(option: HTMLElement): string[] {\n  return [\n    normalized(option.textContent ?? ""),\n    normalized(option.getAttribute("aria-label") ?? ""),\n    normalized(option.getAttribute("data-value") ?? ""),\n  ].filter(Boolean);\n}''',
    '''function comboboxOptionValues(option: HTMLElement): string[] {\n  return [\n    compactText(option.textContent),\n    compactText(option.getAttribute("aria-label")),\n    compactText(option.getAttribute("data-value")),\n    compactText(option.getAttribute("value")),\n  ].filter(Boolean);\n}''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''  const controlled = controlledComboboxOptions(element).filter(\n    (option) =>\n      optionAvailable(option) &&\n      comboboxOptionValues(option).includes(requested),\n  );''',
    '''  const context = interactionContext(element);\n  const controlled = controlledComboboxOptions(element).filter(\n    (option) =>\n      optionAvailable(option) &&\n      comboboxOptionValues(option).some((value) =>\n        optionEquivalent(value, requested, context),\n      ),\n  );''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''  const portaled = portaledComboboxOptions(element).filter(\n    (option) =>\n      optionAvailable(option) &&\n      comboboxOptionValues(option).includes(requested),\n  );''',
    '''  const portaled = portaledComboboxOptions(element).filter(\n    (option) =>\n      optionAvailable(option) &&\n      comboboxOptionValues(option).some((value) =>\n        optionEquivalent(value, requested, context),\n      ),\n  );''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''  if (\n    element instanceof HTMLInputElement &&\n    normalized(element.value) === requested\n  ) {\n    return true;\n  }\n  if (normalized(element.textContent ?? "") === requested) return true;''',
    '''  const context = interactionContext(element);\n  if (\n    element instanceof HTMLInputElement &&\n    optionEquivalent(element.value, requested, context)\n  ) {\n    return true;\n  }\n  if (optionEquivalent(element.textContent ?? "", requested, context)) return true;''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''  const requested = normalized(value);\n  if (!requested) return false;''',
    '''  const requested = compactText(value);\n  if (!requested) return false;''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''function radioVerified(element: HTMLInputElement, value: string): boolean {\n  const requested = normalized(value);\n  const checked = radioCandidates(element).filter(\n    (candidate) => candidate.checked,\n  );\n  return checked.length === 1 && radioMatches(checked[0]!, requested);\n}''',
    '''function radioVerified(element: HTMLInputElement, value: string): boolean {\n  const checked = radioCandidates(element).filter(\n    (candidate) => candidate.checked,\n  );\n  return checked.length === 1 && radioMatches(checked[0]!, value);\n}''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''  if (elementUnavailable(element)) return false;\n  if (\n    element instanceof HTMLElement &&\n    element.getAttribute("role") === "combobox"\n  ) {\n    return fillCombobox(element, value, options);\n  }''',
    '''  if (elementUnavailable(element)) return false;\n  if (element.getAttribute("aria-readonly") === "true") return false;\n  if (element instanceof HTMLElement) {\n    const customDate = await fillCustomDateControl(element, value, options);\n    if (customDate !== null) return customDate;\n    const ariaBoolean = await fillAriaBooleanControl(element, value, options);\n    if (ariaBoolean !== null) return ariaBoolean;\n    const ariaRadio = await fillAriaRadioControl(element, value, options);\n    if (ariaRadio !== null) return ariaRadio;\n    if (isPopupChoiceControl(element)) {\n      return fillCombobox(element, value, options);\n    }\n  }''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''    const original = element.value;\n    element.focus();\n    setNativeValue(element, value);''',
    '''    const original = element.value;\n    if (element.maxLength >= 0 && value.length > element.maxLength) return false;\n    element.focus();\n    setNativeValue(element, value);''',
)
# Apply max length to textarea too (the same anchor occurs again after input; target its surrounding branch).
replace_once(
    "apps/extension/src/content/fill.ts",
    '''  if (element instanceof HTMLTextAreaElement) {\n    if (element.readOnly) return false;\n    const original = element.value;\n    element.focus();''',
    '''  if (element instanceof HTMLTextAreaElement) {\n    if (element.readOnly) return false;\n    if (element.maxLength >= 0 && value.length > element.maxLength) return false;\n    const original = element.value;\n    element.focus();''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''    const requested = normalized(value);\n    const matches = Array.from(element.options).filter(\n      (candidate) =>\n        normalized(candidate.value) === requested ||\n        normalized(candidate.text) === requested,\n    );''',
    '''    const context = interactionContext(element);\n    const matches = Array.from(element.options).filter(\n      (candidate) =>\n        !candidate.disabled &&\n        (optionEquivalent(candidate.value, value, context) ||\n          optionEquivalent(candidate.text, value, context)),\n    );''',
)
# Remove now-unused normalized helper after all native booleans still use it; keep it for checkbox.
replace_once(
    "apps/extension/src/content/fill.ts",
    '''export function assistFilePicker(controlId: string): FilePickerAssistResult {\n  const element = controlElementMap().get(controlId);\n  if (\n    !(element instanceof HTMLInputElement) ||''',
    '''export function assistFilePicker(controlId: string): FilePickerAssistResult {\n  const resolved = resolveControlElement(controlId);\n  const element = resolved?.element;\n  if (\n    !(element instanceof HTMLInputElement) ||''',
)
strategy_code = '''\nfunction strategyFor(element: Element): string {\n  if (isPopupChoiceControl(element)) {\n    return element.getAttribute("aria-haspopup") === "dialog"\n      ? "CUSTOM_DATE"\n      : "ARIA_COMBOBOX";\n  }\n  if (element.getAttribute("role") === "radio") return "ARIA_RADIO";\n  if (["checkbox", "switch"].includes(element.getAttribute("role") ?? "")) {\n    return "ARIA_BOOLEAN";\n  }\n  if (element instanceof HTMLSelectElement) {\n    return element.multiple ? "NATIVE_MULTI_SELECT" : "NATIVE_SELECT";\n  }\n  if (element instanceof HTMLInputElement) return `NATIVE_${element.type.toUpperCase()}`;\n  if (element instanceof HTMLTextAreaElement) return "NATIVE_TEXTAREA";\n  if (element instanceof HTMLElement && element.isContentEditable) return "CONTENTEDITABLE";\n  return "UNKNOWN";\n}\n\nasync function resolveWithRetry(\n  controlId: string,\n  options: Required<FillInteractionOptions>,\n): Promise<ReturnType<typeof resolveControlElement>> {\n  const deadline = Date.now() + Math.min(350, options.verificationTimeoutMs);\n  while (Date.now() <= deadline) {\n    const resolved = resolveControlElement(controlId);\n    if (resolved) return resolved;\n    await delay(options.pollIntervalMs);\n  }\n  return resolveControlElement(controlId);\n}\n'''
replace_once(
    "apps/extension/src/content/fill.ts",
    '''export async function applyFillInstructions(''',
    strategy_code + '''\nexport async function applyFillInstructions(''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''  const elements = controlElementMap();\n  const options: Required<FillInteractionOptions> = {\n    optionTimeoutMs:\n      interactionOptions.optionTimeoutMs ?? DEFAULT_OPTION_TIMEOUT_MS,\n    pollIntervalMs:\n      interactionOptions.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS,\n    verificationTimeoutMs:\n      interactionOptions.verificationTimeoutMs ??\n      DEFAULT_VERIFICATION_TIMEOUT_MS,\n  };''',
    '''  const adaptive = defaultAdaptiveTiming();\n  const options: Required<FillInteractionOptions> = {\n    optionTimeoutMs:\n      interactionOptions.optionTimeoutMs ??\n      adaptive.optionTimeoutMs ??\n      DEFAULT_OPTION_TIMEOUT_MS,\n    pollIntervalMs:\n      interactionOptions.pollIntervalMs ??\n      adaptive.pollIntervalMs ??\n      DEFAULT_POLL_INTERVAL_MS,\n    verificationTimeoutMs:\n      interactionOptions.verificationTimeoutMs ??\n      adaptive.verificationTimeoutMs ??\n      DEFAULT_VERIFICATION_TIMEOUT_MS,\n    stabilityQuietMs:\n      interactionOptions.stabilityQuietMs ?? adaptive.stabilityQuietMs,\n    stabilityTimeoutMs:\n      interactionOptions.stabilityTimeoutMs ?? adaptive.stabilityTimeoutMs,\n  };''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''    const element = elements.get(instruction.controlId);\n    if (!element) {''',
    '''    const resolved = await resolveWithRetry(instruction.controlId, options);\n    const element = resolved?.element;\n    if (!element) {''',
)
replace_once(
    "apps/extension/src/content/fill.ts",
    '''    let filled = false;\n    try {\n      filled = await fillElement(element, instruction.value, options);\n    } catch {\n      filled = false;\n    }\n    results.push({\n      controlId: instruction.controlId,\n      status: filled ? "FILLED" : "FAILED",\n      reason: filled\n        ? "Value applied, browser events dispatched, and DOM value verified"\n        : "Control is unsupported, ambiguous, timed out, or its value did not verify",\n    });''',
    '''    let filled = false;\n    const strategy = strategyFor(element);\n    try {\n      filled = await fillElement(element, instruction.value, options);\n    } catch {\n      filled = false;\n    }\n    const stabilized = filled\n      ? await waitForDomStability(\n          options.stabilityQuietMs,\n          options.stabilityTimeoutMs,\n        )\n      : false;\n    results.push({\n      controlId: instruction.controlId,\n      status: filled ? "FILLED" : "FAILED",\n      reason: filled\n        ? stabilized\n          ? "Value applied, verified, and the dependent DOM reached a quiet state"\n          : "Value applied and verified; the dependent DOM was still changing at the stability timeout"\n        : `${validationFailureReason(element, instruction.value)}; the control may also be unsupported or ambiguous`,\n      strategy,\n      verification: filled ? "POST_ACTION_DOM_VERIFIED" : "FAILED_CLOSED",\n      rebound: resolved?.rebound ?? false,\n      stabilized,\n      componentFingerprint: resolved?.control.componentFingerprint,\n    });''',
)

# Bootstrap: hash owner-selected files locally and observe richer widget state.
replace_once(
    "apps/extension/src/content/bootstrap.ts",
    '''import { applyFillInstructions, assistFilePicker } from "./fill";''',
    '''import { applyFillInstructions, assistFilePicker } from "./fill";\nimport { refreshFileFingerprint } from "./adaptive";''',
)
replace_once(
    "apps/extension/src/content/bootstrap.ts",
    '''    "aria-expanded",\n    "aria-hidden",''',
    '''    "aria-activedescendant",\n    "aria-busy",\n    "aria-checked",\n    "aria-expanded",\n    "aria-hidden",''',
)
replace_once(
    "apps/extension/src/content/bootstrap.ts",
    '''    "aria-required",\n    "class",''',
    '''    "aria-required",\n    "aria-selected",\n    "aria-valuetext",\n    "class",\n    "data-value",''',
)
replace_once(
    "apps/extension/src/content/bootstrap.ts",
    '''document.addEventListener("input", () => scheduleScan(), true);\ndocument.addEventListener("change", () => scheduleScan(), true);''',
    '''document.addEventListener("input", () => scheduleScan(), true);\ndocument.addEventListener(\n  "change",\n  (event) => {\n    const target = event.target;\n    if (target instanceof HTMLInputElement && target.type === "file") {\n      void refreshFileFingerprint(target).finally(() => scheduleScan(true));\n      return;\n    }\n    scheduleScan();\n  },\n  true,\n);\ndocument.addEventListener("invalid", () => scheduleScan(true), true);\ndocument.addEventListener("blur", () => scheduleScan(), true);\nwindow.addEventListener("pageshow", () => scheduleScan(true));\ndocument.addEventListener("visibilitychange", () => {\n  if (document.visibilityState === "visible") scheduleScan(true);\n});''',
)

# Vault + service worker: remove stale per-frame snapshots on iframe document replacement.
replace_once(
    "apps/extension/src/storage/vault.ts",
    '''export async function clearPagesForTab(tabId: number): Promise<void> {''',
    '''export async function deletePage(tabId: number, frameId: number): Promise<void> {\n  const database = await openVault();\n  await new Promise<void>((resolve, reject) => {\n    const transaction = database.transaction(pagesStore, "readwrite");\n    transaction.objectStore(pagesStore).delete(`${tabId}:${frameId}`);\n    transaction.onerror = () =>\n      reject(transaction.error ?? new Error("Vault page deletion failed"));\n    transaction.oncomplete = () => {\n      database.close();\n      resolve();\n    };\n  });\n}\n\nexport async function clearPagesForTab(tabId: number): Promise<void> {''',
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    '''  clearPagesForTab,\n  getLatestPage,''',
    '''  clearPagesForTab,\n  deletePage,\n  getLatestPage,''',
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    '''if (!supportsSidePanel) {''',
    '''if (chrome.webNavigation?.onCommitted) {\n  chrome.webNavigation.onCommitted.addListener((details) => {\n    if (details.tabId < 0) return;\n    if (details.frameId === 0) {\n      void clearPagesForTab(details.tabId);\n    } else {\n      void deletePage(details.tabId, details.frameId);\n    }\n  });\n}\n\nif (!supportsSidePanel) {''',
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    '''        if (frameId === 0) {\n          const previousTopLevel = await getPage(tabId, 0);\n          if (\n            previousTopLevel &&\n            previousTopLevel.documentId !== page.documentId\n          ) {\n            await clearPagesForTab(tabId);\n          }\n        }''',
    '''        const previousFrame = await getPage(tabId, frameId);\n        if (previousFrame && previousFrame.documentId !== page.documentId) {\n          if (frameId === 0) await clearPagesForTab(tabId);\n          else await deletePage(tabId, frameId);\n        }''',
)
replace_once(
    "apps/extension/public/manifest.json",
    '''"permissions": ["nativeMessaging", "sidePanel", "storage", "tabs"],''',
    '''"permissions": [\n    "nativeMessaging",\n    "sidePanel",\n    "storage",\n    "tabs",\n    "webNavigation"\n  ],''',
)

# AutoPilot: block navigation when a dependency reveals a new required unanswered control.
replace_once(
    "packages/application-model/src/autopilot.ts",
    '''  isFinalSubmissionStep: boolean;\n};''',
    '''  isFinalSubmissionStep: boolean;\n  unresolvedRequiredControlIds?: readonly string[];\n};''',
)
replace_once(
    "packages/application-model/src/autopilot.ts",
    '''  if (instruction) {\n    return {\n      action: { type: "FILL", instruction },\n      checkpointRequired: false,\n      reason:\n        "Apply one approved visible instruction and verify before continuing",\n    };\n  }\n\n  if (observation.canNavigateNext) {''',
    '''  if (instruction) {\n    return {\n      action: { type: "FILL", instruction },\n      checkpointRequired: false,\n      reason:\n        "Apply one approved visible instruction and verify before continuing",\n    };\n  }\n\n  const unresolvedRequired = observation.unresolvedRequiredControlIds ?? [];\n  if (unresolvedRequired.length > 0) {\n    return {\n      action: {\n        type: "PAUSE_REVIEW",\n        reason:\n          "A required control appeared after the current fill plan was prepared",\n      },\n      checkpointRequired: true,\n      reason:\n        "Re-scan and rebuild the fill plan before continuing through a dependent form",\n    };\n  }\n\n  if (observation.canNavigateNext) {''',
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '''  pendingDraftUsageId: string | null;\n};\n\nexport type AutoPilotControllerStatus = {''',
    '''  pendingDraftUsageId: string | null;\n  lastFillResult: FillResult | null;\n};\n\nexport type AutoPilotControllerStatus = {''',
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '''  pendingDraftUsageId: string | null;\n};\n\nexport type AutoPilotStartInput = {''',
    '''  pendingDraftUsageId: string | null;\n  lastFillResult: FillResult | null;\n};\n\nexport type AutoPilotStartInput = {''',
)
parse_fill_result = '''\nfunction parseRuntimeFillResult(value: unknown): FillResult | null {\n  if (value === null || value === undefined) return null;\n  if (!value || typeof value !== "object" || Array.isArray(value)) {\n    throw new Error("AutoPilot last fill result must be an object");\n  }\n  const candidate = value as Record<string, unknown>;\n  if (!new Set(["FILLED", "SKIPPED", "FAILED"]).has(String(candidate.status))) {\n    throw new Error("AutoPilot last fill status is invalid");\n  }\n  return {\n    controlId: requiredString(candidate.controlId, "lastFillResult.controlId"),\n    status: candidate.status as FillResult["status"],\n    reason: requiredString(candidate.reason, "lastFillResult.reason"),\n    strategy: typeof candidate.strategy === "string" ? candidate.strategy : undefined,\n    verification:\n      typeof candidate.verification === "string" ? candidate.verification : undefined,\n    rebound: typeof candidate.rebound === "boolean" ? candidate.rebound : undefined,\n    stabilized:\n      typeof candidate.stabilized === "boolean" ? candidate.stabilized : undefined,\n    componentFingerprint:\n      typeof candidate.componentFingerprint === "string"\n        ? candidate.componentFingerprint\n        : undefined,\n    recipeId: typeof candidate.recipeId === "string" ? candidate.recipeId : undefined,\n    recipeAttempted:\n      typeof candidate.recipeAttempted === "boolean"\n        ? candidate.recipeAttempted\n        : undefined,\n    recipeSucceeded:\n      typeof candidate.recipeSucceeded === "boolean"\n        ? candidate.recipeSucceeded\n        : undefined,\n  };\n}\n'''
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '''function parseObservation(value: unknown): AutoPilotObservation | null {''',
    parse_fill_result + '''\nfunction parseObservation(value: unknown): AutoPilotObservation | null {''',
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '''    isFinalSubmissionStep: Boolean(candidate.isFinalSubmissionStep),\n  };''',
    '''    isFinalSubmissionStep: Boolean(candidate.isFinalSubmissionStep),\n    unresolvedRequiredControlIds: Array.isArray(\n      candidate.unresolvedRequiredControlIds,\n    )\n      ? candidate.unresolvedRequiredControlIds.map((item) =>\n          requiredString(item, "unresolvedRequiredControlId"),\n        )\n      : [],\n  };''',
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '''    pendingDraftUsageId:\n      candidate.pendingDraftUsageId === undefined\n        ? null\n        : nullableString(candidate.pendingDraftUsageId, "pendingDraftUsageId"),\n  };''',
    '''    pendingDraftUsageId:\n      candidate.pendingDraftUsageId === undefined\n        ? null\n        : nullableString(candidate.pendingDraftUsageId, "pendingDraftUsageId"),\n    lastFillResult: parseRuntimeFillResult(candidate.lastFillResult),\n  };''',
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '''    isFinalSubmissionStep:\n      page.finalSubmissionBoundary || page.applicationState === "SUBMISSION",\n  };''',
    '''    isFinalSubmissionStep:\n      page.finalSubmissionBoundary || page.applicationState === "SUBMISSION",\n    unresolvedRequiredControlIds: page.controls\n      .filter(\n        (control) =>\n          control.visible &&\n          !control.disabled &&\n          control.required &&\n          control.kind !== "BUTTON" &&\n          control.satisfied === false,\n      )\n      .map((control) => control.controlId),\n  };''',
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '''          actionDeadlineAt: this.deadline(FILL_TIMEOUT_MS),\n        });''',
    '''          actionDeadlineAt: this.deadline(FILL_TIMEOUT_MS),\n          lastFillResult:\n            results.find(\n              (result) =>\n                result.controlId === plan.action.instruction.controlId,\n            ) ?? null,\n        });''',
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '''      pendingDraftUsageId: null,\n    });''',
    '''      pendingDraftUsageId: null,\n      lastFillResult: null,\n    });''',
)
replace_once(
    "apps/extension/src/background/autopilot-controller.ts",
    '''      pendingDraftUsageId: runtime.pendingDraftUsageId,\n    };''',
    '''      pendingDraftUsageId: runtime.pendingDraftUsageId,\n      lastFillResult: runtime.lastFillResult,\n    };''',
)

# Launch-plan file verification: selected résumé must match the application-bound digest.
replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    '''export function buildAutoPilotLaunchPlan(\n  page: ApplicationPage,\n  answers: Record<string, AutoPilotAnswer>,\n): AutoPilotLaunchPlan {''',
    '''export function buildAutoPilotLaunchPlan(\n  page: ApplicationPage,\n  answers: Record<string, AutoPilotAnswer>,\n  options: { expectedResumeSha256?: string | null } = {},\n): AutoPilotLaunchPlan {''',
)
replace_once(
    "apps/extension/src/sidepanel/autopilot-plan.ts",
    '''    if (control.kind === "FILE") {\n      if (!control.fileSelected) manual.set(control.controlId, control);\n      continue;\n    }''',
    '''    if (control.kind === "FILE") {\n      const resumeLike = /\\b(resume|résumé|cv)\\b/i.test(\n        `${control.label} ${control.name} ${control.ariaLabel}`,\n      );\n      if (!control.fileSelected) {\n        manual.set(control.controlId, control);\n      } else if (resumeLike && options.expectedResumeSha256) {\n        if (control.fileFingerprintState !== "READY") {\n          manual.set(control.controlId, {\n            ...control,\n            invalid: true,\n            validationMessage:\n              "Selected résumé is still being fingerprinted locally; wait for verification before continuing.",\n          });\n        } else if (control.fileSha256 !== options.expectedResumeSha256) {\n          manual.set(control.controlId, {\n            ...control,\n            invalid: true,\n            validationMessage:\n              "Selected résumé does not match the résumé version bound to this application.",\n          });\n        }\n      }\n      continue;\n    }''',
)
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    '''  const plan = useMemo(\n    () => (page ? buildAutoPilotLaunchPlan(page, answers) : null),\n    [answers, page],\n  );''',
    '''  const plan = useMemo(\n    () =>\n      page\n        ? buildAutoPilotLaunchPlan(page, answers, {\n            expectedResumeSha256: selectedResumeSha256,\n          })\n        : null,\n    [answers, page, selectedResumeSha256],\n  );''',
)
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    '''            {status?.pendingDraftUsageId && (\n              <span className="diagnostic-error">\n                Recording approved AI-answer usage before continuing\n              </span>\n            )}''',
    '''            {status?.pendingDraftUsageId && (\n              <span className="diagnostic-error">\n                Recording approved AI-answer usage before continuing\n              </span>\n            )}\n            {status?.lastFillResult && (\n              <span>\n                Last verified autofill: {status.lastFillResult.strategy ?? "guarded"}\n                {status.lastFillResult.rebound ? " · self-healed binding" : ""}\n                {status.lastFillResult.stabilized === false\n                  ? " · DOM still changing at timeout"\n                  : ""}\n              </span>\n            )}''',
)
replace_once(
    "apps/extension/src/sidepanel/AutoPilotControlCenter.tsx",
    '''                  <span>{control.kind.replaceAll("_", " ")}</span>\n                  {control.kind === "FILE" ? (''',
    '''                  <span>{control.kind.replaceAll("_", " ")}</span>\n                  {control.validationMessage && (\n                    <span className="diagnostic-error">\n                      {control.validationMessage}\n                    </span>\n                  )}\n                  {control.kind === "FILE" ? (''',
)

# Advanced browser tests.
write(
    "apps/extension/src/content/autofill-advanced.test.ts",
    '''// @vitest-environment jsdom\n\nimport { beforeEach, describe, expect, it, vi } from "vitest";\nimport { applyFillInstructions } from "./fill";\nimport { optionEquivalent, repeatMetadataFor } from "./adaptive";\nimport { scanDocument } from "./scanner";\n\nconst visibleRectangle: DOMRect = {\n  bottom: 40,\n  height: 30,\n  left: 10,\n  right: 210,\n  top: 10,\n  width: 200,\n  x: 10,\n  y: 10,\n  toJSON: () => ({}),\n};\n\nconst quick = {\n  optionTimeoutMs: 100,\n  pollIntervalMs: 5,\n  verificationTimeoutMs: 100,\n  stabilityQuietMs: 5,\n  stabilityTimeoutMs: 50,\n};\n\ndescribe("advanced adaptive autofill", () => {\n  beforeEach(() => {\n    document.body.innerHTML = "";\n    document.title = "Application";\n    window.history.replaceState({}, "", "/apply");\n    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(\n      visibleRectangle,\n    );\n  });\n\n  it("maps only deterministic contextual synonyms", () => {\n    expect(optionEquivalent("New Jersey", "NJ", "State / Province")).toBe(true);\n    expect(optionEquivalent("Master of Science", "M.S.", "Degree")).toBe(true);\n    expect(optionEquivalent("United States", "USA", "Country")).toBe(true);\n    expect(optionEquivalent("New Jersey", "New York", "State")).toBe(false);\n    expect(optionEquivalent("Apple", "Application", "Company")).toBe(false);\n  });\n\n  it("uses semantic equivalence for a native select without fuzzy guessing", async () => {\n    document.body.innerHTML = `\n      <label for="state">State</label>\n      <select id="state"><option value="">Choose</option><option value="new-jersey">New Jersey</option></select>\n    `;\n    const question = scanDocument().questions[0]!;\n    const result = await applyFillInstructions(\n      [{\n        controlId: question.controlId, frameId: 0, value: "NJ",\n        sensitive: false, approved: true,\n      }],\n      quick,\n    );\n    expect(result[0]?.status).toBe("FILLED");\n    expect((document.getElementById("state") as HTMLSelectElement).value).toBe("new-jersey");\n  });\n\n  it("handles an ARIA switch only for an explicit boolean answer", async () => {\n    document.body.innerHTML = `<div role="switch" aria-label="Remote preference" aria-checked="false" tabindex="0"></div>`;\n    const control = document.querySelector<HTMLElement>("[role='switch']")!;\n    control.addEventListener("click", () => {\n      control.setAttribute(\n        "aria-checked",\n        control.getAttribute("aria-checked") === "true" ? "false" : "true",\n      );\n    });\n    const question = scanDocument().questions[0]!;\n    const result = await applyFillInstructions(\n      [{\n        controlId: question.controlId, frameId: 0, value: "Yes",\n        sensitive: false, approved: true,\n      }],\n      quick,\n    );\n    expect(result[0]?.status).toBe("FILLED");\n    expect(control.getAttribute("aria-checked")).toBe("true");\n  });\n\n  it("handles a custom ARIA radio group with one semantic exact match", async () => {\n    document.body.innerHTML = `\n      <div role="radiogroup" aria-label="State">\n        <div id="nj" role="radio" aria-checked="false" data-value="New Jersey">New Jersey</div>\n        <div id="ny" role="radio" aria-checked="false" data-value="New York">New York</div>\n      </div>\n    `;\n    const radios = Array.from(document.querySelectorAll<HTMLElement>("[role='radio']"));\n    for (const radio of radios) {\n      radio.addEventListener("click", () => {\n        radios.forEach((item) => item.setAttribute("aria-checked", "false"));\n        radio.setAttribute("aria-checked", "true");\n      });\n    }\n    const question = scanDocument().questions[0]!;\n    const result = await applyFillInstructions(\n      [{\n        controlId: question.controlId, frameId: 0, value: "NJ",\n        sensitive: false, approved: true,\n      }],\n      quick,\n    );\n    expect(result[0]?.status).toBe("FILLED");\n    expect(document.getElementById("nj")?.getAttribute("aria-checked")).toBe("true");\n  });\n\n  it("self-heals a uniquely identifiable control after a React-style re-render", async () => {\n    document.body.innerHTML = `<label for="old-email">Email</label><input id="old-email" type="email">`;\n    const original = scanDocument().questions[0]!;\n    document.body.innerHTML = `<label for="new-email">Email</label><input id="new-email" type="email">`;\n    const result = await applyFillInstructions(\n      [{\n        controlId: original.controlId, frameId: 0, value: "candidate@example.com",\n        sensitive: false, approved: true,\n      }],\n      quick,\n    );\n    expect(result[0]?.status).toBe("FILLED");\n    expect(result[0]?.rebound).toBe(true);\n    expect((document.getElementById("new-email") as HTMLInputElement).value).toBe(\n      "candidate@example.com",\n    );\n  });\n\n  it("refuses to truncate an answer that exceeds the employer limit", async () => {\n    document.body.innerHTML = `<label for="summary">Summary</label><textarea id="summary" maxlength="5"></textarea>`;\n    const question = scanDocument().questions[0]!;\n    const result = await applyFillInstructions(\n      [{\n        controlId: question.controlId, frameId: 0, value: "123456",\n        sensitive: false, approved: true,\n      }],\n      quick,\n    );\n    expect(result[0]?.status).toBe("FAILED");\n    expect((document.getElementById("summary") as HTMLTextAreaElement).value).toBe("");\n    expect(result[0]?.reason).toContain("5-character limit");\n  });\n\n  it("selects an exact canonical date in a custom calendar", async () => {\n    document.body.innerHTML = `\n      <label for="start">Start date</label>\n      <input id="start" aria-haspopup="dialog">\n      <div role="dialog"><button id="day" role="gridcell" data-date="2026-12-17">17</button></div>\n    `;\n    const input = document.getElementById("start") as HTMLInputElement;\n    const day = document.getElementById("day") as HTMLButtonElement;\n    day.addEventListener("click", () => {\n      input.value = "2026-12-17";\n      day.setAttribute("aria-selected", "true");\n    });\n    const question = scanDocument().questions[0]!;\n    const result = await applyFillInstructions(\n      [{\n        controlId: question.controlId, frameId: 0, value: "2026-12-17",\n        sensitive: false, approved: true,\n      }],\n      quick,\n    );\n    expect(result[0]?.status).toBe("FILLED");\n    expect(input.value).toBe("2026-12-17");\n  });\n\n  it("marks repeated indexed controls without auto-creating records", () => {\n    const input = document.createElement("input");\n    input.name = "employment[2].employer";\n    const repeat = repeatMetadataFor(input);\n    expect(repeat.index).toBe(2);\n    expect(repeat.groupId).toContain("[#]");\n  });\n});\n''',
)
write(
    "packages/application-model/src/autopilot-dependent.test.ts",
    '''import { describe, expect, it } from "vitest";\nimport { planAutoPilotStep } from "./autopilot";\n\ndescribe("dependent AutoPilot forms", () => {\n  it("pauses instead of navigating when a new required control appears", () => {\n    const plan = planAutoPilotStep({\n      observation: {\n        applicationId: "app-1",\n        state: "QUESTIONS",\n        pageId: "page-1",\n        pageFingerprint: "fp-2",\n        visibleControlIds: ["new-required"],\n        validationErrorCount: 0,\n        securityCheckpoint: null,\n        canNavigateNext: true,\n        isFinalSubmissionStep: false,\n        unresolvedRequiredControlIds: ["new-required"],\n      },\n      preflight: {\n        state: "READY",\n        readyCount: 0,\n        reviewCount: 0,\n        unresolvedCount: 0,\n        blockedCount: 0,\n        canAct: true,\n      },\n      fillInstructions: [],\n    });\n    expect(plan.action.type).toBe("PAUSE_REVIEW");\n    expect(plan.reason).toContain("Re-scan");\n  });\n});\n''',
)

print("Autofill core hardening applied.")
