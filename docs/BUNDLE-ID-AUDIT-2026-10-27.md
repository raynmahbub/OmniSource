# Bundle identifier audit — 2026-10-27

A source's bundle identifier should describe the **specific downloadable build** in the feed. It can differ from the stock app, the tweak's package identifier, another release configuration, or the identifier a signing client ultimately assigns. The existing slugs (including `spotiflac`) remain unchanged.

## Corrections

| Catalog entry | Identifier | Evidence for the tracked build |
| --- | --- | --- |
| Nuvio | `com.nuvio.media` | The [publisher's source](https://github.com/NuvioMedia/NuvioMobile/blob/61658f366f985fc7758f0942a14c1754c69aca68/store.json) lists the exact 0.6.4 release IPA under this ID. Its [updater](https://github.com/NuvioMedia/NuvioMobile/blob/0.6.4-beta/scripts/update-store-source.py) reads `CFBundleIdentifier` from the published IPA. `com.nuvio.app` is the debug configuration, not the release ID. |
| RedditFilter | `com.reddit.Reddit` | The [tagged tweak filter](https://github.com/level3tjg/RedditFilter/blob/v2025.37.0-1.1.8/RedditFilter.plist) targets Reddit, not Twitter; the [release workflow](https://github.com/level3tjg/RedditFilter/blob/v2025.37.0-1.1.8/.github/workflows/build.yml) builds the IPA from Reddit. |
| BHInstagram | `com.burbn.instagram` | The [tagged tweak filter](https://github.com/BandarHL/BHInstagram/blob/1.2/BHInsta.plist) targets Instagram. `com.bandarhl.bhinsta` is the [tweak package ID](https://github.com/BandarHL/BHInstagram/blob/1.2/control), not the app ID. [Earlier install logs](https://github.com/BandarHL/BHInstagram/issues/40) also show the Instagram identifier. The 1.2 IPA itself could not be inspected in this environment. |
| Swiftgram (MxGram) | `app.swiftgram.ios.mxgram` | The [IPA Vault source snapshot](https://github.com/927tx/IPA-Vault/blob/4f8d83c3bc46b3ecc36c0eb0d8becc9464c014d3/ipavaultsource.json) associates this ID with the exact Swiftgram 13.0 MxGram download. |
| Telegram MxGram | `ph.telegra.Telegraph.mxgram` | The same IPA Vault snapshot associates this ID with the exact Telegram 13.1.1 MxGram download. |
| Turrit MxGram | `com.seastar.turrit.mxgram` | The same IPA Vault snapshot associates this ID with the exact Turrit 1.5.6 MxGram download. |
| iMe MxGram | `com.olcorporation.olai.mxgram` | An [earlier IPA Vault snapshot](https://github.com/927tx/IPA-Vault/blob/63d456b5/ipavaultsource.json) associates this ID with the exact iMe 12.8.1 MxGram download, which is retained as a manual fallback. |

The four MxGram IPAs are **community builds**, not developer-published releases of their base apps. Their identifiers above come from the distributor's feed, not a claim that the base apps use those IDs. RedditFilter and BHInstagram IDs are supported by source and build evidence rather than direct inspection of these particular release archives.

## Rebrands checked

- Mornye (`spotiflac`): `com.zarz.mornye` in the [v5.2.6 iOS build settings](https://github.com/mornyeapp/Mornye/blob/v5.2.6/ios/Runner.xcodeproj/project.pbxproj).
- Onside TV (`nebuloiptv`): `tv.onside.app` in the [V3.0.0 app build settings](https://github.com/mongoosemonke504/OnsideTV/blob/V3.0.0/OnsideTV.xcodeproj/project.pbxproj); widget and test targets have separate IDs.

## Scope and safeguards

The review inspected candidate build settings, plists and tweak filters for 110 GitHub-backed entries, and compared available distributor-feed entries to their tracked download URLs. An identifier appearing somewhere in a repository does not by itself establish the release IPA's identity: configurations, overrides and signing can change it. Some feeds and release-asset hosts were inaccessible from the audit environment, so this is not a claim that every one of the 128 IPAs was independently inspected.

A feed selected by name now rejects an upstream entry that explicitly reports a different bundle identifier; the pipeline retains the last known release instead of silently publishing it under the wrong ID. Feeds without a bundle-ID field remain usable but cannot be verified by that check. Regression tests check the audited IDs and that catalog values propagate to the combined, per-app, API v2 and API v3 outputs.

BHInstagram now joins an existing Instagram bundle-ID collision group. The pre-existing v3 URLs for iNKillerPlus and both RyukGram entries are reserved so they do not silently start pointing to another app; BHInstagram receives its own `-4` record. The web app resolves the same aliases. Other corrected bundle-based v3 URLs can change, and a bundle-ID correction can cause an installer to treat the app as a different installation. The stable catalog slugs and API v2 paths are unchanged.
