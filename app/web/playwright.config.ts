import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;

// Runs against a production build. The dedicated Maya project runs the real
// canonical offline scripts and the opt-in local adapter; no external services.
// The build also routes `page.fixture.tsx` pages (SERENE_FIXTURE_ROUTES=1),
// which draw synthetic fixtures; a normal `npm run build` has none.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      testIgnore: /maya-demo\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "tablet",
      testIgnore: /maya-demo\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } },
    },
    {
      name: "mobile",
      testIgnore: /maya-demo\.spec\.ts/,
      use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } },
    },
    {
      name: "maya-demo",
      testMatch: /maya-demo\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: `npm run build && npm run start -- --port ${PORT}`,
    env: { SERENE_FIXTURE_ROUTES: "1", SERENE_DEMO_MODE: "1" },
    url: `http://127.0.0.1:${PORT}/today`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
