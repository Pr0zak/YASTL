/**
 * Toolbar popup: destination picker plus the capture queue.
 *
 * Like the options page, this never fetches the server directly — it messages
 * the service worker, which holds the host permissions.
 */

const $ = (id) => document.getElementById(id);

function send(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (reply) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
      } else if (!reply || !reply.ok) {
        const err = new Error((reply && reply.error) || 'Unknown error');
        err.kind = reply && reply.kind;
        reject(err);
      } else {
        resolve(reply.data);
      }
    });
  });
}

function showStatus(message, tone = 'err') {
  const el = $('status');
  if (!message) {
    el.className = 'status';
    el.textContent = '';
    return;
  }
  el.textContent = message;
  el.className = `status show ${tone}`;
}

function relativeTime(ts) {
  const seconds = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

function formatSize(bytes) {
  if (!bytes) return null;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * The status word is always written out, never signalled by the stripe colour
 * alone — the stripe is a scanning aid, not the information itself.
 */
const STATUS_LABEL = {
  pending: 'Waiting for the download',
  uploading: 'Uploading',
  done: 'In your library',
  failed: 'Failed',
  'needs-page': 'No source page found',
};

function captureRow(capture, activeTabId) {
  const li = document.createElement('li');
  li.className = `capture ${capture.status}`;

  const stripe = document.createElement('div');
  stripe.className = 'stripe';

  const body = document.createElement('div');
  body.className = 'body';

  const title = document.createElement('div');
  title.className = 'title';
  title.textContent =
    (capture.metadata && capture.metadata.title) || capture.filename;
  title.title = capture.filename;

  const meta = document.createElement('div');
  meta.className = 'meta';
  const bits = [STATUS_LABEL[capture.status] || capture.status];
  if (capture.status === 'done' && capture.size) bits.push(formatSize(capture.size));
  if (capture.sourceUrl) {
    try {
      bits.push(new URL(capture.sourceUrl).hostname.replace(/^www\./, ''));
    } catch {
      /* ignore */
    }
  }
  bits.push(relativeTime(capture.createdAt));
  meta.textContent = bits.join(' · ');

  body.append(title, meta);

  if (capture.error) {
    const error = document.createElement('div');
    error.className = 'error';
    error.textContent = capture.error;
    body.append(error);
  }

  const tags = (capture.metadata && capture.metadata.tags) || [];
  if (tags.length) {
    const wrap = document.createElement('div');
    wrap.className = 'tags';
    for (const tag of tags.slice(0, 6)) {
      const chip = document.createElement('span');
      chip.className = 'tag';
      chip.textContent = tag;
      wrap.append(chip);
    }
    body.append(wrap);
  }

  const actions = document.createElement('div');
  actions.className = 'actions';

  if (capture.status === 'failed') {
    const retry = document.createElement('button');
    retry.className = 'secondary';
    retry.textContent = 'Retry';
    retry.addEventListener('click', () => act({ type: 'retry-capture', id: capture.id }));
    actions.append(retry);
  }

  if (capture.status === 'needs-page') {
    // We have the file but not the page it came from. Attributing it to the
    // tab the user is looking at is the common case by a wide margin.
    const use = document.createElement('button');
    use.textContent = 'Use this tab';
    use.disabled = activeTabId == null;
    use.title = 'Take the metadata from the page in the active tab';
    use.addEventListener('click', () =>
      act({ type: 'attribute-capture', id: capture.id, tabId: activeTabId }),
    );
    actions.append(use);
  }

  const remove = document.createElement('button');
  remove.className = 'ghost';
  remove.textContent = 'Dismiss';
  remove.addEventListener('click', () => act({ type: 'remove-capture', id: capture.id }));
  actions.append(remove);

  li.append(stripe, body, actions);
  return li;
}

let activeTabId = null;

async function act(message) {
  try {
    const queue = await send(message);
    renderQueue(queue);
    showStatus('');
  } catch (e) {
    showStatus(e.message);
  }
}

function renderQueue(queue) {
  const list = $('queue');
  list.innerHTML = '';
  for (const capture of queue) list.append(captureRow(capture, activeTabId));
  $('empty').hidden = queue.length > 0;
}

async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  activeTabId = tab ? tab.id : null;

  const settings = await send({ type: 'get-settings' });
  const configured = Boolean(settings.serverUrl && settings.token);

  $('setupNeeded').hidden = configured;
  $('main').hidden = !configured;
  if (!configured) return;

  $('subfolder').value = settings.subfolder || '';

  // Populate the library picker from the server, but do not let an unreachable
  // server hide the queue — captures are still worth showing and dismissing.
  try {
    const targets = await send({ type: 'get-targets' });
    const select = $('libraryId');
    select.innerHTML = '';
    for (const library of targets.libraries) {
      const opt = document.createElement('option');
      opt.value = String(library.id);
      opt.textContent = library.name;
      select.append(opt);
    }
    select.value = String(settings.libraryId ?? '');
    if (select.selectedIndex === -1) select.selectedIndex = 0;
  } catch (e) {
    showStatus(e.message, e.kind === 'disabled' ? 'warn' : 'err');
  }

  renderQueue(await send({ type: 'get-queue' }));
}

$('libraryId').addEventListener('change', async (e) => {
  await send({
    type: 'set-settings',
    patch: { libraryId: e.target.value ? Number(e.target.value) : null },
  });
});

$('subfolder').addEventListener('change', async (e) => {
  await send({ type: 'set-settings', patch: { subfolder: e.target.value.trim() } });
});

$('clearFinished').addEventListener('click', () => act({ type: 'clear-finished' }));
$('openOptions').addEventListener('click', () => chrome.runtime.openOptionsPage());
$('goToOptions').addEventListener('click', () => chrome.runtime.openOptionsPage());

// The queue changes while the popup is open — an upload finishing, a capture
// failing — so mirror storage rather than showing a snapshot from open time.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.captureQueue) {
    renderQueue(changes.captureQueue.newValue || []);
  }
});

init().catch((e) => showStatus(e.message));
