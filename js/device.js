/* Device profile and optional signing estimates stay on this browser. */
(function (global) {
  'use strict';
  var PROFILE = 'omnisource:device-profile:v1';
  var INSTALLED = 'omnisource:resign:v1';
  var NOTIFY = 'omnisource:resign-notifications:v1';
  var BADGE = 'omnisource:resign-badge:v1';
  var NOTIFIED = 'omnisource:resign-last-notified:v1';
  var DEVICES = ['iphone', 'ipad'];
  var CLIENTS = ['altstore', 'sidestore', 'flarestore', 'feather', 'esign', 'ksign', 'livecontainer'];
  var booted = false;
  function read(key) {
    try { var value = JSON.parse(global.localStorage.getItem(key) || '{}'); return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
    catch (_) { return {}; }
  }
  function save(key, value) {
    try { global.localStorage.setItem(key, JSON.stringify(value)); return true; }
    catch (_) { return false; }
  }
  function clean(profile) {
    profile = profile || {};
    return {
      ios: /^\d{1,3}(?:\.\d{1,3}){0,2}$/.test(String(profile.ios || '').trim()) ? String(profile.ios).trim() : '',
      device: DEVICES.indexOf(profile.device) >= 0 ? profile.device : '',
      client: CLIENTS.indexOf(profile.client) >= 0 ? profile.client : ''
    };
  }
  function compareVersions(a, b) {
    if (!/^\d+(?:\.\d+)*$/.test(String(a || '')) || !/^\d+(?:\.\d+)*$/.test(String(b || ''))) return null;
    var aa = String(a).split('.').map(Number), bb = String(b).split('.').map(Number);
    for (var i = 0; i < Math.max(aa.length, bb.length); i++) {
      if ((aa[i] || 0) !== (bb[i] || 0)) return (aa[i] || 0) > (bb[i] || 0) ? 1 : -1;
    }
    return 0;
  }
  function evaluate(compat, input) {
    compat = compat && typeof compat === 'object' ? compat : {};
    var profile = clean(input), unknown = [], selected = 0;
    if (profile.ios) {
      selected++;
      if (compat.minOSVersion) {
        var min = compareVersions(profile.ios, compat.minOSVersion);
        if (min === null) unknown.push('minimum iOS');
        else if (min < 0) return { status: 'no', reason: 'Needs iOS ' + compat.minOSVersion + '; selected ' + profile.ios + '.' };
      } else unknown.push('minimum iOS');
      if (compat.maxOSVersion) {
        var max = compareVersions(profile.ios, compat.maxOSVersion);
        if (max === null) unknown.push('maximum iOS');
        else if (max > 0) return { status: 'no', reason: 'Requires iOS ' + compat.maxOSVersion + ' or earlier.' };
      }
    }
    [['device', 'devices'], ['client', 'clients']].forEach(function (pair) {
      if (!profile[pair[0]]) return;
      selected++;
      var values = compat[pair[1]];
      if (!Array.isArray(values) || !values.length) unknown.push(pair[0]);
    });
    if (profile.device && Array.isArray(compat.devices) && compat.devices.length && compat.devices.indexOf(profile.device) < 0)
      return { status: 'no', reason: 'Device family is not listed as supported.' };
    if (profile.client && Array.isArray(compat.clients) && compat.clients.length && compat.clients.indexOf(profile.client) < 0)
      return { status: 'no', reason: 'Signing client is not listed as supported.' };
    if (!selected) return { status: 'unknown', reason: 'Choose a device profile to compare.' };
    if (unknown.length) return { status: 'unknown', reason: 'Not enough metadata: ' + unknown.join(', ') + '.' };
    return { status: 'yes', reason: 'Matches the selected, declared requirements; installation is not guaranteed.' };
  }
  function expiry(date, kind, now) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date || '') || ['free', 'paid'].indexOf(kind) < 0) return null;
    var start = Date.parse(date + 'T00:00:00Z');
    if (!Number.isFinite(start) || new Date(start).toISOString().slice(0, 10) !== date) return null;
    var end = start + (kind === 'free' ? 7 : 365) * 86400000;
    var current = now == null ? Date.now() : now;
    return { date: new Date(end).toISOString().slice(0, 10), days: Math.ceil((end - current) / 86400000), expired: end <= current };
  }
  function estimates() {
    var stored = read(INSTALLED), list = [];
    Object.keys(stored).sort().forEach(function (slug) {
      if (!/^[a-z0-9][a-z0-9-]{0,31}$/.test(slug) || !stored[slug] || typeof stored[slug] !== 'object') return;
      var info = expiry(stored[slug].date, stored[slug].kind);
      if (info) list.push({ slug: slug, date: info.date, days: info.days, expired: info.expired });
    });
    return list;
  }
  function estimate(slug) {
    var item = read(INSTALLED)[slug];
    return item && typeof item === 'object' ? expiry(item.date, item.kind) : null;
  }
  function estimateText(info) {
    return info.expired ? 'Re-sign: possibly expired' : 'Re-sign: ' + info.days + (info.days === 1 ? ' day' : ' days') + ' left';
  }
  function decorate(root) {
    (root || document).querySelectorAll('.app-card[data-slug], .app-card[data-app-id]').forEach(function (card) {
      var slug = card.getAttribute('data-slug') || card.getAttribute('data-app-id');
      var info = estimate(slug), badge = card.querySelector('[data-resign-badge]');
      if (!info) {
        if (badge) badge.remove();
        var existing = card.querySelector('.card-badges');
        if (existing) existing.classList.toggle('has-local-badges', !!existing.querySelector('[data-resign-badge], [data-update-badge]'));
        return;
      }
      if (!badge) {
        var row = card.querySelector('.card-badges');
        if (!row) { row = document.createElement('div'); row.className = 'card-badges'; card.appendChild(row); }
        badge = document.createElement('span'); badge.setAttribute('data-resign-badge', ''); row.appendChild(badge);
      }
      badge.parentNode.classList.add('has-local-badges');
      badge.className = 'badge ' + (info.expired || info.days <= 1 ? 'warn' : 'unverified');
      badge.textContent = estimateText(info);
      badge.title = 'Estimated ' + info.date + '; check the actual certificate and signing client.';
    });
  }
  function refresh() {
    var p = clean(read(PROFILE));
    document.querySelectorAll('[data-device-compat]').forEach(function (node) {
      var compat = {}; try { compat = JSON.parse(node.getAttribute('data-device-compat') || '{}'); } catch (_) { /* unknown */ }
      var result = evaluate(compat, p);
      node.textContent = 'Device compatibility: ' + (result.status === 'yes' ? 'matches' : result.status === 'no' ? 'not compatible' : 'unknown') + ' — ' + result.reason;
    });
    decorate(document);
    var summary = document.getElementById('resignTracker');
    if (summary) {
      var list = summary.querySelector('[data-resign-list]'), status = summary.querySelector('[data-resign-summary]');
      var values = estimates();
      list.replaceChildren();
      values.forEach(function (item) {
        var li = document.createElement('li'), a = document.createElement('a');
        a.href = '../apps/' + encodeURIComponent(item.slug) + '/'; a.textContent = item.slug;
        li.appendChild(a); li.appendChild(document.createTextNode(' — ' + estimateText(item) + ' (estimated ' + item.date + ')'));
        list.appendChild(li);
      });
      status.textContent = values.length ? values.length + ' signing estimate' + (values.length === 1 ? '' : 's') + ' stored locally.' : 'No signing dates saved. Add one on an app page.';
      var toggle = summary.querySelector('[data-resign-icon]');
      if (toggle) toggle.checked = read(BADGE).enabled === true;
    }
  }
  function updateIconBadge() {
    var nav = global.navigator, due = estimates().filter(function (item) { return item.expired || item.days <= 1; }).length;
    if (!nav) return;
    try {
      var result;
      if (read(BADGE).enabled === true && due && typeof nav.setAppBadge === 'function') result = nav.setAppBadge(due);
      else if (typeof nav.clearAppBadge === 'function') result = nav.clearAppBadge();
      if (result && typeof result.catch === 'function') result.catch(function () {});
    } catch (_) { /* unsupported, denied, or not installed */ }
  }
  function notifyDue() {
    if (read(NOTIFY).enabled !== true || !global.Notification || global.Notification.permission !== 'granted') return Promise.resolve(false);
    var due = estimates().filter(function (item) { return item.expired || item.days <= 1; });
    var day = new Date().toISOString().slice(0, 10);
    if (!due.length || read(NOTIFIED).date === day) return Promise.resolve(false);
    var title = 'OmniSource re-sign reminder';
    var options = { body: due.length + ' signing estimate' + (due.length === 1 ? ' is' : 's are') + ' near or past expiry. Check the actual certificates.' };
    function show(registration) {
      if (registration && typeof registration.showNotification === 'function') return registration.showNotification(title, options);
      new global.Notification(title, options);
      return Promise.resolve();
    }
    var service = global.navigator && global.navigator.serviceWorker;
    var registration = service && typeof service.getRegistration === 'function' ? service.getRegistration() : Promise.resolve(null);
    return Promise.resolve(registration).then(show).then(function () { save(NOTIFIED, { date: day }); return true; }).catch(function () { return false; });
  }
  function sync() {
    refresh(); updateIconBadge();
    global.dispatchEvent(new global.CustomEvent('omni:resign-change'));
  }
  function boot() {
    if (booted) return;
    booted = true;
    var form = document.getElementById('deviceProfileForm');
    if (form) {
      var p = clean(read(PROFILE));
      ['ios', 'device', 'client'].forEach(function (key) { if (form.elements[key]) form.elements[key].value = p[key]; });
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        var raw = { ios: form.elements.ios.value, device: form.elements.device.value, client: form.elements.client.value };
        var result = clean(raw), message = document.getElementById('deviceProfileMessage');
        if (raw.ios.trim() && !result.ios) { message.textContent = 'Enter a version such as 16.4.'; return; }
        message.textContent = save(PROFILE, result) ? 'Saved on this device only.' : 'Browser storage is unavailable.';
        refresh(); global.dispatchEvent(new global.CustomEvent('omni:device-change'));
      });
      form.addEventListener('reset', function () {
        save(PROFILE, {}); setTimeout(function () { refresh(); global.dispatchEvent(new global.CustomEvent('omni:device-change')); }, 0);
      });
    }
    document.querySelectorAll('form[data-resign-slug]').forEach(function (form) {
      var slug = form.getAttribute('data-resign-slug'), entries = read(INSTALLED), item = entries[slug] || {};
      var message = form.querySelector('[data-resign-message]');
      form.elements.signed.value = item.date || ''; form.elements.kind.value = item.kind || 'free';
      function show() {
        var info = expiry(form.elements.signed.value, form.elements.kind.value);
        message.textContent = info ? 'Estimated expiry: ' + info.date + ' (' + (info.expired ? 'possibly expired' : info.days + ' days remaining') + '). Actual certificate expiry may differ.' : 'No valid estimate saved.';
      }
      show();
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        var info = expiry(form.elements.signed.value, form.elements.kind.value);
        if (!info) { message.textContent = 'Choose a valid signing date.'; return; }
        var values = read(INSTALLED); values[slug] = { date: form.elements.signed.value, kind: form.elements.kind.value };
        if (!save(INSTALLED, values)) message.textContent = 'Browser storage is unavailable.'; else { show(); sync(); }
      });
      var reminder = form.querySelector('[data-resign-remind]');
      if (reminder) reminder.addEventListener('click', function () {
        if (!estimate(slug)) { message.textContent = 'Save a signing date before enabling reminders.'; return; }
        if (!global.Notification || typeof global.Notification.requestPermission !== 'function') { message.textContent = 'This browser does not support local notifications.'; return; }
        var request;
        try { request = global.Notification.requestPermission(); }
        catch (_) { message.textContent = 'Notification permission is unavailable.'; return; }
        Promise.resolve(request).then(function (permission) {
          if (permission !== 'granted') { message.textContent = 'Notification permission was not granted.'; return; }
          if (!save(NOTIFY, { enabled: true })) { message.textContent = 'Browser storage is unavailable.'; return; }
          message.textContent = 'Reminders enabled on this browser. Open the catalog, Favorites or an app page near expiry; no background push is used.';
          notifyDue();
        }).catch(function () { message.textContent = 'Notification permission is unavailable.'; });
      });
      var disable = form.querySelector('[data-resign-disable]');
      if (disable) disable.addEventListener('click', function () {
        if (!save(NOTIFY, { enabled: false })) message.textContent = 'Browser storage is unavailable.';
        else message.textContent = 'Local reminders are off. Browser notification permission can also be changed in browser settings.';
      });
      var clear = form.querySelector('[data-resign-clear]');
      if (clear) clear.addEventListener('click', function () {
        var values = read(INSTALLED); delete values[slug];
        if (!save(INSTALLED, values)) { message.textContent = 'Browser storage is unavailable.'; return; }
        form.elements.signed.value = ''; show(); sync();
      });
    });
    var summary = document.getElementById('resignTracker');
    if (summary) {
      var icon = summary.querySelector('[data-resign-icon]'), clearAll = summary.querySelector('[data-resign-clear-all]');
      var disableAll = summary.querySelector('[data-resign-disable]');
      if (icon) icon.addEventListener('change', function () {
        if (!save(BADGE, { enabled: icon.checked })) { icon.checked = false; summary.querySelector('[data-resign-summary]').textContent = 'Browser storage is unavailable.'; return; }
        updateIconBadge();
      });
      if (clearAll) clearAll.addEventListener('click', function () {
        if (!save(INSTALLED, {})) { summary.querySelector('[data-resign-summary]').textContent = 'Browser storage is unavailable.'; return; }
        sync();
      });
      if (disableAll) disableAll.addEventListener('click', function () {
        if (!save(NOTIFY, { enabled: false })) summary.querySelector('[data-resign-summary]').textContent = 'Browser storage is unavailable.';
        else summary.querySelector('[data-resign-summary]').textContent = 'Local reminders are off on this browser.';
      });
    }
    global.addEventListener('storage', function (event) {
      if ([PROFILE, INSTALLED, NOTIFY, BADGE].indexOf(event.key) >= 0) { sync(); if (event.key === PROFILE) global.dispatchEvent(new global.CustomEvent('omni:device-change')); }
    });
    document.addEventListener('visibilitychange', function () { if (!document.hidden) { sync(); notifyDue(); } });
    refresh(); updateIconBadge(); notifyDue();
  }
  global.OmniDevice = { profile: function () { return clean(read(PROFILE)); }, evaluate: evaluate, compareVersions: compareVersions, expiry: expiry, estimate: estimate, estimates: estimates, decorate: decorate, refresh: refresh };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})(window);
