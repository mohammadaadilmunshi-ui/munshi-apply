import assert from "node:assert/strict";
import test from "node:test";
import {
  ProtectedProfileConflictError,
  encryptedHistoryNeedsRecovery,
  fetchSyncEvents,
  migrateLegacyProfileSnapshot,
  parseProfileSnapshot,
  putEncryptedEntity,
  reconcileProfileSnapshots,
} from "../app/vault-client.ts";

const now = "2026-08-14T18:00:00.000Z";

function fact(overrides = {}) {
  return {
    factId: "fact-1",
    key: "first_name",
    value: "Aadil",
    category: "IDENTITY",
    trustLevel: "USER_CONFIRMED",
    source: "test",
    confirmedAt: now,
    updatedAt: now,
    protected: false,
    ...overrides,
  };
}

function snapshot(overrides = {}) {
  return {
    profileId: "profile-master",
    displayName: "Test profile",
    facts: [],
    records: [],
    recordTombstones: [],
    createdAt: now,
    updatedAt: now,
    schemaVersion: 1,
    snapshotVersion: 1,
    ...overrides,
  };
}

test("upgrades a legacy flat profile to the canonical snapshot", () => {
  const legacy = {
    ...snapshot(),
    facts: [
      fact({
        factId: "school",
        key: "school_name",
        value: "Example University",
        category: "EDUCATION",
      }),
    ],
  };
  delete legacy.records;
  delete legacy.recordTombstones;
  delete legacy.snapshotVersion;

  const migrated = migrateLegacyProfileSnapshot(legacy);

  assert.equal(migrated.migrated, true);
  assert.equal(migrated.snapshot.snapshotVersion, 1);
  assert.equal(migrated.snapshot.records[0].kind, "EDUCATION");
  assert.equal(migrated.snapshot.records[0].facts[0].key, "school_name");
});

test("rejects duplicate record ids and record/tombstone overlap", () => {
  const record = {
    recordId: "education-1",
    kind: "EDUCATION",
    label: "School",
    facts: [],
    sortOrder: 0,
    createdAt: now,
    updatedAt: now,
  };

  assert.throws(
    () => parseProfileSnapshot(snapshot({ records: [record, record] })),
    /Duplicate encrypted profile record id/,
  );
  assert.throws(
    () =>
      parseProfileSnapshot(
        snapshot({
          records: [record],
          recordTombstones: [
            {
              recordId: record.recordId,
              kind: record.kind,
              deletedAt: now,
              confirmed: true,
            },
          ],
        }),
      ),
    /record and deletion overlap/,
  );
});

test("requires an explicit winner for conflicting protected facts", () => {
  const local = snapshot({
    facts: [
      fact({
        key: "legal_name",
        value: "Local name",
        protected: true,
      }),
    ],
  });
  const remote = snapshot({
    facts: [
      fact({
        factId: "remote-name",
        key: "legal_name",
        value: "Remote name",
        protected: true,
      }),
    ],
  });

  assert.throws(
    () => reconcileProfileSnapshots(local, remote),
    ProtectedProfileConflictError,
  );
  assert.equal(
    reconcileProfileSnapshots(local, remote, "local").facts[0].value,
    "Local name",
  );
  assert.equal(
    reconcileProfileSnapshots(local, remote, "remote").facts[0].value,
    "Remote name",
  );
});

test("uses confirmed tombstone time to resolve cross-device deletion", () => {
  const record = {
    recordId: "education-1",
    kind: "EDUCATION",
    label: "School",
    facts: [],
    sortOrder: 0,
    createdAt: now,
    updatedAt: now,
  };
  const deletedAt = "2026-08-14T18:00:01.000Z";
  const reconciled = reconcileProfileSnapshots(
    snapshot({ records: [record] }),
    snapshot({
      recordTombstones: [
        {
          recordId: record.recordId,
          kind: record.kind,
          deletedAt,
          confirmed: true,
        },
      ],
      updatedAt: deletedAt,
    }),
  );

  assert.equal(reconciled.records.length, 0);
  assert.equal(reconciled.recordTombstones[0].recordId, record.recordId);
});

test("fails closed when the cloud omits the exact next version", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ event: {} }, { status: 201 });
  try {
    await assert.rejects(
      putEncryptedEntity({
        rawKey: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        entityType: "PROFILE.V1",
        entityId: "profile-master",
        baseVersion: 2,
        value: snapshot(),
      }),
      /not acknowledged at the expected version/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("existing encrypted history requires recovery instead of minting a new key", () => {
  assert.equal(
    encryptedHistoryNeedsRecovery({
      hasLocalKey: false,
      eventCount: 1,
      encryptedObjectCount: 0,
    }),
    true,
  );
  assert.equal(
    encryptedHistoryNeedsRecovery({
      hasLocalKey: false,
      eventCount: 0,
      encryptedObjectCount: 0,
    }),
    false,
  );
  assert.equal(
    encryptedHistoryNeedsRecovery({
      hasLocalKey: true,
      eventCount: 20,
      encryptedObjectCount: 4,
    }),
    false,
  );
});

test("owner workspace downloads every sync event page", async () => {
  const originalFetch = globalThis.fetch;
  const cursors = [];
  globalThis.fetch = async (input) => {
    const url = String(input);
    const cursor = new URL(url, "https://workspace.example").searchParams.get(
      "cursor",
    );
    cursors.push(cursor);
    if (cursor === "0") {
      return Response.json({
        workspaceId: "workspace-test",
        events: [{ sequence: 250 }],
        nextCursor: 250,
        hasMore: true,
      });
    }
    return Response.json({
      workspaceId: "workspace-test",
      events: [{ sequence: 251 }],
      nextCursor: 251,
      hasMore: false,
    });
  };
  try {
    const result = await fetchSyncEvents(0);
    assert.deepEqual(cursors, ["0", "250"]);
    assert.equal(result.events.length, 2);
    assert.equal(result.nextCursor, 251);
    assert.equal(result.workspaceId, "workspace-test");
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("sparse newer profile cannot erase unrelated ordinary facts", () => {
  const local = snapshot({
    facts: [
      fact({
        factId: "email",
        key: "email",
        value: "aadil@example.test",
        category: "CONTACT",
        protected: false,
      }),
      fact({
        factId: "preferred-old",
        key: "preferred_name",
        value: "Aadil",
        protected: false,
      }),
    ],
    updatedAt: "2026-08-14T18:00:00.000Z",
  });
  const remote = snapshot({
    facts: [
      fact({
        factId: "preferred-new",
        key: "preferred_name",
        value: "Aadil M",
        protected: false,
        updatedAt: "2026-08-14T18:05:00.000Z",
      }),
    ],
    updatedAt: "2026-08-14T18:05:00.000Z",
  });

  const reconciled = reconcileProfileSnapshots(local, remote);
  assert.equal(
    reconciled.facts.find((candidate) => candidate.key === "email")?.value,
    "aadil@example.test",
  );
  assert.equal(
    reconciled.facts.find((candidate) => candidate.key === "preferred_name")
      ?.value,
    "Aadil M",
  );
});
