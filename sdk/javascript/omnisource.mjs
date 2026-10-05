/**
 * OmniSource JavaScript SDK.
 *
 * A small, dependency-free client for the public OmniSource API. Designed to
 * run in both the browser and Node 18+ environments. All public methods
 * return promises.
 *
 *   const client = new OmniSource({ baseURL: 'https://example.com/OmniSource' });
 *   const trending = await client.getTrending();
 *
 * The SDK never throws on transport errors — every method returns a
 * resolved promise with an empty / null fallback. The error is also
 * published on ``client.lastError`` so callers can inspect the cause
 * without needing a try/catch.
 */
export class OmniSourceError extends Error {
  constructor(message, { status, url, body } = {}) {
    super(message);
    this.name = 'OmniSourceError';
    this.status = status;
    this.url = url;
    this.body = body;
  }
}

const DEFAULT_BASE_URL = 'https://raynmahbub.github.io/OmniSource';
const DEFAULT_TIMEOUT = 8000;

// Linear-time trailing-slash trim. (A /\/+$/ regex backtracks
// quadratically on slash-heavy input, so it must not run on
// caller-supplied URLs.)
function stripTrailingSlashes(value) {
  let end = value.length;
  while (end > 0 && value.charCodeAt(end - 1) === 47) end--;
  return value.slice(0, end);
}

export class OmniSource {
  constructor({ baseURL = DEFAULT_BASE_URL, fetch: fetchImpl, timeout = DEFAULT_TIMEOUT } = {}) {
    this.baseURL = stripTrailingSlashes(baseURL);
    this.timeout = timeout;
    this.lastError = null;
    this.fetch = fetchImpl || ((url, options) => {
      if (typeof fetch !== 'function') {
        return Promise.reject(new Error('No fetch implementation available'));
      }
      return fetch(url, options);
    });
  }

  async _get(path) {
    const url = `${this.baseURL}/${path.replace(/^\/+/, '')}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    try {
      const res = await this.fetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } });
      if (!res.ok) {
        const body = await res.text().catch(() => '');
        this.lastError = new OmniSourceError(`Request failed (${res.status})`, { status: res.status, url, body });
        throw this.lastError;
      }
      this.lastError = null;
      return res.json();
    } catch (error) {
      if (!(error instanceof OmniSourceError)) {
        this.lastError = new OmniSourceError(error.message || 'Network error', { url });
      }
      throw this.lastError;
    } finally {
      clearTimeout(timer);
    }
  }

  /** Search the catalog with the same fuzzy weights as the website. */
  async search(query, { limit = 12, verifiedOnly = false } = {}) {
    const data = await this._safe('feeds/search-index.json', { documents: [], fuse: { keys: [] } });
    const keys = (data.fuse && data.fuse.keys) || [];
    const q = String(query || '').toLowerCase().trim();
    if (q.length < 2) return [];
    const docs = data.documents || [];
    const results = [];
    for (const doc of docs) {
      let score = 0;
      for (const key of keys) {
        const field = doc[key.name];
        if (Array.isArray(field)) {
          for (const v of field) score += key.weight * this._fuzzy(q, String(v).toLowerCase());
        } else {
          score += key.weight * this._fuzzy(q, String(field || '').toLowerCase());
        }
      }
      if (score >= 0.4) results.push({ doc, score });
    }
    results.sort((a, b) => b.score - a.score);
    let out = results.slice(0, limit).map(item => item.doc);
    if (verifiedOnly) out = out.filter(d => d.verificationLevel === 'VERIFIED');
    return out;
  }

  _fuzzy(q, value) {
    if (!value) return 0;
    if (value === q) return 1;
    if (value.startsWith(q)) return 0.85;
    if (value.includes(q)) return 0.65;
    const tokens = q.split(/\s+/).filter(Boolean);
    const hits = tokens.filter(t => value.includes(t)).length;
    if (!hits) return 0;
    return 0.45 * (hits / tokens.length);
  }

  /** Get one app by slug. */
  async getApp(slug) {
    const [discovery, install] = await Promise.all([
      this._safe('discovery.json', { apps: [] }),
      this._safe('feeds/install.json', { apps: [] })
    ]);
    const meta = (discovery.apps || []).find(app => (app.slug || app.id) === slug);
    if (!meta) return null;
    const installCard = (install.apps || []).find(card => card.slug === slug);
    return { ...meta, install: installCard ? installCard.cards : [] };
  }

  /** List apps, optionally filtered. */
  async listApps({ category, status } = {}) {
    const data = await this._safe('discovery.json', { apps: [] });
    return (data.apps || []).filter(app => {
      if (category && app.category !== category) return false;
      if (status && app.status !== status) return false;
      return true;
    });
  }

  /** Get the trending board. */
  async getTrending() {
    return this._safe('feeds/trending.json', { trending: [], rising: [], recentlyUpdated: [] });
  }

  /** Get related apps for the given slug. */
  async getRelated(slug) {
    const data = await this._safe('feeds/related.json', { related: {} });
    return data.related && data.related[slug] ? data.related[slug] : [];
  }

  /** Get source reputation. */
  async getReputation() {
    return this._safe('feeds/reputation.json', { sources: [] });
  }

  /** Get health / download intelligence. */
  async getHealth() {
    return this._safe('feeds/download-intelligence.json', { apps: [], summary: {} });
  }

  /** Get the analytics document. */
  async getAnalytics() {
    return this._safe('feeds/analytics.json', { totals: {} });
  }

  /** Get community lists. */
  async getCommunity() {
    return this._safe('feeds/community.json', { popular: [], recentlyAdded: [], rising: [], requested: [] });
  }

  /** Get install cards for one app, or the master feed. */
  async getInstall(slug) {
    const data = await this._safe('feeds/install.json', { apps: [], master: { cards: [] } });
    if (!slug) return data.master;
    const entry = (data.apps || []).find(item => item.slug === slug);
    return entry ? entry.cards : [];
  }

  /** Get a side-by-side comparison. */
  async getCompare(left, right) {
    const data = await this._safe('feeds/compare.json', { pairs: [] });
    return (data.pairs || []).find(p =>
      (p.left.slug === left && p.right.slug === right) ||
      (p.left.slug === right && p.right.slug === left)
    );
  }

  /** Get the precomputed search index. */
  async getSearchIndex() {
    return this._safe('feeds/search-index.json', { documents: [] });
  }

  async _safe(path, fallback) {
    try {
      return await this._get(path);
    } catch (error) {
      return fallback;
    }
  }
}

export default OmniSource;
