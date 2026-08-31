/**
 * YASTL server client.
 *
 * Every call in here runs in the service worker and nowhere else. Content
 * scripts get no CORS exemption at all and extension pages are inconsistent
 * across builds, so the popup and options page ask the worker to make these
 * calls rather than calling fetch themselves.
 *
 * The worker is not exempt either, as far as the YASTL server is concerned —
 * that is what the CORS middleware in app/api/routes_connect.py is for. If
 * every request here fails with a CORS error while the server log shows clean
 * 200s, the server is running a build from before that middleware existed.
 */

/** The protocol version this build of the extension was written against. */
export const EXPECTED_PROTOCOL = 1;

export class ConnectError extends Error {
  constructor(message, { kind = 'error', status = null } = {}) {
    super(message);
    this.name = 'ConnectError';
    this.kind = kind; // 'unreachable' | 'disabled' | 'auth' | 'error'
    this.status = status;
  }
}

function normaliseBase(serverUrl) {
  const trimmed = (serverUrl || '').trim().replace(/\/+$/, '');
  if (!trimmed) {
    throw new ConnectError('No YASTL server address set.', { kind: 'error' });
  }
  if (!/^https?:\/\//i.test(trimmed)) {
    throw new ConnectError('Server address must start with http:// or https://', {
      kind: 'error',
    });
  }
  return trimmed;
}

async function readError(resp) {
  try {
    const body = await resp.json();
    if (body && body.detail) return body.detail;
  } catch {
    /* fall through to the status line */
  }
  return `${resp.status} ${resp.statusText}`;
}

/**
 * Handshake. Deliberately distinguishes three failure shapes, because they have
 * completely different fixes: the server is not reachable, the server is there
 * but Connect is switched off, or the build is too old for this server.
 */
export async function fetchInfo(serverUrl) {
  const base = normaliseBase(serverUrl);
  let resp;
  try {
    resp = await fetch(`${base}/api/connect/info`, { method: 'GET' });
  } catch (e) {
    // fetch() rejects identically for DNS failure, connection refused and a
    // CORS-blocked response, so the message has to name all three rather than
    // assert one. The real cause is always printed in full in the service
    // worker console; say so, because that is where the answer is.
    throw new ConnectError(
      `Could not reach ${base}. Either the address is wrong or YASTL is not ` +
        `running, or YASTL is running a build without Connect CORS support ` +
        `(the server log would show a clean 200 while this fails). Open the ` +
        `service worker console from chrome://extensions for the exact error.`,
      { kind: 'unreachable' },
    );
  }
  if (!resp.ok) {
    throw new ConnectError(await readError(resp), {
      kind: 'error',
      status: resp.status,
    });
  }
  const info = await resp.json();
  if (info.app !== 'yastl') {
    throw new ConnectError(`${base} did not answer as a YASTL server.`, {
      kind: 'error',
    });
  }
  return info;
}

export async function fetchTargets({ serverUrl, token }) {
  const base = normaliseBase(serverUrl);
  const resp = await fetch(`${base}/api/connect/targets`, {
    headers: { 'X-YASTL-Token': token || '' },
  });
  if (resp.status === 401) {
    throw new ConnectError('YASTL rejected the access token.', { kind: 'auth' });
  }
  if (resp.status === 403) {
    throw new ConnectError(await readError(resp), { kind: 'disabled' });
  }
  if (!resp.ok) {
    throw new ConnectError(await readError(resp), { status: resp.status });
  }
  return resp.json();
}

/**
 * Upload one captured file with its page metadata.
 *
 * @param {Object}  args
 * @param {Blob}    args.blob      file content, already fetched by the browser
 * @param {string}  args.filename
 * @param {Object}  args.metadata  title/description/tags/author/license/sourceUrl
 */
export async function uploadCapture({
  serverUrl,
  token,
  blob,
  filename,
  libraryId,
  subfolder,
  collectionId,
  metadata = {},
}) {
  const base = normaliseBase(serverUrl);

  const form = new FormData();
  form.append('file', blob, filename);
  form.append('library_id', String(libraryId));
  if (subfolder) form.append('subfolder', subfolder);
  if (collectionId) form.append('collection_id', String(collectionId));
  if (metadata.title) form.append('name', metadata.title);
  if (metadata.description) form.append('description', metadata.description);
  if (metadata.sourceUrl) form.append('source_url', metadata.sourceUrl);
  if (metadata.author) form.append('author', metadata.author);
  if (metadata.license) form.append('license', metadata.license);
  if (metadata.tags && metadata.tags.length) {
    form.append('tags', metadata.tags.join(','));
  }

  const resp = await fetch(`${base}/api/connect/capture`, {
    method: 'POST',
    headers: { 'X-YASTL-Token': token || '' },
    body: form,
  });

  if (resp.status === 401) {
    throw new ConnectError('YASTL rejected the access token.', { kind: 'auth' });
  }
  if (resp.status === 403) {
    throw new ConnectError(await readError(resp), { kind: 'disabled' });
  }
  if (!resp.ok) {
    throw new ConnectError(await readError(resp), { status: resp.status });
  }
  return resp.json();
}

/**
 * Ask YASTL to scrape a source page with its own site scrapers.
 *
 * This is why the extension does not reimplement six site scrapers in
 * JavaScript. Where the server already speaks a site's API (Printables GraphQL,
 * Thingiverse and MakerWorld REST) its metadata is structured and correct, and
 * the DOM harvest is only a fallback. Best effort — a failure here costs a few
 * tags, not the capture.
 */
export async function previewSource(serverUrl, url) {
  const base = normaliseBase(serverUrl);
  try {
    const resp = await fetch(`${base}/api/import/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}
