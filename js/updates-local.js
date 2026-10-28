/* Optional local release baseline and badges. Nothing is sent to OmniSource. */
(function (global) {
  'use strict';
  var root = document.getElementById('localUpdates');
  var favorites = document.body && document.body.dataset.page === 'favorites';
  if (!root && !favorites) return;
  var prefix = favorites ? '../' : '';
  var key = 'omnisource:updates-baseline:v1', autoKey = 'omnisource:updates-auto:v1';
  var updates = [], fresh = [], loaded = false;
  var status = root && root.querySelector('[data-updates-status]'), list = root && root.querySelector('[data-updates-list]');
  var save = root && root.querySelector('[data-updates-save]'), clear = root && root.querySelector('[data-updates-clear]');
  var automatic = root && root.querySelector('[data-updates-auto]');
  function itemKey(item) { return String(item.slug || '') + '\u0000' + String(item.version || ''); }
  function get(key, fallback) { try { return JSON.parse(global.localStorage.getItem(key) || fallback); } catch (_) { return null; } }
  function write(key, value) { try { global.localStorage.setItem(key, JSON.stringify(value)); return true; } catch (_) { return false; } }
  function decorate(parent) {
    var slugs = new Set(fresh.map(function (item) { return String(item.slug || ''); }));
    (parent || document).querySelectorAll('.app-card[data-slug], .app-card[data-app-id]').forEach(function (card) {
      var slug = card.getAttribute('data-slug') || card.getAttribute('data-app-id');
      var badge = card.querySelector('[data-update-badge]');
      if (!slugs.has(slug)) {
        if (badge) badge.remove();
        var existing = card.querySelector('.card-badges');
        if (existing) existing.classList.toggle('has-local-badges', !!existing.querySelector('[data-resign-badge], [data-update-badge]'));
        return;
      }
      if (!badge) {
        var row = card.querySelector('.card-badges');
        if (!row) { row = document.createElement('div'); row.className = 'card-badges'; card.appendChild(row); }
        badge = document.createElement('span'); badge.setAttribute('data-update-badge', ''); badge.className = 'badge blue'; row.appendChild(badge);
      }
      badge.parentNode.classList.add('has-local-badges');
      badge.textContent = 'Release not in snapshot';
      badge.title = 'A release entry is absent from your local snapshot; this is not a complete history.';
    });
  }
  function show() {
    var stored = get(key, 'null');
    if (list) list.replaceChildren();
    fresh = [];
    if (!Array.isArray(stored)) {
      if (status) status.textContent = 'Not enabled. Save the current snapshot to compare it on a later visit.';
    } else {
      var previous = new Set(stored);
      fresh = updates.filter(function (item) { return !previous.has(itemKey(item)); });
      if (status) status.textContent = fresh.length + ' release entries are not in your saved snapshot. This compares the latest 100 entries; it is not a complete history.';
      if (list) fresh.slice(0, 10).forEach(function (item) {
        var li = document.createElement('li'), slug = String(item.slug || '');
        if (/^[a-z0-9][a-z0-9-]*$/.test(slug)) {
          var a = document.createElement('a'); a.href = 'apps/' + encodeURIComponent(slug) + '/'; a.textContent = String(item.name || slug); li.appendChild(a);
        } else li.textContent = String(item.name || 'App');
        li.appendChild(document.createTextNode(' — ' + String(item.version || 'unknown version'))); list.appendChild(li);
      });
    }
    document.querySelectorAll('[data-updates-nav]').forEach(function (node) {
      node.hidden = fresh.length === 0;
      node.textContent = fresh.length ? String(fresh.length) : '';
      node.setAttribute('aria-label', fresh.length + ' release entries not in your saved snapshot');
    });
    decorate(document);
    global.dispatchEvent(new global.CustomEvent('omni:updates-change'));
  }
  function saveSnapshot() {
    if (!loaded || !updates.length) { status.textContent = 'The release snapshot is unavailable; nothing was saved.'; return false; }
    if (!write(key, updates.map(itemKey))) { status.textContent = 'Browser storage is unavailable.'; return false; }
    show(); return true;
  }
  if (save) save.addEventListener('click', function () {
    if (saveSnapshot()) status.textContent = 'Current release snapshot saved on this browser only.';
  });
  if (clear) clear.addEventListener('click', function () {
    try {
      global.localStorage.removeItem(key); global.localStorage.removeItem(autoKey);
      if (automatic) automatic.checked = false;
      show();
    } catch (_) { status.textContent = 'Browser storage is unavailable.'; }
  });
  if (automatic) {
    automatic.checked = get(autoKey, 'false') === true;
    automatic.addEventListener('change', function () {
      if (automatic.checked && !Array.isArray(get(key, 'null')) && !saveSnapshot()) { automatic.checked = false; return; }
      if (!write(autoKey, automatic.checked)) { automatic.checked = false; status.textContent = 'Browser storage is unavailable.'; return; }
      status.textContent = automatic.checked ? 'The snapshot will be saved locally when you leave this page.' : 'Automatic snapshots are off; the saved baseline remains until cleared.';
    });
  }
  global.addEventListener('pagehide', function () {
    if (root && get(autoKey, 'false') === true && loaded && updates.length) write(key, updates.map(itemKey));
  });
  global.addEventListener('pageshow', show);
  global.addEventListener('storage', function (event) {
    if (event.key === key || event.key === autoKey) { if (automatic) automatic.checked = get(autoKey, 'false') === true; show(); }
  });
  global.OmniUpdates = { decorate: decorate, freshSlugs: function () { return fresh.map(function (item) { return String(item.slug || ''); }); } };
  fetch(prefix + 'feeds/updates.json').then(function (r) { if (!r.ok) throw new Error('unavailable'); return r.json(); }).then(function (doc) {
    if (!doc || !Array.isArray(doc.updates)) throw new Error('invalid snapshot');
    updates = doc.updates.filter(function (item) { return item && item.slug && item.version; }).slice(0, 100);
    loaded = true; show();
  }).catch(function () { if (status) status.textContent = 'Release snapshot unavailable.'; });
  var subscriptions = root && root.querySelector('[data-subscriptions]');
  if (subscriptions) fetch('feeds/subscriptions.json').then(function (r) { if (!r.ok) throw new Error('unavailable'); return r.json(); }).then(function (doc) {
    (Array.isArray(doc.subscriptions) ? doc.subscriptions : []).forEach(function (item) {
      if (!item || !/^[a-z0-9/-]+\.(xml|ics)$/.test(String(item.path || ''))) return;
      var li = document.createElement('li'), a = document.createElement('a'); a.href = 'feeds/' + item.path; a.textContent = String(item.name || item.path); li.appendChild(a); subscriptions.appendChild(li);
    });
  }).catch(function () { subscriptions.textContent = 'Subscription index unavailable.'; });
})(window);
