/* =============================================================================
 * OmniSource Data Layer
 * -----------------------------------------------------------------------------
 * Single source of truth for frontend rendering. Fetches, normalizes, caches
 * and indexes every API document the UI needs. Exposes a promise-based API
 * (window.OmniData) so every engine (search, compare, recommend, trust) can
 * consume immutable snapshots without refetching.
 *
 * The data layer tolerates partial failures: individual fetches can fail
 * (stale cache, offline PWA) without killing the whole UI — the page falls
 * back to whatever subset was available.
 * ============================================================================= */
(function (global) {
  'use strict';

  // Base URL works under any sub-path (works locally, under /OmniSource/, or on a custom domain).
  var BASE = (function () {
    try {
      var base = document.querySelector('base[href]');
      if (base) return base.getAttribute('href');
    } catch (_) {}
    // Derive from the current script URL so we don't assume a root path.
    try {
      var s = document.currentScript && document.currentScript.src;
      if (s) return s.replace(/\/src\/js\/data-layer\.js.*$/, '/');
    } catch (_) {}
    return './';
  })();

  // API endpoints — v1 (feeds/*) are the canonical generated artifacts; v2
  // aliases point to the same bytes for forward compatibility with OmniStore
  // clients.
  var ENDPOINTS = {
    apps:        'feeds/discovery.json',
    sources:     'feeds/sources.json',
    analytics:   'feeds/analytics.json',
    health:      'feeds/health.json',
    status:      'feeds/status.json',
    trending:    'feeds/trending.json',
    related:     'feeds/related.json',
    verification:'feeds/verification.json',
    reputation:  'feeds/reputation.json',
    collections: 'feeds/collections.json',
    community:   'feeds/community.json',
    updates:     'feeds/updates.json',
    search:      'feeds/search-index.json',
    compare:     'feeds/compare.json',
    dlIntel:     'feeds/download-intelligence.json',
    deadApps:    'feeds/dead_apps.json',
    screenshots: 'feeds/screenshots.json',
    integrity:   'feeds/integrity_report.json',
    duplicates:  'feeds/duplicates.json',
    install:     'feeds/install.json',
    // v2 canonical names
    v2Apps:       'api/v2/apps.json',
    v2Sources:    'api/v2/sources.json',
    v2Trending:   'api/v2/trending.json',
    v2Status:     'api/v2/status.json',
    v2Related:    'api/v2/related.json',
    v2Graph:      'api/v2/graph.json',
  };

  // In-memory cache keyed by URL.
  var cache = Object.create(null);
  // In-flight promises so concurrent callers share one fetch.
  var inflight = Object.create(null);
  // App lookup by slug (built when the catalog loads).
  var appsBySlug = new Map();
  var appsByBundle = new Map();
  var ready = { state: 'pending', resolve: null, reject: null };
  ready.promise = new Promise(function (res, rej) { ready.resolve = res; ready.reject = rej; });

  function fetchJSON(url, opts) {
    if (cache[url]) return Promise.resolve(cache[url]);
    if (inflight[url]) return inflight[url];
    var p = fetch(url, Object.assign({ credentials: 'omit' }, opts || {}))
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + url);
        return r.json();
      })
      .then(function (data) {
        cache[url] = data;
        delete inflight[url];
        return data;
      })
      .catch(function (err) {
        delete inflight[url];
        // Surface the error but don't kill unrelated endpoints.
        console.warn('[data] failed to load', url, err);
        throw err;
      });
    inflight[url] = p;
    return p;
  }

  // Normalize an app record from the discovery catalog so every engine can
  // rely on stable keys regardless of which API doc it came from.
  function normalizeApp(raw) {
    var a = raw || {};
    var slug = a.slug || a.id || '';
    return Object.assign({}, a, {
      slug: slug,
      id: a.id || slug,
      name: a.name || '',
      bundleId: a.bundleId || a.bundleIdentifier || '',
      developerName: a.developerName || a.developer || '',
      icon: a.icon || a.iconURL || '',
      version: a.version || '',
      releaseDate: a.releaseDate || a.versionDate || '',
      category: (a.category || 'other').toLowerCase(),
      categories: Array.isArray(a.categories) ? a.categories : (a.category ? [a.category] : []),
      tags: Array.isArray(a.tags) ? a.tags : [],
      description: a.localizedDescription || a.description || a.shortDescription || '',
      shortDescription: a.shortDescription || (a.description || '').slice(0, 160),
      health: a.health || {},
    });
  }

  // Build slug/bundle lookup maps once the catalog resolves.
  function indexApps(discovery) {
    appsBySlug.clear();
    appsByBundle.clear();
    var list = (discovery && discovery.apps) || [];
    list.forEach(function (raw) {
      var app = normalizeApp(raw);
      appsBySlug.set(app.slug, app);
      if (app.bundleId) appsByBundle.set(app.bundleId.toLowerCase(), app);
    });
    return list.map(function (a) { return normalizeApp(a); });
  }

  // Aliases / known-name variants for fuzzy search. Kept short and declarative
  // so it stays cheap to load synchronously (it ships with the JS, not as an
  // extra request). Expand as the catalog grows.
  var ALIASES = {
    'youtube': ['yt', 'ytube', 'youtube+', 'youtubetweak'],
    'youtube music': ['ytm', 'youtubemusic', 'yt music', 'ymusic'],
    'spotify': ['spotify++', 'spotifytweak', 'spotifyplus'],
    'spotiflac': ['mornye', 'spotify flac', 'spotify premium', 'spotify++', 'flac player'],
    'mornye': ['spotiflac', 'spotify flac', 'spotify premium', 'spotify++', 'flac player'],
    'nebuloiptv': ['onside tv', 'onsidetv', 'nebulo', 'iptv', 'live tv', 'sports'],
    'twitter': ['x', 'twitter++', 'xtweak', 'xapp'],
    'instagram': ['ig', 'insta', 'instagram++', 'igtweak'],
    'tiktok': ['tt', 'tiktok++', 'tttweak'],
    'telegram': ['tg', 'telegram++'],
    'discord': ['dc', 'discord++'],
    'reddit': ['apollo', 'redditclient'],
    'delta': ['delta emulator', 'gbaios', 'nds4ios'],
    'provenance': ['provenance emulator', 'retro'],
    'ppsspp': ['psp', 'psp emulator'],
    'feather': ['feather app', 'feather signer', 'feather sign'],
    'sidestore': ['side store', 'altstore fork'],
    'altstore': ['alt store'],
    'esign': ['e-sign', 'esign app', 'esigner'],
    'livecontainer': ['live container', 'lc'],
    'utorrent': ['itransmission', 'torrent'],
    'utorrent': ['itorrent'],
    'dopamine': ['dopamine jailbreak', 'dopaminejb'],
    'serotonin': ['serotonin jb', 'bootstrap jb'],
    'uyouenhanced': ['uyou', 'u you', 'u-you', 'uyou enhanced', 'youtube enhanced'],
    'youpro': ['you pro', 'youtube pro', 'youtubepro'],
    'ytlite': ['yt lite', 'youtube lite', 'youtubelite'],
    'bhtwitter': ['bh twitter', 'twitter bh'],
    'ryukgram': ['ryuk gram', 'telegram ryuk'],
    'swiftgram': ['swift gram'],
    'gopeed': ['go speed', 'downloader'],
    'qbitconnect': ['qbittorrent', 'qb connect'],
    'jellify': ['jellyfin', 'jellyfin client'],
    'fladder': ['jellyfin client'],
    'streamyfin': ['jellyfin client'],
    'infuseplus': ['infuse+', 'infuse pro', 'infuse premium'],
    'spotube': ['spotube client', 'open source spotify'],
    'maxmusic': ['max music', 'apple music tweak', 'music'],
    'maxtube': ['max tube', 'youtube max'],
    'saber': ['saber vpn', 'vpn'],
  };

  // Known aliases by keyword (reverse index for fast lookups).
  var aliasMap = Object.create(null); // keyword -> [slugs...]
  Object.keys(ALIASES).forEach(function (name) {
    var slugs = [];
    for (var s in appsBySlug) { /* filled after load */ }
    // We don't know all slugs yet — this is built in finalizeAliases().
  });

  function finalizeAliases() {
    Object.keys(ALIASES).forEach(function (needle) {
      // Match the needle to one or more slugs by name similarity.
      var targets = [];
      var needleLower = needle.toLowerCase();
      appsBySlug.forEach(function (app, slug) {
        var name = app.name.toLowerCase();
        if (name === needleLower || name.indexOf(needleLower) === 0) targets.push(slug);
      });
      if (!targets.length) return;
      ALIASES[needle].forEach(function (alias) {
        var key = alias.toLowerCase();
        if (!aliasMap[key]) aliasMap[key] = [];
        targets.forEach(function (t) { if (aliasMap[key].indexOf(t) === -1) aliasMap[key].push(t); });
      });
    });
  }

  // Main boot. Loads the minimum set needed to render, then fires `ready`.
  function load() {
    var tasks = {
      apps:        fetchJSON(BASE + ENDPOINTS.apps).then(indexApps),
      analytics:   fetchJSON(BASE + ENDPOINTS.analytics).catch(function(){return {};}),
      health:      fetchJSON(BASE + ENDPOINTS.health).catch(function(){return {};}),
      status:      fetchJSON(BASE + ENDPOINTS.status).catch(function(){return {};}),
      trending:    fetchJSON(BASE + ENDPOINTS.trending).catch(function(){return {};}),
      related:     fetchJSON(BASE + ENDPOINTS.related).catch(function(){return {};}),
      verification:fetchJSON(BASE + ENDPOINTS.verification).catch(function(){return {};}),
      sources:     fetchJSON(BASE + ENDPOINTS.sources).catch(function(){return {};}),
      collections: fetchJSON(BASE + ENDPOINTS.collections).catch(function(){return {};}),
      community:   fetchJSON(BASE + ENDPOINTS.community).catch(function(){return {};}),
      updates:     fetchJSON(BASE + ENDPOINTS.updates).catch(function(){return {};}),
      search:      fetchJSON(BASE + ENDPOINTS.search).catch(function(){return null;}),
      reputation:  fetchJSON(BASE + ENDPOINTS.reputation).catch(function(){return {};}),
      duplicates:  fetchJSON(BASE + ENDPOINTS.duplicates).catch(function(){return {};}),
      deadApps:    fetchJSON(BASE + ENDPOINTS.deadApps).catch(function(){return {};}),
      install:     fetchJSON(BASE + ENDPOINTS.install).catch(function(){return {};}),
    };

    // Compare matrix is big (3.6MB) — lazy-loaded by Compare Engine only when needed.
    tasks.compare = null;

    Promise.all(Object.keys(tasks).map(function (k) {
      return (tasks[k] || Promise.resolve(null)).then(function (v) { tasks[k] = v; });
    })).then(function () {
      // Attach cached app references back into the task objects.
      tasks.appsList = Array.from(appsBySlug.values());
      finalizeAliases();
      ready.state = 'ready';
      ready.resolve(tasks);
      if (global.OmniHooks && typeof global.OmniHooks.fire === 'function') {
        global.OmniHooks.fire('data-ready', tasks);
      }
    }).catch(function (err) {
      ready.state = 'error';
      ready.reject(err);
      console.error('[data] boot failed', err);
    });

    return ready.promise;
  }

  // Public API.
  var OmniData = {
    BASE: BASE,
    ENDPOINTS: ENDPOINTS,
    load: load,
    ready: function () { return ready.promise; },
    isReady: function () { return ready.state === 'ready'; },
    getApp: function (slug) {
      if (!slug) return null;
      var s = String(slug).toLowerCase();
      return appsBySlug.get(s) || appsByBundle.get(s) || null;
    },
    getApps: function () { return Array.from(appsBySlug.values()); },
    getByUrl: function (url) { return fetchJSON(BASE + url); },
    getTrending: function () { return cache[BASE + ENDPOINTS.trending] || null; },
    getHealth: function () { return cache[BASE + ENDPOINTS.health] || null; },
    getAnalytics: function () { return cache[BASE + ENDPOINTS.analytics] || null; },
    getStatus: function () { return cache[BASE + ENDPOINTS.status] || null; },
    getRelated: function () { return cache[BASE + ENDPOINTS.related] || null; },
    getVerification: function () { return cache[BASE + ENDPOINTS.verification] || null; },
    getSources: function () { return cache[BASE + ENDPOINTS.sources] || null; },
    getCollections: function () { return cache[BASE + ENDPOINTS.collections] || null; },
    getCommunity: function () { return cache[BASE + ENDPOINTS.community] || null; },
    getUpdates: function () { return cache[BASE + ENDPOINTS.updates] || null; },
    getSearchIndex: function () { return cache[BASE + ENDPOINTS.search] || null; },
    // Lazy compare matrix.
    getCompareMatrix: function () {
      if (cache[BASE + ENDPOINTS.compare]) return Promise.resolve(cache[BASE + ENDPOINTS.compare]);
      return fetchJSON(BASE + ENDPOINTS.compare);
    },
    // Aliases for fuzzy search.
    getAliases: function () { return { list: ALIASES, reverse: aliasMap }; },
  };

  global.OmniData = OmniData;

  // Auto-boot unless disabled (e.g. tests).
  if (!document.documentElement.dataset.omniNoBoot) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', load, { once: true });
    } else {
      load();
    }
  }
})(window);
