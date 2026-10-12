import { expect, test } from "@playwright/test";
import example from "../fixtures/approval-command.example.json";

// The shipped /api/approvals relay (Issue #84) on a production build with no
// kernel configured: it refuses before relaying anything, and says plainly
// when there is nowhere to relay to. It never answers a decision itself.
const body = { child_id: `chd_${"a".repeat(32)}`, command: example };

test("the approval relay refuses cross-site, unauthenticated and malformed requests", async ({ request, baseURL }) => {
  const post = (headers: Record<string, string>, data: unknown = body) =>
    request.post("/api/approvals", { headers: { "content-type": "application/json", ...headers }, data });

  expect((await post({ origin: "https://evil.example.com", authorization: "Bearer a.b.c" })).status()).toBe(403);
  expect((await post({ authorization: "Bearer a.b.c" })).status()).toBe(403); // no Origin
  expect((await post({ origin: baseURL! })).status()).toBe(401);
  const oversized = await post({ origin: baseURL!, authorization: "Bearer a.b.c" }, { pad: "x".repeat(5000) });
  expect(oversized.status()).toBe(413);

  const unconfigured = await post({ origin: baseURL!, authorization: "Bearer a.b.c" });
  expect(unconfigured.status()).toBe(503);
  expect(await unconfigured.json()).toEqual({ error: "NOT_CONFIGURED" });
  expect(unconfigured.headers()["cache-control"]).toContain("no-store");

  expect((await request.get("/api/approvals")).status()).toBe(405);
});
