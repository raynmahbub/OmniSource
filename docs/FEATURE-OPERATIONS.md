# Static feature operations

OmniSource keeps `catalog.json` hand-maintained and publishes static files. It
has no accounts, activity tracking, ratings, hosted notification service, or
automatic binary mirroring. The controls below do not change the master feed or
establish that an app is safe.

## Release history and compatibility

Upstreams configured with `keepVersions: 8` request up to eight releases on
future syncs. Existing history is not fabricated or backfilled with unverified
URLs. An app's retained versions are available at
`/api/v2/apps/<slug>/versions.json` and on its static app page. Historical URLs
can disappear or be replaced upstream; check the version and its recorded
SHA-256 before considering a downgrade. Rollback and data migration are not
guaranteed.

The feed exposes the latest declared minimum/maximum OS and device/client
metadata. A browser profile stores only the selected values locally. A match
means that the selected fields agree with catalog declarations, not that the
IPA is signed, installable, or compatible with every device. Missing or
unparseable requirements remain unknown.

## Download evidence and IPA inspection

`feeds/verification.json` separates the source attribution and legacy
metadata-check level from `digestEvidence`: `unavailable`, `recorded`,
`matched`, or `mismatch`. A recorded checksum is not proof that bytes were
compared. A match identifies the bytes read against the recorded digest, whose
publisher origin is not automatically established. An observed digest, size,
or bundle-ID mismatch is flagged for review; a timeout is an unavailable
check, not proof of corruption.

`feeds/transparency.json` and `/api/transparency.json` form an initially empty,
hash-chained log of complete byte observations actually made by the verifier.
The chain can reveal changes relative to a previously saved head; it cannot
prevent a complete rewrite without an independent checkpoint, or prove who
published an IPA. Changed-asset verification cannot detect a silent swap with
the same version, URL and size until a full recheck. The workflow checks
changed assets weekly and performs a full recheck monthly. It retains failed
run evidence as an Actions artifact and publishes structurally valid reports
alongside the corresponding generated outputs.

For a deliberate local check (this performs network downloads and modifies
verification state and generated files):

```bash
python3 scripts/omnisource.py --no-sync --no-health --verify-downloads \
  --verify-changed --inspect-ipa --only spotiflac
```

`--inspect-ipa` uses temporary storage outside the repository, capped at 1.5
GiB per asset; hashing continues when an inspection exceeds the cap. It reads a
bounded ZIP directory and main `Payload/*.app/Info.plist` without extracting or
executing the app. ZIP64, oversized/ambiguous archives, `.deb` files, and
unreadable plists remain uninspected. Packaged entitlement plists are optional
declarations, **not verified code-signature entitlements**. Permission diffs
are shown only when both retained versions have comparable declarations; an
absent history is not treated as an empty permissions list.

Independent monitoring snapshots are not silently folded into offline builds.
To explicitly import a snapshot, first run the dry run, then apply and rebuild:

```bash
python3 scripts/monitoring/import_snapshot.py
python3 scripts/monitoring/import_snapshot.py --apply
python3 scripts/omnisource.py --no-sync --no-health
```

The importer accepts only a matching app and current download URL and preserves
the original observation time. Fallback repairs are review suggestions: only
a declared mirror whose downloaded bytes match an expected SHA-256 can be
placed in the separate review copy, never automatically in the published feed.

## Source variants, updates and browser privacy

The install center lists `/feeds/variants/<slug>.json`: each preserves one
selected alternative from one shared-bundle group while leaving other groups
unchanged. It does not change any on-device bundle identifier. The master
`/apps.json` remains unchanged. A source comparison is performed in the browser
against an explicitly entered HTTPS URL (subject to CORS) or a local JSON
file; local files are not uploaded. Bundle matches can be different builds.

`/feeds/updates.ics` is an all-day release calendar; per-app and collection
calendars live under `/feeds/calendars/`, and filtered RSS lives under
`/feeds/filtered/`. Calendar timestamps use the recorded release date as a
deterministic event timestamp, not a claim about when the calendar was created.
Events with unknown dates are omitted. Calendar applications decide whether to
notify for past events. The optional browser update baseline stores only up to
100 `(slug, version)` pairs locally; it compares the current snapshot with that
baseline and does not claim to be a complete history.

The re-sign tracker stores user-entered dates locally and estimates free/paid
periods. Certificate and client behavior can differ. Notifications require
explicit browser permission and run only when the app's page is open; there is
no background push.

## Archive and issue-intake safeguards

No app is enabled for archiving by default and no durable external host is
configured. An operator who has independently established the necessary rights
may set `archive: true` for an individual catalog entry, obtain a current IPA,
and explicitly run:

```bash
python3 scripts/security/archive_release.py --slug example --file /path/to/app.ipa \
  --destination /path/outside/the/repository --confirm-rights
```

The tool requires a URL-bound matched digest, verifies the actual local bytes
while copying, enforces an operator-configurable quota and retention count, and
never publishes or creates a fallback URL. The operator is responsible for
rights, storage, backups, access controls, and any separately reviewed hosting.

`issue-intake.yml` reads new app-request/broken-link forms as untrusted data.
It checks bundle collisions and, for GitHub repositories only, optionally
queries the fixed GitHub API origin. It does not run a submitted sync, execute
issue text, edit the catalog, mark an app unmaintained, publish a binary, or
open a pull request. A maintainer must review the draft and any replacement.
