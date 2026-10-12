import { defineConfig, devices } from "@playwright/test";

// Actual shipped /sign-in, /experiments and /api/approvals, with a loopback
// test kernel. Auth/PostgREST are synthetic stand-ins; WS delivery is held by
// the test. This lane does not claim real Supabase Auth/Realtime coverage.
export default defineConfig({
  testDir: "./e2e-kernel",
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  timeout: 90_000,
  use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:3278", trace: "retain-on-failure" },
  webServer: [
    {
      command: "uv run python -m tests.web_approval_server",
      cwd: "../..",
      url: "http://127.0.0.1:8806/__test/head",
      timeout: 180_000,
    },
    {
      command: process.env.SERENE_E2E_SKIP_BUILD === "1"
        ? "npm run start -- --port 3278"
        : "npm run build && npm run start -- --port 3278",
      env: {
        NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:8806",
        NEXT_PUBLIC_SUPABASE_ANON_KEY: "fake-anon-key",
        SERENE_KERNEL_URL: "http://127.0.0.1:8806",
        SERENE_WEB_ORIGINS: "http://127.0.0.1:3278",
      },
      url: "http://127.0.0.1:3278/sign-in",
      timeout: 180_000,
    },
  ],
});
