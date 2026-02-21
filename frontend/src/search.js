/**
 * YASTL - Search and formatting utilities
 * ES module with helper functions for the frontend.
 */

/**
 * Create a debounced version of a function.
 * The returned function delays invoking `fn` until after `delay` milliseconds
 * have elapsed since the last time the debounced function was invoked.
 *
 * @param {Function} fn - The function to debounce.
 * @param {number} delay - Delay in milliseconds.
 * @returns {Function} The debounced function.
 */
export function debounce(fn, delay = 300) {
    let timer = null;
    return function (...args) {
        if (timer !== null) {
            clearTimeout(timer);
        }
        timer = setTimeout(() => {
            fn.apply(this, args);
            timer = null;
        }, delay);
    };
}

/**
 * Wrap matching portions of `text` in <mark> tags to highlight search matches.
 * Returns an HTML string safe for use with v-html.
 *
 * @param {string} text - The source text.
 * @param {string} query - The search query to highlight.
 * @returns {string} HTML string with matches wrapped in <mark>.
 */
export function highlightMatch(text, query) {
    if (!text || !query || !query.trim()) {
        return escapeHtml(text || '');
    }
    const escaped = escapeRegExp(query.trim());
    const regex = new RegExp(`(${escaped})`, 'gi');
    return escapeHtml(text).replace(regex, '<mark>$1</mark>');
}

/**
 * Format a byte count into a human-readable file size string.
 *
 * @param {number} bytes - The file size in bytes.
 * @returns {string} Formatted file size (e.g. "1.5 MB").
 */
export function formatFileSize(bytes) {
    if (bytes == null || isNaN(bytes)) return '--';
    if (bytes === 0) return '0 B';

    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const k = 1024;
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    const size = bytes / Math.pow(k, i);

    if (i === 0) return `${bytes} B`;
    return `${size.toFixed(1)} ${units[i]}`;
}

/**
 * Format an ISO date string into a friendly, locale-aware date.
 * Shows relative dates for recent items ("Today", "Yesterday", "3 days ago").
 *
 * @param {string} isoString - ISO 8601 date string.
 * @returns {string} Formatted date string (e.g. "Jan 15, 2025").
 */
export function formatDate(isoString) {
    if (!isoString) return '--';
    try {
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return '--';

        const now = new Date();
        const diffMs = now - date;
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays === 0) return 'Today';
        if (diffDays === 1) return 'Yesterday';
        if (diffDays < 7) return `${diffDays} days ago`;

        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
        });
    } catch {
        return '--';
    }
}

/**
 * Format a number with comma separators for readability.
 *
 * @param {number} n - The number to format.
 * @returns {string} Formatted number string (e.g. "1,234,567").
 */
export function formatNumber(n) {
    if (n == null || isNaN(n)) return '--';
    return Number(n).toLocaleString('en-US');
}

/**
 * Format 3D dimensions (x, y, z) into a readable string.
 *
 * @param {number} x - X dimension
 * @param {number} y - Y dimension
 * @param {number} z - Z dimension
 * @returns {string} Formatted dimensions (e.g. "10.5 x 20.3 x 15.0")
 */
export function formatDimensions(x, y, z) {
    if (x == null && y == null && z == null) return '--';
    const fmt = (v) => (v != null ? Number(v).toFixed(1) : '?');
    return `${fmt(x)} x ${fmt(y)} x ${fmt(z)}`;
}

/* ---- Internal helpers ---- */

/**
 * Escape special regex characters in a string.
 * @param {string} str
 * @returns {string}
 */
function escapeRegExp(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Escape HTML special characters to prevent XSS.
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
    };
    return str.replace(/[&<>"']/g, (c) => map[c]);
}
