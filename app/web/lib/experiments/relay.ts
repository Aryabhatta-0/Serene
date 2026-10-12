// The server side of the approval transport (Issue #84): the body of the
// Next.js route `/api/approvals`. It is a guard and a relay, never a decider:
// it refuses cross-site, oversized, non-JSON and unauthenticated requests, and
// forwards the rest, with the caller's own access token, to the kernel's
// `POST /web/approvals`, which verifies the session, the guardianship and
// every approval rule. Only the kernel's known answer shapes are passed back.

export const MAX_BODY_BYTES = 4096;
// Hosted Auth verification, ledger admission and projection publication can
// outlast ten seconds. Keep a bounded wait for their authoritative answer.
const KERNEL_TIMEOUT_MS = 60_000;
const PASSED_THROUGH = new Set([200, 400, 401, 403, 409, 413, 415, 429]);

type Env = Record<string, string | undefined>;

function reply(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

const fail = (status: number, error: string) => reply(status, { error });

function allowedOrigins(request: Request, env: Env): Set<string> {
  const configured = (env.SERENE_WEB_ORIGINS ?? "")
    .split(",")
    .map((o) => o.trim().replace(/\/$/, ""))
    .filter(Boolean);
  if (configured.length) return new Set(configured);
  // Unconfigured: this server's own origin, as the browser addressed it.
  const url = new URL(request.url);
  const host = request.headers.get("host") ?? url.host;
  return new Set([`${url.protocol}//${host}`]);
}

function kernelUrl(env: Env): string | null {
  const base = env.SERENE_KERNEL_URL?.trim().replace(/\/$/, "");
  if (!base || !/^https:\/\/|^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(base)) return null;
  return `${base}/web/approvals`;
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

/** Keep only the fields of the kernel's answer the web app understands. */
function sanitize(status: number, body: unknown): unknown {
  const b = (typeof body === "object" && body !== null ? body : {}) as Record<string, unknown>;
  if (status === 200) {
    if (typeof b.outcome !== "string" || !strings(b.event_ids) || !strings(b.reason_codes)) return null;
    return { outcome: b.outcome, event_ids: b.event_ids, reason_codes: b.reason_codes };
  }
  return { error: typeof b.error === "string" ? b.error : "REFUSED" };
}

export async function relayApproval(request: Request, env: Env, send: typeof fetch): Promise<Response> {
  // Same-origin only: a browser always sends Origin on a POST.
  const origin = request.headers.get("origin");
  const site = request.headers.get("sec-fetch-site");
  if (!origin || !allowedOrigins(request, env).has(origin) || (site !== null && site !== "same-origin")) {
    return fail(403, "ORIGIN_NOT_ALLOWED");
  }
  const type = (request.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
  if (type !== "application/json") return fail(415, "JSON_REQUIRED");
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (!Number.isFinite(declared) || declared > MAX_BODY_BYTES) return fail(413, "TOO_LARGE");
  const auth = request.headers.get("authorization") ?? "";
  if (!/^Bearer [A-Za-z0-9_.-]{1,4096}$/.test(auth)) return fail(401, "NOT_AUTHENTICATED");
  const body = await request.text();
  if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) return fail(413, "TOO_LARGE");

  const target = kernelUrl(env);
  if (!target) return fail(503, "NOT_CONFIGURED");
  let answer: Response;
  try {
    answer = await send(target, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: auth, Origin: origin },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(KERNEL_TIMEOUT_MS),
    });
  } catch {
    return fail(502, "KERNEL_UNAVAILABLE");
  }
  if (!PASSED_THROUGH.has(answer.status)) return fail(502, "KERNEL_ERROR");
  let parsed: unknown;
  try {
    parsed = await answer.json();
  } catch {
    return fail(502, "KERNEL_ERROR");
  }
  const clean = sanitize(answer.status, parsed);
  return clean === null ? fail(502, "KERNEL_ERROR") : reply(answer.status, clean);
}
