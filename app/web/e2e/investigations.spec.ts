import { expect, test, type Page } from "@playwright/test";
import recorded from "../fixtures/synthetic-investigation.json";

// Today and Investigations from kernel-recorded projection rows, replayed
// through the Realtime projection path (#33) on test-build-only routes. The
// shipped pages have no feed and show nothing from the fixture.
const kernel = (row: { state: Record<string, unknown> }) => Object.values(row.state)[0] as any;
const first = kernel(recorded.snapshot.find((r) => r.projection === "investigations")!);
const investigationChanges = recorded.changes.filter((r) => r.projection === "investigations");
const last = kernel(investigationChanges[investigationChanges.length - 1]);

async function horizontalOverflow(page: Page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

const nextAction = (page: Page) => page.locator('[data-block="next-action"] [data-next-action]');

for (const path of ["/today", "/investigations"]) {
  test(`the shipped ${path} shows no investigation data`, async ({ page }) => {
    await page.goto(path);
    const main = page.getByRole("main");
    await expect(main.getByRole("region").first()).toBeVisible();
    await expect(main).not.toContainText(first.question);
    await expect(main.locator("[data-investigations], [data-next-action]")).toHaveCount(0);
  });
}

test("Today shows every element of the current investigation, cleanly", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/fixtures/today");
  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: first.question })).toBeVisible();
  for (const name of ["workflow", "next-action", "uncertainty", "hypotheses", "missing-evidence", "verification"]) {
    await expect(page.locator(`[data-block="${name}"]`)).toBeVisible();
  }
  await expect(nextAction(page)).toHaveAttribute("data-next-action", first.next_action.kind);
  await expect(page.locator('[data-block="next-action"]')).toContainText(first.next_action.question);
  await expect(page.locator("[data-selected-source]")).toHaveText("Asking you one yes-or-no question");
  await expect(page.locator("[data-uncertainty]")).toHaveCount(first.uncertainty.length);
  const workflow = page.locator('[data-block="workflow"]');
  await expect(workflow.getByRole("status")).toContainText("Waiting for you");
  await expect(workflow.locator("[data-workflow-sequence]")).toHaveCount(first.phase_history.length);
  await expect(workflow.locator("[data-workflow-sequence]").first()).toBeVisible();
  // The default is expanded; keyboard users can collapse and reopen the history.
  await workflow.getByText("Steps Serene actually took", { exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(workflow.locator("[data-workflow-sequence]").first()).not.toBeVisible();
  await page.keyboard.press("Enter");
  await expect(workflow.locator("[data-workflow-sequence]").first()).toBeVisible();
  await workflow.screenshot({ path: testInfo.outputPath("recorded-workflow.png") });
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("changes arrive live, by keyboard, and the next action follows the policy", async ({ page }) => {
  await page.goto("/fixtures/investigations");
  await expect(nextAction(page)).toHaveAttribute("data-next-action", "WAIT_FOR_PARENT_ANSWER");
  const deliver = page.getByRole("button", { name: "Deliver next recorded change" });
  for (const change of recorded.changes) {
    await deliver.focus();
    await page.keyboard.press("Enter");
    if (change.projection === "investigations") {
      await expect(nextAction(page)).toHaveAttribute("data-next-action", kernel(change).next_action.kind);
      await expect(page.locator("article[data-investigation-id]")).toHaveAttribute("data-phase", kernel(change).phase);
      await expect(page.locator("[data-workflow-sequence]")).toHaveCount(kernel(change).phase_history.length);
    }
  }
  await expect(deliver).toBeDisabled();
  await expect(nextAction(page)).toHaveAttribute("data-next-action", last.next_action.kind);
  await expect(page.locator('[data-block="workflow"] [data-latest]')).toHaveAttribute("data-workflow-phase", last.phase);
});

test("a dropped connection is flagged, and reconnecting resyncs to the current state", async ({ page }) => {
  await page.goto("/fixtures/investigations");
  await expect(page.locator("article[data-investigation-id]")).toHaveAttribute("data-phase", first.phase);
  await page.getByRole("button", { name: "Drop connection" }).click();
  await expect(page.locator('[data-sync="reconnecting"]')).toContainText("may be out of date");
  // Nothing missed while disconnected is shown until the resync.
  await expect(page.locator("article[data-investigation-id]")).toHaveAttribute("data-phase", first.phase);
  await page.getByRole("button", { name: "Reconnect" }).click();
  await expect(page.locator('[data-sync="live"]')).toBeVisible();
  await expect(page.locator("article[data-investigation-id]")).toHaveAttribute("data-phase", last.phase);
  await expect(nextAction(page)).toHaveAttribute("data-next-action", last.next_action.kind);
});

test("no width from 360 to 1440 overflows", async ({ page }) => {
  await page.goto("/fixtures/investigations");
  await expect(nextAction(page)).toBeVisible();
  for (const width of [360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await horizontalOverflow(page), `at ${width}px`).toBeLessThanOrEqual(0);
  }
});
