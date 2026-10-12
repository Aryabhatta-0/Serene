import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// REAL Supabase Auth + PostgREST + Realtime and the production approval
// server. Never route/mock Auth, REST or WebSockets in this lane.
const root = resolve(__dirname, "../../..");
const manifest = JSON.parse(readFileSync(resolve(root, ".demo/web-e2e.json"), "utf8"));
const account = manifest.accounts.parent;
const append = (question: string) => execFileSync("uv", ["run", "python", "-m", "scripts.web_supabase_e2e", "append", "--question", question], { cwd: root, stdio: "pipe" });

async function signIn(page: Page, role: "parent" | "other" | "caregiver", next: string) {
  const user = manifest.accounts[role];
  await page.goto(`/sign-in?next=${next}`);
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(`http://127.0.0.1:3279${next}`);
}

test("real parent Auth, kernel append, Realtime, offline reconnect and resync", async ({ page, context }) => {
  await signIn(page, "parent", "/today");
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  const question = `Synthetic: live append ${Date.now()}`;
  append(question);
  await expect(page.getByRole("heading", { name: question })).toBeVisible();
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
    return response.ok() ? response.json() : [];
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
  const green = page.locator('article[data-safety="GREEN"][data-phase="AWAITING_APPROVAL"]').first();
  const id = (await green.getAttribute("data-experiment-id"))!;
  const card = page.locator(`article[data-experiment-id="${id}"]`);
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await card.getByRole("button", { name: "Yes, approve" }).click();
  await expect(card).toHaveAttribute("data-phase", "APPROVED");
  const decline = page.locator('article[data-safety="GREEN"][data-phase="AWAITING_APPROVAL"]').first();
  const declineId = (await decline.getAttribute("data-experiment-id"))!;
  await decline.getByRole("button", { name: "Decline", exact: true }).click();
  await decline.getByRole("button", { name: "Yes, decline" }).click();
  await expect(page.locator(`article[data-experiment-id="${declineId}"]`)).toHaveAttribute("data-phase", "ABANDONED");
  await expect(page.locator('article[data-safety="RED"]').getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
});
