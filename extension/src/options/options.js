/**
 * Options page.
 *
 * Every network call is delegated to the service worker. An extension page can
 * appear to reach a cross-origin server directly on some Chrome builds and be
 * blocked on others; routing through the worker, which holds the host
 * permission, is the behaviour that is actually specified.
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

function showStatus(el, message, tone = 'ok') {
  el.textContent = message;
  el.className = `status show ${tone}`;
}

function fillSelect(select, items, { valueKey, labelKey, emptyLabel, selected }) {
  select.innerHTML = '';
  if (emptyLabel) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = emptyLabel;
    select.append(opt);
  }
  for (const item of items) {
    const opt = document.createElement('option');
    opt.value = String(item[valueKey]);
    opt.textContent = labelKey(item);
    select.append(opt);
  }
  select.value = selected != null ? String(selected) : '';
  // A stored id that no longer exists on the server would leave the select
  // showing nothing at all; fall back to the placeholder instead.
  if (select.selectedIndex === -1) select.selectedIndex = 0;
}

async function loadTargets({ quiet = false } = {}) {
  const settings = await send({ type: 'get-settings' });
  try {
    const targets = await send({
      type: 'get-targets',
      serverUrl: $('serverUrl').value,
      token: $('token').value,
    });
    fillSelect($('libraryId'), targets.libraries, {
      valueKey: 'id',
      labelKey: (l) => `${l.name} — ${l.model_count} models`,
      emptyLabel: 'Choose a library…',
      selected: settings.libraryId,
    });
    fillSelect($('collectionId'), targets.collections, {
      valueKey: 'id',
      labelKey: (c) => c.name,
      emptyLabel: 'None',
      selected: settings.collectionId,
    });
    return targets;
  } catch (e) {
    if (!quiet) showStatus($('testStatus'), e.message, 'err');
    return null;
  }
}

async function restore() {
  const settings = await send({ type: 'get-settings' });
  $('serverUrl').value = settings.serverUrl || '';
  $('token').value = settings.token || '';
  $('subfolder').value = settings.subfolder || '';
  $('captureMode').value = settings.captureMode || 'copy';
  $('autoCapture').checked = settings.autoCapture !== false;
  $('notifyOnCapture').checked = settings.notifyOnCapture !== false;

  if (settings.serverUrl && settings.token) await loadTargets({ quiet: true });
}

async function save() {
  const patch = {
    serverUrl: $('serverUrl').value.trim().replace(/\/+$/, ''),
    token: $('token').value.trim(),
    subfolder: $('subfolder').value.trim(),
    captureMode: $('captureMode').value,
    autoCapture: $('autoCapture').checked,
    notifyOnCapture: $('notifyOnCapture').checked,
    libraryId: $('libraryId').value ? Number($('libraryId').value) : null,
    collectionId: $('collectionId').value ? Number($('collectionId').value) : null,
  };
  await send({ type: 'set-settings', patch });
  $('saveStatus').textContent = 'Saved.';
  setTimeout(() => ($('saveStatus').textContent = ''), 2500);
}

/**
 * Tell the user when the server has a newer extension than the one they loaded.
 *
 * An unpacked extension has no auto-update path whatsoever — the browser reads
 * whatever is on disk and never checks anywhere. Without this, a stale copy
 * keeps running indefinitely and its bugs look like server bugs.
 */
function showUpdateNotice(info) {
  const el = $('updateNotice');
  const installed = chrome.runtime.getManifest().version;
  const offered = info && info.extension_version;
  if (!offered || offered === installed) {
    el.hidden = true;
    return;
  }

  const base = $('serverUrl').value.trim().replace(/\/+$/, '');
  el.innerHTML = '';
  const text = document.createElement('span');
  text.textContent =
    `This server offers YASTL Connect ${offered}; you have ${installed}. ` +
    'Download it, replace the folder you loaded, then reload the extension ' +
    'at chrome://extensions and reload any model pages you have open. ';
  const link = document.createElement('a');
  link.href = `${base}${info.extension_download || '/api/connect/extension.zip'}`;
  link.textContent = `Download ${offered}`;
  link.target = '_blank';
  link.rel = 'noreferrer';
  el.append(text, link);
  el.hidden = false;
}

$('test').addEventListener('click', async () => {
  const button = $('test');
  button.disabled = true;
  showStatus($('testStatus'), 'Connecting…', 'ok');
  try {
    const info = await send({
      type: 'test-connection',
      serverUrl: $('serverUrl').value.trim(),
    });
    showUpdateNotice(info);
    // Persist before loading targets so the worker uses the address just typed.
    await send({
      type: 'set-settings',
      patch: {
        serverUrl: $('serverUrl').value.trim().replace(/\/+$/, ''),
        token: $('token').value.trim(),
      },
    });
    const targets = await loadTargets();
    if (targets) {
      const count = targets.libraries.length;
      showStatus(
        $('testStatus'),
        count
          ? `Connected. ${count} librar${count === 1 ? 'y' : 'ies'} available.`
          : 'Connected, but YASTL has no libraries yet. Add one in YASTL Settings.',
        count ? 'ok' : 'warn',
      );
    }
  } catch (e) {
    showStatus($('testStatus'), e.message, e.kind === 'disabled' ? 'warn' : 'err');
  } finally {
    button.disabled = false;
  }
});

$('grant').addEventListener('click', async () => {
  // Must run inside the click handler: Chrome only honours a permission
  // request that originates from a user gesture, and awaiting anything first
  // loses it.
  try {
    const granted = await chrome.permissions.request({ origins: ['*://*/*'] });
    showStatus(
      $('testStatus'),
      granted
        ? 'Site access granted. Downloads that redirect to a CDN will now work.'
        : 'Site access declined. Captures may fail on sites that redirect downloads to a CDN.',
      granted ? 'ok' : 'warn',
    );
  } catch (e) {
    showStatus($('testStatus'), e.message, 'err');
  }
});

$('reveal').addEventListener('click', () => {
  const field = $('token');
  const hidden = field.type === 'password';
  field.type = hidden ? 'text' : 'password';
  $('reveal').textContent = hidden ? 'Hide' : 'Show';
});

$('save').addEventListener('click', () => {
  save().catch((e) => showStatus($('testStatus'), e.message, 'err'));
});

restore().catch((e) => showStatus($('testStatus'), e.message, 'err'));
