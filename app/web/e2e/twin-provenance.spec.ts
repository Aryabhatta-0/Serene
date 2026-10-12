import { expect, test, type Page } from "@playwright/test";
import payload from "../fixtures/synthetic-twin-provenance.json";

// The provenance panel with the kernel's provenance projection (#39, #75), on
// a test-build-only route. The twin and projection are kernel output for a
// synthetic family (tests/twin_provenance_fixture.py).
const FIXTURE = "/fixtures/causal-twin-provenance";
const panel = (page: Page) => page.getByRole("complementary", { name: "Selected link" });
const list = (page: Page) => page.getByRole("region", { name: "Every link, by how firmly it is held" });

async function horizontalOverflow(page: Page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

// Named in the failure message, so an overflow says which element caused it.
async function overflowingElements(page: Page) {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return [...document.querySelectorAll("body *")]
      .filter((e) => e.getBoundingClientRect().right > width + 1)
      .slice(0, 5)
      .map((e) => `${e.tagName.toLowerCase()}.${String(e.className)} (right ${Math.round(e.getBoundingClientRect().right)}px)`);
  });
}

test("every link answers “why does Serene believe this?” down to raw evidence", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") errors.push(m.text());
  });
  await page.goto(FIXTURE);
  for (const edge of payload.provenance.edges) {
    await list(page).locator(`button[data-edge-id="${edge.edge_id}"]`).click();
    const full = panel(page).locator(`[data-provenance-for="${edge.edge_id}"][data-provenance="full"]`);
    await expect(full).toBeVisible();
    await expect(full.locator("[data-field=level]")).toContainText(`Level ${edge.epistemic_level} of 5`);
    await expect(full.locator("[data-field=complete]")).toContainText("Complete");
    await expect(full.locator('[data-chain="lineage"] > li')).toHaveCount(edge.lineage.steps.length);
    for (const evd of edge.lineage.raw_evidence) {
      await expect(full.locator(`[data-chain="lineage"] [data-node-id="${evd}"]`)).toHaveAttribute(
        "data-node-kind",
        "EVIDENCE",
      );
    }
    for (const x of edge.experiments) {
      for (const o of x.outcomes) {
        await expect(full.locator(`[data-outcome-id="${o.outcome_id}"]`)).toHaveAttribute(
          "data-from-experiment",
          x.experiment_id,
        );
      }
    }
    await expect(full.locator("[data-missing-node]")).toHaveCount(0);
    // Every provenance link resolves to an entry on the page.
    const hrefs = await full.locator("a[data-provenance-link]").evaluateAll((links) =>
      links.map((a) => a.getAttribute("href")!.slice(1)),
    );
    expect(hrefs.length).toBeGreaterThan(0);
    for (const target of hrefs) await expect(page.locator(`[id="${target}"]`)).toHaveCount(1);
  }

  // External evidence, and the level-5 learning's review dates.
  const learned = payload.provenance.edges.find((e) => e.epistemic_level === 5)!;
  await list(page).locator(`button[data-edge-id="${learned.edge_id}"]`).click();
  const full = panel(page).locator(`[data-provenance-for="${learned.edge_id}"]`);
  await expect(full.locator('[data-evidence-detail="external"]')).toContainText("example.org");
  await expect(full.locator("[data-field=review-after] time")).toHaveAttribute("datetime", learned.validity!.review_after);
  await expect(full.locator("[data-field=review-status]")).toBeVisible();

  // Following a link lands on its entry.
  const first = full.locator('[data-chain="lineage"] a[data-provenance-link]').first();
  const target = (await first.getAttribute("href"))!;
  await first.click();
  await expect(page).toHaveURL(new RegExp(`${target}$`));
  await expect(page.locator(`[id="${target.slice(1)}"]`)).toBeInViewport();

  expect(await horizontalOverflow(page), (await overflowingElements(page)).join("; ")).toBeLessThanOrEqual(0);
  await panel(page).screenshot({ path: testInfo.outputPath(`twin-provenance-${testInfo.project.name}.png`) });
  expect(errors).toEqual([]);
});
