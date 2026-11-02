/**
 * Captures App Store screenshots from a running WorkAtlas deployment.
 *
 *   npm run screenshots                        # http://127.0.0.1:8000
 *   EJP_SCREENSHOT_URL=https://app.workatlas.pro npm run screenshots
 *
 * Requires Playwright with WebKit:
 *   npm install
 *   npx playwright install webkit
 *
 * Output: appstore/screenshots/iphone-6.9 and appstore/screenshots/iphone-6.5
 * Each image is exactly 1320x2868 or 1284x2778 (portrait, 3x).
 */
import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { webkit } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const outRoot = join(here, "screenshots");
const base = (process.env.EJP_SCREENSHOT_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

const sizes = {
  "iphone-6.9": { width: 440, height: 956, scale: 3 },
  "iphone-6.5": { width: 428, height: 926, scale: 3 }
};

const shots = [
  { name: "01-home", path: "/", theme: "light" },
  { name: "02-jobs", path: "/jobs", theme: "light" },
  { name: "03-job-detail", path: null, theme: "light" },
  { name: "04-visa-tiers", path: "/visa", theme: "light" },
  { name: "05-tools", path: "/tools", theme: "light" },
  { name: "06-arabic", path: "/jobs?lang=ar", theme: "dark", lang: "ar" }
];

const browser = await webkit.launch();

for (const [sizeName, size] of Object.entries(sizes)) {
  const outDir = join(outRoot, sizeName);
  await mkdir(outDir, { recursive: true });

  const context = await browser.newContext({
    viewport: { width: size.width, height: size.height },
    deviceScaleFactor: size.scale,
    isMobile: true,
    hasTouch: true,
    colorScheme: "light",
    locale: "en-GB",
    reducedMotion: "reduce"
  });

  await context.addInitScript((theme) => {
    try {
      localStorage.setItem("ejp-theme", theme);
    } catch (error) {
      /* private mode */
    }
  }, "light");

  const page = await context.newPage();

  // Resolve a real detail page from the list so the screenshot always matches
  // the current board instead of a hard-coded public id.
  await page.goto(`${base}/jobs?visa_tier=1`, { waitUntil: "networkidle" });
  const detailHref = await page.evaluate(() => {
    const link = document.querySelector('a[href^="/jobs/"]');
    return link ? link.getAttribute("href") : null;
  });

  for (const shot of shots) {
    const target = shot.path || detailHref;
    if (!target) {
      console.warn(`Skipping ${shot.name}: no listing found on the board.`);
      continue;
    }
    await page.goto(`${base}${target}`, { waitUntil: "networkidle" });
    await page.evaluate((theme) => {
      document.documentElement.dataset.theme = theme;
      try {
        localStorage.setItem("ejp-theme", theme);
      } catch (error) {}
      window.scrollTo(0, 0);
      return document.fonts && document.fonts.ready ? document.fonts.ready : null;
    }, shot.theme || "light");
    await page.waitForTimeout(350);
    const file = join(outDir, `${shot.name}.png`);
    await page.screenshot({ path: file, animations: "disabled", caret: "hide" });
    console.log(`${sizeName}/${shot.name}.png`);
  }

  await context.close();
}

await browser.close();
console.log(`Screenshots written to ${outRoot}`);
