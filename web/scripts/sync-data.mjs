// Copy pipeline outputs into web/ so the app builds and runs anywhere
// (Vercel / Cloudflare / self-hosted) without reaching outside its dir.
// Runs automatically via the `prebuild` / `predev` npm hooks.
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, "..");
const root = join(web, "..");

function copy(relSrc, relDst) {
  const src = join(root, relSrc);
  const dst = join(web, relDst);
  if (!existsSync(src)) {
    console.warn(`sync-data: missing ${relSrc} (skipped)`);
    return false;
  }
  mkdirSync(dirname(dst), { recursive: true });
  copyFileSync(src, dst);
  return true;
}

// Server-bundled snapshots (imported by src/lib/data.ts).
const serverDocs = [
  "apps.json",
  "discovery.json",
  "sources.json",
  "collections.json",
  "status.json",
  "analytics.json",
  "search-index.json",
  "reputation.json",
];
for (const name of serverDocs) copy(join("feeds", name), join("src", "data", name));
for (const name of ["security.json", "source_reputation.json", "analytics_rollup.json", "canonical_apps.json"]) {
  copy(join("data", name), join("src", "data", name));
}
copy("catalog.json", "src/data/catalog.json");

// Serve every reviewed app logo from this website's own origin. The catalog
// stores normalized artwork copied from app-owned project assets; the feed
// keeps its canonical absolute iconURL for clients and APIs, while the Next.js
// UI uses /assets/<file>. A missing logo is a build error, never a silent
// letter/brand-placeholder substitution.
const catalog = JSON.parse(readFileSync(join(root, "catalog.json"), "utf8"));
const artwork = new Set([
  ...(catalog.apps ?? []).map((app) => app.icon),
  ...(catalog.clients ?? []).map((client) => client.icon),
]);
for (const filename of artwork) {
  if (typeof filename !== "string" || !/^[A-Za-z0-9._-]+\.(?:webp|png|jpe?g)$/i.test(filename)) {
    throw new Error(`sync-data: invalid catalog artwork filename: ${String(filename)}`);
  }
  if (!copy(join("assets", filename), join("public", "assets", filename))) {
    throw new Error(`sync-data: required official artwork is missing: assets/${filename}`);
  }
}
console.log(`sync-data: ${artwork.size} app/client logos copied from catalog artwork`);

// Client-fetchable API snapshot (powers /search offline + PWA caching).
copy("api/v3/apps.json", "public/data/v3/apps.json");
copy("api/v3/search-index.json", "public/data/v3/search-index.json");
copy("api/v3/status.json", "public/data/v3/status.json");

// Build stamp for the footer / diagnostics.
const stamp = { syncedAt: new Date().toISOString(), root: "OmniSource" };
mkdirSync(join(web, "src", "data"), { recursive: true });
writeFileSync(join(web, "src", "data", "_sync.json"), JSON.stringify(stamp, null, 2) + "\n");

// Sanity: the catalog snapshot must exist or the build cannot render.
const appsRaw = readFileSync(join(web, "src", "data", "apps.json"), "utf8");
const apps = JSON.parse(appsRaw).apps ?? [];
const feedSlugs = new Set(apps.map((app) => app.omnisource?.slug).filter(Boolean));
const missingApps = (catalog.apps ?? []).filter((app) => !feedSlugs.has(app.slug));
if (missingApps.length) {
  throw new Error(`sync-data: catalog apps missing a matching official-artwork feed record: ${missingApps.map((app) => app.slug).join(", ")}`);
}
console.log(`sync-data: ${apps.length} apps synced into web/`);
