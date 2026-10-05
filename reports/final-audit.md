# OmniSource Modernization — Final Audit

_Scoped deliverable of the 15-phase audit & modernization pass. Regenerate the eight
structural reports with `make audit`; this file is the hand-written summary of what
changed, what was verified, and what is deliberately left open._

## Headline

| Metric | Before (`9e5d89c`) | After |
| --- | --- | --- |
| HTML pages in the tree | 95 | 158 (+62 Source Explorer, +1 docs hub) |
| `data-i18n` hooks across pages | 1 535 | 5 802 |
| Locales / canonical keys | 8 × 108 | 8 × 151 (100 % parity, 0 orphans) |
| Reputation statuses per source | 1 legacy `level` | `level` **and** `status` (6 states) + `signals` |
| P0/P1 audit findings | several | **0** |
| Broken internal links / SEO gaps / sitemap errors | 392 + 10 + 0 | **0 / 0 / 0** |
| Unused files · dead globals · unused selectors · uncalled public functions | 27 + | **0 / 0 / 0 / 0** |
| Blocking (non-`defer`) script tags | 2 | **0** |
| Python tests | 235 | 235 passing (shell suite extended for `/sources/`, `js/modules/`, SW v11) |

## What each phase delivered

### 1 — Audit tooling
`scripts/audit.py` (1 241 lines, stdlib only) writes the eight structural reports; wired as
`make audit`. It scans the whole committed tree (generated pages included), resolves every
internal `href`/`src`/`srcset`/`fetch()` against the repository (which *is* what Pages serves in
branch mode), and reproduces the i18n contract. Findings that Phase 1 exposed were fixed in place
rather than reported, so the current run is clean by construction.

### 2 — Navigation IA
Primary nav is now `Home · Apps · Collections · Sources · Status · Docs`, with `Analytics ·
Compare · Favorites · Discover · Community · What's new · Trending · Graph · Install · Search ·
RSS · GitHub` behind “More”. Applied to the home page, all ten hand-maintained section pages, the
generated `apps/**` pages and the new `sources/**` pages. The mobile drawer (`js/core.js`
`setupMobileNav`) and the `.nav-more` CSS needed no change; `aria-current`/`.active` marking is
consistent, and exactly one nav item is current per page (asserted in `tests/test_website_shell.py`).

### 3 — Premium UI
Hero now reads **One Source. / Every Source. / Discover trusted AltStore-compatible
repositories.** with Quick install · Source explorer · GitHub CTAs. Six feature cards (Source
Discovery, App Explorer, Health Monitoring, Verification, Collections, Developer APIs) render
with `data-reveal` staggered reveals, shared `.feature-icon` strokes, token colors only. Animated
stats (`data-count`) already drove the home page and are now reused on `/sources/` via
`js/modules/utils.countUp`. Reduced motion is honored globally by `animations.css`; dark mode
still comes from the pre-paint bootstrap (no flash).

### 4 — Source Explorer (new)
`src/omnisource/source_pages.py` (510 lines) owns the section:

- `feeds/sources.json` **schema v2** — additive enrichment of the discovery index: `slug`, `page`,
  `status`, `score`, `level`, `healthScore`, `appCount`, `verifiedApps`, `updateFrequencyDays`,
  `lastUpdate`, `feedURL`, plus a top-level `statuses` histogram.
- `sources/<slug>/index.html` — 61 static, self-contained pages (design-system CSS, theme
  bootstrap, canonical/OG/Twitter/JSON-LD, localized nav) carrying name, maintainer, source URL,
  app count, update frequency, health score, verification ratio, reputation score and last update.
- `sources/index.html` — interactive explorer: typo-tolerant fuzzy filter, status `<select>` +
  chips, four sort keys, animated hero stats, and a server-rendered `<noscript>` table that the
  publisher refreshes between `<!-- sources:static:start/end -->` markers on every build.
- Slugs are generated once (lowercase folding of the source identity + numeric collision
  suffixes) and shipped inside `sources.json`, so pages, sitemap and website can never disagree.
- Registration: `SITE_FILES`, `API_DOCUMENTS` description, `SITE_PAGES` (`/sources/` + `/docs/`),
  sitemap (`_source_slugs`), service-worker core precache, `sync.yml` commit allowlist, smoke test
  (page ids + one detail page per source).

### 5 — Reputation model
`src/omnisource/reputation.py` composes six weighted signals (`jsonValidity` 25, `uptime` 20,
`updateFrequency` 15, `releaseActivity` 15, `brokenLinks` 15, `metadataCompleteness` 10) into
`score`, and maps score + signals to `status`:
`Verified · Community Verified · Maintained · Warning · Inactive · Deprecated` (archived or
all-inactive apps ⇒ Deprecated; no release in 365 days ⇒ Inactive; invalid entries, broken
releases or unreachable downloads ⇒ Warning; ≥85 with ≤180-day cadence ⇒ Verified; ≥70 ⇒
Community Verified). `level` is retained for existing consumers, and the pre-modernization formula
is still published as `metrics.legacyScore`. Each source exposes `signals`, `metrics` and
`lastUpdate`. Current distribution over 61 sources: 49 Community Verified, 6 Inactive,
5 Deprecated, 1 Warning.

### 6 — Localization recovery
`locales/*.json`: 8 locales × 151 keys, 100 % parity, placeholder parity, no orphaned keys —
verified by both `tests/test_translations.py` and `scripts/validate-translations.js`
(`feeds/translation-status.json` stays build-owned at 100 % for all eight locales). The contract
that made breadth possible: generated and module-rendered markup declares its keys with
`<!-- i18n-keys: … -->` markers (`tests/test_translations.py` now scans `js/modules/`, and
`translate()` is a recognized call site), so nav/hero/feature/source strings are translated on
every page rather than only on the home page.

### 7 — Modular JavaScript
`js/modules/` adds 12 ES modules (1 187 lines): `utils` (esc/fetchJSON/relDays/countUp/translate/
localize), `search` (bigram Dice + capped Levenshtein + field weights), `status` (reputation
presentation), `theme`, `store`, `sources`, `favorites`, `analytics`, `compare`, `install`,
`collections`, `pwa`. Named exports only; no module writes to `window`. `theme.js` defers to
`js/core.js` through a `data-theme-claimed` marker so the toggle can never bind twice. Pages load
them with `<script type="module">`; heavy pieces are imported lazily from the page entry point.
The legacy `js/*.js` facade keeps every existing contract (95+ pages and saved bookmarks depend on
`OS`), now documented as a compatibility layer.

### 8 — Search upgrade
`js/modules/search.js` is the shared fuzzy core: accent/case folding, exact > prefix > word-prefix
> substring > typo-tolerant ranking, per-field weights, conjunctive multi-term matching,
capped edit-distance budget (≤1 error at 4 chars, 2 at 7+), `<mark>` highlighting that escapes
everything it emits. Cost is O(length) per field, so it stays instant at thousands of apps; the
generated `feeds/search-index.json` remains the payload both the ⌘K palette and `/sources/` filter
consume.

### 9 — Performance
Verified with the proxies this environment can measure: 0 blocking script tags (the last two, in
`collections/collection.html`, are now `defer`red), all site JS deferred, 4 CSS files (166 KiB
source, minified for `_site/`), one fetch per feed per page load (`jsonMemo` / `fetchJSON` cache),
deferred anchor scrolling, WebP-first logo + `loading="lazy"` on every icon below the fold, and
SW v11 precaching the new pages and modules with network-first APIs / cache-first assets /
SWR metadata. **Not measured:** an actual Lighthouse run — see “Remaining”.

### 10 — Workflows
`.github/workflows/sync.yml`: commit allowlist extended to `sources/**` and `docs/index.html` so
the branch-deployed Pages mode publishes the new trees; every job (build → unittest → validate →
jq → reproducible → artifact → deploy), `validate.yml`, `health-check.yml`, `merge.yml` and the two
manual IPA builders are unchanged in behaviour. `scripts/*.py` and `scripts/*.sh` were linted and
formatted with the repo’s ruff config; `make audit` is the new entry point for the structural
reports; `pyproject.toml` needed one per-file ignore for the report generator’s long table lines.

### 11 — Repository weight
The generated mirror families (`api/*` ↔ `feeds/*`, `.gz` twins) are **kept**: GitHub Pages serves
the branch, so `/apps.json` and `/api/*` must be committed, and subscribers fetch the `.gz` names
directly. `tests/test_website_shell.py` enforces byte-identity, so the duplication cannot drift.
Everything else stays build-time: `_site/` (flat URL family, minified CSS, gz/br copies) is
assembled by `scripts/build_site.py` and never committed. `reports/duplicates.md` lists the 104
mirror groups explicitly as accepted technical debt with the removal procedure.

### 12 — Documentation
`docs/ARCHITECTURE.md` (module-layer map, Source Explorer flow, SW v11, `sources.json` v2 in the
contract table), `docs/website.md` (Source Explorer + module layer sections), `docs/localization.md`
(the four coverage contracts), `docs/REPOSITORY.md`/`README.md`/`CONTRIBUTING.md` (npm/pip SDK
paths, sources data note, website conventions: modules-first, i18n contract, generated trees are
never hand-edited), and a generated `docs/index.html` hub that lists every Markdown doc with the
title/summary read from the file itself, so the hub cannot drift.

### 13 — Accessibility (WCAG AA)
Structural scan over hand-maintained and sampled generated pages: 0 findings. Concretely: skip
links on `/sources/`, `sources/<slug>/`, `docs/` and `/translation-status/`; heading order fixed on
`/analytics/` and `/favorites/` (no h1→h3/h4 jumps); every new control labelled
(`a11y.filterSources`, `a11y.sortSources`, `sr-only` labels for the selects, `aria-current`,
`role="menu"`/`menuitem`, `aria-live` on the stats and result regions); focus-visible rings and
status colors from tokens only; `<details>/<summary>` nav with Escape handling and outside-click
close from the legacy shell (reused, not reimplemented).

### 14 — SEO
`reports/links.md`: 0 broken internal targets, 0 pages missing title/description/canonical/OG/
Twitter (all 158 HTML files scanned), 0 unresolvable sitemap URLs. Added: `twitter:card` set on
`/discover/`, `/graph/`, the collection templates (so all regenerated collection pages inherit
it), `/translation-status/`, `/compare/` redirect stub (`noindex,follow` + canonical to
`/compare/`), the docs hub, and every `sources/**` page. Each source detail page also emits
JSON-LD `Dataset` with provider; `/sources/` emits an `ItemList`. `sitemap.xml` gained `/sources/`,
`/docs/` and all 61 detail URLs (0.7, weekly).

### 15 — Production hardening
Hardening landed as: CSP meta replicated on the new pages; every interpolation in generated HTML
escaped (`html.escape` in Python, `esc()` in modules); `atomic_write_text` for crash-safe
generation; stale-page pruning for both `apps/` and `sources/` (removed upstreams cannot leave a
404-ing route); sitemap/canonical derived from the same slug map; the smoke test now also proves
that each source has a detail page carrying the explorer contract; `publish_root.py --check`,
`check_reproducible.py` (595 generated files stable) and `validate.py` all pass in `make check`.

## Files

**Added (86 paths)**

| Path | What |
| --- | --- |
| `src/omnisource/source_pages.py` | Source Explorer generator: `sources.json` v2 + static `sources/<slug>/` pages |
| `src/omnisource/docs_index.py` | generated `docs/index.html` hub |
| `scripts/audit.py` | eight structural reports (`make audit`) |
| `js/modules/` (12 files) | ES-module layer (Phase 7/8) |
| `sources/index.html` + `sources/<slug>/index.html` × 61 | Source Explorer pages |
| `docs/index.html` | docs hub |
| `reports/{dead-code,duplicates,localization,performance,workflows,accessibility,links,recommendations}.md` | audit output |

**Modified (540 paths)** — 489 generated mirrors refreshed by the pipeline
(`api/` 231, `feeds/` 181, `apps/` 77), plus hand-maintained: `index.html`; the ten section
pages (`analytics`, `collections/index`, `compare`, `discover`, `favorites`, `graph`, `install`,
`search`, `status`, `translation-status`); `compare.html`; `collections/collection.html`;
`sw.js` (v11 + new precache entries); `assets/design-system/{tokens,components,utilities,animations}.css`;
`locales/*.json` (8); `js/core.js` (theme-claim marker); `src/omnisource/{pipeline,site,reputation,
app_pages,collections,assets,tracking}.py`; `scripts/smoke_test.py`; `tests/{test_translations,
test_website_shell}.py`; `pyproject.toml`; `Makefile`; `README.md`; `CONTRIBUTING.md`;
`.github/workflows/sync.yml`; `docs/{ARCHITECTURE,localization,website}.md`; `sitemap.xml`.

**Removed** — no tracked file was deleted. Within files: 27 unreferenced CSS selectors
(`utilities.css` and dead `.page-hero*`, `.search-page-head*`, `.os-grad-anim`, `.os-bars`,
`.hairline-*` blocks), two dead public functions (`assets.probe_screenshot_urls`,
`tracking.validate_version_entry`), the retired `nav.catalog` key (replaced by `nav.apps` in
every nav), and the old 11-flat-links header row (superseded by the two-tier IA).
`compare.html` remains as a redirect stub — it is a published URL that existing bookmarks use.

## Verification

```
make check → ruff check + format --check (99 files), validate.py (0 errors),
             validate_jq.sh, unittest (235 tests OK), publish_root --check,
             merge_feeds --check, check_reproducible (595 files stable),
             smoke_test (81 URLs) + smoke_test --root (133 URLs, 15 pages, 19 feeds × 3 families)
make audit → 0 unused files / globals / selectors / functions, 0 broken links,
             0 SEO gaps, 0 sitemap errors, 0 a11y findings, 0 workflow drift,
             100 % locale parity with 0 orphaned keys
node scripts/validate-translations.js → all eight locales 100 %
```

## Remaining recommendations

1. **Lighthouse run** — this sandbox has no Chrome, so the >95 targets are supported by
   structural proxies (0 blocking scripts, deferred JS, minified CSS, precached shell) rather than
   measured. Run `npx lighthouse https://raynmahbub.github.io/OmniSource/` (and `/sources/`) in CI or
   locally and paste the four scores into `reports/performance.md` before the public release.
2. **`Verified` coverage is currently 0 sources** — the strictest status needs a source with zero
   broken releases, zero unreachable probes *and* ≤180-day cadence. It will light up as probes
   accumulate; do not lower the bar to make the badge look busier.
3. **`api/` ↔ `feeds/` duplication** stays until Pages stops serving the branch. When it does:
   drop `API_DOCUMENTS` mirroring in `src/omnisource/site.py`, delete the committed `api/` tree,
   relax `test_repo_root_publishes_apps_json_and_api_mirror` and `publish_root.py --check`, and
   shrink the `sync.yml` allowlist in one PR.
4. **Legacy globals** (`window.OS`, `root.OmniI18n`) remain the compatibility facade for 95+
   pages and the app-page generator. Removing them requires converting every page to module
   entry points and re-generating `apps/**`; new code should import `js/modules/*` instead.
5. **`updateFrequencyDays` is `null` for most sources** — the reputation window only measures gaps
   it can see in `feeds/state.json` (one kept version for most apps). Setting `keepVersions: 0` on
   a catalog entry makes real cadence (and the `Verified` gate) computable.
6. **Manual browser pass** — RTL (ar) layout of the new `/sources/` toolbar and feature grid,
   VoiceOver/NVDA on the status chips, and a reduced-motion spot check, which no static audit can
   cover.
