/**
 * YASTL - Search and formatting utilities
 */

/**
 * Create a debounced version of a function.
 * @param {Function} fn - Function to debounce
 * @param {number} delay - Delay in milliseconds
 * @returns {Function}
 */
export function debounce(fn, delay = 300) {
    let timer = null;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

/**
 * Highlight search query matches in text.
 * @param {string} text - Original text
 * @param {string} query - Search query
 * @returns {string} HTML string with <mark> tags
 */
export function highlightMatch(text, query) {
    if (!query || !text) return text || '';
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escaped})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
}

/**
 * Format bytes to human-readable file size.
 * @param {number} bytes
 * @returns {string}
 */
export function formatFileSize(bytes) {
    if (bytes == null || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
        size /= 1024;
        i++;
    }
    return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/**
 * Format ISO date string to friendly format.
 * @param {string} isoString
 * @returns {string}
 */
export function formatDate(isoString) {
    if (!isoString) return '';
    const d = new Date(isoString);
    return d.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}

/**
 * Format number with comma separators.
 * @param {number} n
 * @returns {string}
 */
export function formatNumber(n) {
    if (n == null) return '-';
    return n.toLocaleString();
}

/**
 * Format dimensions as WxHxD string.
 * @param {number} x
 * @param {number} y
 * @param {number} z
 * @returns {string}
 */
export function formatDimensions(x, y, z) {
    if (x == null || y == null || z == null) return '-';
    return `${x.toFixed(1)} x ${y.toFixed(1)} x ${z.toFixed(1)}`;
}
