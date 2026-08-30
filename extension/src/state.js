/**
 * Storage wrappers and the capture queue.
 *
 * Nothing here may be cached in a module-level variable. Chrome kills an MV3
 * service worker after roughly 30 seconds of inactivity and every module is
 * re-evaluated from scratch on the next event, so anything held in memory is
 * silently lost between a download starting and finishing. All state lives in
 * chrome.storage.
 *
 *   sync   - user settings, so they follow a signed-in profile between machines
 *   local  - the capture queue, which must survive the worker being recycled
 *   session- harvested page context, which is worthless after a browser restart
 */

const SETTINGS_DEFAULTS = {
  serverUrl: '',
  token: '',
  libraryId: null,
  subfolder: '',
  collectionId: null,
  // 'copy'      - let the browser finish its download, then re-fetch to upload.
  //               The user keeps their file whatever happens on our side.
  // 'intercept' - cancel the browser download and fetch once ourselves. Needed
  //               for sites that issue single-use presigned URLs.
  captureMode: 'copy',
  notifyOnCapture: true,
  autoCapture: true,
};

export async function getSettings() {
  const stored = await chrome.storage.sync.get(SETTINGS_DEFAULTS);
  return { ...SETTINGS_DEFAULTS, ...stored };
}

export async function setSettings(patch) {
  await chrome.storage.sync.set(patch);
  return getSettings();
}

// ---------------------------------------------------------------------------
// Harvested page context, keyed by tab id
// ---------------------------------------------------------------------------

const PAGE_PREFIX = 'page:';

export async function putPageContext(tabId, context) {
  await chrome.storage.session.set({
    [PAGE_PREFIX + tabId]: { ...context, tabId, capturedAt: Date.now() },
  });
}

export async function getPageContext(tabId) {
  const key = PAGE_PREFIX + tabId;
  const bag = await chrome.storage.session.get(key);
  return bag[key] || null;
}

export async function dropPageContext(tabId) {
  await chrome.storage.session.remove(PAGE_PREFIX + tabId);
}

/** Every cached page context, newest first. Used for referrer correlation. */
export async function allPageContexts() {
  const bag = await chrome.storage.session.get(null);
  return Object.entries(bag)
    .filter(([key]) => key.startsWith(PAGE_PREFIX))
    .map(([, value]) => value)
    .sort((a, b) => (b.capturedAt || 0) - (a.capturedAt || 0));
}

// ---------------------------------------------------------------------------
// Capture queue
// ---------------------------------------------------------------------------

const QUEUE_KEY = 'captureQueue';
const QUEUE_LIMIT = 50;

/**
 * A capture moves through: pending -> uploading -> done | failed | needs-page.
 *
 * 'needs-page' means the file was captured but could not be matched to a source
 * page, so it is waiting for the user to attribute it in the popup. It is a
 * deliberate resting state, not an error.
 */
export async function getQueue() {
  const { [QUEUE_KEY]: queue } = await chrome.storage.local.get(QUEUE_KEY);
  return Array.isArray(queue) ? queue : [];
}

export async function pushCapture(capture) {
  const queue = await getQueue();
  queue.unshift(capture);
  await chrome.storage.local.set({ [QUEUE_KEY]: queue.slice(0, QUEUE_LIMIT) });
  return capture;
}

export async function updateCapture(id, patch) {
  const queue = await getQueue();
  const next = queue.map((c) => (c.id === id ? { ...c, ...patch } : c));
  await chrome.storage.local.set({ [QUEUE_KEY]: next });
  return next.find((c) => c.id === id) || null;
}

export async function removeCapture(id) {
  const queue = await getQueue();
  await chrome.storage.local.set({
    [QUEUE_KEY]: queue.filter((c) => c.id !== id),
  });
}

export async function clearFinishedCaptures() {
  const queue = await getQueue();
  await chrome.storage.local.set({
    [QUEUE_KEY]: queue.filter((c) => c.status !== 'done'),
  });
}

export function newCaptureId() {
  return `cap_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}
