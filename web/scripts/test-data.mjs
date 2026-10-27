// Execute the real data.ts against the generated JSON snapshots without
// adding a second test framework. TypeScript transpiles its JSON imports to
// require(), so Node's normal module loader can run the actual helpers.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire, Module } from "node:module";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const filename = fileURLToPath(new URL("../src/lib/data.ts", import.meta.url));
const source = readFileSync(filename, "utf8");
const { outputText } = ts.transpileModule(source, {
  fileName: filename,
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS,
    esModuleInterop: true,
    resolveJsonModule: true,
  },
});
const loaded = new Module(filename);
loaded.filename = filename;
loaded.paths = Module._nodeModulePaths(dirname(filename));
loaded._compile(outputText, filename);
const data = loaded.exports;

const entries = data.getAppsWithIds();
assert.equal(entries.length, 128, "the complete catalog is addressable");
assert.equal(new Set(entries.map((entry) => entry.id)).size, entries.length, "route IDs are unique");

const live = data.getAppById("livecontainer");
assert.equal(live?.name, "LiveContainer", "friendly catalog slug resolves");
assert.equal(
  data.getAppById("com.kdt.livecontainer"),
  live,
  "legacy bundle-Identifier URL remains compatible",
);
assert.equal(data.getAppById("not-an-app"), undefined);
assert.equal(entries.find(({ app }) => app === live)?.id, "livecontainer");

// Correcting BHInstagram's bundle ID adds it to an existing collision group.
// Historical URLs must keep resolving to their original entries, not the new
// alphabetical first match.
for (const [legacyId, slug] of [
  ["com.burbn.instagram", "inkillerplus"],
  ["com.burbn.instagram-2", "ryukgram"],
  ["com.burbn.instagram-3", "ryukgram-ig410"],
  ["com.burbn.instagram-4", "bhinstagram"],
]) {
  assert.equal(data.getAppById(legacyId)?.omnisource?.slug, slug, `${legacyId} remains stable`);
}
assert.equal(data.getAppById("bhinstagram")?.bundleIdentifier, "com.burbn.instagram");

const screenshots = data.getAppScreenshots(live);
assert.equal(screenshots.length, 1);
assert.equal(screenshots[0].url, "/assets/screenshots/livecontainer/livecontainer-01.png");
assert.equal(
  screenshots[0].thumbnailURL,
  "/assets/screenshots/thumbnails/livecontainer/livecontainer-01.webp",
);
assert.match(screenshots[0].originalURL, /LiveContainer\/LiveContainer\/main\/screenshots\/release\.png$/);
assert.equal(data.getAppScreenshots(data.getAppById("ytmusic")).length, 3);

console.log(`test-data: ${entries.length} unique app routes; slug + legacy IDs and screenshot manifests OK`);
