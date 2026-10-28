'use strict';
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const results = [];
function check(name, fn) { try { fn(); results.push({ name, ok: true }); } catch (error) { results.push({ name, ok: false, detail: String(error.stack || error) }); } }
async function tick() { await new Promise(resolve => setTimeout(resolve, 20)); }
async function main() {
  const markup = `
    <section id="appGuide"><form>
      <select name="group"><option value="">All</option><option value="com.google.ios.youtube">YouTube</option></select>
      <input name="guideIos"><select name="guideClient"><option value="">Saved</option><option value="altstore">AltStore</option></select>
      <input type="checkbox" name="capability" value="no-ads"><input type="checkbox" name="capability" value="picture-in-picture">
      <input name="keywords"><select name="category"><option value="">All</option></select><select name="provenance"><option value="">All</option></select><input type="checkbox" name="reachable">
    </form><p data-guide-status></p><ul data-guide-results></ul></section>
    <a href="#whats-new">Updates <span data-updates-nav hidden></span></a>
    <section id="localUpdates"><button data-updates-save>save</button><button data-updates-clear>clear</button><input type="checkbox" data-updates-auto><p data-updates-status></p><ul data-updates-list></ul><ul data-subscriptions></ul></section>
    <article class="app-card" data-slug="demo"><div class="card-badges"></div></article>
    <article class="app-card" data-app-id="unknown"><div class="card-badges"></div></article>
    <section id="resignTracker"><p data-resign-summary></p><ul data-resign-list></ul><input type="checkbox" data-resign-icon><button data-resign-clear-all>clear</button><button data-resign-disable>disable</button></section>
    <form data-resign-slug="demo"><input type="date" name="signed"><select name="kind"><option value="free">Free</option><option value="paid">Paid</option></select><button data-resign-clear type="button">Clear</button><button data-resign-remind type="button">Remind</button><button data-resign-disable type="button">Disable</button><span data-resign-message></span></form>`;
  const dom = new JSDOM(markup, { url: 'https://example.test/OmniSource/', runScripts: 'outside-only' });
  const w = dom.window;
  const current = new Date();
  const signed = new Date(current.getTime() - 6 * 86400000).toISOString().slice(0, 10);
  w.localStorage.setItem('omnisource:resign:v1', JSON.stringify({ demo: { date: signed, kind: 'free' } }));
  w.localStorage.setItem('omnisource:updates-baseline:v1', JSON.stringify(['demo\u00001']));
  w.localStorage.setItem('omnisource:device-profile:v1', JSON.stringify({ ios: '16', client: 'altstore' }));
  let notifications = 0, iconCount = null, cleared = 0;
  function Notification() { notifications++; }
  Notification.permission = 'granted'; Notification.requestPermission = async () => 'granted';
  w.Notification = Notification;
  w.navigator.setAppBadge = n => { iconCount = n; return Promise.resolve(); };
  w.navigator.clearAppBadge = () => { cleared++; iconCount = 0; return Promise.resolve(); };
  const shared = { bundleIdentifier: 'com.google.ios.youtube', category: 'photo-video', version: '1', minOSVersion: '16', downloadURL: 'https://example.test/a.ipa' };
  const catalog = { apps: [
    { ...shared, name: 'Reviewed', omnisource: { slug: 'demo', compatibility: { minOSVersion: '15', clients: ['altstore'] }, health: { downloadReachable: true, checkedURL: 'https://example.test/a.ipa' }, features: ['no-ads', 'picture-in-picture'], featuresReviewed: { version: '1', downloadURL: 'https://example.test/a.ipa' }, bestFor: 'Playback controls' } },
    { ...shared, name: '<img src=x onerror=alert(1)>', downloadURL: 'https://example.test/b.ipa', omnisource: { slug: 'unknown', compatibility: { minOSVersion: '16', clients: ['altstore'] }, health: { downloadReachable: true, checkedURL: 'https://example.test/old.ipa' }, features: ['no-ads', 'picture-in-picture'], featuresReviewed: { version: '1', downloadURL: 'https://example.test/old.ipa' } } },
    { ...shared, name: 'Incompatible', minOSVersion: '17', omnisource: { slug: 'incompatible', compatibility: { minOSVersion: '15', clients: ['altstore'] }, features: ['no-ads'], featuresReviewed: { version: '1', downloadURL: 'https://example.test/a.ipa' } } }
  ] };
  const updates = [{ slug: 'demo', name: 'Reviewed', version: '2' }, { slug: 'demo', name: 'Reviewed', version: '1' }];
  w.fetch = async url => ({ ok: true, json: async () => String(url).includes('verification') ? { apps: [] } : String(url).includes('updates.json') ? { updates } : String(url).includes('subscriptions') ? { subscriptions: [] } : catalog });
  ['js/device.js', 'js/updates-local.js', 'js/app-guide.js'].forEach(file => w.eval(fs.readFileSync(file, 'utf8')));
  w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
  await tick();
  check('re-sign countdown appears on cards and in the local summary', () => {
    assert.match(w.document.querySelector('[data-slug="demo"] [data-resign-badge]').textContent, /Re-sign:/);
    assert.match(w.document.querySelector('[data-resign-list]').textContent, /demo/);
    assert.equal(w.document.querySelector('[data-app-id="unknown"] [data-resign-badge]'), null);
  });
  check('notifications and app-icon badge are opt-in', () => { assert.equal(notifications, 0); assert.equal(iconCount, 0); });
  const badge = w.document.querySelector('[data-resign-icon]'); badge.checked = true; badge.dispatchEvent(new w.Event('change'));
  await tick();
  check('opted-in icon badge counts due estimates', () => assert.equal(iconCount, 1));
  w.document.querySelector('[data-resign-remind]').click(); await tick();
  check('notification requires explicit opt-in and is limited to one daily summary', () => {
    assert.equal(notifications, 1);
    assert.equal(JSON.parse(w.localStorage.getItem('omnisource:resign-notifications:v1')).enabled, true);
  });
  w.document.dispatchEvent(new w.Event('visibilitychange')); await tick();
  check('revisiting the page does not repeat the daily notification', () => assert.equal(notifications, 1));
  check('snapshot difference decorates matching cards and navigation', () => {
    assert.match(w.document.querySelector('[data-slug="demo"] [data-update-badge]').textContent, /not in snapshot/);
    assert.equal(w.document.querySelector('[data-updates-nav]').textContent, '1');
    assert.equal(w.document.querySelector('[data-app-id="unknown"] [data-update-badge]'), null);
  });
  const form = w.document.querySelector('#appGuide form');
  form.elements.group.value = 'com.google.ios.youtube';
  form.querySelectorAll('[name="capability"]').forEach(node => { node.checked = true; });
  form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true })); await tick();
  check('guide ranks reviewed features and excludes newer minimum iOS', () => {
    const links = w.document.querySelectorAll('[data-guide-results] a');
    assert.equal(links.length, 2); assert.equal(links[0].textContent, 'Reviewed');
    assert.match(w.document.querySelector('[data-guide-status]').textContent, /1 excluded/);
    assert.match(links[0].parentNode.textContent, /2\/2 requested features described/);
  });
  check('stale asset declarations are unknown and text is not HTML', () => {
    const second = w.document.querySelectorAll('[data-guide-results] li')[1];
    assert.match(second.textContent, /not reviewed/); assert.equal(second.querySelector('img'), null);
  });
  form.elements.reachable.checked = true;
  form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true })); await tick();
  check('reachable filter requires a matching checked URL', () => assert.equal(w.document.querySelectorAll('[data-guide-results] li').length, 1));
  const auto = w.document.querySelector('[data-updates-auto]'); auto.checked = true; auto.dispatchEvent(new w.Event('change'));
  w.dispatchEvent(new w.Event('pagehide')); w.dispatchEvent(new w.Event('pageshow'));
  check('automatic last-visit snapshot is optional, local, and advances on leaving', () => {
    assert.equal(JSON.parse(w.localStorage.getItem('omnisource:updates-auto:v1')), true);
    assert.equal(w.document.querySelector('[data-update-badge]'), null);
    assert.equal(w.document.querySelector('[data-updates-nav]').hidden, true);
  });
  w.document.querySelector('[data-updates-clear]').click();
  check('clearing the update snapshot also disables automatic capture', () => {
    assert.equal(w.localStorage.getItem('omnisource:updates-baseline:v1'), null); assert.equal(auto.checked, false);
  });
  w.document.querySelector('[data-resign-clear-all]').click(); await tick();
  check('clearing signing dates removes countdowns and clears the icon badge', () => {
    assert.equal(w.document.querySelector('[data-resign-badge]'), null); assert.equal(iconCount, 0); assert.ok(cleared > 0);
  });
  w.close();
  const fav = new JSDOM('<body data-page="favorites"><a href="../#whats-new"><span data-updates-nav hidden></span></a><article class="app-card" data-app-id="demo"></article></body>', { url: 'https://example.test/OmniSource/favorites/', runScripts: 'outside-only' });
  const fw = fav.window;
  fw.localStorage.setItem('omnisource:updates-baseline:v1', JSON.stringify(['demo\u00001']));
  fw.localStorage.setItem('omnisource:updates-auto:v1', 'true');
  let requestedUrl = '';
  fw.fetch = async url => { requestedUrl = String(url); return { ok: true, json: async () => ({ updates }) }; };
  fw.eval(fs.readFileSync('js/updates-local.js', 'utf8')); await tick();
  check('favorites also show update badges without advancing the home-page baseline', () => {
    assert.equal(requestedUrl, '../feeds/updates.json');
    assert.match(fw.document.querySelector('[data-update-badge]').textContent, /not in snapshot/);
    fw.dispatchEvent(new fw.Event('pagehide'));
    assert.equal(fw.localStorage.getItem('omnisource:updates-baseline:v1'), JSON.stringify(['demo\u00001']));
  });
  fav.window.close();
  console.log(JSON.stringify({ checks: results.length, results }));
  if (results.some(r => !r.ok)) process.exitCode = 1;
}
main().catch(error => { console.error(error); process.exitCode = 1; });
