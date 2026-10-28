'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { JSDOM, VirtualConsole } = require('jsdom');
const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const core = fs.readFileSync(path.join(root, 'js/core.js'), 'utf8');
const site = fs.readFileSync(path.join(root, 'js/site.js'), 'utf8');
const ipa = 'https://example.test/current.ipa';
const results = [];
function check(name, fn) {
  try { fn(); results.push({ name, ok: true }); }
  catch (error) { results.push({ name, ok: false, detail: String(error.stack || error) }); }
}
async function boot(health) {
  const dom = new JSDOM(html, {
    url: 'https://example.test/#demo',
    runScripts: 'outside-only',
    pretendToBeVisual: true,
    virtualConsole: new VirtualConsole(),
  });
  const w = dom.window;
  w.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
  w.requestIdleCallback = () => 1;
  w.Element.prototype.scrollIntoView = () => {};
  w.eval(core);
  const app = {
    name: 'Demo', bundleIdentifier: 'com.example.demo', developerName: 'Developer',
    version: '2.0', versionDate: '2026-10-28', size: 1024, downloadURL: ipa,
    versions: [{ version: '2.0', date: '2026-10-28', downloadURL: ipa, size: 1024 }],
    omnisource: { slug: 'demo', status: 'stable', compatibility: {} },
  };
  w.OS.fetchJSON = async (url) => {
    if (url === 'apps.json' || url === 'feeds/apps.json') return { apps: [app] };
    if (url === 'feeds/health.json') return { apps: [{ slug: 'demo', ...health }] };
    return null;
  };
  w.eval(site);
  await new Promise(resolve => setTimeout(resolve, 180));
  return dom;
}
async function main() {
  const failed = await boot({ downloadReachable: false, checkedURL: ipa, lastCheckedAt: '<img src=x>' });
  let content = failed.window.document.getElementById('dialogContent');
  check('a matching failed probe is visible next to the download button', () => {
    assert.match(content.textContent, /Last download check failed/);
    assert.match(content.textContent, /this IPA link may not work/);
  });
  check('unknown permissions are explicitly described as unrecorded', () => {
    assert.match(content.textContent, /Not recorded; the IPA may still request permissions/);
  });
  check('untrusted probe dates cannot inject markup', () => {
    assert.match(content.textContent, /<img src=x>/);
    assert.equal(content.querySelectorAll('img[src="x"]').length, 0);
  });
  failed.window.close();

  const stale = await boot({ downloadReachable: false, checkedURL: 'https://example.test/old.ipa', lastCheckedAt: '2026-10-27' });
  content = stale.window.document.getElementById('dialogContent');
  check('a probe of a different IPA does not warn on the new link', () => {
    assert.doesNotMatch(content.textContent, /Last download check failed/);
    assert.match(content.textContent, /Not checked/);
  });
  stale.window.close();

  const unknown = await boot({ downloadReachable: false, lastCheckedAt: '2026-10-27' });
  content = unknown.window.document.getElementById('dialogContent');
  check('a probe without its checked URL is treated as unknown', () => {
    assert.doesNotMatch(content.textContent, /Last download check failed/);
    assert.match(content.textContent, /Not checked/);
  });
  unknown.window.close();
  console.log(JSON.stringify({ checks: results.length, results }));
  if (results.some(result => !result.ok)) process.exitCode = 1;
}
main().catch(error => { console.error(error); process.exitCode = 1; });
