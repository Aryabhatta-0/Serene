import { describe, expect, it, vi } from "vitest";
import example from "@/fixtures/approval-command.example.json";
import { MAX_BODY_BYTES, relayApproval } from "./relay";

const APP = "https://serene.example.org";
const KERNEL = "http://127.0.0.1:8788";
const ENV = { SERENE_KERNEL_URL: KERNEL };
const BODY = JSON.stringify({ child_id: `chd_${"a".repeat(32)}`, command: example });
const ANSWER = { outcome: "APPROVAL_GRANTED", event_ids: [`evt_${"2".repeat(32)}`], reason_codes: [] };

function request(over: { headers?: Record<string, string | null>; body?: string } = {}) {
  const headers: Record<string, string> = {};
  const all: Record<string, string | null> = {
    origin: APP,
    "sec-fetch-site": "same-origin",
    "content-type": "application/json",
    authorization: "Bearer fake-access.token.value",
    ...over.headers,
  };
  for (const [k, v] of Object.entries(all)) if (v !== null) headers[k] = v;
  return new Request(`${APP}/api/approvals`, { method: "POST", headers, body: over.body ?? BODY });
}

const kernel = (status: number, body: unknown) =>
  vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

async function result(res: Response) {
  return [res.status, await res.json()] as const;
}

describe("relayApproval", () => {
  it("waits for a hosted kernel answer beyond ten seconds, but still bounds an unavailable kernel", async () => {
    vi.useFakeTimers();
    vi.spyOn(AbortSignal, "timeout").mockImplementation((ms) => {
      const controller = new AbortController();
      setTimeout(() => controller.abort(), ms);
      return controller.signal;
    });
    const send: typeof fetch = async (_url, init) => new Promise((resolve, reject) => {
      const timer = setTimeout(() => resolve(new Response(JSON.stringify(ANSWER))), 20_000);
      init?.signal?.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(new Error("timeout"));
      }, { once: true });
    });
    try {
      const pending = relayApproval(request(), ENV, send);
      await vi.advanceTimersByTimeAsync(20_000);
      expect(await result(await pending)).toEqual([200, ANSWER]);
      const unavailable: typeof fetch = async (_url, init) => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new Error("timeout")), { once: true });
      });
      const down = relayApproval(request(), ENV, unavailable);
      await vi.advanceTimersByTimeAsync(60_000);
      expect(await result(await down)).toEqual([502, { error: "KERNEL_UNAVAILABLE" }]);
    } finally {
      vi.restoreAllMocks();
      vi.useRealTimers();
    }
  });

  it("forwards a same-origin request with the caller's own token, and returns the kernel's answer", async () => {
    const send = kernel(200, { ...ANSWER, extra: "dropped" });
    expect(await result(await relayApproval(request(), ENV, send))).toEqual([200, ANSWER]);
    const [url, init] = send.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${KERNEL}/web/approvals`);
    expect(init.headers).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer fake-access.token.value",
      Origin: APP,
    });
    expect(init.body).toBe(BODY);
  });

  it("refuses cross-site and origin-less requests before anything is sent", async () => {
    const send = kernel(200, ANSWER);
    const refused: Record<string, string | null>[] = [
      { origin: "https://evil.example.com" },
      { origin: null },
      { "sec-fetch-site": "cross-site" },
      { "sec-fetch-site": "same-site" },
    ];
    for (const headers of refused) {
      expect(await result(await relayApproval(request({ headers }), ENV, send))).toEqual([
        403,
        { error: "ORIGIN_NOT_ALLOWED" },
      ]);
    }
    // A configured public origin replaces the request's own (behind a proxy).
    const proxied = { ...ENV, SERENE_WEB_ORIGINS: "https://app.example.org" };
    expect((await relayApproval(request(), proxied, send)).status).toBe(403);
    const fromProxy = request({ headers: { origin: "https://app.example.org" } });
    expect((await relayApproval(fromProxy, proxied, send)).status).toBe(200);
    expect(send).toHaveBeenCalledTimes(1);
    // Unconfigured, the server's own host as the browser addressed it.
    const hosted = request({ headers: { host: "127.0.0.1:3100", origin: "http://127.0.0.1:3100" } });
    expect((await relayApproval(hosted, ENV, send)).status).toBe(403); // the URL says https
  });

  it("refuses unauthenticated, non-JSON and oversized requests before anything is sent", async () => {
    const send = kernel(200, ANSWER);
    const cases: [Parameters<typeof request>[0], number][] = [
      [{ headers: { authorization: null } }, 401],
      [{ headers: { authorization: "Basic dXNlcjpwYXNz" } }, 401],
      [{ headers: { "content-type": "text/plain" } }, 415],
      [{ headers: { "content-length": String(MAX_BODY_BYTES + 1) } }, 413],
      [{ body: "x".repeat(MAX_BODY_BYTES + 1) }, 413],
    ];
    for (const [over, status] of cases) {
      expect((await relayApproval(request(over), ENV, send)).status).toBe(status);
    }
    expect(send).not.toHaveBeenCalled();
  });

  it("says plainly when the kernel is not configured or not reachable", async () => {
    expect(await result(await relayApproval(request(), {}, kernel(200, ANSWER)))).toEqual([
      503,
      { error: "NOT_CONFIGURED" },
    ]);
    const remoteHttp = { SERENE_KERNEL_URL: "http://kernel.example.org" };
    expect((await relayApproval(request(), remoteHttp, kernel(200, ANSWER))).status).toBe(503);
    const down = vi.fn(async () => {
      throw new TypeError("connect ECONNREFUSED");
    });
    expect(await result(await relayApproval(request(), ENV, down))).toEqual([502, { error: "KERNEL_UNAVAILABLE" }]);
  });

  it("passes the kernel's refusals through, and never a malformed or unexpected answer", async () => {
    for (const status of [401, 403, 409, 429]) {
      expect(await result(await relayApproval(request(), ENV, kernel(status, { error: "WHY", user: "x" })))).toEqual([
        status,
        { error: "WHY" },
      ]);
    }
    expect((await relayApproval(request(), ENV, kernel(500, { error: "boom" }))).status).toBe(502);
    expect((await relayApproval(request(), ENV, kernel(200, { outcome: "APPROVAL_GRANTED" }))).status).toBe(502);
  });
});
