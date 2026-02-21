/**
 * YASTL - Yet Another STL Library
 * Main Vue 3 Application (CDN / no build step)
 */
import { initViewer, loadModel, disposeViewer, resetCamera } from './viewer.js';
import {
    debounce,
    highlightMatch,
    formatFileSize,
    formatDate,
    formatNumber,
    formatDimensions,
} from './search.js';

const { createApp, ref, reactive, computed, onMounted, nextTick } = Vue;

/* ==================================================================
   SVG icon strings (inlined to avoid external deps)
   ================================================================== */

const ICONS = {
    search: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
    grid: `<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>`,
    list: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/></svg>`,
    close: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    cube: `<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`,
    download: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
    trash: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`,
    refresh: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`,
    warning: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    menu: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>`,
    chevron: `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>`,
    scan: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>`,
    settings: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
    folder: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
    plus: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
    activity: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
    database: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>`,
    eye: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
    image: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
    home: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`,
    heart: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`,
    heartFilled: `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`,
    collection: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/></svg>`,
    bookmark: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>`,
    check: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
    select: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`,
};

/* ==================================================================
   Application
   ================================================================== */

const app = createApp({
    setup() {
        /* ---- Reactive state ---- */
        const models = ref([]);
        const selectedModel = ref(null);
        const searchQuery = ref('');
        const viewMode = ref('grid');
        const loading = ref(false);
        const showDetail = ref(false);
        const allTags = ref([]);
        const allCategories = ref([]);
        const newTagInput = ref('');
        const toasts = ref([]);
        const sidebarOpen = ref(false);
        const viewerLoading = ref(false);

        // Editable field state
        const editName = ref('');
        const editDesc = ref('');
        const isEditingName = ref(false);
        const isEditingDesc = ref(false);

        // Category expansion state (by category id)
        const expandedCategories = reactive({});

        // Sidebar section collapse state (format starts collapsed)
        const collapsedSections = reactive({ format: true });

        const filters = reactive({
            format: '',
            tag: '',
            tags: [],
            category: '',
            categories: [],
            library_id: null,
            favoritesOnly: false,
            collection: null,
            sortBy: 'updated_at',
            sortOrder: 'desc',
        });

        const pagination = reactive({
            limit: 50,
            offset: 0,
            total: 0,
        });

        const scanStatus = reactive({
            scanning: false,
            total_files: 0,
            processed_files: 0,
        });

        let scanPollTimer = null;

        // Settings / Library management
        const showSettings = ref(false);
        const libraries = ref([]);
        const newLibName = ref('');
        const newLibPath = ref('');
        const addingLibrary = ref(false);

        // Thumbnail settings
        const thumbnailMode = ref('wireframe');
        const thumbnailQuality = ref('fast');
        const regeneratingThumbnails = ref(false);

        // Update system
        const updateInfo = reactive({
            checked: false,
            checking: false,
            update_available: false,
            current_version: '',
            current_sha: '',
            remote_sha: '',
            commits_behind: 0,
            commits: [],
            is_git_repo: false,
            remote_url: '',
            branch: '',
            error: null,
            applying: false,
            restarting: false,
        });

        // System status indicator
        const showStatusMenu = ref(false);
        const systemStatus = reactive({
            health: 'unknown',
            scanner: { status: 'unknown' },
            watcher: { status: 'unknown' },
            database: { status: 'unknown' },
            thumbnails: { status: 'unknown' },
        });
        let statusPollTimer = null;

        // Catalog system: Collections
        const collections = ref([]);
        const showCollectionModal = ref(false);
        const newCollectionName = ref('');
        const newCollectionColor = ref('#0f9b8e');
        const addToCollectionModelId = ref(null);
        const showAddToCollectionModal = ref(false);

        // Catalog system: Saved searches
        const savedSearches = ref([]);
        const showSaveSearchModal = ref(false);
        const saveSearchName = ref('');

        // Catalog system: Selection mode
        const selectionMode = ref(false);
        const selectedModels = reactive(new Set());

        /* ---- Computed ---- */
        const hasLibraries = computed(() => libraries.value.length > 0);
        const scanProgress = computed(() => {
            if (!scanStatus.total_files) return 0;
            return Math.round(
                (scanStatus.processed_files / scanStatus.total_files) * 100
            );
        });

        const hasMore = computed(() => {
            return pagination.offset + pagination.limit < pagination.total;
        });

        const shownCount = computed(() => {
            return Math.min(pagination.offset + pagination.limit, pagination.total);
        });

        const hasActiveFilters = computed(() => {
            return !!(filters.format || filters.tag || filters.category || filters.library_id || filters.tags.length || filters.categories.length || filters.favoritesOnly || filters.collection);
        });

        // Find the library object for the currently selected library_id
        const selectedLibrary = computed(() => {
            if (!filters.library_id) return null;
            return libraries.value.find(l => l.id === filters.library_id) || null;
        });

        // Build breadcrumb trail from current filters
        const breadcrumbTrail = computed(() => {
            const trail = [];
            if (filters.library_id && selectedLibrary.value) {
                trail.push({ type: 'library_id', label: selectedLibrary.value.name });
            }
            if (filters.category) {
                trail.push({ type: 'category', label: filters.category });
            }
            if (filters.tag) {
                trail.push({ type: 'tag', label: filters.tag });
            }
            if (filters.format) {
                trail.push({ type: 'format', label: filters.format.toUpperCase() });
            }
            return trail;
        });

        /* ==============================================================
           API Methods
           ============================================================== */

        async function fetchModels(append = false) {
            loading.value = true;
            try {
                const params = new URLSearchParams({
                    limit: String(pagination.limit),
                    offset: String(pagination.offset),
                });
                if (filters.format) params.append('format', filters.format);
                if (filters.tag) params.append('tag', filters.tag);
                if (filters.category) params.append('category', filters.category);
                if (filters.library_id) params.append('library_id', String(filters.library_id));
                if (filters.tags.length > 0) params.append('tags', filters.tags.join(','));
                if (filters.categories.length > 0) params.append('categories', filters.categories.join(','));
                if (filters.favoritesOnly) params.append('favorites_only', 'true');
                if (filters.collection) params.append('collection', filters.collection);
                params.append('sort_by', filters.sortBy);
                params.append('sort_order', filters.sortOrder);

                const res = await fetch(`/api/models?${params}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                if (append) {
                    models.value = [...models.value, ...(data.models || [])];
                } else {
                    models.value = data.models || [];
                }
                pagination.total = data.total || 0;
            } catch (err) {
                showToast('Failed to load models', 'error');
                console.error('fetchModels error:', err);
            } finally {
                loading.value = false;
            }
        }

        async function searchModels(append = false) {
            if (!searchQuery.value.trim()) {
                pagination.offset = 0;
                return fetchModels();
            }
            loading.value = true;
            try {
                const params = new URLSearchParams({
                    q: searchQuery.value.trim(),
                    limit: String(pagination.limit),
                    offset: String(pagination.offset),
                });
                if (filters.format) params.append('format', filters.format);
                if (filters.tag) params.append('tags', filters.tag);
                if (filters.category) params.append('categories', filters.category);
                if (filters.library_id) params.append('library_id', String(filters.library_id));

                const res = await fetch(`/api/search?${params}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                if (append) {
                    models.value = [...models.value, ...(data.models || [])];
                } else {
                    models.value = data.models || [];
                }
                pagination.total = data.total || 0;
            } catch (err) {
                showToast('Search failed', 'error');
                console.error('searchModels error:', err);
            } finally {
                loading.value = false;
            }
        }

        const debouncedSearch = debounce(() => {
            pagination.offset = 0;
            if (searchQuery.value.trim()) {
                searchModels();
            } else {
                fetchModels();
            }
        }, 300);

        function onSearchInput(e) {
            searchQuery.value = e.target.value;
            debouncedSearch();
        }

        function clearSearch() {
            searchQuery.value = '';
            pagination.offset = 0;
            fetchModels();
        }

        async function fetchTags() {
            try {
                const res = await fetch('/api/tags');
                if (!res.ok) return;
                const data = await res.json();
                allTags.value = data.tags || [];
            } catch (err) {
                console.error('fetchTags error:', err);
            }
        }

        async function fetchCategories() {
            try {
                const res = await fetch('/api/categories');
                if (!res.ok) return;
                const data = await res.json();
                allCategories.value = data.categories || [];
            } catch (err) {
                console.error('fetchCategories error:', err);
            }
        }

        async function fetchScanStatus() {
            try {
                const res = await fetch('/api/scan/status');
                if (!res.ok) return;
                const data = await res.json();
                scanStatus.scanning = data.scanning;
                scanStatus.total_files = data.total_files;
                scanStatus.processed_files = data.processed_files;

                if (data.scanning && !scanPollTimer) {
                    scanPollTimer = setInterval(fetchScanStatus, 2000);
                } else if (!data.scanning && scanPollTimer) {
                    clearInterval(scanPollTimer);
                    scanPollTimer = null;
                    // Refresh all data after scan completes
                    fetchModels();
                    fetchTags();
                    fetchCategories();
                    showToast('Library scan complete');
                }
            } catch (err) {
                console.error('fetchScanStatus error:', err);
            }
        }

        /* ==============================================================
           Library Management
           ============================================================== */

        async function fetchLibraries() {
            try {
                const res = await fetch('/api/libraries');
                if (!res.ok) return;
                const data = await res.json();
                libraries.value = data.libraries || [];
            } catch (err) {
                console.error('fetchLibraries error:', err);
            }
        }

        /* ==============================================================
           System Status
           ============================================================== */

        async function fetchSystemStatus() {
            try {
                const res = await fetch('/api/status');
                if (!res.ok) return;
                const data = await res.json();
                systemStatus.health = data.health || 'unknown';
                systemStatus.scanner = data.scanner || { status: 'unknown' };
                systemStatus.watcher = data.watcher || { status: 'unknown' };
                systemStatus.database = data.database || { status: 'unknown' };
                systemStatus.thumbnails = data.thumbnails || { status: 'unknown' };
            } catch (err) {
                systemStatus.health = 'error';
                console.error('fetchSystemStatus error:', err);
            }
        }

        function toggleStatusMenu() {
            showStatusMenu.value = !showStatusMenu.value;
        }

        function closeStatusMenu() {
            showStatusMenu.value = false;
        }

        function statusLabel(status) {
            const labels = {
                ok: 'Healthy',
                idle: 'Idle',
                scanning: 'Scanning',
                watching: 'Watching',
                stopped: 'Stopped',
                degraded: 'Degraded',
                error: 'Error',
                unavailable: 'Unavailable',
                unknown: 'Unknown',
            };
            return labels[status] || status;
        }

        function statusDotClass(status) {
            if (['ok', 'idle', 'watching'].includes(status)) return 'status-dot-ok';
            if (['scanning', 'degraded'].includes(status)) return 'status-dot-warn';
            if (['error', 'stopped', 'unavailable'].includes(status)) return 'status-dot-error';
            return 'status-dot-unknown';
        }

        async function addLibrary() {
            const name = newLibName.value.trim();
            const path = newLibPath.value.trim();
            if (!name || !path) {
                showToast('Name and path are required', 'error');
                return;
            }
            addingLibrary.value = true;
            try {
                const res = await fetch('/api/libraries', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, path }),
                });
                const data = await res.json();
                if (res.ok) {
                    libraries.value.push(data);
                    newLibName.value = '';
                    newLibPath.value = '';
                    showToast(`Library "${name}" added`);
                } else {
                    showToast(data.detail || 'Failed to add library', 'error');
                }
            } catch (err) {
                showToast('Failed to add library', 'error');
                console.error('addLibrary error:', err);
            } finally {
                addingLibrary.value = false;
            }
        }

        async function deleteLibrary(lib) {
            if (!confirm(`Remove library "${lib.name}"?\n\nModels already scanned from this library will remain in the database.`)) {
                return;
            }
            try {
                const res = await fetch(`/api/libraries/${lib.id}`, { method: 'DELETE' });
                if (res.ok) {
                    libraries.value = libraries.value.filter((l) => l.id !== lib.id);
                    showToast(`Library "${lib.name}" removed`);
                } else {
                    const data = await res.json();
                    showToast(data.detail || 'Failed to remove library', 'error');
                }
            } catch (err) {
                showToast('Failed to remove library', 'error');
            }
        }

        /* ==============================================================
           Thumbnail Settings
           ============================================================== */

        async function fetchSettings() {
            try {
                const res = await fetch('/api/settings');
                if (!res.ok) return;
                const data = await res.json();
                thumbnailMode.value = data.thumbnail_mode || 'wireframe';
                thumbnailQuality.value = data.thumbnail_quality || 'fast';
            } catch (err) {
                console.error('fetchSettings error:', err);
            }
        }

        async function setThumbnailMode(mode) {
            try {
                const res = await fetch('/api/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ thumbnail_mode: mode }),
                });
                if (res.ok) {
                    const data = await res.json();
                    thumbnailMode.value = data.thumbnail_mode || mode;
                    showToast(`Thumbnail mode set to ${mode}`);
                } else {
                    const data = await res.json();
                    showToast(data.detail || 'Failed to update setting', 'error');
                }
            } catch (err) {
                showToast('Failed to update setting', 'error');
                console.error('setThumbnailMode error:', err);
            }
        }

        async function setThumbnailQuality(quality) {
            try {
                const res = await fetch('/api/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ thumbnail_quality: quality }),
                });
                if (res.ok) {
                    const data = await res.json();
                    thumbnailQuality.value = data.thumbnail_quality || quality;
                    showToast(`Thumbnail quality set to ${quality}`);
                } else {
                    const data = await res.json();
                    showToast(data.detail || 'Failed to update setting', 'error');
                }
            } catch (err) {
                showToast('Failed to update setting', 'error');
                console.error('setThumbnailQuality error:', err);
            }
        }

        async function regenerateThumbnails() {
            if (!confirm('Regenerate all thumbnails?\n\nThis will re-render every model thumbnail using the current mode. This runs in the background.')) {
                return;
            }
            regeneratingThumbnails.value = true;
            try {
                const res = await fetch('/api/settings/regenerate-thumbnails', { method: 'POST' });
                if (res.ok) {
                    showToast('Thumbnail regeneration started', 'info');
                } else {
                    const data = await res.json();
                    showToast(data.detail || 'Failed to start regeneration', 'error');
                }
            } catch (err) {
                showToast('Failed to start thumbnail regeneration', 'error');
                console.error('regenerateThumbnails error:', err);
            } finally {
                regeneratingThumbnails.value = false;
            }
        }

        function openSettings() {
            fetchLibraries();
            fetchSettings();
            showSettings.value = true;
            document.body.classList.add('modal-open');
            // Auto-check for updates if not checked yet
            if (!updateInfo.checked && !updateInfo.checking) {
                checkForUpdates();
            }
        }

        function closeSettings() {
            showSettings.value = false;
            if (!showDetail.value) {
                document.body.classList.remove('modal-open');
            }
        }

        /* ==============================================================
           Update System
           ============================================================== */

        async function checkForUpdates() {
            updateInfo.checking = true;
            updateInfo.error = null;
            try {
                const res = await fetch('/api/update/check');
                if (!res.ok) {
                    const data = await res.json();
                    updateInfo.error = data.detail || 'Failed to check for updates';
                    return;
                }
                const data = await res.json();
                updateInfo.checked = true;
                updateInfo.update_available = data.update_available;
                updateInfo.current_version = data.current_version;
                updateInfo.current_sha = data.current_sha;
                updateInfo.remote_sha = data.remote_sha;
                updateInfo.commits_behind = data.commits_behind;
                updateInfo.commits = data.commits || [];
                updateInfo.is_git_repo = data.is_git_repo;
                updateInfo.remote_url = data.remote_url;
                updateInfo.branch = data.branch;
                if (data.error) {
                    updateInfo.error = data.error;
                }
            } catch (err) {
                updateInfo.error = 'Failed to check for updates';
                console.error('checkForUpdates error:', err);
            } finally {
                updateInfo.checking = false;
            }
        }

        async function applyUpdate() {
            if (!confirm('Apply update and restart YASTL?\n\nThe application will be briefly unavailable while it restarts.')) {
                return;
            }
            updateInfo.applying = true;
            updateInfo.error = null;
            try {
                const res = await fetch('/api/update/apply', { method: 'POST' });
                const data = await res.json();
                if (res.ok) {
                    updateInfo.applying = false;
                    updateInfo.restarting = true;
                    showToast('Update applied. Restarting...', 'info');
                    // Poll until the server comes back
                    waitForRestart();
                } else {
                    updateInfo.error = data.detail || 'Update failed';
                    showToast(data.detail || 'Update failed', 'error');
                }
            } catch (err) {
                // Connection may drop during restart - that's expected
                updateInfo.applying = false;
                updateInfo.restarting = true;
                showToast('Update applied. Restarting...', 'info');
                waitForRestart();
            }
        }

        function waitForRestart() {
            let attempts = 0;
            const maxAttempts = 30;
            const interval = setInterval(async () => {
                attempts++;
                try {
                    const res = await fetch('/health');
                    if (res.ok) {
                        clearInterval(interval);
                        updateInfo.restarting = false;
                        updateInfo.update_available = false;
                        updateInfo.commits_behind = 0;
                        updateInfo.commits = [];
                        updateInfo.checked = false;
                        showToast('YASTL has been updated and restarted');
                        // Refresh page to load any frontend changes
                        setTimeout(() => window.location.reload(), 1000);
                    }
                } catch {
                    // Server still down, keep polling
                }
                if (attempts >= maxAttempts) {
                    clearInterval(interval);
                    updateInfo.restarting = false;
                    updateInfo.error = 'Service did not come back after restart. Check server logs.';
                    showToast('Restart may have failed. Check server logs.', 'error');
                }
            }, 2000);
        }

        /* ==============================================================
           Actions
           ============================================================== */

        async function triggerScan() {
            try {
                const res = await fetch('/api/scan', { method: 'POST' });
                const data = await res.json();
                if (res.ok) {
                    showToast('Library scan started', 'info');
                    scanStatus.scanning = true;
                    if (!scanPollTimer) {
                        scanPollTimer = setInterval(fetchScanStatus, 2000);
                    }
                } else {
                    showToast(data.detail || 'Could not start scan', 'error');
                }
            } catch (err) {
                showToast('Failed to start scan', 'error');
                console.error('triggerScan error:', err);
            }
        }

        async function viewModel(model) {
            // Fetch the full model detail first to get complete data
            try {
                const res = await fetch(`/api/models/${model.id}`);
                if (res.ok) {
                    selectedModel.value = await res.json();
                } else {
                    selectedModel.value = { ...model };
                }
            } catch {
                selectedModel.value = { ...model };
            }

            editName.value = selectedModel.value.name || '';
            editDesc.value = selectedModel.value.description || '';
            isEditingName.value = false;
            isEditingDesc.value = false;
            showDetail.value = true;
            document.body.classList.add('modal-open');

            await nextTick();

            // Initialize 3D viewer
            viewerLoading.value = true;
            initViewer('viewer-container');

            const supportedViewerFormats = ['stl', 'obj', 'gltf', 'glb', 'ply', '3mf'];
            const fmt = (selectedModel.value.file_format || '').toLowerCase();
            const glbUrl = `/api/models/${selectedModel.value.id}/file/glb`;

            let loaded = false;

            if (supportedViewerFormats.includes(fmt)) {
                const fileUrl = `/api/models/${selectedModel.value.id}/file`;
                try {
                    await loadModel(fileUrl, fmt);
                    loaded = true;
                } catch (err) {
                    console.warn('Native loader failed for', fmt, '— trying GLB fallback:', err);
                }
            }

            // Fallback: server-side GLB conversion (covers STEP, STP, and
            // any native-loader failures like problematic 3MF files)
            if (!loaded && fmt) {
                try {
                    await loadModel(glbUrl, 'glb');
                    loaded = true;
                } catch (err) {
                    console.error('GLB fallback also failed:', err);
                }
            }
            viewerLoading.value = false;
        }

        function closeDetail() {
            showDetail.value = false;
            disposeViewer();
            selectedModel.value = null;
            isEditingName.value = false;
            isEditingDesc.value = false;
            viewerLoading.value = false;
            if (!showSettings.value) {
                document.body.classList.remove('modal-open');
            }
        }

        async function addTag() {
            const tag = newTagInput.value.trim();
            if (!tag || !selectedModel.value) return;
            try {
                const res = await fetch(
                    `/api/models/${selectedModel.value.id}/tags`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tags: [tag] }),
                    }
                );
                if (res.ok) {
                    const updated = await res.json();
                    selectedModel.value = updated;
                    updateModelInList(updated);
                    newTagInput.value = '';
                    fetchTags();
                    showToast(`Tag "${tag}" added`);
                } else {
                    const err = await res.json();
                    showToast(err.detail || 'Failed to add tag', 'error');
                }
            } catch (err) {
                showToast('Failed to add tag', 'error');
            }
        }

        async function removeTag(tagName) {
            if (!selectedModel.value) return;
            try {
                const res = await fetch(
                    `/api/models/${selectedModel.value.id}/tags/${encodeURIComponent(tagName)}`,
                    { method: 'DELETE' }
                );
                if (res.ok) {
                    selectedModel.value.tags = (selectedModel.value.tags || []).filter(
                        (t) => t !== tagName
                    );
                    updateModelInList(selectedModel.value);
                    fetchTags();
                }
            } catch (err) {
                showToast('Failed to remove tag', 'error');
            }
        }

        async function updateModel(modelId, data) {
            if (!modelId) return;
            try {
                const res = await fetch(`/api/models/${modelId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });
                if (res.ok) {
                    const updated = await res.json();
                    selectedModel.value = updated;
                    editName.value = updated.name || '';
                    editDesc.value = updated.description || '';
                    updateModelInList(updated);
                    showToast('Model updated');
                } else {
                    const err = await res.json();
                    showToast(err.detail || 'Update failed', 'error');
                }
            } catch (err) {
                showToast('Failed to update model', 'error');
            }
            isEditingName.value = false;
            isEditingDesc.value = false;
        }

        async function deleteModel(model) {
            if (
                !confirm(
                    `Delete "${model.name}" from the library?\n\nThis removes it from the database but does NOT delete the file from disk.`
                )
            ) {
                return;
            }
            try {
                const res = await fetch(`/api/models/${model.id}`, {
                    method: 'DELETE',
                });
                if (res.ok) {
                    models.value = models.value.filter((m) => m.id !== model.id);
                    pagination.total = Math.max(0, pagination.total - 1);
                    if (showDetail.value) closeDetail();
                    showToast('Model removed from library');
                } else {
                    const err = await res.json();
                    showToast(err.detail || 'Delete failed', 'error');
                }
            } catch (err) {
                showToast('Failed to delete model', 'error');
            }
        }

        /* ---- Helpers ---- */

        function updateModelInList(updated) {
            const idx = models.value.findIndex((m) => m.id === updated.id);
            if (idx !== -1) {
                models.value[idx] = { ...updated };
            }
        }

        function closeSidebarIfMobile() {
            if (window.innerWidth <= 768) {
                sidebarOpen.value = false;
            }
        }

        function setFormatFilter(fmt) {
            filters.format = filters.format === fmt ? '' : fmt;
            pagination.offset = 0;
            refreshCurrentView();
            closeSidebarIfMobile();
        }

        function setTagFilter(tagName) {
            filters.tag = filters.tag === tagName ? '' : tagName;
            pagination.offset = 0;
            refreshCurrentView();
            closeSidebarIfMobile();
        }

        function setCategoryFilter(catName) {
            filters.category = filters.category === catName ? '' : catName;
            pagination.offset = 0;
            refreshCurrentView();
            closeSidebarIfMobile();
        }

        function setLibraryFilter(libId) {
            filters.library_id = filters.library_id === libId ? null : libId;
            pagination.offset = 0;
            refreshCurrentView();
        }

        function clearFilters() {
            filters.format = '';
            filters.tag = '';
            filters.category = '';
            filters.library_id = null;
            filters.tags = [];
            filters.categories = [];
            filters.favoritesOnly = false;
            filters.collection = null;
            filters.sortBy = 'updated_at';
            filters.sortOrder = 'desc';
            pagination.offset = 0;
            refreshCurrentView();
        }

        function removeBreadcrumb(crumb) {
            if (crumb.type === 'format') {
                filters.format = '';
            } else if (crumb.type === 'tag') {
                filters.tag = '';
            } else if (crumb.type === 'category') {
                filters.category = '';
            } else if (crumb.type === 'library_id') {
                filters.library_id = null;
            }
            pagination.offset = 0;
            refreshCurrentView();
        }

        function refreshCurrentView() {
            if (searchQuery.value.trim()) {
                searchModels();
            } else {
                fetchModels();
            }
        }

        function loadMore() {
            pagination.offset += pagination.limit;
            if (searchQuery.value.trim()) {
                searchModels(true);
            } else {
                fetchModels(true);
            }
        }

        function toggleCategory(catId) {
            expandedCategories[catId] = !expandedCategories[catId];
        }

        function handleResetView() {
            resetCamera();
        }

        function saveName() {
            if (!selectedModel.value) return;
            const val = editName.value.trim();
            if (val && val !== selectedModel.value.name) {
                updateModel(selectedModel.value.id, { name: val });
            } else {
                isEditingName.value = false;
            }
        }

        function saveDesc() {
            if (!selectedModel.value) return;
            const val = editDesc.value;
            if (val !== selectedModel.value.description) {
                updateModel(selectedModel.value.id, { description: val });
            } else {
                isEditingDesc.value = false;
            }
        }

        function startEditName() {
            editName.value = selectedModel.value?.name || '';
            isEditingName.value = true;
        }

        function startEditDesc() {
            editDesc.value = selectedModel.value?.description || '';
            isEditingDesc.value = true;
        }

        /* ---- Thumbnail helpers ---- */
        function thumbUrl(model) {
            if (model.thumbnail_path) {
                return `/thumbnails/${model.thumbnail_path}`;
            }
            return `/api/models/${model.id}/thumbnail`;
        }

        function onThumbError(e) {
            // Hide the broken img and show the fallback icon
            e.target.style.display = 'none';
            const fallback = e.target.parentElement?.querySelector('.no-thumbnail');
            if (fallback) fallback.style.display = 'flex';
        }

        /* ---- Toast notifications ---- */
        function showToast(message, type = 'success') {
            const id = Date.now() + Math.random();
            toasts.value.push({ id, message, type });
            setTimeout(() => {
                toasts.value = toasts.value.filter((t) => t.id !== id);
            }, 3500);
        }

        /* ---- Format badge CSS class ---- */
        function formatClass(fmt) {
            if (!fmt) return '';
            const f = fmt.toLowerCase().replace('.', '');
            if (f === '3mf') return '_3mf';
            return f;
        }

        // ---- Collections API ----
        async function fetchCollections() {
            try {
                const resp = await fetch('/api/collections');
                const data = await resp.json();
                collections.value = data.collections || [];
            } catch (e) {
                console.error('Failed to fetch collections', e);
            }
        }

        async function createCollection() {
            const name = newCollectionName.value.trim();
            if (!name) return;
            try {
                const resp = await fetch('/api/collections', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, color: newCollectionColor.value }),
                });
                if (resp.ok) {
                    showCollectionModal.value = false;
                    newCollectionName.value = '';
                    newCollectionColor.value = '#0f9b8e';
                    await fetchCollections();
                    showToast('Collection created', 'success');
                }
            } catch (e) {
                showToast('Failed to create collection', 'error');
            }
        }

        async function deleteCollection(id) {
            try {
                await fetch(`/api/collections/${id}`, { method: 'DELETE' });
                if (filters.collection === id) {
                    filters.collection = null;
                }
                await fetchCollections();
                showToast('Collection deleted', 'success');
            } catch (e) {
                showToast('Failed to delete collection', 'error');
            }
        }

        function openAddToCollection(modelId) {
            addToCollectionModelId.value = modelId;
            showAddToCollectionModal.value = true;
        }

        async function addModelToCollection(collectionId) {
            const modelId = addToCollectionModelId.value;
            if (!modelId) return;
            try {
                const resp = await fetch(`/api/collections/${collectionId}/models`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_ids: [modelId] }),
                });
                if (resp.ok) {
                    showAddToCollectionModal.value = false;
                    addToCollectionModelId.value = null;
                    await fetchCollections();
                    showToast('Added to collection', 'success');
                }
            } catch (e) {
                showToast('Failed to add to collection', 'error');
            }
        }

        function setCollectionFilter(collectionId) {
            if (filters.collection === collectionId) {
                filters.collection = null;
            } else {
                filters.collection = collectionId;
            }
            pagination.offset = 0;
            fetchModels();
        }

        // ---- Saved Searches API ----
        async function fetchSavedSearches() {
            try {
                const resp = await fetch('/api/saved-searches');
                const data = await resp.json();
                savedSearches.value = data.saved_searches || [];
            } catch (e) {
                console.error('Failed to fetch saved searches', e);
            }
        }

        async function saveCurrentSearch() {
            const name = saveSearchName.value.trim();
            if (!name) return;
            try {
                const resp = await fetch('/api/saved-searches', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name,
                        query: searchQuery.value,
                        filters: {
                            format: filters.format,
                            tags: filters.tags,
                            categories: filters.categories,
                            favoritesOnly: filters.favoritesOnly,
                            collection: filters.collection,
                        },
                        sort_by: filters.sortBy,
                        sort_order: filters.sortOrder,
                    }),
                });
                if (resp.ok) {
                    showSaveSearchModal.value = false;
                    saveSearchName.value = '';
                    await fetchSavedSearches();
                    showToast('Search saved', 'success');
                }
            } catch (e) {
                showToast('Failed to save search', 'error');
            }
        }

        function applySavedSearch(search) {
            searchQuery.value = search.query || '';
            const f = search.filters || {};
            filters.format = f.format || '';
            filters.tags = f.tags || [];
            filters.categories = f.categories || [];
            filters.favoritesOnly = f.favoritesOnly || false;
            filters.collection = f.collection || null;
            filters.sortBy = search.sort_by || 'updated_at';
            filters.sortOrder = search.sort_order || 'desc';
            pagination.offset = 0;
            fetchModels();
        }

        async function deleteSavedSearch(id) {
            try {
                await fetch(`/api/saved-searches/${id}`, { method: 'DELETE' });
                await fetchSavedSearches();
                showToast('Saved search deleted', 'success');
            } catch (e) {
                showToast('Failed to delete saved search', 'error');
            }
        }

        // ---- Favorites ----
        async function toggleFavorite(model, e) {
            if (e) e.stopPropagation();
            const wasFav = model.is_favorite;
            model.is_favorite = !wasFav;
            try {
                const method = wasFav ? 'DELETE' : 'POST';
                const resp = await fetch(`/api/models/${model.id}/favorite`, { method });
                if (!resp.ok) {
                    model.is_favorite = wasFav;
                }
            } catch {
                model.is_favorite = wasFav;
            }
        }

        function toggleFavoritesFilter() {
            filters.favoritesOnly = !filters.favoritesOnly;
            pagination.offset = 0;
            fetchModels();
        }

        // ---- Selection Mode ----
        function toggleSelectionMode() {
            selectionMode.value = !selectionMode.value;
            if (!selectionMode.value) {
                selectedModels.clear();
            }
        }

        function toggleModelSelection(modelId) {
            if (selectedModels.has(modelId)) {
                selectedModels.delete(modelId);
            } else {
                selectedModels.add(modelId);
            }
        }

        function selectAll() {
            models.value.forEach(m => selectedModels.add(m.id));
        }

        function deselectAll() {
            selectedModels.clear();
        }

        function isSelected(modelId) {
            return selectedModels.has(modelId);
        }

        async function bulkFavorite() {
            const ids = [...selectedModels];
            if (!ids.length) return;
            try {
                await fetch('/api/bulk/favorite', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_ids: ids, favorite: true }),
                });
                selectedModels.clear();
                selectionMode.value = false;
                await fetchModels();
                showToast(`${ids.length} model(s) favorited`, 'success');
            } catch {
                showToast('Bulk favorite failed', 'error');
            }
        }

        async function bulkAddToCollection(collectionId) {
            const ids = [...selectedModels];
            if (!ids.length || !collectionId) return;
            try {
                await fetch('/api/bulk/collections', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_ids: ids, collection_id: collectionId }),
                });
                selectedModels.clear();
                selectionMode.value = false;
                showAddToCollectionModal.value = false;
                await fetchCollections();
                showToast(`Added ${ids.length} model(s) to collection`, 'success');
            } catch {
                showToast('Bulk add to collection failed', 'error');
            }
        }

        async function bulkDelete() {
            const ids = [...selectedModels];
            if (!ids.length) return;
            if (!confirm(`Delete ${ids.length} model(s)? This cannot be undone.`)) return;
            try {
                await fetch('/api/bulk/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_ids: ids }),
                });
                selectedModels.clear();
                selectionMode.value = false;
                await fetchModels();
                showToast(`${ids.length} model(s) deleted`, 'success');
            } catch {
                showToast('Bulk delete failed', 'error');
            }
        }

        function openBulkAddToCollection() {
            addToCollectionModelId.value = null;
            showAddToCollectionModal.value = true;
        }

        function handleCollectionSelect(collectionId) {
            if (addToCollectionModelId.value) {
                addModelToCollection(collectionId);
            } else {
                bulkAddToCollection(collectionId);
            }
        }

        // ---- Sort / Filter helpers ----
        function setSortBy(value) {
            filters.sortBy = value;
            pagination.offset = 0;
            fetchModels();
        }

        function toggleSortOrder() {
            filters.sortOrder = filters.sortOrder === 'asc' ? 'desc' : 'asc';
            pagination.offset = 0;
            fetchModels();
        }

        function toggleTagFilter(tagName) {
            const idx = filters.tags.indexOf(tagName);
            if (idx >= 0) {
                filters.tags.splice(idx, 1);
            } else {
                filters.tags.push(tagName);
            }
            pagination.offset = 0;
            fetchModels();
        }

        function toggleCategoryFilter(catName) {
            const idx = filters.categories.indexOf(catName);
            if (idx >= 0) {
                filters.categories.splice(idx, 1);
            } else {
                filters.categories.push(catName);
            }
            pagination.offset = 0;
            fetchModels();
        }

        function removeTagFilter(tagName) {
            const idx = filters.tags.indexOf(tagName);
            if (idx >= 0) {
                filters.tags.splice(idx, 1);
                pagination.offset = 0;
                fetchModels();
            }
        }

        function removeCategoryFilter(catName) {
            const idx = filters.categories.indexOf(catName);
            if (idx >= 0) {
                filters.categories.splice(idx, 1);
                pagination.offset = 0;
                fetchModels();
            }
        }

        /* ---- Keyboard handler for modals ---- */
        function onKeydown(e) {
            if (e.key === 'Escape') {
                if (showAddToCollectionModal.value) {
                    showAddToCollectionModal.value = false;
                } else if (showCollectionModal.value) {
                    showCollectionModal.value = false;
                } else if (showSaveSearchModal.value) {
                    showSaveSearchModal.value = false;
                } else if (showStatusMenu.value) {
                    closeStatusMenu();
                } else if (showSettings.value) {
                    closeSettings();
                } else if (showDetail.value) {
                    closeDetail();
                }
            }
        }

        /* ---- Click-outside handler for status menu ---- */
        function onDocumentClick(e) {
            if (showStatusMenu.value) {
                const wrapper = document.querySelector('.status-wrapper');
                const menu = document.querySelector('.status-menu');
                if (wrapper && !wrapper.contains(e.target) && (!menu || !menu.contains(e.target))) {
                    closeStatusMenu();
                }
            }
        }

        /* ---- Lifecycle ---- */
        onMounted(() => {
            fetchLibraries();
            fetchModels();
            fetchTags();
            fetchCategories();
            fetchScanStatus();
            fetchSystemStatus();
            fetchCollections();
            fetchSavedSearches();
            statusPollTimer = setInterval(fetchSystemStatus, 30000);
            document.addEventListener('keydown', onKeydown);
            document.addEventListener('click', onDocumentClick);
        });

        // Search is triggered by onSearchInput handler instead of a watcher
        // to avoid cursor-position issues caused by v-model re-render cycles.

        /* ---- Expose everything to the template ---- */
        return {
            // State
            models,
            selectedModel,
            searchQuery,
            viewMode,
            loading,
            showDetail,
            allTags,
            allCategories,
            newTagInput,
            toasts,
            sidebarOpen,
            viewerLoading,
            editName,
            editDesc,
            isEditingName,
            isEditingDesc,
            expandedCategories,
            collapsedSections,
            filters,
            pagination,
            scanStatus,
            showSettings,
            libraries,
            newLibName,
            newLibPath,
            addingLibrary,
            updateInfo,
            thumbnailMode,
            thumbnailQuality,
            regeneratingThumbnails,
            showStatusMenu,
            systemStatus,
            collections,
            showCollectionModal,
            newCollectionName,
            newCollectionColor,
            addToCollectionModelId,
            showAddToCollectionModal,
            savedSearches,
            showSaveSearchModal,
            saveSearchName,
            selectionMode,
            selectedModels,

            // Computed
            scanProgress,
            hasMore,
            shownCount,
            hasActiveFilters,
            hasLibraries,
            breadcrumbTrail,
            selectedLibrary,

            // Actions
            onSearchInput,
            clearSearch,
            fetchModels,
            triggerScan,
            viewModel,
            closeDetail,
            addTag,
            removeTag,
            updateModel,
            deleteModel,
            loadMore,
            handleResetView,
            setFormatFilter,
            setTagFilter,
            setCategoryFilter,
            clearFilters,
            setLibraryFilter,
            removeBreadcrumb,
            toggleCategory,
            saveName,
            saveDesc,
            startEditName,
            startEditDesc,
            openSettings,
            closeSettings,
            addLibrary,
            deleteLibrary,
            setThumbnailMode,
            setThumbnailQuality,
            regenerateThumbnails,
            checkForUpdates,
            applyUpdate,
            toggleStatusMenu,
            closeStatusMenu,
            statusLabel,
            statusDotClass,
            fetchCollections,
            createCollection,
            deleteCollection,
            openAddToCollection,
            addModelToCollection,
            setCollectionFilter,
            fetchSavedSearches,
            saveCurrentSearch,
            applySavedSearch,
            deleteSavedSearch,
            toggleFavorite,
            toggleFavoritesFilter,
            toggleSelectionMode,
            toggleModelSelection,
            selectAll,
            deselectAll,
            isSelected,
            bulkFavorite,
            bulkAddToCollection,
            bulkDelete,
            openBulkAddToCollection,
            handleCollectionSelect,
            setSortBy,
            toggleSortOrder,
            toggleTagFilter,
            toggleCategoryFilter,
            removeTagFilter,
            removeCategoryFilter,

            // Helpers
            thumbUrl,
            onThumbError,
            showToast,
            formatClass,
            formatFileSize,
            formatDate,
            formatNumber,
            formatDimensions,
            highlightMatch,

            // Icons
            ICONS,
        };
    },

    template: /* html */ `
<div class="app-layout">
    <!-- ============================================================
         Navbar
         ============================================================ -->
    <nav class="navbar">
        <!-- Mobile sidebar toggle -->
        <button class="btn-icon sidebar-toggle" @click="sidebarOpen = !sidebarOpen"
                title="Toggle sidebar" v-html="ICONS.menu"></button>

        <!-- Brand -->
        <div class="navbar-brand">
            <div class="logo-icon">3D</div>
            <h1><span>YA</span>STL</h1>
        </div>

        <!-- Search -->
        <div class="search-container">
            <span class="search-icon" v-html="ICONS.search"></span>
            <input type="text"
                   :value="searchQuery"
                   @input="onSearchInput"
                   placeholder="Search models..."
                   aria-label="Search models">
            <button v-if="searchQuery"
                    class="search-clear"
                    @click="clearSearch"
                    title="Clear search">&times;</button>
        </div>

        <!-- Actions -->
        <div class="navbar-actions">
            <div class="view-toggle">
                <button class="btn-ghost"
                        :class="{ active: viewMode === 'grid' }"
                        @click="viewMode = 'grid'"
                        title="Grid view"
                        v-html="ICONS.grid"></button>
                <button class="btn-ghost"
                        :class="{ active: viewMode === 'list' }"
                        @click="viewMode = 'list'"
                        title="List view"
                        v-html="ICONS.list"></button>
            </div>
            <!-- Status Indicator -->
            <div class="status-wrapper" @click.stop>
                <button class="btn-icon status-btn" :class="statusDotClass(systemStatus.health)"
                        @click="toggleStatusMenu" title="System Status">
                    <span v-html="ICONS.activity"></span>
                    <span class="status-dot" :class="statusDotClass(systemStatus.health)"></span>
                </button>
            </div>

            <button class="btn-icon" :class="{ active: selectionMode }" @click="toggleSelectionMode" title="Selection mode">
                <span v-html="ICONS.select"></span>
            </button>
            <button class="btn-icon" @click="openSettings" title="Settings" v-html="ICONS.settings"></button>
        </div>
    </nav>

    <!-- ============================================================
         Breadcrumb Bar
         ============================================================ -->
    <div class="breadcrumb-bar">
        <div class="breadcrumb-nav">
            <!-- Root: All Models -->
            <a class="breadcrumb-link" :class="{ active: !hasActiveFilters }" @click="clearFilters">
                <span class="breadcrumb-icon" v-html="ICONS.home"></span>
                All Models
            </a>
            <!-- Filter trail crumbs -->
            <template v-for="(crumb, idx) in breadcrumbTrail" :key="idx">
                <span class="breadcrumb-sep">&rsaquo;</span>
                <a class="breadcrumb-link active" @click="removeBreadcrumb(crumb)">
                    {{ crumb.label }}
                    <span class="breadcrumb-remove">&times;</span>
                </a>
            </template>
        </div>
        <!-- Right side: result count + actions -->
        <div class="breadcrumb-actions">
            <!-- View toggle (shown on mobile, hidden on desktop) -->
            <div class="view-toggle breadcrumb-view-toggle">
                <button class="btn-ghost"
                        :class="{ active: viewMode === 'grid' }"
                        @click="viewMode = 'grid'"
                        title="Grid view"
                        v-html="ICONS.grid"></button>
                <button class="btn-ghost"
                        :class="{ active: viewMode === 'list' }"
                        @click="viewMode = 'list'"
                        title="List view"
                        v-html="ICONS.list"></button>
            </div>
            <button class="btn btn-sm btn-ghost" v-if="searchQuery || filters.tags.length || filters.categories.length || filters.favoritesOnly"
                    @click="showSaveSearchModal = true" title="Save this search">
                <span v-html="ICONS.bookmark"></span> Save
            </button>
            <div class="sort-control">
                <select class="sort-select" :value="filters.sortBy" @change="setSortBy($event.target.value)">
                    <option value="updated_at">Date Modified</option>
                    <option value="created_at">Date Added</option>
                    <option value="name">Name</option>
                    <option value="file_size">File Size</option>
                    <option value="vertex_count">Vertices</option>
                    <option value="face_count">Faces</option>
                </select>
                <button class="btn-icon sort-dir-btn" @click="toggleSortOrder" :title="filters.sortOrder === 'asc' ? 'Ascending' : 'Descending'">
                    {{ filters.sortOrder === 'asc' ? '\u2191' : '\u2193' }}
                </button>
            </div>
            <span class="breadcrumb-count">
                <strong>{{ pagination.total }}</strong> model{{ pagination.total !== 1 ? 's' : '' }}
            </span>
            <button v-if="hasActiveFilters" class="btn btn-sm btn-ghost" @click="clearFilters">Clear all</button>
        </div>
    </div>

    <!-- ============================================================
         Body: Sidebar + Main
         ============================================================ -->
    <div class="app-body">

        <!-- Sidebar backdrop (mobile) -->
        <div v-if="sidebarOpen" class="sidebar-backdrop" @click="sidebarOpen = false"></div>

        <!-- Sidebar -->
        <aside class="sidebar" :class="{ open: sidebarOpen }">

            <!-- Libraries -->
            <div class="sidebar-section" v-if="libraries.length > 0">
                <div class="sidebar-section-title">Libraries</div>
                <div v-for="lib in libraries" :key="lib.id"
                     class="sidebar-item"
                     :class="{ active: filters.library_id === lib.id }"
                     @click="setLibraryFilter(lib.id)">
                    <span class="sidebar-item-icon" v-html="ICONS.folder"></span>
                    <span>{{ lib.name }}</span>
                    <span v-if="lib.model_count != null" class="item-count">{{ lib.model_count }}</span>
                </div>
            </div>

            <!-- Format Filters (collapsible) -->
            <div class="sidebar-section">
                <div class="sidebar-section-title sidebar-section-toggle"
                     @click="collapsedSections.format = !collapsedSections.format">
                    <span>Format</span>
                    <span v-if="filters.format" class="sidebar-section-active-badge">
                        {{ filters.format.toUpperCase() }}
                    </span>
                    <span class="sidebar-section-chevron" :class="{ expanded: !collapsedSections.format }"
                          v-html="ICONS.chevron"></span>
                </div>
                <template v-if="!collapsedSections.format">
                    <label v-for="fmt in ['stl','obj','gltf','glb','3mf','step','stp','ply','fbx','dae','off']"
                           :key="fmt"
                           class="checkbox-item"
                           @click.prevent="setFormatFilter(fmt)">
                        <input type="checkbox" :checked="filters.format === fmt" readonly>
                        <span class="format-badge" :class="formatClass(fmt)">{{ fmt.toUpperCase() }}</span>
                    </label>
                </template>
            </div>

            <!-- Tags -->
            <div class="sidebar-section">
                <div class="sidebar-section-title">Tags</div>
                <div v-if="allTags.length === 0" class="text-muted text-sm" style="padding: 4px 10px;">
                    No tags yet
                </div>
                <div v-for="tag in allTags" :key="tag.id"
                     class="sidebar-item"
                     :class="{ active: filters.tag === tag.name || filters.tags.includes(tag.name) }"
                     @click="toggleTagFilter(tag.name)">
                    <span>{{ tag.name }}</span>
                    <span v-if="tag.model_count != null" class="item-count">{{ tag.model_count }}</span>
                </div>
            </div>

            <!-- Categories -->
            <div class="sidebar-section">
                <div class="sidebar-section-title">Categories</div>
                <div v-if="allCategories.length === 0" class="text-muted text-sm" style="padding: 4px 10px;">
                    No categories yet
                </div>
                <ul class="category-tree">
                    <template v-for="cat in allCategories" :key="cat.id">
                        <li>
                            <div class="category-item"
                                 :class="{ active: filters.category === cat.name || filters.categories.includes(cat.name) }"
                                 @click="toggleCategoryFilter(cat.name)">
                                <span v-if="cat.children && cat.children.length"
                                      class="category-toggle"
                                      :class="{ expanded: expandedCategories[cat.id] }"
                                      @click.stop="toggleCategory(cat.id)"
                                      v-html="ICONS.chevron"></span>
                                <span v-else style="width:16px;display:inline-block"></span>
                                <span class="category-name">{{ cat.name }}</span>
                                <span v-if="cat.model_count" class="category-count">({{ cat.model_count }})</span>
                            </div>
                            <ul v-if="cat.children && cat.children.length && expandedCategories[cat.id]"
                                class="category-children">
                                <li v-for="child in cat.children" :key="child.id">
                                    <div class="category-item"
                                         :class="{ active: filters.category === child.name || filters.categories.includes(child.name) }"
                                         @click="toggleCategoryFilter(child.name)">
                                        <span style="width:16px;display:inline-block"></span>
                                        <span class="category-name">{{ child.name }}</span>
                                        <span v-if="child.model_count" class="category-count">({{ child.model_count }})</span>
                                    </div>
                                    <!-- Third level -->
                                    <ul v-if="child.children && child.children.length && expandedCategories[child.id]"
                                        class="category-children">
                                        <li v-for="grandchild in child.children" :key="grandchild.id">
                                            <div class="category-item"
                                                 :class="{ active: filters.category === grandchild.name || filters.categories.includes(grandchild.name) }"
                                                 @click="toggleCategoryFilter(grandchild.name)">
                                                <span style="width:16px;display:inline-block"></span>
                                                <span class="category-name">{{ grandchild.name }}</span>
                                            </div>
                                        </li>
                                    </ul>
                                </li>
                            </ul>
                        </li>
                    </template>
                </ul>
            </div>

            <!-- Collections -->
            <div class="sidebar-section">
                <div class="sidebar-section-title" style="display:flex;align-items:center;justify-content:space-between">
                    Collections
                    <button class="btn-icon" style="width:20px;height:20px" @click="showCollectionModal = true"
                            title="New collection"><span v-html="ICONS.plus"></span></button>
                </div>
                <div class="sidebar-item" :class="{ active: filters.favoritesOnly }" @click="toggleFavoritesFilter">
                    <span v-html="ICONS.heart"></span>
                    <span>Favorites</span>
                </div>
                <div v-for="col in collections" :key="col.id"
                     class="sidebar-item" :class="{ active: filters.collection === col.id }"
                     @click="setCollectionFilter(col.id)">
                    <span class="collection-dot" :style="{ background: col.color || '#666' }"></span>
                    <span class="truncate">{{ col.name }}</span>
                    <span class="item-count">{{ col.model_count }}</span>
                    <button class="sidebar-item-delete" @click.stop="deleteCollection(col.id)">&times;</button>
                </div>
            </div>

            <!-- Saved Searches -->
            <div class="sidebar-section" v-if="savedSearches.length">
                <div class="sidebar-section-title">Saved Searches</div>
                <div v-for="search in savedSearches" :key="search.id"
                     class="sidebar-item" @click="applySavedSearch(search)">
                    <span v-html="ICONS.bookmark"></span>
                    <span class="truncate">{{ search.name }}</span>
                    <button class="sidebar-item-delete" @click.stop="deleteSavedSearch(search.id)">&times;</button>
                </div>
            </div>
        </aside>

        <!-- Main Content -->
        <main class="main-content">

            <!-- Active Filter Chips -->
            <div class="active-filters" v-if="filters.tags.length || filters.categories.length">
                <template v-for="tag in filters.tags" :key="'tag-'+tag">
                    <span class="filter-chip">
                        Tag: {{ tag }}
                        <button class="chip-remove" @click="removeTagFilter(tag)">&times;</button>
                    </span>
                </template>
                <template v-for="cat in filters.categories" :key="'cat-'+cat">
                    <span class="filter-chip">
                        {{ cat }}
                        <button class="chip-remove" @click="removeCategoryFilter(cat)">&times;</button>
                    </span>
                </template>
            </div>

            <!-- Scan Progress Banner -->
            <div v-if="scanStatus.scanning" class="scan-banner">
                <div class="spinner spinner-sm"></div>
                <span class="scan-text">Scanning library...</span>
                <div class="scan-progress-bar">
                    <div class="scan-progress-fill" :style="{ width: scanProgress + '%' }"></div>
                </div>
                <span class="scan-stats">
                    {{ scanStatus.processed_files }} / {{ scanStatus.total_files }} files
                </span>
            </div>

            <!-- Loading State -->
            <div v-if="loading && models.length === 0" class="loading-overlay">
                <div class="spinner"></div>
                <span>Loading models...</span>
            </div>

            <!-- Empty State -->
            <div v-else-if="!loading && models.length === 0" class="empty-state">
                <div class="empty-icon" v-html="ICONS.cube"></div>
                <div class="empty-title">No models found</div>
                <div class="empty-message" v-if="searchQuery">
                    No results for "{{ searchQuery }}". Try a different search term or adjust your filters.
                </div>
                <div class="empty-message" v-else-if="hasActiveFilters">
                    No models match the current filters. Try clearing some filters.
                </div>
                <div class="empty-message" v-else-if="!hasLibraries">
                    Get started by adding a library. Point YASTL at a local directory containing your 3D model files.
                </div>
                <div class="empty-message" v-else>
                    Your library is empty. Click "Scan" in the toolbar to discover and import 3D models from your directories.
                </div>
                <button v-if="!searchQuery && !hasActiveFilters && !hasLibraries"
                        class="btn btn-primary"
                        @click="openSettings">
                    <span v-html="ICONS.plus"></span>
                    Add Library
                </button>
                <button v-else-if="!searchQuery && !hasActiveFilters && hasLibraries"
                        class="btn btn-primary"
                        @click="triggerScan"
                        :disabled="scanStatus.scanning">
                    <span v-html="ICONS.scan"></span>
                    Scan Library
                </button>
            </div>

            <!-- ============================================================
                 Grid View
                 ============================================================ -->
            <div v-else-if="viewMode === 'grid'" class="models-grid">
                <div v-for="model in models" :key="model.id"
                     class="model-card" :class="{ selected: selectionMode && isSelected(model.id) }" @click="viewModel(model)">
                    <!-- Thumbnail -->
                    <div class="card-thumbnail">
                        <img :src="thumbUrl(model)"
                             :alt="model.name"
                             @error="onThumbError"
                             loading="lazy">
                        <div class="no-thumbnail" style="display:none">
                            <span v-html="ICONS.cube"></span>
                            <span>{{ model.file_format }}</span>
                        </div>
                        <span class="card-format">
                            <span class="format-badge" :class="formatClass(model.file_format)">
                                {{ model.file_format }}
                            </span>
                        </span>
                        <button v-if="!selectionMode" class="card-fav-btn" :class="{ active: model.is_favorite }"
                                @click.stop="toggleFavorite(model, $event)" title="Toggle favorite">
                            <span v-html="model.is_favorite ? ICONS.heartFilled : ICONS.heart"></span>
                        </button>
                        <button v-if="selectionMode" class="card-select-check"
                                @click.stop="toggleModelSelection(model.id)">
                            <span v-html="ICONS.check"></span>
                        </button>
                    </div>
                    <!-- Body -->
                    <div class="card-body">
                        <div class="card-name" :title="model.name">{{ model.name }}</div>
                        <div class="card-meta">{{ formatFileSize(model.file_size) }}</div>
                        <div class="card-tags" v-if="model.tags && model.tags.length">
                            <span v-for="t in model.tags.slice(0, 3)" :key="t" class="tag-chip">{{ t }}</span>
                            <span v-if="model.tags.length > 3" class="tag-chip" style="opacity:0.7">
                                +{{ model.tags.length - 3 }}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ============================================================
                 List View
                 ============================================================ -->
            <div v-else class="models-list">
                <table class="models-table">
                    <thead>
                        <tr>
                            <th v-if="selectionMode" class="col-select" style="width:32px"></th>
                            <th class="col-fav" style="width:32px"></th>
                            <th>Name</th>
                            <th class="col-format">Format</th>
                            <th class="col-vertices">Vertices</th>
                            <th class="col-faces">Faces</th>
                            <th class="col-size">Size</th>
                            <th class="col-date">Date</th>
                            <th class="col-tags">Tags</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="model in models" :key="model.id" :class="{ selected: selectionMode && isSelected(model.id) }" @click="viewModel(model)">
                            <td v-if="selectionMode" class="col-select" @click.stop="toggleModelSelection(model.id)" style="cursor:pointer;text-align:center">
                                <span v-html="ICONS.check" :style="{ opacity: isSelected(model.id) ? 1 : 0.3 }"></span>
                            </td>
                            <td class="col-fav" @click.stop="toggleFavorite(model, $event)" style="cursor:pointer;text-align:center">
                                <span v-html="model.is_favorite ? ICONS.heartFilled : ICONS.heart" :style="{ color: model.is_favorite ? 'var(--danger)' : 'var(--text-muted)' }"></span>
                            </td>
                            <td class="col-name">{{ model.name }}</td>
                            <td class="col-format">
                                <span class="format-badge" :class="formatClass(model.file_format)">
                                    {{ model.file_format }}
                                </span>
                            </td>
                            <td class="col-vertices">{{ formatNumber(model.vertex_count) }}</td>
                            <td class="col-faces">{{ formatNumber(model.face_count) }}</td>
                            <td class="col-size">{{ formatFileSize(model.file_size) }}</td>
                            <td class="col-date">{{ formatDate(model.updated_at || model.created_at) }}</td>
                            <td class="col-tags">
                                <span v-for="t in (model.tags || []).slice(0, 2)" :key="t"
                                      class="tag-chip" style="margin-right:4px">{{ t }}</span>
                                <span v-if="(model.tags || []).length > 2" class="text-muted text-sm">
                                    +{{ model.tags.length - 2 }}
                                </span>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Load More / Pagination Info -->
            <div v-if="models.length > 0 && !loading" class="pagination-info">
                Showing {{ shownCount }} of {{ pagination.total }} models
            </div>
            <div v-if="hasMore" class="load-more-container">
                <button class="btn btn-secondary" @click="loadMore" :disabled="loading">
                    Load More
                </button>
            </div>

            <!-- Loading indicator when loading more -->
            <div v-if="loading && models.length > 0" class="loading-overlay" style="padding:20px">
                <div class="spinner spinner-sm"></div>
            </div>
        </main>
    </div>

    <!-- ============================================================
         Detail Modal / Overlay
         ============================================================ -->
    <div v-if="showDetail && selectedModel" class="detail-overlay" @click.self="closeDetail">
        <div class="detail-panel">
            <!-- Header -->
            <div class="detail-header">
                <div class="detail-title">
                    <template v-if="!isEditingName">
                        <span @dblclick="startEditName" title="Double-click to edit">
                            {{ selectedModel.name }}
                        </span>
                    </template>
                    <template v-else>
                        <input type="text"
                               v-model="editName"
                               @blur="saveName"
                               @keydown.enter="saveName"
                               @keydown.escape="isEditingName = false"
                               style="width:100%;padding:4px 8px;background:var(--bg-input);border:1px solid var(--accent);border-radius:4px;color:var(--text-primary);font-size:1.1rem;font-weight:600"
                               autofocus>
                    </template>
                </div>
                <button class="btn btn-sm btn-ghost" :class="{ 'text-danger': selectedModel.is_favorite }"
                        @click="toggleFavorite(selectedModel, $event)" title="Toggle favorite">
                    <span v-html="selectedModel.is_favorite ? ICONS.heartFilled : ICONS.heart"></span>
                </button>
                <button class="close-btn" @click="closeDetail" title="Close">&times;</button>
            </div>

            <!-- Content: Viewer + Info -->
            <div class="detail-content">
                <!-- 3D Viewer -->
                <div class="detail-viewer">
                    <div id="viewer-container">
                        <!-- Viewer loading -->
                        <div v-if="viewerLoading" class="viewer-loading">
                            <div class="spinner"></div>
                            <span>Loading 3D model...</span>
                        </div>
                    </div>
                    <!-- Viewer toolbar -->
                    <div class="viewer-toolbar">
                        <button class="btn" @click="handleResetView">Reset View</button>
                    </div>
                </div>

                <!-- Info Panel -->
                <div class="detail-info">

                    <!-- Duplicate Warning -->
                    <div v-if="selectedModel.file_hash" class="duplicate-warning" style="display:none">
                        <span v-html="ICONS.warning"></span>
                        <span>This file has duplicates in the library.</span>
                    </div>

                    <!-- Description -->
                    <div class="info-section">
                        <div class="info-section-title">Description</div>
                        <div v-if="!isEditingDesc"
                             @dblclick="startEditDesc"
                             style="cursor:pointer;min-height:36px;font-size:0.85rem;color:var(--text-secondary);padding:4px 0">
                            {{ selectedModel.description || 'Double-click to add a description...' }}
                        </div>
                        <div v-else class="editable-field">
                            <textarea v-model="editDesc"
                                      rows="3"
                                      @blur="saveDesc"
                                      @keydown.escape="isEditingDesc = false"
                                      placeholder="Enter description..."
                                      autofocus></textarea>
                        </div>
                    </div>

                    <!-- File Information -->
                    <div class="info-section">
                        <div class="info-section-title">File Information</div>
                        <div class="info-field">
                            <span class="field-label">Format</span>
                            <span class="field-value">
                                <span class="format-badge" :class="formatClass(selectedModel.file_format)">
                                    {{ selectedModel.file_format }}
                                </span>
                            </span>
                        </div>
                        <div class="info-field">
                            <span class="field-label">Size</span>
                            <span class="field-value">{{ formatFileSize(selectedModel.file_size) }}</span>
                        </div>
                        <div class="info-field">
                            <span class="field-label">Vertices</span>
                            <span class="field-value">{{ formatNumber(selectedModel.vertex_count) }}</span>
                        </div>
                        <div class="info-field">
                            <span class="field-label">Faces</span>
                            <span class="field-value">{{ formatNumber(selectedModel.face_count) }}</span>
                        </div>
                        <div class="info-field">
                            <span class="field-label">Dimensions</span>
                            <span class="field-value">
                                {{ formatDimensions(selectedModel.dimensions_x, selectedModel.dimensions_y, selectedModel.dimensions_z) }}
                            </span>
                        </div>
                        <div class="info-field" style="margin-top:4px">
                            <span class="field-label">Path</span>
                            <span class="field-value field-value-path">
                                {{ selectedModel.file_path }}
                            </span>
                        </div>
                        <div v-if="selectedModel.file_hash" class="info-field">
                            <span class="field-label">Hash</span>
                            <span class="field-value field-value-hash">
                                {{ selectedModel.file_hash }}
                            </span>
                        </div>
                    </div>

                    <!-- Tags -->
                    <div class="info-section">
                        <div class="info-section-title">Tags</div>
                        <div class="tags-list">
                            <span v-for="tag in (selectedModel.tags || [])" :key="tag" class="tag-chip">
                                {{ tag }}
                                <button class="tag-remove" @click="removeTag(tag)" title="Remove tag">&times;</button>
                            </span>
                            <span v-if="!selectedModel.tags || !selectedModel.tags.length"
                                  class="text-muted text-sm">No tags</span>
                        </div>
                        <div class="tag-add-row">
                            <input type="text"
                                   v-model="newTagInput"
                                   placeholder="Add tag..."
                                   @keydown.enter="addTag">
                            <button class="btn btn-sm btn-primary" @click="addTag">Add</button>
                        </div>
                    </div>

                    <!-- Categories -->
                    <div class="info-section">
                        <div class="info-section-title">Categories</div>
                        <div class="tags-list">
                            <span v-for="cat in (selectedModel.categories || [])" :key="cat"
                                  class="tag-chip" style="background:var(--bg-primary);color:var(--text-secondary);border:1px solid var(--border)">
                                {{ cat }}
                            </span>
                            <span v-if="!selectedModel.categories || !selectedModel.categories.length"
                                  class="text-muted text-sm">Uncategorized</span>
                        </div>
                    </div>

                    <!-- Actions -->
                    <div class="detail-actions">
                        <a class="btn btn-secondary" style="flex:1"
                           :href="'/api/models/' + selectedModel.id + '/download'"
                           download>
                            <span v-html="ICONS.download"></span>
                            Download {{ selectedModel.file_format ? selectedModel.file_format.toUpperCase() : '' }}
                        </a>
                        <button class="btn btn-danger" style="flex:1" @click="deleteModel(selectedModel)">
                            <span v-html="ICONS.trash"></span>
                            Delete
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ============================================================
         Settings Modal
         ============================================================ -->
    <div v-if="showSettings" class="detail-overlay" @click.self="closeSettings">
        <div class="settings-panel">
            <!-- Header -->
            <div class="detail-header">
                <div class="detail-title">Settings</div>
                <button class="close-btn" @click="closeSettings" title="Close">&times;</button>
            </div>

            <div class="settings-content">
                <!-- Libraries Section -->
                <div class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.folder"></span>
                        Libraries
                    </div>
                    <div class="settings-section-desc">
                        Add local directories containing your 3D model files. YASTL will scan these paths to discover and index models.
                    </div>

                    <!-- Existing Libraries -->
                    <div v-if="libraries.length > 0" class="library-list">
                        <div v-for="lib in libraries" :key="lib.id" class="library-item">
                            <div class="library-info">
                                <div class="library-name">{{ lib.name }}</div>
                                <div class="library-path">{{ lib.path }}</div>
                            </div>
                            <button class="btn-icon btn-icon-danger" @click="deleteLibrary(lib)" title="Remove library">
                                <span v-html="ICONS.trash"></span>
                            </button>
                        </div>
                    </div>
                    <div v-else class="text-muted text-sm" style="padding:12px 0">
                        No libraries configured yet. Add one below to get started.
                    </div>

                    <!-- Scan Libraries -->
                    <div v-if="libraries.length > 0" style="padding: 0 0 12px 0;">
                        <button class="btn btn-primary"
                                @click="triggerScan"
                                :disabled="scanStatus.scanning"
                                title="Scan libraries for new models">
                            <span v-html="ICONS.scan"></span>
                            {{ scanStatus.scanning ? 'Scanning...' : 'Scan Libraries' }}
                        </button>
                        <div v-if="scanStatus.scanning" class="text-muted text-sm" style="margin-top:6px">
                            {{ scanStatus.processed_files }} / {{ scanStatus.total_files }} files processed
                        </div>
                    </div>

                    <!-- Add Library Form -->
                    <div class="add-library-form">
                        <div class="form-row">
                            <label class="form-label">Library Name</label>
                            <input type="text"
                                   v-model="newLibName"
                                   placeholder="e.g. My 3D Models"
                                   class="form-input">
                        </div>
                        <div class="form-row">
                            <label class="form-label">Local Path</label>
                            <input type="text"
                                   v-model="newLibPath"
                                   placeholder="e.g. /home/user/models"
                                   class="form-input"
                                   @keydown.enter="addLibrary">
                        </div>
                        <button class="btn btn-primary"
                                @click="addLibrary"
                                :disabled="addingLibrary || !newLibName.trim() || !newLibPath.trim()">
                            <span v-html="ICONS.plus"></span>
                            Add Library
                        </button>
                    </div>
                </div>

                <!-- Thumbnails Section -->
                <div class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.image"></span>
                        Thumbnails
                    </div>
                    <div class="settings-section-desc">
                        Choose how model preview thumbnails are rendered. Solid mode shows filled faces with lighting; wireframe shows edges only.
                    </div>

                    <div class="thumbnail-mode-options">
                        <label class="thumbnail-mode-option" :class="{ active: thumbnailMode === 'wireframe' }" @click="setThumbnailMode('wireframe')">
                            <input type="radio" name="thumbnailMode" value="wireframe" :checked="thumbnailMode === 'wireframe'">
                            <div class="thumbnail-mode-info">
                                <div class="thumbnail-mode-label">Wireframe</div>
                                <div class="thumbnail-mode-desc">Edges and outlines only</div>
                            </div>
                        </label>
                        <label class="thumbnail-mode-option" :class="{ active: thumbnailMode === 'solid' }" @click="setThumbnailMode('solid')">
                            <input type="radio" name="thumbnailMode" value="solid" :checked="thumbnailMode === 'solid'">
                            <div class="thumbnail-mode-info">
                                <div class="thumbnail-mode-label">Solid</div>
                                <div class="thumbnail-mode-desc">Filled faces with lighting</div>
                            </div>
                        </label>
                    </div>

                    <div class="settings-section-desc" style="margin-top:12px">
                        Rendering quality. Fast uses a simple painter's algorithm. Quality uses a z-buffer rasterizer with smooth shading (slower, especially for high-poly models).
                    </div>

                    <div class="thumbnail-mode-options">
                        <label class="thumbnail-mode-option" :class="{ active: thumbnailQuality === 'fast' }" @click="setThumbnailQuality('fast')">
                            <input type="radio" name="thumbnailQuality" value="fast" :checked="thumbnailQuality === 'fast'">
                            <div class="thumbnail-mode-info">
                                <div class="thumbnail-mode-label">Fast</div>
                                <div class="thumbnail-mode-desc">Quick rendering, good for most models</div>
                            </div>
                        </label>
                        <label class="thumbnail-mode-option" :class="{ active: thumbnailQuality === 'quality' }" @click="setThumbnailQuality('quality')">
                            <input type="radio" name="thumbnailQuality" value="quality" :checked="thumbnailQuality === 'quality'">
                            <div class="thumbnail-mode-info">
                                <div class="thumbnail-mode-label">Quality</div>
                                <div class="thumbnail-mode-desc">Z-buffer with smooth shading, slower</div>
                            </div>
                        </label>
                    </div>

                    <div class="thumbnail-regen-row">
                        <button class="btn btn-secondary"
                                @click="regenerateThumbnails"
                                :disabled="regeneratingThumbnails">
                            <span v-html="ICONS.refresh"></span>
                            Regenerate All Thumbnails
                        </button>
                        <span class="text-muted text-sm">Re-render existing thumbnails with the current mode and quality</span>
                    </div>
                </div>

                <!-- Update Section -->
                <div class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.refresh"></span>
                        Updates
                    </div>
                    <div class="settings-section-desc">
                        Check for and apply updates from the remote repository. The service will restart automatically after updating.
                    </div>

                    <!-- Not a git repo -->
                    <div v-if="updateInfo.checked && !updateInfo.is_git_repo" class="update-status update-status-unavailable">
                        <div class="update-status-icon">
                            <span v-html="ICONS.warning"></span>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Updates unavailable</div>
                            <div class="update-status-detail">
                                Not running from a git repository. Updates require a git-based installation.
                            </div>
                        </div>
                    </div>

                    <!-- Restarting -->
                    <div v-else-if="updateInfo.restarting" class="update-status update-status-restarting">
                        <div class="update-status-icon">
                            <div class="spinner spinner-sm"></div>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Restarting...</div>
                            <div class="update-status-detail">
                                YASTL is restarting with the latest changes. This page will reload automatically.
                            </div>
                        </div>
                    </div>

                    <!-- Applying update -->
                    <div v-else-if="updateInfo.applying" class="update-status update-status-applying">
                        <div class="update-status-icon">
                            <div class="spinner spinner-sm"></div>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Applying update...</div>
                            <div class="update-status-detail">
                                Pulling changes and reinstalling dependencies.
                            </div>
                        </div>
                    </div>

                    <!-- Checking -->
                    <div v-else-if="updateInfo.checking" class="update-status update-status-checking">
                        <div class="update-status-icon">
                            <div class="spinner spinner-sm"></div>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Checking for updates...</div>
                        </div>
                    </div>

                    <!-- Update available -->
                    <div v-else-if="updateInfo.update_available" class="update-status update-status-available">
                        <div class="update-status-header">
                            <div class="update-status-icon update-icon-available">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="12" y2="16"/><line x1="16" y1="12" x2="12" y2="16"/></svg>
                            </div>
                            <div class="update-status-text">
                                <div class="update-status-title">Update available</div>
                                <div class="update-status-detail">
                                    {{ updateInfo.commits_behind }} new commit{{ updateInfo.commits_behind !== 1 ? 's' : '' }}
                                    on <code>{{ updateInfo.branch }}</code>
                                </div>
                            </div>
                        </div>
                        <!-- Commit list -->
                        <div v-if="updateInfo.commits.length" class="update-commits">
                            <div v-for="commit in updateInfo.commits" :key="commit.sha" class="update-commit">
                                <code class="commit-sha">{{ commit.sha }}</code>
                                <span class="commit-message">{{ commit.message }}</span>
                                <span class="commit-meta">{{ commit.author }} &middot; {{ commit.date }}</span>
                            </div>
                        </div>
                        <button class="btn btn-primary update-apply-btn"
                                @click="applyUpdate"
                                :disabled="updateInfo.applying">
                            <span v-html="ICONS.download"></span>
                            Update &amp; Restart
                        </button>
                    </div>

                    <!-- Up to date -->
                    <div v-else-if="updateInfo.checked && !updateInfo.error" class="update-status update-status-current">
                        <div class="update-status-icon update-icon-current">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="8 12 11 15 16 9"/></svg>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Up to date</div>
                            <div class="update-status-detail">
                                v{{ updateInfo.current_version }}
                                <span v-if="updateInfo.current_sha" class="text-muted">
                                    &middot; {{ updateInfo.current_sha.substring(0, 8) }}
                                </span>
                                <span v-if="updateInfo.branch" class="text-muted">
                                    &middot; {{ updateInfo.branch }}
                                </span>
                            </div>
                        </div>
                    </div>

                    <!-- Error -->
                    <div v-if="updateInfo.error" class="update-error">
                        <span v-html="ICONS.warning"></span>
                        {{ updateInfo.error }}
                    </div>

                    <!-- Check button -->
                    <button class="btn btn-secondary update-check-btn"
                            @click="checkForUpdates"
                            :disabled="updateInfo.checking || updateInfo.applying || updateInfo.restarting">
                        <span v-html="ICONS.refresh"></span>
                        Check for Updates
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- ============================================================
         Status Menu (teleported to body to avoid navbar stacking context)
         ============================================================ -->
    <teleport to="body">
        <div v-if="showStatusMenu" class="status-menu-backdrop" @click="showStatusMenu = false"></div>
        <div v-if="showStatusMenu" class="status-menu" @click.stop>
            <div class="status-menu-header">
                <span>System Status</span>
                <span class="status-badge" :class="statusDotClass(systemStatus.health)">
                    {{ statusLabel(systemStatus.health) }}
                </span>
            </div>
            <div class="status-menu-items">
                <!-- Scanner -->
                <div class="status-menu-item">
                    <span class="status-item-icon" v-html="ICONS.scan"></span>
                    <span class="status-item-label">Scanner</span>
                    <span class="status-item-value" :class="statusDotClass(systemStatus.scanner.status)">
                        {{ statusLabel(systemStatus.scanner.status) }}
                    </span>
                </div>
                <div v-if="systemStatus.scanner.is_scanning" class="status-menu-detail">
                    {{ systemStatus.scanner.processed_files }} / {{ systemStatus.scanner.total_files }} files
                </div>

                <!-- File Watcher -->
                <div class="status-menu-item">
                    <span class="status-item-icon" v-html="ICONS.eye"></span>
                    <span class="status-item-label">File Watcher</span>
                    <span class="status-item-value" :class="statusDotClass(systemStatus.watcher.status)">
                        {{ statusLabel(systemStatus.watcher.status) }}
                    </span>
                </div>
                <div v-if="systemStatus.watcher.watched_count" class="status-menu-detail">
                    {{ systemStatus.watcher.watched_count }} path{{ systemStatus.watcher.watched_count !== 1 ? 's' : '' }} monitored
                </div>

                <!-- Database -->
                <div class="status-menu-item">
                    <span class="status-item-icon" v-html="ICONS.database"></span>
                    <span class="status-item-label">Database</span>
                    <span class="status-item-value" :class="statusDotClass(systemStatus.database.status)">
                        {{ statusLabel(systemStatus.database.status) }}
                    </span>
                </div>
                <div v-if="systemStatus.database.total_models != null" class="status-menu-detail">
                    {{ systemStatus.database.total_models }} models &middot; {{ systemStatus.database.total_libraries }} libraries
                </div>

                <!-- Thumbnails -->
                <div class="status-menu-item">
                    <span class="status-item-icon" v-html="ICONS.image"></span>
                    <span class="status-item-label">Thumbnails</span>
                    <span class="status-item-value" :class="statusDotClass(systemStatus.thumbnails.status)">
                        {{ statusLabel(systemStatus.thumbnails.status) }}
                    </span>
                </div>
                <div v-if="systemStatus.thumbnails.total_cached != null" class="status-menu-detail">
                    {{ systemStatus.thumbnails.total_cached }} cached
                </div>
            </div>
        </div>
    </teleport>

    <!-- ============================================================
         Selection Bar
         ============================================================ -->
    <div v-if="selectionMode && selectedModels.size > 0" class="selection-bar">
        <div class="selection-info">
            <strong>{{ selectedModels.size }}</strong> selected
            <button class="btn btn-sm btn-ghost" @click="selectAll">Select All</button>
            <button class="btn btn-sm btn-ghost" @click="deselectAll">Deselect All</button>
        </div>
        <div class="selection-actions">
            <button class="btn btn-sm btn-primary" @click="bulkFavorite">
                <span v-html="ICONS.heart"></span> Favorite
            </button>
            <button class="btn btn-sm btn-secondary" @click="openBulkAddToCollection">
                <span v-html="ICONS.collection"></span> Collection
            </button>
            <button class="btn btn-sm btn-danger" @click="bulkDelete">
                <span v-html="ICONS.trash"></span> Delete
            </button>
        </div>
    </div>

    <!-- ============================================================
         Create Collection Modal
         ============================================================ -->
    <div v-if="showCollectionModal" class="detail-overlay" @click.self="showCollectionModal = false">
        <div class="mini-modal">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
                <h3 style="margin:0">New Collection</h3>
                <button class="close-btn" @click="showCollectionModal = false">&times;</button>
            </div>
            <div class="form-row">
                <label class="form-label">Name</label>
                <input class="form-input" v-model="newCollectionName" placeholder="Collection name"
                       @keydown.enter="createCollection">
            </div>
            <div class="form-row">
                <label class="form-label">Color</label>
                <input type="color" v-model="newCollectionColor" style="width:48px;height:32px;border:none;cursor:pointer">
            </div>
            <div class="form-actions">
                <button class="btn btn-secondary" @click="showCollectionModal = false">Cancel</button>
                <button class="btn btn-primary" @click="createCollection">Create</button>
            </div>
        </div>
    </div>

    <!-- ============================================================
         Add to Collection Modal
         ============================================================ -->
    <div v-if="showAddToCollectionModal" class="detail-overlay" @click.self="showAddToCollectionModal = false">
        <div class="mini-modal">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
                <h3 style="margin:0">Add to Collection</h3>
                <button class="close-btn" @click="showAddToCollectionModal = false">&times;</button>
            </div>
            <div v-if="collections.length === 0" class="text-muted text-sm" style="padding:16px 0;text-align:center">
                No collections yet. Create one first.
            </div>
            <div v-for="col in collections" :key="col.id"
                 class="sidebar-item" @click="handleCollectionSelect(col.id)">
                <span class="collection-dot" :style="{ background: col.color || '#666' }"></span>
                <span>{{ col.name }}</span>
                <span class="item-count">{{ col.model_count }}</span>
            </div>
        </div>
    </div>

    <!-- ============================================================
         Save Search Modal
         ============================================================ -->
    <div v-if="showSaveSearchModal" class="detail-overlay" @click.self="showSaveSearchModal = false">
        <div class="mini-modal">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
                <h3 style="margin:0">Save Search</h3>
                <button class="close-btn" @click="showSaveSearchModal = false">&times;</button>
            </div>
            <div class="form-row">
                <label class="form-label">Name</label>
                <input class="form-input" v-model="saveSearchName" placeholder="Search name"
                       @keydown.enter="saveCurrentSearch">
            </div>
            <div class="form-actions">
                <button class="btn btn-secondary" @click="showSaveSearchModal = false">Cancel</button>
                <button class="btn btn-primary" @click="saveCurrentSearch">Save</button>
            </div>
        </div>
    </div>

    <!-- ============================================================
         Toast Notifications
         ============================================================ -->
    <div class="toast-container">
        <div v-for="toast in toasts" :key="toast.id"
             class="toast" :class="'toast-' + toast.type">
            {{ toast.message }}
        </div>
    </div>
</div>
    `,
});

app.mount('#app');
