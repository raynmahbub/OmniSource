# OmniSource — feature suggestions

Companion to `ISSUES-REPORT.md`. Suggestions are scoped to the constraints the project has
deliberately chosen: **static GitHub Pages delivery, stdlib-only Python, no build step, no
frameworks, no user tracking, provenance transparency.** Everything below is achievable without
a server.

**Implementation status:** See [Feature operations](docs/FEATURE-OPERATIONS.md)
for the static features, commands and limitations now implemented. Historical
versions accumulate from future syncs rather than fabricated backfills; archives
require per-app opt-in and external storage, issue intake is review-only,
reminders have no background push, and the hash chain is not a publisher
signature. Screenshots still require declared developer-owned origins. Figures
and recommendations below are the original proposal's snapshot, not live totals.

A few numbers that shaped the original list:

| fact | value | why it matters |
|---|---|---|
| apps / upstream sources | 77 / 61 | small enough to do expensive things per-app |
| releases in the last 7 days | 25 | incremental work touches ~1/3 of the catalog per week |
| releases in the last 30 days | 58 | enough activity to make "what's new" genuinely useful |
| total bytes of all newest IPAs | **8.0 GB** (median 55 MB, max **1,076 MB**) | rules out "verify everything every run"; demands incremental |
| apps sharing a bundle ID | 15 across 4 groups | ~19% of the catalog is hard to install from the master feed |
| apps with real screenshots | 12 / 77 | the preview gallery is mostly icon fallbacks |
| `compatibility.minOSVersion` in `catalog.json` | 77 / 77 | data exists, but see Tier 1 #2 |

---

## Tier 1 — highest leverage

### 1. Release history and one-tap rollback

**What.** Stop throwing the past away. Raise `upstream.keepVersions` from `1` to ~8 (one app
already keeps 3, and the knob exists), store every resolved version in `state.json`, and publish
the full `versions[]` array — each entry with its own `downloadURL`, `size`, `sha256` and
`date` — in the per-app feeds and `api/v2/apps/{id}/versions.json`.

**Why it is the single biggest unlock.** AltStore and SideStore already let a user pick an older
version from a source that offers `versions[]`; today OmniSource offers one, so a bad update is
unrecoverable. It also *fixes the root cause of four separate problems already in the repo*:

* reputation scores stop collapsing — 49 of 61 sources currently score exactly 73.9 because
  cadence is computed from a single version (`ISSUES-REPORT.md` #4)
* "removed upstream release" stops misfiring on every normal version bump (#2)
* trending, update cadence and the 90/180/365-day staleness thresholds get a real time series
* changelogs become diffable: "what changed between the version you have and the newest"

**How.** Mostly configuration plus one new document. `select_versions()` already implements
retention; `updateHistory` already records 85 real update events, so the pipeline knows how to
track history — it just isn't per-app. Storage cost is metadata only (no IPAs are retained).

**Effort:** M.

---

### 2. Emit real compatibility into the feed, then filter on it

**What.** Two halves:

1. **Fix the gap:** `catalog.json` carries `compatibility.minOSVersion` for all 77 apps, but
   `render_altstore_app()` (`src/omnisource/feeds/altstore.py:33-49`) never writes `minOSVersion`
   into the feed entry. So the *website* can show "iOS 16+" (it reads
   `app.omnisource.compatibility`) but **AltStore / SideStore / Feather receive no compatibility
   signal at all** and will happily offer an app the user's device cannot run. Emit
   `minOSVersion` (and `maxOSVersion`, and the `devices` / `clients` lists) into the entry.
2. **Build the feature:** a "my device" control — pick iOS version, device family and client —
   stored in `localStorage`, that greys out anything incompatible and shows a one-line reason
   ("needs iOS 17.0, you selected 16.4"). Plus a per-app "Works on your device: yes / no /
   unknown" strip.

**Why.** "Will this run on my iPhone?" is the first question every sideloader asks, and iOS
version support is the most common reason an install fails after the download succeeds. The data
is already collected and maintained; it just never reaches the client. Half of this is a
five-line bug fix.

**Effort:** S for the feed emission, M for the UI.

---

### 3. A binary transparency log

**What.** Make the integrity engine real and make its output a *ledger* rather than a snapshot.
On every build where an app's `(version, size)` tuple changes, stream the IPA, compute SHA-256,
and append a record to an append-only, hash-chained log committed to the repo:

```json
{"seq": 412, "prev": "9f2c…", "slug": "iqface", "version": "578.1",
 "sha256": "…", "size": 227188596, "firstSeen": "2026-09-11",
 "url": "https://…/Facebook-578.1-iQFace.ipa", "verifiedAt": "2026-09-12"}
```

Publish it as `api/transparency.json` + `feeds/transparency.json`, and surface two derived
signals: **"verified"** (bytes actually hashed this week) and **"re-uploaded"** (same version
string, different hash — the classic silent-swap signal in this ecosystem).

**Why it is the right differentiator.** Every competing source lists a checksum if the upstream
happened to publish one. Almost none prove the bytes match, and none tell you when a file changed
under a version number that didn't. For a catalog of repackaged IPAs from 61 third parties, that
is the trust product. And git *is* the tamper-evident log — the repo's own commit history, signed
by GitHub, anchors every entry for free.

Cost control matters: the whole catalog is **8.0 GB** (one IPA alone is 1,076 MB), so verify
**incrementally** — only changed `(version, size)` pairs, ~25 apps/week, median 55 MB. That fits a
weekly job with a long timeout, or a per-app matrix.

**How.** `src/omnisource/integrity.py:185` `verify_downloads()` is already written and currently
called by nothing (see `ISSUES-REPORT.md` #3). This is that function, plus persistence, plus a
chain hash.

**Effort:** M (the verifier exists; the ledger and the two derived signals are new).

---

### 4. Collision-aware "Build my source"

**What.** Generate one master-feed variant per collision-group member — 15 files
(`feeds/variants/<group>/<slug>.json`) — each being the full master feed with exactly one member
of the group present. Then add a short flow: *"Which YouTube app do you want?" → pick → here is
your source URL.* Also publish a `recommended` pick per group and make the default `apps.json`
carry only the recommended member of each colliding group.

**Why.** 15 of 77 apps share just 4 bundle IDs — `com.google.ios.youtube` ×7,
`com.atebits.Tweetie2` ×3, `com.burbn.instagram` ×3, `com.google.ios.youtubemusic` ×2
(`ISSUES-REPORT.md` #7). AltStore-family clients key on bundle ID, so today a user adding the one
URL the project markets gets an arbitrary member of each group, and SideStore cannot add two at
all. The README tells them to work around it with per-app feeds; that works, but it means giving
up the whole catalog. This gives them both.

15 pre-generated files is well inside what a static site can carry, and it needs no server-side
logic.

**Effort:** M.

---

## Tier 2 — strong product features

### 5. Re-sign expiry tracker

**What.** Let a user mark an app installed (date + whether they're on a free or paid Apple ID).
Store it in `localStorage`, compute the 7-day (free) / 365-day (paid) expiry, and show a countdown
badge on cards, in `/favorites/`, and on the PWA icon area. Offer a local browser notification the
day before.

**Why.** For anyone sideloading without AltStore's daemon or SideStore's on-device refresh, apps
silently stop opening after 7 days. It is the single most recurring pain in this space and no
source or catalog handles it. It is also *perfectly* suited to this project: pure client state, no
backend, no tracking, and it makes the PWA something users open daily rather than once.

**Effort:** S–M.

### 6. Update notifications that work without a server

**What.** Three cheap layers, in order of effort:

* **iCalendar release feed** — publish `/feeds/updates.ics` (and per-app / per-collection
  variants). Users subscribe in any calendar app and get real notifications. Zero infra, works on
  iOS natively, and it is the only push mechanism available to a static site.
* **"New since your last visit"** — store a timestamp in `localStorage`, diff against
  `api/updates.json`, and badge the nav and the relevant app cards.
* **Filtered RSS** — per-collection and per-category feeds, not just per-app.

**Why.** The site already builds `updates.json` and per-app RSS; the missing piece is getting
"there is a new build" in front of a user who isn't visiting the site. An `.ics` file is a
genuinely unusual and completely server-free answer.

**Effort:** S for the ICS feed, S for last-visit, S for filtered RSS.

### 7. "Pick for me" decision guide

**What.** A five-question quiz — iOS version, signing client, and the capabilities they care
about (SponsorBlock, PiP, downloads, 4K, no-ads, background audio) — that ranks the colliding
variants and explains *why* each ranked where it did.

**Why.** Seven apps share the YouTube bundle ID and the compare page is a generic side-by-side
table; users still have no way to choose. This needs one new optional field in `catalog.json`
(`features: []`, plus a short `bestFor` string), which is a maintainable curation cost, and it
converts OmniSource from "a list" into "an answer".

**Effort:** M (data curation dominates; the UI is small).

### 8. Permissions and entitlements, with a diff between versions

**What.** 42 of 77 apps already carry `appPermissions`. Standardise the panel (entitlements,
privacy usage strings), and once Tier 1 #1 lands, show what *changed*: "this update added
2 entitlements and a new Photos usage description."

**Why.** The audience is installing modified IPAs from third parties. "What can this build see,
and what did the new build change?" is exactly the question a transparency-first catalog should
answer — and nobody shows the diff.

**Effort:** S once version history exists.

---

## Tier 3 — ecosystem and scale

### 9. IPA introspection

During the weekly verification stream, read the zip central directory, parse
`Payload/*.app/Info.plist`, and record the **real** bundle ID, version, minimum OS and
entitlements. Cross-check against `catalog.json`. This catches mislabeled, repackaged and renamed
IPAs, auto-populates `minOSVersion` (Tier 1 #2) instead of trusting hand-entered values, and feeds
the permissions panel (#8). Cost is bounded because it rides the same incremental stream as #3.

### 10. Last-known-good archive (opt-in per app)

When an upstream genuinely yanks a release — which the fixed detector from `ISSUES-REPORT.md` #2
will finally identify correctly — the download 404s and every installed copy loses its update
path. Archive the last known good IPA to a durable host (you already use archive.org for
uYouEnhanced) for apps that opt in via `archive: true` in `catalog.json`. Prioritise community
builds and `status: manual` entries. **Expensive — 8 GB at full coverage** — so treat it as an
opt-in insurance policy for a subset, not a blanket mirror.

### 11. Issue-ops for contributors

When an "app request" issue is opened, run a validation job that probes the proposed upstream,
checks for bundle-ID collisions, dry-runs the sync, and posts a comment with the verdict plus a
ready-to-merge `catalog.json` snippet. Same for "broken upstream" → open a PR marking the app
`unmaintained`. This is the biggest lever on maintainer toil. **Handle with care:** the workflow
must not interpolate issue titles or bodies into shell (`ISSUES-REPORT.md` #1 is exactly that
mistake in another file).

### 12. Source-to-source migration and diff

Paste any other AltStore source URL and see: which of its apps OmniSource already has, which it's
missing (with a prefilled request-issue link), and which of your apps have newer versions here.
Client-side fetch works for sources that send CORS headers; for the rest, fall back to a
`workflow_dispatch` job that comments the diff on an issue. Directly addresses "I already use
three sources, why switch?"

---

## Quick wins (hours, not days)

* **Emit `minOSVersion` / `maxOSVersion` / `devices` into feed entries** — the data is already in
  `catalog.json` for 77/77 apps and clients silently ignore it today.
* **Screenshot coverage** — only 12/77 apps have any, and `screenshots.json` shows most entries as
  `iconFallback: true`. Harvest `screenshotURLs` from upstream AltStore feeds during sync (the
  uYouEnhanced entry proves upstreams publish them; they're currently skipped as "non-image URL").
  Biggest visual upgrade available on the app pages.
* **Fix `api/collections.json`** — every collection has `name: null`, so any consumer keying on
  it gets nothing.
* **Per-app size warnings** — the largest IPA is 1,076 MB; surface it prominently on the download
  button rather than after a long download over cellular.
* **Drop the RSS `lastBuildDate` churn** — one line, and it stops 79 files changing on every build
  (`ISSUES-REPORT.md` #6).

---

## What I would deliberately *not* build

* **Web Push / a notification service.** Breaks the static-only model and introduces a server to
  operate. The `.ics` feed (#6) reaches iOS users better for free.
* **Download counts or install telemetry.** Conflicts with the no-tracking stance, and GitHub
  release download counts are already surfaced where available.
* **A dynamic per-user source builder with a real backend.** The pre-generated variant approach
  (#4) gets 95% of the value with none of the operational cost.
* **Mirroring every IPA** (#10 at full coverage). 8 GB per snapshot for a volunteer-run repo is a
  liability, not a feature. Keep it opt-in and narrow.

---

## Suggested sequence

1. **#1 version history** — unblocks rollback and repairs reputation, cadence, staleness and the
   dead-app false positives in one move.
2. **#2 compatibility** — half bug fix, half headline feature.
3. **#4 collision-aware sources** — makes the master feed work for the 19% it currently fails.
4. **#3 transparency log** — the trust story the README already claims, finally backed by bytes.
5. **#5 + #6** — the two features that make users open the PWA every day.
6. Quick wins whenever, then #7–#12 as appetite allows.
