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

---

## High Priority

### 1. Multi-Part Model Grouping
Link related STLs into a "project" so `base.stl + lid.stl + clip.stl` stay together.
- New `model_groups` table (id, name, created_at)
- New `model_group_members` junction table (group_id, model_id, sort_order)
- API: CRUD for groups, add/remove members
- UI: Group indicator on cards, grouped view in grid, manage group in detail panel
- Drag-to-group or multi-select-to-group workflow

### 2. Smart Collections
Collections that auto-populate based on saved filter rules.
- New `smart_collections` table (id, name, color, rules JSON)
- Rules: format, tags, categories, size range, date range, favorites, duplicates
- API: CRUD for smart collections, query endpoint that evaluates rules
- UI: Smart collection icon in sidebar, edit rules modal
- Essentially a saved search that appears as a collection

## Medium Priority

### 3. PWA / Mobile Layout
Make YASTL installable on phone/tablet for quick reference at the printer.
- Add manifest.json with app icon and theme color
- Add service worker for offline shell caching
- Polish responsive CSS: larger touch targets, swipe gestures, mobile-optimized detail panel
- Test on iOS Safari and Android Chrome

## Nice to Have

### 4. Bulk Collection Import
Import entire Thingiverse/Printables collections by URL.
- Detect collection URLs in import modal
- Scrape collection page for individual model URLs
- Queue all for import with shared metadata
