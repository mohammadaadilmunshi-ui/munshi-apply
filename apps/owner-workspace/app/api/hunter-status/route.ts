import { env } from "cloudflare:workers";
import { authError, apiError, requirePrincipal } from "../_shared";
import { proxyHunterStatus } from "./bridge";

export async function GET(request: Request): Promise<Response> {
  try {
    const principal = await requirePrincipal(request);
    const workerEnv = env as unknown as Record<string, string | undefined>;
    return proxyHunterStatus(
      principal.workspaceId,
      new URL(request.url).searchParams.get("applicationId") ?? "",
      {
        origin: workerEnv.MUNSHI_HUNTER_STATUS_ORIGIN,
        secret: workerEnv.MUNSHI_HUNTER_BRIDGE_SECRET,
        allowedWorkspace: workerEnv.MUNSHI_HUNTER_BRIDGE_WORKSPACE_ID,
      },
    );
  } catch (error) {
    return authError(error) ?? apiError(error);
  }
}
