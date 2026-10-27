/* Local device profile and optional re-sign reminders. No data leaves this browser. */
(function (global) {
  'use strict';
  var PROFILE = 'omnisource:device-profile:v1';
  var INSTALLED = 'omnisource:resign:v1';
  var DEVICES = ['iphone', 'ipad'];
  var CLIENTS = ['altstore', 'sidestore', 'flarestore', 'feather', 'esign', 'ksign', 'livecontainer'];
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
  function refresh() {
    var p = clean(read(PROFILE));
    document.querySelectorAll('[data-device-compat]').forEach(function (node) {
      var compat = {}; try { compat = JSON.parse(node.getAttribute('data-device-compat') || '{}'); } catch (_) { /* unknown */ }
      var result = evaluate(compat, p);
      node.textContent = 'Device compatibility: ' + (result.status === 'yes' ? 'matches' : result.status === 'no' ? 'not compatible' : 'unknown') + ' — ' + result.reason;
    });
  }
  function boot() {
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
        refresh(); global.dispatchEvent(new CustomEvent('omni:device-change'));
      });
      form.addEventListener('reset', function () {
        save(PROFILE, {}); setTimeout(function () { refresh(); global.dispatchEvent(new CustomEvent('omni:device-change')); }, 0);
      });
    }
    document.querySelectorAll('[data-resign-slug]').forEach(function (form) {
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
        if (!save(INSTALLED, values)) message.textContent = 'Browser storage is unavailable.'; else show();
      });
      var reminder = form.querySelector('[data-resign-remind]');
      if (reminder) reminder.addEventListener('click', function () {
        if (!global.Notification || typeof global.Notification.requestPermission !== 'function') { message.textContent = 'This browser does not support local notifications.'; return; }
        var request;
        try { request = global.Notification.requestPermission(); }
        catch (_) { message.textContent = 'Notification permission is unavailable.'; return; }
        Promise.resolve(request).then(function (permission) {
          var info = expiry(form.elements.signed.value, form.elements.kind.value);
          if (permission !== 'granted') { message.textContent = 'Notification permission was not granted.'; return; }
          if (info && info.days <= 1) new global.Notification('OmniSource re-sign reminder', { body: 'The estimated signing period for ' + slug + ' is near expiry. Check the actual certificate.' });
          else message.textContent = 'Notifications allowed. Open this page near expiry to receive a reminder; no background push is used.';
        }).catch(function () { message.textContent = 'Notification permission is unavailable.'; });
      });
      if (global.Notification && global.Notification.permission === 'granted') {
        var due = expiry(item.date, item.kind), lastKey = 'omnisource:reminded:' + slug + ':' + new Date().toISOString().slice(0, 10);
        try {
          if (due && due.days <= 1 && !global.sessionStorage.getItem(lastKey)) {
            new global.Notification('OmniSource re-sign reminder', { body: 'Check the signing expiry for ' + slug + '.' });
            global.sessionStorage.setItem(lastKey, '1');
          }
        } catch (_) { /* unsupported or storage unavailable */ }
      }
      var clear = form.querySelector('[data-resign-clear]');
      if (clear) clear.addEventListener('click', function () {
        var values = read(INSTALLED); delete values[slug];
        if (!save(INSTALLED, values)) { message.textContent = 'Browser storage is unavailable.'; return; }
        form.elements.signed.value = ''; show();
      });
    });
    refresh();
  }
  global.OmniDevice = { profile: function () { return clean(read(PROFILE)); }, evaluate: evaluate, compareVersions: compareVersions, expiry: expiry, refresh: refresh };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})(window);
