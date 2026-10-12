import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// REAL Supabase Auth + PostgREST + Realtime and the production approval
// server. No synthetic Auth, REST responses or fabricated WebSocket events.
const root = resolve(__dirname, "../../..");
const manifest = JSON.parse(readFileSync(resolve(root, ".demo/web-e2e.json"), "utf8"));
const account = manifest.accounts.parent;
const append = (question: string) => execFileSync("uv", ["run", "python", "-m", "scripts.web_supabase_e2e", "append", "--question", question], { cwd: root, stdio: "pipe" });
const check = () => JSON.parse(execFileSync("uv", ["run", "python", "-m", "scripts.web_supabase_e2e", "check"], { cwd: root, encoding: "utf8", stdio: "pipe" }));

function realtimeRows(page: Page) {
  const rows: any[] = [];
  page.on("websocket", (socket) => {
    if (!socket.url().includes("/realtime/v1/websocket")) return;
    socket.on("framereceived", ({ payload }) => {
      const frame = JSON.parse(String(payload));
      if (frame[3] === "postgres_changes") rows.push(frame[4].data.record);
    });
  });
  return rows;
}

async function signIn(page: Page, role: "parent" | "other" | "caregiver", next: string) {
  const user = manifest.accounts[role];
  await page.goto(`/sign-in?next=${next}`);
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(`http://127.0.0.1:3279${next}`);
}

test("real parent Auth, kernel append, Realtime, offline reconnect and resync", async ({ page, context }) => {
  const changes = realtimeRows(page);
  await page.goto("/today");
  await expect(page.locator('[data-record="Not signed in"]')).toBeVisible();
  await expect(page.getByLabel("Child")).toHaveCount(0);
  await signIn(page, "parent", "/today");
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  await expect(page.getByLabel("Child").locator("option")).toHaveCount(1);
  await expect(page.getByLabel("Child")).toHaveValue(account.child_id);
  const before = check();
  const question = `Synthetic: live append ${Date.now()}`;
  append(question);
  await expect(page.getByRole("heading", { name: question })).toBeVisible();
  expect(check().sequence).toBe(before.sequence + 1);
  await expect.poll(() => changes.some((row) => row.child_id === account.child_id && row.last_sequence === before.sequence + 1)).toBe(true);
  await page.goto("/investigations");
  await expect(page.getByRole("heading", { name: question })).toBeVisible();
  await context.setOffline(true);
  await expect(page.locator('[data-sync="reconnecting"]')).toContainText("Reconnecting", { timeout: 90_000 });
  const missed = `Synthetic: offline append ${Date.now()}`;
  append(missed);
  await expect(page.getByRole("heading", { name: missed })).toHaveCount(0);
  await context.setOffline(false);
  await expect(page.locator('[data-sync="live"]')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("heading", { name: missed })).toBeVisible();
  await expect(page.getByRole("heading", { name: missed })).toHaveCount(1);
  expect(check().sequence).toBe(before.sequence + 2);
  expect(changes.every((row) => row.child_id === account.child_id)).toBe(true);
});

test("real sessions respect child RLS, and browser approval/decline update the projection", async ({ page, request }) => {
  const url = process.env.SUPABASE_URL!;
  const anon = process.env.SUPABASE_ANON_KEY!;
  const login = async (role: string) => {
    const user = manifest.accounts[role];
    const response = await request.post(`${url}/auth/v1/token?grant_type=password`, { headers: { apikey: anon }, data: { email: user.email, password: user.password } });
    expect(response.ok()).toBe(true);
    return (await response.json()).access_token as string;
  };
  const rows = async (access: string) => {
    const response = await request.get(`${url}/rest/v1/projection_state?child_id=eq.${account.child_id}`, { headers: { apikey: anon, authorization: `Bearer ${access}`, "Accept-Profile": "serene" } });
    if (access === anon) {
      expect(response.status()).toBe(401);
      expect((await response.json()).code).toBe("42501");
      return [];
    }
    expect(response.ok()).toBe(true);
    return response.json();
  };
  const parent = await login("parent");
  expect((await rows(parent)).some((r: any) => r.projection === "experiments")).toBe(true);
  const all = await request.get(`${url}/rest/v1/projection_state`, { headers: { apikey: anon, authorization: `Bearer ${parent}`, "Accept-Profile": "serene" } });
  expect(all.ok()).toBe(true);
  expect((await all.json()).every((r: any) => r.child_id === account.child_id)).toBe(true);
  expect(await rows(await login("other"))).toEqual([]);
  expect((await rows(await login("caregiver"))).every((r: any) => r.projection === "active_learnings")).toBe(true);
  expect(await rows(anon)).toEqual([]);
  await signIn(page, "parent", "/experiments");
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  await expect(page.getByLabel("Child").locator("option")).toHaveCount(1);
  await expect(page.getByLabel("Child")).toHaveValue(account.child_id);
  // Delay only genuine server frames. HTTP and the real Supabase connection
  // remain live, proving an accepted response alone cannot change the stage.
  let hold = true;
  const queued: (() => void)[] = [];
  const delivered: any[] = [];
  await page.routeWebSocket(/\/realtime\/v1\/websocket/, (socket) => {
    const server = socket.connectToServer();
    server.onMessage((message) => {
      const frame = JSON.parse(String(message));
      const deliver = () => {
        if (frame[3] === "postgres_changes") delivered.push(frame[4].data.record);
        socket.send(message);
      };
      if (hold && frame[3] === "postgres_changes") queued.push(deliver);
      else deliver();
    });
  });
  await page.reload();
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  const green = page.locator('article[data-safety="GREEN"][data-phase="AWAITING_APPROVAL"]').first();
  const id = (await green.getAttribute("data-experiment-id"))!;
  const card = page.locator(`article[data-experiment-id="${id}"]`);
  const view = (await rows(parent)).find((r: any) => r.projection === "experiments").state;
  const approval = view.experiments.find((e: any) => e.experiment_id === id).approval;
  const body = { child_id: account.child_id, command: { approval_request_id: approval.approval_request_id, decision: "APPROVE", shown_intervention_digest: approval.intervention_digest, shown_safety_class: "GREEN", request_id: `real-refusal-${Date.now()}` } };
  const relay = (token: string, data: unknown) => request.post("/api/approvals", { headers: { origin: "http://127.0.0.1:3279", authorization: `Bearer ${token}`, "content-type": "application/json" }, data });
  const before = check();
  expect((await relay(await login("other"), body)).status()).toBe(403);
  expect((await relay(await login("caregiver"), body)).status()).toBe(403);
  const stale = await relay(parent, { ...body, command: { ...body.command, request_id: `real-stale-${Date.now()}`, shown_intervention_digest: "0".repeat(64) } });
  expect((await stale.json()).reason_codes).toContain("INTERVENTION_DIGEST_MISMATCH");
  expect(check()).toEqual(before);
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  const sent = page.waitForRequest((r) => r.url().endsWith("/api/approvals") && r.method() === "POST");
  const answered = page.waitForResponse((r) => r.url().endsWith("/api/approvals") && r.request().method() === "POST");
  await card.getByRole("button", { name: "Yes, approve" }).click();
  const browserRequest = await sent;
  const response = await answered;
  expect(response.status()).toBe(200);
  expect((await response.json()).outcome).toBe("APPROVAL_GRANTED");
  await expect(card.getByText(/Serene recorded your approval/)).toBeVisible();
  await expect(card).toHaveAttribute("data-phase", "AWAITING_APPROVAL");
  await expect.poll(() => queued.length).toBeGreaterThan(0);
  const after = check();
  expect(after.decisions).toBe(before.decisions + 1);
  expect((await rows(parent)).find((r: any) => r.projection === "experiments").state.experiments.find((e: any) => e.experiment_id === id).phase).toBe("APPROVED");
  const replay = await relay(parent, browserRequest.postData()!);
  expect((await replay.json()).outcome).toBe("APPROVAL_GRANTED");
  expect(check()).toEqual(after);
  hold = false;
  for (const deliver of queued.splice(0)) deliver();
  await expect(card).toHaveAttribute("data-phase", "APPROVED");
  // The delayed payload originated at Supabase, with the committed PG sequence.
  expect(delivered.some((row) => row.projection === "experiments" && row.last_sequence === after.sequence)).toBe(true);
  const decline = page.locator('article[data-safety="GREEN"][data-phase="AWAITING_APPROVAL"]').first();
  const declineId = (await decline.getAttribute("data-experiment-id"))!;
  await decline.getByRole("button", { name: "Decline", exact: true }).click();
  await decline.getByRole("button", { name: "Yes, decline" }).click();
  await expect(page.locator(`article[data-experiment-id="${declineId}"]`)).toHaveAttribute("data-phase", "ABANDONED");
  await expect(page.locator('article[data-safety="RED"]').getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
  expect(check().decisions).toBe(before.decisions + 2);
});

test("real user switching, caregiver denial and cross-tab session loss clear the family", async ({ page, context }) => {
  await signIn(page, "other", "/today");
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  await expect(page.getByLabel("Child").locator("option")).toHaveCount(1);
  await expect(page.getByLabel("Child")).toHaveValue(manifest.accounts.other.child_id);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.locator('[data-record="Not signed in"]')).toBeVisible();
  await expect(page.getByLabel("Child")).toHaveCount(0);
  await signIn(page, "caregiver", "/experiments");
  await expect(page.locator('[data-record="No child linked"]')).toBeVisible();
  await expect(page.getByLabel("Child")).toHaveCount(0);
  await expect(page.locator("article[data-experiment-id]")).toHaveCount(0);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signIn(page, "parent", "/today");
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  const otherTab = await context.newPage();
  await otherTab.goto("/today");
  await expect(otherTab.locator('[data-sync="live"]')).toBeVisible();
  await otherTab.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.locator('[data-record="Your session ended"]')).toBeVisible();
  await expect(page.getByLabel("Child")).toHaveCount(0);
  await expect(page.locator('[data-sync="live"]')).toHaveCount(0);
});
