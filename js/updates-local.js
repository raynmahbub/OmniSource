/* Optional local release baseline; nothing is sent to OmniSource. */
(function () {
  'use strict';
  var root = document.getElementById('localUpdates');
  if (!root) return;
  var key = 'omnisource:updates-baseline:v1', updates = [];
  var status = root.querySelector('[data-updates-status]'), list = root.querySelector('[data-updates-list]');
  var save = root.querySelector('[data-updates-save]'), clear = root.querySelector('[data-updates-clear]');
  function itemKey(item) { return String(item.slug || '') + '\u0000' + String(item.version || ''); }
  function show() {
    var stored;
    try { stored = JSON.parse(localStorage.getItem(key) || 'null'); } catch (_) { stored = null; }
    list.replaceChildren();
    if (!Array.isArray(stored)) { status.textContent = 'Not enabled. Save the current snapshot to compare it on a later visit.'; return; }
    var previous = new Set(stored), fresh = updates.filter(function (item) { return !previous.has(itemKey(item)); });
    status.textContent = fresh.length + ' release entries are not in your saved snapshot. This compares the latest 100 entries; it is not a complete history.';
    fresh.slice(0, 10).forEach(function (item) {
      var li = document.createElement('li'), slug = String(item.slug || '');
      if (/^[a-z0-9][a-z0-9-]*$/.test(slug)) {
        var a = document.createElement('a'); a.href = 'apps/' + encodeURIComponent(slug) + '/'; a.textContent = String(item.name || slug); li.appendChild(a);
      } else li.textContent = String(item.name || 'App');
      li.appendChild(document.createTextNode(' — ' + String(item.version || 'unknown version'))); list.appendChild(li);
    });
  }
  save.addEventListener('click', function () {
    if (!updates.length) { status.textContent = 'The release snapshot is unavailable; nothing was saved.'; return; }
    try { localStorage.setItem(key, JSON.stringify(updates.map(itemKey))); show(); status.textContent = 'Current release snapshot saved on this browser only.'; }
    catch (_) { status.textContent = 'Browser storage is unavailable.'; }
  });
  clear.addEventListener('click', function () {
    try { localStorage.removeItem(key); show(); } catch (_) { status.textContent = 'Browser storage is unavailable.'; }
  });
  fetch('feeds/updates.json').then(function (r) { if (!r.ok) throw new Error('unavailable'); return r.json(); }).then(function (doc) {
    updates = Array.isArray(doc.updates) ? doc.updates.filter(function (item) { return item && item.slug && item.version; }).slice(0, 100) : [];
    show();
  }).catch(function () { status.textContent = 'Release snapshot unavailable.'; });
  var subscriptions = root.querySelector('[data-subscriptions]');
  fetch('feeds/subscriptions.json').then(function (r) { if (!r.ok) throw new Error('unavailable'); return r.json(); }).then(function (doc) {
    (Array.isArray(doc.subscriptions) ? doc.subscriptions : []).forEach(function (item) {
      if (!item || !/^[a-z0-9/-]+\.(xml|ics)$/.test(String(item.path || ''))) return;
      var li = document.createElement('li'), a = document.createElement('a'); a.href = 'feeds/' + item.path; a.textContent = String(item.name || item.path); li.appendChild(a); subscriptions.appendChild(li);
    });
  }).catch(function () { subscriptions.textContent = 'Subscription index unavailable.'; });
})();
