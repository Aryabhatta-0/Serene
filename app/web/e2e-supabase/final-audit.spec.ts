import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

// Opt-in, real hosted Auth/RLS on the shipped production routes. Screenshots
// are taken only after password controls have left the document, and remain
// in ignored local artifacts. All records must be prepared as SYNTHETIC.
const root = resolve(__dirname, "../../..");
const manifest = JSON.parse(readFileSync(resolve(root, ".demo/web-e2e.json"), "utf8"));
const account = manifest.accounts.parent;
const paths = ["/today", "/investigations", "/experiments", "/memory", "/causal-twin"];

test("owning parent cannot bypass projections by requesting canonical ledger rows", async ({ request }) => {
  const url = process.env.SUPABASE_URL!;
  const anon = process.env.SUPABASE_ANON_KEY!;
  const login = await request.post(`${url}/auth/v1/token?grant_type=password`, {
    headers: { apikey: anon }, data: { email: account.email, password: account.password },
  });
  expect(login.ok()).toBe(true);
  const token = (await login.json()).access_token;
  const canonicalTable = ["domain", "events"].join("_");
  const response = await request.get(`${url}/rest/v1/${canonicalTable}?child_id=eq.${account.child_id}`, {
    headers: { apikey: anon, authorization: `Bearer ${token}`, "Accept-Profile": "serene" },
  });
  expect(response.status()).toBe(403);
  expect((await response.json()).code).toBe("42501");
});

test("clean parent journey, every production surface at seven widths, and sign-out", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("response", (response) => { if (response.status() >= 400) errors.push(`${response.status()} ${new URL(response.url()).pathname}`); });
  for (const width of [320, 375, 390, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of ["/", "/sign-in"]) {
      await page.goto(path);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), `${path} at ${width}`).toBeLessThanOrEqual(1);
      if (path === "/sign-in") {
        await expect(page.getByLabel("Email")).toBeVisible();
        await expect(page.getByLabel("Password")).toBeVisible();
      }
    }
  }
  await page.goto("/");
  await page.getByRole("button", { name: "Enter Serene" }).click();
  await expect(page).toHaveURL(/\/today$/);
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  const child = manifest.audit_child ?? account.child_id;
  await page.getByLabel("Child").selectOption(child);
  const screenshots = resolve(root, ".demo/final-audit-screenshots");
  mkdirSync(screenshots, { recursive: true });
  for (const width of [320, 375, 390, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: width < 768 ? 844 : 1000 });
    for (const path of paths) {
      await page.goto(path);
      await expect(page.locator('[data-sync="live"]')).toBeVisible();
      await expect(page.getByLabel("Child")).toHaveValue(child);
      await expect(page.locator("h1")).toHaveCount(1);
      if (path === "/memory" && manifest.audit_child) {
        await expect(page.locator("[data-memory-review]")).toBeVisible();
        await expect(page.getByText("INSUFFICIENT_EVIDENCE:OBSERVATION_BELOW_PATTERN", { exact: true })).toBeVisible();
        expect(await page.locator("main").innerText()).toMatch(/[0-9a-f]{40}/);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), `${path} at ${width}`).toBeLessThanOrEqual(1);
      expect(await page.locator('button:not([aria-label])').evaluateAll((buttons) => buttons.filter((button) => !(button.textContent ?? '').trim()).length)).toBe(0);
      if (width === 390 || width === 1440) await page.screenshot({ path: resolve(screenshots, `${path.slice(1)}-${width}.png`), fullPage: true });
    }
  }
  // The textual provenance list remains available without using the graph.
  const links = page.locator('section button[data-edge-id]:not(.react-flow *)');
  for (let i = 0; i < await links.count(); i++) {
    await links.nth(i).click();
    await expect(page.locator('[data-provenance="full"]')).toBeVisible();
    const broken = await page.locator('[data-provenance="full"] a[href^="#"]').evaluateAll((anchors) => anchors.filter((a) => !document.getElementById(decodeURIComponent(a.getAttribute('href')!.slice(1)))).map((a) => a.textContent));
    expect(broken).toEqual([]);
  }
  await page.goto("/today");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: /Skip to/ })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.locator('[data-record="Not signed in"]')).toBeVisible();
  await expect(page.getByLabel("Child")).toHaveCount(0);
  await page.goBack();
  await expect(page.locator('[data-sync="live"]')).toHaveCount(0);
  expect(errors).toEqual([]);
});
