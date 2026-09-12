import type { ApplicationPage } from "@munshi-apply/contracts";
import {
  decryptJson,
  fetchCloudEvents,
  getCloudConnection,
  getWorkspaceEncryptionKey,
  isCloudEncryptionReady,
  postEncryptedEntity,
  type CloudSyncEvent,
} from "../storage/cloud";

const ENTITY_TYPE = "SECURITY.CHALLENGE.V1";

type ChallengeSnapshot = {
  pageId: string;
  tabId: number;
  url: string;
  title: string;
  securityCheckpoint: ApplicationPage["securityCheckpoint"];
  observedAt: string;
};

function latestForPage(
  events: CloudSyncEvent[],
  pageId: string,
): CloudSyncEvent | null {
  return (
    events
      .filter(
        (event) =>
          event.entityType === ENTITY_TYPE && event.entityId === pageId,
      )
      .sort((left, right) => right.sequence - left.sequence)[0] ?? null
  );
}

function sameChallenge(
  left: ChallengeSnapshot,
  right: ChallengeSnapshot,
): boolean {
  return (
    left.pageId === right.pageId &&
    left.tabId === right.tabId &&
    left.url === right.url &&
    left.securityCheckpoint === right.securityCheckpoint
  );
}

async function publishTransition(
  sender: chrome.runtime.MessageSender,
  page: ApplicationPage,
): Promise<void> {
  const tabId = sender.tab?.id;
  if (tabId === undefined || (sender.frameId ?? 0) !== 0) return;

  const connection = await getCloudConnection();
  if (!connection || !(await isCloudEncryptionReady())) return;
  const rawKey = await getWorkspaceEncryptionKey();
  if (!rawKey) return;

  const snapshot: ChallengeSnapshot = {
    pageId: page.pageId,
    tabId,
    url: page.url,
    title: page.title,
    securityCheckpoint: page.securityCheckpoint,
    observedAt: page.observedAt,
  };
  const { events } = await fetchCloudEvents(connection, 0);
  const latest = latestForPage(events, page.pageId);
  if (latest) {
    const previous = await decryptJson<ChallengeSnapshot>(
      rawKey,
      latest.payloadCiphertext,
    );
    if (sameChallenge(previous, snapshot)) return;
  }

  await postEncryptedEntity({
    connection,
    rawKey,
    entityType: ENTITY_TYPE,
    entityId: page.pageId,
    baseVersion: latest ? latest.baseVersion + 1 : 0,
    value: snapshot,
  });
}

chrome.runtime.onMessage.addListener((request, sender) => {
  if (
    request?.type !== "PAGE_SNAPSHOT" ||
    !request.payload ||
    typeof request.payload !== "object"
  ) {
    return false;
  }
  const page = request.payload as ApplicationPage;
  if (
    typeof page.pageId !== "string" ||
    typeof page.url !== "string" ||
    typeof page.observedAt !== "string"
  ) {
    return false;
  }
  void publishTransition(sender, page).catch(() => undefined);
  return false;
});
