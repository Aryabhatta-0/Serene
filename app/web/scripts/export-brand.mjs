// Exports the Serene brand assets from the running app, so the files always
// match what the components draw. The logo is the bloom's hellebore, built
// from the photographic petal in public/brand/bloom/:
//   app/icon.png                   192px icon (browsers and Android)
//   app/apple-icon.png             180px home-screen icon (full square)
//   app/favicon.ico                16px and 32px, for clients that ignore PNG icons
//   public/brand/serene-mark.png   512px logo
//   public/brand/serene-bloom.jpg  the landing bloom on the ruled sheet
//
// Usage: npm run build && npm run start, then in another shell:
//   node scripts/export-brand.mjs [base-url]   (default http://127.0.0.1:3000)

import { writeFileSync } from "node:fs";
import { chromium } from "@playwright/test";

const base = process.argv[2] ?? "http://127.0.0.1:3000";
const browser = await chromium.launch();

// Opens a page with the intro skipped (any key ends it), so every flower is
// captured fully open. The logo is taken from a surface, where the bar is
// drawn; the bloom from the landing page, the only place it grows.
async function open(path, viewport, deviceScaleFactor) {
  const context = await browser.newContext({ viewport, deviceScaleFactor });
  const page = await context.newPage();
  await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
  await page.keyboard.press("Shift");
  await page.evaluate(() => Promise.all([...document.images].map((img) => img.decode())));
  return page;
}

// The logo, alone on a transparent page, at `size` pixels square.
// `square` lays it on the paper (iOS rounds the corners itself).
async function renderMark(size, square) {
  const page = await open("/today", { width: 64, height: 64 }, size / 32);
  await page.evaluate((square) => {
    const mark = document.querySelector("[data-brand-mark]");
    document.body.replaceChildren(mark);
    // The logo is the flower alone. Only the home-screen icon (a full square
    // that iOS would otherwise fill with black) lies on the warm paper.
    mark.style.cssText = `position:fixed;inset:0 auto auto 0;width:32px;height:32px;${square ? "background:#e0dfd8" : ""}`;
    const style = document.createElement("style");
    style.textContent = "html,body{background:transparent!important}body::before{display:none!important}";
    document.head.append(style);
  }, square);
  const png = await page.locator("[data-brand-mark]").screenshot({ omitBackground: true });
  await page.context().close();
  return png;
}

// An ICO may carry PNGs directly: a 6-byte header, then a 16-byte entry each.
function ico(images) {
  const header = Buffer.alloc(6 + images.length * 16);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  let offset = header.length;
  images.forEach(({ size, png }, i) => {
    const entry = 6 + i * 16;
    header.writeUInt8(size, entry);
    header.writeUInt8(size, entry + 1);
    header.writeUInt16LE(1, entry + 4);
    header.writeUInt16LE(32, entry + 6);
    header.writeUInt32LE(png.length, entry + 8);
    header.writeUInt32LE(offset, entry + 12);
    offset += png.length;
  });
  return Buffer.concat([header, ...images.map(({ png }) => png)]);
}

try {
  writeFileSync("app/icon.png", await renderMark(192, false));
  writeFileSync("app/apple-icon.png", await renderMark(180, true));
  writeFileSync("public/brand/serene-mark.png", await renderMark(512, false));
  writeFileSync(
    "app/favicon.ico",
    ico([
      { size: 16, png: await renderMark(16, false) },
      { size: 32, png: await renderMark(32, false) },
    ]),
  );

  // The bloom on its sheet, without the plate's words.
  const page = await open("/", { width: 1440, height: 900 }, 2);
  await page.addStyleTag({
    content: "main header :is(h1, p, button), main header::after { visibility: hidden }",
  });
  const scene = page.locator("[data-bloom-art]");
  const box = await scene.boundingBox();
  const sheet = await page.locator("main header").first().boundingBox();
  // The scene overhangs the plate; keep its middle, down to the plate's foot.
  const clip = {
    x: box.x + box.width * 0.15,
    y: Math.max(sheet.y, box.y + box.height * 0.1),
    width: box.width * 0.75,
    height: sheet.y + sheet.height - Math.max(sheet.y, box.y + box.height * 0.1),
  };
  writeFileSync(
    "public/brand/serene-bloom.jpg",
    await page.screenshot({ clip, type: "jpeg", quality: 90 }),
  );
  await page.context().close();

  console.log("Exported brand assets.");
} finally {
  await browser.close();
}
