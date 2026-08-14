from pathlib import Path

cloud_path = Path("apps/extension/src/storage/cloud.ts")
cloud = cloud_path.read_text(encoding="utf-8")

old_record = '''export type ResumeRecord = {
  resumeId: string;
  objectId: string;
  name: string;
  contentType: string;
  sizeBytes: number;
  addedAt: string;
};
'''
new_record = '''export type ResumeRecord = {
  resumeId: string;
  objectId: string;
  name: string;
  contentType: string;
  sizeBytes: number;
  addedAt: string;
  sha256?: string;
  family?: string;
  version?: number;
  source?: "MASTER" | "TAILORED" | "IMPORTED";
  roleFamily?: string | null;
  active?: boolean;
};
'''
if old_record in cloud:
    cloud = cloud.replace(old_record, new_record, 1)
elif "sha256?: string;" not in cloud:
    raise SystemExit("ResumeRecord block not found")

old_review = '''export type ApplicationReview = {
  reviewId: string;
  pageId: string;
  resumeId: string | null;
  approvedAt: string;
'''
new_review = '''export type ApplicationReview = {
  reviewId: string;
  pageId: string;
  resumeId: string | null;
  resumeSha256?: string | null;
  approvedAt: string;
'''
if old_review in cloud:
    cloud = cloud.replace(old_review, new_review, 1)
elif "resumeSha256?: string | null;" not in cloud:
    raise SystemExit("ApplicationReview block not found")

anchor = '''export async function uploadEncryptedResume(
  connection: CloudConnection,
  file: File,
): Promise<ResumeRecord> {
'''
if anchor not in cloud:
    raise SystemExit("uploadEncryptedResume anchor not found")

start = cloud.index(anchor)
end = cloud.index('\nexport async function disconnectCloud()', start)
old_upload = cloud[start:end]
new_upload = '''const allowedResumeExtensions = new Set(["pdf", "doc", "docx"]);
const allowedResumeContentTypes = new Set([
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

export function validateResumeFile(file: Pick<File, "name" | "size" | "type">): void {
  if (file.size === 0 || file.size > 12 * 1024 * 1024) {
    throw new Error("Choose a résumé file between 1 byte and 12 MB");
  }
  const extension = file.name.toLowerCase().split(".").pop() ?? "";
  if (!allowedResumeExtensions.has(extension)) {
    throw new Error("Résumé must be a PDF, DOC, or DOCX file");
  }
  if (file.type && !allowedResumeContentTypes.has(file.type.toLowerCase())) {
    throw new Error("Résumé file type does not match PDF, DOC, or DOCX");
  }
}

export async function uploadEncryptedResume(
  connection: CloudConnection,
  file: File,
  options: {
    family?: string;
    source?: "MASTER" | "TAILORED" | "IMPORTED";
    roleFamily?: string | null;
  } = {},
): Promise<ResumeRecord> {
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");
  validateResumeFile(file);

  const family = options.family?.trim() || "master";
  const snapshot = await getCloudSnapshot(connection);
  const version =
    Math.max(
      0,
      ...snapshot.resumes
        .filter((resume) => (resume.family ?? "master") === family)
        .map((resume) => resume.version ?? 1),
    ) + 1;
  const fileBuffer = await file.arrayBuffer();
  const fileSha256 = await sha256Hex(fileBuffer);
  const objectId = `obj-${crypto.randomUUID()}`;
  const record: ResumeRecord = {
    resumeId: `resume-${crypto.randomUUID()}`,
    objectId,
    name: file.name,
    contentType: file.type || "application/octet-stream",
    sizeBytes: file.size,
    addedAt: new Date().toISOString(),
    sha256: fileSha256,
    family,
    version,
    source: options.source ?? "IMPORTED",
    roleFamily: options.roleFamily ?? null,
    active: true,
  };
  const encryptedPayload = await encryptBytes(
    rawKey,
    new Uint8Array(fileBuffer),
  );
  const bytes = new TextEncoder().encode(encryptedPayload);
  const metadataCiphertext = await encryptJson(rawKey, record);
  const response = await fetch(`${connection.baseUrl}/api/objects`, {
    method: "POST",
    headers: {
      "content-type": "application/octet-stream",
      authorization: `Bearer ${connection.credential}`,
      "x-munshi-object-id": objectId,
      "x-munshi-purpose": "RESUME",
      "x-munshi-metadata-ciphertext": metadataCiphertext,
      "x-munshi-wrapped-key": "workspace-key-v1",
      "x-munshi-payload-sha256": await sha256Hex(bytes.buffer),
    },
    body: bytes,
  });
  const payload = (await response.json()) as { error?: string };
  if (!response.ok) {
    throw new Error(payload.error ?? "Encrypted résumé upload failed");
  }
  await postEncryptedEntity({
    connection,
    rawKey,
    entityType: "RESUME.V1",
    entityId: record.resumeId,
    baseVersion: 0,
    value: record,
  });
  return record;
}
'''
cloud = cloud[:start] + new_upload + cloud[end:]
cloud_path.write_text(cloud, encoding="utf-8")

app_path = Path("apps/extension/src/sidepanel/App.tsx")
app = app_path.read_text(encoding="utf-8")
old = '''        const review: ApplicationReview = {
          reviewId: `review-${page.pageId}`, pageId: page.pageId,
          resumeId: selectedResumeId || null, approvedAt: now(),
'''
new = '''        const selectedResume = cloudSnapshot?.resumes.find(
          (resume) => resume.resumeId === selectedResumeId,
        );
        const review: ApplicationReview = {
          reviewId: `review-${page.pageId}`, pageId: page.pageId,
          resumeId: selectedResumeId || null,
          resumeSha256: selectedResume?.sha256 ?? null,
          approvedAt: now(),
'''
if old in app:
    app = app.replace(old, new, 1)
elif "resumeSha256: selectedResume?.sha256 ?? null," not in app:
    raise SystemExit("ApplicationReview construction not found")
app_path.write_text(app, encoding="utf-8")
