import { expect, test, type Locator, type Page } from "@playwright/test";
import payload from "../fixtures/synthetic-causal-twin.json";

// The map is drawn from the synthetic fixture on a test-build-only route; the
// shipped surface (/causal-twin) has no record connected and draws nothing.
const FIXTURE = "/fixtures/causal-twin";
const HYP = (n: number) => `hyp_${n.toString(16).padStart(32, "0")}`;
const CATEGORIES = ["tested", "observed", "hypothesis", "refuted", "superseded"] as const;

const map = (page: Page) => page.locator(".react-flow");
const mapLabel = (page: Page, id: string) => map(page).locator(`button[data-edge-id="${id}"]`);
const panel = (page: Page) => page.getByRole("complementary", { name: "Selected link" });
const list = (page: Page) => page.getByRole("region", { name: "Every link, by how firmly it is held" });

function viewportTransform(page: Page) {
  return page.locator(".react-flow__viewport").evaluate((el) => getComputedStyle(el).transform);
}

// The view once an animation has finished: two reads in a row agree.
async function settledTransform(page: Page) {
  let last = "";
  await expect
    .poll(async () => {
      const now = await viewportTransform(page);
      const settled = now === last && now !== "none" && now !== "";
      last = now;
      return settled;
    })
    .toBe(true);
  return last;
}

// Whether a link's label lies inside the map's frame (the map itself may be
// scrolled out of the browser's view).
async function expectInsideMap(page: Page, label: Locator) {
  await expect
    .poll(async () => {
      const [frame, box] = [await map(page).boundingBox(), await label.boundingBox()];
      if (!frame || !box) return false;
      return (
        box.x >= frame.x && box.y >= frame.y &&
        box.x + box.width <= frame.x + frame.width && box.y + box.height <= frame.y + frame.height
      );
    })
    .toBe(true);
}

async function horizontalOverflow(page: Page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

test("the shipped surface draws no map and no fixture data", async ({ page }) => {
  await page.goto("/causal-twin");
  await expect(page.getByRole("heading", { name: "No links to draw yet" })).toBeVisible();
  await expect(map(page)).toHaveCount(0);
  const main = page.getByRole("main");
  for (const edge of payload.edges) await expect(main).not.toContainText(edge.relationship);
  await expect(main.locator("[data-provenance-for]")).toHaveCount(0);
  await expect(main).not.toContainText(/(hyp|evd|obs|out|exp|pat)_[0-9a-f]{32}/);
});

test("the map draws every category distinctly and keeps refuted links", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto(FIXTURE);
  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.locator("[data-fixture-banner]")).toBeVisible();
  await expect(map(page)).toBeVisible();

  const drawn = new Set<string>();
  for (const category of CATEGORIES) {
    const group = map(page).locator(`g[data-category="${category}"]`).first();
    await expect(group).toBeAttached();
    const line = await group.locator("path[data-stroke]").evaluate((el) => {
      const s = getComputedStyle(el);
      return [s.strokeDasharray, s.strokeWidth, s.stroke].join("|");
    });
    const struck = await group.locator("[data-strike]").count();
    const hollow = await group.locator("[data-hollow]").count();
    drawn.add(`${line}|${struck}|${hollow}`);
    // Each link is fitted into view and named by its category.
    await expectInsideMap(page, map(page).locator(`button[data-category="${category}"]`).first());
  }
  expect(drawn.size).toBe(CATEGORIES.length);

  // No label covers another label or a variable.
  const boxes = await map(page)
    .locator(".react-flow__edgelabel-renderer button, [data-variable]")
    .evaluateAll((els) => els.map((el) => el.getBoundingClientRect().toJSON() as DOMRect));
  for (const [i, a] of boxes.entries()) {
    for (const b of boxes.slice(i + 1)) {
      const apart =
        a.right <= b.left + 1 || b.right <= a.left + 1 || a.bottom <= b.top + 1 || b.bottom <= a.top + 1;
      expect(apart, `${JSON.stringify(a)} overlaps ${JSON.stringify(b)}`).toBe(true);
    }
  }

  // Refuted: on the map, visible and struck through, never removed.
  await expect(mapLabel(page, HYP(4))).toBeVisible();
  await expect(mapLabel(page, HYP(4))).toContainText("Refuted");
  const refuted = map(page).locator(`g[data-edge-id="${HYP(4)}"]`);
  await expect(refuted.locator("[data-strike]")).toHaveCount(1);
  const box = await refuted.locator("path[data-stroke]").boundingBox();
  expect(box!.width + box!.height).toBeGreaterThan(20);

  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  await page.screenshot({
    path: testInfo.outputPath(`causal-twin-${testInfo.project.name}.png`),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("selecting a link names it for the provenance panel", async ({ page }) => {
  await page.goto(FIXTURE);
  await expect(panel(page)).not.toHaveAttribute("data-selected-edge-id", /.*/);

  await mapLabel(page, HYP(1)).click();
  await expect(panel(page)).toHaveAttribute("data-selected-edge-id", HYP(1));
  await expect(panel(page)).toContainText("Tested in context");
  await expect(panel(page)).toContainText(HYP(1));
  await expect(mapLabel(page, HYP(1))).toHaveAttribute("aria-pressed", "true");

  // From the list, by keyboard: the map moves to show the chosen link.
  await list(page).locator(`button[data-edge-id="${HYP(4)}"]`).focus();
  await page.keyboard.press("Enter");
  await expect(panel(page)).toHaveAttribute("data-selected-edge-id", HYP(4));
  await expect(panel(page)).toContainText("Refuted");
  await expectInsideMap(page, mapLabel(page, HYP(4)));

  await panel(page).getByRole("button", { name: "Clear" }).click();
  await expect(panel(page)).not.toHaveAttribute("data-selected-edge-id", /.*/);
});

test("links on the map can be reached and chosen from the keyboard", async ({ page }) => {
  await page.goto(FIXTURE);
  await expect(map(page)).toBeVisible();
  let focused: string | null = null;
  for (let i = 0; i < 40 && !focused; i++) {
    await page.keyboard.press("Tab");
    focused = await page.evaluate(() => {
      const active = document.activeElement;
      return active?.closest(".react-flow") ? active.getAttribute("data-edge-id") : null;
    });
  }
  expect(focused).toMatch(/^hyp_/);
  await page.keyboard.press("Enter");
  await expect(panel(page)).toHaveAttribute("data-selected-edge-id", focused!);
});

test("choosing any link from the list brings its label into view", async ({ page }) => {
  await page.goto(FIXTURE);
  await expect(map(page)).toBeVisible();
  for (const edge of payload.edges.filter((e) => e.cause !== null)) {
    await list(page).locator(`button[data-edge-id="${edge.edge_id}"]`).click();
    await expect(panel(page)).toHaveAttribute("data-selected-edge-id", edge.edge_id);
    await expectInsideMap(page, mapLabel(page, edge.edge_id));
    await panel(page).getByRole("button", { name: "Clear" }).click();
  }
});

test("zoom and fit-to-view move the map", async ({ page }) => {
  await page.goto(FIXTURE);
  await expect(map(page)).toBeVisible();
  const fitted = await settledTransform(page);
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect.poll(() => viewportTransform(page)).not.toBe(fitted);
  await page.getByRole("button", { name: "Fit to view" }).click();
  await expect.poll(() => viewportTransform(page)).toBe(fitted);
  await page.getByRole("button", { name: "Zoom out" }).click();
  await expect.poll(() => viewportTransform(page)).not.toBe(fitted);
});

test("on a phone the map reads top to bottom and the panel follows it", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "phone layout only");
  for (const width of [390, 360]) {
    await page.setViewportSize({ width, height: 800 });
    await page.goto(FIXTURE);
    // Narrow screens read causes top to bottom.
    await expect(page.locator('[data-direction="TB"] .react-flow')).toBeVisible();
    const canvas = (await map(page).boundingBox())!;
    expect(canvas.width).toBeLessThanOrEqual(width);
    const side = (await panel(page).boundingBox())!;
    expect(side.y).toBeGreaterThanOrEqual(canvas.y + canvas.height);
    const cause = (await map(page).locator('[data-variable="screens_after_dinner"]').boundingBox())!;
    const effect = (await map(page).locator('[data-variable="bedtime_resistance"]').boundingBox())!;
    expect(effect.y).toBeGreaterThan(cause.y);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  }
});

// The provenance panel (#39): why Serene holds the selected link this way.
const provenance = (page: Page) => panel(page).locator("[data-provenance-for]");
const section = (page: Page, name: string) => panel(page).getByRole("region", { name });

test("the provenance panel follows the selected link and its lineage", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") errors.push(m.text());
  });
  await page.goto(FIXTURE);
  await expect(provenance(page)).toHaveCount(0);

  await mapLabel(page, HYP(1)).click();
  await expect(provenance(page)).toHaveAttribute("data-provenance-for", HYP(1));
  await expect(section(page, "Evidence for it").locator("[data-entity-id]")).toHaveCount(3);
  await expect(section(page, "Where and when it holds")).toContainText("Review after");
  await expect(section(page, "Where and when it holds").locator("time")).toHaveCount(2);

  // A different link has different evidence.
  await mapLabel(page, HYP(4)).click();
  await expect(provenance(page)).toHaveAttribute("data-provenance-for", HYP(4));
  await expect(section(page, "Evidence against it")).toContainText("Experiment outcome: contradicts it");
  await expect(section(page, "Evidence for it")).not.toContainText("evd_00000000000000000000000000000001");

  // Replaced link -> its replacement, chosen from the panel: the map follows.
  await list(page).locator(`button[data-edge-id="${HYP(5)}"]`).click();
  await expect(section(page, "Why it is drawn this way")).toContainText("better-formed version");
  await section(page, "Replaced and replacing").locator(`button[data-edge-ref="${HYP(1)}"]`).click();
  await expect(panel(page)).toHaveAttribute("data-selected-edge-id", HYP(1));
  await expect(mapLabel(page, HYP(1))).toHaveAttribute("aria-pressed", "true");
  await expectInsideMap(page, mapLabel(page, HYP(1)));
  await expect(section(page, "Why it is drawn this way").getByRole("heading")).toBeFocused();
  await expect(section(page, "Replaced and replacing").locator(`button[data-edge-ref="${HYP(5)}"]`)).toBeVisible();

  // Nothing in the panel overflows the page, at any width.
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  const sheet = (await panel(page).boundingBox())!;
  expect(sheet.x + sheet.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  await panel(page).screenshot({ path: testInfo.outputPath(`provenance-${testInfo.project.name}.png`) });
  expect(errors).toEqual([]);
});

test("the provenance panel opens and closes from the keyboard", async ({ page }) => {
  await page.goto(FIXTURE);
  const item = list(page).locator(`button[data-edge-id="${HYP(6)}"]`);
  await item.focus();
  await page.keyboard.press("Enter");
  await expect(provenance(page)).toHaveAttribute("data-provenance-for", HYP(6));
  await expect(section(page, "Evidence against it")).toContainText("Observation against it");

  await panel(page).getByRole("button", { name: "Clear" }).focus();
  await page.keyboard.press("Escape");
  await expect(panel(page)).not.toHaveAttribute("data-selected-edge-id", /.*/);
  await expect(item).toBeFocused();
});
