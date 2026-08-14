import { access, readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = process.cwd();
const desktopRoot = resolve(root, "apps/extension/dist");
const mobileRoot = resolve(root, "apps/extension/dist-mobile");
const manifest = JSON.parse(
  await readFile(resolve(desktopRoot, "manifest.json"), "utf8"),
);
const mobileManifest = JSON.parse(
  await readFile(resolve(mobileRoot, "manifest.json"), "utf8"),
);

if (manifest.manifest_version !== 3) {
  throw new Error("Extension build is not Manifest V3");
}

const expectedPermissions = ["nativeMessaging", "sidePanel", "storage", "tabs"];
if (
  JSON.stringify(manifest.permissions) !== JSON.stringify(expectedPermissions)
) {
  throw new Error(
    "Extension permission budget changed without verification update",
  );
}

const requiredArtifacts = [
  manifest.background.service_worker,
  manifest.side_panel.default_path,
  ...manifest.content_scripts.flatMap((script) => script.js),
];

await Promise.all(
  requiredArtifacts.map((artifact) => access(resolve(desktopRoot, artifact))),
);

if (mobileManifest.manifest_version !== 3) {
  throw new Error("Mobile extension build is not Manifest V3");
}

const expectedMobilePermissions = ["storage", "tabs"];
if (
  JSON.stringify(mobileManifest.permissions) !==
  JSON.stringify(expectedMobilePermissions)
) {
  throw new Error(
    "Mobile extension permission budget changed without verification update",
  );
}
if ("side_panel" in mobileManifest) {
  throw new Error(
    "Mobile extension must not require the desktop side panel API",
  );
}
if (mobileManifest.action.default_popup !== "sidepanel/index.html") {
  throw new Error("Mobile extension must expose the application UI as a popup");
}

const requiredMobileArtifacts = [
  mobileManifest.background.service_worker,
  mobileManifest.action.default_popup,
  ...mobileManifest.content_scripts.flatMap((script) => script.js),
];

await Promise.all(
  requiredMobileArtifacts.map((artifact) =>
    access(resolve(mobileRoot, artifact)),
  ),
);

console.log(
  `Verified ${requiredArtifacts.length} desktop and ${requiredMobileArtifacts.length} mobile extension entry points.`,
);
