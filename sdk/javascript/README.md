# OmniSource JavaScript SDK

Browser- and Node-compatible client for the public OmniSource API.

```js
import OmniSource from '@omnisource/sdk';

const client = new OmniSource({ baseURL: 'https://raynmahbub.github.io/OmniSource' });

// Search the catalog.
const results = await client.search('spotify');

// Get an app's metadata, latest version and source feed URL.
const app = await client.getApp('spotiflac');

// List trending apps.
const trending = await client.getTrending();

// Source health and reputation.
const health = await client.getHealth();
const reputation = await client.getReputation();
```

The SDK is fully typed, has zero runtime dependencies, and works in the
browser via the `dist/omnisource.browser.js` IIFE bundle or in Node via
`dist/omnisource.node.js` (CommonJS).

## API surface

| Method | Returns | Description |
| --- | --- | --- |
| `client.search(query, { limit, verifiedOnly })` | `App[]` | Fuzzy search by name, developer, bundle ID, tags, description. |
| `client.getApp(slug)` | `App \| null` | One app with versions, mirror URLs, verification status. |
| `client.listApps({ category, status })` | `App[]` | Filtered catalog listing. |
| `client.getTrending()` | `{ trending, rising, recentlyUpdated, all }` | Phase 1 trending board. |
| `client.getRelated(slug)` | `App[]` | Phase 2 relationship graph. |
| `client.getReputation()` | `Source[]` | Phase 6 source reputation. |
| `client.getHealth()` | `Health[]` | Phase 7 download intelligence. |
| `client.getAnalytics()` | `Analytics` | Pipeline analytics snapshot. |
| `client.getCommunity()` | `{ popular, recentlyAdded, requested, rising }` | Phase 13 community lists. |
| `client.getInstall(slug?)` | `InstallCard[]` | Phase 9 install cards for one app or the master feed. |
| `client.getCompare(left, right)` | `Comparison` | Phase 5 side-by-side comparison. |
| `client.getSearchIndex()` | `{ fuse, documents }` | Phase 4 search index (consumable by any Fuse.js compatible engine). |

## Error handling

The SDK throws `OmniSourceError` for any non-2xx response. The error
exposes `status`, `url` and a `body` snapshot so callers can render their
own retry messaging.

## License

MIT
