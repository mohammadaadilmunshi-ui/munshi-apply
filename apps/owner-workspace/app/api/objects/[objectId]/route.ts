import { env } from "cloudflare:workers";
import { and, eq } from "drizzle-orm";
import { getDb } from "../../../../db";
import { encryptedObjects } from "../../../../db/schema";
import { apiError, authError, requirePrincipal } from "../../_shared";

export async function GET(
  request: Request,
  context: { params: Promise<{ objectId: string }> },
) {
  try {
    const principal = await requirePrincipal(request);
    const { objectId } = await context.params;
    const record = await getDb().query.encryptedObjects.findFirst({
      where: and(
        eq(encryptedObjects.id, objectId),
        eq(encryptedObjects.workspaceId, principal.workspaceId),
      ),
    });
    if (!record) {
      return Response.json({ error: "Object not found." }, { status: 404 });
    }
    const object = await env.BUCKET.get(record.objectKey);
    if (!object) {
      return Response.json(
        { error: "Encrypted object bytes are unavailable." },
        { status: 503 },
      );
    }
    return new Response(object.body, {
      headers: {
        "cache-control": "no-store",
        "content-type": "application/octet-stream",
        "x-munshi-metadata-ciphertext": record.metadataCiphertext,
        "x-munshi-payload-sha256": record.payloadSha256,
        "x-munshi-purpose": record.purpose,
        "x-munshi-wrapped-key": record.wrappedKey,
      },
    });
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}


export async function DELETE(
  request: Request,
  context: { params: Promise<{ objectId: string }> },
) {
  try {
    const principal = await requirePrincipal(request);
    if (principal.kind !== "owner") {
      return Response.json(
        { error: "Only the workspace owner can delete encrypted résumés." },
        { status: 403 },
      );
    }

    const { objectId } = await context.params;
    const db = getDb();
    const record = await db.query.encryptedObjects.findFirst({
      where: and(
        eq(encryptedObjects.id, objectId),
        eq(encryptedObjects.workspaceId, principal.workspaceId),
      ),
    });
    if (!record) {
      return Response.json({ object: { id: objectId }, deleted: false });
    }
    if (record.purpose !== "RESUME") {
      return Response.json(
        { error: "Only résumé objects can be deleted from the résumé vault." },
        { status: 409 },
      );
    }

    await env.BUCKET.delete(record.objectKey);
    await db
      .delete(encryptedObjects)
      .where(
        and(
          eq(encryptedObjects.id, objectId),
          eq(encryptedObjects.workspaceId, principal.workspaceId),
        ),
      );
    return Response.json({ object: { id: objectId }, deleted: true });
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}
