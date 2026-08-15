from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one replacement target, found {count}")
    write(path, content.replace(old, new, 1))


def append_before(path: str, marker: str, addition: str) -> None:
    content = read(path)
    index = content.rfind(marker)
    if index < 0:
        raise RuntimeError(f"{path}: marker not found")
    write(path, content[:index] + addition + content[index:])


# ---------------------------------------------------------------------------
# Native protocol negotiation: a PING from an old host must not be mistaken
# for compatibility with the current extension.
# ---------------------------------------------------------------------------
replace_once(
    "apps/native-host/src/munshi_apply_native/native_messaging.py",
    "from .settings import Settings\n\n\ndef read_message",
    '''from .settings import Settings\n\n\nNATIVE_PROTOCOL_VERSION = 2\nNATIVE_CAPABILITIES: dict[str, bool] = {\n    "profile_vault": True,\n    "application_checkpoints": True,\n    "interaction_learning": True,\n    "ai_settings": True,\n    "ai_governance": True,\n    "ai_draft_lifecycle": True,\n}\n\n\ndef read_message''',
)
replace_once(
    "apps/native-host/src/munshi_apply_native/native_messaging.py",
    '''    if message_type == "PING":\n        return {"ok": True, "data": database.health()}''',
    '''    if message_type == "PING":\n        health = database.health()\n        health["protocol_version"] = NATIVE_PROTOCOL_VERSION\n        health["capabilities"] = dict(NATIVE_CAPABILITIES)\n        return {"ok": True, "data": health}''',
)

replace_once(
    "apps/native-host/tests/test_native_messaging.py",
    '''import io\n\nfrom munshi_apply_native.native_messaging import read_message, write_message''',
    '''import io\nfrom pathlib import Path\n\nfrom munshi_apply_native.database import Database\nfrom munshi_apply_native.native_messaging import handle, read_message, write_message''',
)
append_before(
    "apps/native-host/tests/test_native_messaging.py",
    "\n",
    '''\n\ndef test_ping_advertises_current_protocol_and_capabilities(tmp_path: Path) -> None:\n    repository_root = Path(__file__).resolve().parents[3]\n    database = Database(tmp_path / "native.sqlite", repository_root / "migrations")\n    database.migrate()\n\n    response = handle({"type": "PING"}, database)\n\n    assert response["ok"] is True\n    data = response["data"]\n    assert isinstance(data, dict)\n    assert data["protocol_version"] == 2\n    assert data["capabilities"]["ai_governance"] is True\n    assert data["capabilities"]["ai_draft_lifecycle"] is True\n    assert data["capabilities"]["profile_vault"] is True\n''',
)

# ---------------------------------------------------------------------------
# Extension native runtime compatibility model + explicit profile conflict
# resolution message.
# ---------------------------------------------------------------------------
replace_once(
    "apps/extension/src/messaging/client.ts",
    '''export type NativeRuntimeHealth = {\n  status: string;\n  database: string;\n  migration_count: number;\n  schema_version: string;\n  outbox: Record<string, number>;\n};''',
    '''export type NativeRuntimeHealth = {\n  status: string;\n  database: string;\n  migration_count: number;\n  schema_version: string;\n  outbox: Record<string, number>;\n  protocol_version?: number;\n  capabilities?: {\n    profile_vault?: boolean;\n    application_checkpoints?: boolean;\n    interaction_learning?: boolean;\n    ai_settings?: boolean;\n    ai_governance?: boolean;\n    ai_draft_lifecycle?: boolean;\n  };\n};\n\nexport const REQUIRED_NATIVE_PROTOCOL_VERSION = 2;\n\nexport type NativeRuntimeCompatibility =\n  | { compatible: true }\n  | { compatible: false; reason: string };\n\nexport function nativeRuntimeCompatibility(\n  health: NativeRuntimeHealth,\n): NativeRuntimeCompatibility {\n  if (health.protocol_version !== REQUIRED_NATIVE_PROTOCOL_VERSION) {\n    return {\n      compatible: false,\n      reason:\n        health.protocol_version === undefined\n          ? "Installed native companion predates the current protocol."\n          : `Installed native protocol ${health.protocol_version}; version ${REQUIRED_NATIVE_PROTOCOL_VERSION} is required.`,\n    };\n  }\n  const requiredCapabilities = [\n    "profile_vault",\n    "application_checkpoints",\n    "ai_settings",\n    "ai_governance",\n    "ai_draft_lifecycle",\n  ] as const;\n  const missing = requiredCapabilities.filter(\n    (capability) => health.capabilities?.[capability] !== true,\n  );\n  return missing.length === 0\n    ? { compatible: true }\n    : {\n        compatible: false,\n        reason: `Native companion is missing required capabilities: ${missing.join(", ")}.`,\n      };\n}''',
)
replace_once(
    "apps/extension/src/messaging/client.ts",
    '''export type ProfileSyncStatus = {\n  conflict: {\n    keys: string[];\n    detectedAt: string;\n  } | null;\n};''',
    '''export type ProfileConflictDetail = {\n  key: string;\n  localValue: unknown;\n  remoteValue: unknown;\n};\n\nexport type ProfileSyncStatus = {\n  conflict: {\n    keys: string[];\n    details: ProfileConflictDetail[];\n    detectedAt: string;\n  } | null;\n};''',
)
replace_once(
    "apps/extension/src/messaging/client.ts",
    '''export async function getProfileSyncStatus(): Promise<ProfileSyncStatus> {\n  return (await send({ type: "GET_PROFILE_SYNC_STATUS" })) as ProfileSyncStatus;\n}\n\nexport function saveProfile''',
    '''export async function getProfileSyncStatus(): Promise<ProfileSyncStatus> {\n  return (await send({ type: "GET_PROFILE_SYNC_STATUS" })) as ProfileSyncStatus;\n}\n\nexport async function resolveProfileSyncConflict(\n  winner: "local" | "remote",\n): Promise<ProfileSnapshot> {\n  return parseProfileSnapshot(\n    await send({\n      type: "RESOLVE_PROFILE_SYNC_CONFLICT",\n      payload: { winner },\n    }),\n  );\n}\n\nexport function saveProfile''',
)

write(
    "apps/extension/src/messaging/native-runtime.test.ts",
    '''import { describe, expect, it } from "vitest";\nimport {\n  REQUIRED_NATIVE_PROTOCOL_VERSION,\n  nativeRuntimeCompatibility,\n  type NativeRuntimeHealth,\n} from "./client";\n\nfunction health(\n  input: Partial<NativeRuntimeHealth> = {},\n): NativeRuntimeHealth {\n  return {\n    status: "healthy",\n    database: "healthy",\n    migration_count: 6,\n    schema_version: "006_ai_budget_reservations.sql",\n    outbox: {},\n    ...input,\n  };\n}\n\ndescribe("native runtime compatibility", () => {\n  it("rejects a legacy PING that has no protocol version", () => {\n    expect(nativeRuntimeCompatibility(health())).toEqual({\n      compatible: false,\n      reason: "Installed native companion predates the current protocol.",\n    });\n  });\n\n  it("accepts the current protocol only when required capabilities exist", () => {\n    expect(\n      nativeRuntimeCompatibility(\n        health({\n          protocol_version: REQUIRED_NATIVE_PROTOCOL_VERSION,\n          capabilities: {\n            profile_vault: true,\n            application_checkpoints: true,\n            interaction_learning: true,\n            ai_settings: true,\n            ai_governance: true,\n            ai_draft_lifecycle: true,\n          },\n        }),\n      ),\n    ).toEqual({ compatible: true });\n  });\n});\n''',
)

replace_once(
    "packages/contracts/src/index.ts",
    '''  | { type: "GET_PROFILE_SYNC_STATUS" }\n  | { type: "SAVE_PROFILE"; payload: MasterProfile }''',
    '''  | { type: "GET_PROFILE_SYNC_STATUS" }\n  | {\n      type: "RESOLVE_PROFILE_SYNC_CONFLICT";\n      payload: { winner: "local" | "remote" };\n    }\n  | { type: "SAVE_PROFILE"; payload: MasterProfile }''',
)

# ---------------------------------------------------------------------------
# Profile reconciliation: retain the fail-closed default, but allow an explicit
# owner choice to resolve all currently listed protected conflicts.
# ---------------------------------------------------------------------------
replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''export class ProtectedProfileConflictError extends Error {\n  readonly keys: string[];\n\n  constructor(keys: string[]) {\n    super(\n      `Protected profile facts changed on another device: ${keys.join(", ")}. Review the workspace before continuing.`,\n    );\n    this.name = "ProtectedProfileConflictError";\n    this.keys = keys;\n  }\n}''',
    '''export type ProtectedProfileConflictWinner = "local" | "remote";\n\nexport type ProtectedProfileConflictDetail = {\n  key: string;\n  localValue: ProfileFact["value"] | null;\n  remoteValue: ProfileFact["value"] | null;\n};\n\nexport class ProtectedProfileConflictError extends Error {\n  readonly keys: string[];\n  readonly details: ProtectedProfileConflictDetail[];\n\n  constructor(keys: string[], details: ProtectedProfileConflictDetail[] = []) {\n    super(\n      `Protected profile facts changed on another device: ${keys.join(", ")}. Review the workspace before continuing.`,\n    );\n    this.name = "ProtectedProfileConflictError";\n    this.keys = keys;\n    this.details = details;\n  }\n}''',
)
replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''export function protectedProfileConflictKeys(\n  localProfile: ProfileSnapshot,\n  remoteProfile: ProfileSnapshot,\n): string[] {\n  const conflicts = protectedFactConflictKeys(\n    localProfile.facts,\n    remoteProfile.facts,\n  );\n  const remoteRecords = new Map(\n    remoteProfile.records.map((record) => [record.recordId, record] as const),\n  );\n  for (const localRecord of localProfile.records) {\n    const remoteRecord = remoteRecords.get(localRecord.recordId);\n    if (!remoteRecord) continue;\n    if (localRecord.kind !== remoteRecord.kind) {\n      conflicts.push(`record:${localRecord.recordId}:kind`);\n      continue;\n    }\n    conflicts.push(\n      ...protectedFactConflictKeys(\n        localRecord.facts,\n        remoteRecord.facts,\n        `record:${localRecord.recordId}:`,\n      ),\n    );\n  }\n  return [...new Set(conflicts)].sort();\n}\n\nfunction chooseProtectedFact''',
    '''export function protectedProfileConflictKeys(\n  localProfile: ProfileSnapshot,\n  remoteProfile: ProfileSnapshot,\n): string[] {\n  const conflicts = protectedFactConflictKeys(\n    localProfile.facts,\n    remoteProfile.facts,\n  );\n  const remoteRecords = new Map(\n    remoteProfile.records.map((record) => [record.recordId, record] as const),\n  );\n  for (const localRecord of localProfile.records) {\n    const remoteRecord = remoteRecords.get(localRecord.recordId);\n    if (!remoteRecord) continue;\n    if (localRecord.kind !== remoteRecord.kind) {\n      conflicts.push(`record:${localRecord.recordId}:kind`);\n      continue;\n    }\n    conflicts.push(\n      ...protectedFactConflictKeys(\n        localRecord.facts,\n        remoteRecord.facts,\n        `record:${localRecord.recordId}:`,\n      ),\n    );\n  }\n  return [...new Set(conflicts)].sort();\n}\n\nfunction conflictValue(\n  profile: ProfileSnapshot,\n  key: string,\n): ProfileFact["value"] | null {\n  if (!key.startsWith("record:")) {\n    return profile.facts.find((fact) => fact.key === key)?.value ?? null;\n  }\n  const [, recordId, factKey] = key.split(":");\n  const record = profile.records.find((candidate) => candidate.recordId === recordId);\n  if (!record) return null;\n  if (factKey === "kind") return record.kind;\n  return record.facts.find((fact) => fact.key === factKey)?.value ?? null;\n}\n\nexport function protectedProfileConflictDetails(\n  localProfile: ProfileSnapshot,\n  remoteProfile: ProfileSnapshot,\n): ProtectedProfileConflictDetail[] {\n  return protectedProfileConflictKeys(localProfile, remoteProfile).map((key) => ({\n    key,\n    localValue: conflictValue(localProfile, key),\n    remoteValue: conflictValue(remoteProfile, key),\n  }));\n}\n\nfunction chooseProtectedFact''',
)
replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''function chooseProtectedFact(\n  baseFact: ProfileFact | undefined,\n  localFact: ProfileFact | undefined,\n  remoteFact: ProfileFact | undefined,\n): ProfileFact | undefined {\n  if (localFact && remoteFact) {\n    const sameValue =\n      factValueFingerprint(localFact.value) ===\n      factValueFingerprint(remoteFact.value);\n    if (sameValue) {\n      if (isConfirmedProtectedFact(baseFact)) return baseFact;\n      if (isConfirmedProtectedFact(localFact)) return localFact;\n      if (isConfirmedProtectedFact(remoteFact)) return remoteFact;\n      return baseFact ?? laterFact(localFact, remoteFact);\n    }\n  }\n  if (isConfirmedProtectedFact(localFact)) return localFact;\n  if (isConfirmedProtectedFact(remoteFact)) return remoteFact;\n  return baseFact ?? laterFact(localFact, remoteFact);\n}''',
    '''function chooseProtectedFact(\n  baseFact: ProfileFact | undefined,\n  localFact: ProfileFact | undefined,\n  remoteFact: ProfileFact | undefined,\n  winner: ProtectedProfileConflictWinner | null,\n): ProfileFact | undefined {\n  if (localFact && remoteFact) {\n    const sameValue =\n      factValueFingerprint(localFact.value) ===\n      factValueFingerprint(remoteFact.value);\n    if (sameValue) {\n      if (isConfirmedProtectedFact(baseFact)) return baseFact;\n      if (isConfirmedProtectedFact(localFact)) return localFact;\n      if (isConfirmedProtectedFact(remoteFact)) return remoteFact;\n      return baseFact ?? laterFact(localFact, remoteFact);\n    }\n    if (winner === "local") return localFact;\n    if (winner === "remote") return remoteFact;\n  }\n  if (isConfirmedProtectedFact(localFact)) return localFact;\n  if (isConfirmedProtectedFact(remoteFact)) return remoteFact;\n  return baseFact ?? laterFact(localFact, remoteFact);\n}''',
)
replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''function reconcileFacts(\n  baseFacts: ProfileFact[],\n  localFacts: ProfileFact[],\n  remoteFacts: ProfileFact[],\n): ProfileFact[] {''',
    '''function reconcileFacts(\n  baseFacts: ProfileFact[],\n  localFacts: ProfileFact[],\n  remoteFacts: ProfileFact[],\n  protectedWinner: ProtectedProfileConflictWinner | null = null,\n): ProfileFact[] {''',
)
replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''    const choice = protectedFact\n      ? chooseProtectedFact(baseFact, localFact, remoteFact)\n      : ordinaryChoice;''',
    '''    const choice = protectedFact\n      ? chooseProtectedFact(\n          baseFact,\n          localFact,\n          remoteFact,\n          protectedWinner,\n        )\n      : ordinaryChoice;''',
)
replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''function reconcileRecord(\n  local: ProfileRecord,\n  remote: ProfileRecord,\n): ProfileRecord {\n  if (local.kind !== remote.kind) {\n    throw new ProtectedProfileConflictError([`record:${local.recordId}:kind`]);\n  }\n  const conflicts = protectedFactConflictKeys(\n    local.facts,\n    remote.facts,\n    `record:${local.recordId}:`,\n  );\n  if (conflicts.length > 0) throw new ProtectedProfileConflictError(conflicts);\n  const base = local.updatedAt > remote.updatedAt ? local : remote;\n  return {\n    ...base,\n    createdAt:\n      local.createdAt < remote.createdAt ? local.createdAt : remote.createdAt,\n    facts: reconcileFacts(base.facts, local.facts, remote.facts),\n  };\n}''',
    '''function reconcileRecord(\n  local: ProfileRecord,\n  remote: ProfileRecord,\n  protectedWinner: ProtectedProfileConflictWinner | null,\n): ProfileRecord {\n  if (local.kind !== remote.kind) {\n    if (protectedWinner === "local") return local;\n    if (protectedWinner === "remote") return remote;\n    throw new ProtectedProfileConflictError([`record:${local.recordId}:kind`]);\n  }\n  const conflicts = protectedFactConflictKeys(\n    local.facts,\n    remote.facts,\n    `record:${local.recordId}:`,\n  );\n  if (conflicts.length > 0 && !protectedWinner) {\n    throw new ProtectedProfileConflictError(conflicts);\n  }\n  const base = local.updatedAt > remote.updatedAt ? local : remote;\n  return {\n    ...base,\n    createdAt:\n      local.createdAt < remote.createdAt ? local.createdAt : remote.createdAt,\n    facts: reconcileFacts(\n      base.facts,\n      local.facts,\n      remote.facts,\n      protectedWinner,\n    ),\n  };\n}''',
)
replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''function reconcileRecordEvents(\n  local: ProfileSnapshot,\n  remote: ProfileSnapshot,\n): {''',
    '''function reconcileRecordEvents(\n  local: ProfileSnapshot,\n  remote: ProfileSnapshot,\n  protectedWinner: ProtectedProfileConflictWinner | null,\n): {''',
)
replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''      const record = reconcileRecord(localEvent.record, remoteEvent.record);''',
    '''      const record = reconcileRecord(\n        localEvent.record,\n        remoteEvent.record,\n        protectedWinner,\n      );''',
)
replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''export function reconcileProtectedProfile(\n  localProfile: ProfileSnapshot,\n  remoteProfile: ProfileSnapshot,\n): ProfileSnapshot {\n  const conflicts = protectedProfileConflictKeys(localProfile, remoteProfile);\n  if (conflicts.length > 0) {\n    throw new ProtectedProfileConflictError(conflicts);\n  }\n\n  const base =\n    localProfile.updatedAt > remoteProfile.updatedAt\n      ? localProfile\n      : remoteProfile;\n  const recordState = reconcileRecordEvents(localProfile, remoteProfile);''',
    '''export function reconcileProtectedProfile(\n  localProfile: ProfileSnapshot,\n  remoteProfile: ProfileSnapshot,\n  protectedWinner: ProtectedProfileConflictWinner | null = null,\n): ProfileSnapshot {\n  const conflicts = protectedProfileConflictKeys(localProfile, remoteProfile);\n  if (conflicts.length > 0 && !protectedWinner) {\n    throw new ProtectedProfileConflictError(\n      conflicts,\n      protectedProfileConflictDetails(localProfile, remoteProfile),\n    );\n  }\n\n  const base =\n    localProfile.updatedAt > remoteProfile.updatedAt\n      ? localProfile\n      : remoteProfile;\n  const recordState = reconcileRecordEvents(\n    localProfile,\n    remoteProfile,\n    protectedWinner,\n  );''',
)
replace_once(
    "apps/extension/src/storage/profile-sync.ts",
    '''    facts: reconcileFacts(base.facts, localProfile.facts, remoteProfile.facts),''',
    '''    facts: reconcileFacts(\n      base.facts,\n      localProfile.facts,\n      remoteProfile.facts,\n      protectedWinner,\n    ),''',
)
append_before(
    "apps/extension/src/storage/profile-sync.ts",
    "\nexport async function synchronizeProtectedProfile",
    '''\nexport async function resolveProtectedProfileConflict(\n  connection: CloudConnection,\n  localProfile: ProfileSnapshot,\n  winner: ProtectedProfileConflictWinner,\n): Promise<ProfileSnapshot> {\n  const rawKey = await getWorkspaceEncryptionKey();\n  if (!rawKey) throw new Error("Encrypted synchronization is not enabled");\n\n  const snapshot = await getCloudSnapshot(connection);\n  if (!snapshot.profile) {\n    throw new Error("No encrypted workspace profile exists to resolve");\n  }\n  const conflicts = protectedProfileConflictKeys(localProfile, snapshot.profile);\n  if (conflicts.length === 0) {\n    return synchronizeProtectedProfile(connection, localProfile);\n  }\n  const resolved = reconcileProtectedProfile(\n    localProfile,\n    snapshot.profile,\n    winner,\n  );\n  const synchronized = parseProfileSnapshot({\n    ...resolved,\n    updatedAt: new Date().toISOString(),\n  });\n  await postProfile(connection, rawKey, synchronized, snapshot.profileVersion);\n  return synchronized;\n}\n''',
)
append_before(
    "apps/extension/src/storage/profile-sync.test.ts",
    "\n});",
    '''\n\n  it("resolves confirmed protected conflicts only after an explicit owner winner", () => {\n    const local = profile(\n      [fact("first_name", "Mohammad Aadil Vasim")],\n      "2026-08-14T12:02:00.000Z",\n    );\n    const remote = profile(\n      [fact("first_name", "Mohammad Aadil")],\n      "2026-08-14T12:03:00.000Z",\n    );\n\n    expect(() => reconcileProtectedProfile(local, remote)).toThrow(\n      /first_name/,\n    );\n    expect(\n      reconcileProtectedProfile(local, remote, "local").facts.find(\n        (candidate) => candidate.key === "first_name",\n      )?.value,\n    ).toBe("Mohammad Aadil Vasim");\n    expect(\n      reconcileProtectedProfile(local, remote, "remote").facts.find(\n        (candidate) => candidate.key === "first_name",\n      )?.value,\n    ).toBe("Mohammad Aadil");\n  });\n''',
)

# ---------------------------------------------------------------------------
# Service worker: conflict is a review state, not a transport failure; expose an
# explicit resolution operation and keep concrete local/remote values in memory.
# ---------------------------------------------------------------------------
replace_once(
    "apps/extension/src/background/service-worker.ts",
    '''import {\n  ProtectedProfileConflictError,\n  synchronizeProtectedProfile,\n} from "../storage/profile-sync";''',
    '''import {\n  ProtectedProfileConflictError,\n  resolveProtectedProfileConflict,\n  synchronizeProtectedProfile,\n} from "../storage/profile-sync";''',
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    '''let profileSyncConflict: { keys: string[]; detectedAt: string } | null = null;\n\nfunction rememberProfileConflict(error: ProtectedProfileConflictError): void {\n  profileSyncConflict = {\n    keys: [...error.keys],\n    detectedAt: new Date().toISOString(),\n  };\n}''',
    '''let profileSyncConflict: {\n  keys: string[];\n  details: ProtectedProfileConflictError["details"];\n  detectedAt: string;\n} | null = null;\n\nfunction rememberProfileConflict(error: ProtectedProfileConflictError): void {\n  profileSyncConflict = {\n    keys: [...error.keys],\n    details: [...error.details],\n    detectedAt: new Date().toISOString(),\n  };\n}''',
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    '''      case "GET_PROFILE_SYNC_STATUS":\n        return { ok: true, data: { conflict: profileSyncConflict } };\n      case "SAVE_PROFILE": {''',
    '''      case "GET_PROFILE_SYNC_STATUS":\n        return { ok: true, data: { conflict: profileSyncConflict } };\n      case "RESOLVE_PROFILE_SYNC_CONFLICT": {\n        const localProfile = await loadAuthoritativeProfileSnapshot();\n        if (!localProfile) throw new Error("No local profile is available");\n        const connection = await getCloudConnection();\n        if (!connection || !(await isCloudEncryptionReady())) {\n          throw new Error("Encrypted workspace synchronization is unavailable");\n        }\n        const resolved = await resolveProtectedProfileConflict(\n          connection,\n          localProfile,\n          request.payload.winner,\n        );\n        await persistAuthoritativeProfileSnapshot(resolved);\n        profileSyncConflict = null;\n        return { ok: true, data: resolved };\n      }\n      case "SAVE_PROFILE": {''',
)
replace_once(
    "apps/extension/src/background/service-worker.ts",
    '''          } catch (error) {\n            if (error instanceof ProtectedProfileConflictError) {\n              rememberProfileConflict(error);\n            }\n            throw error;\n          }\n        }\n        return { ok: true };\n      }''',
    '''          } catch (error) {\n            if (error instanceof ProtectedProfileConflictError) {\n              rememberProfileConflict(error);\n              return {\n                ok: true,\n                data: {\n                  localSaved: true,\n                  cloudSynced: false,\n                  conflict: profileSyncConflict,\n                },\n              };\n            }\n            throw error;\n          }\n        }\n        return { ok: true, data: { localSaved: true, cloudSynced: true } };\n      }''',
)

# ---------------------------------------------------------------------------
# Side panel: separate native compatibility, resolve protected conflicts
# explicitly, and stop conflict retry storms / false synced labels.
# ---------------------------------------------------------------------------
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''  getNativeHealth,\n  getProfile,\n  getProfileSyncStatus,\n  saveProfile,''',
    '''  getNativeHealth,\n  getProfile,\n  getProfileSyncStatus,\n  nativeRuntimeCompatibility,\n  resolveProfileSyncConflict,\n  saveProfile,''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''type NativeState =\n  | { status: "checking" }\n  | { status: "unsupported" }\n  | { status: "unavailable"; error: string }\n  | { status: "healthy"; data: NativeRuntimeHealth };''',
    '''type NativeState =\n  | { status: "checking" }\n  | { status: "unsupported" }\n  | { status: "upgrade_required"; data: NativeRuntimeHealth; reason: string }\n  | { status: "unavailable"; error: string }\n  | { status: "healthy"; data: NativeRuntimeHealth };''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''  const [profileSyncStatus, setProfileSyncStatus] = useState<ProfileSyncStatus>(\n    {\n      conflict: null,\n    },\n  );''',
    '''  const [profileSyncStatus, setProfileSyncStatus] = useState<ProfileSyncStatus>(\n    {\n      conflict: null,\n    },\n  );\n  const [profileConflictBusy, setProfileConflictBusy] = useState(false);''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''      const nativeHealth = await getNativeHealth();\n      setNative({ status: "healthy", data: nativeHealth });\n      await refreshAI();''',
    '''      const nativeHealth = await getNativeHealth();\n      const compatibility = nativeRuntimeCompatibility(nativeHealth);\n      if (!compatibility.compatible) {\n        setNative({\n          status: "upgrade_required",\n          data: nativeHealth,\n          reason: compatibility.reason,\n        });\n        return;\n      }\n      setNative({ status: "healthy", data: nativeHealth });\n      await refreshAI();''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''        void saveProfile(profile)\n          .then(() => {\n            if (profileRevision.current !== revision) return;\n            setProfileDirty(false);\n            setSaveState(\n              cloud.status === "connected" && cloud.data.encryptionReady\n                ? "synced"\n                : "local",\n            );\n          })\n          .catch(() => {''',
    '''        void saveProfile(profile)\n          .then(async () => {\n            const status = await getProfileSyncStatus();\n            setProfileSyncStatus(status);\n            if (profileRevision.current !== revision) return;\n            setProfileDirty(false);\n            setSaveState(\n              status.conflict\n                ? "conflict"\n                : cloud.status === "connected" && cloud.data.encryptionReady\n                  ? "synced"\n                  : "local",\n            );\n          })\n          .catch(() => {''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''            void getProfileSyncStatus().then((status) => {\n              setProfileSyncStatus(status);\n              setSaveState(status.conflict ? "conflict" : "error");\n            });\n            retryTimer.current = window.setTimeout(\n              () => setRetryTick((value) => value + 1),\n              5_000,\n            );''',
    '''            void getProfileSyncStatus().then((status) => {\n              setProfileSyncStatus(status);\n              setSaveState(status.conflict ? "conflict" : "error");\n              if (!status.conflict) {\n                retryTimer.current = window.setTimeout(\n                  () => setRetryTick((value) => value + 1),\n                  5_000,\n                );\n              }\n            });''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''  const connectionLabel =\n    health.toLowerCase() !== "healthy"\n      ? "Unavailable"\n      : native.status === "healthy"\n        ? "Connected"\n        : native.status === "checking"\n          ? "Checking"\n          : "Extension ready";''',
    '''  const connectionLabel =\n    health.toLowerCase() !== "healthy"\n      ? "Unavailable"\n      : native.status === "healthy"\n        ? "Connected"\n        : native.status === "upgrade_required"\n          ? "Companion update"\n          : native.status === "checking"\n            ? "Checking"\n            : "Extension ready";''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''  async function syncNow(): Promise<void> {\n    setSaveState("saving");''',
    '''  async function syncNow(): Promise<void> {\n    if (profileSyncStatus.conflict) {\n      setSaveState("conflict");\n      setNotice("Resolve the protected profile conflict before synchronizing.");\n      return;\n    }\n    setSaveState("saving");''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''      await saveProfile(profile);\n      const syncStatus = await getProfileSyncStatus();''',
    '''      await saveProfile(profile);\n      const syncStatus = await getProfileSyncStatus();''',
)
# Add explicit resolver immediately before syncNow.
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''  async function syncNow(): Promise<void> {''',
    '''  async function resolveProfileConflict(\n    winner: "local" | "remote",\n  ): Promise<void> {\n    setProfileConflictBusy(true);\n    setNotice("");\n    try {\n      const resolved = await resolveProfileSyncConflict(winner);\n      setProfile(resolved);\n      setProtectedDrafts({});\n      profileRevision.current += 1;\n      setProfileDirty(false);\n      setProfileSyncStatus({ conflict: null });\n      setSaveState("synced");\n      setNotice(\n        winner === "local"\n          ? "Protected profile conflict resolved using this Mac's confirmed values."\n          : "Protected profile conflict resolved using the encrypted workspace values.",\n      );\n    } catch (error) {\n      setSaveState("conflict");\n      setNotice(\n        error instanceof Error\n          ? error.message\n          : "Protected profile conflict resolution failed",\n      );\n    } finally {\n      setProfileConflictBusy(false);\n    }\n  }\n\n  async function syncNow(): Promise<void> {''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''      {profileSyncStatus.conflict && (\n        <div className="notice review">\n          <strong>Profile review required.</strong>{" "}\n          {profileSyncStatus.conflict.keys.map(profileConflictLabel).join(", ")}\n          {profileSyncStatus.conflict.keys.length === 1\n            ? " differs"\n            : " differ"}\n          {\n            " between this Mac and the encrypted workspace. Open Profile and confirm the intended value; application detection and extension health remain available."\n          }\n        </div>\n      )}''',
    '''      {profileSyncStatus.conflict && (\n        <div className="notice review profile-conflict-banner">\n          <div>\n            <strong>Profile review required.</strong>{" "}\n            {profileSyncStatus.conflict.keys\n              .map(profileConflictLabel)\n              .join(", ")}\n            {profileSyncStatus.conflict.keys.length === 1\n              ? " differs"\n              : " differ"}\n            {" between this Mac and the encrypted workspace."}\n          </div>\n          {view !== "profile" && (\n            <button className="quiet" type="button" onClick={() => setView("profile")}>\n              Review profile\n            </button>\n          )}\n        </div>\n      )}''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''          <p>\n            Regular facts save automatically after you stop typing. Protected\n            facts become confirmed only after you leave the field, and are\n            encrypted before cloud synchronization.\n          </p>\n          {profileSections.map((sectionName) => (''',
    '''          <p>\n            Regular facts save automatically after you stop typing. Protected\n            facts become confirmed only after you leave the field, and are\n            encrypted before cloud synchronization.\n          </p>\n          {profileSyncStatus.conflict && (\n            <div className="profile-conflict-panel">\n              <strong>Choose the authoritative protected value</strong>\n              <p>\n                Both sides contain confirmed protected information, so MUNSHI\n                will not choose automatically. Review every difference below,\n                then explicitly keep one side for all listed conflicts.\n              </p>\n              <div className="profile-conflict-list">\n                {profileSyncStatus.conflict.keys.map((key) => {\n                  const detail = profileSyncStatus.conflict?.details.find(\n                    (candidate) => candidate.key === key,\n                  );\n                  return (\n                    <article key={key}>\n                      <strong>{profileConflictLabel(key)}</strong>\n                      <span>\n                        This Mac: {String(detail?.localValue ?? "(empty)")}\n                      </span>\n                      <span>\n                        Workspace: {String(detail?.remoteValue ?? "(empty)")}\n                      </span>\n                    </article>\n                  );\n                })}\n              </div>\n              <div className="profile-conflict-actions">\n                <button\n                  className="primary"\n                  type="button"\n                  disabled={profileConflictBusy}\n                  onClick={() => void resolveProfileConflict("local")}\n                >\n                  Keep this Mac's values\n                </button>\n                <button\n                  className="quiet"\n                  type="button"\n                  disabled={profileConflictBusy}\n                  onClick={() => void resolveProfileConflict("remote")}\n                >\n                  Use workspace values\n                </button>\n              </div>\n            </div>\n          )}\n          {profileSections.map((sectionName) => (''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''            <span className={saveState === "error" ? "badge review" : "badge"}>\n              {saveLabel}\n            </span>''',
    '''            <span\n              className={\n                saveState === "error" || saveState === "conflict"\n                  ? "badge review"\n                  : "badge"\n              }\n            >\n              {saveLabel}\n            </span>''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''      {view === "ai" && (\n        <AIControlCenter nativeAvailable={native.status === "healthy"} />\n      )}''',
    '''      {view === "ai" && (\n        <AIControlCenter\n          nativeAvailable={native.status === "healthy"}\n          nativeIssue={\n            native.status === "upgrade_required" ? native.reason : undefined\n          }\n        />\n      )}''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''            <div>\n              <dt>Native companion</dt>\n              <dd>{native.status}</dd>\n            </div>''',
    '''            <div>\n              <dt>Native companion</dt>\n              <dd>{native.status}</dd>\n            </div>\n            <div>\n              <dt>Native protocol</dt>\n              <dd>\n                {native.status === "healthy" || native.status === "upgrade_required"\n                  ? (native.data.protocol_version ?? "legacy")\n                  : "not available"}\n              </dd>\n            </div>''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''          {native.status === "unavailable" && (\n            <p className="diagnostic-error">\n              Native connection failed: {native.error}\n            </p>\n          )}''',
    '''          {native.status === "upgrade_required" && (\n            <p className="diagnostic-error">\n              Native companion update required: {native.reason}\n            </p>\n          )}\n          {native.status === "unavailable" && (\n            <p className="diagnostic-error">\n              Native connection failed: {native.error}\n            </p>\n          )}''',
)

# ---------------------------------------------------------------------------
# AI control center: truthful native compatibility state, accurate API-key badge,
# and error styling.
# ---------------------------------------------------------------------------
replace_once(
    "apps/extension/src/sidepanel/AIControlCenter.tsx",
    '''export function AIControlCenter({\n  nativeAvailable,\n}: {\n  nativeAvailable: boolean;\n}) {''',
    '''export function AIControlCenter({\n  nativeAvailable,\n  nativeIssue,\n}: {\n  nativeAvailable: boolean;\n  nativeIssue?: string;\n}) {''',
)
replace_once(
    "apps/extension/src/sidepanel/AIControlCenter.tsx",
    '''  const [message, setMessage] = useState("");''',
    '''  const [message, setMessage] = useState("");\n  const [messageIsError, setMessageIsError] = useState(false);''',
)
# Every error catch uses setMessage; mark errors, and success starts reset.
replace_once(
    "apps/extension/src/sidepanel/AIControlCenter.tsx",
    '''    const next = await getAIControlStatus();\n    setStatus(next);''',
    '''    const next = await getAIControlStatus();\n    setMessageIsError(false);\n    setStatus(next);''',
)
replace_once(
    "apps/extension/src/sidepanel/AIControlCenter.tsx",
    '''    void refresh().catch((error: unknown) => {\n      setMessage(''',
    '''    void refresh().catch((error: unknown) => {\n      setMessageIsError(true);\n      setMessage(''',
)
# Generic catch blocks: add error flag before setMessage. This is deliberately
# scoped to the repeated exact catch shape.
content = read("apps/extension/src/sidepanel/AIControlCenter.tsx")
content = content.replace(
    '''    } catch (error) {\n      setMessage(''',
    '''    } catch (error) {\n      setMessageIsError(true);\n      setMessage(''',
)
# Success messages should clear error tone.
for success in [
    'setMessage(\n        "OpenAI credential stored in macOS Keychain. The saved secret is never displayed by MUNSHI.",\n      );',
    'setMessage("Stored OpenAI credential removed from macOS Keychain.");',
    'setMessage(\n        `OpenAI connection verified. ${connection.modelCount} models are visible to this credential. No generation request was made.`,\n      );',
    'setMessage("AI permissions and spending controls saved locally.");',
]:
    if success not in content:
        raise RuntimeError(f"AI success marker missing: {success[:40]}")
    content = content.replace(success, f"setMessageIsError(false);\n      {success}", 1)
write("apps/extension/src/sidepanel/AIControlCenter.tsx", content)
replace_once(
    "apps/extension/src/sidepanel/AIControlCenter.tsx",
    '''          <strong>Native companion required</strong>\n          <span>\n            API credentials and paid-AI enforcement live in the local native\n            companion. No browser-only fallback stores or uses your API key.\n          </span>''',
    '''          <strong>\n            {nativeIssue ? "Native companion update required" : "Native companion required"}\n          </strong>\n          <span>\n            {nativeIssue ??\n              "API credentials and paid-AI enforcement live in the local native companion. No browser-only fallback stores or uses your API key."}\n          </span>''',
)
replace_once(
    "apps/extension/src/sidepanel/AIControlCenter.tsx",
    '''          {settings.keyConfigured ? "Keychain connected" : "Not connected"}''',
    '''          {settings.keyConfigured ? "Keychain connected" : "API key not configured"}''',
)
replace_once(
    "apps/extension/src/sidepanel/AIControlCenter.tsx",
    '''      {message && <div className="notice">{message}</div>}''',
    '''      {message && (\n        <div className={messageIsError ? "diagnostic-error" : "notice"}>\n          {message}\n        </div>\n      )}''',
)

# ---------------------------------------------------------------------------
# CSS: checkboxes were inheriting full-width text-input styling; conflict UI
# needs explicit review colors and compact layout.
# ---------------------------------------------------------------------------
replace_once(
    "apps/extension/src/sidepanel/styles.css",
    '''.form-grid input,\n.form-grid textarea {''',
    '''.form-grid input:not([type="checkbox"]):not([type="radio"]),\n.form-grid textarea {''',
)
replace_once(
    "apps/extension/src/sidepanel/styles.css",
    '''.form-grid input:focus,\n.form-grid textarea:focus {''',
    '''.form-grid input:not([type="checkbox"]):not([type="radio"]):focus,\n.form-grid textarea:focus {''',
)
append_before(
    "apps/extension/src/sidepanel/styles.css",
    "\n.answer-list {",
    '''\n.profile-conflict-banner {\n  align-items: center;\n  display: flex;\n  gap: 12px;\n  justify-content: space-between;\n}\n\n.profile-conflict-panel {\n  background: #f5e6df;\n  border: 1px solid #e3c0b2;\n  border-radius: 12px;\n  margin: 18px 0 24px;\n  padding: 14px;\n}\n\n.profile-conflict-panel > p {\n  margin: 7px 0 12px;\n}\n\n.profile-conflict-list {\n  display: grid;\n  gap: 8px;\n}\n\n.profile-conflict-list article {\n  background: #fff;\n  border: 1px solid #e3c0b2;\n  border-radius: 9px;\n  display: grid;\n  gap: 4px;\n  padding: 10px;\n}\n\n.profile-conflict-list span {\n  color: #555b63;\n  font-size: 11px;\n  overflow-wrap: anywhere;\n}\n\n.profile-conflict-actions {\n  display: grid;\n  gap: 8px;\n  grid-template-columns: 1fr 1fr;\n  margin-top: 12px;\n}\n\n''',
)
append_before(
    "apps/extension/src/sidepanel/styles.css",
    "\n.resume-select {",
    '''\n.answer-approval input[type="checkbox"],\n.answer-approval input[type="radio"] {\n  accent-color: #b85c38;\n  flex: 0 0 auto;\n  height: 18px;\n  margin: 0;\n  padding: 0;\n  width: 18px;\n}\n\n''',
)

# ---------------------------------------------------------------------------
# Permanent local-update command: updating the extension without reinstalling
# the native package is what caused the protocol split. This updates both.
# ---------------------------------------------------------------------------
write(
    "scripts/update-local-runtime.sh",
    '''#!/usr/bin/env bash\n\nset -euo pipefail\nsource "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"\n\nbranch="${MUNSHI_UPDATE_BRANCH:-feat/v3-foundation-alignment}"\ncd "${REPOSITORY_ROOT}"\n\nif [[ -n "$(git status --porcelain)" ]]; then\n  printf 'STOP: local changes detected; nothing was updated.\\n' >&2\n  git status --short >&2\n  exit 1\nfi\nif [[ "$(git branch --show-current)" != "${branch}" ]]; then\n  printf 'STOP: expected branch %s, found %s.\\n' "${branch}" "$(git branch --show-current)" >&2\n  exit 1\nfi\n\nprintf 'Fetching %s...\\n' "${branch}"\ngit fetch origin "${branch}"\ngit merge --ff-only "origin/${branch}"\n\nprintf 'Installing locked JavaScript dependencies and rebuilding extension...\\n'\nnpm ci\nnpm run build\nnode scripts/verify-artifacts.mjs\n\nruntime_root="$(resolve_runtime_root)"\nnative_python="${runtime_root}/native-host/bin/python"\nnative_launcher="${runtime_root}/native-host/bin/munshi-apply-native"\nif [[ ! -x "${native_python}" || ! -x "${native_launcher}" ]]; then\n  printf 'STOP: native runtime is not installed at %s. Run scripts/install.sh once.\\n' "${runtime_root}" >&2\n  exit 1\nfi\n\nprintf 'Updating native companion in the existing private runtime...\\n'\n"${native_python}" -m pip install --upgrade --force-reinstall "${REPOSITORY_ROOT}/apps/native-host"\n"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" migrate \\\n  --database "${runtime_root}/database/munshi-apply.sqlite" \\\n  --migrations "${REPOSITORY_ROOT}/migrations"\n"${PYTHON_BIN}" "${REPOSITORY_ROOT}/scripts/runtime-ops.py" native-smoke \\\n  --launcher "${native_launcher}" \\\n  --database "${runtime_root}/database/munshi-apply.sqlite" \\\n  --migrations "${REPOSITORY_ROOT}/migrations"\n\nprintf '\\nMUNSHI Apply local runtime updated successfully.\\nHEAD: %s\\nExtension: %s\\n' \\\n  "$(git rev-parse HEAD)" "${REPOSITORY_ROOT}/apps/extension/dist"\n''',
)

write(
    "docs/reports/RUNTIME_COHERENCE_AND_PROFILE_CONFLICT_REPAIR_2026-08-15.md",
    '''# Runtime Coherence and Protected Profile Conflict Repair — 2026-08-15\n\n## Diagnosis\n\nThe Edge extension and installed macOS native companion could drift because the normal local update loop rebuilt only JavaScript artifacts. A legacy native companion could still answer `PING`, causing the extension to report a healthy connection while newer AI messages failed with `Unsupported native message`.\n\nThe protected-profile synchronizer correctly detected conflicting confirmed protected values, but the desktop side panel had no explicit owner resolution path and treated the conflict too much like a transport error. The AI permission checkboxes also inherited full-width text-input CSS.\n\n## Repair\n\n- Native `PING` now advertises protocol version 2 and explicit capabilities.\n- The extension fails closed on native protocol mismatch and labels it `Companion update` instead of calling unsupported native features.\n- `scripts/update-local-runtime.sh` updates both the extension and the installed native Python package, preserves the existing runtime/database, applies migrations, and runs the native smoke test.\n- Confirmed protected profile conflicts remain fail-closed until the owner explicitly chooses either the Mac values or encrypted-workspace values.\n- Conflict saves remain locally durable but no longer enter an automatic retry storm or falsely report synchronized.\n- The Profile UI shows both conflicting values and explicit resolution actions.\n- AI checkbox/radio controls no longer inherit text-field width/padding.\n- AI status distinguishes API-key configuration from MUNSHI/native connectivity, and native errors are rendered as errors rather than success notices.\n\n## Invariants preserved\n\n- No protected value is silently selected.\n- No encrypted history is deleted.\n- No pairing, credential, Keychain item, or database is reset by the code repair.\n- Final submission and security checkpoints remain manual.\n- PR #11 remains draft and unmerged unless separately authorized.\n''',
)

print("runtime coherence patch applied")
