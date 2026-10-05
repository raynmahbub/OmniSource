# OmniSource API v3

API v3 is the versioned, paginated, cache-friendly surface for source and
release consumers. It is static-hostable and also implemented by the Next.js
route handler. It exposes deterministic catalog/search results and operational
intelligence; it does not expose user activity or personalized recommendations.

## Endpoints

| Endpoint | Description |
|---|---|
| `/api/v3` or `/api/v3/index.json` | version and endpoint registry |
| `/api/v3/apps` | paginated app catalog |
| `/api/v3/apps/{id}` | normalized app plus versions |
| `/api/v3/sources` | global source registry |
| `/api/v3/sources/{id}` | source detail, history, health and score |
| `/api/v3/search?q=...` | weighted search over declared metadata |
| `/api/v3/releases` | release timeline sorted by release date |
| `/api/v3/status` | monitor and feed health snapshot |
| `/api/v3/security` | digest, provenance and integrity posture |
| `/api/v3/analytics` | catalog and pipeline rollups |

`/api/v3/trending` is retained as a deprecated legacy snapshot only so old
clients do not fail during migration. It is deliberately absent from the web
navigation and from new endpoint documentation.

## Query semantics

```text
GET /api/v3/apps?page=2&per_page=20&sort=-versionDate&category=Games&q=youtube
GET /api/v3/apps?developer=acme&sort=name
GET /api/v3/sources?status=verified&sort=-score
GET /api/v3/search?q=trollstore&per_page=10
```

- `page` is 1-based; `per_page` is clamped to 1–200 (default 50).
- `sort=field` and `sort=-field` support name, version, versionDate,
  category, developerName, size, and source score.
- app filters are exact category/status values and substring developer/query
  values; source filters include status.
- search uses name, bundle ID, developer, category, tags, description, and
  source metadata only. It does not use clicks, downloads, accounts, or
  behavioral profiles.
- response data is wrapped in `{apiVersion, schemaVersion, feedVersion,
  pagination?, data}`.

## Caching

- Every dynamic response includes a weak SHA-256 ETag.
- Send `If-None-Match` to receive `304 Not Modified` when unchanged.
- Cache policy is `public, s-maxage=300, stale-while-revalidate=3600`.
- Static v3 documents include per-document SHA-256 checksums in `index.json`.
- `feedVersion` changes when the generated source documents change.

## Examples

```bash
curl 'https://raynmahbub.github.io/OmniSource/api/v3/index.json'
curl 'https://raynmahbub.github.io/OmniSource/api/v3/apps.json'
curl 'https://HOST/api/v3/search?q=music&per_page=5'
```

## Relationship to v2

`api/v2/` remains unchanged for delta-sync consumers. Both versions are
projections of the same validated catalog and never read quarantine records.
New integrations should use v3 and select `/releases`, `/status`,
`/security`, or `/analytics` for operational views.
