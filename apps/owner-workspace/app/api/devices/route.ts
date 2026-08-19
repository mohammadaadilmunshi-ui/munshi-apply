import { and, desc, eq } from "drizzle-orm";
import { getDb } from "../../../db";
import { devices } from "../../../db/schema";
import { apiError, authError, getOrCreateOwnerWorkspace } from "../_shared";

export async function GET() {
  try {
    const workspace = await getOrCreateOwnerWorkspace();
    const rows = await getDb()
      .select({
        id: devices.id,
        labelCiphertext: devices.labelCiphertext,
        platform: devices.platform,
        status: devices.status,
        createdAt: devices.createdAt,
        lastSeenAt: devices.lastSeenAt,
        revokedAt: devices.revokedAt,
      })
      .from(devices)
      .where(
        and(
          eq(devices.workspaceId, workspace.id),
          eq(devices.status, "ACTIVE"),
        ),
      )
      .orderBy(desc(devices.createdAt));
    return Response.json({ devices: rows });
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}
