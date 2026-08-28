import { build } from "esbuild";
import { cp, readFile, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const debugArtifacts = process.env.MUNSHI_EXTENSION_DEBUG_ARTIFACTS === "1";
const shared = {
  bundle: true,
  legalComments: "none",
  minify: !debugArtifacts,
  sourcemap: debugArtifacts,
  target: "chrome120",
};

await Promise.all([
  build({
    ...shared,
    entryPoints: ["src/background/service-worker.ts"],
    format: "esm",
    outfile: "dist/background/service-worker.js",
  }),
  build({
    ...shared,
    entryPoints: ["src/content/entry.ts"],
    format: "iife",
    globalName: "MunshiApplyContent",
    outfile: "dist/content/bootstrap.js",
  }),
]);

const desktopRoot = resolve("dist");
const mobileRoot = resolve("dist-mobile");
const desktopManifest = JSON.parse(
  await readFile(resolve(desktopRoot, "manifest.json"), "utf8"),
);
const mobileManifest = structuredClone(desktopManifest);

mobileManifest.description =
  "Evidence-grounded application understanding and preparation for Microsoft Edge mobile.";
// webNavigation is required only by the desktop AutoPilot iframe lifecycle observer.
// Keep the mobile owner surface on its smaller storage + tabs permission budget.
mobileManifest.permissions = mobileManifest.permissions.filter(
  (permission) =>
    !["nativeMessaging", "sidePanel", "scripting", "webNavigation"].includes(
      permission,
    ),
);
mobileManifest.action = {
  ...mobileManifest.action,
  default_popup: "sidepanel/index.html",
};
delete mobileManifest.side_panel;

await rm(mobileRoot, { recursive: true, force: true });
await cp(desktopRoot, mobileRoot, { recursive: true });
await writeFile(
  resolve(mobileRoot, "manifest.json"),
  `${JSON.stringify(mobileManifest, null, 2)}\n`,
  "utf8",
);
