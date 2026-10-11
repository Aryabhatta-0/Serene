import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit and component tests (jsdom). Browser behaviour, layout and the real
// production build are covered by the Playwright suite in e2e/.
export default defineConfig({
  esbuild: { jsx: "automatic" },
  resolve: {
    alias: [{ find: /^@\//, replacement: fileURLToPath(new URL("./", import.meta.url)) }],
  },
  test: {
    environment: "jsdom",
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", ".next/**", "e2e/**"],
    setupFiles: ["./vitest.setup.ts"],
  },
});
