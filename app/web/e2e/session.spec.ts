import { expect, test, type Page } from "@playwright/test";
import recorded from "../fixtures/synthetic-investigation.json";

// Web sign-in and child selection (Issue #87). `/fixtures/session` drives the
// real record control, sign-in form, provider and surface with Supabase
// replaced by a synthetic stand-in; the shipped pages are checked as they
// build without Supabase configured. Every account and child is synthetic.
const kernel = (row: { state: Record<string, unknown> }) => Object.values(row.state)[0] as any;
const first = kernel(recorded.snapshot.find((r) => r.projection === "investigations")!);
const investigationChanges = recorded.changes.filter((r) => r.projection === "investigations");
const last = kernel(investigationChanges[investigationChanges.length - 1]);
const CHILD = recorded.snapshot[0].child_id;
const SIBLING = `chd_${"5".repeat(32)}`;

const article = (page: Page) => page.locator("article[data-investigation-id]");

async function signIn(page: Page) {
  await page.goto("/fixtures/session");
  await expect(page.getByText("Not signed in")).toBeVisible();
  await page.getByLabel("Email").fill("parent@example.org");
  await page.getByLabel("Password").fill("fake-synthetic-only");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Family record connected")).toBeVisible();
}

test("signed in, a parent picks a child and follows its record live through a drop and a resync", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  await signIn(page);
  await page.getByLabel("Child").selectOption(CHILD);
  await expect(page.getByRole("heading", { level: 2, name: first.question })).toBeVisible();
  await expect(page.locator('[data-sync="live"]')).toBeVisible();

  // A kernel append publishes a projection row and the page follows it.
  await page.getByRole("button", { name: "Kernel append" }).click();
  await page.getByRole("button", { name: "Kernel append" }).click();
  await expect(article(page)).toHaveAttribute("data-phase", kernel(investigationChanges[0]).phase);

  // The network drops: what was shown stays, flagged as possibly out of date.
  await page.getByRole("button", { name: "Drop network" }).click();
  await expect(page.locator('[data-sync="reconnecting"]')).toContainText("Reconnecting");
  for (let i = 2; i < recorded.changes.length; i++) await page.getByRole("button", { name: "Kernel append" }).click();
  await expect(article(page)).toHaveAttribute("data-phase", kernel(investigationChanges[0]).phase);

  // Restored, the resync shows everything that was missed.
  await page.getByRole("button", { name: "Restore network" }).click();
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  await expect(article(page)).toHaveAttribute("data-phase", last.phase);
  expect(errors).toEqual([]);
});

test("switching child never shows the other child's record", async ({ page }) => {
  await signIn(page);
  await page.getByLabel("Child").selectOption(CHILD);
  await expect(page.getByRole("heading", { level: 2, name: first.question })).toBeVisible();
  await page.getByLabel("Child").selectOption(SIBLING);
  await expect(page.getByRole("heading", { level: 2, name: "Synthetic: why is bedtime slow?" })).toBeVisible();
  await expect(page.getByText(first.question)).toHaveCount(0);
  // A kernel append for the first child is not this child's, and never appears here.
  await page.getByRole("button", { name: "Kernel append" }).click();
  await page.getByRole("button", { name: "Kernel append" }).click();
  await expect(page.getByText(first.question)).toHaveCount(0);
});

test("an expired session clears the record and asks to sign in again", async ({ page }) => {
  await signIn(page);
  await expect(article(page)).toBeVisible();
  await page.getByRole("button", { name: "Expire session" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Your session ended" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in again" })).toBeVisible();
  await expect(article(page)).toHaveCount(0);
  expect(await page.evaluate(() => sessionStorage.getItem("serene.selected-child"))).toBeNull();
});

test("signing out returns to the honest signed-out state", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByText("Not signed in")).toBeVisible();
  await expect(article(page)).toHaveCount(0);
});

test("the record control fits every width from 360 to 1440", async ({ page }) => {
  await signIn(page);
  await expect(article(page)).toBeVisible();
  for (const width of [360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `at ${width}px`).toBeLessThanOrEqual(0);
  }
});

test("the shipped sign-in page says plainly when sign-in is not configured", async ({ page }) => {
  await page.goto("/sign-in?next=/investigations");
  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("Sign-in isn’t set up");
  await expect(page.getByLabel("Password")).toHaveCount(0);
});
