/**
 * YASTL - Tag namespacing helpers.
 *
 * Tags may use a `namespace:value` convention (e.g. `franchise:starwars`,
 * `type:miniature`, `material:pla`). These helpers split a tag into its parts
 * and derive a stable color from the namespace so related tags read as a group
 * across the sidebar, cards, and detail panel. Tags without a colon are plain.
 */

/**
 * Split a tag into { namespace, value, raw }.
 * Only the first colon is treated as the separator, so `type:foo:bar` →
 * namespace `type`, value `foo:bar`. A leading/trailing colon or empty side
 * falls back to a plain tag (namespace null).
 *
 * @param {string} name
 * @returns {{ namespace: string|null, value: string, raw: string }}
 */
export function parseTag(name) {
    const raw = String(name ?? '');
    const idx = raw.indexOf(':');
    if (idx > 0 && idx < raw.length - 1) {
        return { namespace: raw.slice(0, idx), value: raw.slice(idx + 1), raw };
    }
    return { namespace: null, value: raw, raw };
}

/**
 * Deterministic hue (0-359) from a namespace string. Same namespace always maps
 * to the same hue, so `franchise:*` tags share a color everywhere they appear.
 *
 * @param {string} ns
 * @returns {number}
 */
export function tagHue(ns) {
    let h = 0;
    for (let i = 0; i < ns.length; i++) {
        h = (h * 31 + ns.charCodeAt(i)) % 360;
    }
    return h;
}

/**
 * Inline style object tinting a namespaced tag's accent color. Mid lightness so
 * it stays legible on both light and dark chip backgrounds. Returns {} for
 * plain (non-namespaced) tags so the default chip styling applies.
 *
 * @param {string} name
 * @returns {Record<string, string>}
 */
export function tagColorStyle(name) {
    const { namespace } = parseTag(name);
    if (!namespace) return {};
    const h = tagHue(namespace);
    return {
        '--tag-ns-color': `hsl(${h}, 55%, 58%)`,
        '--tag-ns-border': `hsl(${h}, 45%, 50%)`,
    };
}
