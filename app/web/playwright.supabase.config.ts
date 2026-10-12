import { defineConfig, devices } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Playwright's default failure snapshot includes password form values.
// This real-service lane must not capture those values in error-context.md.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";

// Opt-in proof against the REAL Supabase project. Missing config is a hard
// failure, never a skipped/pass result. Prepare synthetic data first; see docs.
for (const name of ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_DB_URL"]) {
  if (!process.env[name]) throw new Error(`Real Supabase proof requires ${name}`);
}
const manifest = JSON.parse(readFileSync(resolve(__dirname, "../../.demo/web-e2e.json"), "utf8"));
if (manifest.classification !== "SYNTHETIC" || !manifest.ready) throw new Error("Prepare a synthetic run first");

export default defineConfig({
  testDir: "./e2e-supabase",
  outputDir: resolve(__dirname, "../../.demo/real-web-e2e-artifacts"),
  workers: 1,
  timeout: 300_000,
  expect: { timeout: 30_000 },
  use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:3279", trace: "off" },
  // No traces/screenshots. Any failure context stays in ignored .demo;
  // this opt-in lane must never upload real sessions/test credentials to CI.
  webServer: [
    {
      command: "uv run python app/approvals/approvals_server.py --port 8807",
      cwd: "../..",
      env: { SERENE_WEB_BINDINGS: JSON.stringify(manifest.bindings), SERENE_WEB_ORIGINS: "http://127.0.0.1:3279", SUPABASE_SERVICE_ROLE_KEY: "" },
      port: 8807,
      timeout: 60_000,
    },
    {
      command: "npm run build && npm run start -- --port 3279",
      env: {
        NEXT_PUBLIC_SUPABASE_URL: process.env.SUPABASE_URL!, NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.SUPABASE_ANON_KEY!,
        SERENE_KERNEL_URL: "http://127.0.0.1:8807", SERENE_WEB_ORIGINS: "http://127.0.0.1:3279",
        SUPABASE_DB_URL: "", SUPABASE_SERVICE_ROLE_KEY: "",
      },
      url: "http://127.0.0.1:3279/sign-in",
      timeout: 180_000,
    },
  ],
});
