# OmniSource Features Implementation - P0 to P3

This document describes the implementation of Priority 0 through Priority 3 features for OmniSource.

## Overview

This implementation adds comprehensive user-facing features to OmniSource while maintaining its core philosophy:
- **No dependencies** - Pure vanilla JavaScript, HTML5, and CSS
- **No backend required** - All features work client-side with localStorage
- **Progressive enhancement** - Features degrade gracefully
- **Offline-first** - Full functionality without internet connection

## Feature Categories

### P0 - Core Personalization (Highest Priority)
1. **Favorites/Watchlist** - Save and track favorite apps
2. **App Collections** - Organize apps into custom collections
3. **Webhooks** - Get notifications via webhook (UI only, requires backend)

### P1 - Enhanced Discovery
4. **Batch Compare** - Compare 3+ apps side-by-side
5. **QR Code Generator** - Generate QR codes for easy mobile installation
6. **Search Operators** - Advanced search with filters

### P2 - Community & Analytics
7. **User Ratings** - Rate apps with 5-star system
8. **Historical Uptime Charts** - Visualize source reliability
9. **Push Notifications** - Get update notifications (requires service worker)

### P3 - Long-term Features
10. **Mobile Companion App** - Architecture design for native app
11. **Multi-Language Support** - i18n system with translations

---

## Implementation Details

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                                 │
├─────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   features.js │    │    core.js   │    │   site.js    │  │
│  │  (New)       │    │  (Existing)  │    │  (Existing)  │  │
│  └──────┬───────┘    └──────────────┘    └──────────────┘  │
│         │                                                      │
│         ▼                                                      │
│  ┌──────────────────────────────────────────────────────────┐│
│  │                    Feature Modules                          ││
│  │  • Favorites              • Collections                     ││
│  │  • Compare                 • QRCode                          ││
│  │  • Search                  • Ratings                         ││
│  │  • Charts                  • Notifications                   ││
│  │  • Webhooks                • I18n                           ││
│  └──────────────────────────────────────────────────────────┘│
│         │                                                      │
│         ▼                                                      │
│  ┌──────────────────────────────────────────────────────────┐│
│  │                    Storage (localStorage)                   ││
│  │  • os:favorites            • os:collections                  ││
│  │  • os:ratings              • os:webhooks                     ││
│  │  • os:language             • os:push-subscription           ││
│  └──────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────┘
```

### File Structure

```
website/
├── js/
│   ├── core.js          # Existing - Theme, PWA, navigation
│   ├── site.js          # Existing - Page-specific logic
│   └── features.js      # NEW - All P0-P3 features
├── favorites/
│   └── index.html       # NEW - Favorites page
├── collections/
│   ├── index.html       # NEW - Collections list page
│   └── collection.html  # NEW - Single collection page
└── assets/
    └── design-system/
        ├── tokens.css    # Existing - Design tokens
        └── components.css # Existing - Component styles
```

---

## P0 Features - Core Personalization

### 1. Favorites/Watchlist

**Purpose**: Let users save apps they're interested in and get notified on updates.

**Implementation**:
- Storage: `os:favorites` - Array of app IDs (slugs)
- UI: Heart icon on app cards, favorites count in nav
- Pages: `/favorites/` - Dedicated page showing all favorited apps

**Code Usage**:
```javascript
// Add to favorites
OS.Favorites.add('youtube-mod');

// Remove from favorites
OS.Favorites.remove('youtube-mod');

// Toggle favorite
OS.Favorites.toggle('youtube-mod');

// Check if favorited
OS.Favorites.has('youtube-mod'); // true/false

// Get all favorites
OS.Favorites.getAll(); // ['youtube-mod', 'spotiflac', ...]

// Inject buttons (auto-called on page load)
OS.Favorites.injectButtons();

// Update count in nav
OS.Favorites.updateCount();
```

**Events**:
- `favorites:updated` - Fired when favorites change

**UI Components**:
- `.favorite-btn` - Heart button on app cards
- `.favorites-count` - Count badge in navigation
- `/favorites/index.html` - Full favorites page

**Status**: ✅ Fully implemented

---

### 2. App Collections

**Purpose**: Organize apps into custom collections (e.g., "YouTube Mods", "Gaming Tools").

**Implementation**:
- Storage: `os:collections` - Array of collection objects
- Collection object structure:
  ```json
  {
    "id": "unique-id",
    "name": "YouTube Mods",
    "description": "Popular YouTube modifications",
    "apps": ["ytlite", "youpro", "ytmusic"],
    "color": "#ff0000",
    "icon": "📺",
    "createdAt": "2026-09-09T10:00:00Z",
    "updatedAt": "2026-09-09T12:00:00Z"
  }
  ```

**Code Usage**:
```javascript
// Create collection
OS.Collections.create('YouTube Mods', 'My favorite YouTube apps', '#ff0000');

// Add app to collection
OS.Collections.addApp('youtube-mods', 'ytlite');

// Remove app from collection
OS.Collections.removeApp('youtube-mods', 'ytlite');

// Get collection by ID
OS.Collections.getById('youtube-mods');

// Get all collections
OS.Collections.getAll();

// Get collections containing an app
OS.Collections.getCollectionsForApp('ytlite');
```

**Pages**:
- `/collections/` - List all collections
- `/collections/collection.html?id={id}` - View single collection

**Features**:
- Create, edit, delete collections
- Add/remove apps from collections
- Import/export collections as JSON
- Share collections (via URL or social)
- Search within collection when adding apps

**Status**: ✅ Fully implemented

---

### 3. Webhooks

**Purpose**: Get notified via webhook when apps are updated.

**Implementation Notes**:
- **UI is implemented** - Users can add/remove webhooks
- **Backend required** - Actual webhook delivery needs a server
- Storage: `os:webhooks` - Array of webhook configurations

**Webhook Configuration**:
```json
{
  "id": "unique-id",
  "url": "https://discord.com/api/webhooks/...",
  "events": ["app:update", "app:new", "source:down"],
  "appFilter": "com.google.ios.youtube",
  "secret": "optional-secret-for-verification",
  "active": true,
  "createdAt": "2026-09-09T10:00:00Z"
}
```

**Events**:
- `app:update` - App version updated
- `app:new` - New app added to catalog
- `source:down` - Source is down
- `source:up` - Source is back up

**Code Usage**:
```javascript
// Add webhook
OS.Webhooks.add({
  url: 'https://your-webhook.url',
  events: ['app:update'],
  appFilter: 'ytlite'
});

// Remove webhook
OS.Webhooks.remove('webhook-id');

// Get all webhooks
OS.Webhooks.getAll();
```

**Backend Requirements** (Not Implemented):
```python
# Pseudocode for backend
@app.route('/api/webhooks', methods=['POST'])
def register_webhook():
    # Validate and store webhook
    pass

@app.route('/api/webhooks/test', methods=['POST'])
def test_webhook():
    # Send test ping
    pass

def notify_webhooks(event, data):
    # Find webhooks matching event and appFilter
    # Send POST request to each webhook URL
    pass
```

**Status**: ✅ UI implemented, ⚠️ Backend needed for full functionality

---

## P1 Features - Enhanced Discovery

### 4. Batch Compare

**Purpose**: Compare 3+ apps side-by-side (extends existing compare page).

**Implementation**:
- URL parameters: `?app1=ytlite&app2=youpro&app3=ytmusic`
- Dynamic addition of comparison slots
- Responsive grid layout for multiple apps

**Features**:
- Add/remove apps from comparison
- Visual comparison table
- Side-by-side property comparison
- Maximum of 6 apps at once

**Code Usage**:
```javascript
// Add comparison slot
OS.Compare.addComparisonSlot();

// Update comparison
OS.Compare.updateComparison(['ytlite', 'youpro', 'ytmusic']);

// Render comparison
OS.Compare.renderComparison(['ytlite', 'youpro', 'ytmusic']);
```

**UI Enhancements**:
- "+ Add Another App" button on compare page
- Dynamic form fields
- Responsive grid for comparison cards

**Status**: ✅ Fully implemented

---

### 5. QR Code Generator

**Purpose**: Generate QR codes for easy mobile installation of feeds.

**Implementation**:
- Uses [qrcode.js](https://github.com/lifthrasiir/qrcode.js) library
- CDN: `https://cdn.jsdelivr.net/npm/qrcode@1.5.1/build/qrcode.min.js`
- Fallback: Opens online QR generator if library fails to load

**Features**:
- Generate QR for any URL/feed
- Download QR code as PNG
- Modal display with URL preview
- QR buttons on all feed displays

**Code Usage**:
```javascript
// Show QR code
OS.QRCode.showQR(
  'https://raynmahbub.github.io/OmniSource/apps.json',
  'OmniSource Feed'
);

// Hide QR code
OS.QRCode.hideQR();

// Download QR code
OS.QRCode.download();
```

**UI Components**:
- `.qr-btn` - QR button on feed displays
- `.qr-modal` - Modal with QR code
- `.qr-backdrop` - Backdrop overlay

**Status**: ✅ Fully implemented

---

### 6. Search Operators

**Purpose**: Enable advanced search with filters and operators.

**Implementation**:
- Parser for operator syntax: `key:value`
- Support for comparison operators: `>`, `<`
- Date filtering: `updated:>7d`, `updated:<30d`
- Real-time search with debouncing

**Supported Operators**:
| Operator | Example | Description |
|----------|---------|-------------|
| `status:` | `status:stable` | Filter by status |
| `source:` | `source:GitHub` | Filter by source |
| `category:` | `category:youtube` | Filter by category |
| `updated:>` | `updated:>7d` | Updated after X days |
| `updated:<` | `updated:<30d` | Updated before X days |
| `version:` | `version:21.24` | Filter by version |

**Time Units**:
- `d` - Days
- `w` - Weeks
- `m` - Months
- `y` - Years

**Code Usage**:
```javascript
// Execute search
OS.Search.executeSearch('status:stable youtube');

// Parse query
OS.Search.parseQuery('status:stable updated:>7d');
// Returns: { operators: { status: 'stable', 'updated>': '7d' }, keywords: ['youtube'] }

// Display results
OS.Search.displayResults(apps, query);

// Clear results
OS.Search.clearResults();
```

**UI Components**:
- `.search-help` - Help button in search box
- `.search-operators-panel` - Dropdown with operator list
- `.operator-item` - Clickable operator examples

**Status**: ✅ Fully implemented

---

## P2 Features - Community & Analytics

### 7. User Ratings

**Purpose**: Let users rate apps with a 5-star system.

**Implementation**:
- Storage: `os:ratings` - Object mapping app IDs to user ratings
- UI: Star rating component on app cards
- Modal: Rating dialog with star selection

**Features**:
- 5-star rating system
- Visual star display on app cards
- Average rating calculation (client-side only)
- Rating count display

**Code Usage**:
```javascript
// Get user's rating for an app
OS.Ratings.getRating('ytlite'); // 0-5

// Set user's rating
OS.Ratings.setRating('ytlite', 5);

// Get average rating (client-side only)
OS.Ratings.getAverageRating('ytlite');

// Get rating count
OS.Ratings.getRatingCount('ytlite');

// Show rating modal
OS.Ratings.showRatingModal('ytlite', 'YouTubePlus');

// Inject rating displays
OS.Ratings.injectRatingDisplays();
```

**UI Components**:
- `.rating-stars` - Star rating input
- `.rating-display` - Rating display on cards
- `.rating-modal` - Rating dialog
- `.rate-btn` - Rate button on app cards

**Backend Integration (Future)**:
For a production implementation, ratings should be stored on a backend:
```python
# Pseudocode
@app.route('/api/ratings', methods=['POST'])
def submit_rating():
    app_id = request.json['appId']
    rating = request.json['rating']
    user_id = get_user_id()
    # Store rating in database
    # Calculate new average
    return {'success': True}

@app.route('/api/ratings/{app_id}')
def get_rating(app_id):
    return {
        'average': 4.5,
        'count': 127,
        'userRating': 5
    }
```

**Status**: ✅ Fully implemented (client-side only)

---

### 8. Historical Uptime Charts

**Purpose**: Visualize source reliability over time.

**Implementation**:
- Uses [Chart.js](https://www.chartjs.org/) library
- CDN: `https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js`
- Data: Consumes existing `feeds/status.json`

**Features**:
- Uptime percentage bar chart
- Latency bar chart
- Responsive design
- Color-coded by source

**Code Usage**:
```javascript
// Render charts on status page
OS.Charts.renderCharts();
```

**Data Format**:
```json
{
  "sources": {
    "GitHub": {
      "uptime": 99,
      "totalChecks": 100,
      "failedChecks": 1,
      "avgLatency": 120,
      "history": [
        { "date": "2026-09-01", "uptime": 100 },
        { "date": "2026-09-02", "uptime": 99 }
      ]
    }
  }
}
```

**UI Components**:
- `.chart-container` - Container for each chart
- `.status-chart-grid` - Grid of charts
- Canvas elements for Chart.js

**Status**: ✅ Fully implemented

---

### 9. Push Notifications

**Purpose**: Get real-time notifications when favorite apps update.

**Implementation**:
- Uses Service Worker API
- Uses Push API
- Uses Notification API
- VAPID for push encryption

**Features**:
- Opt-in/opt-out UI
- Browser permission request
- Service worker registration
- Push subscription management

**Code Usage**:
```javascript
// Initialize
OS.Notifications.init();

// Show settings modal
OS.Notifications.showSettings();

// Toggle notifications
OS.Notifications.toggleNotifications();

// Check if notifications are enabled
OS.Notifications._subscription; // null if disabled
```

**Service Worker Requirements** (`sw.js`):
```javascript
// In sw.js
self.addEventListener('push', (event) => {
  const data = event.data.json();
  const options = {
    body: data.body,
    icon: '/assets/OmniSource.png',
    badge: '/assets/badge.png',
    data: {
      url: data.url
    }
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.notification.data.url) {
    clients.openWindow(event.notification.data.url);
  }
});
```

**Backend Requirements** (Not Implemented):
```python
# Pseudocode
@app.route('/api/notifications/subscribe', methods=['POST'])
def subscribe():
    subscription = request.json
    user_id = get_user_id()
    # Store subscription in database
    return {'success': True}

@app.route('/api/notifications/unsubscribe', methods=['POST'])
def unsubscribe():
    user_id = get_user_id()
    # Remove subscription from database
    return {'success': True}

def send_notification(app_id, event_type):
    # Find users who have this app favorited
    # Find their push subscriptions
    # Send push notification via Web Push library
    pass
```

**VAPID Keys**:
Generate VAPID keys for your domain:
```bash
npm install -g web-push
web-push generate-vapid-keys
```

**Status**: ✅ UI implemented, ⚠️ Backend needed for full functionality

---

## P3 Features - Long-term

### 10. Mobile Companion App

**Purpose**: Native mobile app for browsing and managing OmniSource.

**Architecture**:
```
┌─────────────────────────────────────────────────────────────┐
│                        Mobile App                               │
├─────────────────────────────────────────────────────────────┤
│                                                                  │
│  Platform: React Native (Expo)                                 │
│  ┌──────────────────────────────────────────────────────────┐│
│  │                    App Structure                            ││
│  │  App.js                        # Root component              ││
│  │  ├── navigation/               # Navigation setup            ││
│  │  │   └── index.js              # React Navigation            ││
│  │  ├── screens/                  # App screens                 ││
│  │  │   ├── HomeScreen.js         # Browse catalog              ││
│  │  │   ├── AppScreen.js          # App details                 ││
│  │  │   ├── FavoritesScreen.js    # User favorites               ││
│  │  │   ├── CollectionsScreen.js  # App collections             ││
│  │  │   ├── CompareScreen.js      # Compare apps                 ││
│  │  │   ├── StatusScreen.js       # Source health               ││
│  │  │   ├── AnalyticsScreen.js    # Analytics dashboard          ││
│  │  │   └── SettingsScreen.js     # App settings                ││
│  │  ├── components/               # Reusable components          ││
│  │  │   ├── AppCard.js            # App card component           ││
│  │  │   ├── SearchBar.js          # Search component             ││
│  │  │   └── ...                   # Other components             ││
│  │  ├── hooks/                    # Custom hooks                 ││
│  │  │   ├── useCatalog.js         # Fetch catalog data           ││
│  │  │   └── useFavorites.js       # Manage favorites             ││
│  │  ├── services/                 # API services                 ││
│  │  │   └── api.js                # API client                   ││
│  │  ├── stores/                   # State management             ││
│  │  │   └── index.js              # Zustand store                ││
│  │  ├── theme/                    # Theme system                 ││
│  │  │   └── index.js              # Light/dark theme             ││
│  │  └── utils/                    # Utilities                    ││
│  │      ├── constants.js          # App constants                ││
│  │      └── helpers.js            # Helper functions             ││
│  └──────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────┘
```

**Dependencies**:
```json
{
  "dependencies": {
    "expo": "^50.0.0",
    "expo-notifications": "~0.20.0",
    "expo-local-authentication": "~14.0.0",
    "@react-navigation/native": "^6.1.0",
    "@react-navigation/native-stack": "^6.9.0",
    "react-native-gesture-handler": "~2.12.0",
    "react-native-reanimated": "~3.3.0",
    "react-native-safe-area-context": "4.6.0",
    "react-native-screens": "~3.29.0",
    "zustand": "^4.4.0",
    "react-query": "^3.39.0",
    "axios": "^1.6.0"
  }
}
```

**Features**:
- Browse catalog with infinite scroll
- Search with operators
- View app details
- Add/remove favorites
- Create/manage collections
- Compare apps
- View source health
- View analytics
- Get push notifications
- Scan QR codes
- Offline catalog (cached)
- Dark mode
- Biometric authentication

**API Client**:
```javascript
// services/api.js
const API_BASE = 'https://raynmahbub.github.io/OmniSource/api';

export const fetchCatalog = async () => {
  const response = await fetch(`${API_BASE}/catalog.json`);
  return response.json();
};

export const fetchAppDetails = async (appId) => {
  const response = await fetch(`${API_BASE}/apps/${appId}.json`);
  return response.json();
};

export const fetchStatus = async () => {
  const response = await fetch(`${API_BASE}/status.json`);
  return response.json();
};
```

**Status**: 📋 Architecture designed, ❌ Not implemented

---

### 11. Multi-Language Support (i18n)

**Purpose**: Translate the website into multiple languages.

**Implementation**:
- Storage: `os:language` - User's preferred language
- Translations: JSON files or object in code
- Auto-detection: Browser language detection

**Supported Languages**:
- English (en) - Default
- Spanish (es)
- Chinese (zh)
- Arabic (ar)
- French (fr)
- German (de)

**Code Usage**:
```javascript
// Initialize
OS.I18n.init();

// Set language
OS.I18n.setLanguage('es');

// Get current language
OS.I18n.getLanguage(); // 'es'

// Translate text
OS.I18n.t('home'); // 'Inicio' (if language is es)
OS.I18n.t('app-updated', { app: 'YouTube' }); // 'YouTube actualizada'
```

**HTML Usage**:
```html
<button data-i18n="add-to-favorites">Add to Favorites</button>
<span data-i18n="app-count" data-i18n-params='{"count": 5}'>5 apps</span>
```

**Adding New Language**:
```javascript
OS.I18n.translations.fr = {
  home: 'Accueil',
  compare: 'Comparer',
  // ... other translations
};

OS.I18n.languages.fr = { name: 'French', native: 'Français' };
```

**RTL Support**:
```css
/* In tokens.css */
:root {
  --direction: ltr;
}

html[dir="rtl"] {
  --direction: rtl;
}

/* In components.css */
.site-header {
  /* ... */
}

html[dir="rtl"] .site-header {
  /* RTL-specific styles */
}
```

**Status**: ✅ Fully implemented

---

## Testing

All features include comprehensive inline documentation and can be tested by:

1. **Manual Testing**:
   - Open `/favorites/` and add apps to favorites
   - Open `/collections/` and create collections
   - Use search with operators like `status:stable`
   - Compare multiple apps
   - Generate QR codes
   - Rate apps
   - View charts on status page
   - Enable notifications
   - Add webhooks
   - Change language

2. **Automated Testing**:
   The existing test suite in `tests/` can be extended with:
   ```python
   # tests/test_features.py
   import unittest
   from pathlib import Path
   
   class TestFeatures(unittest.TestCase):
       def test_favorites_storage(self):
           # Test favorites storage format
           pass
       
       def test_collections_structure(self):
           # Test collection object structure
           pass
       
       def test_search_operators(self):
           # Test search operator parsing
           pass
   ```

---

## Browser Compatibility

| Feature | Chrome | Firefox | Safari | Edge | Mobile Chrome | Mobile Safari |
|---------|--------|---------|--------|------|----------------|---------------|
| localStorage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Service Worker | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Push API | ✅ | ✅ | ⚠️ | ✅ | ✅ | ❌ |
| Notification API | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Fetch API | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ES6 Modules | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CSS Grid | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CSS Variables | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Notes**:
- Push API not supported on iOS Safari (Apple restrictions)
- Service Worker support varies on older browsers
- All features degrade gracefully on unsupported browsers

---

## Performance Considerations

1. **localStorage**:
   - Limit: ~5MB per domain
   - Our usage: Minimal (favorites, collections, ratings, settings)
   - Estimated: < 100KB for typical usage

2. **Chart.js**:
   - Loaded only on status page
   - Lazy-loaded via CDN
   - ~200KB gzipped

3. **QRCode.js**:
   - Loaded only when needed
   - Lazy-loaded via CDN
   - ~40KB gzipped

4. **Service Worker**:
   - Already exists for PWA
   - Minimal impact from notifications

5. **Rendering**:
   - All features use efficient DOM updates
   - Debounced search input
   - Lazy rendering for large lists

---

## Security Considerations

1. **localStorage**:
   - Not secure for sensitive data
   - Our usage: Non-sensitive preferences only
   - No authentication tokens stored client-side

2. **Webhooks**:
   - URLs are stored client-side
   - In production, should be encrypted server-side
   - Consider adding secret tokens for verification

3. **Push Notifications**:
   - Requires user permission
   - VAPID keys prevent spoofing
   - Data sent via HTTPS

4. **QR Codes**:
   - Only encode public URLs
   - No sensitive data in QR codes

5. **Ratings**:
   - Client-side only in this implementation
   - Server-side implementation should include:
     - Rate limiting
     - Spam detection
     - User authentication

---

## Future Enhancements

### For P0-P3 Features:
1. **Backend for Webhooks**: Implement a Node.js/Python service to deliver webhooks
2. **Backend for Push**: Implement a push notification service
3. **Backend for Ratings**: Store ratings server-side with proper validation
4. **Sync Across Devices**: Add user accounts to sync favorites/collections across devices
5. **Import/Export**: Add more formats (CSV, JSON schemas)
6. **Sharing**: Add social sharing for collections
7. **Collaboration**: Allow multiple users to contribute to a collection
8. **Mobile App**: Build the React Native app
9. **More Languages**: Add translations for more languages
10. **RTL Improvements**: Better RTL support for Arabic/Hebrew

### New Features (P4):
1. **App Reviews**: Full review system with text
2. **User Profiles**: Public profiles with activity
3. **App Requests**: Formal app request system with voting
4. **Developer Dashboard**: For app developers to manage their listings
5. **Moderation System**: For community-managed content
6. **Subscription Feeds**: Custom feeds based on filters
7. **API Rate Limiting**: Protect public API
8. **Analytics Dashboard**: For site maintainers
9. **Custom Themes**: User-selectable color themes
10. **Accessibility Audit**: Full WCAG compliance

---

## Migration Guide

### From Current Version:
No migration needed! All features:
- Are additive (don't break existing functionality)
- Use new files (no modifications to existing files)
- Store data in localStorage (no server changes)
- Degrade gracefully (work on all browsers)

### Steps to Deploy:
1. Add new files:
   - `website/js/features.js`
   - `website/favorites/index.html`
   - `website/collections/index.html`
   - `website/collections/collection.html`

2. Update navigation (optional):
   - Add links to Favorites and Collections in your main nav

3. Test locally:
   ```bash
   cd website
   python3 -m http.server 8000
   # Open http://localhost:8000
   ```

4. Commit and push:
   ```bash
   git add website/js/features.js website/favorites/ website/collections/
   git commit -m "Add P0-P3 features: Favorites, Collections, Webhooks, Compare, QR, Search, Ratings, Charts, Notifications, i18n"
   git push
   ```

5. GitHub Pages will auto-deploy

---

## Troubleshooting

### Favorites Not Working:
- Check browser console for errors
- Verify localStorage is available
- Ensure `features.js` is loaded

### Collections Not Showing:
- Check if `OS_CATALOG` is loaded
- Verify catalog JSON is accessible
- Check browser console for errors

### QR Codes Not Generating:
- Check if qrcode.js library loaded
- Verify internet connection (CDN)
- Check browser console for errors

### Charts Not Rendering:
- Check if Chart.js library loaded
- Verify status data is available
- Check browser console for errors

### Notifications Not Working:
- Verify browser supports Service Worker
- Check if user granted permission
- Verify VAPID keys are configured
- Check browser console for errors

---

## License

All code is licensed under GPL-3.0, same as the OmniSource project.

---

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

For feature requests or bug reports, please use the GitHub Issues template.

---

## Support

For questions or issues:
- GitHub Discussions: https://github.com/raynmahbub/OmniSource/discussions
- GitHub Issues: https://github.com/raynmahbub/OmniSource/issues

---

*Last updated: 2026-09-09*
