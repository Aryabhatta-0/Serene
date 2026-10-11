import { expect, test, type Page } from "@playwright/test";
import example from "../fixtures/approval-command.example.json";
import payload from "../fixtures/synthetic-experiments.json";

// Experiments are shown from the synthetic fixture on a test-build-only
// route, with a scripted stand-in for the kernel transport (?answer=...).
// The shipped surface (/experiments) has no record and no transport.
const FIXTURE = "/fixtures/experiments";
const PHASES = [
  "PROPOSED",
  "CLASSIFIED",
  "BLOCKED",
  "AWAITING_APPROVAL",
  "APPROVED",
  "WAITING_FOR_OUTCOME",
  "OUTCOME_OVERDUE",
  "COMPLETED",
  "ABANDONED",
  "PARKED_UNRESOLVED",
];
const green = payload.experiments.find((e) => e.phase === "AWAITING_APPROVAL" && e.safety_class === "GREEN")!;

async function horizontalOverflow(page: Page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

async function sentCommands(page: Page) {
  return JSON.parse((await page.locator("[data-sent-commands]").getAttribute("data-sent-commands")) ?? "[]");
}

test("the shipped surface shows no experiments and no decision", async ({ page }) => {
  await page.goto("/experiments");
  await expect(page.getByRole("heading", { name: "No experiments proposed" })).toBeVisible();
  const main = page.getByRole("main");
  for (const e of payload.experiments) await expect(main).not.toContainText(e.intervention.description);
  await expect(main.locator("[data-experiment-id]")).toHaveCount(0);
  await expect(main.getByRole("button")).toHaveCount(0);
});

test("every lifecycle stage is shown, cleanly", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(FIXTURE);
  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.locator("[data-fixture-banner]")).toBeVisible();
  for (const phase of PHASES) await expect(page.locator(`article[data-phase="${phase}"]`).first()).toBeVisible();
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test("RED is visibly blocked and has no approve control", async ({ page }) => {
  await page.goto(FIXTURE);
  const red = page.locator('article[data-safety="RED"]');
  await expect(red).toHaveCount(1);
  await expect(red.locator("[data-safety-label]")).toHaveText("Risk: Not allowed");
  await expect(red.locator('[data-decision="not-approvable"]')).toContainText("This cannot be approved");
  await expect(red.getByRole("button")).toHaveCount(0);
  // Only open requests can be decided, and none of them is RED.
  const approve = page.getByRole("button", { name: "Approve", exact: true });
  await expect(approve).toHaveCount(2);
  for (const article of await page.locator("article:has(button)").all()) {
    await expect(article).toHaveAttribute("data-phase", "AWAITING_APPROVAL");
    await expect(article).not.toHaveAttribute("data-safety", "RED");
  }
});

test("approving by keyboard sends the shown request and shows the kernel's answer", async ({ page }) => {
  await page.goto(`${FIXTURE}?answer=granted`);
  const article = page.locator(`article[data-experiment-id="${green.experiment_id}"]`);
  await article.getByRole("button", { name: "Approve", exact: true }).focus();
  await page.keyboard.press("Enter");
  const confirm = article.getByRole("button", { name: "Yes, approve" });
  await expect(confirm).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(article.getByRole("status")).toContainText("Serene recorded your approval.");

  const [sent] = await sentCommands(page);
  const { request_id, ...shown } = sent;
  const { request_id: _exampleId, ...expected } = example;
  expect(shown).toEqual(expected); // the same command the kernel's channel test applies
  expect(request_id).toMatch(/^[A-Za-z0-9_-]{16,64}$/);
  // The stage is not changed by the page; only Serene's record changes it.
  await expect(article).toHaveAttribute("data-phase", "AWAITING_APPROVAL");
});

test("a refusal or a failure is never shown as success", async ({ page }) => {
  for (const [answer, text] of [
    ["refused", "Serene did not record this decision."],
    ["unreadable", "could not be confirmed"],
    ["offline", "could not be confirmed"],
  ]) {
    await page.goto(`${FIXTURE}?answer=${answer}`);
    const article = page.locator(`article[data-experiment-id="${green.experiment_id}"]`);
    await article.getByRole("button", { name: "Approve", exact: true }).click();
    await article.getByRole("button", { name: "Yes, approve" }).click();
    await expect(article.getByRole("status")).toContainText(text);
    await expect(article).not.toContainText("recorded your approval");
  }
});

test("no width from 360 to 1440 overflows", async ({ page }) => {
  await page.goto(FIXTURE);
  for (const width of [360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await horizontalOverflow(page), `at ${width}px`).toBeLessThanOrEqual(0);
  }
});
