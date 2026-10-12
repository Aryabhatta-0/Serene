import { afterEach, expect, it, vi } from "vitest";
vi.mock("@/lib/demo/server", () => ({ readDemoState: vi.fn() }));
import { readDemoState } from "@/lib/demo/server";
import { GET } from "./route";

afterEach(() => { vi.unstubAllEnvs(); vi.clearAllMocks(); });

it("returns 404 without touching the adapter when the demo is disabled", async () => {
  vi.stubEnv("SERENE_DEMO_MODE", "");
  expect((await GET()).status).toBe(404);
  expect(readDemoState).not.toHaveBeenCalled();
});

it("does not cache or leak local subprocess errors", async () => {
  vi.stubEnv("SERENE_DEMO_MODE", "1");
  vi.mocked(readDemoState).mockRejectedValue(new Error("private local path and diagnostics"));
  const response = await GET();
  expect(response.status).toBe(503);
  expect(response.headers.get("Cache-Control")).toBe("no-store");
  expect(await response.text()).not.toContain("private local path");
});
