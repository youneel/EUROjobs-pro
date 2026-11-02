/**
 * Generates the 1024px App Store icon and 2732px splash sources.
 * Run: npm run generate:icon
 */
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const here = dirname(fileURLToPath(import.meta.url));
const resources = join(here, "..", "resources");
await mkdir(resources, { recursive: true });

const ring = (cx, cy, r, dots = 12) =>
  Array.from({ length: dots }, (_, i) => {
    const angle = (Math.PI * 2 * i) / dots - Math.PI / 2;
    return `<circle cx="${(cx + Math.cos(angle) * r).toFixed(2)}" cy="${(cy + Math.sin(angle) * r).toFixed(2)}" r="34" fill="url(#ring)"/>`;
  }).join("");

const icon = `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0b1220"/>
      <stop offset="0.55" stop-color="#12233d"/>
      <stop offset="1" stop-color="#1d3f6b"/>
    </linearGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f5f5f7"/>
      <stop offset="0.5" stop-color="#8ecbff"/>
      <stop offset="1" stop-color="#0a84ff"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.42" r="0.55">
      <stop offset="0" stop-color="#0a84ff" stop-opacity="0.42"/>
      <stop offset="1" stop-color="#0a84ff" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1024" height="1024" fill="url(#bg)"/>
  <rect width="1024" height="1024" fill="url(#glow)"/>
  ${ring(512, 512, 330)}
  <circle cx="512" cy="512" r="196" fill="#0b1220" stroke="#2b4d7a" stroke-width="10"/>
  <g stroke="#f5f5f7" stroke-width="40" stroke-linecap="round">
    <path d="M430 452h164"/>
    <path d="M430 512h118"/>
    <path d="M430 572h118"/>
  </g>
  <circle cx="512" cy="842" r="26" fill="#0a84ff"/>
</svg>`;

const splash = `<svg xmlns="http://www.w3.org/2000/svg" width="2732" height="2732" viewBox="0 0 2732 2732">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0b1220"/>
      <stop offset="1" stop-color="#16294a"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.42" r="0.5">
      <stop offset="0" stop-color="#0a84ff" stop-opacity="0.35"/>
      <stop offset="1" stop-color="#0a84ff" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f5f5f7"/>
      <stop offset="0.5" stop-color="#8ecbff"/>
      <stop offset="1" stop-color="#0a84ff"/>
    </linearGradient>
  </defs>
  <rect width="2732" height="2732" fill="url(#bg)"/>
  <rect width="2732" height="2732" fill="url(#glow)"/>
  <g transform="translate(1366 1246) scale(1.05) translate(-512 -512)">
    ${ring(512, 512, 330)}
    <circle cx="512" cy="512" r="196" fill="#0b1220" stroke="#2b4d7a" stroke-width="10"/>
    <g stroke="#f5f5f7" stroke-width="40" stroke-linecap="round">
      <path d="M430 452h164"/>
      <path d="M430 512h118"/>
      <path d="M430 572h118"/>
    </g>
  </g>
  <text x="1366" y="2020" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="128" font-weight="700" fill="#f5f5f7" letter-spacing="-2">WorkAtlas</text>
  <text x="1366" y="2150" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="64" fill="#a1a1a6">Visa-sponsoring jobs, worldwide</text>
</svg>`;

await writeFile(join(resources, "icon.svg"), icon, "utf8");
await writeFile(join(resources, "splash.svg"), splash, "utf8");
await sharp(Buffer.from(icon)).png().toFile(join(resources, "icon.png"));
await sharp(Buffer.from(icon)).png().toFile(join(resources, "icon-only.png"));
await sharp(Buffer.from(splash)).png().toFile(join(resources, "splash.png"));
await sharp(Buffer.from(splash)).png().toFile(join(resources, "splash-dark.png"));

console.log("Wrote resources/icon.png (1024) and resources/splash.png (2732)");
