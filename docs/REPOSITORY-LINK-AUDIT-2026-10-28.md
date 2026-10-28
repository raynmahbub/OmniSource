# Repository and download-link audit — 2026-10-28

This report describes the local branch, not a deployment. Link availability can
change; a publisher listing or an HTTP redirect does not prove the destination
still serves the expected IPA. No current IPA was downloaded, hashed, inspected,
or signature-verified for this audit.

## Changes made

- Preserved the existing `spotiflac` slug and feed URLs while publishing the
  current name **Mornye**, bundle identifier `com.zarz.mornye`, and publisher
  [`mornyeapp/Mornye`](https://github.com/mornyeapp/Mornye). Its current
  publisher-listed release is v5.2.6.
- Updated the existing `ytlite` entry to **YouTube Plus** using the community
  [`mrdrvt99/YouProEXTRA`](https://github.com/mrdrvt99/YouProEXTRA) IPA while
  retaining its slug, aliases, and per-release iOS requirements. YouPro and
  YouMod track their current publisher releases and retain community attribution.
- Refreshed publisher-listed URLs for Infuse Plus, Swiftgram MxGram, RyukGram,
  Sparkle, NexaSC, ThreadSaver, Turrit MxGram, iNKillerPlus and TTKillerPlus.
  Corrected raw-GitHub feed publisher links and Flow project attribution.
- Removed copied YouTube permission descriptions from unrelated apps. Missing
  permissions mean **unknown**, not that the app has none. Removed an
  unsupported Glow tweak-version assertion from its current fallback.
- Prevented missing feeds, empty results, failed failover chains and mismatched
  app identities from being silently counted as incremental successes or
  replacing cached releases with unrelated data. Incremental hits are bound to
  the actual previous URL and asset selection policy. Multi-version histories
  refresh fully, and the scheduled publisher now does a daily full metadata sync.
- Kept 18 previously misattributed history entries as explicitly quarantined
  evidence: six RedditFilter records under Glow and 12 iQTele records under
  MxGram variants. They cannot be selected for rollback or inflate release
  cadence. Publisher feed snapshots distinguish the iQTele and MxGram bundle
  identifiers. Quarantine does not assert that the underlying IPA is unsafe.
- Added a dated warning next to download actions when the latest failed probe
  belongs to the current URL. A cached result for a different or unspecified URL
  remains unknown.

## Remaining issues and limitations

1. **Glow, iMe MxGram and Messenger Flow:** their last-known IPA URLs returned
   HTTP 404 in the 2026-10-27 monitoring snapshot and those apps were absent
   from the current IPA Vault feed. The entries remain visible with warnings and
   cached versions; no equivalent replacement IPA was established. The official
   [Flow](https://github.com/dayanch96/Flow) and
   [Glow](https://github.com/dayanch96/Glow) projects publish tweak packages,
   not a verified replacement IPA for these entries. The normal feed validator
   reports six warnings (each affected app in the aggregate and individual feed).
2. **Unverified binary availability:** the nine refreshed IPA Vault/iKarwan
   URLs above came from publisher feed metadata, but this sandbox could not
   reach their binary hosts. GitHub release URLs tested at the origin returned
   success or redirects; the redirect targets and IPA bytes were not validated.
   Run independent download and integrity checks from an unrestricted network.
3. **Shared bundle identifiers:** the metadata validator reports 13 warnings
   for intentional alternative builds of Instagram, Twitter, YouTube,
   YouTube Music and Messenger. Their catalog relationships are declared, but
   installers may replace or conflict with another build sharing the same ID;
   the warning is not proof that variants install side by side.
4. **Discovery quarantine:** the source validator reports 658 quarantined
   discovery records. These are retained candidates, not 658 active download
   failures or findings that the projects are malicious. They require separate
   review before admission.
5. **Historical observations:** the source-registry builder can append a new
   timestamped observation on an unchanged rebuild, so older source trend/uptime
   history must not be treated as independently repeated live probes. Current
   projections exclude unknown health samples; the underlying history was not
   rewritten. Historical IPA links outside the quarantined mismatches have not
   all been revalidated.
6. **Toolchain:** npm reports that ESLint 9.39.5 is out of support; the current
   lockfile passed `npm audit` with zero known vulnerabilities. An upgrade
   requires separate compatibility testing.

## Checks performed

- Static audit: zero P0 findings. Site integrity: 261 HTML pages and 10,901
  local URLs checked; zero broken local links, duplicate IDs, missing titles,
  missing language attributes, missing image alt attributes or missing English
  i18n keys. A separate check found zero missing targets among 760 absolute
  links back to this site; a heuristic Markdown scan found no broken relative
  targets among 76 links in 53 Markdown files.
- External origin checks: 115 GitHub download origins and 126 other GitHub
  links appearing in HTML returned 2xx/3xx; redirects were not followed to
  validate binary contents. GitHub's contents API reported 132 raw-GitHub HTML
  asset paths present; this is repository metadata, not a byte-level check.
  These checks do not cover every external URL.
- `scripts/validate.py`: zero errors and six known download warnings.
  `scripts/validate_jq.sh`: 1,176 JSON files and 129 feeds passed. Root and API
  `apps.json` match `feeds/apps.json` byte-for-byte. The downloader index is
  current.
- Python suite: 737 tests passed with the jsdom harnesses installed. Ruff
  checks and formatting passed. Web typecheck, lint, tests, production build
  and npm audit passed. Offline rebuild reproduced 1,461 generated files.
  The assembled-site and repository-root HTTP smoke tests passed.

## Next operator action

From a network that can reach the publisher hosts, run
`python3 scripts/monitoring/check_downloads.py` and independently verify any
replacement against its app identity and expected digest. To update persisted
health deliberately, see the snapshot-import procedure in
[FEATURE-OPERATIONS.md](FEATURE-OPERATIONS.md). Do not substitute a different
app or tweak solely because its link is reachable.
