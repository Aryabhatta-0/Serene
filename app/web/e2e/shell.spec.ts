import { expect, test, type Page } from "@playwright/test";

const SURFACES = [
  { path: "/today", label: "Today" },
  { path: "/memory", label: "Memory" },
  { path: "/investigations", label: "Investigations" },
  { path: "/experiments", label: "Experiments" },
  { path: "/causal-twin", label: "Causal Twin" },
] as const;

// The navigation visible at the current viewport. On phones it lives in the
// menu sheet, which has to be opened first.
async function openNav(page: Page) {
  const menu = page.getByRole("button", { name: "Surfaces" });
  if (await menu.isVisible()) {
    await menu.click();
    await expect(page.getByRole("dialog")).toBeVisible();
  }
  return page.getByRole("navigation", { name: "Surfaces" });
}

test("the landing page opens onto Today, then the bar fills in", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Serene" })).toBeVisible();
  // The bar is held empty until Serene is entered.
  await expect(page.getByRole("navigation", { name: "Surfaces" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Surfaces" })).toBeHidden();

  await page.getByRole("button", { name: "Enter Serene" }).click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
  const nav = await openNav(page);
  await expect(nav.getByRole("link")).toHaveCount(SURFACES.length);
});

test("the shell exposes exactly the five surfaces", async ({ page }) => {
  await page.goto("/today");
  const nav = await openNav(page);
  const links = nav.getByRole("link");
  await expect(links).toHaveCount(SURFACES.length);
  await expect(links).toHaveText(SURFACES.map((s) => new RegExp(`^${s.label}`)));
});

test("navigation reaches every surface and marks it current", async ({ page }) => {
  await page.goto("/today");
  for (const surface of [...SURFACES].reverse()) {
    const nav = await openNav(page);
    await nav.getByRole("link", { name: new RegExp(`^${surface.label}`) }).click();
    await expect(page).toHaveURL(new RegExp(`${surface.path}$`));
    await expect(
      page.getByRole("heading", { level: 1, name: surface.label }),
    ).toBeVisible();
    await expect(page.getByRole("dialog")).toBeHidden();

    const current = (await openNav(page)).locator('[aria-current="page"]');
    await expect(current).toHaveCount(1);
    await expect(current).toHaveAttribute("href", surface.path);
    await page.keyboard.press("Escape");
  }
});

test("no surface renders fabricated data", async ({ page }) => {
  for (const surface of SURFACES) {
    await page.goto(surface.path);
    const main = page.getByRole("main");
    // Every surface is an honest empty state until projections are connected.
    await expect(main.getByRole("region").first()).toBeVisible();
    // No counts, dates, times, percentages or identifiers of any kind.
    await expect(main).not.toContainText(/\d/);
    await expect(main.locator("table, canvas")).toHaveCount(0);
    // The bloom is the landing page's alone; a surface draws no images.
    await expect(main.locator("img")).toHaveCount(0);
    await expect(page.locator("[data-bloom-art]")).toHaveCount(0);
  }
});

test("keyboard users can skip straight to the content", async ({ page }) => {
  await page.goto("/memory");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
});

test("the logo and favicon are the bloom's hellebore", async ({ page, request }) => {
  await page.goto("/");
  // The same photographic petal builds the landing bloom and the logo.
  const petal = 'img[src="/brand/bloom/petal.webp"]';
  await expect(page.locator(`[data-bloom-art] ${petal}`)).toHaveCount(10);
  await expect(page.locator("[data-brand-mark]").first().locator(petal)).toHaveCount(5);
  await expect(page.locator(petal).first()).toHaveJSProperty("complete", true);

  for (const href of ["/favicon.ico", "/brand/bloom/petal.webp", "/brand/bloom/bud.webp"]) {
    expect((await request.get(href)).ok()).toBe(true);
  }
  const icon = page.locator('head link[rel="icon"][type="image/png"]');
  expect((await request.get((await icon.getAttribute("href"))!)).ok()).toBe(true);
});

test("the bloom plays on the landing page only and gives way to any input", async ({ page }) => {
  const html = page.locator("html");
  await page.goto("/");
  await expect(html).toHaveAttribute("data-bloom", "play");
  // Pressing anything ends the intro at once; nobody has to wait it out.
  await page.keyboard.press("Shift");
  await expect(html).not.toHaveAttribute("data-bloom", /.*/);

  await page.goto("/today");
  await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
  await expect(html).not.toHaveAttribute("data-bloom", /.*/);
});
