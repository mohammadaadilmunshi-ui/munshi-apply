import { access, readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = process.cwd();
const manifestPath = resolve(root, "apps/extension/dist/manifest.json");
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));

if (manifest.manifest_version !== 3) {
  throw new Error("Extension build is not Manifest V3");
}

const expectedPermissions = ["sidePanel", "storage", "tabs"];
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
  requiredArtifacts.map((artifact) =>
    access(resolve(root, "apps/extension/dist", artifact)),
  ),
);

console.log(`Verified ${requiredArtifacts.length} extension entry points.`);
