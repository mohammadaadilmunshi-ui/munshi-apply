import { and, count, eq } from "drizzle-orm";
import { getDb } from "../../../db";
import { conflicts, encryptedObjects, syncEvents } from "../../../db/schema";
import {
  apiError,
  authError,
  getOrCreateOwnerWorkspace,
  workspaceCounts,
} from "../_shared";

export async function GET() {
  try {
    const workspace = await getOrCreateOwnerWorkspace();
    const db = getDb();
    const [{ value: objectCount } = { value: 0 }] = await db
      .select({ value: count() })
      .from(encryptedObjects)
      .where(eq(encryptedObjects.workspaceId, workspace.id));
    const [{ value: eventCount } = { value: 0 }] = await db
      .select({ value: count() })
      .from(syncEvents)
      .where(eq(syncEvents.workspaceId, workspace.id));
    const [{ value: conflictCount } = { value: 0 }] = await db
      .select({ value: count() })
      .from(conflicts)
      .where(
        and(
          eq(conflicts.workspaceId, workspace.id),
          eq(conflicts.status, "OPEN"),
        ),
      );
    const counts = await workspaceCounts(workspace.id);

    return Response.json({
      workspace: {
        id: workspace.id,
        status: "ready",
        devices: counts.devices,
        encryptedObjects: objectCount,
        events: eventCount,
        conflicts: conflictCount,
      },
    });
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}
