import { requireChatGPTUser } from "../chatgpt-auth";
import { MobileWorkspace } from "./mobile-workspace";
import { SecurityChallengeOverlay } from "./security-challenge-overlay";

export const dynamic = "force-dynamic";

export default async function WorkspacePage() {
  const user = await requireChatGPTUser("/workspace");
  return (
    <>
      <SecurityChallengeOverlay />
      <MobileWorkspace ownerName={user.displayName} />
    </>
  );
}
