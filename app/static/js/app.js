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
    link: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
    copy: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
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
        const tagSuggestions = ref([]);
        const tagSuggestionsLoading = ref(false);
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
            duplicatesOnly: false,
            collection: null,
            sortBy: 'updated_at',
            sortOrder: 'desc',
        });

        const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];
        const savedPageSize = parseInt(localStorage.getItem('yastl_page_size')) || 50;

        const pagination = reactive({
            limit: PAGE_SIZE_OPTIONS.includes(savedPageSize) ? savedPageSize : 50,
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
        const regeneratingThumbnails = ref(false);

        // Thumbnail regeneration progress
        const regenProgress = reactive({
            running: false,
            total: 0,
            completed: 0,
        });
        let regenPollTimer = null;

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

        // Favorites count
        const favoritesCount = ref(0);

        // Catalog system: Collections
        const collections = ref([]);
        const COLLECTION_COLORS = [
            '#0f9b8e', '#e06c75', '#61afef', '#e5c07b', '#c678dd',
            '#56b6c2', '#d19a66', '#98c379', '#be5046', '#7c8fa6',
            '#e06898', '#36b37e', '#6c5ce7', '#f39c12', '#00b894',
        ];

        const showCollectionModal = ref(false);
        const newCollectionName = ref('');
        const newCollectionColor = ref('#0f9b8e');
        const addToCollectionModelId = ref(null);
        const showAddToCollectionModal = ref(false);
        const editingCollectionId = ref(null);
        const editCollectionName = ref('');

        // Catalog system: Saved searches
        const savedSearches = ref([]);
        const showSaveSearchModal = ref(false);
        const saveSearchName = ref('');

        // Catalog system: Selection mode
        const selectionMode = ref(false);
        const selectedModels = reactive(new Set());

        // Bulk tag modal
        const showBulkTagModal = ref(false);
        const bulkTagInput = ref('');

        // URL Import
        const showImportModal = ref(false);
        const importMode = ref('url');  // 'url' or 'file'
        const importUrls = ref('');
        const importLibraryId = ref(null);
        const importSubfolder = ref('');
        const importRunning = ref(false);
        const importDone = ref(false);
        const importPreview = reactive({ loading: false, data: null });
        const importProgress = reactive({ running: false, total: 0, completed: 0, current_url: null, results: [] });
        const uploadFiles = ref([]);
        const uploadResults = ref([]);
        let importPollTimer = null;

        // Import credentials
        const importCredentials = ref({});
        const credentialInputs = reactive({});

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
            return !!(filters.format || filters.tag || filters.category || filters.library_id || filters.tags.length || filters.categories.length || filters.favoritesOnly || filters.duplicatesOnly || filters.collection);
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
                if (filters.duplicatesOnly) params.append('duplicates_only', 'true');
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
                busy: 'Busy',
                idle: 'Idle',
                scanning: 'Scanning',
                watching: 'Watching',
                regenerating: 'Regenerating',
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
            if (['busy', 'scanning', 'degraded', 'regenerating'].includes(status)) return 'status-dot-warn';
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

        async function regenerateThumbnails() {
            if (!confirm('Regenerate all thumbnails?\n\nThis will re-render every model thumbnail using the current mode. This runs in the background.')) {
                return;
            }
            regeneratingThumbnails.value = true;
            try {
                const res = await fetch('/api/settings/regenerate-thumbnails', { method: 'POST' });
                if (res.ok) {
                    showToast('Thumbnail regeneration started', 'info');
                    startRegenPolling();
                } else {
                    const data = await res.json();
                    showToast(data.detail || 'Failed to start regeneration', 'error');
                    regeneratingThumbnails.value = false;
                }
            } catch (err) {
                showToast('Failed to start thumbnail regeneration', 'error');
                console.error('regenerateThumbnails error:', err);
                regeneratingThumbnails.value = false;
            }
        }

        function startRegenPolling() {
            if (regenPollTimer) clearInterval(regenPollTimer);
            regenPollTimer = setInterval(async () => {
                try {
                    const res = await fetch('/api/settings/regenerate-thumbnails/status');
                    if (!res.ok) return;
                    const data = await res.json();
                    regenProgress.running = data.running;
                    regenProgress.total = data.total;
                    regenProgress.completed = data.completed;
                    if (!data.running) {
                        clearInterval(regenPollTimer);
                        regenPollTimer = null;
                        regeneratingThumbnails.value = false;
                        showToast('Thumbnail regeneration complete');
                        fetchModels();
                    }
                } catch (err) {
                    console.error('regenPoll error:', err);
                }
            }, 2000);
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
           URL Import
           ============================================================== */

        function openImportModal() {
            fetchLibraries();
            importMode.value = 'url';
            importUrls.value = '';
            importSubfolder.value = '';
            importPreview.loading = false;
            importPreview.data = null;
            importDone.value = false;
            importProgress.results = [];
            uploadFiles.value = [];
            uploadResults.value = [];
            // Default to first library if available
            if (libraries.value.length > 0 && !importLibraryId.value) {
                importLibraryId.value = libraries.value[0].id;
            }
            showImportModal.value = true;
            document.body.classList.add('modal-open');
        }

        function closeImportModal() {
            showImportModal.value = false;
            if (!showDetail.value && !showSettings.value) {
                document.body.classList.remove('modal-open');
            }
        }

        async function previewImportUrl() {
            const lines = importUrls.value.split('\n').map(u => u.trim()).filter(Boolean);
            if (!lines.length) return;
            const firstUrl = lines[0];
            importPreview.loading = true;
            importPreview.data = null;
            try {
                const res = await fetch('/api/import/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: firstUrl }),
                });
                if (res.ok) {
                    importPreview.data = await res.json();
                } else {
                    const err = await res.json();
                    importPreview.data = { error: err.detail || 'Preview failed' };
                }
            } catch (e) {
                importPreview.data = { error: 'Network error' };
            } finally {
                importPreview.loading = false;
            }
        }

        async function startImport() {
            const urls = importUrls.value.split('\n').map(u => u.trim()).filter(Boolean);
            if (!urls.length || !importLibraryId.value) return;

            importRunning.value = true;
            try {
                const res = await fetch('/api/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        urls,
                        library_id: importLibraryId.value,
                        subfolder: importSubfolder.value || null,
                    }),
                });
                if (res.ok) {
                    showToast(`Importing ${urls.length} URL(s)...`, 'info');
                    startImportPolling();
                } else {
                    const data = await res.json();
                    showToast(data.detail || 'Import failed', 'error');
                    importRunning.value = false;
                }
            } catch (e) {
                showToast('Failed to start import', 'error');
                importRunning.value = false;
            }
        }

        function startImportPolling() {
            if (importPollTimer) clearInterval(importPollTimer);
            importPollTimer = setInterval(async () => {
                try {
                    const res = await fetch('/api/import/status');
                    if (!res.ok) return;
                    const data = await res.json();
                    importProgress.running = data.running;
                    importProgress.total = data.total;
                    importProgress.completed = data.completed;
                    importProgress.current_url = data.current_url;
                    importProgress.results = data.results || [];
                    if (!data.running) {
                        clearInterval(importPollTimer);
                        importPollTimer = null;
                        importRunning.value = false;
                        importDone.value = true;
                        fetchModels();
                        fetchTags();
                        fetchCategories();
                    }
                } catch (e) {
                    console.error('importPoll error:', e);
                }
            }, 2000);
        }

        function onFilesSelected(event) {
            uploadFiles.value = Array.from(event.target.files || []);
        }

        async function startUpload() {
            if (!uploadFiles.value.length || !importLibraryId.value) return;
            importRunning.value = true;
            importDone.value = false;
            uploadResults.value = [];

            const formData = new FormData();
            formData.append('library_id', importLibraryId.value);
            if (importSubfolder.value) formData.append('subfolder', importSubfolder.value);
            for (const f of uploadFiles.value) {
                formData.append('files', f);
            }

            try {
                const res = await fetch('/api/import/upload', {
                    method: 'POST',
                    body: formData,
                });
                if (res.ok) {
                    const data = await res.json();
                    uploadResults.value = data.results || [];
                    importDone.value = true;
                    fetchModels();
                    fetchTags();
                    fetchCategories();
                } else {
                    const err = await res.json();
                    showToast(err.detail || 'Upload failed', 'error');
                }
            } catch (e) {
                showToast('Upload failed', 'error');
            } finally {
                importRunning.value = false;
            }
        }

        async function fetchImportCredentials() {
            try {
                const res = await fetch('/api/import/credentials');
                if (res.ok) {
                    importCredentials.value = await res.json();
                }
            } catch (e) {
                console.error('fetchImportCredentials error:', e);
            }
        }

        async function saveImportCredential(site, key) {
            const value = (credentialInputs[site] || '').trim();
            if (!value) {
                showToast('Please enter a value first', 'error');
                return;
            }
            try {
                const creds = {};
                creds[key] = value;
                const res = await fetch('/api/import/credentials', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ site, credentials: creds }),
                });
                if (res.ok) {
                    importCredentials.value = await res.json();
                    credentialInputs[site] = '';
                    showToast(`${site} credentials saved`);
                } else {
                    const data = await res.json();
                    showToast(data.detail || 'Failed to save credentials', 'error');
                }
            } catch (e) {
                showToast('Failed to save credentials', 'error');
            }
        }

        async function deleteImportCredential(site) {
            try {
                const res = await fetch(`/api/import/credentials/${site}`, { method: 'DELETE' });
                if (res.ok) {
                    importCredentials.value = await res.json();
                    showToast(`${site} credentials removed`);
                }
            } catch (e) {
                showToast('Failed to remove credentials', 'error');
            }
        }

        /* ==============================================================
           Duplicate filter toggle
           ============================================================== */

        function toggleDuplicatesFilter() {
            filters.duplicatesOnly = !filters.duplicatesOnly;
            pagination.offset = 0;
            fetchModels();
        }

        /* ==============================================================
           Tag Suggestions
           ============================================================== */

        async function fetchTagSuggestions() {
            if (!selectedModel.value) return;
            tagSuggestionsLoading.value = true;
            tagSuggestions.value = [];
            try {
                const res = await fetch(`/api/models/suggest-tags/${selectedModel.value.id}`);
                if (res.ok) {
                    const data = await res.json();
                    tagSuggestions.value = data.suggestions || [];
                }
            } catch (e) {
                console.error('fetchTagSuggestions error:', e);
            } finally {
                tagSuggestionsLoading.value = false;
            }
        }

        async function applyTagSuggestion(tag) {
            // Add the suggested tag to the model
            newTagInput.value = tag;
            await addTag();
            // Remove from suggestions list
            tagSuggestions.value = tagSuggestions.value.filter(t => t !== tag);
        }

        async function bulkAutoTag() {
            const ids = [...selectedModels];
            if (!ids.length) return;
            try {
                const res = await fetch('/api/bulk/auto-tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_ids: ids }),
                });
                if (res.ok) {
                    const data = await res.json();
                    showToast(`Auto-tagged ${data.models_tagged} model(s) with ${data.tags_added} tags`, 'success');
                    selectedModels.clear();
                    selectionMode.value = false;
                    await fetchModels();
                    await fetchTags();
                } else {
                    showToast('Auto-tag failed', 'error');
                }
            } catch {
                showToast('Auto-tag failed', 'error');
            }
        }

        async function bulkAddTags() {
            const ids = [...selectedModels];
            const tagsStr = bulkTagInput.value.trim();
            if (!ids.length || !tagsStr) return;
            const tags = tagsStr.split(',').map(t => t.trim()).filter(Boolean);
            if (!tags.length) return;
            try {
                const res = await fetch('/api/bulk/tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_ids: ids, tags }),
                });
                if (res.ok) {
                    showToast(`Tags applied to ${ids.length} model(s)`, 'success');
                    showBulkTagModal.value = false;
                    bulkTagInput.value = '';
                    selectedModels.clear();
                    selectionMode.value = false;
                    await fetchModels();
                    await fetchTags();
                } else {
                    showToast('Bulk tag failed', 'error');
                }
            } catch {
                showToast('Bulk tag failed', 'error');
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
            tagSuggestions.value = [];
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
            filters.duplicatesOnly = false;
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

        function setPageSize(size) {
            const val = parseInt(size);
            if (!PAGE_SIZE_OPTIONS.includes(val)) return;
            pagination.limit = val;
            pagination.offset = 0;
            localStorage.setItem('yastl_page_size', String(val));
            if (searchQuery.value.trim()) {
                searchModels();
            } else {
                fetchModels();
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

        function zipName(model) {
            if (!model.zip_path) return '';
            const parts = model.zip_path.replace(/\\/g, '/').split('/');
            const filename = parts[parts.length - 1] || '';
            return filename.replace(/\.zip$/i, '');
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

        function thumbnailStatus(model) {
            if (!model.thumbnail_path) return 'missing';
            if (!model.thumbnail_mode) return 'stale';
            if (model.thumbnail_mode !== thumbnailMode.value) return 'stale';
            return 'current';
        }

        function thumbStatusClass(model) {
            const s = thumbnailStatus(model);
            if (s === 'current') return 'thumb-status-current';
            if (s === 'stale') return 'thumb-status-stale';
            return 'thumb-status-missing';
        }

        function thumbStatusTitle(model) {
            const s = thumbnailStatus(model);
            if (s === 'current') return 'Thumbnail is up to date';
            if (s === 'stale') return 'Thumbnail was generated with different settings';
            return 'No thumbnail';
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

        // ---- Favorites count ----
        async function fetchFavoritesCount() {
            try {
                const resp = await fetch('/api/favorites?limit=1&offset=0');
                const data = await resp.json();
                favoritesCount.value = data.total || 0;
            } catch (e) {
                console.error('Failed to fetch favorites count', e);
            }
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

        function pickNextCollectionColor() {
            const used = new Set(collections.value.map(c => (c.color || '').toLowerCase()));
            return COLLECTION_COLORS.find(c => !used.has(c.toLowerCase())) || COLLECTION_COLORS[0];
        }

        function openCollectionModal() {
            newCollectionName.value = '';
            newCollectionColor.value = pickNextCollectionColor();
            showCollectionModal.value = true;
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

        function startEditCollection(col) {
            editingCollectionId.value = col.id;
            editCollectionName.value = col.name;
        }

        async function saveCollectionName(col) {
            const newName = editCollectionName.value.trim();
            editingCollectionId.value = null;
            if (!newName || newName === col.name) return;
            try {
                await fetch(`/api/collections/${col.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newName }),
                });
                await fetchCollections();
            } catch (e) {
                showToast('Failed to rename collection', 'error');
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
                    // Refresh selected model to update collections list
                    if (selectedModel.value && selectedModel.value.id === modelId) {
                        await refreshSelectedModel();
                    }
                    showToast('Added to collection', 'success');
                }
            } catch (e) {
                showToast('Failed to add to collection', 'error');
            }
        }

        async function removeModelFromCollection(collectionId, modelId) {
            try {
                const resp = await fetch(`/api/collections/${collectionId}/models/${modelId}`, {
                    method: 'DELETE',
                });
                if (resp.ok) {
                    await fetchCollections();
                    if (selectedModel.value && selectedModel.value.id === modelId) {
                        await refreshSelectedModel();
                    }
                    showToast('Removed from collection', 'success');
                }
            } catch (e) {
                showToast('Failed to remove from collection', 'error');
            }
        }

        async function refreshSelectedModel() {
            if (!selectedModel.value) return;
            try {
                const resp = await fetch(`/api/models/${selectedModel.value.id}`);
                if (resp.ok) {
                    const data = await resp.json();
                    selectedModel.value = data;
                }
            } catch { /* ignore */ }
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
                } else {
                    favoritesCount.value += wasFav ? -1 : 1;
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
                await fetchFavoritesCount();
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
                if (showBulkTagModal.value) {
                    showBulkTagModal.value = false;
                } else if (showImportModal.value) {
                    closeImportModal();
                } else if (showAddToCollectionModal.value) {
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
            fetchFavoritesCount();
            fetchSavedSearches();
            fetchImportCredentials();
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
            tagSuggestions,
            tagSuggestionsLoading,
            showBulkTagModal,
            bulkTagInput,
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
            regeneratingThumbnails,
            regenProgress,
            showStatusMenu,
            systemStatus,
            favoritesCount,
            collections,
            showCollectionModal,
            newCollectionName,
            newCollectionColor,
            COLLECTION_COLORS,
            openCollectionModal,
            addToCollectionModelId,
            showAddToCollectionModal,
            editingCollectionId,
            editCollectionName,
            savedSearches,
            showSaveSearchModal,
            saveSearchName,
            selectionMode,
            selectedModels,
            showImportModal,
            importMode,
            importUrls,
            importLibraryId,
            importSubfolder,
            importRunning,
            importDone,
            importPreview,
            importProgress,
            importCredentials,
            credentialInputs,
            uploadFiles,
            uploadResults,

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
            setPageSize,
            PAGE_SIZE_OPTIONS,
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
            regenerateThumbnails,
            thumbnailStatus,
            thumbStatusClass,
            thumbStatusTitle,
            zipName,
            checkForUpdates,
            applyUpdate,
            toggleStatusMenu,
            closeStatusMenu,
            statusLabel,
            statusDotClass,
            fetchCollections,
            createCollection,
            deleteCollection,
            startEditCollection,
            saveCollectionName,
            openAddToCollection,
            addModelToCollection,
            removeModelFromCollection,
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
            openImportModal,
            closeImportModal,
            previewImportUrl,
            startImport,
            onFilesSelected,
            startUpload,
            fetchImportCredentials,
            saveImportCredential,
            deleteImportCredential,
            toggleDuplicatesFilter,
            fetchTagSuggestions,
            applyTagSuggestion,
            bulkAutoTag,
            bulkAddTags,

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

            <button class="btn-icon" @click="openImportModal" title="Import Models">
                <span v-html="ICONS.link"></span>
            </button>
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
                    <button class="btn-icon" style="width:20px;height:20px" @click="openCollectionModal()"
                            title="New collection"><span v-html="ICONS.plus"></span></button>
                </div>
                <div class="sidebar-item" :class="{ active: filters.favoritesOnly }" @click="toggleFavoritesFilter">
                    <span v-html="ICONS.heart"></span>
                    <span>Favorites</span>
                    <span v-if="favoritesCount > 0" class="item-count">{{ favoritesCount }}</span>
                </div>
                <div class="sidebar-item" :class="{ active: filters.duplicatesOnly }" @click="toggleDuplicatesFilter">
                    <span v-html="ICONS.copy"></span>
                    <span>Duplicates</span>
                </div>
                <div v-for="col in collections" :key="col.id"
                     class="sidebar-item" :class="{ active: filters.collection === col.id }"
                     @click="setCollectionFilter(col.id)">
                    <span class="collection-dot" :style="{ background: col.color || '#666' }"></span>
                    <template v-if="editingCollectionId === col.id">
                        <input class="sidebar-edit-input" v-model="editCollectionName"
                               @blur="saveCollectionName(col)"
                               @keydown.enter="saveCollectionName(col)"
                               @keydown.escape="editingCollectionId = null"
                               @click.stop
                               autofocus>
                    </template>
                    <span v-else class="truncate" @dblclick.stop="startEditCollection(col)">{{ col.name }}</span>
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
                        <div class="card-meta">
                            {{ formatFileSize(model.file_size) }}
                            <span v-if="model.zip_path" class="zip-badge" :title="zipName(model)">zip</span>
                            <span v-if="model.is_duplicate" class="dup-badge" title="Duplicate file (same hash)">dup</span>
                        </div>
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
                            <td class="col-name">{{ model.name }} <span v-if="model.zip_path" class="zip-badge" :title="zipName(model)">zip</span><span v-if="model.is_duplicate" class="dup-badge" title="Duplicate">dup</span></td>
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
            <div v-if="models.length > 0 && !loading" class="pagination-bar">
                <div class="pagination-info">
                    Showing {{ shownCount }} of {{ pagination.total }} models
                </div>
                <div class="pagination-controls">
                    <label class="page-size-label">Per page:
                        <select class="page-size-select" :value="pagination.limit" @change="setPageSize($event.target.value)">
                            <option v-for="opt in PAGE_SIZE_OPTIONS" :key="opt" :value="opt">{{ opt }}</option>
                        </select>
                    </label>
                    <button v-if="hasMore" class="btn btn-secondary btn-sm" @click="loadMore" :disabled="loading">
                        Load More
                    </button>
                </div>
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
                <button class="btn btn-sm btn-ghost"
                        @click="openAddToCollection(selectedModel.id)" title="Add to collection">
                    <span v-html="ICONS.collection"></span>
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
                        <div v-if="selectedModel.zip_path" class="info-field" style="margin-top:4px">
                            <span class="field-label">Zip Archive</span>
                            <span class="field-value field-value-path">
                                {{ selectedModel.zip_path }}
                            </span>
                        </div>
                        <div v-if="selectedModel.zip_entry" class="info-field">
                            <span class="field-label">Zip Entry</span>
                            <span class="field-value field-value-path">
                                {{ selectedModel.zip_entry }}
                            </span>
                        </div>
                        <div class="info-field" :style="selectedModel.zip_path ? {} : { 'margin-top': '4px' }">
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
                        <!-- Tag suggestions -->
                        <div style="margin-top:8px">
                            <button class="btn btn-sm btn-ghost" @click="fetchTagSuggestions" :disabled="tagSuggestionsLoading">
                                Suggest Tags
                            </button>
                            <div v-if="tagSuggestions.length > 0" class="tag-suggestions" style="margin-top:6px">
                                <span v-for="s in tagSuggestions" :key="s" class="tag-chip tag-suggestion"
                                      @click="applyTagSuggestion(s)" style="cursor:pointer">
                                    + {{ s }}
                                </span>
                            </div>
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

                    <!-- Collections -->
                    <div class="info-section">
                        <div class="info-section-title" style="display:flex;align-items:center;justify-content:space-between">
                            Collections
                            <button class="btn-icon" style="width:20px;height:20px"
                                    @click="openAddToCollection(selectedModel.id)" title="Add to collection">
                                <span v-html="ICONS.plus"></span>
                            </button>
                        </div>
                        <div class="tags-list">
                            <span v-for="col in (selectedModel.collections || [])" :key="col.id"
                                  class="tag-chip" :style="{ background: (col.color || '#666') + '22', color: col.color || '#666', border: '1px solid ' + (col.color || '#666') + '44' }">
                                <span class="collection-dot" :style="{ background: col.color || '#666' }" style="width:8px;height:8px;margin-right:4px"></span>
                                {{ col.name }}
                                <button class="tag-remove" @click="removeModelFromCollection(col.id, selectedModel.id)" title="Remove from collection">&times;</button>
                            </span>
                            <span v-if="!selectedModel.collections || !selectedModel.collections.length"
                                  class="text-muted text-sm">No collections</span>
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

                    <div class="thumbnail-regen-row">
                        <button class="btn btn-secondary"
                                @click="regenerateThumbnails"
                                :disabled="regeneratingThumbnails">
                            <span v-html="ICONS.refresh"></span>
                            Regenerate All Thumbnails
                        </button>
                        <span class="text-muted text-sm">Re-render existing thumbnails with the current mode</span>
                    </div>
                    <div v-if="regeneratingThumbnails && regenProgress.total > 0" class="regen-progress" style="margin-top:12px">
                        <div class="regen-progress-bar">
                            <div class="regen-progress-fill" :style="{ width: Math.round((regenProgress.completed / regenProgress.total) * 100) + '%' }"></div>
                        </div>
                        <span class="text-muted text-sm" style="margin-top:4px;display:block">
                            {{ regenProgress.completed }} / {{ regenProgress.total }} models
                        </span>
                    </div>
                </div>

                <!-- Import Credentials Section -->
                <div class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.link"></span>
                        Import Credentials
                    </div>
                    <div class="settings-section-desc">
                        Configure API keys or cookies for 3D model hosting sites to enable richer metadata extraction during URL import.
                    </div>

                    <div class="import-cred-list">
                        <div class="import-cred-item" v-for="site in ['thingiverse', 'makerworld', 'printables', 'myminifactory', 'cults3d', 'thangs']" :key="site">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                                <span style="font-weight:600;text-transform:capitalize;font-size:0.85rem">{{ site }}</span>
                                <button v-if="importCredentials[site]" class="btn btn-sm btn-ghost text-danger"
                                        @click="deleteImportCredential(site)">Remove</button>
                            </div>
                            <div v-if="site === 'thingiverse'" class="form-row">
                                <label class="form-label">API Key</label>
                                <div style="display:flex;gap:6px">
                                    <input type="text" class="form-input" v-model="credentialInputs[site]"
                                           :placeholder="importCredentials.thingiverse ? importCredentials.thingiverse.api_key || 'Not set' : 'Not set'"
                                           style="flex:1">
                                    <button class="btn btn-sm btn-primary"
                                            @click="saveImportCredential(site, 'api_key')">Save</button>
                                </div>
                            </div>
                            <div v-else-if="site === 'makerworld'" class="form-row">
                                <label class="form-label">Token</label>
                                <div style="display:flex;gap:6px">
                                    <input type="text" class="form-input" v-model="credentialInputs[site]"
                                           :placeholder="importCredentials[site] ? importCredentials[site].token || 'Not set' : 'Not set'"
                                           style="flex:1">
                                    <button class="btn btn-sm btn-primary"
                                            @click="saveImportCredential(site, 'token')">Save</button>
                                </div>
                                <div class="text-muted" style="font-size:0.7rem;margin-top:4px">
                                    In your browser on makerworld.com: press F12 → Application → Cookies → copy the <strong>token</strong> value (starts with AAB_). Valid for 90 days.
                                </div>
                            </div>
                            <div v-else class="form-row">
                                <label class="form-label">Cookie</label>
                                <div style="display:flex;gap:6px">
                                    <input type="text" class="form-input" v-model="credentialInputs[site]"
                                           :placeholder="importCredentials[site] ? importCredentials[site].cookie || 'Not set' : 'Not set'"
                                           style="flex:1">
                                    <button class="btn btn-sm btn-primary"
                                            @click="saveImportCredential(site, 'cookie')">Save</button>
                                </div>
                            </div>
                        </div>
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
                        {{ systemStatus.thumbnails.regenerating ? 'regenerating' : statusLabel(systemStatus.thumbnails.status) }}
                    </span>
                </div>
                <div v-if="systemStatus.thumbnails.regenerating" class="status-menu-detail">
                    Regenerating: {{ systemStatus.thumbnails.regen_completed }} / {{ systemStatus.thumbnails.regen_total }} models
                </div>
                <div v-else-if="systemStatus.thumbnails.total_cached != null" class="status-menu-detail">
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
            <button class="btn btn-sm btn-secondary" @click="showBulkTagModal = true">
                Tag
            </button>
            <button class="btn btn-sm btn-secondary" @click="bulkAutoTag">
                Auto-Tag
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
                <div class="color-swatch-grid">
                    <button v-for="c in COLLECTION_COLORS" :key="c"
                            class="color-swatch" :class="{ active: newCollectionColor === c }"
                            :style="{ background: c }"
                            @click="newCollectionColor = c"
                            type="button"></button>
                </div>
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
         Import Modal
         ============================================================ -->
    <div v-if="showImportModal" class="detail-overlay" @click.self="closeImportModal">
        <div class="settings-panel" style="max-width:560px">
            <div class="detail-header">
                <div class="detail-title">Import Models</div>
                <button class="close-btn" @click="closeImportModal" title="Close">&times;</button>
            </div>
            <div class="settings-content">
                <!-- Mode tabs -->
                <div class="import-tabs">
                    <button class="import-tab" :class="{ active: importMode === 'url' }" @click="importMode = 'url'">
                        <span v-html="ICONS.link"></span> From URL
                    </button>
                    <button class="import-tab" :class="{ active: importMode === 'file' }" @click="importMode = 'file'">
                        <span v-html="ICONS.download"></span> Upload Files
                    </button>
                </div>

                <!-- URL mode -->
                <template v-if="importMode === 'url'">
                    <div class="settings-section">
                        <div class="settings-section-desc">
                            Paste one or more URLs (one per line). Supports Thingiverse, MakerWorld, Printables, MyMiniFactory, Cults3D, Thangs, or direct download links.
                        </div>
                        <div class="form-row">
                            <textarea class="form-input import-textarea"
                                      v-model="importUrls"
                                      placeholder="https://www.thingiverse.com/thing/12345&#10;https://example.com/model.stl"
                                      rows="4"
                                      @blur="previewImportUrl"></textarea>
                        </div>
                    </div>

                    <!-- Preview -->
                    <div v-if="importPreview.loading" class="text-muted text-sm" style="padding:8px 0;display:flex;align-items:center;gap:8px">
                        <div class="spinner spinner-sm"></div> Fetching preview...
                    </div>
                    <div v-else-if="importPreview.data" class="import-preview-card">
                        <div v-if="importPreview.data.error" class="text-sm text-danger" style="padding:4px 0 8px">
                            {{ importPreview.data.error }}
                        </div>
                        <div v-if="importPreview.data.title" style="font-weight:600;margin-bottom:4px">{{ importPreview.data.title }}</div>
                        <div v-if="importPreview.data.source_site" class="text-muted text-sm" style="margin-bottom:4px;text-transform:capitalize">{{ importPreview.data.source_site }}</div>
                        <div v-if="importPreview.data.file_count" class="text-sm">{{ importPreview.data.file_count }} downloadable file(s)</div>
                        <div v-if="importPreview.data.tags && importPreview.data.tags.length" class="tags-list" style="margin-top:6px">
                            <span v-for="t in importPreview.data.tags.slice(0, 8)" :key="t" class="tag-chip">{{ t }}</span>
                            <span v-if="importPreview.data.tags.length > 8" class="tag-chip" style="opacity:0.7">+{{ importPreview.data.tags.length - 8 }}</span>
                        </div>
                    </div>
                </template>

                <!-- File upload mode -->
                <template v-if="importMode === 'file'">
                    <div class="settings-section">
                        <div class="settings-section-desc">
                            Select 3D model files to upload (.stl, .obj, .3mf, .step, .gltf, .glb, .ply, .zip).
                        </div>
                        <div class="form-row">
                            <label class="file-upload-area" :class="{ 'has-files': uploadFiles.length }">
                                <input type="file" multiple
                                       accept=".stl,.obj,.gltf,.glb,.3mf,.ply,.dae,.off,.step,.stp,.fbx,.zip"
                                       @change="onFilesSelected"
                                       style="display:none">
                                <div v-if="!uploadFiles.length" class="file-upload-placeholder">
                                    <span v-html="ICONS.download"></span>
                                    <span>Click to select files or drag &amp; drop</span>
                                </div>
                                <div v-else class="file-upload-list">
                                    <div v-for="(f, i) in uploadFiles" :key="i" class="text-sm">{{ f.name }} ({{ formatFileSize(f.size) }})</div>
                                </div>
                            </label>
                        </div>
                    </div>
                </template>

                <!-- Library + Subfolder (shared) -->
                <div class="settings-section" style="margin-top:16px">
                    <div class="settings-section-title">
                        <span v-html="ICONS.folder"></span>
                        Destination
                    </div>
                    <div class="form-row">
                        <label class="form-label">Library</label>
                        <select class="form-input" v-model="importLibraryId">
                            <option v-for="lib in libraries" :key="lib.id" :value="lib.id">{{ lib.name }}</option>
                        </select>
                    </div>
                    <div class="form-row" style="margin-top:8px">
                        <label class="form-label">Subfolder (optional)</label>
                        <input type="text" class="form-input" v-model="importSubfolder"
                               placeholder="e.g. imported/thingiverse">
                    </div>
                </div>

                <!-- Progress (URL mode) -->
                <div v-if="importRunning && importMode === 'url' && importProgress.total > 0" style="margin-top:16px">
                    <div class="regen-progress-bar">
                        <div class="regen-progress-fill" :style="{ width: Math.round((importProgress.completed / importProgress.total) * 100) + '%' }"></div>
                    </div>
                    <span class="text-muted text-sm" style="margin-top:4px;display:block">
                        {{ importProgress.completed }} / {{ importProgress.total }} URLs
                        <span v-if="importProgress.current_url" style="opacity:0.7"> &mdash; {{ importProgress.current_url }}</span>
                    </span>
                </div>

                <!-- Results (URL mode) -->
                <div v-if="importDone && importMode === 'url' && importProgress.results.length" class="import-results" style="margin-top:16px">
                    <div class="settings-section-title" style="margin-bottom:8px">Results</div>
                    <div v-for="(r, i) in importProgress.results" :key="i" class="import-result-row">
                        <span v-if="r.status === 'ok'" class="import-status-icon import-status-ok" title="Success">&#10003;</span>
                        <span v-else class="import-status-icon import-status-error" title="Failed">&#10007;</span>
                        <div class="import-result-detail">
                            <div class="import-result-url">{{ r.url }}</div>
                            <div v-if="r.status === 'ok'" class="text-sm" style="color:var(--color-success, #4caf50)">
                                {{ r.models.length }} model(s) imported
                            </div>
                            <div v-else class="text-sm" style="color:var(--color-danger, #ef4444)">
                                {{ r.error || 'Import failed' }}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Results (file upload mode) -->
                <div v-if="importDone && importMode === 'file' && uploadResults.length" class="import-results" style="margin-top:16px">
                    <div class="settings-section-title" style="margin-bottom:8px">Results</div>
                    <div v-for="(r, i) in uploadResults" :key="i" class="import-result-row">
                        <span v-if="r.status === 'ok'" class="import-status-icon import-status-ok" title="Success">&#10003;</span>
                        <span v-else class="import-status-icon import-status-error" title="Failed">&#10007;</span>
                        <div class="import-result-detail">
                            <div class="import-result-url">{{ r.filename }}</div>
                            <div v-if="r.status === 'ok'" class="text-sm" style="color:var(--color-success, #4caf50)">
                                Imported successfully
                            </div>
                            <div v-else class="text-sm" style="color:var(--color-danger, #ef4444)">
                                {{ r.error || 'Import failed' }}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Actions -->
                <div class="form-actions" style="margin-top:20px;display:flex;justify-content:flex-end;gap:8px">
                    <button v-if="importDone" class="btn btn-primary" @click="closeImportModal">Done</button>
                    <template v-else-if="importMode === 'url'">
                        <button class="btn btn-secondary" @click="closeImportModal">Cancel</button>
                        <button class="btn btn-primary"
                                @click="startImport"
                                :disabled="importRunning || !importUrls.trim() || !importLibraryId">
                            <span v-html="ICONS.download"></span>
                            {{ importRunning ? 'Importing...' : 'Import' }}
                        </button>
                    </template>
                    <template v-else>
                        <button class="btn btn-secondary" @click="closeImportModal">Cancel</button>
                        <button class="btn btn-primary"
                                @click="startUpload"
                                :disabled="importRunning || !uploadFiles.length || !importLibraryId">
                            <span v-html="ICONS.download"></span>
                            {{ importRunning ? 'Uploading...' : 'Upload' }}
                        </button>
                    </template>
                </div>
            </div>
        </div>
    </div>

    <!-- ============================================================
         Bulk Tag Modal
         ============================================================ -->
    <div v-if="showBulkTagModal" class="detail-overlay" @click.self="showBulkTagModal = false">
        <div class="mini-modal">
            <h3>Add Tags to {{ selectedModels.size }} Model(s)</h3>
            <div class="form-row">
                <label class="form-label">Tags (comma-separated)</label>
                <input type="text" class="form-input" v-model="bulkTagInput"
                       placeholder="e.g. figurine, fantasy, painted"
                       @keydown.enter="bulkAddTags">
            </div>
            <div class="form-actions">
                <button class="btn btn-secondary" @click="showBulkTagModal = false">Cancel</button>
                <button class="btn btn-primary" @click="bulkAddTags" :disabled="!bulkTagInput.trim()">Apply Tags</button>
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
