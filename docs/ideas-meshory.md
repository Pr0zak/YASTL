# YASTL — Ideas from Meshory (backlog + implementation plans)

> Research date: 2026-07-24. Source: [meshory.com](https://www.meshory.com/) + [pricing](https://www.meshory.com/pricing).
> Meshory is a **local-first desktop** (macOS/Win/Linux) STL/3MF organizer — "point at folders, get a visual searchable library, nothing leaves your machine." One-time license ($29–59). Deliberately minimal.

## Strategic read

YASTL is already **more capable** than Meshory on nearly every axis (9 formats vs 2, richer Three.js viewer, URL import, smart collections, provenance, stats, backups, web/PWA). Meshory's value to us is **(a) ruthless simplicity** and **(b) ~4 specific features worth borrowing**. This doc turns those into grounded implementation plans + a task list.

**Where YASTL already wins (dismiss):** duplicate + near-dup detection, worker-pool thumbnails, collections/tags, 3D viewer, local processing, 9 formats, URL import from maker sites, smart collections/pinning/covers/saved searches, namespaced tags + category tree + tag co-occurrence, model docs viewer, license/source provenance, variant pairing, stats/health, backup export, scheduled scans + webhooks, zip support, web/PWA.

## How to read each item

Each borrowed idea below has: **What/Why · Current YASTL state · Implementation approach (grounded in real files) · Effort/Value · Risks · Tasks**. Effort/Value are rough (S/M/L). Tasks are mirrored into the harness task list.

---

## Cross-cutting: how a new feature plugs into YASTL (reference)

Reuse the existing patterns — do not invent new ones:

- **New tables** → add `CREATE TABLE IF NOT EXISTS …` to `SCHEMA_SQL` in `app/database_schema.py` (safe for new *and* existing DBs). Indexes on those tables can go straight in `SCHEMA_SQL`.
- **New columns on existing tables** → add to the `CREATE TABLE` in `SCHEMA_SQL` **and** add a gated `ALTER TABLE … ADD COLUMN` block in `init_db()` in `app/database.py` (pattern: `PRAGMA table_info(<table>)` → if column missing, `ALTER`). Indexes on migrated columns go in `_POST_MIGRATION_INDEXES` (they run *after* the ALTERs), never in `SCHEMA_SQL`.
- **New API module** → `app/api/routes_<feature>.py` with an `APIRouter(prefix="/api/<feature>")`, then `app.include_router(<feature>_router)` in `app/main.py` (registration block ~lines 181–199).
- **New settings** → add the key to `SETTINGS_SCHEMA` (enum/bool), `NUMERIC_SETTINGS`, or `STRING_SETTINGS` in `app/api/routes_settings.py`; add a `ref()` in `frontend/src/composables/useSettings.js` + load it in the `loadSettings` mapping; surface UI in `frontend/src/components/SettingsModal.vue` (card sections with `.settings-section-title`).
- **New detail-panel content** → `frontend/src/components/DetailPanel.vue` tabs are `.detail-tab` (Info/Tags/More); add sections under the relevant `<template v-if="detailTab === '…'">`.
- **New top-level view/modal** → follow `StatsModal.vue` (navbar icon → `.detail-overlay` modal) or add a sidebar section in `SideBar.vue`.
- **CPU-bound work** (rendering, embeddings if local) → `app/workers.py` `run_cpu_job(...)`; background bulk jobs follow the `regenerate-thumbnails` / `generate-previews` pattern in `routes_settings.py` (module-level progress dict + `GET …/status`).
- **Search** lives in `app/api/routes_search.py` — FTS5 subquery + dynamic WHERE, BM25 `rank` ordering. Hybrid semantic search hooks in here.

---

## 1. AI auto-tagging + semantic / natural-language search  ·  Value: **L** · Effort: **L**

*Flagship Meshory differentiator: "AI tagging & semantic search (your own key)", OpenRouter, "find 'articulated dragon' even when the file is `dragon_v2_final.stl`."*

**Current YASTL state:** heuristic auto-tagger (`services/tagger.py` — URL/filename/bbox shape) + tag co-occurrence. No vision/LLM tagging, no embeddings, no semantic search. Search is FTS5 keyword only.

**Feasibility (from research):** both features are **cheap** (vision auto-tag ≈ $15–75 one-time for 50k models; embeddings ≈ $0.15 for 50k — effectively free) and fit YASTL's existing background-job + settings + FTS patterns with **almost no new infrastructure**. All strictly opt-in, off by default, degrading to today's behavior when no key is set.

**Provider plumbing** — new `app/services/ai_client.py` with just two ops, dispatched on settings:
- `vision_tags(image_bytes, filename, vocab) -> {tags, description}` and `embed_texts(texts) -> vectors`.
- Two backends: **OpenAI-compatible** (`openai` async SDK, `base_url` swap covers OpenAI *and* OpenRouter) + **Anthropic native** (`anthropic` async SDK).
- **Embeddings asymmetry (important):** Anthropic has **no embeddings API** — when the chat key is Anthropic, route embeddings to **Voyage** (`voyage-3.5-lite`, 1024-dim, Anthropic-owned) or OpenRouter. So embeddings are a *separately-configured sub-provider* (`ai_embed_provider`/`ai_embed_key`/`ai_embed_model`), not glued to the chat provider.
- **Default models:** vision → Anthropic `claude-haiku-4-5` (or OpenAI `gpt-4o-mini`) — *not* a flagship, a 256×256 thumbnail is trivial; embeddings → `text-embedding-3-small` (use `dimensions=512` to shrink) or Voyage lite. All exposed as settings.

**Vector storage — the key decision: float32 BLOB + in-memory numpy brute-force (NOT a SQLite extension).**
- New `model_embeddings` table: `model_id PK, embedding BLOB (float32 LE), dim, embed_model, source_hash, updated_at`.
- On startup, load all vectors into one resident numpy matrix (kept on the event-loop process, *never* the trimesh worker); cosine = one matmul (~5–15 ms even at 50k with 512-dim). Zero native dependency, zero extension-loading friction (matters: `open_db()` opens a fresh connection per request; macOS Python ships without extension support). 
- Graduate to **`sqlite-vec`** (pure-C, `pip install`) *only* past ~100k vectors or if you want vector search fused with SQL metadata filters. **Never `sqlite-vss`** (deprecated).

**Hybrid search — Reciprocal Rank Fusion (RRF), ~15 lines.** Don't try to combine BM25 and cosine scores numerically (incomparable scales). Instead: run the existing FTS `MATCH` branch (top-N by `fts.rank`) + the vector branch (top-N by cosine), fuse by `Σ 1/(60+rank)`, sort, paginate, then reuse `enrich_models_page()`. Add `?mode=hybrid` to `GET /api/search`; **empty vector branch (no key) ⇒ automatic fallback to today's pure-FTS**. All existing filters apply as a post-filter on the fused IDs.

**What to embed:** `name` + last 1–2 folder segments + tags + description (this is where "articulated dragon" hides when the file is `dragon_v2_final.stl` in `…/Articulated Dragons/`). Store `source_hash` of that text; re-embed on name/desc edit, tag change (incl. auto-tagger), move, or embed-model switch.

**Vision auto-tagging:** structured JSON output (Anthropic `json_schema` / OpenAI `response_format`), constrain toward the existing tag vocabulary by **soft-steering in the prompt + post-filtering against the `tags` table** (enum-in-schema doesn't scale past ~200 tags). Insert accepted tags with **`source='ai'`** — the `model_tags.source` column already exists (`auto`/`manual`) and the UI already dims non-manual chips + offers "clear auto tags", so the treatment falls out for free. Fill `description` only when empty (mirrors the existing metadata policy).

**Background job & ops:** model the backfill on the existing `_auto_tag_all_models` / `regenerate-thumbnails` pattern (module-level progress dict + `POST …/backfill` + `GET …/status`), **but run AI calls with the async SDK directly on the event loop under an `asyncio.Semaphore(4–8)` — NOT the process pool** (AI is network-I/O-bound, not CPU-bound). Batch embeddings 100–500 texts/call. Cost cap via a settings counter (`ai_monthly_cost_cap_usd`) checked before each batch. Key handling: prefer an env var (`YASTL_AI_API_KEY` in `config.py`), or store in `settings` and reuse `services/import_credentials.py` masking — be honest it's "masked & local," not "secure."

**Phasing (recommended MVP = Phase 0 + Phase 1):**
- **Phase 0 — provider plumbing + settings + `POST /api/settings/ai/test`.** The fiddly, independently-testable foundation. Ship alone.
- **Phase 1 — semantic + hybrid search.** Highest value, lowest risk (reuses FTS + enrich). `model_embeddings` + numpy matrix + backfill job + RRF in `routes_search.py`. Delivers the "articulated dragon" win.
- **Phase 2 — vision auto-tagging.** `POST …/ai/auto-tag-all` + per-model action; then re-embed touched models so new tags improve search.
- **Phase 3 (optional) — polish:** provider Batch APIs (50% off) for the first 50k sweep; graduate to `sqlite-vec` if the library crosses ~100k.

**Risks:** provider plumbing is the fiddly part (isolate it in Phase 0). Otherwise additive and reversible. **Effort: Phase 0 = M, Phase 1 = M–L, Phase 2 = M.**

**Tasks:** see `1a` (Phase 0 plumbing), `1b` (Phase 1 semantic/hybrid search), `1c` (Phase 2 vision auto-tagging) in the task list.

---

## 2. Multi-plate Bambu 3MF project support  ·  Value: **M** (high for Bambu users) · Effort: **M**

*Meshory: "including multi-plate Bambu Studio 3MF projects" with plate selection.*

**Current YASTL state:** 3MF is handled by `services/processor.py` (trimesh load) and treated as **one model** → one thumbnail. A Bambu project 3MF with several plates collapses to a single blob; per-plate structure is lost.

**Key facts (from research):** A `.3mf` is an OPC zip. **trimesh reads only `3D/3dmodel.model` and ignores `Metadata/` entirely** — so the plate structure must be parsed from the zip ourselves. Bambu/Orca store it in `Metadata/model_settings.config` (XML). Detection + plate enumeration is a **cheap zipfile peek, no mesh load**.

- **Detect** a Bambu/Orca project = presence of `Metadata/model_settings.config` (plain 3MF from Fusion/Prusa/Blender has none). **Plate count** = number of `<plate>` blocks in that file.
- **Plate → objects:** each `<plate>` has `<metadata key="plater_id">`, `<metadata key="plater_name">` (note the Bambu typo — it's `plater_name`), `<metadata key="thumbnail_file" value="Metadata/plate_1.png">`, and `<model_instance>` children carrying `object_id` / `instance_id`. `object_id` maps to `<object id="N">` in `3D/3dmodel.model` (what trimesh loads).
- **Per-plate previews are already embedded** — `Metadata/plate_N.png` (lit), `plate_N_small.png`, `top_N.png`, `pick_N.png`. **Reuse them** (resolve the path from the plate's `thumbnail_file` metadata, don't hardcode) instead of re-rendering; fall back to render only when absent (unsliced plate).
- **Per-plate slice stats** (optional caption "18.5 g / 1h20m") live in `Metadata/slice_info.config` (`prediction`=seconds, `weight`=grams, `<filament>` color/type).
- **Gotcha:** trimesh de-dupes geometry names (may suffix), so don't use trimesh names as the `object_id` key — build the id→name map from `3D/3dmodel.model` yourself.

**Implementation approach:**
- **Scanner/processor** (`services/processor.py` / `services/scanner.py`): add a `zipfile` peek for `.3mf` files → if `Metadata/model_settings.config` present, parse plates. Store `plate_count` + a compact `plate_meta` JSON (plater_id, name, object_ids, embedded thumb path, weight/time) on the model row.
- **DB migration:** add `plate_count INTEGER DEFAULT NULL` and `plate_meta TEXT DEFAULT NULL` to `models` (SCHEMA_SQL + gated `ALTER TABLE` in `init_db()`).
- **Card thumbnail:** for a multi-plate model, use `plate_1.png` as the card thumb and show a **plate-count badge** (mirror the existing zip-group count badge).
- **API:** `GET /api/models/{id}/plates` (list: id, name, object count, weight/time, has-thumb); `GET /api/models/{id}/plates/{n}/thumbnail` (serve embedded PNG, else render); `GET /api/models/{id}/plates/{n}/glb` (per-plate GLB on demand — filter the trimesh scene to that plate's `object_ids`, reuse `services/preview.build_preview_glb` in the worker pool).
- **Viewer** (`DetailPanel.vue` + `useViewer.js`): when `plate_count > 1`, show a plate selector (tabs/dropdown) above the viewer; selecting a plate loads its PNG (instant) or GLB (for rotate/inspect).
- **⚠️ Validate first:** no `.3mf` samples on this dev box — before finalizing the parser, test against a **real multi-plate export from `/mnt/DATA/3dPrinting` on CT333** to confirm exact `model_settings.config` nesting.

**Risks:** medium — parser must handle plain-3MF, single-plate-Bambu, multi-plate, and production-extension (multi-file) 3MF gracefully. **Effort: M.**

**Tasks:** (a) zipfile plate detector + `plate_count`/`plate_meta` columns + scanner integration; (b) `/plates` list + per-plate thumbnail (reuse embedded PNG) endpoints; (c) per-plate GLB on demand; (d) plate-count badge + viewer plate selector; (e) validate against a real CT333 sample.

---

## 3. Filament inventory  ·  Value: **M** · Effort: **M**

*Meshory roadmap item. Track spools; optionally tie to prints.*

**Current YASTL state:** none. Adjacent to existing print tracking (`models.print_count`, `last_printed_at`).

**Implementation approach:**
- **DB** (`SCHEMA_SQL`): new table
  ```sql
  CREATE TABLE IF NOT EXISTS filaments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      brand TEXT, material TEXT,            -- PLA/PETG/ABS/TPU/resin…
      color_name TEXT, color_hex TEXT,      -- swatch in UI
      diameter REAL DEFAULT 1.75,
      spool_weight_g REAL,                  -- full spool net weight
      remaining_g REAL,                     -- decremented as prints log usage
      cost REAL, vendor TEXT, purchased_at TIMESTAMP,
      notes TEXT DEFAULT '',
      status TEXT DEFAULT 'active',         -- active/empty/archived
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  ```
- **API:** `app/api/routes_filament.py` → CRUD `GET/POST/PUT/DELETE /api/filaments`. Register in `main.py`.
- **Frontend:** a "Filament" modal (clone `StatsModal.vue` structure) opened from the navbar or a new Settings card. Table with color swatch (`color_hex`), material chip, remaining-weight bar, add/edit form. Optional "low spool" badge when `remaining_g` under a threshold.
- **Tie-in (optional, phase 2):** the print-log row (item #4) references `filament_id` + `grams_used`, and logging a print decrements `filaments.remaining_g`.

**Risks:** low — standalone domain, no coupling until the optional print tie-in. **Effort: M.**

**Tasks:** (a) filaments table + migration; (b) routes_filament CRUD + tests; (c) Filament UI modal + api.js wrappers; (d) optional print→filament deduction.

---

## 4. Finished-prints inventory ("by location")  ·  Value: **M** · Effort: **M**

*Meshory roadmap: "print history documentation" + "finished prints inventory by location." Turns a print counter into a real inventory of physical objects.*

**Current YASTL state:** `POST /api/models/{id}/print` just does `print_count += 1` + `last_printed_at = now` (`routes_models.py:527`). No per-print records, no location/filament/quantity.

**Implementation approach:**
- **DB** (`SCHEMA_SQL`): new log table
  ```sql
  CREATE TABLE IF NOT EXISTS print_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
      printed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      quantity INTEGER DEFAULT 1,
      filament_id INTEGER REFERENCES filaments(id) ON DELETE SET NULL,  -- item #3
      grams_used REAL, print_time_min INTEGER,
      location TEXT DEFAULT '',            -- "bin A3", "gift box", "office"
      status TEXT DEFAULT 'kept',          -- kept/gifted/sold/failed/scrapped
      notes TEXT DEFAULT ''
  );
  CREATE INDEX IF NOT EXISTS idx_print_log_model ON print_log(model_id);
  CREATE INDEX IF NOT EXISTS idx_print_log_location ON print_log(location);
  ```
- **Migration/backfill:** keep `models.print_count`/`last_printed_at` as a fast denormalized summary (or derive via `COUNT`/`MAX`). On first run, optionally backfill one `print_log` row per existing `print_count`.
- **API:** extend `POST /api/models/{id}/print` to accept `{quantity, filament_id, grams_used, location, notes}` and insert a `print_log` row (still bump the summary counter). Add `GET /api/prints?model_id=&location=&since=` and `PUT/DELETE /api/prints/{id}`. New `routes_prints.py` (or fold into `routes_models.py`).
- **Frontend:** the detail **More** tab already has "Print History" — upgrade from count/undo to a list of `print_log` entries (date · qty · filament swatch · location · status). Add a global **Inventory** view grouped by `location` (what physical objects are where). "Mark printed" gains an optional quick form (qty/location/filament).

**Risks:** medium — must keep the existing counter UX working while adding the log; migration/backfill needs care. **Effort: M.**

**Tasks:** (a) print_log table + indexes; (b) extend print endpoint + new /api/prints routes + tests; (c) detail More-tab history list; (d) location-grouped Inventory view.

---

## 5. First-class Print Queue  ·  Value: **M** · Effort: **S–M**

*Meshory roadmap "print lists and tracking." YASTL currently fakes this with a manual "Print Queue" collection.*

**Current YASTL state:** no queue entity. The demo used a manual collection named "Print Queue". Drag-drop-to-collection infra already exists (`apiBulkAddToCollection`, card `draggable`).

**Implementation approach:**
- **DB** (`SCHEMA_SQL`):
  ```sql
  CREATE TABLE IF NOT EXISTS print_queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
      status TEXT DEFAULT 'queued',        -- queued/printing/done/failed
      position INTEGER DEFAULT 0,
      printer TEXT, notes TEXT DEFAULT '',
      added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      started_at TIMESTAMP, finished_at TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_print_queue_status ON print_queue(status, position);
  ```
- **API:** `routes_queue.py` → `GET /api/queue`, `POST /api/queue {model_id}`, `PUT /api/queue/{id}` (status/position), `DELETE /api/queue/{id}`, `PUT /api/queue/reorder`. On `status → done`, auto-insert a `print_log` row (item #4) and bump `print_count` — so the queue *feeds* the inventory.
- **Frontend:** a Queue view (navbar icon or sidebar item) — a simple ordered list or status lanes (queued / printing / done). Reuse the drag/reorder patterns already used for collections. "Add to print queue" action on card hover + detail panel.
- **Migration note:** offer to convert an existing "Print Queue" *collection* into real queue rows (nice touch, low effort).

**Risks:** low — leans on existing drag infra + print tracking. **Effort: S–M.**

**Tasks:** (a) print_queue table; (b) routes_queue CRUD + reorder + done→print_log hook + tests; (c) Queue view + "add to queue" actions; (d) optional collection→queue import.

---

## 6. Slicer auto-detection & one-click handoff  ·  Value: **M** · Effort: **M** ⚠️ architecture caveat

*Meshory (desktop) "auto-detects 15+ slicers" and opens files in them. YASTL is a **web app**, so the server can't see or launch the client's slicer — the mechanism is fundamentally different.*

**Current YASTL state:** a `preferred_slicer` setting exists (`none/bambustudio/orcaslicer/prusaslicer`) but no actual "open in slicer" action.

**Hard architectural truth (from research):** the server can't see or launch the client's slicer — everything must happen in the browser or in client software the user installs. Three levers: a **preferred-slicer setting**, a **`scheme://` URL link**, or a **companion helper**. And a landmine: **PrusaSlicer and Bambu Studio hard-code a domain whitelist** (`printables.com` / `makerworld.com`) into their URL handlers, so `prusaslicer://open?file=http://10.0.0.59/...` is **silently rejected** for a self-hosted origin. **OrcaSlicer and Cura enforce no whitelist**, so their schemes *do* work on a LAN. (Confirmed by [Manyfold](https://github.com/manyfold3d/manyfold), the closest self-hosted analog — it offers one-click for Orca/SuperSlicer via schemes and falls back to download, and pointedly does *not* claim Prusa/Bambu one-click.)

**Recommended tiered approach (degrade gracefully):**
- **Tier 1 — default, works with ALL slicers:** "Download for <preferred slicer>" button. Serve `/api/models/{id}/file` with `Content-Disposition: attachment; filename="<name>.<ext>"` + a real model MIME (`model/stl`, `model/3mf`, else `application/octet-stream`). Browser downloads → opens the OS-default slicer via file association. No whitelist issues; covers Prusa, Bambu, SuperSlicer, all OSes. *(Backend touch: `routes_model_files.py` set the disposition header.)*
- **Tier 2 — true one-click for OrcaSlicer & Cura only:** when `preferred_slicer ∈ {orca, cura}`, render a scheme link that the slicer fetches itself:
  - Orca: `orcaslicer://open?file=http://<yastl-host>:8000/api/models/{id}/file`
  - Cura: `cura://open?file=<percent-encoded same absolute URL>`
  Must use an **absolute** host URL (`window.location.origin` in the frontend, not a relative path). Limitations to show in-UI: scheme must be registered on the client (reliable on Win/macOS, **may need manual `.desktop` setup on Linux/AppImage**), and the file URL should end in `.stl`/`.3mf` or carry `Content-Disposition` so the slicer sniffs the type. **Do NOT render scheme buttons for Prusa/Bambu/SuperSlicer** — fall through to Tier 1 for those.
- **Tier 3 — optional power-user companion helper (document as advanced):** a tiny localhost daemon (`fetch("http://127.0.0.1:7845/open", …)` with permissive CORS) that downloads the file and launches *any* chosen slicer with a real local path — the only way to get reliable Prusa/Bambu one-click and genuine "which slicers are installed" detection (it can stat the known install paths). Ship optional; app must fully work without it.

**Implementation approach:**
- Extend the existing `preferred_slicer` setting (`none/bambustudio/orcaslicer/prusaslicer`) to add `cura`, `superslicer`.
- Add `Content-Disposition` (+ correct MIME) to the file-serving endpoint (`routes_model_files.py`).
- Frontend (`DetailPanel.vue` + card hover): a slicer button that switches between Tier 1 (download) and Tier 2 (scheme link) based on `preferred_slicer`, built with `window.location.origin`.
- Tier 3 helper is a separate optional deliverable — defer.

**Risks:** low for Tier 1/2 (frontend + one header). The value ceiling is capped by the whitelist reality — be honest in the UI about what one-click supports. **Effort: M** (S if Tier 1 only).

**Tasks:** (a) extend preferred_slicer enum; (b) Content-Disposition on file endpoint; (c) tiered "Open/Download in slicer" button (Orca/Cura scheme vs download); (d) optional Tier-3 companion helper (separate, later).

---

## 7. Simplicity / UX lessons  ·  Value: **M–L** · Effort: **S** (mostly)

*You said you like that Meshory is simpler. These are cheap wins that make YASTL feel calmer without removing power.*

**7a. Folder-first onboarding.** First-run empty state: when `libraries.length === 0`, App.vue shows a single centered "Add your models folder" field (name + path → create library → auto-scan) instead of routing through Settings → Libraries. Low effort, big first-impression win.

**7b. "Minimal" grid density.** `localStorage yastl_grid_density` is already `compact`/`comfortable`; add a third **`minimal`** mode (or a toggle) that hides badges/pills/tags on the card until hover, leaving just thumbnail + name. Pure CSS + a body/grid class. Matches Meshory's clean gallery. Low effort.

**7c. Progressive disclosure.** The grid card currently stacks many signals (format, fav, printed, collections, tags, namespaces, collection color bar). Consider: show ≤N tag chips, move printed/collection cues to hover, keep the default card quiet. Detail panel already tabs advanced content behind Tags/More — keep the **Info** tab lean.

**7d. Lean into local-first framing.** README / landing copy: "your files never leave your machine, no account, no cloud." Already true of YASTL; just say it. Docs-only.

**7e. (optional) Command palette / quick-jump.** `⌘K` to jump to a model/collection/tag — a "simple but powerful" flourish. Medium effort; nice-to-have.

**Risks:** low; all reversible UI. **Effort: S** (7a/7b/7c/7d), **M** (7e).

**Tasks:** (a) first-run folder onboarding; (b) minimal grid density; (c) card progressive-disclosure pass; (d) README local-first copy; (e) optional ⌘K palette.

---

## Suggested sequencing

1. **Quick wins first:** 7a–7d simplicity (S) → immediate feel improvement, no schema risk.
2. **Print pipeline:** #5 Queue → #4 Finished-prints log → #3 Filament (they compose: queue done → print_log → filament deduction). Do as one themed wave.
3. **Bambu 3MF (#2):** self-contained, high value for Bambu users.
4. **AI (#1):** biggest lift; phase it — **Phase 0** provider plumbing → **Phase 1** semantic/hybrid search (the recommended MVP: highest value, lowest risk, reuses FTS) → **Phase 2** vision auto-tagging. Off-by-default, BYO-key.
5. **Slicer handoff (#6):** last — architecture-constrained; ship the pragmatic subset.

## Task list

See the harness task list (one parent task per item + sub-tasks). This doc is the source of truth for scope; update it as items are refined or shipped.
