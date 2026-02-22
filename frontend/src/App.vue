<script setup>
/**
 * YASTL - Yet Another STL Library
 * Main Vue 3 Application (Vite SFC)
 */
import { ref, reactive, computed, onMounted, nextTick } from 'vue';
import { debounce } from './search.js';
import { ICONS } from './icons.js';
import { useToast } from './composables/useToast.js';
import { useViewer } from './composables/useViewer.js';

/* ---- Child components ---- */
import NavBar from './components/NavBar.vue';
import SideBar from './components/SideBar.vue';
import ModelGrid from './components/ModelGrid.vue';
import DetailPanel from './components/DetailPanel.vue';
import SettingsModal from './components/SettingsModal.vue';
import ImportModal from './components/ImportModal.vue';
import CollectionModal from './components/CollectionModal.vue';
import SelectionBar from './components/SelectionBar.vue';
import {
    apiGetModels,
    apiGetModel,
    apiUpdateModel,
    apiDeleteModel,
    apiRenameModelFile,
    apiGetTags,
    apiAddTagsToModel,
    apiRemoveTagFromModel,
    apiSuggestTags,
    apiGetCategories,
    apiSearchModels,
    apiTriggerScan,
    apiGetScanStatus,
    apiToggleFavorite,
    apiGetFavoritesCount,
    apiGetSavedSearches,
    apiSaveSearch,
    apiDeleteSavedSearch,
    apiGetSystemStatus,
} from './api.js';
import { useImport } from './composables/useImport.js';
import { useCollections } from './composables/useCollections.js';
import { useSelection } from './composables/useSelection.js';
import { useSettings } from './composables/useSettings.js';
import { useUpdates } from './composables/useUpdates.js';

/* ---- Toast ---- */
const { toasts, showToast } = useToast();

/* ---- 3D Viewer ---- */
const {
    viewerLoading,
    initViewer,
    loadModel,
    resetCamera,
    dispose: disposeViewer,
} = useViewer();

/* ---- Core reactive state ---- */
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
const sidebarOpen = ref(window.innerWidth > 768);

// Editable field state
const editName = ref('');
const editDesc = ref('');
const editSourceUrl = ref('');
const isEditingName = ref(false);
const isEditingDesc = ref(false);
const isEditingSourceUrl = ref(false);

// Detail panel tab state
const detailTab = ref('info');
const showFileDetails = ref(false);

// Category expansion state (by category id)
const expandedCategories = reactive({});

// Sidebar section collapse state (format starts collapsed)
const collapsedSections = reactive({ format: true, tags: true, categories: true });

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

// Favorites count
const favoritesCount = ref(0);

// Saved searches
const savedSearches = ref([]);
const showSaveSearchModal = ref(false);
const saveSearchName = ref('');

// System status indicator
const showStatusMenu = ref(false);
const systemStatus = reactive({
    health: 'unknown',
    scanner: { status: 'unknown' },
    watcher: { status: 'unknown' },
    database: { status: 'unknown' },
    thumbnails: { status: 'unknown' },
});
// eslint-disable-next-line no-unused-vars -- interval ref kept for root component lifecycle
let statusPollTimer = null;

/* ---- Composables ---- */
const settingsComposable = useSettings(showToast, () => fetchModels());
const {
    showSettings, libraries, newLibName, newLibPath, addingLibrary,
    thumbnailMode, regeneratingThumbnails, regenProgress,
    fetchLibraries, addLibrary, deleteLibrary,
    setThumbnailMode, regenerateThumbnails,
} = settingsComposable;

const updatesComposable = useUpdates(showToast);
const { updateInfo, checkForUpdates, applyUpdate } = updatesComposable;

const collectionsComposable = useCollections(showToast);
const {
    collections, COLLECTION_COLORS,
    showCollectionModal, newCollectionName, newCollectionColor,
    addToCollectionModelId, showAddToCollectionModal,
    editingCollectionId, editCollectionName, inlineNewCollection,
    fetchCollections, openCollectionModal, createCollection,
    startInlineNewCollection, cancelInlineNewCollection,
    deleteCollection: _deleteCollection,
    startEditCollection, saveCollectionName,
    openAddToCollection,
    addModelToCollection: _addModelToCollection,
    removeModelFromCollection: _removeModelFromCollection,
} = collectionsComposable;

// Wrap collection functions that need extra context
function deleteCollection(id) {
    _deleteCollection(id, filters);
}

async function refreshSelectedModel(modelId) {
    if (!selectedModel.value) return;
    if (modelId && selectedModel.value.id !== modelId) return;
    try {
        const data = await apiGetModel(selectedModel.value.id);
        selectedModel.value = data;
    } catch { /* ignore */ }
}

function addModelToCollection(collectionId) {
    _addModelToCollection(collectionId, refreshSelectedModel);
}

function removeModelFromCollection(collectionId, modelId) {
    _removeModelFromCollection(collectionId, modelId, refreshSelectedModel);
}

const selectionComposable = useSelection(
    showToast,
    () => fetchModels(),
    models,
    () => fetchTags(),
    () => fetchFavoritesCount(),
    fetchCollections,
);
const {
    selectionMode, selectedModels, showBulkTagModal, bulkTagInput,
    toggleSelectionMode, toggleModelSelection, selectAll, deselectAll,
    bulkFavorite, bulkAutoTag, bulkAddTags,
    bulkAddToCollection: _bulkAddToCollection,
    bulkDelete,
} = selectionComposable;

function bulkAddToCollection(collectionId) {
    _bulkAddToCollection(collectionId, showAddToCollectionModal);
}

function refreshImportData() {
    fetchModels();
    fetchTags();
    fetchCategories();
}

const importComposable = useImport(
    showToast, refreshImportData, libraries, collections, fetchCollections,
);
const {
    showImportModal, importMode, importUrls, importLibraryId, importSubfolder,
    importRunning, importDone, importPreview, importProgress,
    uploadFiles, uploadResults, uploadTags, uploadTagSuggestions,
    uploadCollectionId, uploadSourceUrl, uploadDescription, uploadZipMeta,
    importCredentials, credentialInputs,
    openImportModal: _openImportModal,
    closeImportModal: _closeImportModal,
    previewImportUrl, startImport, onFilesSelected, startUpload,
    addUploadTagSuggestion, fetchImportCredentials,
    saveImportCredential, deleteImportCredential,
} = importComposable;

function openImportModal() {
    fetchLibraries();
    _openImportModal();
}

function closeImportModal() {
    _closeImportModal(showDetail.value, showSettings.value);
}

/* ---- Inline collection callback for upload/addToCollection contexts ---- */
function confirmInlineNewCollection(context) {
    collectionsComposable.confirmInlineNewCollection(context, (newId, ctx) => {
        if (ctx === 'upload') {
            uploadCollectionId.value = newId;
        } else if (ctx === 'addToCollection') {
            handleCollectionSelect(newId);
        }
    });
}

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
   Core data fetching
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

        const data = await apiGetModels(params);

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

        const data = await apiSearchModels(params);

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
        const data = await apiGetTags();
        allTags.value = data.tags || [];
    } catch (err) {
        console.error('fetchTags error:', err);
    }
}

async function fetchCategories() {
    try {
        const data = await apiGetCategories();
        allCategories.value = data.categories || [];
    } catch (err) {
        console.error('fetchCategories error:', err);
    }
}

async function fetchScanStatus() {
    try {
        const data = await apiGetScanStatus();
        scanStatus.scanning = data.scanning;
        scanStatus.total_files = data.total_files;
        scanStatus.processed_files = data.processed_files;

        if (data.scanning && !scanPollTimer) {
            scanPollTimer = setInterval(fetchScanStatus, 2000);
        } else if (!data.scanning && scanPollTimer) {
            clearInterval(scanPollTimer);
            scanPollTimer = null;
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
   System Status
   ============================================================== */

async function fetchSystemStatus() {
    try {
        const data = await apiGetSystemStatus();
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

/* ==============================================================
   Tag Suggestions
   ============================================================== */

async function fetchTagSuggestions() {
    if (!selectedModel.value) return;
    tagSuggestionsLoading.value = true;
    tagSuggestions.value = [];
    try {
        const data = await apiSuggestTags(selectedModel.value.id);
        tagSuggestions.value = data.suggestions || [];
    } catch (e) {
        console.error('fetchTagSuggestions error:', e);
    } finally {
        tagSuggestionsLoading.value = false;
    }
}

async function applyTagSuggestion(tag) {
    newTagInput.value = tag;
    await addTag();
    tagSuggestions.value = tagSuggestions.value.filter(t => t !== tag);
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
   Actions
   ============================================================== */

async function triggerScan() {
    try {
        const { ok, data } = await apiTriggerScan();
        if (ok) {
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
    try {
        const data = await apiGetModel(model.id);
        selectedModel.value = data;
    } catch {
        selectedModel.value = { ...model };
    }

    editName.value = selectedModel.value.name || '';
    editDesc.value = selectedModel.value.description || '';
    editSourceUrl.value = selectedModel.value.source_url || '';
    isEditingName.value = false;
    isEditingDesc.value = false;
    isEditingSourceUrl.value = false;
    tagSuggestions.value = [];
    detailTab.value = 'info';
    showFileDetails.value = false;
    showDetail.value = true;
    document.body.classList.add('modal-open');

    await nextTick();

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
            console.warn('Native loader failed for', fmt, '-- trying GLB fallback:', err);
        }
    }

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
    isEditingSourceUrl.value = false;
    viewerLoading.value = false;
    if (!showSettings.value) {
        document.body.classList.remove('modal-open');
    }
}

async function addTag() {
    const tag = newTagInput.value.trim();
    if (!tag || !selectedModel.value) return;
    try {
        const updated = await apiAddTagsToModel(selectedModel.value.id, [tag]);
        selectedModel.value = updated;
        updateModelInList(updated);
        newTagInput.value = '';
        fetchTags();
        showToast(`Tag "${tag}" added`);
    } catch (err) {
        showToast(err.message || 'Failed to add tag', 'error');
    }
}

async function removeTag(tagName) {
    if (!selectedModel.value) return;
    try {
        await apiRemoveTagFromModel(selectedModel.value.id, tagName);
        selectedModel.value.tags = (selectedModel.value.tags || []).filter(
            (t) => t !== tagName
        );
        updateModelInList(selectedModel.value);
        fetchTags();
    } catch (err) {
        showToast('Failed to remove tag', 'error');
    }
}

async function updateModel(modelId, data) {
    if (!modelId) return;
    try {
        const updated = await apiUpdateModel(modelId, data);
        selectedModel.value = updated;
        editName.value = updated.name || '';
        editDesc.value = updated.description || '';
        editSourceUrl.value = updated.source_url || '';
        updateModelInList(updated);
        showToast('Model updated');
    } catch (err) {
        showToast(err.message || 'Failed to update model', 'error');
    }
    isEditingName.value = false;
    isEditingDesc.value = false;
    isEditingSourceUrl.value = false;
}

async function renameModelFile() {
    if (!selectedModel.value) return;
    const model = selectedModel.value;
    const oldName = model.file_path?.split('/').pop() || '';
    const ext = oldName.includes('.') ? oldName.slice(oldName.lastIndexOf('.')) : '';
    const newName = model.name.replace(/[^\w\s.-]/g, '').replace(/\s+/g, '_') + ext;
    if (!confirm(`Rename file on disk?\n\n"${oldName}"\n→ "${newName}"`)) return;
    try {
        const updated = await apiRenameModelFile(model.id);
        selectedModel.value = updated;
        updateModelInList(updated);
        showToast('File renamed');
    } catch (e) {
        showToast(e.message || 'Failed to rename file', 'error');
    }
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
        await apiDeleteModel(model.id);
        models.value = models.value.filter((m) => m.id !== model.id);
        pagination.total = Math.max(0, pagination.total - 1);
        if (showDetail.value) closeDetail();
        showToast('Model removed from library');
    } catch (err) {
        showToast(err.message || 'Failed to delete model', 'error');
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

function saveSourceUrl() {
    if (!selectedModel.value) return;
    const val = editSourceUrl.value.trim();
    // Allow clearing (empty string → null) or setting a URL
    if (val !== (selectedModel.value.source_url || '')) {
        updateModel(selectedModel.value.id, { source_url: val || null });
    } else {
        isEditingSourceUrl.value = false;
    }
}

function startEditSourceUrl() {
    editSourceUrl.value = selectedModel.value?.source_url || '';
    isEditingSourceUrl.value = true;
}

// ---- Favorites count ----
async function fetchFavoritesCount() {
    try {
        const data = await apiGetFavoritesCount();
        favoritesCount.value = data.total || 0;
    } catch (e) {
        console.error('Failed to fetch favorites count', e);
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

// ---- Saved Searches ----
async function fetchSavedSearches() {
    try {
        const data = await apiGetSavedSearches();
        savedSearches.value = data.saved_searches || [];
    } catch (e) {
        console.error('Failed to fetch saved searches', e);
    }
}

async function saveCurrentSearch() {
    const name = saveSearchName.value.trim();
    if (!name) return;
    try {
        await apiSaveSearch({
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
        });
        showSaveSearchModal.value = false;
        saveSearchName.value = '';
        await fetchSavedSearches();
        showToast('Search saved', 'success');
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
        await apiDeleteSavedSearch(id);
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
        await apiToggleFavorite(model.id, wasFav);
        favoritesCount.value += wasFav ? -1 : 1;
    } catch {
        model.is_favorite = wasFav;
    }
}

function toggleFavoritesFilter() {
    filters.favoritesOnly = !filters.favoritesOnly;
    pagination.offset = 0;
    fetchModels();
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

// Settings wrappers
function openSettings() {
    settingsComposable.openSettings(checkForUpdates, updateInfo);
}

function closeSettings() {
    settingsComposable.closeSettings(showDetail.value);
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

// pickNextCollectionColor is needed in template via collectionsComposable
const { pickNextCollectionColor } = collectionsComposable;
</script>

<template>
<div class="app-layout">
    <!-- ============================================================
         Navbar
         ============================================================ -->
    <NavBar
        :searchQuery="searchQuery"
        :viewMode="viewMode"
        :scanStatus="scanStatus"
        :systemStatus="systemStatus"
        :selectionMode="selectionMode"
        :sidebarOpen="sidebarOpen"
        @update:searchQuery="searchQuery = $event"
        @update:viewMode="viewMode = $event"
        @update:sidebarOpen="sidebarOpen = $event"
        @openSettings="openSettings"
        @openImportModal="openImportModal"
        @toggleSelectionMode="toggleSelectionMode"
        @toggleStatusMenu="toggleStatusMenu"
        @searchInput="onSearchInput"
        @clearSearch="clearSearch"
    />

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

        <SideBar
            :sidebarOpen="sidebarOpen"
            :filters="filters"
            :allTags="allTags"
            :allCategories="allCategories"
            :collections="collections"
            :libraries="libraries"
            :favoritesCount="favoritesCount"
            :collapsedSections="collapsedSections"
            :expandedCategories="expandedCategories"
            :savedSearches="savedSearches"
            :editingCollectionId="editingCollectionId"
            :editCollectionName="editCollectionName"
            @update:sidebarOpen="sidebarOpen = $event"
            @update:editCollectionName="editCollectionName = $event"
            @setLibraryFilter="setLibraryFilter"
            @setFormatFilter="setFormatFilter"
            @toggleTagFilter="toggleTagFilter"
            @toggleCategoryFilter="toggleCategoryFilter"
            @toggleCategory="toggleCategory"
            @toggleCollapsedSection="(section) => collapsedSections[section] = !collapsedSections[section]"
            @setCollectionFilter="setCollectionFilter"
            @toggleFavoritesFilter="toggleFavoritesFilter"
            @toggleDuplicatesFilter="toggleDuplicatesFilter"
            @openCollectionModal="openCollectionModal"
            @startEditCollection="startEditCollection"
            @saveCollectionName="saveCollectionName"
            @cancelEditCollection="editingCollectionId = null"
            @deleteCollection="deleteCollection"
            @applySavedSearch="applySavedSearch"
            @deleteSavedSearch="deleteSavedSearch"
        />

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
                 Model Grid / List
                 ============================================================ -->
            <ModelGrid
                v-else
                :models="models"
                :viewMode="viewMode"
                :selectionMode="selectionMode"
                :selectedModels="selectedModels"
                :thumbnailMode="thumbnailMode"
                @viewModel="viewModel"
                @toggleSelect="toggleModelSelection"
                @toggleFavorite="toggleFavorite"
            />

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
    <DetailPanel
        :selectedModel="selectedModel"
        :showDetail="showDetail"
        :viewerLoading="viewerLoading"
        :editName="editName"
        :editDesc="editDesc"
        :editSourceUrl="editSourceUrl"
        :isEditingName="isEditingName"
        :isEditingDesc="isEditingDesc"
        :isEditingSourceUrl="isEditingSourceUrl"
        :tagSuggestions="tagSuggestions"
        :tagSuggestionsLoading="tagSuggestionsLoading"
        :newTagInput="newTagInput"
        :allCategories="allCategories"
        :collections="collections"
        :detailTab="detailTab"
        :showFileDetails="showFileDetails"
        @close="closeDetail"
        @update:detailTab="detailTab = $event"
        @update:showFileDetails="showFileDetails = $event"
        @update:editName="editName = $event"
        @update:editDesc="editDesc = $event"
        @update:editSourceUrl="editSourceUrl = $event"
        @update:isEditingName="isEditingName = $event"
        @update:isEditingDesc="isEditingDesc = $event"
        @update:isEditingSourceUrl="isEditingSourceUrl = $event"
        @update:newTagInput="newTagInput = $event"
        @saveName="saveName"
        @saveDesc="saveDesc"
        @saveSourceUrl="saveSourceUrl"
        @startEditName="startEditName"
        @startEditDesc="startEditDesc"
        @startEditSourceUrl="startEditSourceUrl"
        @resetView="handleResetView"
        @toggleFavorite="toggleFavorite"
        @openAddToCollection="openAddToCollection"
        @removeModelFromCollection="removeModelFromCollection"
        @addTag="addTag"
        @removeTag="removeTag"
        @fetchTagSuggestions="fetchTagSuggestions"
        @applyTagSuggestion="applyTagSuggestion"
        @renameModelFile="renameModelFile"
        @deleteModel="deleteModel"
    />

    <!-- ============================================================
         Settings Modal
         ============================================================ -->
    <SettingsModal
        :showSettings="showSettings"
        :libraries="libraries"
        :newLibName="newLibName"
        :newLibPath="newLibPath"
        :addingLibrary="addingLibrary"
        :thumbnailMode="thumbnailMode"
        :regeneratingThumbnails="regeneratingThumbnails"
        :regenProgress="regenProgress"
        :updateInfo="updateInfo"
        :scanStatus="scanStatus"
        :importCredentials="importCredentials"
        :credentialInputs="credentialInputs"
        @close="closeSettings"
        @update:newLibName="newLibName = $event"
        @update:newLibPath="newLibPath = $event"
        @addLibrary="addLibrary"
        @deleteLibrary="deleteLibrary"
        @triggerScan="triggerScan"
        @setThumbnailMode="setThumbnailMode"
        @regenerateThumbnails="regenerateThumbnails"
        @checkForUpdates="checkForUpdates"
        @applyUpdate="applyUpdate"
        @saveImportCredential="saveImportCredential"
        @deleteImportCredential="deleteImportCredential"
        @updateCredentialInput="(site, val) => credentialInputs[site] = val"
    />

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
    <SelectionBar
        :selectionMode="selectionMode"
        :selectedModels="selectedModels"
        @selectAll="selectAll"
        @deselectAll="deselectAll"
        @bulkFavorite="bulkFavorite"
        @showBulkTagModal="showBulkTagModal = true"
        @bulkAutoTag="bulkAutoTag"
        @openBulkAddToCollection="openBulkAddToCollection"
        @bulkDelete="bulkDelete"
    />

    <!-- ============================================================
         Collection Modals
         ============================================================ -->
    <CollectionModal
        :showCollectionModal="showCollectionModal"
        :showAddToCollectionModal="showAddToCollectionModal"
        :newCollectionName="newCollectionName"
        :newCollectionColor="newCollectionColor"
        :addToCollectionModelId="addToCollectionModelId"
        :collections="collections"
        :COLLECTION_COLORS="COLLECTION_COLORS"
        :inlineNewCollection="inlineNewCollection"
        @update:showCollectionModal="showCollectionModal = $event"
        @update:showAddToCollectionModal="showAddToCollectionModal = $event"
        @update:newCollectionName="newCollectionName = $event"
        @update:newCollectionColor="newCollectionColor = $event"
        @createCollection="createCollection"
        @handleCollectionSelect="handleCollectionSelect"
        @startInlineNewCollection="startInlineNewCollection"
        @confirmInlineNewCollection="confirmInlineNewCollection"
        @cancelInlineNewCollection="cancelInlineNewCollection"
        @pickNextCollectionColor="inlineNewCollection.color = pickNextCollectionColor()"
        @updateInlineNewCollectionName="inlineNewCollection.name = $event"
        @updateInlineNewCollectionColor="inlineNewCollection.color = $event"
    />

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
    <ImportModal
        :showImportModal="showImportModal"
        :importMode="importMode"
        :importUrls="importUrls"
        :importLibraryId="importLibraryId"
        :importSubfolder="importSubfolder"
        :importRunning="importRunning"
        :importDone="importDone"
        :importPreview="importPreview"
        :importProgress="importProgress"
        :uploadFiles="uploadFiles"
        :uploadResults="uploadResults"
        :uploadTags="uploadTags"
        :uploadTagSuggestions="uploadTagSuggestions"
        :uploadCollectionId="uploadCollectionId"
        :uploadSourceUrl="uploadSourceUrl"
        :uploadDescription="uploadDescription"
        :uploadZipMeta="uploadZipMeta"
        :libraries="libraries"
        :collections="collections"
        :inlineNewCollection="inlineNewCollection"
        :COLLECTION_COLORS="COLLECTION_COLORS"
        @close="closeImportModal"
        @update:importMode="importMode = $event"
        @update:importUrls="importUrls = $event"
        @update:importLibraryId="importLibraryId = $event"
        @update:importSubfolder="importSubfolder = $event"
        @update:uploadTags="uploadTags = $event"
        @update:uploadCollectionId="uploadCollectionId = $event"
        @update:uploadSourceUrl="uploadSourceUrl = $event"
        @update:uploadDescription="uploadDescription = $event"
        @previewImportUrl="previewImportUrl"
        @startImport="startImport"
        @onFilesSelected="onFilesSelected"
        @startUpload="startUpload"
        @addUploadTagSuggestion="addUploadTagSuggestion"
        @startInlineNewCollection="startInlineNewCollection"
        @confirmInlineNewCollection="confirmInlineNewCollection"
        @cancelInlineNewCollection="cancelInlineNewCollection"
        @updateInlineNewCollectionName="inlineNewCollection.name = $event"
        @updateInlineNewCollectionColor="inlineNewCollection.color = $event"
    />

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
</template>

<style>
@import './styles/base.css';
@import './styles/layout.css';
@import './styles/components.css';
@import './styles/cards.css';
@import './styles/detail-panel.css';
@import './styles/features.css';
@import './styles/responsive.css';
</style>
