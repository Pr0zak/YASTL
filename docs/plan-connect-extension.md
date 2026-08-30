# YASTL Connect — browser capture extension

**Status:** in progress (started 2026-08-30)
**Mnemonic prefix:** `CONN`
**Branch:** `claude/connect-extension`

A Manifest V3 browser extension that captures 3D model downloads from model
hosting sites and pushes them into a YASTL library with the page's metadata
already attached. Modelled on MeshVault Connect, but written from scratch — that
extension is closed-source proprietary freeware and cannot be forked or bundled.

---

## 1. Why an extension at all

YASTL already imports by URL. `app/services/scrapers.py` detects six sites
(Thingiverse, MakerWorld, Printables, MyMiniFactory, Cults3D, Thangs) and pulls
structured metadata from their own APIs; `importer.py` and `downloader.py` fetch
the files server-side; `import_credentials.py` stores site logins so the server
can authenticate as the user.

That covers the easy half. What server-side fetching cannot do:

- **Auth-walled downloads.** Printables and MakerWorld gate some files behind a
  login; Cults3D gates paid models entirely. Storing the user's site password on
  the server to work around this is a liability we would rather not carry.
- **Bot detection.** Cloudflare and Akamai increasingly reject datacenter and
  residential-server traffic. A real browser session with a real cookie jar and
  a real TLS fingerprint sails through.
- **Expiring signed CDN URLs.** Scraped download links are frequently one-shot
  S3/GCS presigned URLs. By the time a background job dequeues them they are
  dead.
- **Gallery images, README and licence text.** URL import captures none of these
  today, and the detail panel's docs viewer (`GET /api/models/{id}/docs`) has
  nothing to show for imported models as a result.

The browser is already authenticated, already trusted, and already holds the
page. Moving the fetch there solves all four at once.

## 2. What the extension is responsible for

Deliberately narrow. The extension harvests and uploads; it does not parse 3D
files, generate thumbnails, or hold a library index. Everything it captures
lands through one server endpoint and then follows the existing import pipeline.

```
  model site page                    background service worker            YASTL
  ───────────────                    ─────────────────────────            ─────
  content script harvests    ──msg──▶  cache page context by tabId
  OG/JSON-LD/DOM + gallery

  user clicks site's own     ──────▶  downloads.onCreated fires
  Download button                     correlate via DownloadItem.referrer
                                      re-fetch finalUrl with credentials
                                      ────────── multipart POST ──────────▶ /api/connect/capture
                                                                            ├─ writes into library dir
                                                                            ├─ process_imported_file()
                                                                            └─ applies title/desc/tags/
                                                                               author/licence/source_url
```

### Correlation is the fiddly part

`chrome.downloads.DownloadItem` carries **no `tabId`**. Correlation therefore
falls back to, in order:

1. `DownloadItem.referrer` matched against the cached page contexts by host and
   path. Reliable when the site navigates to the download; absent when the
   download is kicked off by `fetch` + `<a download>` from JS.
2. The most recently focused tab on a supported site, if the download started
   within a 60-second window of that tab last being active.
3. Nothing — the capture is queued as "unattributed" in the popup, and the user
   can pick a page for it manually or discard it.

### Capture modes

Getting the bytes is the other fiddly part: **an extension cannot read the
downloaded file off disk.** The only way to obtain the content is to fetch the
URL itself from the service worker, where `host_permissions` supply the cookies.
Two modes, user-selectable, defaulting to the safe one:

- **Copy (default).** Let the browser's download complete normally, then
  re-fetch `finalUrl` and upload that copy. The user keeps their file no matter
  what happens on our side. Costs one extra download, and fails on genuinely
  single-use presigned URLs.
- **Intercept.** Cancel the browser download at `onCreated`, fetch once
  ourselves, upload, and optionally re-offer the blob as a local download. Uses
  the token exactly once, but if our fetch fails the user has to click Download
  again.

That MeshVault Connect requests optional host permissions for S3 and Google
Storage is strong evidence it re-fetches the CDN URL the same way.

## 3. Server side

A dedicated router rather than bolting onto `/api/import/upload`, for three
reasons: the payload is richer (author, licence, gallery, page HTML), the
endpoint needs token auth that the existing SPA routes must not inherit, and
keeping it separate means the extension contract can version independently.

**`app/api/routes_connect.py`**

| Route | Auth | Purpose |
|---|---|---|
| `GET /api/connect/info` | none | Handshake. Returns `{app, version, connect_enabled}` so "Test connection" can report *reachable but disabled* distinctly from *unreachable*. |
| `GET /api/connect/targets` | token | Libraries (id, name, path, model_count) and collections for the popup's destination picker. |
| `POST /api/connect/capture` | token | Multipart: the model file plus `library_id`, `subfolder`, `source_url`, `name`, `description`, `tags`, `author`, `license`, `collection_id`. Runs `process_imported_file`, then applies the metadata. |

### Auth

YASTL has no authentication today, and adding real auth is out of scope — it
would break the SPA. Instead the Connect endpoints are **opt-in and disabled by
default**:

- New bool setting `connect_enabled` (default `false`).
- New string setting `connect_token`, masked on read like `ai_api_key`, generated
  in the Settings UI.
- A FastAPI dependency rejects any `/api/connect/{targets,capture}` request whose
  `X-YASTL-Token` header does not match the stored token, and rejects everything
  with 403 when `connect_enabled` is false or the token is empty.

This is a shared-secret bearer token over plain HTTP on a LAN. It stops a random
web page from silently writing to the library; it is not protection against
someone already on the network sniffing traffic. That limitation gets stated
plainly in the Settings UI and the extension README rather than papered over.

### No CORS middleware

None is needed and none will be added. All network calls happen in the service
worker, which bypasses CORS for origins covered by `host_permissions`. The popup
and options page message the worker rather than fetching directly, precisely so
this stays true — content scripts and extension pages do *not* reliably get the
same exemption.

## 4. Extension layout

Plain JavaScript, no build step, no dependencies. `chrome://extensions` →
*Load unpacked* works straight from a git checkout, and there is nothing extra
to wire into the Vite build or the CT333 deploy.

```
extension/
  manifest.json          # MV3
  README.md              # install + configure, and the token caveat
  icons/                 # reused from app/static/
  src/
    background.js        # service worker entry: downloads, queue, messaging
    api.js               # YASTL client (info / targets / capture)
    state.js             # chrome.storage wrappers, capture queue
    sites.js             # per-site normalizers, run in the worker
    content.js           # dumb page harvester, one file, no imports
    popup/               # destination picker + capture queue
    options/             # server URL, token, capture mode, site toggles
```

**The content script is deliberately dumb.** It reads `<meta>` tags, JSON-LD
blocks, `<script id="__NEXT_DATA__">`, gallery `<img>` sources and a small set of
per-site selectors, and ships that raw bag to the worker. All interpretation
happens in `sites.js`, where it is a plain ES module that can be unit-tested in
Node. MV3 does not support ES modules in manifest-declared content scripts, so
keeping the script import-free is a constraint, not a preference.

**Metadata comes from two places and gets merged.** The harvested page context is
the fallback; where the site is one of the six YASTL already knows, the worker
also asks `POST /api/import/preview` for the server's API-derived metadata, which
is cleaner and structured. Server wins on conflict. This is the point of the
whole design — the six site scrapers stay in Python, written once.

## 5. Tasks

| Mnemonic | Subject | Blocked by |
|---|---|---|
| CONN-1 | Server: `routes_connect.py` — info/targets/capture, token dependency, `connect_enabled` + `connect_token` settings | — |
| CONN-2 | Server: Settings → Connect card (toggle, generate/rotate/copy token, install pointer, security note) | CONN-1 |
| CONN-3 | Extension skeleton: MV3 manifest, service worker, API client, options page, icons | CONN-1 |
| CONN-4 | Extension: content-script harvester + per-site normalizers + `/api/import/preview` merge | CONN-3 |
| CONN-5 | Extension: download interception, referrer correlation, Copy/Intercept modes | CONN-3 |
| CONN-6 | Extension: popup — destination picker, capture queue, progress, retry, unattributed captures | CONN-4, CONN-5 |
| CONN-7 | Gallery images + README bundling. Needs `process_uploaded_zip` to stop discarding non-model entries so the docs viewer can see them | CONN-6 |
| CONN-8 | Tests: pytest for the connect routes; Node smoke test for the normalizers | CONN-1, CONN-4 |
| CONN-9 | Docs: `extension/README.md`, CLAUDE.md architecture note, README section | CONN-6 |

CONN-1 through CONN-6 are the working core. CONN-7 is the first thing that is
genuinely optional.

## 6. Known risks

- **Site DOM churn.** Every scraper against a site we do not have an API for
  rots. The harvester leans on Open Graph and JSON-LD first for exactly this
  reason; per-site selectors are a bonus layer that degrades to "still captured,
  fewer tags" rather than to a hard failure.
- **Single-use download tokens** break Copy mode on some sites. Intercept mode
  exists for those, and the popup surfaces the failure with a retry rather than
  swallowing it.
- **Store review.** Publishing to the Chrome Web Store means justifying broad
  host permissions. Loading unpacked, or self-hosting a Firefox `.xpi`, avoids
  the question entirely and is the expected distribution for a self-hosted tool.
- **Chrome MV3 service-worker lifetime.** The worker is killed after ~30s idle.
  All capture state lives in `chrome.storage.session`, never in a module-level
  variable, and long uploads keep the worker alive by virtue of the in-flight
  fetch.
