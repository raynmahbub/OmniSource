# Security Policy

## Scope

OmniSource distributes metadata, not binaries. This repository contains no application code — the
IPAs it points at are built and hosted by third parties. Security work here covers the automation,
the feeds, and the supply chain between an upstream release and your device.

## Reporting a vulnerability

Use [private vulnerability reporting](https://github.com/raynmahbub/OmniSource/security/advisories/new).
Do not open a public issue for:

- a feed entry pointing at a malicious or hijacked download,
- a workflow that leaks a token or allows command injection,
- anything that lets a third party publish into this repository.

Expect an initial response within 72 hours.

## What we guarantee

- **No credentials leave the API layer.** `GH_TOKEN` is attached only to `api.github.com` requests
  inside the HTTP client (`omnisource.http`). Download probes send no `Authorization` header, ever.
- **Least privilege.** Workflows declare `permissions: {}` at the top level and opt in per job.
  `validate.yml` runs read-only with `persist-credentials: false`, so pull requests from forks
  cannot touch repository state.
- **No third-party code in the write path.** `sync.yml` runs only first-party, standard-library
  Python plus GitHub's own actions. There is no `pip install` step in the pipeline that holds a
  write-scoped token.
- **Reproducibility.** CI rebuilds every feed from `catalog.json` and fails if the committed output
  differs, so a hand-edited or tampered feed cannot land silently.
- **Link verification.** Every download URL is probed each run and flagged in `feeds/health.json`.

## What we cannot guarantee

- **Upstream integrity.** If an upstream maintainer's account is compromised and they publish a
  malicious release asset, OmniSource will mirror the link. Check each entry's `omnisource.verification`
  metadata block: `github-release` means the file comes straight from the upstream project;
  `self-built` means an OmniSource workflow compiled it and published a SHA-256;
  `manual-mirror` is the weakest and is used only as a fallback.
- **Signing.** Nothing here is pre-signed. You sign with your own certificate or Apple ID, and you
  are trusting the IPA at that moment.

## Hardening backlog

Tracked improvements, roughly in priority order:

1. Publish and verify SHA-256 checksums for every tracked release, not just self-built ones.
2. Pin third-party actions to commit SHAs (currently pinned to major tags).
3. Retire the remaining URL-shortener download in favour of a first-party GitHub release.
4. Add Sigstore attestation to `build-uyouenhanced.yml` output.

## Supported versions

Only the current state of `main` is supported. Feeds are regenerated every six hours; stale forks
receive no security updates.
