/**
 * YASTL - Import/Upload composable
 *
 * Manages the import modal state and logic for both URL import and file upload modes.
 */

import {
    apiPreviewImport,
    apiStartImport,
    apiGetImportStatus,
    apiUploadFiles,
    apiGetImportCredentials,
    apiSaveImportCredential,
    apiDeleteImportCredential,
} from '../api.js';

import { ref, reactive } from 'vue';

/**
 * @param {Function} showToast - Toast notification function
 * @param {Function} refreshData - Callback to refresh models/tags/categories after import
 * @param {import('vue').Ref} libraries - Reactive ref of libraries list
 * @param {import('vue').Ref} collections - Reactive ref of collections list
 * @param {Function} fetchCollectionsFn - Callback to refresh collections
 */
export function useImport(showToast, refreshData, libraries, collections, fetchCollectionsFn) {
    // Modal state
    const showImportModal = ref(false);
    const importMode = ref('file');
    const importUrls = ref('');
    const importLibraryId = ref(null);
    const importSubfolder = ref('');
    const importRunning = ref(false);
    const importDone = ref(false);
    const importPreview = reactive({ loading: false, data: null });
    const importProgress = reactive({ running: false, total: 0, completed: 0, current_url: null, results: [] });

    // File upload state
    const uploadFiles = ref([]);
    const uploadResults = ref([]);
    const uploadTags = ref('');
    const uploadTagSuggestions = ref([]);
    const uploadCollectionId = ref(null);
    const uploadName = ref('');
    const uploadSourceUrl = ref('');
    const uploadDescription = ref('');
    const uploadZipMeta = ref(null);

    // Import credentials
    const importCredentials = ref({});
    const credentialInputs = reactive({});

    let importPollTimer = null;

    // The destination you used last is almost always the one you want next.
    const DEST_KEY = 'yastl-import-destination';
    function loadDestination() {
        try {
            const d = JSON.parse(localStorage.getItem(DEST_KEY) || 'null');
            if (d && libraries.value.some((l) => l.id === d.libraryId)) {
                importLibraryId.value = d.libraryId;
                importSubfolder.value = d.subfolder || '';
                return true;
            }
        } catch { /* storage unavailable */ }
        return false;
    }
    function saveDestination() {
        try {
            localStorage.setItem(DEST_KEY, JSON.stringify({
                libraryId: importLibraryId.value, subfolder: importSubfolder.value,
            }));
        } catch { /* storage unavailable */ }
    }

    /**
     * Open the import dialog, optionally pre-filled: `files` from a drop
     * anywhere on the page, `urls` from a paste anywhere on the page.
     */
    function openImportModal(prefill = {}) {
        importMode.value = 'file';
        importUrls.value = '';
        importPreview.loading = false;
        importPreview.data = null;
        importDone.value = false;
        importProgress.results = [];
        uploadFiles.value = [];
        uploadResults.value = [];
        uploadTags.value = '';
        uploadTagSuggestions.value = [];
        uploadCollectionId.value = null;
        uploadName.value = '';
        uploadSourceUrl.value = '';
        uploadDescription.value = '';
        uploadZipMeta.value = null;
        importSubfolder.value = '';
        if (!loadDestination() && libraries.value.length > 0
            && !libraries.value.some((l) => l.id === importLibraryId.value)) {
            importLibraryId.value = libraries.value[0].id;
        }
        showImportModal.value = true;
        if (prefill.files && prefill.files.length) {
            onFilesSelected({ target: { files: prefill.files } });
        } else if (prefill.urls) {
            setImportUrls(prefill.urls);
            previewImportUrl();
        }
        document.body.classList.add('modal-open');
    }

    function closeImportModal(showDetail, showSettings) {
        showImportModal.value = false;
        if (!showDetail && !showSettings) {
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
            importPreview.data = await apiPreviewImport(firstUrl);
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
        saveDestination();
        try {
            const { ok, data } = await apiStartImport(urls, importLibraryId.value, importSubfolder.value);
            if (ok) {
                showToast(`Importing ${urls.length} URL(s)...`, 'info');
                startImportPolling();
            } else {
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
                const data = await apiGetImportStatus();
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
                    refreshData();
                }
            } catch (e) {
                console.error('importPoll error:', e);
            }
        }, 2000);
    }

    /** Links typed or pasted into the import box switch it to link mode. */
    function setImportUrls(value) {
        importUrls.value = value;
        if (value.trim()) {
            uploadFiles.value = [];
            uploadZipMeta.value = null;
            importMode.value = 'url';
        } else if (!uploadFiles.value.length) {
            importMode.value = 'file';
        }
    }

    function clearUploadFiles() {
        uploadFiles.value = [];
        uploadZipMeta.value = null;
        uploadTagSuggestions.value = [];
    }

    function onFilesSelected(event) {
        uploadFiles.value = Array.from(event.target.files || []);
        if (uploadFiles.value.length) {
            importMode.value = 'file';
            importUrls.value = '';
            importPreview.data = null;
        }
        uploadZipMeta.value = null;

        // Generate tag suggestions from filenames
        const stopWords = new Set([
            'a','an','the','and','or','but','in','on','at','to','for','of','is','it','by','as','with','from',
            'file','model','stl','obj','gltf','glb','3mf','ply','step','stp','dae','off','fbx','print','3d',
            'final','v1','v2','v3','copy','new','old','test','tmp','temp','zip','files',
        ]);
        const seen = new Set();
        const suggestions = [];
        for (const f of uploadFiles.value) {
            const stem = f.name.replace(/\.[^.]+$/, '');

            // Detect Thingiverse zip pattern: Name_12345_files.zip or Name-12345.zip
            if (f.name.toLowerCase().endsWith('.zip')) {
                const tvMatch = stem.match(/[\s_-]+(\d{4,})(?:[\s_-]+files)?$/i);
                if (tvMatch) {
                    const thingId = tvMatch[1];
                    const titlePart = stem.slice(0, tvMatch.index).replace(/[\s_-]+$/g, '').trim();
                    uploadZipMeta.value = {
                        title: titlePart || stem,
                        source_url: `https://www.thingiverse.com/thing:${thingId}`,
                        site: 'thingiverse',
                    };
                    if (!seen.has('thingiverse')) { seen.add('thingiverse'); suggestions.push('thingiverse'); }
                } else {
                    // Generic zip — show title from filename
                    const cleaned = stem.replace(/[_-]+/g, ' ').trim();
                    uploadZipMeta.value = { title: cleaned, source_url: null, site: null };
                }
            }

            // Split on separators + camelCase
            const words = stem
                .replace(/([a-z])([A-Z])/g, '$1 $2')
                .replace(/[_\-.\s]+/g, ' ')
                .split(' ')
                .map(w => w.trim().toLowerCase())
                .filter(w => w.length >= 2 && !w.match(/^\d+$/) && !stopWords.has(w));
            for (const w of words) {
                if (!seen.has(w)) { seen.add(w); suggestions.push(w); }
            }
        }
        uploadTagSuggestions.value = suggestions.slice(0, 15);
    }

    async function startUpload() {
        if (!uploadFiles.value.length || !importLibraryId.value) return;
        importRunning.value = true;
        importDone.value = false;
        uploadResults.value = [];
        saveDestination();

        const formData = new FormData();
        formData.append('library_id', importLibraryId.value);
        if (importSubfolder.value) formData.append('subfolder', importSubfolder.value);
        const tagStr = uploadTags.value.trim();
        if (tagStr) formData.append('tags', tagStr);
        if (uploadCollectionId.value) formData.append('collection_id', uploadCollectionId.value);
        const uploadNameStr = uploadName.value.trim();
        if (uploadNameStr) formData.append('name', uploadNameStr);
        const srcUrl = uploadSourceUrl.value.trim() || (uploadZipMeta.value?.source_url || '');
        if (srcUrl) formData.append('source_url', srcUrl);
        const desc = uploadDescription.value.trim();
        if (desc) formData.append('description', desc);
        for (const f of uploadFiles.value) {
            formData.append('files', f);
        }

        try {
            const data = await apiUploadFiles(formData);
            uploadResults.value = data.results || [];
            importDone.value = true;
            refreshData();
            fetchCollectionsFn();
        } catch (e) {
            showToast(e.message || 'Upload failed', 'error');
        } finally {
            importRunning.value = false;
        }
    }

    function addUploadTagSuggestion(tag) {
        const current = uploadTags.value.split(',').map(t => t.trim()).filter(Boolean);
        if (!current.includes(tag)) {
            current.push(tag);
            uploadTags.value = current.join(', ');
        }
        uploadTagSuggestions.value = uploadTagSuggestions.value.filter(t => t !== tag);
    }

    async function fetchImportCredentials() {
        try {
            importCredentials.value = await apiGetImportCredentials();
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
            importCredentials.value = await apiSaveImportCredential(site, creds);
            credentialInputs[site] = '';
            showToast(`${site} credentials saved`);
        } catch (e) {
            showToast('Failed to save credentials', 'error');
        }
    }

    async function deleteImportCredential(site) {
        try {
            importCredentials.value = await apiDeleteImportCredential(site);
            showToast(`${site} credentials removed`);
        } catch (e) {
            showToast('Failed to remove credentials', 'error');
        }
    }

    return {
        // State
        showImportModal,
        importMode,
        importUrls,
        importLibraryId,
        importSubfolder,
        importRunning,
        importDone,
        importPreview,
        importProgress,
        uploadFiles,
        uploadResults,
        uploadTags,
        uploadTagSuggestions,
        uploadCollectionId,
        uploadName,
        uploadSourceUrl,
        uploadDescription,
        uploadZipMeta,
        importCredentials,
        credentialInputs,

        // Actions
        openImportModal,
        closeImportModal,
        previewImportUrl,
        startImport,
        onFilesSelected,
        setImportUrls,
        clearUploadFiles,
        startUpload,
        addUploadTagSuggestion,
        fetchImportCredentials,
        saveImportCredential,
        deleteImportCredential,
    };
}
