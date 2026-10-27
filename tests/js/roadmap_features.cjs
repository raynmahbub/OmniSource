'use strict';
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const results = [];
function check(name, fn) { try { fn(); results.push({ name, ok: true }); } catch (error) { results.push({ name, ok: false, detail: String(error.stack || error) }); } }
const markup = `
  <section id="appGuide"><form><input name="keywords"><select name="category"><option value=""></option><option value="music">music</option></select><select name="provenance"><option value=""></option><option value="official">official</option></select><input type="checkbox" name="reachable"></form><p data-guide-status></p><ul data-guide-results></ul></section>
  <section id="localUpdates"><button data-updates-save>save</button><button data-updates-clear>clear</button><p data-updates-status></p><ul data-updates-list></ul><ul data-subscriptions></ul></section>
  <section id="variantPicker"><select name="group"></select><select name="choice"></select><span data-variant-url></span><a data-variant-link></a><button data-variant-copy>copy</button><p data-variant-message></p></section>`;
const catalog = { apps: [
  { name: '<img src=x onerror=alert(1)>', category: 'music', subtitle: 'play music', omnisource: { slug: 'demo', health: { downloadReachable: true }, compatibility: { minOSVersion: '16' } } },
  { name: 'Other', category: 'music', subtitle: 'play music', omnisource: { slug: 'other', health: { downloadReachable: false } } }
] };
const verification = { apps: [{ app: 'demo', provenance: 'official' }, { app: 'other', provenance: 'community' }] };
const subscriptions = { subscriptions: [{ name: 'Calendar', path: 'updates.ics' }, { name: 'unsafe', path: '../../bad.xml' }] };
const variants = { groups: [{ bundleIdentifier: 'com.example.same', choices: [
  { name: 'Demo', url: 'https://example.test/feeds/variants/demo.json' }, { name: 'Bad', url: 'javascript:alert(1)' }
] }] };
async function boot(saved, updates) {
  const dom = new JSDOM(markup, { url: 'https://example.test/', runScripts: 'outside-only' });
  const w = dom.window;
  if (saved) w.localStorage.setItem('omnisource:updates-baseline:v1', saved);
  w.OmniDevice = { profile: () => ({ ios: '16' }), evaluate: () => ({ status: 'unknown' }) };
  w.fetch = async (url) => ({ ok: true, json: async () => String(url).includes('verification') ? verification : String(url).includes('updates.json') ? { updates } : String(url).includes('subscriptions') ? subscriptions : String(url).includes('variants') ? variants : catalog });
  ['js/app-guide.js', 'js/updates-local.js', 'js/variant-picker.js'].forEach(file => w.eval(fs.readFileSync(file, 'utf8')));
  await new Promise(resolve => setTimeout(resolve, 10));
  return dom;
}
async function main() {
  const first = await boot(null, [{ slug: 'demo', name: 'Demo', version: '1' }]);
  const w = first.window;
  const form = w.document.querySelector('#appGuide form');
  form.elements.keywords.value = 'play music'; form.elements.provenance.value = 'official'; form.elements.reachable.checked = true;
  form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await new Promise(resolve => setTimeout(resolve, 10));
  check('guide filters declared source and last recorded health', () => { assert.match(w.document.querySelector('[data-guide-status]').textContent, /1 matching/); assert.equal(w.document.querySelectorAll('[data-guide-results] li').length, 1); });
  check('guide treats missing compatibility as unknown and does not render HTML', () => { const list = w.document.querySelector('[data-guide-results]'); assert.match(list.textContent, /unknown/); assert.equal(list.querySelectorAll('img').length, 0); });
  check('updates are opt-in', () => assert.match(w.document.querySelector('[data-updates-status]').textContent, /Not enabled/));
  w.document.querySelector('[data-updates-save]').click();
  check('updates save only a local baseline', () => assert.match(w.document.querySelector('[data-updates-status]').textContent, /saved on this browser/));
  check('subscription index rejects traversal', () => assert.equal(w.document.querySelectorAll('[data-subscriptions] a').length, 1));
  check('variant picker selects a source', () => assert.match(w.document.querySelector('[data-variant-url]').textContent, /^https:\/\//));
  w.document.querySelector('[name="choice"]').value = '1';
  w.document.querySelector('[name="choice"]').dispatchEvent(new w.Event('change'));
  check('variant picker rejects non-HTTPS links', () => assert.equal(w.document.querySelector('[data-variant-link]').hidden, true));
  const saved = w.localStorage.getItem('omnisource:updates-baseline:v1');
  first.window.close();
  const second = await boot(saved, [{ slug: 'demo', name: '<b>Demo</b>', version: '2' }, { slug: 'demo', version: '1' }]);
  check('later visit compares current releases to saved baseline', () => { assert.match(second.window.document.querySelector('[data-updates-status]').textContent, /^1 release/); assert.equal(second.window.document.querySelector('[data-updates-list] b'), null); });
  second.window.document.querySelector('[data-updates-clear]').click();
  check('baseline can be cleared', () => assert.equal(second.window.localStorage.getItem('omnisource:updates-baseline:v1'), null));
  second.window.close();
  console.log(JSON.stringify({ checks: results.length, results }));
  if (results.some(r => !r.ok)) process.exitCode = 1;
}
main().catch(error => { console.error(error); process.exitCode = 1; });
