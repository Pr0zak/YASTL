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

const { createApp, ref, reactive, computed, onMounted, watch, nextTick } = Vue;

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

        const filters = reactive({
            format: '',
            tag: '',
            category: '',
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
            return !!(filters.format || filters.tag || filters.category);
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

        function openSettings() {
            fetchLibraries();
            showSettings.value = true;
        }

        function closeSettings() {
            showSettings.value = false;
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

            await nextTick();

            // Initialize 3D viewer
            viewerLoading.value = true;
            initViewer('viewer-container');

            const supportedViewerFormats = ['stl', 'obj', 'gltf', 'glb', 'ply'];
            const fmt = (selectedModel.value.file_format || '').toLowerCase();

            if (supportedViewerFormats.includes(fmt)) {
                const fileUrl = `/api/models/${selectedModel.value.id}/file`;
                try {
                    await loadModel(fileUrl, fmt);
                } catch (err) {
                    console.error('Failed to load 3D model:', err);
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

        function setFormatFilter(fmt) {
            filters.format = filters.format === fmt ? '' : fmt;
            pagination.offset = 0;
            refreshCurrentView();
        }

        function setTagFilter(tagName) {
            filters.tag = filters.tag === tagName ? '' : tagName;
            pagination.offset = 0;
            refreshCurrentView();
        }

        function setCategoryFilter(catName) {
            filters.category = filters.category === catName ? '' : catName;
            pagination.offset = 0;
            refreshCurrentView();
        }

        function clearFilters() {
            filters.format = '';
            filters.tag = '';
            filters.category = '';
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

        /* ---- Keyboard handler for modals ---- */
        function onKeydown(e) {
            if (e.key === 'Escape') {
                if (showStatusMenu.value) {
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
                const menu = document.querySelector('.status-wrapper');
                if (menu && !menu.contains(e.target)) {
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
            statusPollTimer = setInterval(fetchSystemStatus, 30000);
            document.addEventListener('keydown', onKeydown);
            document.addEventListener('click', onDocumentClick);
        });

        // Watch search query for debounced search
        watch(searchQuery, () => {
            debouncedSearch();
        });

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
            filters,
            pagination,
            scanStatus,
            showSettings,
            libraries,
            newLibName,
            newLibPath,
            addingLibrary,
            showStatusMenu,
            systemStatus,

            // Computed
            scanProgress,
            hasMore,
            shownCount,
            hasActiveFilters,
            hasLibraries,

            // Actions
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
            toggleCategory,
            saveName,
            saveDesc,
            startEditName,
            startEditDesc,
            openSettings,
            closeSettings,
            addLibrary,
            deleteLibrary,
            toggleStatusMenu,
            closeStatusMenu,
            statusLabel,
            statusDotClass,

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
                   v-model="searchQuery"
                   placeholder="Search models by name or description..."
                   aria-label="Search models">
            <button v-if="searchQuery"
                    class="search-clear"
                    @click="searchQuery = ''"
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
                <!-- Status Submenu -->
                <div v-if="showStatusMenu" class="status-menu">
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
            </div>

            <button class="btn-icon" @click="openSettings" title="Settings" v-html="ICONS.settings"></button>
            <button class="btn btn-primary"
                    @click="triggerScan"
                    :disabled="scanStatus.scanning || !hasLibraries">
                <span v-html="ICONS.scan"></span>
                <span>Scan Library</span>
            </button>
        </div>
    </nav>

    <!-- ============================================================
         Body: Sidebar + Main
         ============================================================ -->
    <div class="app-body">

        <!-- Sidebar backdrop (mobile) -->
        <div v-if="sidebarOpen" class="sidebar-backdrop" @click="sidebarOpen = false"></div>

        <!-- Sidebar -->
        <aside class="sidebar" :class="{ open: sidebarOpen }">

            <!-- Format Filters -->
            <div class="sidebar-section">
                <div class="sidebar-section-title">Format</div>
                <label v-for="fmt in ['stl','obj','gltf','glb','3mf','step','stp','ply','fbx','dae','off']"
                       :key="fmt"
                       class="checkbox-item"
                       @click.prevent="setFormatFilter(fmt)">
                    <input type="checkbox" :checked="filters.format === fmt" readonly>
                    <span class="format-badge" :class="formatClass(fmt)">{{ fmt.toUpperCase() }}</span>
                </label>
            </div>

            <!-- Tags -->
            <div class="sidebar-section">
                <div class="sidebar-section-title">Tags</div>
                <div v-if="allTags.length === 0" class="text-muted text-sm" style="padding: 4px 10px;">
                    No tags yet
                </div>
                <div v-for="tag in allTags" :key="tag.id"
                     class="sidebar-item"
                     :class="{ active: filters.tag === tag.name }"
                     @click="setTagFilter(tag.name)">
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
                                 :class="{ active: filters.category === cat.name }"
                                 @click="setCategoryFilter(cat.name)">
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
                                         :class="{ active: filters.category === child.name }"
                                         @click="setCategoryFilter(child.name)">
                                        <span style="width:16px;display:inline-block"></span>
                                        <span class="category-name">{{ child.name }}</span>
                                        <span v-if="child.model_count" class="category-count">({{ child.model_count }})</span>
                                    </div>
                                    <!-- Third level -->
                                    <ul v-if="child.children && child.children.length && expandedCategories[child.id]"
                                        class="category-children">
                                        <li v-for="grandchild in child.children" :key="grandchild.id">
                                            <div class="category-item"
                                                 :class="{ active: filters.category === grandchild.name }"
                                                 @click="setCategoryFilter(grandchild.name)">
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
        </aside>

        <!-- Main Content -->
        <main class="main-content">

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

            <!-- Content Toolbar -->
            <div class="content-toolbar">
                <div class="result-count">
                    <strong>{{ pagination.total }}</strong>
                    model{{ pagination.total !== 1 ? 's' : '' }}
                    <span v-if="searchQuery" class="text-muted">
                        for "{{ searchQuery }}"
                    </span>
                </div>
            </div>

            <!-- Active Filters -->
            <div class="active-filters" v-if="hasActiveFilters">
                <span class="text-muted text-sm">Filters:</span>
                <span v-if="filters.format" class="filter-chip" @click="setFormatFilter(filters.format)">
                    Format: {{ filters.format.toUpperCase() }}
                    <span class="chip-remove">&times;</span>
                </span>
                <span v-if="filters.tag" class="filter-chip" @click="setTagFilter(filters.tag)">
                    Tag: {{ filters.tag }}
                    <span class="chip-remove">&times;</span>
                </span>
                <span v-if="filters.category" class="filter-chip" @click="setCategoryFilter(filters.category)">
                    Category: {{ filters.category }}
                    <span class="chip-remove">&times;</span>
                </span>
                <button class="btn btn-sm btn-ghost" @click="clearFilters">Clear all</button>
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
                    Your library is empty. Click "Scan Library" to discover and import 3D models from your directories.
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
                     class="model-card" @click="viewModel(model)">
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
                        <tr v-for="model in models" :key="model.id" @click="viewModel(model)">
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
                            <span class="field-value" style="font-size:0.7rem;word-break:break-all;max-width:200px;text-align:right">
                                {{ selectedModel.file_path }}
                            </span>
                        </div>
                        <div v-if="selectedModel.file_hash" class="info-field">
                            <span class="field-label">Hash</span>
                            <span class="field-value" style="font-size:0.65rem;word-break:break-all;max-width:180px;text-align:right;opacity:0.7">
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
                           :href="'/api/models/' + selectedModel.id + '/file'"
                           download>
                            <span v-html="ICONS.download"></span>
                            Download
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
