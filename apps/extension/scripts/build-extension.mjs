import { build } from "esbuild";

const shared = {
  bundle: true,
  legalComments: "none",
  minify: false,
  sourcemap: true,
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
    entryPoints: ["src/content/bootstrap.ts"],
    format: "iife",
    globalName: "MunshiApplyContent",
    outfile: "dist/content/bootstrap.js",
  }),
]);
