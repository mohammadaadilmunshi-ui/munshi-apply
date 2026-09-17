import {
  fetchCloudEvents,
  getWorkspaceEncryptionKey,
  postEncryptedEntity,
  type CloudConnection,
  type CloudSyncEvent,
  type ResumeRecord,
} from "./cloud";

export type ResumeVaultSource = "MASTER" | "TAILORED" | "IMPORTED";

function latestResumeEvent(
  events: readonly CloudSyncEvent[],
  resumeId: string,
): CloudSyncEvent | null {
  return (
    events
      .filter(
        (event) =>
          event.entityType === "RESUME.V1" && event.entityId === resumeId,
      )
      .sort((left, right) => right.sequence - left.sequence)[0] ?? null
  );
}

function baseVersionFor(event: CloudSyncEvent | null): number {
  return event ? event.baseVersion + 1 : 0;
}

export function resumeFamilyFor(
  source: ResumeVaultSource,
  roleFamily: string | null | undefined,
): string {
  if (source === "MASTER") return "master";
  if (source === "TAILORED") {
    const normalized = (roleFamily ?? "")
      .trim()
      .toLocaleLowerCase("en-US")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return normalized ? `tailored:${normalized}` : "tailored:general";
  }
  return "imported";
}

export function resumeKindLabel(resume: ResumeRecord): string {
  if (resume.source === "MASTER") return "Master résumé";
  if (resume.source === "TAILORED") {
    return resume.roleFamily?.trim()
      ? `Tailored · ${resume.roleFamily.trim()}`
      : "Tailored résumé";
  }
  return "Imported résumé";
}

export async function classifyEncryptedResume(
  connection: CloudConnection,
  resume: ResumeRecord,
  input: {
    source: ResumeVaultSource;
    roleFamily?: string | null;
  },
): Promise<ResumeRecord> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");
  const { events } = await fetchCloudEvents(connection, 0);
  const latest = latestResumeEvent(events, resume.resumeId);
  const roleFamily =
    input.source === "TAILORED" ? input.roleFamily?.trim() || null : null;
  const updated: ResumeRecord = {
    ...resume,
    source: input.source,
    family: resumeFamilyFor(input.source, roleFamily),
    roleFamily,
    active: true,
    deletedAt: undefined,
  };
  await postEncryptedEntity({
    connection,
    rawKey,
    entityType: "RESUME.V1",
    entityId: resume.resumeId,
    baseVersion: baseVersionFor(latest),
    value: updated,
  });
  return updated;
}

export async function deleteEncryptedResume(
  connection: CloudConnection,
  resume: ResumeRecord,
): Promise<void> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");
  const { events } = await fetchCloudEvents(connection, 0);
  const latest = latestResumeEvent(events, resume.resumeId);
  const deleted: ResumeRecord = {
    ...resume,
    active: false,
    deletedAt: new Date().toISOString(),
  };

  await postEncryptedEntity({
    connection,
    rawKey,
    entityType: "RESUME.V1",
    entityId: resume.resumeId,
    baseVersion: baseVersionFor(latest),
    value: deleted,
  });

  const response = await fetch(
    `${connection.baseUrl}/api/objects/${encodeURIComponent(resume.objectId)}`,
    {
      method: "DELETE",
      headers: {
        accept: "application/json",
        authorization: `Bearer ${connection.credential}`,
      },
    },
  );
  if (!response.ok && response.status !== 404) {
    throw new Error(
      "Résumé was removed from the active vault, but encrypted object cleanup failed",
    );
  }
}
