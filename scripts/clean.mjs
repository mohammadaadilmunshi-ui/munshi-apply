import { rm } from "node:fs/promises";
import { resolve } from "node:path";

const roots = [
  "apps/extension/dist",
  "coverage",
  "packages/contracts/dist",
  "packages/semantic-engine/dist",
  "packages/application-model/dist",
  "packages/shared/dist",
];

await Promise.all(
  roots.map((directory) =>
    rm(resolve(process.cwd(), directory), { force: true, recursive: true }),
  ),
);
