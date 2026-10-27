'use strict';
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const results = [];
function check(name, fn) { try { fn(); results.push({ name, ok: true }); } catch (error) { results.push({ name, ok: false, detail: String(error.stack || error) }); } }
async function main() {
  const html = `<form id="deviceProfileForm"><input name="ios"><select name="device"><option value=""></option><option value="iphone">iPhone</option></select><select name="client"><option value=""></option><option value="sidestore">SideStore</option></select><button type="submit">Save</button><span id="deviceProfileMessage"></span></form>
  <p id="compat" data-device-compat='{"minOSVersion":"16.0","devices":["iphone"],"clients":["sidestore"]}'></p>
  <form data-resign-slug="demo"><input type="date" name="signed"><select name="kind"><option value="free">Free</option><option value="paid">Paid</option></select><button data-resign-clear type="button">Clear</button><button data-resign-remind type="button">Remind</button><span data-resign-message></span></form>
  <section id="sourceMigration"><form><input type="url" name="sourceUrl"><input type="file" name="sourceFile"><button type="submit">Compare</button></form><p data-migration-status></p><ul data-migration-results></ul></section>`;
  const dom = new JSDOM(html, { url: 'https://example.test/install/', runScripts: 'outside-only' });
  const w = dom.window;
  w.TextDecoder = TextDecoder;
  w.eval(fs.readFileSync('js/device.js', 'utf8'));
  w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
  const d = w.OmniDevice;
  check('version comparison is numeric', () => { assert.equal(d.compareVersions('16.10', '16.9'), 1); assert.equal(d.compareVersions('bad', '16'), null); });
  check('known incompatible versions do not match', () => assert.equal(d.evaluate({ minOSVersion: '17' }, { ios: '16.4' }).status, 'no'));
  check('missing declarations remain unknown', () => assert.equal(d.evaluate({}, { ios: '16' }).status, 'unknown'));
  check('declared match is qualified', () => { const x = d.evaluate({ minOSVersion: '16', devices: ['iphone'] }, { ios: '16.4', device: 'iphone' }); assert.equal(x.status, 'yes'); assert.match(x.reason, /not guaranteed/i); });
  check('expiry rejects impossible dates and marks the day reached', () => { assert.equal(d.expiry('2026-02-30', 'free'), null); assert.equal(d.expiry('2026-01-01', 'free', Date.parse('2026-01-01T00:00:00Z')).date, '2026-01-08'); assert.equal(d.expiry('2026-01-01', 'free', Date.parse('2026-01-08T12:00:00Z')).expired, true); });
  check('profile saves locally and updates declared compatibility', () => {
    const form = w.document.getElementById('deviceProfileForm'); form.elements.ios.value = '16.4'; form.elements.device.value = 'iphone'; form.elements.client.value = 'sidestore';
    form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
    assert.equal(d.profile().ios, '16.4'); assert.match(w.document.getElementById('compat').textContent, /matches/);
  });
  check('re-sign estimates can be saved and cleared', () => {
    const form = w.document.querySelector('[data-resign-slug]'); form.elements.signed.value = '2026-10-01';
    form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
    assert.match(form.querySelector('[data-resign-message]').textContent, /Estimated expiry/);
    form.querySelector('[data-resign-clear]').click(); assert.match(form.querySelector('[data-resign-message]').textContent, /No valid/);
  });
  check('storage denial is handled', () => {
    Object.defineProperty(w, 'localStorage', { configurable: true, get() { throw new Error('denied'); } });
    const form = w.document.getElementById('deviceProfileForm'); form.dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
    assert.match(w.document.getElementById('deviceProfileMessage').textContent, /unavailable/);
  });
  function response(doc) {
    const bytes = new TextEncoder().encode(JSON.stringify(doc)); let sent = false;
    return { ok: true, headers: { get() { return null; } }, body: { getReader() { return { async read() { if (sent) return { done: true }; sent = true; return { done: false, value: bytes }; }, releaseLock() {}, async cancel() {} }; } } };
  }
  w.fetch = async (url) => String(url).includes('apps.json') ? response({ apps: [{ name: 'Known', bundleIdentifier: 'com.test.app', version: '2.0' }] }) : response({ apps: [
    { name: 'Known', bundleIdentifier: 'com.test.app', version: '1.0' }, { name: '<img src=x onerror=alert(1)>', bundleIdentifier: 'com.other.app' }
  ] });
  w.eval(fs.readFileSync('js/source-migration.js', 'utf8'));
  const migration = w.document.querySelector('#sourceMigration'); migration.querySelector('[name="sourceUrl"]').value = 'https://other.test/source.json';
  migration.querySelector('form').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await new Promise(resolve => setTimeout(resolve, 20));
  check('migration uses local bundle comparison with qualified version information', () => {
    assert.match(migration.querySelector('[data-migration-status]').textContent, /1 entries share.*1 do not/);
    assert.match(migration.textContent, /numerically newer/); assert.match(migration.textContent, /can be alternatives/);
  });
  check('migration renders source names as text, not markup', () => { assert.equal(migration.querySelectorAll('img').length, 0); assert.match(migration.textContent, /<img/); });
  check('migration creates only an explicit review link', () => assert.match(migration.querySelector('ul a').href, /^https:\/\/github\.com\/raynmahbub\/OmniSource\/issues\/new\?/));
  w.close();
  console.log(JSON.stringify({ checks: results.length, results }));
  if (results.some(r => !r.ok)) process.exitCode = 1;
}
main().catch(error => { console.error(error); process.exitCode = 1; });
