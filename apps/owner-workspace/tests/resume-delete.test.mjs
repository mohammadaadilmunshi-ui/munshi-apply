import assert from "node:assert/strict";
import test from "node:test";
import { deleteEncryptedResume } from "../app/vault-client.ts";

test("owner resume delete helper calls the encrypted-object DELETE route", async () => {
  const originalFetch = globalThis.fetch;
  let capturedUrl = "";
  let capturedMethod = "";
  globalThis.fetch = async (input, init) => {
    capturedUrl = String(input);
    capturedMethod = init?.method ?? "GET";
    return Response.json({ object: { id: "obj-resume" }, deleted: true });
  };
  try {
    await deleteEncryptedResume({
      resumeId: "resume-test",
      objectId: "obj-resume",
      name: "Aadil Resume.pdf",
      contentType: "application/pdf",
      sizeBytes: 1024,
      addedAt: "2026-08-15T00:00:00.000Z",
    });
    assert.equal(capturedUrl, "/api/objects/obj-resume");
    assert.equal(capturedMethod, "DELETE");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
