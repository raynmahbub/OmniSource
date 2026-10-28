/* Local, evidence-limited app guide. Rankings are not endorsements. */
(function () {
  'use strict';
  var root = document.getElementById('appGuide'); if (!root) return;
  var form = root.querySelector('form'), status = root.querySelector('[data-guide-status]'), list = root.querySelector('[data-guide-results]');
  var labels = { 'no-ads': 'no ads', 'picture-in-picture': 'picture-in-picture', downloads: 'downloads', 'background-audio': 'background audio', sponsorblock: 'SponsorBlock', '4k': '4K' };
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
  function compatFor(app) {
    var meta = app.omnisource || {}, compat = Object.assign({}, meta.compatibility || {});
    if (typeof app.minOSVersion === 'string' && app.minOSVersion) compat.minOSVersion = app.minOSVersion;
    if (typeof app.maxOSVersion === 'string' && app.maxOSVersion) compat.maxOSVersion = app.maxOSVersion;
    return compat;
  }
  function reviewedFeatures(app) {
    var meta = app.omnisource || {}, reviewed = meta.featuresReviewed;
    if (!reviewed || reviewed.version !== app.version || reviewed.downloadURL !== app.downloadURL || !Array.isArray(meta.features)) return [];
    return meta.features.filter(function (value) { return Object.prototype.hasOwnProperty.call(labels, value); });
  }
  form.addEventListener('submit', async function (event) {
    event.preventDefault(); list.replaceChildren(); status.textContent = 'Finding matching descriptions…';
    var ios = form.elements.guideIos ? String(form.elements.guideIos.value || '').trim() : '';
    if (ios && !/^\d{1,3}(?:\.\d{1,3}){0,2}$/.test(ios)) { status.textContent = 'Enter an iOS version such as 16.4.'; return; }
    try {
      var docs = await load(), apps = Array.isArray(docs[0].apps) ? docs[0].apps : [];
      var verdicts = new Map((docs[1].apps || []).map(function (v) { return [v.app, v]; }));
      var terms = String(form.elements.keywords.value || '').toLowerCase().trim().split(/\s+/).filter(Boolean).slice(0, 8);
      var category = form.elements.category.value, provenance = form.elements.provenance.value;
      var group = form.elements.group ? form.elements.group.value : '';
      var requested = Array.from(form.querySelectorAll('input[name="capability"]:checked')).map(function (node) { return node.value; }).filter(function (value) { return Object.prototype.hasOwnProperty.call(labels, value); });
      var onlyReachable = form.elements.reachable.checked, device = window.OmniDevice;
      var profile = Object.assign({}, device ? device.profile() : {});
      if (ios) profile.ios = ios;
      if (form.elements.guideClient && form.elements.guideClient.value) profile.client = form.elements.guideClient.value;
      var incompatible = 0;
      var matches = apps.reduce(function (found, app) {
        var meta = app.omnisource || {}, v = verdicts.get(meta.slug) || {};
        var haystack = [app.name, app.subtitle, app.localizedDescription, app.category].join(' ').toLowerCase();
        if (terms.some(function (term) { return haystack.indexOf(term) < 0; })) return found;
        if (category && app.category !== category) return found;
        if (provenance && v.provenance !== provenance) return found;
        if (group && app.bundleIdentifier !== group) return found;
        if (onlyReachable && (!meta.health || meta.health.downloadReachable !== true || !app.downloadURL || !meta.health.checkedURL || meta.health.checkedURL !== app.downloadURL)) return found;
        var compatibility = device ? device.evaluate(compatFor(app), profile) : { status: 'unknown', reason: 'No device profile selected.' };
        if (compatibility.status === 'no') { incompatible++; return found; }
        var features = reviewedFeatures(app);
        var hits = requested.filter(function (value) { return features.indexOf(value) >= 0; });
        found.push({ app: app, verdict: v, compatibility: compatibility, features: features, hits: hits });
        return found;
      }, []);
      matches.sort(function (a, b) {
        return b.hits.length - a.hits.length || Number(b.compatibility.status === 'yes') - Number(a.compatibility.status === 'yes') || String(a.app.name).localeCompare(String(b.app.name));
      });
      status.textContent = matches.length + ' matching entries' + (incompatible ? '; ' + incompatible + ' excluded by declared device requirements' : '') + '. ' + (requested.length ? 'Ranked by reviewed descriptions, not verified functionality. Unlisted features remain unknown.' : 'Select capabilities to rank by reviewed descriptions; otherwise results are alphabetical within device-match groups.');
      matches.slice(0, 20).forEach(function (item) {
        var app = item.app, meta = app.omnisource || {}, slug = String(meta.slug || '');
        if (!/^[a-z0-9][a-z0-9-]*$/.test(slug)) return;
        var row = document.createElement('li'), a = add(row, 'a', String(app.name || slug)); a.href = 'apps/' + encodeURIComponent(slug) + '/';
        var details = [];
        if (requested.length) {
          details.push(item.hits.length + '/' + requested.length + ' requested features described' + (item.hits.length ? ': ' + item.hits.map(function (value) { return labels[value]; }).join(', ') : ''));
          var unknown = requested.filter(function (value) { return item.hits.indexOf(value) < 0; });
          if (unknown.length) details.push('not reviewed: ' + unknown.map(function (value) { return labels[value]; }).join(', '));
        }
        details.push('device: ' + (item.compatibility.status === 'yes' ? 'declared match' : 'unknown') + ' (' + item.compatibility.reason + ')');
        details.push('source: ' + String(item.verdict.provenance || 'unknown'));
        if (item.features.length && typeof meta.bestFor === 'string') details.push(meta.bestFor);
        add(row, 'span', ' — ' + details.join('; '));
        list.appendChild(row);
      });
    } catch (_) { status.textContent = 'Catalog data is unavailable. Try again when online.'; }
  });
})();
