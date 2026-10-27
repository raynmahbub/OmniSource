/* Compare a user-supplied source in the browser. No proxy or server upload. */
(function () {
  'use strict';
  var root = document.getElementById('sourceMigration');
  if (!root) return;
  var status = root.querySelector('[data-migration-status]');
  var output = root.querySelector('[data-migration-results]');
  var input = root.querySelector('[name="sourceUrl"]');
  var file = root.querySelector('[name="sourceFile"]');
  var LIMIT = 5 * 1024 * 1024;
  function message(text) { status.textContent = text; }
  function text(value) { return typeof value === 'string' ? value.slice(0, 160) : ''; }
  function version(app) { var versions = Array.isArray(app.versions) ? app.versions : []; return text(app.version || (versions[0] && versions[0].version)); }
  function compareVersions(a, b) {
    if (!/^\d+(?:\.\d+)*$/.test(a) || !/^\d+(?:\.\d+)*$/.test(b)) return null;
    var one = a.split('.').map(Number), two = b.split('.').map(Number);
    for (var i = 0; i < Math.max(one.length, two.length); i++) {
      if ((one[i] || 0) !== (two[i] || 0)) return (one[i] || 0) > (two[i] || 0) ? 1 : -1;
    }
    return 0;
  }
  async function boundedResponse(response) {
    if (!response.ok) throw new Error('The source returned HTTP ' + response.status + '.');
    if (Number(response.headers.get('content-length')) > LIMIT) throw new Error('Source exceeds the 5 MB limit.');
    if (!response.body || !response.body.getReader) throw new Error('Streaming is not supported; use a local JSON file instead.');
    var reader = response.body.getReader(), parts = [], total = 0;
    try {
      while (true) {
        var part = await reader.read();
        if (part.done) break;
        total += part.value.length;
        if (total > LIMIT) { await reader.cancel(); throw new Error('Source exceeds the 5 MB limit.'); }
        parts.push(part.value);
      }
    } finally { reader.releaseLock(); }
    var decoder = new TextDecoder(), result = '';
    parts.forEach(function (part) { result += decoder.decode(part, { stream: true }); });
    return result + decoder.decode();
  }
  function add(tag, parent, value) { var node = document.createElement(tag); node.textContent = value; parent.appendChild(node); return node; }
  function show(source, master) {
    if (!source || !Array.isArray(source.apps)) throw new Error('Expected an AltStore source with an apps array.');
    if (source.apps.length > 2000) throw new Error('Source has more than 2,000 apps.');
    var byBundle = new Map(), local = Array.isArray(master.apps) ? master.apps : [];
    local.forEach(function (app) {
      if (!app || typeof app.bundleIdentifier !== 'string') return;
      var key = app.bundleIdentifier.toLowerCase();
      if (!byBundle.has(key)) byBundle.set(key, []);
      byBundle.get(key).push(app);
    });
    var matches = 0, missing = 0, fragment = document.createDocumentFragment();
    source.apps.forEach(function (app, index) {
      if (!app || typeof app !== 'object') return;
      var name = text(app.name) || 'Unnamed app', bundle = text(app.bundleIdentifier);
      var candidates = bundle ? (byBundle.get(bundle.toLowerCase()) || []) : [];
      if (candidates.length) matches++; else missing++;
      if (index >= 200) return;
      var li = document.createElement('li');
      add('strong', li, name);
      if (candidates.length) {
        var labels = candidates.map(function (candidate) { return text(candidate.name); }).filter(Boolean).join(', ');
        var note = ' — shared bundle with: ' + labels + '. Bundle matches can be alternatives, not the same app.';
        var exact = candidates.filter(function (candidate) { return text(candidate.name).toLowerCase() === name.toLowerCase(); });
        if (exact.length === 1) {
          var incoming = version(app), current = version(exact[0]), order = compareVersions(current, incoming);
          if (order !== null) note += order > 0 ? ' OmniSource lists a numerically newer version.' : order < 0 ? ' The supplied source lists a numerically newer version.' : ' Listed version numbers match.';
        }
        add('span', li, note);
      } else {
        add('span', li, bundle ? ' — no matching bundle listed. ' + bundle + ' ' : ' — no bundle identifier provided. ');
        var issue = document.createElement('a');
        var params = new URLSearchParams({ template: '01-app-request.yml', title: 'Add app: ' + name });
        issue.href = 'https://github.com/raynmahbub/OmniSource/issues/new?' + params.toString();
        issue.textContent = 'Request review'; issue.target = '_blank'; issue.rel = 'noopener noreferrer'; li.appendChild(issue);
      }
      fragment.appendChild(li);
    });
    output.replaceChildren(fragment);
    message(matches + ' entries share a listed bundle; ' + missing + ' do not. Showing up to 200 entries. No installations or catalog changes were made.');
  }
  root.querySelector('form').addEventListener('submit', async function (event) {
    event.preventDefault(); output.replaceChildren(); message('Comparing locally…');
    try {
      var inputText;
      if (file.files && file.files[0]) {
        if (file.files[0].size > LIMIT) throw new Error('File exceeds the 5 MB limit.');
        inputText = await file.files[0].text();
      } else {
        var url = new URL(input.value);
        if (url.protocol !== 'https:' || url.username || url.password) throw new Error('Use an HTTPS URL without credentials.');
        var controller = new AbortController();
        var timer = setTimeout(function () { controller.abort(); }, 15000);
        try { inputText = await boundedResponse(await fetch(url.href, { credentials: 'omit', redirect: 'error', signal: controller.signal })); }
        finally { clearTimeout(timer); }
      }
      var masterResponse = await fetch('../apps.json', { credentials: 'same-origin' });
      var masterText = await boundedResponse(masterResponse);
      show(JSON.parse(inputText), JSON.parse(masterText));
    } catch (error) { message('Could not compare this source. Check the URL, CORS access or JSON file. ' + text(error && error.message)); }
  });
})();
