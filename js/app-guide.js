/* Local, evidence-limited app finder. Matching is not an endorsement. */
(function () {
  'use strict';
  var root = document.getElementById('appGuide'); if (!root) return;
  var form = root.querySelector('form'), status = root.querySelector('[data-guide-status]'), list = root.querySelector('[data-guide-results]');
  var documents;
  async function load() {
    if (!documents) {
      documents = Promise.all(['feeds/apps.json', 'feeds/verification.json'].map(function (url) {
        return fetch(url).then(function (r) { if (!r.ok) throw new Error('unavailable'); return r.json(); });
      })).catch(function (error) { documents = null; throw error; });
    }
    return documents;
  }
  function add(parent, tag, value) { var node = document.createElement(tag); node.textContent = value; parent.appendChild(node); return node; }
  form.addEventListener('submit', async function (event) {
    event.preventDefault(); list.replaceChildren(); status.textContent = 'Finding matching descriptions…';
    try {
      var docs = await load(), apps = Array.isArray(docs[0].apps) ? docs[0].apps : [];
      var verdicts = new Map((docs[1].apps || []).map(function (v) { return [v.app, v]; }));
      var terms = String(form.elements.keywords.value || '').toLowerCase().trim().split(/\s+/).filter(Boolean).slice(0, 8);
      var category = form.elements.category.value, provenance = form.elements.provenance.value;
      var onlyReachable = form.elements.reachable.checked, device = window.OmniDevice;
      var profile = device ? device.profile() : {};
      var matches = apps.filter(function (app) {
        var meta = app.omnisource || {}, v = verdicts.get(meta.slug) || {};
        var haystack = [app.name, app.subtitle, app.localizedDescription, app.category].join(' ').toLowerCase();
        if (terms.some(function (term) { return haystack.indexOf(term) < 0; })) return false;
        if (category && app.category !== category) return false;
        if (provenance && v.provenance !== provenance) return false;
        if (onlyReachable && (!meta.health || meta.health.downloadReachable !== true)) return false;
        return !device || device.evaluate(meta.compatibility, profile).status !== 'no';
      }).sort(function (a, b) { return String(a.name).localeCompare(String(b.name)); });
      status.textContent = matches.length + ' matching entries. Keywords match catalog text, not proven capabilities; missing compatibility data remains unknown.';
      matches.slice(0, 20).forEach(function (app) {
        var meta = app.omnisource || {}, slug = String(meta.slug || '');
        if (!/^[a-z0-9][a-z0-9-]*$/.test(slug)) return;
        var item = document.createElement('li'), a = add(item, 'a', String(app.name || slug)); a.href = 'apps/' + encodeURIComponent(slug) + '/';
        var result = device ? device.evaluate(meta.compatibility, profile) : { status: 'unknown' };
        var v = verdicts.get(slug) || {};
        add(item, 'span', ' — ' + String(app.category || 'category unknown') + '; device: ' + (result.status === 'yes' ? 'declared match' : 'unknown') + '; source: ' + String(v.provenance || 'unknown'));
        list.appendChild(item);
      });
    } catch (_) { status.textContent = 'Catalog data is unavailable. Try again when online.'; }
  });
})();
