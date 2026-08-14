import assert from "node:assert/strict";
import test from "node:test";
import {
  ProtectedProfileConflictError,
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
