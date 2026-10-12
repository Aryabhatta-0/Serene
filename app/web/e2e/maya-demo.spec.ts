import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

const root = resolve(process.cwd(), "../..");
function run(script: string) {
  execFileSync("uv", ["run", "python", `scripts/${script}.py`], {
    cwd: root, timeout: 180_000, windowsHide: true,
  });
}
function report() {
  return JSON.parse(readFileSync(resolve(root, ".demo/maya/report.json"), "utf8"));
}

test("canonical reset → Maya → report → rendered UI, then regeneration without restarting web", async ({ page, request }, testInfo) => {
  test.setTimeout(600_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  run("demo_reset");
  await page.goto("/demo/maya");
  const reportAlert = page.getByRole("alert").filter({ hasText: "Canonical Maya report" });
  await expect(reportAlert).toContainText("unavailable or invalid", { timeout: 40_000 });
  run("maya_demo");
  const canonical = report();
  await page.getByRole("button", { name: "Reload generated report" }).click();
  await expect(page.locator("[data-report-sha]")).toBeVisible({ timeout: 40_000 });
  const firstReceipt = await page.locator("[data-artifact-modified]").textContent();
  const firstHash = await page.locator("[data-report-sha]").textContent();
  const api = await request.get("/demo/maya/state");
  expect(api.headers()["cache-control"]).toBe("no-store");
  const state = await api.json();
  expect(state.twin_after).toEqual(canonical.twin_after);
  expect(state.event_count).toBe(canonical.events.length);

  await expect(page.getByRole("heading", { name: "Today", exact: true })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Demo mode" })).toContainText("DEMO MODE — synthetic Maya scenario");
  const investigation = page.locator(`[data-investigation-id="${canonical.investigation_id}"]`);
  await expect(investigation).toHaveAttribute("data-phase", canonical.phase);
  await expect(investigation.locator("[data-uncertainty=COMPETING_EXPLANATIONS]")).toBeVisible();
  await expect(investigation.locator("[data-next-action=NONE_COMPLETE]")).toBeVisible();
  for (const h of state.investigations[canonical.investigation_id].hypotheses) {
    await expect(investigation.getByText(h.statement, { exact: true })).toBeVisible();
  }
  for (const status of ["VERIFIED", "REJECTED"]) {
    const expected = state.investigations[canonical.investigation_id].evidence_requests
      .flatMap((r: { evidence: { verification_status: string }[] }) => r.evidence)
      .filter((e: { verification_status: string }) => e.verification_status === status).length;
    await expect(investigation.locator(`[data-verification=${status}]`)).toHaveCount(expected);
    await expect(investigation.locator(`[data-verification=${status}]`).first()).toBeVisible();
  }
  await expect(investigation).toContainText("EXCERPT_NOT_ON_SOURCE");
  const missing = state.snapshots.findIndex((s: { investigations: Record<string, { phase: string }> }) => s.investigations[canonical.investigation_id]?.phase === "ASKING_HUMAN");
  expect(missing).toBeGreaterThanOrEqual(0);
  await page.getByLabel("Recorded investigation checkpoint").selectOption(String(missing));
  await expect(investigation.locator("[data-next-action=WAIT_FOR_PARENT_ANSWER]")).toBeVisible();
  await expect(investigation.locator("[data-selected-source=ASK_PARENT]")).toBeVisible();
  await page.getByLabel("Recorded investigation checkpoint").selectOption("-1");

  const experiment = state.experiments.experiments[0];
  const card = page.locator(`[data-experiment-id="${experiment.experiment_id}"]`);
  await expect(card).toHaveAttribute("data-phase", experiment.phase);
  await expect(card).toHaveAttribute("data-safety", experiment.safety_class);
  await expect(card.getByRole("region", { name: "Approval", exact: true })).toContainText("Approved");
  await expect(card.getByRole("region", { name: "Approval", exact: true })).toContainText("Telegram");
  await expect(card.locator("[data-result]")).toContainText(experiment.outcomes[0].summary);
  await expect(page.locator("#demo-experiment > ul > [data-promotion]")).toHaveCount(2);
  for (const patch of state.memory.patches) {
    const item = page.locator(`[data-patch-id="${patch.patch_id}"]`);
    await expect(item).toHaveAttribute("data-status", patch.status);
    await expect(item).toContainText(patch.target_path);
    for (const reason of patch.rejection_reasons) await expect(item).toContainText(reason);
  }
  await expect(page.locator("#demo-memory")).toContainText(state.memory.memories[0].body);
  const supported = state.twin_after.edges.find((e: { status: string }) => e.status === "SUPPORTED");
  await expect(page.locator("#demo-twin div[data-category=tested] button")).toHaveCount(1);
  await page.locator(`#demo-twin button[data-edge-id="${supported.edge_id}"]`).click();
  await expect(page.locator(`[data-provenance-for="${supported.edge_id}"]`)).toContainText(`Level ${supported.epistemic_level} of 5`);
  await page.getByLabel("Show recorded before state").check();
  await expect(page.locator("#demo-twin")).toContainText("Before experiment");
  await expect(page.locator("#demo-twin div[data-category=tested] button")).toHaveCount(0);
  await page.getByLabel("Show recorded before state").uncheck();

  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator("[data-report-sha]")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
  await page.screenshot({ path: testInfo.outputPath("maya-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: testInfo.outputPath("maya-desktop.png"), fullPage: true });

  run("demo_reset");
  await page.getByRole("button", { name: "Reload generated report" }).click();
  await expect(reportAlert).toBeVisible({ timeout: 40_000 });
  await expect(page.locator("[data-experiment-id]")).toHaveCount(0);
  run("maya_demo");
  await page.getByRole("button", { name: "Reload generated report" }).click();
  await expect(page.locator("[data-report-sha]")).toHaveText(firstHash!, { timeout: 40_000 });
  await expect(page.locator("[data-artifact-modified]")).not.toHaveText(firstReceipt!);
  await expect(page.locator("[data-experiment-id]")).toHaveAttribute("data-phase", "COMPLETED");
  expect(report()).toEqual(canonical);
  expect(errors).toEqual([]);
  await page.goto("/today");
  await expect(page.getByText("No family record connected")).toBeVisible();
  await expect(page.getByText("Nothing to review today")).toBeVisible();
});
