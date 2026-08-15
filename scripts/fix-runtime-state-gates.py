from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:80]!r}")
    file.write_text(text.replace(old, new, 1))


# Contracts: expose profile sync conflict status without turning a profile read into a fatal runtime error.
replace_once(
    "packages/contracts/src/index.ts",
    '''  | { type: "GET_PROFILE" }\n  | { type: "SAVE_PROFILE"; payload: MasterProfile }''',
    '''  | { type: "GET_PROFILE" }\n  | { type: "GET_PROFILE_SYNC_STATUS" }\n  | { type: "SAVE_PROFILE"; payload: MasterProfile }''',
)

# Extension client: typed access to the separate sync-review state.
client = "apps/extension/src/messaging/client.ts"
replace_once(
    client,
    '''export type AutoPilotResumePayload = {\n  preflight: PreflightGateSummary;\n  fillInstructions: readonly FillInstruction[];\n};\n''',
    '''export type AutoPilotResumePayload = {\n  preflight: PreflightGateSummary;\n  fillInstructions: readonly FillInstruction[];\n};\n\nexport type ProfileSyncStatus = {\n  conflict: {\n    keys: string[];\n    detectedAt: string;\n  } | null;\n};\n''',
)
replace_once(
    client,
    '''export async function getProfile(): Promise<ProfileSnapshot | null> {\n  const candidate = await send({ type: "GET_PROFILE" });\n  return candidate === null ? null : parseProfileSnapshot(candidate);\n}\n\nexport function saveProfile(profile: ProfileSnapshot): Promise<void> {''',
    '''export async function getProfile(): Promise<ProfileSnapshot | null> {\n  const candidate = await send({ type: "GET_PROFILE" });\n  return candidate === null ? null : parseProfileSnapshot(candidate);\n}\n\nexport async function getProfileSyncStatus(): Promise<ProfileSyncStatus> {\n  return (await send({ type: "GET_PROFILE_SYNC_STATUS" })) as ProfileSyncStatus;\n}\n\nexport function saveProfile(profile: ProfileSnapshot): Promise<void> {''',
)

# Service worker: enforce the existing application eligibility gate before exposing/cloud-publishing pages,
# and separate profile conflicts from extension health.
worker = "apps/extension/src/background/service-worker.ts"
replace_once(
    worker,
    '''import type { PreflightGateSummary } from "@munshi-apply/application-model";''',
    '''import {\n  isEligibleApplicationPage,\n  type PreflightGateSummary,\n} from "@munshi-apply/application-model";''',
)
replace_once(
    worker,
    '''  deletePage,\n  getLatestPage,\n  getPage,''',
    '''  deletePage,\n  getPage,''',
)
replace_once(
    worker,
    '''let initialized = false;\n''',
    '''let initialized = false;\nlet profileSyncConflict: { keys: string[]; detectedAt: string } | null = null;\n\nfunction rememberProfileConflict(error: ProtectedProfileConflictError): void {\n  profileSyncConflict = {\n    keys: [...error.keys],\n    detectedAt: new Date().toISOString(),\n  };\n}\n''',
)
replace_once(
    worker,
    '''async function getActivePage(): Promise<unknown> {\n  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });\n  if (tab?.id !== undefined && /^https?:\\/\\//.test(tab.url ?? "")) {\n    const activePage = await getMergedPageForTab(tab.id);\n    if (activePage) return activePage;\n  }\n  return getLatestPage();\n}\n''',
    '''async function getActivePage(): Promise<unknown> {\n  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });\n  if (tab?.id === undefined || !/^https?:\\/\\//.test(tab.url ?? "")) return null;\n  const activePage = await getMergedPageForTab(tab.id);\n  return activePage && isEligibleApplicationPage(activePage) ? activePage : null;\n}\n''',
)
replace_once(
    worker,
    '''            if (localProfile) {\n              localProfile = await synchronizeProtectedProfile(\n                connection,\n                localProfile,\n              );\n            } else {\n              localProfile = (await getCloudSnapshot(connection)).profile;\n            }\n            if (localProfile) {\n              await persistAuthoritativeProfileSnapshot(localProfile);\n            }\n          } catch (error) {\n            if (error instanceof ProtectedProfileConflictError) throw error;\n            // Local-first operation continues when cloud is temporarily unavailable.\n          }\n        }\n        return { ok: true, data: localProfile };\n      }\n      case "SAVE_PROFILE": {\n        const parsed = parseProfileSnapshot(request.payload);\n        await persistAuthoritativeProfileSnapshot(parsed);\n        const connection = await getCloudConnection();\n        if (connection && (await isCloudEncryptionReady())) {\n          const synchronized = await synchronizeProtectedProfile(\n            connection,\n            parsed,\n          );\n          await persistAuthoritativeProfileSnapshot(synchronized);\n          if (!sameProfileSaveContent(synchronized, parsed)) {\n            throw new Error(\n              "Profile content changed on another device. Refresh before saving again.",\n            );\n          }\n        }\n        return { ok: true };\n      }''',
    '''            if (localProfile) {\n              localProfile = await synchronizeProtectedProfile(\n                connection,\n                localProfile,\n              );\n            } else {\n              localProfile = (await getCloudSnapshot(connection)).profile;\n            }\n            if (localProfile) {\n              await persistAuthoritativeProfileSnapshot(localProfile);\n            }\n            profileSyncConflict = null;\n          } catch (error) {\n            if (error instanceof ProtectedProfileConflictError) {\n              rememberProfileConflict(error);\n            }\n            // Local-first operation continues when cloud is unavailable or review is required.\n          }\n        }\n        return { ok: true, data: localProfile };\n      }\n      case "GET_PROFILE_SYNC_STATUS":\n        return { ok: true, data: { conflict: profileSyncConflict } };\n      case "SAVE_PROFILE": {\n        const parsed = parseProfileSnapshot(request.payload);\n        await persistAuthoritativeProfileSnapshot(parsed);\n        const connection = await getCloudConnection();\n        if (connection && (await isCloudEncryptionReady())) {\n          try {\n            const synchronized = await synchronizeProtectedProfile(\n              connection,\n              parsed,\n            );\n            await persistAuthoritativeProfileSnapshot(synchronized);\n            if (!sameProfileSaveContent(synchronized, parsed)) {\n              throw new Error(\n                "Profile content changed on another device. Refresh before saving again.",\n              );\n            }\n            profileSyncConflict = null;\n          } catch (error) {\n            if (error instanceof ProtectedProfileConflictError) {\n              rememberProfileConflict(error);\n            }\n            throw error;\n          }\n        }\n        return { ok: true };\n      }''',
)
replace_once(
    worker,
    '''        const mergedPage = await getMergedPageForTab(tabId);\n        const activePage = mergedPage ?? page;\n        const connection = await getCloudConnection();\n        if (connection && (await isCloudEncryptionReady())) {\n          try {\n            await publishApplicationSnapshot(connection, activePage);\n          } catch {\n            // Page discovery remains local-first and retries on the next scan.\n          }\n        }\n        try {\n          await chrome.runtime.sendMessage({\n            type: "ACTIVE_PAGE_UPDATED",\n            payload: activePage,\n          });\n        } catch {\n          // The side panel is optional and may be closed while the sensor is active.\n        }\n        await autoPilotController.onPageSnapshot(tabId, activePage);''',
    '''        const mergedPage = await getMergedPageForTab(tabId);\n        const activePage = mergedPage ?? page;\n        const eligible = isEligibleApplicationPage(activePage);\n        const connection = await getCloudConnection();\n        if (eligible && connection && (await isCloudEncryptionReady())) {\n          try {\n            await publishApplicationSnapshot(connection, activePage);\n          } catch {\n            // Page discovery remains local-first and retries on the next scan.\n          }\n        }\n        try {\n          await chrome.runtime.sendMessage(\n            eligible\n              ? { type: "ACTIVE_PAGE_UPDATED", payload: activePage }\n              : { type: "ACTIVE_PAGE_CLEARED" },\n          );\n        } catch {\n          // The side panel is optional and may be closed while the sensor is active.\n        }\n        await autoPilotController.onPageSnapshot(tabId, activePage);''',
)

# Side panel: health is independent from profile-review state, stale/non-application pages clear,
# and profile conflicts get their own review indicator instead of masquerading as an outage.
app = "apps/extension/src/sidepanel/App.tsx"
replace_once(
    app,
    '''  getNativeHealth,\n  getProfile,\n  saveProfile,\n  type AutoPilotControllerStatus,\n  type ExtensionRuntimeHealth,\n  type NativeRuntimeHealth,''',
    '''  getNativeHealth,\n  getProfile,\n  getProfileSyncStatus,\n  saveProfile,\n  type AutoPilotControllerStatus,\n  type ExtensionRuntimeHealth,\n  type NativeRuntimeHealth,\n  type ProfileSyncStatus,''',
)
replace_once(
    app,
    '''type SaveState = "idle" | "editing" | "saving" | "synced" | "local" | "error";''',
    '''type SaveState =\n  | "idle"\n  | "editing"\n  | "saving"\n  | "synced"\n  | "local"\n  | "conflict"\n  | "error";''',
)
replace_once(
    app,
    '''function sameOrigin(left: string, right: string): boolean {\n  try {\n    return new URL(left).origin === new URL(right).origin;\n  } catch {\n    return false;\n  }\n}\n''',
    '''function sameOrigin(left: string, right: string): boolean {\n  try {\n    return new URL(left).origin === new URL(right).origin;\n  } catch {\n    return false;\n  }\n}\n\nfunction profileConflictLabel(key: string): string {\n  const field = fieldDefinition(key);\n  if (field) return field.label;\n  if (key.startsWith("record:")) {\n    return key.split(":").at(-1)?.replaceAll("_", " ") ?? key;\n  }\n  return key.replaceAll("_", " ");\n}\n''',
)
replace_once(
    app,
    '''  const [cloud, setCloud] = useState<CloudState>({ status: "checking" });\n  const [workspaceUrl, setWorkspaceUrl] = useState(defaultWorkspaceUrl);''',
    '''  const [cloud, setCloud] = useState<CloudState>({ status: "checking" });\n  const [profileSyncStatus, setProfileSyncStatus] = useState<ProfileSyncStatus>({\n    conflict: null,\n  });\n  const [workspaceUrl, setWorkspaceUrl] = useState(defaultWorkspaceUrl);''',
)
replace_once(
    app,
    '''  const refresh = useCallback(async () => {\n    const [activePage, savedProfile, extensionRuntime] = await Promise.all([\n      getActivePage(),\n      getProfile(),\n      getHealth(),\n    ]);\n    setPage(activePage);\n    if (savedProfile) setProfile(savedProfile);\n    setProtectedDrafts({});\n    profileRevision.current += 1;\n    setProfileLoaded(true);\n    setProfileDirty(false);\n    setSaveState("idle");\n    setHealth(extensionRuntime.status);\n    setRuntime(extensionRuntime);\n''',
    '''  const refresh = useCallback(async () => {\n    const [activePage, extensionRuntime] = await Promise.all([\n      getActivePage(),\n      getHealth(),\n    ]);\n    setPage(activePage);\n    setHealth(extensionRuntime.status);\n    setRuntime(extensionRuntime);\n\n    let savedProfile: ProfileSnapshot | null = null;\n    try {\n      savedProfile = await getProfile();\n    } catch (error) {\n      setNotice(\n        error instanceof Error ? error.message : "Unable to load profile",\n      );\n    }\n    const syncStatus = await getProfileSyncStatus().catch(() => ({\n      conflict: null,\n    }));\n    setProfileSyncStatus(syncStatus);\n    if (savedProfile) setProfile(savedProfile);\n    setProtectedDrafts({});\n    profileRevision.current += 1;\n    setProfileLoaded(true);\n    setProfileDirty(false);\n    setSaveState(syncStatus.conflict ? "conflict" : "idle");\n''',
)
replace_once(
    app,
    '''    const listener = (message: {\n      type?: string;\n      payload?: ApplicationPage;\n    }) => {\n      if (message.type === "ACTIVE_PAGE_UPDATED" && message.payload)\n        setPage(message.payload);\n    };''',
    '''    const listener = (message: {\n      type?: string;\n      payload?: ApplicationPage | null;\n    }) => {\n      if (message.type === "ACTIVE_PAGE_UPDATED" && message.payload) {\n        setPage(message.payload);\n      } else if (message.type === "ACTIVE_PAGE_CLEARED") {\n        setPage(null);\n      }\n    };''',
)
replace_once(
    app,
    '''    const [syncedProfile, snapshot] = await Promise.all([\n      getProfile(),\n      getCloudSnapshot(connection),\n    ]);\n    setCloudSnapshot(snapshot);\n    if (syncedProfile) {\n      setProfile(syncedProfile);\n      profileRevision.current += 1;\n      setSaveState("synced");\n    }\n    setLastCloudPullAt(now());''',
    '''    const syncedProfile = await getProfile();\n    const syncStatus = await getProfileSyncStatus();\n    const snapshot = await getCloudSnapshot(connection);\n    setCloudSnapshot(snapshot);\n    setProfileSyncStatus(syncStatus);\n    if (syncedProfile) {\n      setProfile(syncedProfile);\n      profileRevision.current += 1;\n      setSaveState(syncStatus.conflict ? "conflict" : "synced");\n    }\n    setLastCloudPullAt(now());''',
)
replace_once(
    app,
    '''          .catch(() => {\n            setSaveState("error");\n            retryTimer.current = window.setTimeout(\n              () => setRetryTick((value) => value + 1),\n              5_000,\n            );\n          });''',
    '''          .catch(() => {\n            void getProfileSyncStatus().then((status) => {\n              setProfileSyncStatus(status);\n              setSaveState(status.conflict ? "conflict" : "error");\n            });\n            retryTimer.current = window.setTimeout(\n              () => setRetryTick((value) => value + 1),\n              5_000,\n            );\n          });''',
)
replace_once(
    app,
    '''          : saveState === "local"\n            ? "Saved locally"\n            : saveState === "error"\n              ? "Waiting to sync"''',
    '''          : saveState === "local"\n            ? "Saved locally"\n            : saveState === "conflict"\n              ? "Profile review required"\n              : saveState === "error"\n                ? "Waiting to sync"''',
)
replace_once(
    app,
    '''      await saveProfile(profile);\n      if (profileRevision.current === revision) {\n        setProfileDirty(false);\n        setSaveState(\n          cloud.status === "connected" && cloud.data.encryptionReady\n            ? "synced"\n            : "local",\n        );\n      }\n    } catch (error) {\n      setSaveState("error");\n      setNotice(error instanceof Error ? error.message : "Profile sync failed");\n    }''',
    '''      await saveProfile(profile);\n      const syncStatus = await getProfileSyncStatus();\n      setProfileSyncStatus(syncStatus);\n      if (profileRevision.current === revision) {\n        setProfileDirty(false);\n        setSaveState(\n          syncStatus.conflict\n            ? "conflict"\n            : cloud.status === "connected" && cloud.data.encryptionReady\n              ? "synced"\n              : "local",\n        );\n      }\n    } catch (error) {\n      const syncStatus = await getProfileSyncStatus().catch(() => ({\n        conflict: null,\n      }));\n      setProfileSyncStatus(syncStatus);\n      setSaveState(syncStatus.conflict ? "conflict" : "error");\n      if (!syncStatus.conflict) {\n        setNotice(error instanceof Error ? error.message : "Profile sync failed");\n      }\n    }''',
)
replace_once(
    app,
    '''      {notice && <div className="notice">{notice}</div>}\n\n      {view === "application" && (''',
    '''      {profileSyncStatus.conflict && (\n        <div className="notice review">\n          <strong>Profile review required.</strong>{" "}\n          {profileSyncStatus.conflict.keys.map(profileConflictLabel).join(", ")}\n          {profileSyncStatus.conflict.keys.length === 1 ? " differs" : " differ"}\n          {" between this Mac and the encrypted workspace. Open Profile and confirm the intended value; application detection and extension health remain available."}\n        </div>\n      )}\n      {notice && <div className="notice">{notice}</div>}\n\n      {view === "application" && (''',
)

# Styling: conflicts are review state, not healthy/success banners.
replace_once(
    "apps/extension/src/sidepanel/styles.css",
    '''.notice {\n  background: #e3eee8;\n  color: #276346;\n  font-size: 12px;\n  padding: 9px 20px;\n}\n''',
    '''.notice {\n  background: #e3eee8;\n  color: #276346;\n  font-size: 12px;\n  padding: 9px 20px;\n}\n.notice.review {\n  background: #f5e6df;\n  color: #8b3f24;\n}\n''',
)

# Regression: a normal LinkedIn profile page with a language selector is never an application.
test = Path("packages/application-model/src/application-detection.test.ts")
text = test.read_text()
anchor = '''  it("rejects ordinary portfolio pages", () => {\n'''
case = '''  it("rejects a LinkedIn profile page even when the scanner sees a language selector", () => {\n    expect(\n      applicationPageEligibility(\n        page({\n          url: "https://www.linkedin.com/in/aadil-munshi/",\n          title: "Aadil Munshi | LinkedIn",\n          semantics: ["LANGUAGES"],\n        }),\n      ).eligible,\n    ).toBe(false);\n  });\n\n'''
if anchor not in text:
    raise SystemExit("LinkedIn regression anchor missing")
test.write_text(text.replace(anchor, case + anchor, 1))
