import { build } from "esbuild";

await build({
  entryPoints: ["apps/extension/src/content/plan-runtime.ts"],
  bundle: true,
  format: "iife",
  globalName: "MunshiPlanRuntime",
  platform: "browser",
  target: "chrome120",
  outfile: "apps/native-host/browser-dist/plan-runtime.js",
  sourcemap: false,
});
