/* =============================================================================
 * OmniSource Compare Engine
 * -----------------------------------------------------------------------------
 * Dynamic, client-side comparison for ?app1={slug}&app2={slug}. Lazy-loads the
 * comparison matrix (feeds/compare.json) only when needed, then:
 *   • Builds a side-by-side matrix
 *   • Scores each app across size/recency/trust/compatibility/health
 *   • Generates a recommendation summary with "winner" reasoning
 *   • Updates URL + metadata for shareable deep links
 *
 * The engine is framework-free and works against the existing feeds/compare.json
 * format, so no pipeline changes are required for it to function.
 * ============================================================================= */
(function (global) {
  'use strict';

  var CompareEngine = {
    matrix: null,
    loading: false,
    pending: null,
  };

  // Load the comparison matrix (3.6MB) once and cache it.
  CompareEngine.load = function () {
    var self = this;
    if (this.matrix) return Promise.resolve(this.matrix);
    if (this.loading) return this.pending;
    this.loading = true;
    this.pending = (global.OmniData ? global.OmniData.getCompareMatrix() : Promise.reject(new Error('no data layer')))
      .then(function (data) {
        self.matrix = data || { pairs: [] };
        // Build a slug1+slug2 index (canonical order).
        self._index = new Map();
        (self.matrix.pairs || []).forEach(function (p) {
          var a = (p.left && p.left.slug) || '';
          var b = (p.right && p.right.slug) || '';
          if (!a || !b) return;
          var key = a < b ? a + '|' + b : b + '|' + a;
          self._index.set(key, p);
        });
        self.loading = false;
        return self.matrix;
      })
      .catch(function (err) {
        self.loading = false;
        console.warn('[compare] failed to load matrix', err);
        throw err;
      });
    return this.pending;
  };

  // Pull two full app records (from the data layer, not just the compare summary),
  // so we can render richer metadata even before the matrix resolves.
  function getApps(slug1, slug2) {
    return {
      left: global.OmniData.getApp(slug1),
      right: global.OmniData.getApp(slug2),
    };
  }

  // Find a pair in the matrix.
  CompareEngine.findPair = function (slug1, slug2) {
    if (!this._index) return null;
    var key = slug1 < slug2 ? slug1 + '|' + slug2 : slug2 + '|' + slug1;
    return this._index.get(key) || null;
  };

  // Score an app across several dimensions (0-100 each). Returns an overall score
  // plus the breakdown for the per-row highlighting.
  function scoreApp(summary, pairData) {
    var verificationScore = { VERIFIED: 100, 'COMMUNITY VERIFIED': 75, COMMUNITY: 75, MANUAL: 50, UNVERIFIED: 25 }[summary.verificationLevel] || 30;
    var healthScore = summary.downloadReachable === true ? 100 : summary.downloadReachable === false ? 10 : 50;
    // Recency: newer is better; decay over 180 days.
    var daysAgo = 0;
    if (summary.releaseDate) {
      var t = Date.parse(summary.releaseDate);
      if (!isNaN(t)) daysAgo = Math.max(0, (Date.now() - t) / 86400000);
    }
    var recencyScore = Math.max(0, Math.round(100 - (daysAgo / 180) * 100));
    // Update frequency: more frequent updates = better maintenance.
    var gap = summary.updateFrequencyDays || 0;
    var updateScore = gap <= 0 ? 40 : Math.max(10, Math.min(100, Math.round(100 - (gap / 60) * 80)));
    // Compatibility: more clients = better.
    var compatDevices = (summary.compatibility && summary.compatibility.devices) || [];
    var compatScore = Math.min(100, 40 + compatDevices.length * 15);

    var overall = Math.round(
      verificationScore * 0.30 +
      healthScore * 0.25 +
      recencyScore * 0.20 +
      updateScore * 0.15 +
      compatScore * 0.10
    );

    return {
      overall: overall,
      verification: verificationScore,
      health: healthScore,
      recency: recencyScore,
      maintenance: updateScore,
      compatibility: compatScore,
    };
  }

  // Build a structured comparison for two slugs. The result is a plain object
  // that the UI can feed into any renderer.
  CompareEngine.compare = function (slug1, slug2) {
    var self = this;
    return this.load().then(function () {
      var apps = getApps(slug1, slug2);
      if (!apps.left || !apps.right) {
        return { error: 'App not found', slug1: slug1, slug2: slug2 };
      }
      var pair = self.findPair(slug1, slug2) || { left: apps.left, right: apps.right };
      // The matrix only stores summaries; fill in any missing fields from the catalog.
      var leftSummary = Object.assign({}, apps.left, pair.left || {});
      var rightSummary = Object.assign({}, apps.right, pair.right || {});
      var leftScore = scoreApp(leftSummary, pair);
      var rightScore = scoreApp(rightSummary, pair);

      // Determine recommendation.
      var winner = null;
      var reasons = [];
      if (leftScore.overall > rightScore.overall + 5) { winner = 'left'; }
      else if (rightScore.overall > leftScore.overall + 5) { winner = 'right'; }

      if (winner) {
        var w = winner === 'left' ? leftSummary : rightSummary;
        var wscore = winner === 'left' ? leftScore : rightScore;
        reasons.push(w.name + ' scores higher overall (' + wscore.overall + '/100).');
        if (wscore.verification >= 90) reasons.push('Its declared source meets the catalog metadata checks.');
        if (wscore.health >= 90) reasons.push('Its download was reachable at the last recorded check.');
        if (wscore.recency >= 70) reasons.push('It was updated recently.');
      } else {
        reasons.push('Both apps score similarly — pick based on the features you need.');
      }

      return {
        left: { summary: leftSummary, score: leftScore },
        right: { summary: rightSummary, score: rightScore },
        winner: winner,
        reasons: reasons,
        shareBundle: !!pair.shareBundle,
        shareCategory: !!pair.shareCategory,
        matrixRow: pair,
      };
    });
  };

  // Build a comparison matrix (rows of fields) for the table view.
  CompareEngine.buildMatrix = function (result) {
    var L = result.left.summary; var R = result.right.summary;
    var LS = result.left.score; var RS = result.right.score;
    function row(label, lval, rval, key, hint) {
      var better = null;
      if (typeof lval === 'number' && typeof rval === 'number') {
        if (lval > rval) better = 'left';
        else if (rval > lval) better = 'right';
      }
      return { label: label, left: lval, right: rval, better: better, key: key, hint: hint };
    }
    return [
      row('Version', L.version || '—', R.version || '—', 'version'),
      row('Released', L.releaseDate || '—', R.releaseDate || '—', 'date'),
      row('Category', L.category || '—', R.category || '—', 'category'),
      row('Developer', L.developerName || L.developer || '—', R.developerName || R.developer || '—', 'developer'),
      row('Source', (L.source || '—'), (R.source || '—'), 'source'),
      row('Verification', L.verificationLevel || '—', R.verificationLevel || '—', 'verification'),
      row('Last download probe', L.downloadReachable === true ? 'Reachable' : L.downloadReachable === false ? 'Failed' : 'Not checked', R.downloadReachable === true ? 'Reachable' : R.downloadReachable === false ? 'Failed' : 'Not checked', 'health'),
      row('Update cadence', (L.updateFrequencyDays ? L.updateFrequencyDays + ' days' : '—'), (R.updateFrequencyDays ? R.updateFrequencyDays + ' days' : '—'), 'cadence'),
      row('Min iOS', (L.compatibility && L.compatibility.minOSVersion) || '—', (R.compatibility && R.compatibility.minOSVersion) || '—', 'minos'),
      row('Devices', ((L.compatibility && L.compatibility.devices) || []).join(', ') || '—', ((R.compatibility && R.compatibility.devices) || []).join(', ') || '—', 'devices'),
      row('Trust score', LS.overall, RS.overall, 'trust'),
      row('Maintenance', LS.maintenance, RS.maintenance, 'maintenance'),
    ];
  };

  // Parse ?app1=x&app2=y or legacy ?left=x&right=y from the URL.
  CompareEngine.parseUrl = function (search) {
    var params = new URLSearchParams(search || location.search);
    var a = params.get('app1') || params.get('left') || '';
    var b = params.get('app2') || params.get('right') || '';
    return { app1: a, app2: b };
  };

  // Update URL + document title for shareable deep links.
  CompareEngine.shareUrl = function (slug1, slug2) {
    var url = new URL(location.href);
    url.search = '';
    if (slug1) url.searchParams.set('app1', slug1);
    if (slug2) url.searchParams.set('app2', slug2);
    return url.pathname + url.search;
  };

  CompareEngine.updateUrl = function (slug1, slug2, opts) {
    var opts_ = opts || {};
    var p = this.shareUrl(slug1, slug2);
    if (opts_.replace) history.replaceState(null, '', p);
    else history.pushState(null, '', p);
    // Update metadata.
    var a = global.OmniData.getApp(slug1); var b = global.OmniData.getApp(slug2);
    if (a && b) {
      var title = a.name + ' vs ' + b.name + ' — OmniSource';
      document.title = title;
      var desc = 'Side-by-side comparison of ' + a.name + ' and ' + b.name +
                 ': version, developer, source, verification, health, update frequency and compatibility.';
      document.querySelector('meta[name="description"]').setAttribute('content', desc);
      document.querySelector('meta[property="og:title"]').setAttribute('content', title);
      document.querySelector('meta[property="og:description"]').setAttribute('content', desc);
    }
  };

  global.OmniCompare = CompareEngine;
})(window);
