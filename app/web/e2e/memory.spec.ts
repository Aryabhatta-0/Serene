import { expect, test } from "@playwright/test";
import payload from "../fixtures/synthetic-memory-dream.json";

// Memory and Dream runs are shown from the synthetic fixture on a
// test-build-only route; the shipped surface (/memory) has no record
// connected and shows nothing from it.
const FIXTURE = "/fixtures/memory";

async function horizontalOverflow(page: import("@playwright/test").Page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

test("the shipped surface shows no memory and no fixture data", async ({ page }) => {
  await page.goto("/memory");
  await expect(page.getByRole("heading", { name: "No memories yet" })).toBeVisible();
  const main = page.getByRole("main");
  for (const memory of payload.memories) await expect(main).not.toContainText(memory.title);
  await expect(main.locator("[data-memory-review], [data-patch-id]")).toHaveCount(0);
  await expect(main).not.toContainText(/(mpt|lrn|evd|obs|pat|hyp)_[0-9a-f]{32}/);
});

test("memory, Dream runs, kept and refused changes are all shown, cleanly", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto(FIXTURE);
  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.locator("[data-fixture-banner]")).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "What Serene remembers" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Dream runs" })).toBeVisible();
  await expect(page.locator("[data-memory-path]")).toHaveCount(payload.memories.length);
  await expect(page.locator("[data-run-id]")).toHaveCount(payload.dream_runs.length);

  const refused = page.locator('[data-patch-id][data-status="REJECTED"]');
  await expect(refused).toHaveCount(1);
  await expect(refused.getByRole("list", { name: "Reasons it was refused" }).getByRole("listitem")).toHaveCount(1);
  await expect(refused).toContainText("Not enough evidence");
  await expect(page.locator('[data-patch-id][data-status="COMMITTED"]')).toContainText("Kept");

  // The certainty notation draws each state, and the state is also written.
  for (const [status, certainty] of [
    ["COMMITTED", "tested"],
    ["REJECTED", "refuted"],
    ["PROPOSED", "unknown"],
  ]) {
    const mark = page.locator(`[data-patch-id][data-status="${status}"] svg[data-certainty]`).first();
    await expect(mark).toHaveAttribute("data-certainty", certainty);
  }

  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("provenance can be followed by keyboard, and back", async ({ page }) => {
  await page.goto(FIXTURE);
  const memory = page.locator("[data-memory-path]").first();
  const keptBy = memory.locator("a[data-written-by]");
  await keptBy.focus();
  await page.keyboard.press("Enter");
  const writtenBy = payload.memories[0].written_by;
  await expect(page).toHaveURL(new RegExp(`#patch-${writtenBy}$`));
  const patch = page.locator(`[data-patch-id="${writtenBy}"]`);
  await expect(patch).toBeInViewport();
  await expect(patch).toHaveAttribute("data-status", "COMMITTED");

  // The proposed change opens from the keyboard.
  const summary = patch.locator("summary");
  await summary.focus();
  await page.keyboard.press("Enter");
  await expect(patch.locator("details")).toHaveAttribute("open", "");
  await expect(patch.locator("pre")).toContainText("+# A five-minute heads-up helps weekday pickups");

  await patch.getByRole("link", { name: "See the memory" }).focus();
  await page.keyboard.press("Enter");
  await expect(memory).toBeInViewport();

  // Every source leads to a rung of the evidence trail.
  const source = memory.getByRole("list", { name: "Sources" }).getByRole("link").first();
  const href = await source.getAttribute("href");
  await source.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(href!)).toBeInViewport();
  await expect(page.locator(href!)).toContainText("Raw evidence: the bottom of the trail.");
});

test("nothing on the page can edit, commit or approve memory", async ({ page }) => {
  await page.goto(FIXTURE);
  const main = page.getByRole("main");
  await expect(main.locator("input, textarea, select, [contenteditable], form")).toHaveCount(0);
  await expect(main.getByRole("button")).toHaveCount(0);
});

test("no width from 360 to 1440 overflows", async ({ page }) => {
  await page.goto(FIXTURE);
  for (const width of [360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await horizontalOverflow(page), `at ${width}px`).toBeLessThanOrEqual(0);
  }
});
