import { requireChatGPTUser } from "../chatgpt-auth";
import { MobileWorkspace } from "./mobile-workspace";

export const dynamic = "force-dynamic";

export default async function WorkspacePage() {
  const user = await requireChatGPTUser("/workspace");
  return <MobileWorkspace ownerName={user.displayName} />;
}
