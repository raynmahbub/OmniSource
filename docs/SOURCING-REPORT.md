# Sourcing report — OmniSource additions from RyukSign & Senumy

Date: 2026-09-10 · Branch: `arena/01a08c5f-omnisource` · PR: https://github.com/raynmahbub/OmniSource/pull/42
Sources: `https://store.ryuksign.com/` and `https://senumy.com/ipa-library/` (jailbreak, emulator, tweaks, 3rd-party-store and IPA-installer pages)

This report records what was taken from those pages and what was skipped, with the reason.
Nothing was taken from a re-upload or a mirror: every catalogued app resolves from the
developer's own GitHub Releases or their own AltStore source.

## Inclusion rule

1. **Official upstream required** — the release must come from the developer's own GitHub Releases, or their
   own AltStore/Feather source. Aggregator re-uploads, account-gated mirrors and "store" pages are out.
2. **Maintained, or the final official build of a jailbreak tool** — a dormant project's *last* release is
   still catalogued when it is the only official jailbreak for a firmware range nothing else covers
   (Taurine / Odyssey / unc0ver / Serotonin). Dormant projects that are simply superseded are skipped.
3. **Installable by the clients the catalog serves** — AltStore, SideStore, Feather, ESign, LiveContainer.
   A build aimed at firmware older than those clients support has no consumer here.
4. **No near-duplicates** — one entry per product line, and no two entries that install over each other
   without declaring `alternativeTo`.

## Added (14 apps — catalog 49 → 63)

### RyukSign — 3 apps, all from the developer's own AltStore source

| Entry | Upstream | Notes |
| --- | --- | --- |
| `ryukgram` | `source.ryuksign.com/plugins` | Instagram mod with the plugin loader, v446.0.0, `com.burbn.instagram` |
| `ryukgram-ig410` | `source.ryuksign.com/ig410` | IG-410 line, v410.1.0, `com.burbn.instagram` |
| `ryukgram-sidebyside` | `source.ryuksign.com/duplicate` | Own bundle ID `com.ryuk.ryukgram`, installs next to real Instagram |

(`inkillerplus`, already in the catalog, now declares `alternativeTo: ryukgram` so the shared bundle ID is explicit.)

### Senumy — 11 apps, each re-sourced from its own project

| Entry | Category | Upstream |
| --- | --- | --- |
| `dopamine` | Jailbreak | `opa334/Dopamine` — v3.0.9 |
| `dopamine-roothide` | Jailbreak | `roothide/Dopamine2-roothide` — "2.4.9.26" |
| `bootstrap` | Jailbreak | `roothide/Bootstrap` — .tipa, iOS 15–17 |
| `serotonin` | Jailbreak | `mineek/Serotonin` — final .tipa (16.5.1–16.7 RC / 17.0), `unmaintained` |
| `taurine` | Jailbreak | `Odyssey-Team/Taurine` — final build for 14.0–14.3, `unmaintained` |
| `odyssey` | Jailbreak | `Odyssey-Team/Odyssey` — final build for 13.0–13.7, `unmaintained` |
| `unc0ver` | Jailbreak | `pwn20wndstuff/Undecimus` — final build, 11.0–14.8.1, `unmaintained` |
| `sameboy` | Emulator | `LIJI32/SameBoy` — `sameboy_ios_v1.0.3.ipa` |
| `manicemu` | Emulator | `Manic-EMU/ManicEMU` — SideloadJIT IPA |
| `xenios` | Emulator | `xenios-jp/XeniOS` — Xbox 360, `release-*` channel, iOS 18+ |
| `gopeed` | Utility | `GopeedLab/gopeed` — `Gopeed-1.9.3-ios.ipa` |

Icons for these were pulled from each project's own asset catalog and normalized into `assets/`.

## Skipped — with reasons

### RyukSign

* **Root source `source.ryuksign.com/`** — "all apps (6)": it aggregates the six variant feeds below;
  there is no seventh app hiding in it.
* **`/noplugins`, `/ig410-noplugins`, `/ig410-duplicate`** — the same product with the plugin loader
  stripped or mirrored; they share the bundle identifiers (`com.burbn.instagram` / `com.ryuk.ryukgram`)
  of the builds that were catalogued, so each would install over an existing entry.
* **`/apt/` packages** (`com.faroukbmiled.ryukgram` 1.4.0 and `.legacy` 1.3.3) — Cydia/Sileo `.deb`
  tweaks for jailbroken devices, not AltStore apps.

### Senumy — third-party stores listed on the library page

SenIPA, Velixa, AppleJr, MapleSign, IPA Installer, JBIPAs, Sileem, zJailbreak, Cydia 2, Redensa,
AppleGPT, Safari 3DX, Apple AI Search, Emula, Zentify, CoolStore, TutuPro, Panda Helper, iOSGods,
iOS Ninja, AppValley, Ela Themes, Android on iOS, ryOS, Scylla, Scarlet, TutuBox — these are stores
or store-like tools, not apps with their own release channel, and several redistribute paid software.
`SideStore` from the same page was already in the catalog.

### Jailbreak page — skipped entries

| Group | Entries | Reason |
| --- | --- | --- |
| Pre-iOS-12 era | EverPwnage (7.0–9.3.6), Phoenix, Home Depot, Pangu, Saigon, Yalu102, H3lix, DoubleH3lix, g0blin, Meridian, LiberiOS, p0insettia, Kok3shi9, Electra, Chimera | Last official builds target firmware older than any client this catalog serves; mostly distributed as `.ipa` via Impactor-era flows or as `.deb`. |
| No installable release | Relaxin, NathanLR, XinaA15, KFDmineek, Cherimoya, Meow / MEOWBREK2, Xinam1ne, Freya15, Manticore (web-based), OdysseyRa1n, Rootless, Flux6, Socket, Ra1ncloud | Upstream publishes source, a web tool or a `.deb`, but no official `.ipa`/`.tipa` in its releases (or the repository is gone). |
| `.deb` / desktop only | palera1n, checkra1n | Official releases are `.deb` packages / desktop tooling, not sideloadable apps. |
| Superseded or dormant | Fugu15 Max, Od1n, u0Launcher, SaiGon15, CanYouJB | No longer maintained, and their firmware coverage is already served by Dopamine / Serotonin / unc0ver. |

### Emulator page — skipped entries

| Entries | Reason |
| --- | --- |
| PPSSPP, UTM, DolphiniOS, Delta, Provenance | Already in the catalog. |
| Play!, Flycast, GearBoy | Official releases ship no iOS `.ipa`. |
| iPSX2, Limón, iSSB, GC4iOS, SNES4iOS, GamePad, iDOS | No maintained official upstream with an installable IPA (forks or abandoned projects only). |
| MeloNX | The upstream repository is gone; only a 0-star fork remains (`nurtrino/MeloNX`). |
| iGBA, GBA Emu, iMAME, Snake '97 | App Store listings or re-uploads; no official sideload source. |
| Happy Chick | Third-party store. |
| iNDS | Official upstream and IPA exist, but the project stopped in March 2021 and is superseded by the maintained DS-capable emulators above. |

### Tweaks page — skipped entries

| Entries | Reason |
| --- | --- |
| iTorrent, Aidoku, uYou+ | Already in the catalog. |
| Watusi, Infuse Plus, CyDown, CrackerXI+, Power Selector, Chroma Hue, StoreControl, Violyn, Instagram Plus, VideoStar++, ScreenshotX, Facebook (NoAds), YouTube Reborn, iTransmission, Countdown-App, CPU-X, OldOS, Spotify Plus | Cydia/Sileo `.deb` tweaks (or paid/hosted-only builds); no official standalone IPA. YouTube Reborn verified: release assets are `.deb` only. CPU-X and OldOS repositories are gone. |
| Enmity | Upstream repository publishes no release assets. |
| AdGuard, Loon, Widgy, Keka | App Store / macOS products. |
| CyPwn Store | Third-party store. |

### Unresolvable

* **Misaka** — the upstream is a product site with no release assets and no authoritative bundle
  identifier, so an official-sourced entry can't be authored. Third-party copy IPAs are re-uploads.
* **IPA Installer** (senumy.com/ipa-library/ipa-installer) — Senumy's own install flow; downloads only
  through its account-gated store.

## Caveats

* `source.ryuksign.com` is not reachable from this working sandbox, so the three RyukGram entries were
  built from their `manualRelease` snapshots (exact URLs/sizes read from the live feed earlier today);
  the scheduled sync will refresh them once merged. A pipeline fix in this branch makes `manualRelease`
  the last-resort fallback when a new app's upstream is unreachable and no cached state exists yet.
* Senumy download links are account-gated; none were used.
