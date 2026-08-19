import { and, count, eq } from "drizzle-orm";
import { getDb } from "../../db";
import { devices, workspaces } from "../../db/schema";
import { getChatGPTUser } from "../chatgpt-auth";

export type WorkspacePrincipal = {
  workspaceId: string;
  deviceId: string | null;
  kind: "owner" | "device";
};

export function apiError(error: unknown): Response {
  const message = error instanceof Error ? error.message : "Unexpected error";
  if (message.includes("no such table")) {
    return Response.json(
      { error: "Workspace storage is not migrated yet." },
      { status: 503 },
    );
  }
  return Response.json({ error: "Workspace request failed." }, { status: 500 });
}

export function normalizeOwnerEmail(email: string): string {
  return email.trim().toLowerCase();
}

export async function sha256Hex(value: string | ArrayBuffer): Promise<string> {
  const bytes =
    typeof value === "string" ? new TextEncoder().encode(value) : value;
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

export function randomSecret(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

export async function getOrCreateOwnerWorkspace(): Promise<{
  id: string;
  ownerEmail: string;
}> {
  const user = await getChatGPTUser();
  if (!user) throw new Error("OWNER_AUTH_REQUIRED");

  const ownerEmail = normalizeOwnerEmail(user.email);
  const db = getDb();
  const existing = await db.query.workspaces.findFirst({
    where: eq(workspaces.ownerEmail, ownerEmail),
  });
  if (existing) return existing;

  const created = { id: crypto.randomUUID(), ownerEmail };
  await db.insert(workspaces).values(created).onConflictDoNothing();
  const workspace = await db.query.workspaces.findFirst({
    where: eq(workspaces.ownerEmail, ownerEmail),
  });
  if (!workspace) throw new Error("WORKSPACE_CREATE_FAILED");
  return workspace;
}

export async function requirePrincipal(
  request: Request,
): Promise<WorkspacePrincipal> {
  const authorization = request.headers.get("authorization") ?? "";
  if (authorization.startsWith("Bearer ")) {
    const credential = authorization.slice("Bearer ".length).trim();
    if (credential.length < 32 || credential.length > 256) {
      throw new Error("AUTH_REQUIRED");
    }
    const credentialSha256 = await sha256Hex(credential);
    const db = getDb();
    const device = await db.query.devices.findFirst({
      where: and(
        eq(devices.credentialSha256, credentialSha256),
        eq(devices.status, "ACTIVE"),
      ),
    });
    if (!device) throw new Error("AUTH_REQUIRED");
    return {
      workspaceId: device.workspaceId,
      deviceId: device.id,
      kind: "device",
    };
  }

  const user = await getChatGPTUser();
  if (user) {
    const workspace = await getOrCreateOwnerWorkspace();
    return { workspaceId: workspace.id, deviceId: null, kind: "owner" };
  }

  throw new Error("AUTH_REQUIRED");
}

export function authError(error: unknown): Response | null {
  if (
    error instanceof Error &&
    ["OWNER_AUTH_REQUIRED", "AUTH_REQUIRED"].includes(error.message)
  ) {
    return Response.json(
      { error: "Authentication required." },
      { status: 401 },
    );
  }
  return null;
}

export async function workspaceCounts(workspaceId: string) {
  const db = getDb();
  const [deviceCount] = await db
    .select({ value: count() })
    .from(devices)
    .where(
      and(eq(devices.workspaceId, workspaceId), eq(devices.status, "ACTIVE")),
    );
  return { devices: deviceCount?.value ?? 0 };
}
