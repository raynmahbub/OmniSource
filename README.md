<div align="center">

<a href="https://raynmahbub.github.io/OmniSource/">
  <img src="assets/brand/hero.svg" width="100%" alt="OmniSource — one verified, automatically maintained source for every iOS sideloading client. Maintained by raynmahbub.">
</a>

<br>
<br>

[![Website](https://img.shields.io/website?url=https%3A%2F%2Fraynmahbub.github.io%2FOmniSource%2F&label=website&style=flat-square&labelColor=0d0926&color=8b5cf6)](https://raynmahbub.github.io/OmniSource/)
[![Apps](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fraynmahbub%2FOmniSource%2Fmain%2Ffeeds%2Fbadge-apps.json&style=flat-square&labelColor=0d0926)](https://raynmahbub.github.io/OmniSource/#catalog)
[![Download health](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fraynmahbub%2FOmniSource%2Fmain%2Ffeeds%2Fbadge-health.json&style=flat-square&labelColor=0d0926)](https://raynmahbub.github.io/OmniSource/status/)
[![Verified](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fraynmahbub%2FOmniSource%2Fmain%2Ffeeds%2Fbadge-verified.json&style=flat-square&labelColor=0d0926)](https://raynmahbub.github.io/OmniSource/status/)
[![Validate](https://img.shields.io/github/actions/workflow/status/raynmahbub/OmniSource/validate.yml?branch=main&label=validate&style=flat-square&labelColor=0d0926)](https://github.com/raynmahbub/OmniSource/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/raynmahbub/OmniSource?style=flat-square&labelColor=0d0926&color=5b3df5)](LICENSE)

<br>

<a href="https://raynmahbub.github.io/OmniSource/install/"><img src="assets/brand/btn-add-source.svg" alt="Add the OmniSource source"></a>

<br>

<a href="https://raynmahbub.github.io/OmniSource/install/?add=altstore"><img src="assets/brand/btn-add-altstore.svg" alt="Add to AltStore" height="46"></a>
<a href="https://raynmahbub.github.io/OmniSource/install/?add=sidestore"><img src="assets/brand/btn-add-sidestore.svg" alt="Add to SideStore" height="46"></a>
<a href="https://raynmahbub.github.io/OmniSource/install/?add=feather"><img src="assets/brand/btn-add-feather.svg" alt="Add to Feather" height="46"></a>
<a href="https://raynmahbub.github.io/OmniSource/install/?add=esign"><img src="assets/brand/btn-add-esign.svg" alt="Add to ESign" height="46"></a>
<a href="https://raynmahbub.github.io/OmniSource/install/?add=livecontainer"><img src="assets/brand/btn-add-livecontainer.svg" alt="Add to LiveContainer" height="46"></a>

<br>

**One installable source for AltStore, SideStore, Feather, ESign and LiveContainer —**
**every app resolved from its developer's own upstream, verified on every sync.**

<br>

<!-- omnisource:stats:start -->

**131** apps · **114** upstream sources · **123** verified · **1** community verified · **124/131** downloads online · last sync **2026-10-05**.

<!-- omnisource:stats:end -->

</div>

<img src="assets/brand/divider.svg" width="100%" alt="">

## The source

```text
https://raynmahbub.github.io/OmniSource/apps.json
```

Paste that into your client's **Add Source** screen. On a phone, the buttons
above open the [install center](https://raynmahbub.github.io/OmniSource/install/) —
one tap, and a QR code when the client is not installed yet.

<br>

## Why OmniSource

<table>
  <tr>
    <td width="33%" valign="top">
      <img src="assets/brand/feature-upstream.svg" width="44" height="44" alt=""><br>
      <b>Upstream only</b><br>
      <sub>Every entry resolves from the developer's own GitHub releases or official feed. Nothing is re-hosted, nothing is repackaged.</sub>
    </td>
    <td width="33%" valign="top">
      <img src="assets/brand/feature-verified.svg" width="44" height="44" alt=""><br>
      <b>Verified on every sync</b><br>
      <sub>Downloads are probed, digests checked where the publisher ships one, and the result is published as a per-app provenance page.</sub>
    </td>
    <td width="33%" valign="top">
      <img src="assets/brand/feature-clients.svg" width="44" height="44" alt=""><br>
      <b>One feed, every client</b><br>
      <sub>A deterministic AltStore v2 feed plus tailored feeds for Feather, ESign, Ksign and LiveContainer — the same catalog everywhere.</sub>
    </td>
  </tr>
  <tr>
    <td width="33%" valign="top">
      <img src="assets/brand/feature-automation.svg" width="44" height="44" alt=""><br>
      <b>Hands-off by design</b><br>
      <sub>Seventeen GitHub Actions workflows sync, validate, monitor, scan and publish. One hand-maintained <code>catalog.json</code>; everything else is generated.</sub>
    </td>
    <td width="33%" valign="top">
      <img src="assets/brand/feature-api.svg" width="44" height="44" alt=""><br>
      <b>A real API</b><br>
      <sub>Static JSON endpoints (v2 and v3) with gzip twins, a search index, release history, reputation scores and SDKs for JavaScript and Python.</sub>
    </td>
    <td width="33%" valign="top">
      <img src="assets/brand/feature-factory.svg" width="44" height="44" alt=""><br>
      <b>The Tweak Factory</b><br>
      <sub>Bring a decrypted base IPA and official tweaks; the pipeline injects them with Cyan and publishes a provenance-tagged release.</sub>
    </td>
  </tr>
</table>

No accounts. No ads. No tracking. No re-hosted binaries.

<br>

## How it works

```mermaid
flowchart LR
    A[("catalog.json<br/><sub>hand-maintained</sub>")] --> B["Sync<br/><sub>GitHub releases · official feeds</sub>"]
    B --> C["Validate<br/><sub>schema · digests · link probes</sub>"]
    C --> D["Build<br/><sub>AltStore v2 feed · client feeds · RSS</sub>"]
    D --> E["Publish<br/><sub>apps.json · api/ · app pages</sub>"]
    E --> F(("GitHub Pages<br/><sub>raynmahbub.github.io/OmniSource</sub>"))
    C -. quarantine .-> Q["data/quarantine"]
    D --> G["Derive<br/><sub>reputation · release ledger · API v3</sub>"]
    G --> E
    style A fill:#1b1140,stroke:#8b5cf6,color:#f2f3fa
    style F fill:#5b3df5,stroke:#c084fc,color:#ffffff
    style Q fill:#2a1160,stroke:#c084fc,color:#f2f3fa,stroke-dasharray: 4 3
```

The full picture — stages, workflows and the data they own — lives in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the workflow map in
[`.github/workflows/README.md`](.github/workflows/README.md).

<br>

## The website is the documentation

Catalog, app pages with screenshots and release history, per-app hashes and
provenance, source reputation, status and the machine API all live at
**[raynmahbub.github.io/OmniSource](https://raynmahbub.github.io/OmniSource/)**.

<div align="center">

<a href="https://raynmahbub.github.io/OmniSource/#catalog"><img src="assets/brand/btn-website.svg" alt="Browse the catalog" height="44"></a>
<a href="https://raynmahbub.github.io/OmniSource/install/"><img src="assets/brand/btn-install.svg" alt="Install center" height="44"></a>
<a href="https://raynmahbub.github.io/OmniSource/docs/"><img src="assets/brand/btn-docs.svg" alt="Documentation" height="44"></a>
<a href="https://raynmahbub.github.io/OmniSource/api/index.json"><img src="assets/brand/btn-api.svg" alt="API" height="44"></a>

</div>

| Surface | URL |
| :-- | :-- |
| App pages | [`/apps/<slug>/`](https://raynmahbub.github.io/OmniSource/apps/delta/) — screenshots, release history, hashes, provenance |
| Install center | [`/install/`](https://raynmahbub.github.io/OmniSource/install/) — one-tap client links and QR codes |
| Source explorer | [`/sources/`](https://raynmahbub.github.io/OmniSource/sources/) — every upstream with its reputation score |
| Status | [`/status/`](https://raynmahbub.github.io/OmniSource/status/) — download health, last sync, dead links |
| Collections | [`/collections/`](https://raynmahbub.github.io/OmniSource/collections/) — curated shelves (emulators, YouTube, tweaks…) |
| API | [`/api/index.json`](https://raynmahbub.github.io/OmniSource/api/index.json) · [`docs/API.md`](docs/API.md) · [`docs/API-V3.md`](docs/API-V3.md) |
| RSS | [`/feeds/feed.xml`](https://raynmahbub.github.io/OmniSource/feeds/feed.xml) — combined release feed, per-app feeds at `/feeds/<slug>.xml` |

<br>

## For maintainers

```bash
export PYTHONPATH=src                    # stdlib-only, Python 3.11+
python3 -m unittest discover -s tests    # the test suite
python3 scripts/validate.py              # catalog + feed validation
make check                               # the whole gate: lint, tests, reproducibility, smoke
```

`catalog.json` is the only app file you hand-edit — then `make build` (feeds)
and `make derived` (client feeds, API v3, reputation) regenerate the rest.
`scripts/omnisource.py --no-sync --no-health` rebuilds everything offline from
the committed state, and `make check` fails if a generated file drifts.

<details>
<summary><b>Repository map</b></summary>
<br>

| Path | What lives there |
| :-- | :-- |
| `catalog.json` | The hand-maintained catalog — the single source of truth |
| `src/omnisource/` | The pipeline: providers, feeds, validation, site and API builders |
| `scripts/` | CLI entry points, discovery, monitoring, security, reputation, the Tweak Factory |
| `feeds/` | Generated feeds — `apps.json`, per-app JSON/XML, badges, client feeds |
| `api/` | The published static API (v2 + v3) with gzip twins |
| `apps/` · `sources/` · `collections/` | Generated static pages for GitHub Pages |
| `assets/` | Icons, screenshots, brand assets and the Liquid Glass design system |
| `web/` | The Next.js edition of the website (built on CI, promoted manually) |
| `sdk/` | JavaScript and Python clients for the API |
| `tests/` | 600+ unit tests covering the pipeline, feeds, pages and workflows |
| `docs/` | Architecture, operations, API, deployment and the Tweak Factory guide |

</details>

<details>
<summary><b>Design system</b></summary>
<br>

The website ships a zero-dependency **Liquid Glass** design system
(`assets/design-system/`): translucent materials, aurora diffusion, spring
motion and a light/dark/auto theme model. The v3 identity pairs two
materials, exactly like the mark — **chrome silver** for rings, the first
headline line and dividers, and a monochrome **violet aurora**
(`#5b3df5 → #8b5cf6 → #c084fc`) for gradients and glows — set in Inter with
JetBrains Mono for feed URLs, hashes and identifiers.

</details>

Rules in [CONTRIBUTING.md](CONTRIBUTING.md), threat model in
[SECURITY.md](SECURITY.md), the Tweak Factory in
[`docs/TWEAK-FACTORY.md`](docs/TWEAK-FACTORY.md).

<img src="assets/brand/divider.svg" width="100%" alt="">

<div align="center">

Maintained by **[@raynmahbub](https://github.com/raynmahbub)** · GPL-3.0

<sub>App names, icons and trademarks belong to their owners. OmniSource aggregates metadata and links to public publishers — it does not re-host upstream binaries.</sub>

</div>
