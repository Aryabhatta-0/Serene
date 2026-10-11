// Page extensions for the Next.js build. `page.fixture.tsx` routes render
// synthetic data for the browser tests; they exist only when the build is
// made with SERENE_FIXTURE_ROUTES=1 (see playwright.config.ts), so a normal
// production build contains no fixture page and no fixture data.
/** @param {{ SERENE_FIXTURE_ROUTES?: string }} env */
export function pageExtensions(env = process.env) {
  const base = ["tsx", "ts", "jsx", "js"];
  return env.SERENE_FIXTURE_ROUTES === "1" ? ["fixture.tsx", ...base] : base;
}
