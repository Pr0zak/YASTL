/**
 * Page harvester — deliberately dumb.
 *
 * This script does no interpretation. It scrapes every plausible metadata
 * source out of the DOM and ships the raw bag to the service worker, where
 * sites.js turns it into something structured. Two reasons for the split:
 *
 *   1. Manifest V3 does not support ES modules in manifest-declared content
 *      scripts, so anything living here has to be one import-free file. The
 *      normalizers are far easier to maintain — and to unit-test in Node — as
 *      a module in the worker.
 *   2. Sites rewrite their markup constantly. Keeping the fragile part in one
 *      place, behind a stable payload shape, means a site redesign is a small
 *      edit rather than a rewrite.
 *
 * Runs in the isolated world, so page JavaScript globals are unreachable.
 * Everything below reads the DOM only.
 */

(() => {
  'use strict';

  const MAX_GALLERY = 12;
  const MAX_DESCRIPTION = 8000;

  function metaTags() {
    const out = {};
    for (const el of document.querySelectorAll('meta[property], meta[name]')) {
      const key = el.getAttribute('property') || el.getAttribute('name');
      const value = el.getAttribute('content');
      if (key && value && !(key in out)) out[key] = value;
    }
    return out;
  }

  function jsonLdBlocks() {
    const out = [];
    for (const el of document.querySelectorAll(
      'script[type="application/ld+json"]',
    )) {
      try {
        const parsed = JSON.parse(el.textContent || '');
        // A @graph wrapper is common; flatten it so consumers see plain nodes.
        if (parsed && Array.isArray(parsed['@graph'])) out.push(...parsed['@graph']);
        else if (Array.isArray(parsed)) out.push(...parsed);
        else if (parsed) out.push(parsed);
      } catch {
        /* malformed JSON-LD is common in the wild; skip it silently */
      }
    }
    return out;
  }

  /**
   * Next.js and Nuxt embed the whole page model as JSON in a script tag.
   * Reading it from the DOM works from the isolated world, where the
   * corresponding window globals would not.
   */
  function embeddedState() {
    const out = {};
    const next = document.getElementById('__NEXT_DATA__');
    if (next && next.textContent) {
      try {
        out.next = JSON.parse(next.textContent);
      } catch {
        /* ignore */
      }
    }
    for (const el of document.querySelectorAll('script[type="application/json"]')) {
      const id = el.id || '';
      if (!id || id === '__NEXT_DATA__') continue;
      try {
        out[id] = JSON.parse(el.textContent || '');
      } catch {
        /* ignore */
      }
    }
    return out;
  }

  function galleryImages() {
    const urls = new Set();
    const og = document.querySelector('meta[property="og:image"]');
    if (og && og.content) urls.add(og.content);

    for (const img of document.querySelectorAll('img')) {
      const src = img.currentSrc || img.src;
      if (!src || src.startsWith('data:')) continue;
      // Thumbnails and avatars are noise; only keep images rendered at a size
      // that suggests they are actual model photos.
      const w = img.naturalWidth || img.width || 0;
      const h = img.naturalHeight || img.height || 0;
      if (w < 200 || h < 200) continue;
      urls.add(src);
      if (urls.size >= MAX_GALLERY) break;
    }
    return [...urls];
  }

  function visibleText(selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      const text = el && el.innerText && el.innerText.trim();
      if (text) return text.slice(0, MAX_DESCRIPTION);
    }
    return null;
  }

  /**
   * Per-site DOM selectors. These are the part that rots when a site
   * redesigns, which is exactly why they are a bonus layer: everything they
   * provide is also attempted from Open Graph and JSON-LD, so a stale selector
   * degrades a capture to "fewer tags" rather than breaking it.
   */
  const SELECTORS = {
    'printables.com': {
      description: ['#description', '[class*="description"]'],
      tags: ['a[href*="/model-tags/"]', 'a[href*="/tag/"]'],
      author: ['a[href^="/@"]', '[class*="user-name"]'],
    },
    'thingiverse.com': {
      description: ['[class*="ThingPage__description"]', '#description'],
      tags: ['a[href*="/tag:"]'],
      author: ['[class*="DesignerHeader__name"]', 'a[href^="/thing:"] + a'],
    },
    'makerworld.com': {
      description: ['[class*="detail-description"]', '[class*="description"]'],
      tags: ['a[href*="/tag/"]', '[class*="tag-item"]'],
      author: ['[class*="designer-name"]', '[class*="user-name"]'],
    },
    'myminifactory.com': {
      description: ['#object-description', '[class*="description"]'],
      tags: ['a[href*="/search?tag"]', 'a[href*="/tag/"]'],
      author: ['a[href*="/users/"]'],
    },
    'cults3d.com': {
      description: ['.text-content', '[class*="description"]'],
      tags: ['a[href*="/tags/"]'],
      author: ['a[href*="/users/"]'],
    },
    'thangs.com': {
      description: ['[class*="description"]'],
      tags: ['[class*="tag"]'],
      author: ['a[href*="/designer/"]'],
    },
  };

  function siteKey() {
    const host = location.hostname.replace(/^www\./, '');
    return Object.keys(SELECTORS).find((k) => host.endsWith(k)) || null;
  }

  function domHarvest() {
    const key = siteKey();
    if (!key) return {};
    const rules = SELECTORS[key];

    const tags = [];
    for (const sel of rules.tags || []) {
      for (const el of document.querySelectorAll(sel)) {
        const text = (el.innerText || '').trim();
        if (text && text.length <= 40 && !tags.includes(text)) tags.push(text);
        if (tags.length >= 25) break;
      }
      if (tags.length) break;
    }

    return {
      siteKey: key,
      description: visibleText(rules.description || []),
      author: visibleText(rules.author || []),
      tags,
    };
  }

  function buildContext() {
    return {
      url: location.href,
      host: location.hostname,
      title: document.title || null,
      meta: metaTags(),
      jsonLd: jsonLdBlocks(),
      embedded: embeddedState(),
      gallery: galleryImages(),
      dom: domHarvest(),
    };
  }

  function send() {
    try {
      chrome.runtime.sendMessage({ type: 'page-context', context: buildContext() });
    } catch {
      // The worker may be mid-restart, or the extension was just reloaded.
      // The next navigation will send again; nothing here is worth retrying.
    }
  }

  send();

  // Every one of these sites is a single-page app, so a click through to
  // another model fires no page load. Watch for the URL changing instead, and
  // debounce because a route change churns the DOM for a while afterwards.
  let lastUrl = location.href;
  let pending = null;
  new MutationObserver(() => {
    if (location.href === lastUrl) return;
    lastUrl = location.href;
    clearTimeout(pending);
    pending = setTimeout(send, 900);
  }).observe(document.documentElement, { subtree: true, childList: true });
})();
