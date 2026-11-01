/**
 * Writes the tiny local web shell used by Capacitor for the offline fallback,
 * and keeps the Associated Domains entitlement in sync with EJP_APP_URL.
 *
 * The hosted FastAPI deployment is configured through EJP_APP_URL. The iOS
 * shell cannot run Python on the device.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const www = join(root, "www");
const appUrl = (process.env.EJP_APP_URL || "https://app.eurojobs.pro").replace(/\/+$/, "");
const host = new URL(appUrl).hostname;

await mkdir(www, { recursive: true });

await writeFile(
  join(www, "config.js"),
  `window.EJP_APP_URL = ${JSON.stringify(appUrl)};\n`,
  "utf8"
);

// Universal links and shared web credentials must name the same host that
// serves the site. Rewriting the entitlement here avoids a stale domain in the
// archive when EJP_APP_URL changes.
const entitlementsDir = join(root, "ios", "App", "App");
if (existsSync(entitlementsDir)) {
  const entitlements = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>com.apple.developer.associated-domains</key>
\t<array>
\t\t<string>applinks:${host}</string>
\t\t<string>webcredentials:${host}</string>
\t</array>
</dict>
</plist>
`;
  await writeFile(join(entitlementsDir, "App.entitlements"), entitlements, "utf8");
}

console.log(`Local shell prepared for ${appUrl}`);
