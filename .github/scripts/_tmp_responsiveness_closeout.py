from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Expected exactly one match in {path}, found {count}: {old[:80]!r}"
        )
    file.write_text(text.replace(old, new, 1))


def sub_once(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text()
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(
            f"Expected exactly one regex match in {path}, found {count}: {pattern[:80]!r}"
        )
    file.write_text(updated)


client = "apps/extension/src/messaging/client.ts"
replace_once(
    client,
    '  return (await send({ type: "GET_ACTIVE_PAGE" })) as ApplicationPage | null;\n}\n\nexport async function getProfile()',
    '  void send({ type: "GET_ACTIVE_PAGE" }).catch(() => undefined);\n  return null;\n}\n\nexport async function getProfile()',
)
replace_once(
    client,
    'export async function getProfileSyncStatus(): Promise<ProfileSyncStatus> {',
    '''export async function reconcileProfile(): Promise<ProfileSnapshot | null> {
  const candidate = await withTimeout(
    send({ type: "GET_PROFILE" }),
    12_000,
    "Encrypted profile reconciliation timed out. Your local profile remains available.",
  );
  return candidate === null ? null : parseProfileSnapshot(candidate);
}

export async function getProfileSyncStatus(): Promise<ProfileSyncStatus> {''',
)

cloud = "apps/extension/src/storage/cloud.ts"
sub_once(
    cloud,
    r'''  void operation\.finally\(\(\) => \{\s*if \(cloudHealthInFlight === operation\) cloudHealthInFlight = null;\s*\}\);''',
    '''  void operation.then(
    () => {
      if (cloudHealthInFlight === operation) cloudHealthInFlight = null;
    },
    () => {
      if (cloudHealthInFlight === operation) cloudHealthInFlight = null;
    },
  );''',
)
sub_once(
    cloud,
    r'''  void operation\.finally\(\(\) => \{\s*if \(cloudSnapshotInFlight === operation\) cloudSnapshotInFlight = null;\s*\}\);''',
    '''  void operation.then(
    () => {
      if (cloudSnapshotInFlight === operation) cloudSnapshotInFlight = null;
    },
    () => {
      if (cloudSnapshotInFlight === operation) cloudSnapshotInFlight = null;
    },
  );''',
)

app = "apps/extension/src/sidepanel/App.tsx"
replace_once(
    app,
    '  const profileRevision = useRef(0);\n',
    '  const profileRevision = useRef(0);\n  const cloudPullInFlight = useRef(false);\n',
)
replace_once(
    app,
    '  getProfile,\n  getProfileSyncStatus,',
    '  getProfile,\n  getProfileSyncStatus,\n  reconcileProfile,',
)
sub_once(
    app,
    r'''  const pullCloudChanges = useCallback\(async \(\) => \{.*?  \}, \[profileDirty, protectedDrafts\]\);''',
    '''  const pullCloudChanges = useCallback(async () => {
    if (
      cloudPullInFlight.current ||
      profileDirty ||
      Object.keys(protectedDrafts).length > 0
    )
      return;
    cloudPullInFlight.current = true;
    try {
      const connection = await getCloudConnection();
      if (!connection) {
        setCloud({ status: "disconnected" });
        return;
      }
      const cloudHealth = await getCloudHealth(connection);
      setCloud({ status: "connected", data: cloudHealth });
      if (!cloudHealth.encryptionReady) return;
      const syncedProfile = await reconcileProfile();
      const syncStatus = await getProfileSyncStatus();
      const snapshot = await getCloudSnapshot(connection);
      setCloudSnapshot(snapshot);
      setProfileSyncStatus(syncStatus);
      if (syncedProfile) {
        setProfile(syncedProfile);
        setProfileRecoveryIssue(null);
        setProfileLoaded(true);
        setProfileDirty(false);
        profileRevision.current += 1;
        setSaveState(syncStatus.conflict ? "conflict" : "synced");
      }
      setLastCloudPullAt(now());
    } catch (error) {
      setCloud({
        status: "unavailable",
        error: error instanceof Error ? error.message : "Cloud unavailable",
      });
      throw error;
    } finally {
      cloudPullInFlight.current = false;
    }
  }, [profileDirty, protectedDrafts]);''',
)
sub_once(
    app,
    r'''  const connectionLabel =.*?(?=  const connectionClass =)''',
    '''  const connectionLabel =
    health.toLowerCase() !== "healthy"
      ? "Unavailable"
      : native.status === "upgrade_required"
        ? "Companion update"
        : native.status === "checking"
          ? "Checking"
          : native.status === "healthy"
            ? cloud.status === "connected"
              ? "Cloud synced"
              : "Local ready"
            : "Extension ready";
''',
)
