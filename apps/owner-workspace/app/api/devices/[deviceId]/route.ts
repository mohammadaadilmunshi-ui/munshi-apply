import { and, eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { devices } from "../../../../db/schema";
import { apiError, authError, getOrCreateOwnerWorkspace } from "../../_shared";

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ deviceId: string }> },
) {
  try {
    const workspace = await getOrCreateOwnerWorkspace();
    const { deviceId } = await context.params;
    const revokedAt = new Date().toISOString();
    const rows = await getDb()
      .update(devices)
      .set({ status: "REVOKED", revokedAt })
      .where(
        and(eq(devices.id, deviceId), eq(devices.workspaceId, workspace.id)),
      )
      .returning({ id: devices.id });
    if (rows.length === 0) {
      return Response.json({ error: "Device not found." }, { status: 404 });
    }
    return Response.json({ device: { id: deviceId, status: "REVOKED" } });
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}
