/**
 * Unit tests for the metadata normalizers.
 *
 * Run with: node --test extension/tests/
 *
 * sites.js is pure by design so this needs no browser and no fixtures beyond
 * the harvest payloads below, which are trimmed copies of what content.js
 * actually produces on each site.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildMetadata,
  cleanText,
  hostSlug,
  isModelPage,
  isServerScraped,
  normaliseLicense,
  normaliseTags,
  siteTag,
  storageFilename,
} from '../src/sites.js';

test('hostSlug strips the www prefix', () => {
  assert.equal(hostSlug('https://www.printables.com/model/1'), 'printables.com');
  assert.equal(hostSlug('https://thingiverse.com/thing:1'), 'thingiverse.com');
  assert.equal(hostSlug('not a url'), '');
});

test('isServerScraped recognises the sites YASTL already scrapes', () => {
  assert.ok(isServerScraped('https://www.printables.com/model/1'));
  assert.ok(isServerScraped('https://www.thingiverse.com/thing:1'));
  assert.ok(!isServerScraped('https://example.com/model.stl'));
});

test('siteTag gives a short origin tag', () => {
  assert.equal(siteTag('https://www.printables.com/model/1'), 'printables');
  assert.equal(siteTag('https://makerworld.com/en/models/2'), 'makerworld');
  assert.equal(siteTag('https://example.com/x'), null);
});

test('normaliseTags folds near-duplicates into one tag', () => {
  const tags = normaliseTags(['Low Poly', 'low-poly', 'low poly!', '#Dragon']);
  assert.deepEqual(tags, ['low-poly', 'dragon']);
});

test('normaliseTags drops tags that are too short or too long', () => {
  const tags = normaliseTags(['a', 'ok', 'x'.repeat(60)]);
  assert.deepEqual(tags, ['ok']);
});

test('normaliseTags preserves a namespace colon', () => {
  // YASTL treats "namespace:value" as a display convention (frontend/src/tags.js),
  // so the colon has to survive normalisation.
  assert.deepEqual(normaliseTags(['author:Someone']), ['author:someone']);
});

test('normaliseLicense canonicalises the common Creative Commons forms', () => {
  assert.equal(normaliseLicense('Creative Commons - Attribution'), 'CC-BY');
  assert.equal(normaliseLicense('CC BY-NC-SA 4.0'), 'CC-BY-NC-SA');
  assert.equal(normaliseLicense('Public Domain'), 'CC0');
  assert.equal(
    normaliseLicense('https://creativecommons.org/licenses/by-sa/4.0/'),
    'CC-BY-SA',
  );
  assert.equal(normaliseLicense(null), null);
});

test('normaliseLicense prefers the more specific variant', () => {
  // "CC-BY-NC-SA" contains "CC-BY"; matching the loose pattern first would
  // silently downgrade a NonCommercial licence to plain attribution.
  assert.equal(normaliseLicense('CC-BY-NC-SA'), 'CC-BY-NC-SA');
  assert.equal(normaliseLicense('CC-BY-SA'), 'CC-BY-SA');
});

test('cleanText strips markup and collapses whitespace', () => {
  const html = '<p>First   line</p><p>Second &amp; third</p>';
  assert.equal(cleanText(html), 'First line\n\nSecond & third');
});

test('cleanText respects the length limit', () => {
  assert.equal(cleanText('x'.repeat(100), 10).length, 10);
});

// ---------------------------------------------------------------------------
// buildMetadata
// ---------------------------------------------------------------------------

const PRINTABLES_HARVEST = {
  url: 'https://www.printables.com/model/12345-cable-clip',
  host: 'www.printables.com',
  title: 'Cable Clip | Printables.com',
  meta: {
    'og:title': 'Cable Clip | Printables.com',
    'og:description': 'A simple clip for routing cables.',
    'og:image': 'https://media.printables.com/thumb.png',
  },
  jsonLd: [
    {
      '@type': 'BreadcrumbList',
      name: 'Printables',
    },
    {
      '@type': 'CreativeWork',
      name: 'Cable Clip',
      author: { '@type': 'Person', name: 'Jamie' },
      license: 'https://creativecommons.org/licenses/by-nc/4.0/',
      keywords: ['cable', 'organiser'],
    },
  ],
  gallery: ['https://media.printables.com/1.png'],
  dom: {
    siteKey: 'printables.com',
    description: 'A simple clip for routing cables around a desk.',
    author: 'Jamie',
    tags: ['Cable', 'Desk'],
  },
};

test('buildMetadata merges every layer', () => {
  const meta = buildMetadata(PRINTABLES_HARVEST);
  assert.equal(meta.title, 'Cable Clip');
  assert.equal(meta.author, 'Jamie');
  assert.equal(meta.license, 'CC-BY-NC');
  assert.equal(meta.sourceUrl, PRINTABLES_HARVEST.url);
  assert.deepEqual(meta.gallery, ['https://media.printables.com/1.png']);
});

test('buildMetadata strips the site name from the title', () => {
  // og:title is routinely "Model | Site"; the site half would otherwise become
  // part of the model's name in the library.
  assert.equal(buildMetadata(PRINTABLES_HARVEST).title, 'Cable Clip');
  assert.equal(
    buildMetadata({
      url: 'https://www.thingiverse.com/thing:1',
      meta: { 'og:title': 'Widget - Thingiverse' },
    }).title,
    'Widget',
  );
});

test('buildMetadata ignores breadcrumb and organisation JSON-LD nodes', () => {
  // A BreadcrumbList carries name: "Printables", which would win the title.
  const meta = buildMetadata({
    url: 'https://www.printables.com/model/1-thing',
    meta: {},
    jsonLd: [
      { '@type': 'BreadcrumbList', name: 'Printables' },
      { '@type': 'Organization', name: 'Printables' },
      { '@type': 'CreativeWork', name: 'Real Title' },
    ],
  });
  assert.equal(meta.title, 'Real Title');
});

test('buildMetadata prepends the site tag', () => {
  const meta = buildMetadata(PRINTABLES_HARVEST);
  assert.equal(meta.tags[0], 'printables');
});

test('buildMetadata lets the server scrape win over the page', () => {
  const meta = buildMetadata(PRINTABLES_HARVEST, {
    title: 'Cable Clip v2',
    description: 'Scraped through the Printables API.',
    tags: ['cable-management'],
  });
  assert.equal(meta.title, 'Cable Clip v2');
  assert.equal(meta.description, 'Scraped through the Printables API.');
  assert.ok(meta.tags.includes('cable-management'));
  // Page tags still ride along; the server's just take precedence.
  assert.ok(meta.tags.includes('cable'));
});

test('buildMetadata falls back to Open Graph when there is no JSON-LD', () => {
  const meta = buildMetadata({
    url: 'https://example.com/thing',
    meta: {
      'og:title': 'Bare Model',
      'og:description': 'Only Open Graph here.',
      keywords: 'one, two',
    },
    jsonLd: [],
    dom: {},
  });
  assert.equal(meta.title, 'Bare Model');
  assert.equal(meta.description, 'Only Open Graph here.');
  assert.deepEqual(meta.tags, ['one', 'two']);
});

test('buildMetadata survives an empty harvest', () => {
  assert.deepEqual(buildMetadata(null), { tags: [] });
  const meta = buildMetadata({ url: 'https://example.com/x' });
  assert.equal(meta.title, null);
  assert.deepEqual(meta.tags, []);
});

test('buildMetadata caps the tag list', () => {
  const meta = buildMetadata({
    url: 'https://example.com/x',
    meta: {},
    jsonLd: [],
    dom: { tags: Array.from({ length: 40 }, (_, i) => `tag${i}`) },
  });
  assert.ok(meta.tags.length <= 25);
});

test('normaliseLicense reads the spelled-out Thingiverse forms', () => {
  assert.equal(
    normaliseLicense('Creative Commons - Attribution - Non-Commercial - Share Alike'),
    'CC-BY-NC-SA',
  );
  assert.equal(
    normaliseLicense('Creative Commons - Attribution - No Derivatives'),
    'CC-BY-ND',
  );
  assert.equal(
    normaliseLicense('Creative Commons - Public Domain Dedication'),
    'CC0',
  );
  assert.equal(normaliseLicense('GNU - GPL'), 'GPL');
  assert.equal(normaliseLicense('All Rights Reserved'), 'All Rights Reserved');
});

test('normaliseLicense keeps ND and SA from combining', () => {
  // No real CC licence is both NoDerivatives and ShareAlike; emitting
  // "CC-BY-ND-SA" would invent a licence that does not exist.
  const name = normaliseLicense('Attribution No Derivatives Share Alike');
  assert.ok(!/ND-SA|SA-ND/.test(name), name);
});

test('storageFilename prefers the model title over an opaque download name', () => {
  // The first real capture landed as f29762eb-8583-49fa-8468-3c8096e48416.3mf
  // because MakerWorld serves downloads under a UUID.
  assert.equal(
    storageFilename('f29762eb-8583-49fa-8468-3c8096e48416.3mf', 'Cable Clip'),
    'Cable Clip.3mf',
  );
});

test('storageFilename keeps the download name when there is no title', () => {
  assert.equal(storageFilename('thing.stl', null), 'thing.stl');
  assert.equal(storageFilename(null, null), 'capture.stl');
});

test('storageFilename strips characters that are illegal in a filename', () => {
  const name = storageFilename('x.stl', 'A/B: "weird" <name>?');
  assert.ok(!/[<>:"/\\|?*]/.test(name), name);
  assert.ok(name.endsWith('.stl'));
});

test('storageFilename does not leave a trailing dot or space', () => {
  // Windows silently rejects both, and the library may be on a CIFS share.
  assert.equal(storageFilename('x.stl', 'Widget v2. '), 'Widget v2.stl');
});

test('storageFilename falls back when the title sanitises to nothing', () => {
  assert.equal(storageFilename('thing.3mf', '///'), '___.3mf');
  assert.equal(storageFilename('thing.3mf', '   '), 'thing.3mf');
});

test('isModelPage accepts real model URLs on every supported site', () => {
  const pages = [
    'https://www.printables.com/model/12345-cable-clip',
    'https://www.thingiverse.com/thing:4567890',
    'https://makerworld.com/en/models/198362-vernier-caliper-ruler-two-lengths',
    'https://www.myminifactory.com/object/3d-print-dragon-12345',
    'https://cults3d.com/en/3d-model/gadget/thing',
    'https://thangs.com/designer/someone/3d-model/widget-98765',
  ];
  for (const url of pages) assert.ok(isModelPage(url), url);
});

test('isModelPage rejects the pages that caused a mis-titled capture', () => {
  // A capture was attributed to "ProZac | Visit History" because the harvester
  // remembered a browsing-history page on a supported host.
  const notModels = [
    'https://makerworld.com/en/@user_1834999983/browsing-history',
    'https://makerworld.com/en/models',
    'https://www.printables.com/search/models?q=clip',
    'https://www.printables.com/@someone',
    'https://www.thingiverse.com/thing:4567890/comments'.replace('/thing:4567890', '/search'),
    'https://cults3d.com/en/users/someone',
    'https://www.myminifactory.com/users/someone',
  ];
  for (const url of notModels) assert.ok(!isModelPage(url), url);
});

test('isModelPage ignores a locale prefix and a query string', () => {
  assert.ok(isModelPage('https://makerworld.com/en/models/198362-name?from=recommend#p-1'));
  assert.ok(isModelPage('https://cults3d.com/de/3d-model/spiel/ding'));
});

test('isModelPage gives an unknown host the benefit of the doubt', () => {
  // A bad title beats refusing to capture from a site we have no rules for.
  assert.ok(isModelPage('https://example.com/whatever'));
  assert.ok(!isModelPage('not a url'));
});
