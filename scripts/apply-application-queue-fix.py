from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def write(path: str, value: str) -> None:
    (ROOT / path).write_text(value)


def replace_once(path: str, old: str, new: str) -> None:
    value = read(path)
    count = value.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one match in {path}, found {count}: {old[:120]!r}"
        )
    write(path, value.replace(old, new, 1))


replace_once(
    "packages/application-model/src/index.ts",
    'export * from "./analytics";\nexport * from "./autopilot";',
    'export * from "./analytics";\nexport * from "./application-detection";\nexport * from "./autopilot";',
)

replace_once(
    "apps/extension/src/storage/cloud.ts",
    'import type { ApplicationPage } from "@munshi-apply/contracts";\nimport {',
    'import type { ApplicationPage } from "@munshi-apply/contracts";\nimport { isEligibleApplicationPage } from "@munshi-apply/application-model";\nimport {',
)

replace_once(
    "apps/extension/src/storage/cloud.ts",
    '''export async function getCloudConnection(): Promise<CloudConnection | null> {''',
    '''function sameOrigin(left: string, right: string): boolean {\n  try {\n    return new URL(left).origin === new URL(right).origin;\n  } catch {\n    return false;\n  }\n}\n\nexport function shouldPublishApplicationSnapshot(\n  connection: CloudConnection,\n  page: ApplicationPage,\n): boolean {\n  return (\n    !sameOrigin(connection.baseUrl, page.url) && isEligibleApplicationPage(page)\n  );\n}\n\nexport async function getCloudConnection(): Promise<CloudConnection | null> {''',
)

replace_once(
    "apps/extension/src/storage/cloud.ts",
    '''    } else if (event.entityType === "APPLICATION.V1") {\n      applications.push(\n        await decryptJson<ApplicationPage>(rawKey, event.payloadCiphertext),\n      );\n    } else if (event.entityType === "APPLICATION.REVIEW.V1") {''',
    '''    } else if (event.entityType === "APPLICATION.V1") {\n      const application = await decryptJson<ApplicationPage>(\n        rawKey,\n        event.payloadCiphertext,\n      );\n      if (shouldPublishApplicationSnapshot(connection, application)) {\n        applications.push(application);\n      }\n    } else if (event.entityType === "APPLICATION.REVIEW.V1") {''',
)

replace_once(
    "apps/extension/src/storage/cloud.ts",
    '''export async function publishApplicationSnapshot(\n  connection: CloudConnection,\n  page: ApplicationPage,\n): Promise<void> {\n  const rawKey = await getWorkspaceEncryptionKey();''',
    '''export async function publishApplicationSnapshot(\n  connection: CloudConnection,\n  page: ApplicationPage,\n): Promise<void> {\n  if (!shouldPublishApplicationSnapshot(connection, page)) return;\n  const rawKey = await getWorkspaceEncryptionKey();''',
)

replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''} from "../vault-client";\n\ntype View =''',
    '''} from "../vault-client";\nimport {\n  isEligibleApplicationSnapshot,\n  pendingReviewCount,\n} from "../application-eligibility";\n\ntype View =''',
)

replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''    const snapshots = Array.from(nextEntities.entries())\n      .filter(([entityKey]) => entityKey.startsWith("APPLICATION.V1:"))\n      .map(([, entity]) => entity.value as ApplicationSnapshot)\n      .sort((left, right) => right.observedAt.localeCompare(left.observedAt));''',
    '''    const snapshots = Array.from(nextEntities.entries())\n      .filter(([entityKey]) => entityKey.startsWith("APPLICATION.V1:"))\n      .map(([, entity]) => entity.value as ApplicationSnapshot)\n      .filter((application) =>\n        isEligibleApplicationSnapshot(application, window.location.origin),\n      )\n      .sort((left, right) => right.observedAt.localeCompare(left.observedAt));''',
)

replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''  const openReviews = useMemo(\n    () =>\n      applications.reduce(\n        (total, application) =>\n          total +\n          application.questions.filter((question) => question.requiresReview)\n            .length,\n        0,\n      ),\n    [applications],\n  );''',
    '''  const openReviews = useMemo(\n    () =>\n      applications.reduce((total, application) => {\n        const prior = entities.get(\n          `APPLICATION.REVIEW.V1:review-${application.pageId}`,\n        ) as DecryptedEntity<ApplicationReview> | undefined;\n        return total + pendingReviewCount(application, prior?.value);\n      }, 0),\n    [applications, entities],\n  );''',
)

replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''              <p>\n                Applications appear here after the paired desktop extension\n                observes them.\n              </p>''',
    '''              <p>\n                Only pages with verified application-form evidence appear here.\n                Ordinary browsing pages are ignored.\n              </p>''',
)

replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''                {applications.length === 0 && (\n                  <p>No application checkpoint has synchronized yet.</p>\n                )}\n                {applications.map((application) => (\n                  <article key={application.pageId}>\n                    <div>\n                      <strong>{application.title}</strong>\n                      <span>\n                        {new URL(application.url).hostname} ·{" "}\n                        {application.questions.length} questions\n                      </span>\n                    </div>\n                    <button\n                      type="button"\n                      onClick={() => beginReview(application)}\n                    >\n                      Review\n                    </button>\n                  </article>\n                ))}''',
    '''                {applications.length === 0 && (\n                  <p>No verified application checkpoint has synchronized yet.</p>\n                )}\n                {applications.map((application) => {\n                  const prior = entities.get(\n                    `APPLICATION.REVIEW.V1:review-${application.pageId}`,\n                  ) as DecryptedEntity<ApplicationReview> | undefined;\n                  const pending = pendingReviewCount(application, prior?.value);\n                  return (\n                    <article key={application.pageId}>\n                      <div>\n                        <strong>{application.title}</strong>\n                        <span>\n                          {new URL(application.url).hostname} ·{" "}\n                          {application.questions.length} questions · {pending}{" "}\n                          pending\n                        </span>\n                      </div>\n                      <button\n                        type="button"\n                        disabled={application.questions.length === 0}\n                        onClick={() => beginReview(application)}\n                      >\n                        {pending > 0\n                          ? "Review"\n                          : application.questions.length > 0\n                            ? "View"\n                            : "Tracked"}\n                      </button>\n                    </article>\n                  );\n                })}''',
)

print("Application queue repair applied")
