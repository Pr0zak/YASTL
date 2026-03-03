# YASTL Roadmap

## Completed

### Print Bed Overlay in 3D Viewer
Configurable build plate rendered as a transparent wireframe in the 3D viewer.
- Settings: bed shape (rectangular/circular), dimensions, printer presets (Ender 3, Prusa MK3S+, Bambu Lab P1S/A1, Voron 2.4)
- Three.js: wireframe box/cylinder at correct scale relative to model
- Visual "fits" / "too large" indicator based on model bounding box vs bed size
- Overlay toggle button in viewer toolbar

### Stats & Status Dashboard
Unified library statistics and system health panel.
- Model counts, total size, format breakdown, library breakdown
- Tag cloud, coverage bars (thumbnails, source URLs, zips, duplicates)
- Largest models, recently added (7d/30d)
- System health indicators (scanner, watcher, database, thumbnails)

### Smart Collections
Rule-based collections that auto-populate via live filter evaluation.
- Extended `collections` table with `is_smart` and `rules` JSON columns
- Rules: format, tags (AND), categories (OR), library, favorites, duplicates, date range
- Dynamic model count computed on list; clicking applies rules as live filters
- Sidebar section with zap icon, create/edit rules modal
- Backend count query builder mirrors model listing filter logic

### PWA / Mobile Install
YASTL is installable as a Progressive Web App on phone/tablet.
- `manifest.json` with app name, theme color, 192x192 + 512x512 PNG icons (any + maskable)
- Minimal service worker (`sw.js`) with install/activate/fetch handlers (no offline caching)
- iOS meta tags (`apple-mobile-web-app-capable`, touch icon)
- Backend serves manifest at `/manifest.json` and SW at `/sw.js` with proper MIME types and no-cache headers
- LAN installs (no HTTPS): use Chrome flag `chrome://flags/#unsafely-treat-insecure-origin-as-secure`

---

## High Priority

### 1. Multi-Part Model Grouping
Link related STLs into a "project" so `base.stl + lid.stl + clip.stl` stay together.
- New `model_groups` table (id, name, created_at)
- New `model_group_members` junction table (group_id, model_id, sort_order)
- API: CRUD for groups, add/remove members
- UI: Group indicator on cards, grouped view in grid, manage group in detail panel
- Drag-to-group or multi-select-to-group workflow

## Medium Priority

### 2. Mobile Layout Polish
Improve responsive CSS for phone/tablet use at the printer.
- Larger touch targets, swipe gestures, mobile-optimized detail panel
- Test on iOS Safari and Android Chrome

## Nice to Have

### 3. Bulk Collection Import
Import entire Thingiverse/Printables collections by URL.
- Detect collection URLs in import modal
- Scrape collection page for individual model URLs
- Queue all for import with shared metadata
