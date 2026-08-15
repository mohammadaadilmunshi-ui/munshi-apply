from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:120]!r}")
    file.write_text(text.replace(old, new, 1))


# Server: expose the authenticated workspace id on sync reads so both clients can
# prove that they are attached to the same workspace.
replace_once(
    "apps/owner-workspace/app/api/sync/events/route.ts",
    '''    return Response.json({\n      events,\n      nextCursor: events.at(-1)?.sequence ?? cursor,\n      hasMore: events.length === 250,\n    });''',
    '''    return Response.json({\n      workspaceId: principal.workspaceId,\n      events,\n      nextCursor: events.at(-1)?.sequence ?? cursor,\n      hasMore: events.length === 250,\n    });''',
)

# Owner workspace vault: fail closed on missing keys with existing history,
# fingerprint the key without exposing it, and paginate the full sync ledger.
replace_once(
    "apps/owner-workspace/app/vault-client.ts",
    '''export async function fetchSyncEvents(cursor = 0): Promise<{\n  events: SyncEvent[];\n  nextCursor: number;\n}> {\n  const response = await fetch(`/api/sync/events?cursor=${cursor}`, {\n    headers: { accept: "application/json" },\n  });\n  const payload = (await response.json()) as {\n    events?: SyncEvent[];\n    nextCursor?: number;\n    error?: string;\n  };\n  if (!response.ok || !payload.events) {\n    throw new Error(payload.error ?? "Cloud synchronization failed.");\n  }\n  return { events: payload.events, nextCursor: payload.nextCursor ?? cursor };\n}\n''',
    '''export function encryptedHistoryNeedsRecovery(input: {\n  hasLocalKey: boolean;\n  eventCount: number;\n  encryptedObjectCount: number;\n}): boolean {\n  return (\n    !input.hasLocalKey &&\n    (input.eventCount > 0 || input.encryptedObjectCount > 0)\n  );\n}\n\nexport async function workspaceKeyFingerprint(rawKey: string): Promise<string> {\n  return (await sha256Hex(validateWorkspaceKey(rawKey))).slice(0, 16);\n}\n\nexport async function fetchSyncEvents(cursor = 0): Promise<{\n  events: SyncEvent[];\n  nextCursor: number;\n  workspaceId: string | null;\n}> {\n  const events: SyncEvent[] = [];\n  let nextCursor = cursor;\n  let workspaceId: string | null = null;\n\n  for (let page = 0; page < 100; page += 1) {\n    const response = await fetch(`/api/sync/events?cursor=${nextCursor}`, {\n      headers: { accept: "application/json" },\n    });\n    const payload = (await response.json()) as {\n      workspaceId?: string;\n      events?: SyncEvent[];\n      nextCursor?: number;\n      hasMore?: boolean;\n      error?: string;\n    };\n    if (!response.ok || !payload.events) {\n      throw new Error(payload.error ?? "Cloud synchronization failed.");\n    }\n    if (payload.workspaceId) {\n      if (workspaceId && workspaceId !== payload.workspaceId) {\n        throw new Error("Cloud workspace identity changed during synchronization.");\n      }\n      workspaceId = payload.workspaceId;\n    }\n    events.push(...payload.events);\n    const candidateCursor = payload.nextCursor ?? nextCursor;\n    if (!payload.hasMore) {\n      return { events, nextCursor: candidateCursor, workspaceId };\n    }\n    if (candidateCursor <= nextCursor) {\n      throw new Error("Cloud synchronization cursor did not advance.");\n    }\n    nextCursor = candidateCursor;\n  }\n\n  throw new Error("Cloud synchronization exceeded the safe pagination limit.");\n}\n''',
)

# Owner workspace compatibility filter: legacy application records must not be
# able to crash workspace/profile synchronization.
replace_once(
    "apps/owner-workspace/app/application-eligibility.ts",
    '''  const knownAts = Boolean(page.atsFamily && page.atsFamily !== "GENERIC");\n  const explicitIntent = hasExplicitIntent(page);\n  const meaningfulQuestions = page.questions.filter(\n    (question) => question.semanticType !== "UNKNOWN",\n  ).length;\n  const specificQuestions = page.questions.filter((question) =>\n    applicationSpecificSemantics.has(question.semanticType),\n  ).length;''',
    '''  const knownAts = Boolean(page.atsFamily && page.atsFamily !== "GENERIC");\n  const explicitIntent = hasExplicitIntent(page);\n  const questions = Array.isArray(page.questions) ? page.questions : [];\n  const meaningfulQuestions = questions.filter(\n    (question) => question.semanticType !== "UNKNOWN",\n  ).length;\n  const specificQuestions = questions.filter((question) =>\n    applicationSpecificSemantics.has(question.semanticType),\n  ).length;''',
)
replace_once(
    "apps/owner-workspace/app/application-eligibility.ts",
    '''  return application.questions.filter(\n    (question) =>\n      question.requiresReview && !approvedQuestionIds.has(question.questionId),\n  ).length;''',
    '''  const questions = Array.isArray(application.questions)\n    ? application.questions\n    : [];\n  return questions.filter(\n    (question) =>\n      question.requiresReview && !approvedQuestionIds.has(question.questionId),\n  ).length;''',
)

# Owner workspace UI/runtime: never mint a replacement key over existing
# encrypted history; auto-pull remote updates while idle; surface workspace/key
# identity and last-sync state.
replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''  decryptLatestEntities,\n  downloadEncryptedResume,\n  ensureWorkspaceKey,\n  fetchSyncEvents,\n  getWorkspaceKey,''',
    '''  decryptLatestEntities,\n  downloadEncryptedResume,\n  encryptedHistoryNeedsRecovery,\n  ensureWorkspaceKey,\n  fetchSyncEvents,\n  getWorkspaceKey,''',
)
replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''  uploadEncryptedResume,\n  type ApplicationReview,''',
    '''  uploadEncryptedResume,\n  workspaceKeyFingerprint,\n  type ApplicationReview,''',
)
replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''type WorkspaceStatus = {\n  devices: number;''',
    '''type WorkspaceStatus = {\n  id: string;\n  devices: number;''',
)
replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''  const [busy, setBusy] = useState(false);\n  const [status, setStatus] = useState("Opening encrypted workspace…");''',
    '''  const [busy, setBusy] = useState(false);\n  const [status, setStatus] = useState("Opening encrypted workspace…");\n  const [vaultFingerprint, setVaultFingerprint] = useState<string | null>(null);\n  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);''',
)

mobile = Path("apps/owner-workspace/app/workspace/mobile-workspace.tsx")
text = mobile.read_text()
start = text.index("  const loadWorkspace = useCallback(async () => {")
end_marker = "  }, []);\n\n  useEffect(() => {"
end = text.index(end_marker, start)
old = text[start:end + len("  }, []);\n")]
new = '''  const loadWorkspace = useCallback(async (quiet = false) => {\n    if (!quiet) setStatus("Synchronizing encrypted workspace…");\n    const existingKey = await getWorkspaceKey();\n    const [workspaceResponse, devicesResponse, sync] = await Promise.all([\n      fetch("/api/workspace", { headers: { accept: "application/json" } }),\n      fetch("/api/devices", { headers: { accept: "application/json" } }),\n      fetchSyncEvents(0),\n    ]);\n    const workspacePayload = (await workspaceResponse.json()) as {\n      workspace?: WorkspaceStatus;\n      error?: string;\n    };\n    const devicesPayload = (await devicesResponse.json()) as {\n      devices?: DeviceRecord[];\n      error?: string;\n    };\n    if (!workspaceResponse.ok || !workspacePayload.workspace) {\n      throw new Error(\n        workspacePayload.error ?? "Workspace status is unavailable.",\n      );\n    }\n    if (!devicesResponse.ok || !devicesPayload.devices) {\n      throw new Error(devicesPayload.error ?? "Device list is unavailable.");\n    }\n    if (sync.workspaceId && sync.workspaceId !== workspacePayload.workspace.id) {\n      throw new Error(\n        "Workspace identity mismatch. Do not save until the Site and Edge pairing are reconciled.",\n      );\n    }\n\n    setWorkspace(workspacePayload.workspace);\n    setDevices(devicesPayload.devices);\n\n    if (\n      encryptedHistoryNeedsRecovery({\n        hasLocalKey: Boolean(existingKey),\n        eventCount: sync.events.length,\n        encryptedObjectCount: workspacePayload.workspace.encryptedObjects,\n      })\n    ) {\n      setRawKey(null);\n      setVaultFingerprint(null);\n      setView("security");\n      throw new Error(\n        "Existing encrypted workspace detected. Restore the recovery key used by your paired Edge installation; MUNSHI will not create a replacement key.",\n      );\n    }\n\n    const key = existingKey ?? (await ensureWorkspaceKey());\n    const fingerprint = await workspaceKeyFingerprint(key);\n    let nextEntities: Map<string, DecryptedEntity>;\n    try {\n      nextEntities = await decryptLatestEntities(key, sync.events);\n    } catch {\n      setRawKey(key);\n      setVaultFingerprint(fingerprint);\n      setView("security");\n      throw new Error(\n        `Encrypted history cannot be opened with vault ${fingerprint}. Restore the recovery key used by the paired Edge installation.`,\n      );\n    }\n    const resumeRecords = await listEncryptedResumes(key);\n    const cloudProfile = nextEntities.get("PROFILE.V1:profile-master") as\n      | DecryptedEntity<unknown>\n      | undefined;\n    const snapshots = Array.from(nextEntities.entries())\n      .filter(([entityKey]) => entityKey.startsWith("APPLICATION.V1:"))\n      .map(([, entity]) => entity.value as ApplicationSnapshot)\n      .filter((application) =>\n        isEligibleApplicationSnapshot(application, window.location.origin),\n      )\n      .sort((left, right) => right.observedAt.localeCompare(left.observedAt));\n\n    setRawKey(key);\n    setVaultFingerprint(fingerprint);\n    setEntities(nextEntities);\n    setResumes(resumeRecords);\n    setApplications(snapshots);\n    setLastSyncAt(new Date().toISOString());\n    if (cloudProfile && !profileDirtyRef.current) {\n      const migrated = migrateLegacyProfileSnapshot(cloudProfile.value);\n      setProfile(migrated.snapshot);\n      setProfileVersion(cloudProfile.version);\n      profileVersionRef.current = cloudProfile.version;\n      profileRevision.current += 1;\n      profileDirtyRef.current = migrated.migrated;\n      setProfileDirty(migrated.migrated);\n      setProtectedDrafts({});\n      setRetryTick(0);\n      setStatus(\n        migrated.migrated\n          ? "Legacy profile upgraded; encrypted synchronization pending"\n          : "Encrypted workspace synchronized",\n      );\n    } else if (!cloudProfile && !profileDirtyRef.current) {\n      setProfileVersion(0);\n      profileVersionRef.current = 0;\n      setStatus("Encrypted workspace synchronized");\n    } else if (!quiet) {\n      setStatus(\n        "Workspace refreshed; local profile edits are still waiting to synchronize",\n      );\n    }\n  }, []);\n'''
mobile.write_text(text[:start] + new + text[end + len("  }, []);\n"):])

replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''  useEffect(\n    () => () => {\n      if (retryTimer.current !== null) window.clearTimeout(retryTimer.current);\n    },\n    [],\n  );\n\n  useEffect(() => {\n    if (!rawKey || !profileDirty || protectedConflicts.length > 0) {''',
    '''  useEffect(\n    () => () => {\n      if (retryTimer.current !== null) window.clearTimeout(retryTimer.current);\n    },\n    [],\n  );\n\n  useEffect(() => {\n    if (\n      !rawKey ||\n      profileDirty ||\n      Object.keys(protectedDrafts).length > 0 ||\n      protectedConflicts.length > 0\n    ) {\n      return;\n    }\n    let cancelled = false;\n    const pull = () => {\n      if (\n        cancelled ||\n        document.visibilityState !== "visible" ||\n        profileSaveInFlight.current\n      ) {\n        return;\n      }\n      void loadWorkspace(true).catch((error: unknown) => {\n        setStatus(\n          error instanceof Error ? error.message : "Workspace synchronization failed",\n        );\n      });\n    };\n    const interval = window.setInterval(pull, 15_000);\n    const onFocus = () => pull();\n    const onVisibility = () => {\n      if (document.visibilityState === "visible") pull();\n    };\n    window.addEventListener("focus", onFocus);\n    document.addEventListener("visibilitychange", onVisibility);\n    return () => {\n      cancelled = true;\n      window.clearInterval(interval);\n      window.removeEventListener("focus", onFocus);\n      document.removeEventListener("visibilitychange", onVisibility);\n    };\n  }, [\n    loadWorkspace,\n    profileDirty,\n    protectedConflicts.length,\n    protectedDrafts,\n    rawKey,\n  ]);\n\n  useEffect(() => {\n    if (!rawKey || !profileDirty || protectedConflicts.length > 0) {''',
)
replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''              setRetryTick(0);\n              setStatus("Profile encrypted and synchronized");''',
    '''              setRetryTick(0);\n              setLastSyncAt(new Date().toISOString());\n              setStatus("Profile encrypted and synchronized");''',
)
replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''    if (profileDirty) {\n      setRetryTick((value) => value + 1);''',
    '''    if (profileDirtyRef.current) {\n      setRetryTick((value) => value + 1);''',
)
replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''                  <span>\n                    Cloud version {profileVersion} ·{" "}\n                    {profileDirty ? "changes pending" : "synchronized"}\n                  </span>''',
    '''                  <span>\n                    Cloud version {profileVersion} ·{" "}\n                    {profileDirty ? "changes pending" : "synchronized"}\n                  </span>\n                  <span>\n                    Workspace {workspace?.id.slice(0, 8) ?? "—"} · vault{" "}\n                    {vaultFingerprint ?? "locked"} · last sync{" "}\n                    {lastSyncAt ? new Date(lastSyncAt).toLocaleTimeString() : "never"}\n                  </span>''',
)
replace_once(
    "apps/owner-workspace/app/workspace/mobile-workspace.tsx",
    '''              <p>\n                This recovery key decrypts your synchronized profile and\n                résumés. MUNSHI’s server cannot recover it for you.\n              </p>''',
    '''              <p>\n                This recovery key decrypts your synchronized profile and\n                résumés. MUNSHI’s server cannot recover it for you.\n              </p>\n              <p>\n                Workspace {workspace?.id ?? "unknown"} · vault{" "}\n                {vaultFingerprint ?? "not unlocked"}\n              </p>''',
)

# Extension cloud client: identify workspace/key and consume all sync pages.
replace_once(
    "apps/extension/src/storage/cloud.ts",
    '''export type CloudHealth = {\n  connected: true;\n  baseUrl: string;\n  deviceId: string;\n  nextCursor: number;\n  encryptionReady: boolean;\n};''',
    '''export type CloudHealth = {\n  connected: true;\n  baseUrl: string;\n  deviceId: string;\n  workspaceId: string | null;\n  vaultFingerprint: string | null;\n  nextCursor: number;\n  encryptionReady: boolean;\n};''',
)
replace_once(
    "apps/extension/src/storage/cloud.ts",
    '''export type CloudSnapshot = {\n  profile: ProfileSnapshot | null;\n  profileVersion: number;\n  applications: ApplicationPage[];\n  reviews: ApplicationReview[];\n  resumes: ResumeRecord[];\n  nextCursor: number;\n};''',
    '''export type CloudSnapshot = {\n  profile: ProfileSnapshot | null;\n  profileVersion: number;\n  applications: ApplicationPage[];\n  reviews: ApplicationReview[];\n  resumes: ResumeRecord[];\n  nextCursor: number;\n  workspaceId: string | null;\n};''',
)
replace_once(
    "apps/extension/src/storage/cloud.ts",
    '''    const payload = (await response.json()) as {\n      nextCursor?: number;\n      error?: string;\n    };''',
    '''    const payload = (await response.json()) as {\n      workspaceId?: string;\n      nextCursor?: number;\n      error?: string;\n    };''',
)
replace_once(
    "apps/extension/src/storage/cloud.ts",
    '''    return {\n      connected: true,\n      baseUrl: connection.baseUrl,\n      deviceId: connection.deviceId,\n      nextCursor: payload.nextCursor ?? 0,\n      encryptionReady: await isCloudEncryptionReady(),\n    };''',
    '''    const rawKey = await getWorkspaceEncryptionKey();\n    return {\n      connected: true,\n      baseUrl: connection.baseUrl,\n      deviceId: connection.deviceId,\n      workspaceId: payload.workspaceId ?? null,\n      vaultFingerprint: rawKey ? (await sha256Hex(rawKey)).slice(0, 16) : null,\n      nextCursor: payload.nextCursor ?? 0,\n      encryptionReady: rawKey !== null,\n    };''',
)
replace_once(
    "apps/extension/src/storage/cloud.ts",
    '''export async function fetchCloudEvents(\n  connection: CloudConnection,\n  cursor = 0,\n): Promise<{ events: CloudSyncEvent[]; nextCursor: number }> {\n  const response = await fetch(\n    `${connection.baseUrl}/api/sync/events?cursor=${cursor}`,\n    {\n      headers: {\n        accept: "application/json",\n        authorization: `Bearer ${connection.credential}`,\n      },\n    },\n  );\n  const payload = (await response.json()) as {\n    events?: CloudSyncEvent[];\n    nextCursor?: number;\n    error?: string;\n  };\n  if (!response.ok || !payload.events) {\n    throw new Error(payload.error ?? "Cloud event download failed");\n  }\n  return { events: payload.events, nextCursor: payload.nextCursor ?? cursor };\n}\n''',
    '''export async function fetchCloudEvents(\n  connection: CloudConnection,\n  cursor = 0,\n): Promise<{\n  events: CloudSyncEvent[];\n  nextCursor: number;\n  workspaceId: string | null;\n}> {\n  const events: CloudSyncEvent[] = [];\n  let nextCursor = cursor;\n  let workspaceId: string | null = null;\n\n  for (let page = 0; page < 100; page += 1) {\n    const response = await fetch(\n      `${connection.baseUrl}/api/sync/events?cursor=${nextCursor}`,\n      {\n        headers: {\n          accept: "application/json",\n          authorization: `Bearer ${connection.credential}`,\n        },\n      },\n    );\n    const payload = (await response.json()) as {\n      workspaceId?: string;\n      events?: CloudSyncEvent[];\n      nextCursor?: number;\n      hasMore?: boolean;\n      error?: string;\n    };\n    if (!response.ok || !payload.events) {\n      throw new Error(payload.error ?? "Cloud event download failed");\n    }\n    if (payload.workspaceId) {\n      if (workspaceId && workspaceId !== payload.workspaceId) {\n        throw new Error("Cloud workspace identity changed during synchronization");\n      }\n      workspaceId = payload.workspaceId;\n    }\n    events.push(...payload.events);\n    const candidateCursor = payload.nextCursor ?? nextCursor;\n    if (!payload.hasMore) {\n      return { events, nextCursor: candidateCursor, workspaceId };\n    }\n    if (candidateCursor <= nextCursor) {\n      throw new Error("Cloud synchronization cursor did not advance");\n    }\n    nextCursor = candidateCursor;\n  }\n\n  throw new Error("Cloud synchronization exceeded the safe pagination limit");\n}\n''',
)
replace_once(
    "apps/extension/src/storage/cloud.ts",
    '''  const { events, nextCursor } = await fetchCloudEvents(connection, 0);''',
    '''  const { events, nextCursor, workspaceId } = await fetchCloudEvents(\n    connection,\n    0,\n  );''',
)
replace_once(
    "apps/extension/src/storage/cloud.ts",
    '''    resumes,\n    nextCursor,\n  };''',
    '''    resumes,\n    nextCursor,\n    workspaceId,\n  };''',
)

# Extension side panel: getProfile() is the authoritative reconciliation path.
# Do not overwrite it with raw cloud state, and continuously pull while idle.
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''  const [autoPilotStatus, setAutoPilotStatus] =\n    useState<AutoPilotControllerStatus | null>(null);''',
    '''  const [autoPilotStatus, setAutoPilotStatus] =\n    useState<AutoPilotControllerStatus | null>(null);\n  const [lastCloudPullAt, setLastCloudPullAt] = useState<string | null>(null);''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''          const snapshot = await getCloudSnapshot(connection);\n          setCloudSnapshot(snapshot);\n          if (snapshot.profile) setProfile(snapshot.profile);\n          setSelectedResumeId(''',
    '''          const snapshot = await getCloudSnapshot(connection);\n          setCloudSnapshot(snapshot);\n          setLastCloudPullAt(now());\n          setSelectedResumeId(''',
)

app = Path("apps/extension/src/sidepanel/App.tsx")
text = app.read_text()
anchor = '''  }, [refreshAI]);\n\n  useEffect(() => {\n    void refresh().catch((error: unknown) => {'''
if anchor not in text:
    raise SystemExit("App refresh insertion anchor missing")
pull_code = '''  }, [refreshAI]);\n\n  const pullCloudChanges = useCallback(async () => {\n    if (profileDirty || Object.keys(protectedDrafts).length > 0) return;\n    const connection = await getCloudConnection();\n    if (!connection) return;\n    const cloudHealth = await getCloudHealth(connection);\n    setCloud({ status: "connected", data: cloudHealth });\n    if (!cloudHealth.encryptionReady) return;\n    const [syncedProfile, snapshot] = await Promise.all([\n      getProfile(),\n      getCloudSnapshot(connection),\n    ]);\n    setCloudSnapshot(snapshot);\n    if (syncedProfile) {\n      setProfile(syncedProfile);\n      profileRevision.current += 1;\n      setSaveState("synced");\n    }\n    setLastCloudPullAt(now());\n  }, [profileDirty, protectedDrafts]);\n\n  useEffect(() => {\n    void refresh().catch((error: unknown) => {'''
text = text.replace(anchor, pull_code, 1)
app.write_text(text)

replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''  }, [refresh]);\n\n  useEffect(() => {\n    if (!profileLoaded || !profileDirty) return;''',
    '''  }, [refresh]);\n\n  useEffect(() => {\n    let cancelled = false;\n    const pull = () => {\n      if (cancelled || document.visibilityState !== "visible") return;\n      void pullCloudChanges().catch((error: unknown) => {\n        setNotice(\n          error instanceof Error ? error.message : "Cloud profile refresh failed",\n        );\n      });\n    };\n    const interval = window.setInterval(pull, 15_000);\n    const onFocus = () => pull();\n    const onVisibility = () => {\n      if (document.visibilityState === "visible") pull();\n    };\n    window.addEventListener("focus", onFocus);\n    document.addEventListener("visibilitychange", onVisibility);\n    return () => {\n      cancelled = true;\n      window.clearInterval(interval);\n      window.removeEventListener("focus", onFocus);\n      document.removeEventListener("visibilitychange", onVisibility);\n    };\n  }, [pullCloudChanges]);\n\n  useEffect(() => {\n    if (!profileLoaded || !profileDirty) return;''',
)
replace_once(
    "apps/extension/src/sidepanel/App.tsx",
    '''            <div>\n              <dt>Cloud synchronization</dt>\n              <dd>\n                {cloud.status === "connected"\n                  ? cloud.data.encryptionReady\n                    ? "encrypted"\n                    : "paired only"\n                  : cloud.status}\n              </dd>\n            </div>''',
    '''            <div>\n              <dt>Cloud synchronization</dt>\n              <dd>\n                {cloud.status === "connected"\n                  ? cloud.data.encryptionReady\n                    ? "encrypted"\n                    : "paired only"\n                  : cloud.status}\n              </dd>\n            </div>\n            <div>\n              <dt>Cloud workspace</dt>\n              <dd>\n                {cloud.status === "connected"\n                  ? cloud.data.workspaceId ?? "unknown"\n                  : "not connected"}\n              </dd>\n            </div>\n            <div>\n              <dt>Vault fingerprint</dt>\n              <dd>\n                {cloud.status === "connected"\n                  ? cloud.data.vaultFingerprint ?? "not unlocked"\n                  : "not connected"}\n              </dd>\n            </div>\n            <div>\n              <dt>Last cloud pull</dt>\n              <dd>\n                {lastCloudPullAt\n                  ? new Date(lastCloudPullAt).toLocaleTimeString()\n                  : "not yet"}\n              </dd>\n            </div>''',
)

# Extension pagination regression test.
replace_once(
    "apps/extension/src/storage/cloud.test.ts",
    '''  normalizeBaseUrl,\n  parsePairingBundle,\n  validateResumeFile,''',
    '''  fetchCloudEvents,\n  normalizeBaseUrl,\n  parsePairingBundle,\n  validateResumeFile,''',
)
cloud_test = Path("apps/extension/src/storage/cloud.test.ts")
text = cloud_test.read_text()
insert = '''\n\ndescribe("cloud event pagination", () => {\n  it("downloads every sync page and preserves workspace identity", async () => {\n    const originalFetch = globalThis.fetch;\n    const cursors: string[] = [];\n    globalThis.fetch = async (input) => {\n      const url = String(input);\n      cursors.push(new URL(url).searchParams.get("cursor") ?? "");\n      if (url.endsWith("cursor=0")) {\n        return Response.json({\n          workspaceId: "workspace-test",\n          events: [{ sequence: 250 }],\n          nextCursor: 250,\n          hasMore: true,\n        });\n      }\n      return Response.json({\n        workspaceId: "workspace-test",\n        events: [{ sequence: 251 }],\n        nextCursor: 251,\n        hasMore: false,\n      });\n    };\n    try {\n      const result = await fetchCloudEvents(\n        {\n          baseUrl: "https://workspace.example",\n          deviceId: "device-test",\n          credential: "credential-test",\n          platform: "macos-edge",\n          connectedAt: "2026-08-15T00:00:00.000Z",\n        },\n        0,\n      );\n      expect(cursors).toEqual(["0", "250"]);\n      expect(result.events).toHaveLength(2);\n      expect(result.nextCursor).toBe(251);\n      expect(result.workspaceId).toBe("workspace-test");\n    } finally {\n      globalThis.fetch = originalFetch;\n    }\n  });\n});\n'''
cloud_test.write_text(text + insert)

# Owner workspace regression tests for recovery gating, pagination, and legacy
# application compatibility.
replace_once(
    "apps/owner-workspace/tests/profile-vault.test.mjs",
    '''  ProtectedProfileConflictError,\n  migrateLegacyProfileSnapshot,\n  parseProfileSnapshot,\n  putEncryptedEntity,''',
    '''  ProtectedProfileConflictError,\n  encryptedHistoryNeedsRecovery,\n  fetchSyncEvents,\n  migrateLegacyProfileSnapshot,\n  parseProfileSnapshot,\n  putEncryptedEntity,''',
)
owner_test = Path("apps/owner-workspace/tests/profile-vault.test.mjs")
text = owner_test.read_text()
text += '''\n\ntest("existing encrypted history requires recovery instead of minting a new key", () => {\n  assert.equal(\n    encryptedHistoryNeedsRecovery({\n      hasLocalKey: false,\n      eventCount: 1,\n      encryptedObjectCount: 0,\n    }),\n    true,\n  );\n  assert.equal(\n    encryptedHistoryNeedsRecovery({\n      hasLocalKey: false,\n      eventCount: 0,\n      encryptedObjectCount: 0,\n    }),\n    false,\n  );\n  assert.equal(\n    encryptedHistoryNeedsRecovery({\n      hasLocalKey: true,\n      eventCount: 20,\n      encryptedObjectCount: 4,\n    }),\n    false,\n  );\n});\n\ntest("owner workspace downloads every sync event page", async () => {\n  const originalFetch = globalThis.fetch;\n  const cursors = [];\n  globalThis.fetch = async (input) => {\n    const url = String(input);\n    const cursor = new URL(url, "https://workspace.example").searchParams.get(\n      "cursor",\n    );\n    cursors.push(cursor);\n    if (cursor === "0") {\n      return Response.json({\n        workspaceId: "workspace-test",\n        events: [{ sequence: 250 }],\n        nextCursor: 250,\n        hasMore: true,\n      });\n    }\n    return Response.json({\n      workspaceId: "workspace-test",\n      events: [{ sequence: 251 }],\n      nextCursor: 251,\n      hasMore: false,\n    });\n  };\n  try {\n    const result = await fetchSyncEvents(0);\n    assert.deepEqual(cursors, ["0", "250"]);\n    assert.equal(result.events.length, 2);\n    assert.equal(result.nextCursor, 251);\n    assert.equal(result.workspaceId, "workspace-test");\n  } finally {\n    globalThis.fetch = originalFetch;\n  }\n});\n'''
owner_test.write_text(text)

eligibility_test = Path("apps/owner-workspace/tests/application-eligibility.test.mjs")
text = eligibility_test.read_text()
text += '''\n\ntest("legacy snapshots with missing questions fail closed instead of crashing sync", () => {\n  const legacy = snapshot({ url: "https://help.openai.com/legacy" });\n  delete legacy.questions;\n  assert.equal(isEligibleApplicationSnapshot(legacy), false);\n  assert.equal(pendingReviewCount(legacy), 0);\n});\n'''
eligibility_test.write_text(text)
