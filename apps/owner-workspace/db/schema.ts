import { sql } from "drizzle-orm";
import {
  index,
  integer,
  primaryKey,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

export const workspaces = sqliteTable(
  "workspaces",
  {
    id: text("id").primaryKey(),
    ownerEmail: text("owner_email").notNull(),
    createdAt: text("created_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [uniqueIndex("workspaces_owner_email").on(table.ownerEmail)],
);

export const pairingChallenges = sqliteTable(
  "pairing_challenges",
  {
    id: text("id").primaryKey(),
    workspaceId: text("workspace_id")
      .notNull()
      .references(() => workspaces.id, { onDelete: "cascade" }),
    secretSha256: text("secret_sha256").notNull(),
    expiresAt: text("expires_at").notNull(),
    usedAt: text("used_at"),
    createdAt: text("created_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [index("pairing_challenges_workspace").on(table.workspaceId)],
);

export const devices = sqliteTable(
  "devices",
  {
    id: text("id").primaryKey(),
    workspaceId: text("workspace_id")
      .notNull()
      .references(() => workspaces.id, { onDelete: "cascade" }),
    pairingChallengeId: text("pairing_challenge_id")
      .notNull()
      .references(() => pairingChallenges.id, { onDelete: "restrict" }),
    labelCiphertext: text("label_ciphertext").notNull(),
    platform: text("platform").notNull(),
    publicKeyJwk: text("public_key_jwk").notNull(),
    credentialSha256: text("credential_sha256").notNull(),
    status: text("status").notNull().default("ACTIVE"),
    createdAt: text("created_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    lastSeenAt: text("last_seen_at"),
    revokedAt: text("revoked_at"),
  },
  (table) => [
    index("devices_workspace").on(table.workspaceId),
    uniqueIndex("devices_pairing_challenge").on(table.pairingChallengeId),
    uniqueIndex("devices_credential").on(table.credentialSha256),
  ],
);

export const encryptedObjects = sqliteTable(
  "encrypted_objects",
  {
    id: text("id").primaryKey(),
    workspaceId: text("workspace_id")
      .notNull()
      .references(() => workspaces.id, { onDelete: "cascade" }),
    objectKey: text("object_key").notNull(),
    purpose: text("purpose").notNull(),
    metadataCiphertext: text("metadata_ciphertext").notNull(),
    wrappedKey: text("wrapped_key").notNull(),
    payloadSha256: text("payload_sha256").notNull(),
    sizeBytes: integer("size_bytes").notNull(),
    createdAt: text("created_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    index("encrypted_objects_workspace").on(table.workspaceId),
    uniqueIndex("encrypted_objects_key").on(table.objectKey),
  ],
);

export const syncEvents = sqliteTable(
  "sync_events",
  {
    sequence: integer("sequence").primaryKey({ autoIncrement: true }),
    id: text("id").notNull(),
    workspaceId: text("workspace_id")
      .notNull()
      .references(() => workspaces.id, { onDelete: "cascade" }),
    deviceId: text("device_id").references(() => devices.id, {
      onDelete: "set null",
    }),
    correlationId: text("correlation_id").notNull(),
    entityType: text("entity_type").notNull(),
    entityId: text("entity_id").notNull(),
    baseVersion: integer("base_version").notNull(),
    schemaVersion: text("schema_version").notNull(),
    payloadCiphertext: text("payload_ciphertext").notNull(),
    payloadSha256: text("payload_sha256").notNull(),
    createdAt: text("created_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    uniqueIndex("sync_events_event_id").on(table.id),
    index("sync_events_workspace_created").on(
      table.workspaceId,
      table.createdAt,
    ),
    index("sync_events_entity").on(
      table.workspaceId,
      table.entityType,
      table.entityId,
    ),
    uniqueIndex("sync_events_entity_version_slot").on(
      table.workspaceId,
      table.entityType,
      table.entityId,
      table.baseVersion,
    ),
  ],
);

export const entityVersions = sqliteTable(
  "entity_versions",
  {
    workspaceId: text("workspace_id")
      .notNull()
      .references(() => workspaces.id, { onDelete: "cascade" }),
    entityType: text("entity_type").notNull(),
    entityId: text("entity_id").notNull(),
    currentVersion: integer("current_version").notNull(),
    lastEventId: text("last_event_id").notNull(),
    updatedAt: text("updated_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    primaryKey({
      columns: [table.workspaceId, table.entityType, table.entityId],
    }),
  ],
);

export const conflicts = sqliteTable(
  "conflicts",
  {
    id: text("id").primaryKey(),
    workspaceId: text("workspace_id")
      .notNull()
      .references(() => workspaces.id, { onDelete: "cascade" }),
    entityType: text("entity_type").notNull(),
    entityId: text("entity_id").notNull(),
    incomingEventId: text("incoming_event_id").notNull(),
    correlationId: text("correlation_id").notNull(),
    schemaVersion: text("schema_version").notNull(),
    payloadCiphertext: text("payload_ciphertext").notNull(),
    payloadSha256: text("payload_sha256").notNull(),
    expectedVersion: integer("expected_version").notNull(),
    receivedBaseVersion: integer("received_base_version").notNull(),
    status: text("status").notNull().default("OPEN"),
    createdAt: text("created_at")
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    resolvedAt: text("resolved_at"),
  },
  (table) => [
    index("conflicts_workspace_status").on(table.workspaceId, table.status),
    uniqueIndex("conflicts_incoming_event").on(table.incomingEventId),
  ],
);
