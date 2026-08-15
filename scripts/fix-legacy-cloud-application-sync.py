from pathlib import Path

cloud = Path("apps/extension/src/storage/cloud.ts")
text = cloud.read_text()
old_import = 'import type { ApplicationPage } from "@munshi-apply/contracts";'
new_import = 'import { ApplicationPageSchema, type ApplicationPage } from "@munshi-apply/contracts";'
if old_import not in text:
    raise SystemExit("cloud ApplicationPage import anchor missing")
text = text.replace(old_import, new_import, 1)

anchor = '''export function shouldPublishApplicationSnapshot(\n  connection: CloudConnection,\n  page: ApplicationPage,\n): boolean {\n'''
helper = '''export function parseCloudApplicationPage(value: unknown): ApplicationPage | null {\n  const parsed = ApplicationPageSchema.safeParse(value);\n  return parsed.success ? parsed.data : null;\n}\n\nexport function shouldPublishApplicationSnapshot(\n  connection: CloudConnection,\n  page: ApplicationPage,\n): boolean {\n'''
if anchor not in text:
    raise SystemExit("cloud publication boundary anchor missing")
text = text.replace(anchor, helper, 1)

old_block = '''    } else if (event.entityType === "APPLICATION.V1") {\n      const application = await decryptJson<ApplicationPage>(\n        rawKey,\n        event.payloadCiphertext,\n      );\n      if (shouldPublishApplicationSnapshot(connection, application)) {\n        applications.push(application);\n      }\n'''
new_block = '''    } else if (event.entityType === "APPLICATION.V1") {\n      const application = parseCloudApplicationPage(\n        await decryptJson<unknown>(rawKey, event.payloadCiphertext),\n      );\n      if (application && shouldPublishApplicationSnapshot(connection, application)) {\n        applications.push(application);\n      }\n'''
if old_block not in text:
    raise SystemExit("cloud APPLICATION.V1 block missing")
text = text.replace(old_block, new_block, 1)
cloud.write_text(text)

eligibility = Path("packages/application-model/src/application-detection.ts")
text = eligibility.read_text()
text = text.replace(
'''function meaningfulQuestionCount(page: ApplicationPage): number {\n  return page.questions.filter(\n    (question) => question.semanticType !== "UNKNOWN",\n  ).length;\n}\n''',
'''function meaningfulQuestionCount(page: ApplicationPage): number {\n  const questions = Array.isArray(page.questions) ? page.questions : [];\n  return questions.filter(\n    (question) => question.semanticType !== "UNKNOWN",\n  ).length;\n}\n''',
1,
)
text = text.replace(
'''function applicationSpecificQuestionCount(page: ApplicationPage): number {\n  return page.questions.filter((question) =>\n    applicationSpecificSemantics.has(question.semanticType),\n  ).length;\n}\n''',
'''function applicationSpecificQuestionCount(page: ApplicationPage): number {\n  const questions = Array.isArray(page.questions) ? page.questions : [];\n  return questions.filter((question) =>\n    applicationSpecificSemantics.has(question.semanticType),\n  ).length;\n}\n''',
1,
)
text = text.replace(
'''function hasResumeControl(page: ApplicationPage): boolean {\n  return page.controls.some(\n''',
'''function hasResumeControl(page: ApplicationPage): boolean {\n  const controls = Array.isArray(page.controls) ? page.controls : [];\n  return controls.some(\n''',
1,
)
text = text.replace(
'''function hasApplicationNavigation(page: ApplicationPage): boolean {\n  return page.navigationCandidates.some(\n''',
'''function hasApplicationNavigation(page: ApplicationPage): boolean {\n  const navigationCandidates = Array.isArray(page.navigationCandidates)\n    ? page.navigationCandidates\n    : [];\n  return navigationCandidates.some(\n''',
1,
)
if text == eligibility.read_text():
    raise SystemExit("application eligibility guards were not applied")
eligibility.write_text(text)

app_test = Path("packages/application-model/src/application-detection.test.ts")
text = app_test.read_text()
insert = '''\n  it("does not crash on legacy snapshots that omit newer array fields", () => {\n    const legacy = page({\n      url: "https://help.openai.com/en/articles/legacy-help",\n      title: "Legacy help page",\n      semantics: ["UNKNOWN", "UNKNOWN"],\n    }) as ApplicationPage & {\n      controls?: ApplicationPage["controls"];\n      navigationCandidates?: ApplicationPage["navigationCandidates"];\n    };\n    delete legacy.controls;\n    delete legacy.navigationCandidates;\n\n    expect(applicationPageEligibility(legacy as ApplicationPage)).toEqual({\n      eligible: false,\n      reasons: [],\n    });\n  });\n'''
closing = '\n});\n'
if not text.endswith(closing):
    raise SystemExit("application detection test closing anchor missing")
text = text[:-len(closing)] + insert + closing
app_test.write_text(text)

cloud_test = Path("apps/extension/src/storage/cloud-application.test.ts")
text = cloud_test.read_text()
text = text.replace(
'import { shouldPublishApplicationSnapshot } from "./cloud";',
'import { parseCloudApplicationPage, shouldPublishApplicationSnapshot } from "./cloud";',
1,
)
insert = '''\n  it("normalizes valid legacy application snapshots and skips malformed ones", () => {\n    const current = applicationPage("https://careers.example.test/apply/legacy");\n    const { navigationCandidates: _navigationCandidates, ...legacy } = current;\n    const normalized = parseCloudApplicationPage(legacy);\n\n    expect(normalized).not.toBeNull();\n    expect(normalized?.navigationCandidates).toEqual([]);\n    expect(\n      shouldPublishApplicationSnapshot(connection, normalized!),\n    ).toBe(true);\n\n    const { controls: _controls, ...malformed } = legacy;\n    expect(parseCloudApplicationPage(malformed)).toBeNull();\n  });\n'''
if not text.endswith(closing):
    raise SystemExit("cloud application test closing anchor missing")
text = text[:-len(closing)] + insert + closing
cloud_test.write_text(text)
