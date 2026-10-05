# OmniSource Python SDK

```python
from omnisource_sdk import OmniSource

client = OmniSource(base_url="https://raynmahbub.github.io/OmniSource")

# Search the catalog.
results = client.search("spotify")

# Get one app.
app = client.get_app("spotiflac")

# Trending, related, reputation, install cards, comparisons.
trending = client.get_trending()
related = client.get_related("uyouenhanced")
reputation = client.get_reputation()
health = client.get_health()
```

The SDK is a single-file, dependency-free client that mirrors the
JavaScript SDK. It works on Python 3.8+.

## API

| Method | Returns | Description |
| --- | --- | --- |
| `client.search(query, limit=12, verified_only=False)` | `list[dict]` | Fuzzy search. |
| `client.get_app(slug)` | `dict \| None` | One app with versions, install cards. |
| `client.list_apps(category=None, status=None)` | `list[dict]` | Catalog listing. |
| `client.get_trending()` | `dict` | `{trending, rising, recentlyUpdated, all}` |
| `client.get_related(slug)` | `list[dict]` | Apps related to slug. |
| `client.get_reputation()` | `dict` | `{sources, levels, windowDays}` |
| `client.get_health()` | `dict` | Download intelligence. |
| `client.get_analytics()` | `dict` | Pipeline analytics. |
| `client.get_community()` | `dict` | Community lists. |
| `client.get_install(slug=None)` | `list[dict] \| dict` | Install cards. |
| `client.get_compare(left, right)` | `dict \| None` | Side-by-side comparison. |
| `client.get_search_index()` | `dict` | Precomputed search index. |

## Errors

`OmniSourceError` is raised for transport errors. The error has
`.status`, `.url`, and `.body` attributes.

## License

MIT
