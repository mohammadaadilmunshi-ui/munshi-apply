from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match in {path}, found {count}")
    file.write_text(text.replace(old, new, 1))


def insert_before(path: str, marker: str, addition: str, label: str) -> None:
    file = Path(path)
    text = file.read_text()
    pos = text.find(marker)
    if pos < 0:
        raise SystemExit(f"{label}: marker missing in {path}")
    file.write_text(text[:pos] + addition + text[pos:])


replace_once(
    "packages/contracts/src/index.ts",
    '  title: z.string(),\n  observedAt: z.string().datetime(),',
    '  title: z.string(),\n  pageContext: z.string().max(20_000).optional(),\n  observedAt: z.string().datetime(),',
    "application page context contract",
)

replace_once(
    "packages/semantic-engine/src/index.ts",
    '''  {\n    id: "graduation",\n    pattern: /\\b(graduation|graduate|completion) (date|year)\\b/i,\n    semanticType: "GRADUATION_DATE",\n  },''',
    '''  {\n    id: "graduation",\n    pattern:\n      /(?:\\b(?:graduation|completion)\\s+(?:date|year)\\b|\\b(?:when|what)\\b.{0,60}\\bgraduat(?:e|ing|ed)\\b|\\bgraduat(?:e|ing|ed)\\b.{0,45}\\b(?:university|college|school)\\b)/i,\n    semanticType: "GRADUATION_DATE",\n  },''',
    "graduation semantic expansion",
)
replace_once(
    "packages/semantic-engine/src/index.ts",
    '''  {\n    id: "career-motivation",\n    pattern:\n      /\\bwhat motivates you\\b.{0,100}\\b(?:career|recruitment|recruiting|sales|talent acquisition)\\b/i,\n    semanticType: "CAREER_GOALS",\n  },''',
    '''  {\n    id: "career-motivation",\n    pattern:\n      /\\bwhat motivates you\\b.{0,100}\\b(?:career|recruitment|recruiting|sales|talent acquisition)\\b/i,\n    semanticType: "CAREER_GOALS",\n  },\n  {\n    id: "leave-current-employer",\n    pattern:\n      /\\b(?:why are you|why do you|what makes you)\\b.{0,70}\\b(?:leave|leaving|looking to leave|move on from|change from)\\b.{0,60}\\b(?:current )?(?:employer|company|role|job|position)\\b/i,\n    semanticType: "CAREER_GOALS",\n  },''',
    "career transition semantic",
)

scanner = Path("apps/extension/src/content/scanner.ts")
text = scanner.read_text()
label_marker = "function labelFor(element: Element): string {\n"
helpers = '''function placeholderChoiceText(value: string): boolean {\n  const text = normalized(value).replace(/[–—-]+/g, " ").trim();\n  return /^(select|choose)( one| an option| option)?$/.test(text) || text === "please select";\n}\n\nfunction usablePromptText(value: string): string {\n  const text = compactText(value);\n  if (!text || placeholderChoiceText(text)) return "";\n  if (/^(yes|no|true|false)$/i.test(text)) return "";\n  return text.length <= 500 ? text : "";\n}\n\nfunction nearbyPromptText(element: Element): string {\n  if (element.id) {\n    const root = element.getRootNode();\n    const labels =\n      root instanceof Document || root instanceof ShadowRoot\n        ? Array.from(root.querySelectorAll(`label[for="${CSS.escape(element.id)}"]`))\n        : [];\n    const direct = labels\n      .map((item) => usablePromptText(item.textContent ?? ""))\n      .find(Boolean);\n    if (direct) return direct;\n  }\n\n  const group = element.closest("fieldset, [role='radiogroup'], [role='group']");\n  if (group) {\n    const legend = usablePromptText(group.querySelector("legend")?.textContent ?? "");\n    if (legend) return legend;\n    const aria = usablePromptText(group.getAttribute("aria-label") ?? "");\n    if (aria) return aria;\n    const labelled = usablePromptText(labelledByText(group));\n    if (labelled) return labelled;\n  }\n\n  let current: Element | null = element.parentElement;\n  for (let depth = 0; current && depth < 6; depth += 1, current = current.parentElement) {\n    const candidates = Array.from(\n      current.querySelectorAll(\n        ":scope > label, :scope > legend, :scope > p, :scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > [class*='label' i], :scope > [class*='question' i]",\n      ),\n    );\n    for (const candidate of candidates) {\n      if (candidate === element || candidate.contains(element)) continue;\n      const value = usablePromptText(candidate.textContent ?? "");\n      if (value) return value;\n    }\n    let previous: Element | null =\n      current === element.parentElement\n        ? element.previousElementSibling\n        : current.previousElementSibling;\n    for (let hops = 0; previous && hops < 3; hops += 1, previous = previous.previousElementSibling) {\n      const value = usablePromptText(previous.textContent ?? "");\n      if (value) return value;\n    }\n  }\n  return "";\n}\n\n'''
if text.count(label_marker) != 1:
    raise SystemExit("scanner label marker missing")
text = text.replace(label_marker, helpers + label_marker, 1)
old_label = '''function labelFor(element: Element): string {\n  const ariaLabel = compactText(element.getAttribute("aria-label"));\n  if (ariaLabel) return ariaLabel;\n\n  const labelled = labelledByText(element);\n  if (labelled) return labelled;\n\n  if (element instanceof HTMLInputElement) {\n    if (element.type === "radio") {\n      const legend = groupLegend(element);\n      if (legend) return legend;\n    }\n    const labels = inputLabel(element);\n    if (labels) return labels;\n    if (["button", "submit", "reset"].includes(element.type)) {\n      return compactText(element.value);\n    }\n  }\n\n  if (\n    element instanceof HTMLSelectElement ||\n    element instanceof HTMLTextAreaElement\n  ) {\n    const labels = Array.from(element.labels)\n      .map((label) => compactText(label.textContent))\n      .filter(Boolean)\n      .join(" ");\n    if (labels) return labels;\n  }\n\n  if (\n    element instanceof HTMLButtonElement ||\n    element.getAttribute("role") === "button"\n  ) {\n    const text = compactText(element.textContent);\n    if (text) return text;\n  }\n\n  const container = element.closest("fieldset, [role='group'], .form-group");\n  return compactText(container?.querySelector("legend")?.textContent);\n}\n'''
new_label = '''function labelFor(element: Element): string {\n  const ariaLabel = usablePromptText(element.getAttribute("aria-label") ?? "");\n  if (ariaLabel) return ariaLabel;\n\n  const labelled = usablePromptText(labelledByText(element));\n  if (labelled) return labelled;\n\n  if (element instanceof HTMLInputElement) {\n    if (element.type === "radio") {\n      const legend = usablePromptText(groupLegend(element));\n      if (legend) return legend;\n      const prompt = nearbyPromptText(element);\n      if (prompt) return prompt;\n    }\n    const labels = usablePromptText(inputLabel(element));\n    if (labels) return labels;\n    const prompt = nearbyPromptText(element);\n    if (prompt) return prompt;\n    if (["button", "submit", "reset"].includes(element.type)) {\n      return compactText(element.value);\n    }\n  }\n\n  if (\n    element instanceof HTMLSelectElement ||\n    element instanceof HTMLTextAreaElement\n  ) {\n    const labels = Array.from(element.labels)\n      .map((label) => usablePromptText(label.textContent ?? ""))\n      .filter(Boolean)\n      .join(" ");\n    if (labels) return labels;\n    const prompt = nearbyPromptText(element);\n    if (prompt) return prompt;\n  }\n\n  if (isPopupChoiceControl(element) || isCustomDateControl(element)) {\n    const prompt = nearbyPromptText(element);\n    if (prompt) return prompt;\n  }\n\n  if (\n    element instanceof HTMLButtonElement ||\n    element.getAttribute("role") === "button"\n  ) {\n    const value = usablePromptText(element.textContent ?? "");\n    if (value) return value;\n  }\n\n  return nearbyPromptText(element);\n}\n'''
if text.count(old_label) != 1:
    raise SystemExit("scanner original labelFor body missing")
text = text.replace(old_label, new_label, 1)
page_marker = '    title: document.title,\n    observedAt: new Date().toISOString(),'
if text.count(page_marker) != 1:
    raise SystemExit("scanner page context marker missing")
text = text.replace(
    page_marker,
    '    title: document.title,\n    pageContext: compactText(document.body?.textContent).slice(0, 20_000),\n    observedAt: new Date().toISOString(),',
    1,
)
scanner.write_text(text)

adaptive = Path("apps/extension/src/content/adaptive.ts")
text = adaptive.read_text()
replace_target = '    hostname.includes("icims");'
if text.count(replace_target) != 1:
    raise SystemExit("adaptive dynamic ATS marker missing")
text = text.replace(
    replace_target,
    '    hostname.includes("icims") ||\n    hostname.includes("levintalent");',
    1,
)
old_date_marker = '''  return canonicalDate(date);\n}\n\nfunction dateForCandidate(element: Element): string | null {'''
new_date_helpers = '''  return canonicalDate(date);\n}\n\nfunction flexibleDate(value: string): string | null {\n  const direct = canonicalDate(value.trim());\n  if (direct) return direct;\n  const text = compactText(value);\n  const us = text.match(/^(\\d{1,2})[\\/-](\\d{1,2})[\\/-](\\d{4})$/);\n  if (us) {\n    const date = `${us[3]}-${String(Number(us[1])).padStart(2, "0")}-${String(Number(us[2])).padStart(2, "0")}`;\n    const parsed = canonicalDate(date);\n    if (parsed) return parsed;\n  }\n  return naturalDate(text);\n}\n\nfunction setNativeTextValue(element: HTMLInputElement, value: string): void {\n  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;\n  if (setter) setter.call(element, value);\n  else element.value = value;\n}\n\nfunction dateDisplayCandidates(element: HTMLInputElement, canonical: string): string[] {\n  const [year, month, day] = canonical.split("-");\n  const placeholder = normalizedText(element.placeholder);\n  const us = `${month}/${day}/${year}`;\n  const eu = `${day}/${month}/${year}`;\n  const order = /dd.{0,3}mm.{0,3}yyyy/.test(placeholder)\n    ? [eu, canonical, us]\n    : [us, canonical, eu];\n  return [...new Set(order)];\n}\n\nfunction dateTextRejected(element: HTMLInputElement): boolean {\n  if (element.getAttribute("aria-invalid") === "true" || !element.validity.valid) return true;\n  const message = normalizedText(validationMessageFor(element));\n  return /\\b(not valid date|invalid date|valid date|date format)\\b/.test(message);\n}\n\nexport async function fillDateLikeTextInput(\n  element: HTMLInputElement,\n  value: string,\n  timing: AdaptiveTiming,\n): Promise<boolean | null> {\n  if (element.type !== "text" && element.type !== "search") return null;\n  const requested = canonicalDate(value);\n  if (!requested) return null;\n  if (!/\\b(date|day|month|year|graduat|available|start|end)\\b/.test(normalizedText(interactionContext(element)))) {\n    return null;\n  }\n  const original = element.value;\n  for (const candidate of dateDisplayCandidates(element, requested)) {\n    element.focus();\n    setNativeTextValue(element, candidate);\n    element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));\n    element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));\n    element.dispatchEvent(new Event("blur", { bubbles: true, composed: true }));\n    const verified = await waitForCondition(\n      () => flexibleDate(element.value) === requested && !dateTextRejected(element),\n      timing.verificationTimeoutMs,\n      timing.pollIntervalMs,\n    );\n    if (verified) return true;\n  }\n  setNativeTextValue(element, original);\n  element.dispatchEvent(new Event("input", { bubbles: true, composed: true }));\n  element.dispatchEvent(new Event("change", { bubbles: true, composed: true }));\n  return false;\n}\n\nfunction dateForCandidate(element: Element): string | null {'''
if text.count(old_date_marker) != 1:
    raise SystemExit("adaptive date helper marker missing")
text = text.replace(old_date_marker, new_date_helpers, 1)
old_custom = '''  const originalValue =\n    element instanceof HTMLInputElement ? element.value : null;\n  element.focus();\n  element.click();'''
new_custom = '''  const originalValue =\n    element instanceof HTMLInputElement ? element.value : null;\n  if (element instanceof HTMLInputElement) {\n    const direct = await fillDateLikeTextInput(element, requested, timing);\n    if (direct === true) return true;\n  }\n  element.focus();\n  element.click();'''
if text.count(old_custom) != 1:
    raise SystemExit("adaptive custom date marker missing")
text = text.replace(old_custom, new_custom, 1)
replace_verify = '        if (naturalDate(element.value) === requested) return true;'
if text.count(replace_verify) != 1:
    raise SystemExit("adaptive date verification marker missing")
text = text.replace(replace_verify, '        if (flexibleDate(element.value) === requested) return true;', 1)
adaptive.write_text(text)

fill = Path("apps/extension/src/content/fill.ts")
text = fill.read_text()
replace_target = '  fillCustomDateControl,\n  interactionContext,'
if text.count(replace_target) != 1:
    raise SystemExit("fill adaptive import marker missing")
text = text.replace(
    replace_target,
    '  fillCustomDateControl,\n  fillDateLikeTextInput,\n  interactionContext,',
    1,
)
old_radio = '''  const match = candidates[0]!;\n  match.focus();\n  setNativeChecked(match, true);\n  dispatchValueEvents(match);\n  return match.checked;'''
new_radio = '''  const match = candidates[0]!;\n  match.focus();\n  match.click();\n  if (!match.checked) {\n    setNativeChecked(match, true);\n    dispatchValueEvents(match);\n  }\n  return match.checked;'''
if text.count(old_radio) != 1:
    raise SystemExit("fill radio marker missing")
text = text.replace(old_radio, new_radio, 1)
old_checkbox = '''  const shouldCheck = truthy.includes(requested);\n  element.focus();\n  setNativeChecked(element, shouldCheck);\n  dispatchValueEvents(element);\n  return element.checked === shouldCheck;'''
new_checkbox = '''  const shouldCheck = truthy.includes(requested);\n  element.focus();\n  if (element.checked !== shouldCheck) element.click();\n  if (element.checked !== shouldCheck) {\n    setNativeChecked(element, shouldCheck);\n    dispatchValueEvents(element);\n  }\n  return element.checked === shouldCheck;'''
if text.count(old_checkbox) != 1:
    raise SystemExit("fill checkbox marker missing")
text = text.replace(old_checkbox, new_checkbox, 1)
old_portal = '''    for (const option of Array.from(root.querySelectorAll("[role='option']"))) {'''
new_portal = '''    for (const option of Array.from(\n      root.querySelectorAll(\n        "[role='option'], [role='menuitem'], [data-value], [data-option-value], li",\n      ),\n    )) {'''
if text.count(old_portal) != 1:
    raise SystemExit("fill portal option marker missing")
text = text.replace(old_portal, new_portal, 1)
old_temporal = '''    const strictTemporal = fillStrictTemporalInput(element, value);\n    if (strictTemporal !== null) return strictTemporal;'''
new_temporal = '''    const dateLikeText = await fillDateLikeTextInput(element, value, options);\n    if (dateLikeText !== null) return dateLikeText;\n    const strictTemporal = fillStrictTemporalInput(element, value);\n    if (strictTemporal !== null) return strictTemporal;'''
if text.count(old_temporal) != 1:
    raise SystemExit("fill temporal marker missing")
text = text.replace(old_temporal, new_temporal, 1)
fill.write_text(text)

resolver = Path("packages/application-model/src/resolver.ts")
text = resolver.read_text()
resolver_marker = 'function startAvailabilityDateFromQuestion(rawText: string): number | null {\n'
resolver_helpers = '''function ownerDefaultReferral(question: Question): AnswerResolution | null {\n  if (question.semanticType !== "REFERRAL") return null;\n  return {\n    state: "READY",\n    value: "LinkedIn",\n    sourceFactId: null,\n    sourceKey: "owner_default_referral",\n    trustLevel: "USER_CONFIRMED",\n    sensitive: false,\n    protected: false,\n    confidence: Math.max(question.confidence, 0.99),\n    reasons: ["Owner default referral source is LinkedIn"],\n  };\n}\n\nfunction salaryBoolean(value: string): "Yes" | "No" | null {\n  const token = value.trim().toLocaleLowerCase("en-US");\n  if (/^(yes|true|accept|acceptable|accepted|ok|okay|willing|agree)$/.test(token)) return "Yes";\n  if (/^(no|false|decline|unacceptable|not acceptable|not willing|disagree)$/.test(token)) return "No";\n  return null;\n}\n\nfunction moneyValues(value: string): number[] {\n  const values: number[] = [];\n  for (const match of value.matchAll(/\\$?\\s*(\\d{2,3}(?:,\\d{3})+|\\d{2,3}(?:\\.\\d+)?)\\s*([kK])?/g)) {\n    const numeric = Number(match[1]!.replaceAll(",", ""));\n    if (!Number.isFinite(numeric)) continue;\n    const expanded = match[2] ? numeric * 1_000 : numeric;\n    if (expanded >= 10_000) values.push(expanded);\n  }\n  return values;\n}\n\nfunction resolveSalaryAcceptance(\n  question: Question,\n  profile: MasterProfile | ProfileSnapshot,\n): AnswerResolution | null {\n  if (question.semanticType !== "SALARY_EXPECTATION") return null;\n  if (!/\\b(accept|happy|comfortable|agree|willing)\\b/i.test(question.rawText)) return null;\n  const fact = profile.facts.find((candidate) => candidate.key === "salary_expectation");\n  if (!fact || !factIsExplicitlyUsable(fact)) return null;\n  const raw = stringifyFactValue(fact.value).trim();\n  const direct = salaryBoolean(raw);\n  if (direct) {\n    return {\n      state: "READY",\n      value: direct,\n      sourceFactId: fact.factId,\n      sourceKey: fact.key,\n      trustLevel: fact.trustLevel,\n      sensitive: true,\n      protected: fact.protected,\n      confidence: Math.min(question.confidence, 0.96),\n      reasons: ["Exact owner-confirmed salary acceptance preference"],\n    };\n  }\n  const offered = moneyValues(question.rawText)[0];\n  const expected = moneyValues(raw)[0];\n  if (offered && expected && offered >= expected) {\n    return {\n      state: "READY",\n      value: "Yes",\n      sourceFactId: fact.factId,\n      sourceKey: fact.key,\n      trustLevel: fact.trustLevel,\n      sensitive: true,\n      protected: fact.protected,\n      confidence: Math.min(question.confidence, 0.94),\n      reasons: ["Advertised base salary meets the owner-confirmed minimum salary preference"],\n    };\n  }\n  return null;\n}\n\n'''
if text.count(resolver_marker) != 1:
    raise SystemExit("resolver helper marker missing")
text = text.replace(resolver_marker, resolver_helpers + resolver_marker, 1)
old_resolve = '''export function resolveProfileAnswer(\n  question: Question,\n  profile: MasterProfile | ProfileSnapshot,\n): AnswerResolution {\n  const availabilityResolution = resolveBooleanAvailabilityDate('''
new_resolve = '''export function resolveProfileAnswer(\n  question: Question,\n  profile: MasterProfile | ProfileSnapshot,\n): AnswerResolution {\n  const referralResolution = ownerDefaultReferral(question);\n  if (referralResolution) return referralResolution;\n\n  const salaryResolution = resolveSalaryAcceptance(question, profile);\n  if (salaryResolution) return salaryResolution;\n\n  const availabilityResolution = resolveBooleanAvailabilityDate('''
if text.count(old_resolve) != 1:
    raise SystemExit("resolver entry marker missing")
resolver.write_text(text.replace(old_resolve, new_resolve, 1))

app = Path("apps/extension/src/sidepanel/App.tsx")
text = app.read_text()
replace_target = '  getProfileSyncStatus,\n  nativeRuntimeCompatibility,'
if text.count(replace_target) != 1:
    raise SystemExit("App client import marker missing")
text = text.replace(
    replace_target,
    '  getProfileSyncStatus,\n  nativeRuntimeCompatibility,\n  requestFilePickerAssist,',
    1,
)
old_answer_type = '''type AnswerDraft = {\n  value: string;\n  approved: boolean;\n  sensitive: boolean;\n  sourceDraftId?: string | null;\n};'''
new_answer_type = '''type AnswerDraft = {\n  value: string;\n  approved: boolean;\n  sensitive: boolean;\n  sourceDraftId?: string | null;\n  ownerEdited?: boolean;\n};'''
if text.count(old_answer_type) != 1:
    raise SystemExit("App AnswerDraft marker missing")
text = text.replace(old_answer_type, new_answer_type, 1)
old_set = '''    setAnswers(next);\n    setSelectedResumeId((current) => {'''
new_set = '''    setAnswers((current) =>\n      Object.fromEntries(\n        page.questions.map((question) => [\n          question.questionId,\n          current[question.questionId]?.ownerEdited\n            ? current[question.questionId]!\n            : next[question.questionId]!,\n        ]),\n      ),\n    );\n    setSelectedResumeId((current) => {'''
if text.count(old_set) != 1:
    raise SystemExit("App answer reset marker missing")
text = text.replace(old_set, new_set, 1)
old_manual_change = '''                              approved: false,\n                              sourceDraftId: null,\n                            },'''
new_manual_change = '''                              approved: false,\n                              sourceDraftId: null,\n                              ownerEdited: true,\n                            },'''
if text.count(old_manual_change) != 1:
    raise SystemExit("App manual answer change marker missing")
text = text.replace(old_manual_change, new_manual_change, 1)
old_approval = '''                                ...answer,\n                                approved: event.target.checked,\n                              },'''
new_approval = '''                                ...answer,\n                                approved: event.target.checked,\n                                ownerEdited: true,\n                              },'''
if text.count(old_approval) != 1:
    raise SystemExit("App approval change marker missing")
text = text.replace(old_approval, new_approval, 1)
old_ai_prop = '''                        nativeAvailable={native.status === "healthy"}\n                        onApproved='''
new_ai_prop = '''                        nativeAvailable={native.status === "healthy"}\n                        pageContext={page.pageContext ?? ""}\n                        onApproved='''
if text.count(old_ai_prop) != 1:
    raise SystemExit("App AI property marker missing")
text = text.replace(old_ai_prop, new_ai_prop, 1)
old_ai_answer = '''                              sensitive: question.sensitive,\n                              sourceDraftId: draftId,\n                            },'''
new_ai_answer = '''                              sensitive: question.sensitive,\n                              sourceDraftId: draftId,\n                              ownerEdited: true,\n                            },'''
if text.count(old_ai_answer) != 1:
    raise SystemExit("App AI answer marker missing")
text = text.replace(old_ai_answer, new_ai_answer, 1)
selected_marker = '''  const selectedResume = useMemo(\n    () =>\n      cloudSnapshot?.resumes.find(\n        (resume) => resume.resumeId === selectedResumeId,\n      ) ?? null,\n    [cloudSnapshot, selectedResumeId],\n  );'''
selected_new = selected_marker + '''\n  const employerFileControl = useMemo(\n    () =>\n      page?.controls.find(\n        (control) =>\n          control.kind === "FILE" &&\n          /\\b(resume|résumé|cv)\\b/i.test(`${control.label} ${control.name}`),\n      ) ?? page?.controls.find((control) => control.kind === "FILE") ?? null,\n    [page],\n  );'''
if text.count(selected_marker) != 1:
    raise SystemExit("App selected resume marker missing")
text = text.replace(selected_marker, selected_new, 1)
old_resume_ui = '''                  <small>\n                    Browser security requires you to choose the file in the\n                    employer’s upload control manually.\n                  </small>\n                </label>'''
new_resume_ui = '''                  <small>\n                    Browser security requires you to choose the file in the\n                    employer’s upload control manually.\n                  </small>\n                  {employerFileControl && (\n                    <button\n                      className="quiet"\n                      type="button"\n                      onClick={() =>\n                        void requestFilePickerAssist(\n                          employerFileControl.frameId,\n                          employerFileControl.controlId,\n                        )\n                          .then(() =>\n                            setNotice(\n                              "Employer file handoff opened. Choose the matching résumé file; MUNSHI will verify it after selection.",\n                            ),\n                          )\n                          .catch((error: unknown) =>\n                            setNotice(\n                              error instanceof Error\n                                ? error.message\n                                : "Unable to open employer file handoff",\n                            ),\n                          )\n                      }\n                    >\n                      Open employer file picker\n                    </button>\n                  )}\n                </label>'''
if text.count(old_resume_ui) != 1:
    raise SystemExit("App resume UI marker missing")
text = text.replace(old_resume_ui, new_resume_ui, 1)
app.write_text(text)

replace_once(
    "apps/extension/src/messaging/native.ts",
    '  semanticType: string;\n  correlationId: string;',
    '  semanticType: string;\n  pageContext?: string;\n  correlationId: string;',
    "AI request page context type",
)

review = Path("apps/extension/src/sidepanel/AIDraftReview.tsx")
text = review.read_text()
replace_target = '''  nativeAvailable,\n  onApproved,'''
if text.count(replace_target) != 1:
    raise SystemExit("AIDraftReview destructure marker missing")
text = text.replace(replace_target, '''  nativeAvailable,\n  pageContext,\n  onApproved,''', 1)
replace_target = '''  nativeAvailable: boolean;\n  onApproved: (value: string, draftId: string) => void;'''
if text.count(replace_target) != 1:
    raise SystemExit("AIDraftReview prop type marker missing")
text = text.replace(replace_target, '''  nativeAvailable: boolean;\n  pageContext: string;\n  onApproved: (value: string, draftId: string) => void;''', 1)
replace_target = '''      semanticType: question.semanticType,\n      correlationId: `draft-${question.questionId}`,'''
if text.count(replace_target) != 1:
    raise SystemExit("AIDraftReview request marker missing")
text = text.replace(replace_target, '''      semanticType: question.semanticType,\n      pageContext,\n      correlationId: `draft-${question.questionId}`,''', 1)
replace_target = '''      applicationId,\n      pageId,\n      question.controlId,'''
if text.count(replace_target) != 1:
    raise SystemExit("AIDraftReview dependency marker missing")
text = text.replace(replace_target, '''      applicationId,\n      pageContext,\n      pageId,\n      question.controlId,''', 1)
review.write_text(text)

governance = Path("apps/native-host/src/munshi_apply_native/ai_governance.py")
text = governance.read_text()
if text.count("import re\nimport uuid") != 1:
    raise SystemExit("AI governance import marker missing")
text = text.replace("import re\nimport uuid", "import hashlib\nimport re\nimport uuid", 1)
if text.count("from .providers import (\n") != 1:
    raise SystemExit("AI governance provider import marker missing")
text = text.replace("from .providers import (\n", "from .profile_store import ProfileStore\nfrom .providers import (\n", 1)
validate_marker = '        max_output_tokens = payload.get("maxOutputTokens", 512)'
validate_new = '''        page_context = payload.get("pageContext", "")\n        if page_context is not None and not isinstance(page_context, str):\n            raise ValueError("AI draft pageContext must be a string")\n        page_context = (page_context or "").strip()\n        if len(page_context) > 20_000:\n            raise ValueError("AI draft pageContext exceeds 20,000 characters")\n        max_output_tokens = payload.get("maxOutputTokens", 512)'''
if text.count(validate_marker) != 1:
    raise SystemExit("AI governance validation marker missing")
text = text.replace(validate_marker, validate_new, 1)
return_marker = '''            "semanticType": semantic_type.strip(),\n            "correlationId": correlation_id.strip(),'''
if text.count(return_marker) != 1:
    raise SystemExit("AI governance return request marker missing")
text = text.replace(return_marker, '''            "semanticType": semantic_type.strip(),\n            "pageContext": page_context,\n            "correlationId": correlation_id.strip(),''', 1)
context_signature = '''        semantic_type: str,\n        config: AIConfiguration,\n    ) -> tuple[tuple[ProviderContextItem, ...], set[str], dict[str, object]]:'''
if text.count(context_signature) != 1:
    raise SystemExit("AI governance context signature marker missing")
text = text.replace(context_signature, '''        semantic_type: str,\n        page_context: str,\n        config: AIConfiguration,\n    ) -> tuple[tuple[ProviderContextItem, ...], set[str], dict[str, object]]:''', 1)
candidates_marker = '''        candidates: list[tuple[float, dict[str, object]]] = []\n        blocked_protected = 0'''
runtime_candidates = '''        candidates: list[tuple[float, dict[str, object]]] = []\n        if page_context:\n            page_evidence_id = "job-context-" + hashlib.sha256(page_context.encode("utf-8")).hexdigest()[:20]\n            candidates.append(\n                (\n                    1.0,\n                    {\n                        "evidence_id": page_evidence_id,\n                        "kind": "JOB_REQUIREMENT",\n                        "text": page_context,\n                        "semantic_types": [semantic_type],\n                        "trust_level": "DOCUMENT_CONFIRMED",\n                        "protected": False,\n                        "source": "current-employer-page",\n                        "updated_at": self._now().isoformat(),\n                    },\n                )\n            )\n\n        profile = ProfileStore(self.database).latest()\n        if profile:\n            if config.allow_profile_evidence:\n                for fact in profile.get("facts", []):\n                    if fact.get("protected") or fact.get("trustLevel") not in _AUTHORITATIVE_TRUST:\n                        continue\n                    value = str(fact.get("value", "")).strip()\n                    if not value:\n                        continue\n                    candidates.append(\n                        (\n                            0.58,\n                            {\n                                "evidence_id": "profile-" + str(fact.get("factId", "unknown")),\n                                "kind": "PROFILE_FACT",\n                                "text": f"{fact.get('key', 'profile fact')}: {value}",\n                                "semantic_types": [],\n                                "trust_level": fact.get("trustLevel"),\n                                "protected": False,\n                                "source": "confirmed-profile",\n                                "updated_at": fact.get("updatedAt", self._now().isoformat()),\n                            },\n                        )\n                    )\n            for record in profile.get("records", []):\n                if record.get("kind") not in {"EMPLOYMENT", "PROJECT", "EDUCATION", "CERTIFICATION"}:\n                    continue\n                for fact in record.get("facts", []):\n                    if fact.get("protected") or fact.get("trustLevel") not in _AUTHORITATIVE_TRUST:\n                        continue\n                    key = str(fact.get("key", ""))\n                    if not config.allow_profile_evidence and not (\n                        config.allow_resume_evidence\n                        and key in {"responsibilities", "achievements", "project_summary", "project_technologies", "gpa"}\n                    ):\n                        continue\n                    value = str(fact.get("value", "")).strip()\n                    if not value:\n                        continue\n                    kind = (\n                        "RESUME_BULLET"\n                        if key in {"responsibilities", "achievements", "project_summary", "project_technologies"}\n                        else str(record.get("kind"))\n                    )\n                    candidates.append(\n                        (\n                            0.72 if kind == "RESUME_BULLET" else 0.62,\n                            {\n                                "evidence_id": "record-" + str(fact.get("factId", "unknown")),\n                                "kind": kind,\n                                "text": f"{record.get('label', record.get('kind', 'record'))}: {value}",\n                                "semantic_types": [],\n                                "trust_level": fact.get("trustLevel"),\n                                "protected": False,\n                                "source": "confirmed-profile-record",\n                                "updated_at": fact.get("updatedAt", self._now().isoformat()),\n                            },\n                        )\n                    )\n\n        blocked_protected = 0'''
if text.count(candidates_marker) != 1:
    raise SystemExit("AI governance candidates marker missing")
text = text.replace(candidates_marker, runtime_candidates, 1)
context_call = '''            semantic_type=semantic_type,\n            config=config,\n        )'''
if text.count(context_call) != 1:
    raise SystemExit("AI governance context call marker missing")
text = text.replace(context_call, '''            semantic_type=semantic_type,\n            page_context=str(request.get("pageContext", "")),\n            config=config,\n        )''', 1)
governance.write_text(text)

replace_once(
    "apps/native-host/src/munshi_apply_native/providers.py",
    '''                "You draft one job-application answer using only the supplied evidence. "\n                "Do not add facts, metrics, employers, dates, credentials, immigration facts, "\n                "or claims that are not supported by the supplied evidence. Every factual claim "\n                "must cite one or more supplied evidenceId values in the structured claims array."''',
    '''                "Draft one direct, natural, professional job-application answer to the supplied question. "\n                "Use the current job/company context together with the candidate evidence when relevant. "\n                "Do not invent facts, metrics, employers, dates, credentials, immigration facts, motives, or claims. "\n                "For career-transition questions, stay constructive and future-focused; do not criticize an employer unless evidence explicitly requires it. "\n                "Avoid generic filler and do not mention the evidence system. Every factual claim must cite one or more supplied evidenceId values in the structured claims array."''',
    "provider job-context instructions",
)

semantic_test = Path("packages/semantic-engine/src/index.test.ts")
text = semantic_test.read_text()
insert_point = '  it("leaves novel questions unknown instead of inventing a meaning", () => {'
addition = '''  it("recognizes live graduation and career-transition prompts", () => {\n    expect(\n      classifyQuestion("When did you / when do you Graduate from University? *"),\n    ).toMatchObject({ semanticType: "GRADUATION_DATE", matchedRule: "graduation" });\n    expect(\n      classifyQuestion("Why are you looking to leave your current employer? *"),\n    ).toMatchObject({ semanticType: "CAREER_GOALS", matchedRule: "leave-current-employer" });\n  });\n\n'''
if text.count(insert_point) != 1:
    raise SystemExit("semantic regression insertion marker missing")
semantic_test.write_text(text.replace(insert_point, addition + insert_point, 1))

resolver_test = Path("packages/application-model/src/resolver.test.ts")
text = resolver_test.read_text()
insert_point = '  it("does not promote generated facts to ready answers", () => {'
addition = '''  it("uses LinkedIn as the owner default referral source", () => {\n    const result = resolveProfileAnswer(\n      question({ semanticType: "REFERRAL", rawText: "How did you hear about us? *" }),\n      profile([]),\n    );\n    expect(result).toMatchObject({\n      state: "READY",\n      value: "LinkedIn",\n      sourceKey: "owner_default_referral",\n    });\n  });\n\n  it("fills an explicitly saved salary acceptance answer", () => {\n    const result = resolveProfileAnswer(\n      question({\n        semanticType: "SALARY_EXPECTATION",\n        rawText: "Are you happy to accept an annual base salary of $55,000 + commission? *",\n        sensitive: true,\n        requiresReview: true,\n      }),\n      profile([\n        fact({\n          key: "salary_expectation",\n          value: "Yes",\n          category: "SAVED_ANSWER",\n          protected: false,\n        }),\n      ]),\n    );\n    expect(result).toMatchObject({\n      state: "READY",\n      value: "Yes",\n      sourceKey: "salary_expectation",\n    });\n  });\n\n'''
if text.count(insert_point) != 1:
    raise SystemExit("resolver regression insertion marker missing")
resolver_test.write_text(text.replace(insert_point, addition + insert_point, 1))

scanner_test = Path("apps/extension/src/content/scanner.test.ts")
text = scanner_test.read_text()
insert_point = '  it("does not treat an application-entry Apply Now control as final submission", () => {'
addition = '''  it("recovers a nearby prompt for a custom select instead of its placeholder", () => {\n    document.body.innerHTML = `\n      <div class="question-field">\n        <label>How did you hear about us? *</label>\n        <div id="source" role="combobox" aria-haspopup="listbox" aria-label="-- Select one --"></div>\n      </div>\n    `;\n    const question = scanDocument().questions[0];\n    expect(question).toMatchObject({\n      rawText: "How did you hear about us? *",\n      semanticType: "REFERRAL",\n    });\n  });\n\n  it("uses the radio-group prompt instead of Yes or No option labels", () => {\n    document.body.innerHTML = `\n      <div class="question-field">\n        <p>Would you require any Visa sponsorship now or in the future? *</p>\n        <label><input type="radio" name="sponsor" value="Yes"> Yes</label>\n        <label><input type="radio" name="sponsor" value="No"> No</label>\n      </div>\n    `;\n    const result = scanDocument();\n    expect(result.questions).toHaveLength(1);\n    expect(result.questions[0]).toMatchObject({\n      rawText: "Would you require any Visa sponsorship now or in the future? *",\n      semanticType: "SPONSORSHIP_FUTURE",\n    });\n  });\n\n  it("captures bounded visible page text for AI job context", () => {\n    document.body.innerHTML = `<main><h1>Recruiter</h1><p>Build relationships with candidates and clients.</p><label for="why">Why this role?</label><textarea id="why"></textarea></main>`;\n    expect(scanDocument().pageContext).toContain(\n      "Build relationships with candidates and clients.",\n    );\n  });\n\n'''
if text.count(insert_point) != 1:
    raise SystemExit("scanner regression insertion marker missing")
scanner_test.write_text(text.replace(insert_point, addition + insert_point, 1))

fill_test = Path("apps/extension/src/content/fill.test.ts")
text = fill_test.read_text()
insert_point = '  it("reports only whether a file has been selected, never its local path", () => {'
addition = '''  it("fills a date-like text widget using the employer display format", async () => {\n    document.body.innerHTML = `\n      <label for="available">When are you available to start this role?</label>\n      <input id="available" type="text" placeholder="MM/DD/YYYY">\n    `;\n    const input = document.getElementById("available") as HTMLInputElement;\n    const question = scanDocument().questions[0]!;\n    const result = await applyFillInstructions(\n      [\n        {\n          controlId: question.controlId,\n          frameId: 0,\n          value: "2026-12-17",\n          sensitive: false,\n          approved: true,\n        },\n      ],\n      { verificationTimeoutMs: 80, pollIntervalMs: 5 },\n    );\n    expect(result[0]?.status).toBe("FILLED");\n    expect(input.value).toBe("12/17/2026");\n  });\n\n  it("uses a real click for a controlled native radio group", async () => {\n    document.body.innerHTML = `\n      <fieldset><legend>Are you happy to accept the salary?</legend>\n        <label><input type="radio" name="salary" value="Yes"> Yes</label>\n        <label><input type="radio" name="salary" value="No"> No</label>\n      </fieldset>\n    `;\n    const yes = document.querySelector<HTMLInputElement>('input[value="Yes"]')!;\n    let clicks = 0;\n    yes.addEventListener("click", () => {\n      clicks += 1;\n    });\n    const question = scanDocument().questions[0]!;\n    const result = await applyFillInstructions([\n      {\n        controlId: question.controlId,\n        frameId: 0,\n        value: "Yes",\n        sensitive: true,\n        approved: true,\n      },\n    ]);\n    expect(result[0]?.status).toBe("FILLED");\n    expect(clicks).toBeGreaterThan(0);\n    expect(yes.checked).toBe(true);\n  });\n\n'''
if text.count(insert_point) != 1:
    raise SystemExit("fill regression insertion marker missing")
fill_test.write_text(text.replace(insert_point, addition + insert_point, 1))

ai_test = Path("apps/native-host/tests/test_ai_governance.py")
text = ai_test.read_text()
addition = '''\n\ndef test_preview_uses_live_job_context_and_confirmed_profile_without_seeded_evidence(\n    tmp_path: Path, monkeypatch: pytest.MonkeyPatch\n) -> None:\n    database = create_database(tmp_path)\n    store = configured_store(tmp_path, monkeypatch)\n    from munshi_apply_native.profile_store import ProfileStore\n\n    ProfileStore(database).save(\n        {\n            "profileId": "profile-1",\n            "displayName": "Aadil",\n            "facts": [\n                {\n                    "factId": "skills-1",\n                    "key": "skills",\n                    "value": "recruiting operations, people analytics",\n                    "category": "SKILL",\n                    "trustLevel": "USER_CONFIRMED",\n                    "source": "profile",\n                    "confirmedAt": FIXED_NOW.isoformat(),\n                    "updatedAt": FIXED_NOW.isoformat(),\n                    "protected": False,\n                }\n            ],\n            "records": [],\n            "recordTombstones": [],\n            "createdAt": FIXED_NOW.isoformat(),\n            "updatedAt": FIXED_NOW.isoformat(),\n            "schemaVersion": 1,\n            "snapshotVersion": 1,\n        }\n    )\n    payload = request("CAREER_GOALS")\n    payload["question"] = "Why are you looking to leave your current employer?"\n    payload["pageContext"] = (\n        "Recruiter role focused on candidate relationships, business development, "\n        "and career growth."\n    )\n    result = service(database, store).preview(payload)\n    assert result["state"] == "READY_FOR_PROVIDER"\n    assert len(result["evidenceIds"]) >= 2\n    assert any(item.startswith("job-context-") for item in result["evidenceIds"])\n    assert any(item.startswith("profile-") for item in result["evidenceIds"])\n'''
ai_test.write_text(text + addition)
