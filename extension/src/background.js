/**
 * Service worker: the whole of YASTL Connect's actual behaviour.
 *
 * Two things make this file's shape non-negotiable.
 *
 * First, every listener is registered synchronously at module top level. Chrome
 * recycles an MV3 worker after roughly 30 seconds idle and re-evaluates the
 * module on the next event; a listener attached inside an async callback would
 * simply not exist when the download it was meant to catch fires.
 *
 * Second, an extension cannot read a downloaded file off disk. There is no API
 * for it and no way around it. The only route to the bytes is to fetch the URL
 * ourselves from here, where host permissions attach the site's cookies. That
 * single constraint is what the two capture modes below exist to manage.
 */

import {
  buildMetadata,
  isModelPage,
  isServerScraped,
  storageFilename,
} from './sites.js';
import {
  ConnectError,
  fetchInfo,
  fetchTargets,
  previewSource,
  uploadCapture,
} from './api.js';
import {
  allPageContexts,
  clearFinishedCaptures,
  dropPageContext,
  getPageContext,
  getQueue,
  getSettings,
  newCaptureId,
  pushCapture,
  putPageContext,
  removeCapture,
  setSettings,
  updateCapture,
} from './state.js';

/** Extensions we will try to capture. Mirrors the server's MODEL_EXTENSIONS. */
const CAPTURE_EXTENSIONS = new Set([
  '.stl', '.obj', '.gltf', '.glb', '.3mf',
  '.ply', '.dae', '.off', '.step', '.stp', '.fbx', '.zip',
]);

/** How stale a page context may be and still be credited with a download. */
const CORRELATION_WINDOW_MS = 60_000;

function extensionOf(name) {
  const match = /(\.[a-z0-9]+)(?:[?#].*)?$/i.exec(name || '');
  return match ? match[1].toLowerCase() : '';
}

function looksCapturable(item) {
  const fromFilename = extensionOf(item.filename);
  if (CAPTURE_EXTENSIONS.has(fromFilename)) return true;
  // Some sites serve the file from a path with no extension and set the name
  // via Content-Disposition, which is not populated on the item yet at
  // onCreated. Fall back to the URL.
  try {
    return CAPTURE_EXTENSIONS.has(extensionOf(new URL(item.finalUrl || item.url).pathname));
  } catch {
    return false;
  }
}

function filenameOf(item) {
  const base = (item.filename || '').split(/[\\/]/).pop();
  if (base) return base;
  try {
    const path = new URL(item.finalUrl || item.url).pathname;
    return decodeURIComponent(path.split('/').pop()) || 'capture.stl';
  } catch {
    return 'capture.stl';
  }
}

// ---------------------------------------------------------------------------
// Correlating a download with the page that produced it
// ---------------------------------------------------------------------------

/**
 * `chrome.downloads.DownloadItem` carries no tabId — there is no direct link
 * from a download back to the page that started it. Three strategies, in
 * descending confidence:
 *
 *   1. `referrer` matched against a cached page context by host and path. Right
 *      when the site navigates to the download; empty when the page kicked it
 *      off with fetch + <a download>, which is increasingly common.
 *   2. The most recent context on the same host, within a minute.
 *   3. The most recent context on any supported host, within a minute. Loose
 *      enough to be wrong, so it is marked low-confidence and the popup lets
 *      the user re-attribute it.
 *
 * Returns `{ context, confidence }`, or null when nothing plausible is cached.
 */
async function correlate(item) {
  const contexts = await allPageContexts();
  if (!contexts.length) return null;

  const now = Date.now();
  const fresh = contexts.filter(
    (c) => now - (c.capturedAt || 0) < CORRELATION_WINDOW_MS,
  );

  if (item.referrer) {
    try {
      const ref = new URL(item.referrer);
      const exact = contexts.find((c) => {
        try {
          const u = new URL(c.url);
          return u.hostname === ref.hostname && u.pathname === ref.pathname;
        } catch {
          return false;
        }
      });
      if (exact) return { context: exact, confidence: 'high' };

      const sameHost = contexts.find((c) => {
        try {
          return new URL(c.url).hostname === ref.hostname;
        } catch {
          return false;
        }
      });
      if (sameHost) return { context: sameHost, confidence: 'medium' };
    } catch {
      /* unparseable referrer; fall through */
    }
  }

  // No usable referrer. Prefer a fresh context on the same host as the file.
  try {
    const fileHost = new URL(item.finalUrl || item.url).hostname;
    const sameHost = fresh.find((c) => {
      try {
        const h = new URL(c.url).hostname.replace(/^www\./, '');
        return fileHost.endsWith(h);
      } catch {
        return false;
      }
    });
    if (sameHost) return { context: sameHost, confidence: 'medium' };
  } catch {
    /* ignore */
  }

  if (fresh.length) return { context: fresh[0], confidence: 'low' };
  return null;
}

// ---------------------------------------------------------------------------
// Capture pipeline
// ---------------------------------------------------------------------------

async function notify(title, message) {
  const settings = await getSettings();
  if (!settings.notifyOnCapture) return;
  try {
    await chrome.notifications.create({
      type: 'basic',
      iconUrl: chrome.runtime.getURL('icons/icon-128.png'),
      title,
      message,
    });
  } catch {
    /* notifications can be disabled at the OS level; not worth failing over */
  }
}

async function setBadge(text, color = '#61afef') {
  try {
    await chrome.action.setBadgeText({ text });
    if (text) await chrome.action.setBadgeBackgroundColor({ color });
  } catch {
    /* ignore */
  }
}

async function refreshBadge() {
  const queue = await getQueue();
  const active = queue.filter(
    (c) => c.status === 'pending' || c.status === 'uploading',
  ).length;
  const failed = queue.filter(
    (c) => c.status === 'failed' || c.status === 'needs-page',
  ).length;
  if (active) await setBadge(String(active), '#61afef');
  else if (failed) await setBadge(String(failed), '#dc3545');
  else await setBadge('');
}

/**
 * Fetch the model bytes.
 *
 * `credentials: 'include'` is the entire reason the extension exists: it sends
 * the user's own session cookie, so a login-gated file downloads exactly as it
 * would if they clicked it themselves.
 */
async function fetchModel(url) {
  const resp = await fetch(url, {
    credentials: 'include',
    redirect: 'follow',
  });
  if (!resp.ok) {
    throw new ConnectError(
      `The site returned ${resp.status} for the download. ` +
        (resp.status === 403
          ? 'That usually means a single-use download link that has already been spent — try Intercept capture mode in options.'
          : 'Try downloading again.'),
      { status: resp.status },
    );
  }
  return resp.blob();
}

/** Resolve the metadata for a capture, merging the server's scrape if useful. */
async function resolveMetadata(context, settings) {
  if (!context) return null;
  let server = null;
  if (context.url && isServerScraped(context.url) && settings.serverUrl) {
    server = await previewSource(settings.serverUrl, context.url);
  }
  return buildMetadata(context, server);
}

async function runCapture(captureId) {
  const settings = await getSettings();
  const queue = await getQueue();
  const capture = queue.find((c) => c.id === captureId);
  if (!capture) return;
  // Both the completion event and beginCapture's own state check can arrive for
  // the same capture. Whichever gets here first claims it below by moving it to
  // 'uploading'; the loser stops here rather than uploading the file twice.
  if (capture.status !== 'pending') return;

  if (!settings.serverUrl || !settings.token) {
    await updateCapture(captureId, {
      status: 'failed',
      error: 'YASTL Connect is not configured yet. Open the extension options.',
    });
    console.warn('[YASTL] no server address or token configured');
    await refreshBadge();
    return;
  }
  if (!capture.libraryId && !settings.libraryId) {
    await updateCapture(captureId, {
      status: 'failed',
      error: 'No destination library chosen. Pick one in the extension options.',
    });
    console.warn('[YASTL] no destination library selected');
    await refreshBadge();
    return;
  }

  await updateCapture(captureId, { status: 'uploading', error: null });
  await refreshBadge();

  try {
    const blob = await fetchModel(capture.url);
    const result = await uploadCapture({
      serverUrl: settings.serverUrl,
      token: settings.token,
      blob,
      filename: storageFilename(capture.filename, capture.metadata && capture.metadata.title),
      libraryId: capture.libraryId || settings.libraryId,
      subfolder: capture.subfolder ?? settings.subfolder,
      collectionId: capture.collectionId ?? settings.collectionId,
      metadata: capture.metadata || {},
    });

    await updateCapture(captureId, {
      status: 'done',
      error: null,
      size: blob.size,
      result: result.detail,
      modelIds: result.model_ids || [],
    });
    await notify(
      'Captured to YASTL',
      `${capture.metadata?.title || capture.filename} — ${result.detail}`,
    );
  } catch (e) {
    console.error('[YASTL] capture failed:', capture.filename, e);
    await updateCapture(captureId, {
      status: 'failed',
      error: e instanceof ConnectError ? e.message : String(e && e.message ? e.message : e),
    });
    await notify('Capture failed', `${capture.filename}: ${e.message || e}`);
  }
  await refreshBadge();
}

async function beginCapture(item) {
  const settings = await getSettings();
  if (!settings.autoCapture) {
    console.log('[YASTL] automatic capture is switched off in options; skipping');
    return;
  }

  // Correlation is a storage read and returns immediately. Metadata resolution
  // is not — it calls the server to scrape the source page, which can take
  // seconds. So the capture is written to storage *first*, in a 'preparing'
  // state, and only promoted to 'pending' once its metadata is attached.
  //
  // Doing this the obvious way round loses small downloads entirely: the file
  // finishes in well under a second, downloads.onChanged fires against an empty
  // queue, and by the time the capture is written there is no completion event
  // left to trigger it. The capture then sits on "Waiting for the download"
  // forever. 'preparing' also keeps onChanged from grabbing the capture early
  // and uploading it before it has any metadata.
  const match = await correlate(item);

  const capture = {
    id: newCaptureId(),
    url: item.finalUrl || item.url,
    filename: filenameOf(item),
    downloadId: item.id,
    createdAt: Date.now(),
    confidence: match ? match.confidence : 'none',
    sourceUrl: match ? match.context.url : null,
    metadata: null,
    libraryId: settings.libraryId,
    subfolder: settings.subfolder,
    collectionId: settings.collectionId,
    status: 'preparing',
  };
  await pushCapture(capture);
  await refreshBadge();

  const metadata = match ? await resolveMetadata(match.context, settings) : null;
  // Without a source page there is no metadata worth attaching, so the file
  // waits for the user to say where it came from rather than landing bare.
  const status = match ? 'pending' : 'needs-page';
  await updateCapture(capture.id, { metadata, status });
  await refreshBadge();

  if (status !== 'pending') return;

  if (settings.captureMode === 'intercept') {
    // Cancel the browser's copy so the download token is spent exactly once —
    // by us. Costs the user their local copy if our fetch then fails, which is
    // why this is not the default.
    try {
      await chrome.downloads.cancel(item.id);
      await chrome.downloads.erase({ id: item.id });
    } catch {
      /* already finished, or the user cancelled it first */
    }
    await runCapture(capture.id);
    return;
  }

  // Copy mode waits for the browser's download to finish before re-fetching,
  // rather than competing with it for the same connection. Ask where that
  // download actually got to, because it may well have finished while the
  // metadata scrape above was in flight.
  await resumeIfDownloadSettled(capture.id, item.id);
}

/**
 * Run or fail a pending capture according to the download's current state.
 *
 * Covers the completion that happened while we were busy, and the interrupted
 * download that would otherwise leave a capture waiting on an event that is
 * never coming.
 */
async function resumeIfDownloadSettled(captureId, downloadId) {
  let live = null;
  try {
    [live] = await chrome.downloads.search({ id: downloadId });
  } catch (e) {
    console.warn('[YASTL] could not read download state', e);
    return;
  }
  if (!live) return;

  if (live.state === 'complete') {
    console.log('[YASTL] download already finished; capturing now');
    await runCapture(captureId);
  } else if (live.state === 'interrupted') {
    console.warn('[YASTL] browser download was interrupted:', live.error);
    await updateCapture(captureId, {
      status: 'failed',
      error: `The browser's download failed (${live.error || 'interrupted'}), so there is nothing to capture. Try downloading again.`,
    });
    await refreshBadge();
  }
}

// ---------------------------------------------------------------------------
// Listeners — all registered synchronously
// ---------------------------------------------------------------------------

chrome.downloads.onCreated.addListener((item) => {
  // Log every download we see and what we decided. A capture that silently
  // does nothing is the worst failure this extension has, because there is no
  // surface anywhere that says why — not the popup, not the server log.
  if (!looksCapturable(item)) {
    console.log(
      '[YASTL] ignoring download (not a model file):',
      item.filename || item.finalUrl || item.url,
    );
    return;
  }
  console.log('[YASTL] capturing download:', item.filename || item.finalUrl || item.url);
  beginCapture(item).catch((e) => console.error('[YASTL] capture start failed', e));
});

chrome.downloads.onChanged.addListener((delta) => {
  if (!delta.state) return;
  const settled = delta.state.current;
  if (settled !== 'complete' && settled !== 'interrupted') return;
  (async () => {
    const settings = await getSettings();
    if (settings.captureMode !== 'copy') return;
    const queue = await getQueue();
    // Only 'pending' — a capture still 'preparing' has no metadata yet, and
    // beginCapture checks the download state itself once it is ready.
    const capture = queue.find(
      (c) => c.downloadId === delta.id && c.status === 'pending',
    );
    if (capture) await resumeIfDownloadSettled(capture.id, delta.id);
  })().catch((e) => console.error('[YASTL] capture finish failed', e));
});

chrome.tabs.onRemoved.addListener((tabId) => {
  dropPageContext(tabId).catch(() => {});
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handleMessage(msg, sender)
    .then((data) => sendResponse({ ok: true, data }))
    .catch((e) =>
      sendResponse({
        ok: false,
        error: e && e.message ? e.message : String(e),
        kind: e && e.kind ? e.kind : 'error',
      }),
    );
  return true; // keep the channel open for the async reply
});

async function handleMessage(msg, sender) {
  switch (msg && msg.type) {
    case 'page-context': {
      const url = msg.context && msg.context.url;
      // Search results, profiles and browsing history all live on the same
      // hosts as the models. Remembering them lets a download be attributed to
      // whichever of them happened to be visited most recently, which is how a
      // capture ended up titled "ProZac | Visit History".
      if (!isModelPage(url)) {
        console.log('[YASTL] not a model page, not remembering it:', url);
        return { stored: false, reason: 'not-a-model-page' };
      }
      if (sender.tab && sender.tab.id != null) {
        await putPageContext(sender.tab.id, msg.context);
      }
      return { stored: true };
    }

    case 'get-settings':
      return getSettings();

    case 'set-settings':
      return setSettings(msg.patch || {});

    case 'test-connection': {
      const settings = await getSettings();
      const url = msg.serverUrl || settings.serverUrl;
      const info = await fetchInfo(url);
      if (!info.connect_enabled) {
        throw new ConnectError(
          'YASTL is reachable, but Connect is switched off. Enable it in YASTL Settings -> Connect.',
          { kind: 'disabled' },
        );
      }
      return info;
    }

    case 'get-targets': {
      const settings = await getSettings();
      return fetchTargets({
        serverUrl: msg.serverUrl || settings.serverUrl,
        token: msg.token || settings.token,
      });
    }

    case 'get-queue':
      return getQueue();

    case 'retry-capture':
      await updateCapture(msg.id, { status: 'pending', error: null });
      await runCapture(msg.id);
      return getQueue();

    case 'attribute-capture': {
      // The user picked a source page for a capture we could not correlate.
      const settings = await getSettings();
      const context = msg.tabId != null ? await getPageContext(msg.tabId) : null;
      if (!context) {
        // Uploading anyway would put the file in the library named after its
        // download URL with no title, tags or source — the exact outcome the
        // user pressed this button to avoid. Refuse and say why instead.
        throw new ConnectError(
          'No page data for that tab. The extension was probably reloaded after ' +
            'that tab was opened — reload the model page, then try again.',
        );
      }
      const metadata = await resolveMetadata(context, settings);
      await updateCapture(msg.id, {
        metadata,
        sourceUrl: context ? context.url : null,
        confidence: 'manual',
        status: 'pending',
      });
      await runCapture(msg.id);
      return getQueue();
    }

    case 'update-capture':
      await updateCapture(msg.id, msg.patch || {});
      await refreshBadge();
      return getQueue();

    case 'remove-capture':
      await removeCapture(msg.id);
      await refreshBadge();
      return getQueue();

    case 'clear-finished':
      await clearFinishedCaptures();
      await refreshBadge();
      return getQueue();

    case 'capture-current-tab': {
      // Manual capture from the popup, for a download the listener missed.
      const settings = await getSettings();
      const context = msg.tabId != null ? await getPageContext(msg.tabId) : null;
      if (!context) {
        throw new ConnectError(
          'No page data for that tab yet. Reload the model page and try again.',
        );
      }
      const metadata = await resolveMetadata(context, settings);
      const capture = await pushCapture({
        id: newCaptureId(),
        url: msg.url,
        filename: msg.filename || 'capture.stl',
        createdAt: Date.now(),
        confidence: 'manual',
        sourceUrl: context.url,
        metadata,
        libraryId: settings.libraryId,
        subfolder: settings.subfolder,
        collectionId: settings.collectionId,
        status: 'pending',
      });
      await runCapture(capture.id);
      return getQueue();
    }

    default:
      throw new Error(`Unknown message type: ${msg && msg.type}`);
  }
}

/**
 * Inject the harvester into tabs that are already open.
 *
 * Manifest-declared content scripts only run when a page loads. Installing or
 * reloading the extension therefore leaves every tab already sitting on a model
 * page with no harvester in it — and because a capture with no page context
 * still uploads the file, the result is a model in the library named after the
 * download's opaque filename with no title, tags or source URL. That is exactly
 * what happened on the first real-world capture, so this runs on install and on
 * every update.
 */
async function injectIntoOpenTabs() {
  const manifest = chrome.runtime.getManifest();
  const spec = (manifest.content_scripts || [])[0];
  if (!spec) return;

  let tabs = [];
  try {
    tabs = await chrome.tabs.query({ url: spec.matches });
  } catch (e) {
    console.warn('[YASTL] could not enumerate open tabs', e);
    return;
  }

  for (const tab of tabs) {
    if (tab.id == null) continue;
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: spec.js,
      });
      console.log('[YASTL] harvester injected into open tab:', tab.url);
    } catch (e) {
      // A discarded tab, a page still loading, or one the browser will not let
      // us touch. Its next navigation injects normally, so this is not fatal.
      console.warn('[YASTL] could not inject into tab', tab.url, e.message);
    }
  }
}

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    chrome.runtime.openOptionsPage().catch(() => {});
  }
  injectIntoOpenTabs().catch((e) => console.error('[YASTL] injection sweep failed', e));
  refreshBadge().catch(() => {});
});

chrome.runtime.onStartup.addListener(() => {
  refreshBadge().catch(() => {});
});
