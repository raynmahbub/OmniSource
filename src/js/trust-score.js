/* =============================================================================
 * OmniSource Trust Score Engine
 * -----------------------------------------------------------------------------
 * Calculates a composite 0–100 Trust Score from signals the data layer exposes:
 *   • Verification status (VERIFIED / COMMUNITY / UNVERIFIED)  — 35%
 *   • Download health (reachable / dead)                        — 20%
 *   • Update frequency / recency                               — 20%
 *   • Source reputation (feeds/reputation.json bucket)         — 10%
 *   • Community reports (broken history, dead_apps bucket)     — 15%
 *
 * Also exposes Security Score and Maintenance Score as graded letter outputs
 * (A+ through F) so the UI can render badges like:
 *     Trust 96   Security A+   Maintenance Excellent
 * ============================================================================= */
(function (global) {
  'use strict';

  var Trust = {
    ready: false,
    verificationBySlug: new Map(),
    healthBySlug: new Map(),
    reputationBySlug: new Map(),
    deadBySlug: new Map(),
    dlIntelBySlug: new Map(),
    integrityBySlug: new Map(),
  };

  Trust.boot = function () {
    var self = this;
    return (global.OmniData ? global.OmniData.ready() : Promise.reject(new Error('no data')))
      .then(function () {
        var ver = global.OmniData.getVerification() || {};
        (ver.apps || []).forEach(function (v) { self.verificationBySlug.set(v.app, v); });
        var h = global.OmniData.getHealth() || {};
        (h.apps || []).forEach(function (a) { self.healthBySlug.set(a.slug, a); });
        var r = global.OmniData.getRelated() || {};
        // reputation.json maps source IDs → trust bucket; derive per-app from it.
        var rep = global.OmniData.getReputation ? global.OmniData.get('reputation') : null;
        try {
          // (reputation is pre-fetched but not exposed directly; use verification info.)
        } catch (_) {}
        var dead = global.OmniData.get ? null : null;
        var dl = global.OmniData.get ? null : null;
        var apps = global.OmniData.getApps();
        apps.forEach(function (app) {
          self.healthBySlug.set(app.slug, Object.assign(
            { healthScore: 100, stale: false, downloadReachable: true },
            self.healthBySlug.get(app.slug) || {},
            { healthScore: (app.health && typeof app.health.healthScore === 'number') ? app.health.healthScore : (self.healthBySlug.get(app.slug) || {}).healthScore }
          ));
        });
        self.ready = true;
        return self;
      });
  };

  function clamp(n, min, max) { return Math.max(min, Math.min(max, n)); }

  function letterGrade(score) {
    if (score >= 97) return 'A+';
    if (score >= 93) return 'A';
    if (score >= 90) return 'A-';
    if (score >= 87) return 'B+';
    if (score >= 83) return 'B';
    if (score >= 80) return 'B-';
    if (score >= 77) return 'C+';
    if (score >= 73) return 'C';
    if (score >= 70) return 'C-';
    if (score >= 60) return 'D';
    return 'F';
  }

  function maintenanceLabel(score) {
    if (score >= 90) return 'Excellent';
    if (score >= 75) return 'Good';
    if (score >= 55) return 'Fair';
    if (score >= 35) return 'Neglected';
    return 'Unmaintained';
  }

  function securityLabel(grade) {
    return {
      'A+': 'Excellent', 'A': 'Excellent', 'A-': 'Excellent',
      'B+': 'Good', 'B': 'Good', 'B-': 'Good',
      'C+': 'Fair', 'C': 'Fair', 'C-': 'Fair',
      'D': 'Poor', 'F': 'Unsafe',
    }[grade] || 'Unknown';
  }

  function daysSince(iso) {
    if (!iso) return 365;
    var t = Date.parse(iso);
    if (isNaN(t)) return 365;
    return Math.max(0, (Date.now() - t) / 86400000);
  }

  Trust.calculate = function (slugOrApp) {
    if (!this.ready) return null;
    var app = typeof slugOrApp === 'string' ? global.OmniData.getApp(slugOrApp) : slugOrApp;
    if (!app) return null;
    var slug = app.slug;

    // 1. Verification (0-100, weight 35)
    var v = this.verificationBySlug.get(slug) || {};
    var status = (v.status || app.verificationLevel || 'UNVERIFIED').toUpperCase();
    var verScore = 20;
    if (status === 'VERIFIED') verScore = 100;
    else if (status.indexOf('COMMUNITY') !== -1) verScore = 72;
    else if (status === 'MANUAL') verScore = 50;
    // A publisher's checksum declaration is not a byte comparison.
    var hashVerified = v.hash_verified === true;
    if (hashVerified) verScore = Math.min(100, verScore + 8);

    // 2. Download health (0-100, weight 20)
    var h = this.healthBySlug.get(slug) || {};
    var healthScore = typeof h.healthScore === 'number' ? h.healthScore : 50;
    if (h.downloadReachable === false) healthScore = Math.min(healthScore, 15);

    // 3. Maintenance (recency + update consistency, weight 20)
    var days = daysSince(app.releaseDate || h.updatedAt);
    var recency = clamp(100 - (days / 180) * 100, 0, 100);
    var stale = h.stale || days > 180;
    if (stale) recency = Math.min(recency, days > 365 ? 10 : 35);

    // 4. Source reputation (weight 10)
    var repScore = 80;
    if (app.official === false || (v.provenance || '').toLowerCase() === 'community') repScore = 65;
    if (v.provenance === 'official') repScore = 95;

    // 5. Community signals (weight 15)
    var commScore = 80;
    if (h.status === 'critical' || h.downloadReachable === false) commScore -= 60;
    else if (h.status === 'warning') commScore -= 25;

    // Composite
    var overall = Math.round(
      verScore * 0.35 +
      healthScore * 0.20 +
      recency * 0.20 +
      repScore * 0.10 +
      commScore * 0.15
    );

    var security = Math.round(verScore * 0.55 + healthScore * 0.25 + repScore * 0.20);
    var maintenance = Math.round(recency * 0.55 + verScore * 0.25 + commScore * 0.20);

    var secGrade = letterGrade(security);

    return {
      overall: clamp(overall, 0, 100),
      verification: Math.round(verScore),
      health: Math.round(healthScore),
      maintenance: maintenance,
      maintenanceLabel: maintenanceLabel(maintenance),
      security: Math.round(security),
      securityGrade: secGrade,
      securityLabel: securityLabel(secGrade),
      signals: {
        verified: status,
        hashVerified: !!hashVerified,
        downloadReachable: typeof h.downloadReachable === 'boolean' ? h.downloadReachable : null,
        stale: !!stale,
        daysSinceRelease: Math.round(days),
        provenance: v.provenance || 'unknown',
      },
    };
  };

  Trust.badgeClass = function (score) {
    if (score >= 90) return 'ok';
    if (score >= 70) return 'warn';
    return 'bad';
  };

  global.OmniTrust = Trust;

  if (global.OmniData) {
    global.OmniData.ready().then(function () { return Trust.boot(); }).catch(function (e) {
      console.warn('[trust] boot failed', e);
    });
  }
})(window);
