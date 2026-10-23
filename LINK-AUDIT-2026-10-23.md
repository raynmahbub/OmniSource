# Link audit — 2026-10-23

A pass over every link the repository publishes (catalog → feeds → API → pages →
docs), with dead targets replaced by their current upstream or removed when the
upstream no longer exists.

## How it was checked

| Surface | Method |
| :-- | :-- |
| Catalog upstreams and every GitHub URL in the tree (827 distinct repositories) | `GET /repos/{owner}/{repo}` — a `200` with a different `full_name` is a rename, `404` is a dead repository |
| Published download links (108 GitHub release assets) | `GET /releases/tags/{tag}` and an exact asset-name match, with tag/asset URL-decoding |
| Screenshots (`raw.githubusercontent.com`) | `GET /contents/{path}` against the declared branch |
| Internal hrefs/src/srcset, sitemap and anchors | `scripts/audit_site_integrity.py`, `scripts/audit.py`, `make smoke` |
| Non-GitHub download hosts that this environment cannot reach directly | the publisher's own index (`apt.cercube.com/Packages`) and the Internet Archive metadata API, read directly |

## Upstreams that moved (links replaced)

| App | Was | Now |
| :-- | :-- | :-- |
| Conduit | `cogwheel0/condui` | `cogwheel0/conduit` |
| Spotube | `KRTirtho/spotube` | `team-spotube/spotube` |
| Streamyfin | `fredrikburmester/streamyfin` | `streamyfin/streamyfin` |
| Orbot | `guardianproject/orbot-ios` | `guardianproject/orbot-apple` |
| Serotonin | `mineek/Serotonin` | `SerotoninApp/Serotonin` |
| Dopamine (roothide) | `roothide/Dopamine2-roothide` | `roothide/Dopamine-roothide` |
| Mornye (was SpotiFLAC Mobile) | `spotiflacapp/SpotiFLAC-Mobile` | `mornyeapp/Mornye` |
| Onside TV (was Nebulo) | `mongoosemonke504/NebuloIPTV` | `mongoosemonke504/OnsideTV` |

The last two are product renames, not just owner moves: the catalog entry,
subtitle, description, screenshots and `descriptionTemplate` follow the new name
while the slug (and therefore every feed, page and API URL) stays stable.

## Links that were dead and are now updated

- **YouMod, YouPro, YouTubePlus, uProVid** — `mrdrvt99/YouProEXTRA` rotates its
  release tags (the old `ytl-ipa6`, `youmod-ipa2`, `youproextra-ipa2`,
  `ASJTube-ipa3` tags were deleted). Re-synced to `ytl-ipa7` / `youmod-ipa1` /
  `youproextra-ipa4` (YouTube 21.42.4), and uProVid's stand-in now points at the
  publisher's own `asjrx/ASJTube` v1.4 IPA (YouTube 21.39.4) instead of a mirror
  upload that had been removed.
- **Cercube** — `apt.cercube.com/files/com.cercube.ios_6.1.3_*.deb` 404s. The
  package moved on to 6.4.2; the entry now pins
  `com.cercube.ios_6.4.2_iphoneos-arm64.deb` (plus arm/arm64e fallbacks) with the
  SHA-256 published in the repository's `Packages` index.
- **Screenshots** — `spotiflacapp/SpotiFLAC-Mobile/assets/readme/{1,2,3}.jpg` no
  longer exist; the entry uses `mornyeapp/Mornye/assets/readme/showcase-light.png`.
- **Docs** — the QR library link in `docs/FEATURES-P0-P3.md` pointed at
  `lifthrasiir/qrcode.js` (deleted); it now points at `soldair/node-qrcode`, the
  package the CDN URL actually resolves to. The two sourcing reports and the
  SideStore screenshot-host record follow the renamed repositories.
- **Discovery data** — 43 dead repositories pruned from
  `data/discovered_sources.json` and 44 from `data/quarantine/sources.json`, plus
  dead source/download samples and duplicate old-name records in
  `data/status.json`, `data/source_registry.json` and the derived intelligence
  documents.

## Entries removed because the upstream is gone

The GitHub accounts/repositories behind these four apps were deleted, and no
fork publishes a release: the artifacts are gone, not moved.

| App | Former upstream | Evidence |
| :-- | :-- | :-- |
| Jaility | `haxi0/Jaility` | `404`; the account's 14 remaining repositories do not include it |
| KillMyOTA | `haxi0/KillMyOTA` | `404`; surviving forks have no releases |
| TrollBoard Reborn | `haxi0/TrollBoard-Reborn` | `404`; surviving forks have no releases |
| PlayTorrio | `ayman708-UX/PlayTorrioV3` | account `404`; every fork has no releases |

Removing the catalog entries also removed their feeds (`feeds/<slug>.json|xml`,
`feeds/single/`), app pages, API documents (`api/v2/apps`,
`api/v3/apps|sources`), source pages, sitemap rows and icons, so nothing 404s or
advertises a dead download.

## Fixes that keep links honest going forward

- `scripts/build_ipa_downloader.py` now emits canonical, Open Graph and Twitter
  tags; the page was the only one on the site without them.
- `stage_readme` no longer returns early when the README carries only the live
  statistics block. The front page had been advertising a stale app count and a
  `2026-10-05` sync date; it now refreshes from the build.

## Verification

- Catalog: 127 apps (was 131), feed and API documents rebuilt from the same state.
- `scripts/validate.py`: 0 errors. `publish_root --check`: root mirrors `feeds/`.
- `scripts/check_reproducible.py`: 897 generated files stable on an offline rebuild.
- `scripts/audit_site_integrity.py`: 0 broken local URLs, 0 structural problems.
- `scripts/audit.py`: 0 broken internal links, 0 sitemap 404s, 0 pages missing SEO
  metadata (259 pages).
- `make smoke`: all checks pass, root and `_site` artifact.
- `python3 -m unittest discover -s tests`: 619 tests, OK (2 skipped).
- Every one of the 108 GitHub-hosted download links resolves to a live release asset.

## Remaining, by design

- `uYouEnhanced` reuses the Internet Archive item that publishes the build. The
  file is present (the item's metadata lists `yt-uYE-21144-305.ipa`, 135 840 058 B,
  matching the catalog size), but the archive's CDN often exceeds the 25 s probe
  timeout, so the health board still shows it as unreachable until a probe lands.
- Five download probes (`Glow`, `TTKillerPlus`, `iMe MxGram`, `iNKillerPlus`,
  `iQFace`) were already failing against third-party hosts on the last live run;
  those hosts are not reachable from this environment, so the next scheduled
  monitoring run re-tests them.
- Release descriptions quoted from upstream still contain the URLs upstream wrote
  at the time (e.g. a `KRTirtho/spotube` changelog link inside Spotube 5.1.2's
  notes). They are verbatim upstream text and are left untouched.
