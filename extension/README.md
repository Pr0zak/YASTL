# YASTL Connect

A browser extension that captures 3D model downloads from the usual hosting
sites and pushes them into a YASTL library with the source page's title,
description, tags, author and licence already attached.

Supported today: **Printables, Thingiverse, MakerWorld, Thangs, MyMiniFactory,
Cults3D**. Anything else still captures — it just falls back to whatever Open
Graph metadata the page provides.

## Why not just paste the URL into YASTL?

YASTL can already import from a URL, and where that works it is the simpler
path. Use the extension for the cases server-side importing structurally cannot
reach:

- **Files behind a site login.** Your browser is already signed in. Nothing has
  to store your Printables password on the server.
- **Sites behind Cloudflare or similar.** A real browser session passes checks
  that a server-side fetch increasingly does not.
- **One-shot presigned CDN links.** The extension has the link while it is
  still valid, rather than minutes later from a queue.

## Install

There is no build step and no dependencies — the source directory *is* the
extension.

**Chrome / Edge / Brave**

1. Open `chrome://extensions` (or `edge://extensions`).
2. Turn on **Developer mode**.
3. **Load unpacked**, and select this `extension/` directory.

**Firefox**

1. Open `about:debugging#/runtime/this-firefox`.
2. **Load Temporary Add-on**, and select `extension/manifest.json`.

Firefox unloads a temporary add-on when the browser closes. For a permanent
install you would need to package and sign it through addons.mozilla.org.

## Set up

**In YASTL** — open **Settings → Connect**, switch Connect on, and press
**Generate**. Copy the token; it is shown once and masked from then on.

**In the extension** — open its options page (the puzzle-piece menu → YASTL
Connect → Options, or it opens itself on first install) and fill in:

| Field | Value |
|---|---|
| YASTL address | The same URL you open YASTL at, including the port — e.g. `http://10.0.0.59:8000` |
| Access token | The token you just generated |

Press **Test connection**, then **Grant site access**, then pick a destination
library and press **Save**.

**Grant site access** matters more than it looks. Model sites routinely redirect
downloads to a CDN on a different host, and the extension can only fetch a file
from a host it has permission for. Chrome will only grant that permission in
response to a button press, so it cannot be requested later when a download is
already in flight — if you skip this step, captures from those sites fail with a
permission error.

## Use

Browse to a model page and click the site's own Download button as usual. The
capture appears in the extension's popup, and the model lands in your library a
few seconds later.

The toolbar badge shows captures in flight in blue, and anything failed or
waiting for you in red.

## Capture modes

An extension **cannot read a downloaded file off your disk** — there is no API
for it. The only way to get the bytes to YASTL is to fetch the URL a second
time, from the extension, where your cookies are attached. The two modes differ
in how they handle that.

**Copy** (default) lets your normal download finish, then fetches its own copy.
You keep the file whatever happens on our side. The cost is downloading twice,
and on sites that issue single-use download links the second fetch fails with a
403.

**Intercept** cancels the browser's download the moment it starts and fetches
once, so a single-use link is spent exactly once. If that fetch then fails you
have lost nothing but the click — press Download again.

Start on Copy. Switch a site to Intercept only if its captures fail with 403.

## When a capture says "No source page found"

A download carries no reference to the tab that started it — Chrome's download
API genuinely does not expose one. The extension matches downloads to pages by
the `referrer` the browser reports, falling back to the most recent supported
page you were looking at. When a site starts its download entirely from
JavaScript there can be nothing to match on.

Those captures wait in the popup rather than landing without metadata. Open the
model's page in the active tab and press **Use this tab**.

## About the token

The token is a shared secret sent with every capture. Over plain `http://` on a
home network it is readable by anything already watching that network. It exists
to stop an arbitrary web page silently writing into your library; it is not
protection against someone who is already on your wire.

Regenerating the token in YASTL Settings immediately stops any browser still
holding the old one — that is how you revoke access.

## Layout

```
manifest.json          Manifest V3
src/
  background.js        Service worker — downloads, correlation, upload queue
  api.js               YASTL client (info / targets / capture)
  state.js             chrome.storage wrappers and the capture queue
  sites.js             Metadata normalizers — pure, unit-tested
  content.js           Page harvester — scrapes, interprets nothing
  popup/               Destination picker and capture queue
  options/             Server, token, destination, capture mode
tests/sites.test.mjs   node --test extension/tests/
```

Two structural notes for anyone editing this.

**All network calls belong in the service worker.** It is exempt from CORS for
hosts it has permission for; extension pages and content scripts are not
reliably exempt. The popup and options page message the worker instead. Moving a
`fetch` into a page will appear to work and then fail on a different Chrome
build.

**Nothing may live in a module-level variable.** Chrome recycles an MV3 service
worker after roughly 30 seconds idle and re-evaluates every module from scratch,
so in-memory state vanishes between a download starting and finishing. All state
goes through `state.js` into `chrome.storage`.

## Relationship to MeshVault Connect

This was written from scratch after studying what MeshVault Connect does. That
extension is closed-source proprietary freeware and neither its code nor its
name is used here. The shared design — a content script harvesting metadata, a
worker correlating downloads and posting to a local HTTP API — is the obvious
shape for the problem rather than anything borrowed.
