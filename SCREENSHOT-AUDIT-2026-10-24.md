# Screenshot audit — 2026-10-24

A pass that replaces the empty preview galleries with screenshots published by
each app's own project, following the provenance rule in
`omnisource.validation._validate_screenshots`: the declared URL must live in the
developer's repository, never in ours and never in a third party's copy.

Before: **26 / 128** apps declared screenshots (69 images).
After: **54 / 128** apps declare screenshots (**151** images), 28 of them added
here.

## How each image was found

| Surface | Method |
| :-- | :-- |
| Every app repository (default branch tree) | `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1` |
| Candidate images | `screenshot*/`, `fastlane` screenshot sets, README-embedded images, `docs/images/`, `resources/` — icons, logos, banners, splash screens, bezels and credit avatars were excluded by name |
| Content check | every candidate was downloaded through the Contents API (Git blob fallback for files above the inline limit) and opened with Pillow: minimum 250 px a side, phone/tablet aspect ratio, not animated, no Xcode asset-catalog stubs and no git-lfs pointers |
| Manual review | contact sheets of all candidates; settings-only, error-state, duplicate and promotional-collage frames were dropped in favour of the app's own main screens |
| Verification | `scripts/validate.py` (0 errors), `scripts/smoke_test.py` (site + repo root), `scripts/check_reproducible.py --diff`, the 630-test suite, `scripts/validate_jq.sh` |

The mirror + thumbnail pass then copied every image into
`assets/screenshots/<slug>/<slug>-NN.<ext>` and produced the 480 px WebP
thumbnails, with the size and SHA-256 of each file recorded in
`feeds/screenshots.json`.

## Added (28 apps, 82 images)

| App | Repository | Branch | Images | First image |
| :-- | :-- | :-- | --: | :-- |
| Anx Reader | `Anxcye/anx-reader` | `develop` | 3 | 1320×2868 |
| AnymeX | `RyanYuuki/AnymeX` | `main` | 3 | 750×1334 |
| Apollo Reborn | `Apollo-Reborn/Apollo-Reborn` | `main` | 3 | 1206×2622 |
| Conduit | `cogwheel0/conduit` | `main` | 3 | 1206×2622 |
| Fladder | `DonutWare/Fladder` | `develop` | 3 | 1236×2745 |
| Glow | `dayanch96/Glow` | `main` | 3 | 1242×2688 |
| iMe | `m1ronx1412/mxgram` | `main` | 3 | 590×1280 |
| InfusePlus | `dayanch96/InfusePlus` | `main` | 3 | 1242×2688 |
| Jellify | `Jellify-Music/App` | `main` | 3 | 1290×2796 |
| JellyBook | `JellyBookOrg/JellyBook` | `main` | 4 | 1136×2470 |
| MAME4iOS | `yoshisuga/MAME4iOS` | `master` | 3 | 1080×2008 |
| Mangayomi | `kodjodevf/mangayomi` | `main` | 3 | 750×1334 |
| Monal | `monal-im/Monal` | `develop` | 3 | 1242×2208 |
| Onside TV (Nebulo) | `mongoosemonke504/OnsideTV` | `main` | 1 | 640×1391 |
| NeoFreeBird | `NeoFreeBird/app` | `v7` | 3 | 1170×2532 |
| Orbot | `guardianproject/orbot-apple` | `main` | 3 | 640×1136 |
| Otraku | `lotusprey/otraku` | `main` | 3 | 1080×2280 |
| PikaTorrent | `G-Ray/pikatorrent` | `main` | 3 | 1080×2400 |
| Saber | `saber-notes/saber` | `main` | 3 | 1320×2868 |
| Sora | `cranci1/Sora` | `dev` | 3 | 1284×2778 |
| Sparkle | `efibalogh/sparkle-ig` | `main` | 2 | 1206×2622 |
| Spotube | `team-spotube/spotube` | `master` | 3 | 492×875 |
| Streamyfin | `streamyfin/streamyfin` | `develop` | 3 | 684×1400 |
| Telegram mxgram | `m1ronx1412/mxgram` | `main` | 3 | 590×1280 |
| Thunder | `thunder-app/thunder` | `develop` | 3 | 1080×1920 |
| Turrit mxgram | `m1ronx1412/mxgram` | `main` | 3 | 590×1280 |
| Voyager | `aeharding/voyager` | `main` | 3 | 2160×3840 |
| Yattee | `yattee/yattee` | `main` | 3 | 1206×2622 |

36.6 MB of originals, 2.4 MB of WebP thumbnails.

## The one caveat, stated plainly

Thirteen of the entries above are cross-platform projects whose iOS build
shares the UI with the frames the project publishes for its mobile app:
AnymeX, Anx Reader, Fladder, Flutter-family entries (Mangayomi, Otraku, Saber,
Spotube, Thunder, JellyBook, PikaTorrent), Voyager and iMe/Turrit/Telegram
mxgram. Their repositories contain no separate iOS screenshot set — the iOS
target is the same Dart/React Native/Expo UI — so the project's own current
screenshots are the honest preview of what the iOS build shows. Nothing was
rendered, cropped, or mocked up to fill the gap. Apps whose projects publish
only Android-store art in a *different* UI were left empty instead.

The remaining **74 apps stay without screenshots on purpose**: 59 publish no
usable image anywhere in their repository (jailbreak utilities such as
Dopamine, TrollStore-family tools, iTorrent, ChatSen, TrollFools, the
DevelopCubeLab tweaks), and the rest keep their art only on external hosts that
either do not exist any more or that this environment cannot reach to verify
(`github.com/user-attachments/…`, `raw.githubusercontent.com` at pinned tags,
publisher depiction servers). A missing preview is better than an unverifiable
one: the app page says so, and `feeds/asset-manifest.json` records the gap.

## Baseline refresh

`screenshots.json` is network-dependent and deliberately excluded from the
reproducibility diff, but it is regenerated here so the committed manifest,
the mirrored bytes and the thumbnails stay consistent with the catalog. Four
stale mirror directories (BlueWallet, qBController, Synkplay, Zeus) were
removed: their candidate art was reviewed and rejected during this pass, so
neither the images nor the manifest entries survive.

## Mornye (spotiflac) — official rebrand assets

The entry still carried the pre-rebrand SpotiFLAC artwork: a green-on-black
"music download" circle that the project retired when SpotiFLAC Mobile became
Mornye in October 2026. Both assets now come from the project's own tree.

| Asset | Source | Notes |
| :-- | :-- | :-- |
| Icon (`assets/SpotiFLAC.{png,webp}`, 512×512) | `ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-1024x1024@1x.png` | the iOS app icon the project ships, downscaled with Lanczos; full-bleed Deep Teal `#1E4E4F` square with the Mist `#BBEBEC` mark, matching how the other catalog icons are cut |
| Screenshot 1 | `assets/readme/showcase-light.png` | the project's README showcase (Home, Library, Now Playing, Equalizer) — unchanged upstream, re-mirrored and re-thumbnailed |
| Screenshot 2 | `assets/readme/showcase-dark.png` | the dark-theme showcase, newly declared |

`tintColor` moves from Spotify green `#1DB954` to the brand's Deep Teal
`#1E4E4F` (`assets/brand/README.md` in the project lists Deep Teal, Mist, Ink
and Paper as the palette). The icon *filename* stays `SpotiFLAC.*`: it is a
published `iconURL` in the feeds and API, so renaming it would break consumers
for a cosmetic gain.

The showcase images are 1500×783 composites of four phone screens, not the
usual 9:19.5 phone capture. `.ap-screenshots img` used to force that ratio on
every tile, which squashed landscape art into a phone-shaped box; it now uses
`aspect-ratio: auto 9 / 19.5`, keeping the phone-shaped placeholder only until
the bytes land and then honouring each image's real proportions.
