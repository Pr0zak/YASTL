/**
 * Turn a raw page harvest into structured model metadata.
 *
 * Every function here is pure: harvested bag in, metadata out, no browser APIs
 * touched. That is deliberate — it means the fragile, site-specific half of the
 * extension can be exercised in Node without a browser (see
 * tests/sites.test.mjs).
 *
 * Precedence, weakest first, each layer only filling gaps the previous left:
 *
 *   1. Open Graph / standard meta tags — near-universal, survives redesigns.
 *   2. JSON-LD — structured, and where sites declare licence and author.
 *   3. Per-site DOM selectors — richest, rots fastest.
 *   4. The server's own API scrapers, merged in by the caller. Highest quality
 *      where available, which is why it wins outright.
 */

/** Hosts YASTL's own Python scrapers already understand. */
export const SERVER_SCRAPED_HOSTS = [
  'thingiverse.com',
  'makerworld.com',
  'printables.com',
  'myminifactory.com',
  'cults3d.com',
  'thangs.com',
];

export function hostSlug(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

export function isServerScraped(url) {
  const host = hostSlug(url);
  return SERVER_SCRAPED_HOSTS.some((h) => host.endsWith(h));
}


/**
 * Does this URL look like a model's own page?
 *
 * The harvester runs on every page of a supported site, which includes search
 * results, profiles and browsing history. Storing context for those is what let
 * a capture be attributed to a page called "ProZac | Visit History" — the
 * download's referrer gave nothing usable, correlation fell back to the most
 * recent page seen, and that was a history page rather than the model.
 *
 * So only model pages are worth remembering. Patterns are kept loose about
 * locale prefixes and trailing slugs, which vary, and strict about the shape
 * that identifies a model.
 */
const MODEL_PAGE_PATTERNS = [
  ['printables.com', /\/model\/\d+/],
  ['thingiverse.com', /\/thing:\d+/],
  ['makerworld.com', /\/models\/\d+/],
  ['myminifactory.com', /\/object\//],
  ['cults3d.com', /\/3d-model\//],
  ['thangs.com', /\/3d-model\/|\/m\/\d+/],
];

export function isModelPage(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  const host = parsed.hostname.replace(/^www\./, '');
  const path = parsed.pathname;

  for (const [suffix, pattern] of MODEL_PAGE_PATTERNS) {
    if (host.endsWith(suffix)) return pattern.test(path);
  }
  // An unrecognised host gets the benefit of the doubt: the user may be on a
  // site we have no rules for, and a bad title beats no capture at all.
  return true;
}

/** A short site tag, so captures are filterable by origin in YASTL. */
export function siteTag(url) {
  const host = hostSlug(url);
  const match = SERVER_SCRAPED_HOSTS.find((h) => host.endsWith(h));
  return match ? match.replace(/\.com$/, '') : null;
}

/**
 * Licence strings arrive in two dialects for the same licence: Printables and
 * MakerWorld use the abbreviations ("CC-BY-NC-SA"), Thingiverse spells them out
 * ("Creative Commons - Attribution - Non-Commercial - Share Alike"). Matching a
 * flat list of patterns gets this wrong in a way that matters — a loose CC-BY
 * pattern hits inside "CC-BY-NC-SA" and silently downgrades a NonCommercial
 * licence to plain attribution. So detect the clauses and rebuild the name.
 */
const CC_CLAUSES = [
  ['nc', /non[\s-]?commercial|\bNC\b/i],
  ['nd', /no[\s-]?deriv\w*|\bND\b/i],
  ['sa', /share[\s-]?alike|\bSA\b/i],
  ['by', /attribution|\bBY\b/i],
];

const OTHER_LICENSES = [
  [/\bLGPL\b/i, 'LGPL'],
  [/\bA?GPL\b|GNU\s*[-–]?\s*GPL|General\s+Public\s+License/i, 'GPL'],
  [/\bMIT\b/, 'MIT'],
  [/\bBSD\b/i, 'BSD'],
  [/\bApache\b/i, 'Apache-2.0'],
  [/all\s+rights\s+reserved/i, 'All Rights Reserved'],
];

/** Reduce a licence string or URL to a short canonical name. */
export function normaliseLicense(raw) {
  if (!raw) return null;
  const text = String(raw).trim();
  if (!text) return null;

  // Public domain first: "Creative Commons - Public Domain Dedication" is CC0,
  // and would otherwise be read as an ordinary Creative Commons licence.
  if (/\bCC0\b|public\s+domain|zero\s+licen[cs]e/i.test(text)) return 'CC0';

  // A creativecommons.org URL states the clauses in its path unambiguously.
  const url = text.match(/creativecommons\.org\/licenses\/([a-z-]+)/i);
  const scope = url ? url[1] : text;

  const isCC = url || /creative\s*commons|\bCC[\s-]?BY\b|\bCC\b/i.test(text);
  if (isCC) {
    const has = {};
    for (const [key, pattern] of CC_CLAUSES) has[key] = pattern.test(scope);
    // Every modern CC licence except CC0 includes attribution, so treat a
    // recognised CC licence with no explicit clause as BY rather than nothing.
    if (has.by || has.nc || has.nd || has.sa) {
      let name = 'CC-BY';
      if (has.nc) name += '-NC';
      if (has.nd) name += '-ND';
      else if (has.sa) name += '-SA';
      return name;
    }
  }

  for (const [pattern, name] of OTHER_LICENSES) {
    if (pattern.test(text)) return name;
  }

  return text.length <= 60 ? text : null;
}

function textOf(value) {
  if (!value) return null;
  if (typeof value === 'string') return value.trim() || null;
  if (Array.isArray(value)) return textOf(value[0]);
  if (typeof value === 'object') return textOf(value.name || value['@value']);
  return null;
}

/** Strip HTML and collapse whitespace; descriptions arrive in both forms. */
export function cleanText(raw, limit = 8000) {
  if (!raw) return null;
  const text = String(raw)
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  return text ? text.slice(0, limit) : null;
}

/**
 * Tags arrive as free text from three sources and go straight into a shared
 * vocabulary, so they get normalised hard: lowercased, spaces to hyphens, no
 * punctuation, length-bounded. Without this the tag list fills with
 * near-duplicates like "Low Poly", "low-poly" and "low poly!".
 */
export function normaliseTags(raw) {
  const out = [];
  for (const item of raw || []) {
    const tag = String(item || '')
      .trim()
      .toLowerCase()
      .replace(/^#/, '')
      .replace(/[^\w\s:-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-{2,}/g, '-')
      .replace(/^-|-$/g, '');
    if (tag.length < 2 || tag.length > 40) continue;
    if (!out.includes(tag)) out.push(tag);
    if (out.length >= 25) break;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Layers
// ---------------------------------------------------------------------------

function fromMeta(meta = {}) {
  return {
    title: textOf(meta['og:title'] || meta['twitter:title'] || null),
    description: cleanText(
      meta['og:description'] || meta.description || meta['twitter:description'],
    ),
    thumbnail: textOf(meta['og:image'] || meta['twitter:image'] || null),
    author: textOf(meta['author'] || meta['article:author'] || null),
    tags: normaliseTags(
      (meta['keywords'] || meta['article:tag'] || '')
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    ),
    license: normaliseLicense(meta['license'] || null),
  };
}

function fromJsonLd(blocks = []) {
  const out = { title: null, description: null, author: null, tags: [], license: null };
  for (const node of blocks) {
    if (!node || typeof node !== 'object') continue;
    const type = String(node['@type'] || '').toLowerCase();
    // Breadcrumbs and site-wide Organization nodes describe the site, not the
    // model, and would otherwise overwrite the title with the site name.
    if (type.includes('breadcrumb') || type === 'organization' || type === 'website') {
      continue;
    }
    out.title = out.title || textOf(node.name || node.headline);
    out.description = out.description || cleanText(node.description);
    out.author = out.author || textOf(node.author || node.creator);
    out.license = out.license || normaliseLicense(node.license);
    if (node.keywords) {
      const raw = Array.isArray(node.keywords)
        ? node.keywords
        : String(node.keywords).split(',');
      out.tags = out.tags.length ? out.tags : normaliseTags(raw);
    }
  }
  return out;
}

function fromDom(dom = {}) {
  return {
    title: null,
    description: cleanText(dom.description),
    author: textOf(dom.author),
    tags: normaliseTags(dom.tags),
    license: null,
  };
}

/** Fill each empty field from the first later layer that has one. */
function coalesce(layers) {
  const out = {
    title: null,
    description: null,
    author: null,
    license: null,
    thumbnail: null,
    tags: [],
  };
  for (const layer of layers) {
    if (!layer) continue;
    for (const key of ['title', 'description', 'author', 'license', 'thumbnail']) {
      if (!out[key] && layer[key]) out[key] = layer[key];
    }
    for (const tag of layer.tags || []) {
      if (!out.tags.includes(tag)) out.tags.push(tag);
    }
  }
  out.tags = out.tags.slice(0, 25);
  return out;
}

/**
 * Build metadata from a harvested page context.
 *
 * @param {Object} context  the payload content.js sent
 * @param {Object} [server] optional `/api/import/preview` response, which wins
 */
export function buildMetadata(context, server = null) {
  if (!context) return { tags: [] };

  const layers = [
    // Server first: where it has a site API, its answer is the good one.
    server
      ? {
          title: textOf(server.title),
          description: cleanText(server.description),
          tags: normaliseTags(server.tags || []),
          author: null,
          license: null,
          thumbnail: null,
        }
      : null,
    fromJsonLd(context.jsonLd),
    fromMeta(context.meta),
    fromDom(context.dom),
  ];

  const merged = coalesce(layers);

  // og:title is routinely "Model name | Printables.com". The site half is
  // noise and would end up as the model's name in the library.
  if (merged.title) {
    merged.title = merged.title
      .replace(/\s*[|–—-]\s*(Printables|Thingiverse|MakerWorld|Thangs|MyMiniFactory|Cults3D)\b.*$/i, '')
      .trim();
  }

  const tag = siteTag(context.url);
  if (tag && !merged.tags.includes(tag)) merged.tags.unshift(tag);

  return {
    ...merged,
    sourceUrl: context.url || null,
    gallery: context.gallery || [],
  };
}

/**
 * Choose the filename a capture is stored under.
 *
 * Sites increasingly serve downloads from opaque URLs — MakerWorld hands out
 * `<uuid>.3mf` — which leaves a library full of files nobody can identify on
 * disk. When the page gave us a title, use that and keep the real extension.
 * With no title we have nothing better than what the download was called.
 */
export function storageFilename(originalName, title) {
  const original = originalName || 'capture.stl';
  if (!title) return original;

  const match = /(\.[a-z0-9]+)$/i.exec(original);
  const ext = match ? match[1].toLowerCase() : '';
  const stem = String(title)
    .trim()
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, '_')
    .replace(/\s+/g, ' ')
    .slice(0, 120)
    .trim()
    .replace(/[. ]+$/, '');
  return stem ? `${stem}${ext}` : original;
}
