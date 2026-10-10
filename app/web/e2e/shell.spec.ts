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

test("the root address opens Today", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
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
    await expect(main.locator("table, img, canvas")).toHaveCount(0);
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
