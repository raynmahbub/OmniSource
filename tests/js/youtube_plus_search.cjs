'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const discovery = { apps: [
  { slug: 'ytlite', name: 'YouTube Plus', bundleIdentifier: 'com.google.ios.youtube' },
  { slug: 'other', name: 'Other App', bundleIdentifier: 'com.example.other' }
] };
const context = {
  window: {},
  document: {
    querySelector: () => null,
    currentScript: null,
    documentElement: { dataset: { omniNoBoot: '1' } }
  },
  console,
  fetch: async url => ({ ok: true, json: async () => String(url).endsWith('discovery.json') ? discovery : {} })
};
vm.createContext(context);
for (const path of ['src/js/data-layer.js', 'src/js/search-engine.js']) {
  vm.runInContext(fs.readFileSync(path, 'utf8'), context, { filename: path });
}

async function main() {
  await context.window.OmniData.load();
  await context.window.OmniSearch.boot();
  const aliases = context.window.OmniData.getAliases().reverse;
  for (const query of ['yt lite', 'youtube lite', 'youtubelite', 'youtubeplus', 'youtube plus']) {
    assert.ok(aliases[query].includes('ytlite'), `${query} must target the stable slug`);
    const results = context.window.OmniSearch.search(query);
    assert.ok(results.some(result => result.app.slug === 'ytlite'), `${query} must find YouTube Plus`);
  }
  assert.equal(context.window.OmniData.getApp('ytlite').name, 'YouTube Plus');
  console.log('YouTube Plus search aliases passed');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
