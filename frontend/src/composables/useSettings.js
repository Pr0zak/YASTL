/**
 * YASTL - Settings composable
 *
 * Manages settings modal state, library management, and thumbnail settings.
 */

import {
    apiGetLibraries,
    apiAddLibrary,
    apiRemoveLibrary,
    apiGetSettings,
    apiUpdateSettings,
    apiRegenerateThumbnails,
    apiGetRegenStatus,
    apiAutoTagAll,
    apiGetAutoTagStatus,
} from '../api.js';

import { ref, reactive } from 'vue';

/**
 * @param {Function} showToast - Toast notification function
 * @param {Function} fetchModelsFn - Callback to refresh models after regen
 * @param {Function} showConfirm - Confirm dialog function
 * @param {Function} fetchTagsFn - Callback to refresh tags after auto-tag
 */
export function useSettings(showToast, fetchModelsFn, showConfirm, fetchTagsFn) {
    const showSettings = ref(false);
    const libraries = ref([]);
    const newLibName = ref('');
    const newLibPath = ref('');
    const addingLibrary = ref(false);
    const thumbnailMode = ref('wireframe');
    const regeneratingThumbnails = ref(false);
    const regenProgress = reactive({ running: false, total: 0, completed: 0 });
    const autoTagging = ref(false);
    const autoTagProgress = reactive({ running: false, total: 0, completed: 0, tags_added: 0 });

    let regenPollTimer = null;
    let autoTagPollTimer = null;

    async function fetchLibraries() {
        try {
            const data = await apiGetLibraries();
            libraries.value = data.libraries || [];
        } catch (err) {
            console.error('fetchLibraries error:', err);
        }
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
            const { ok, data } = await apiAddLibrary(name, path);
            if (ok) {
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
        if (!await showConfirm({
            title: 'Remove Library',
            message: `Remove "${lib.name}"? Scanned models stay in database.`,
            action: 'Remove',
            danger: true,
        })) return;
        try {
            await apiRemoveLibrary(lib.id);
            libraries.value = libraries.value.filter((l) => l.id !== lib.id);
            showToast(`Library "${lib.name}" removed`);
        } catch (err) {
            showToast('Failed to remove library', 'error');
        }
    }

    async function fetchSettings() {
        try {
            const data = await apiGetSettings();
            thumbnailMode.value = data.thumbnail_mode || 'wireframe';
        } catch (err) {
            console.error('fetchSettings error:', err);
        }
    }

    async function setThumbnailMode(mode) {
        try {
            const data = await apiUpdateSettings({ thumbnail_mode: mode });
            thumbnailMode.value = data.thumbnail_mode || mode;
            showToast(`Thumbnail mode set to ${mode}`);
        } catch (err) {
            showToast('Failed to update setting', 'error');
            console.error('setThumbnailMode error:', err);
        }
    }

    async function regenerateThumbnails() {
        if (!await showConfirm({
            title: 'Regenerate Thumbnails',
            message: 'Re-render all thumbnails using current mode? Runs in background.',
            action: 'Regenerate',
        })) return;
        regeneratingThumbnails.value = true;
        try {
            await apiRegenerateThumbnails();
            showToast('Thumbnail regeneration started', 'info');
            startRegenPolling();
        } catch (err) {
            showToast(err.message || 'Failed to start thumbnail regeneration', 'error');
            console.error('regenerateThumbnails error:', err);
            regeneratingThumbnails.value = false;
        }
    }

    function startRegenPolling() {
        if (regenPollTimer) clearInterval(regenPollTimer);
        regenPollTimer = setInterval(async () => {
            try {
                const data = await apiGetRegenStatus();
                regenProgress.running = data.running;
                regenProgress.total = data.total;
                regenProgress.completed = data.completed;
                if (!data.running) {
                    clearInterval(regenPollTimer);
                    regenPollTimer = null;
                    regeneratingThumbnails.value = false;
                    showToast('Thumbnail regeneration complete');
                    fetchModelsFn();
                }
            } catch (err) {
                console.error('regenPoll error:', err);
            }
        }, 2000);
    }

    async function autoTagAll() {
        if (!await showConfirm({
            title: 'Auto-Tag All Models',
            message: 'Generate and apply suggested tags to all models? Runs in background.',
            action: 'Auto-Tag',
        })) return;
        autoTagging.value = true;
        try {
            await apiAutoTagAll();
            showToast('Auto-tagging started', 'info');
            startAutoTagPolling();
        } catch (err) {
            showToast(err.message || 'Failed to start auto-tagging', 'error');
            console.error('autoTagAll error:', err);
            autoTagging.value = false;
        }
    }

    function startAutoTagPolling() {
        if (autoTagPollTimer) clearInterval(autoTagPollTimer);
        autoTagPollTimer = setInterval(async () => {
            try {
                const data = await apiGetAutoTagStatus();
                autoTagProgress.running = data.running;
                autoTagProgress.total = data.total;
                autoTagProgress.completed = data.completed;
                autoTagProgress.tags_added = data.tags_added;
                if (!data.running) {
                    clearInterval(autoTagPollTimer);
                    autoTagPollTimer = null;
                    autoTagging.value = false;
                    showToast(`Auto-tagging complete: ${data.tags_added} tags added`);
                    fetchModelsFn();
                    if (fetchTagsFn) fetchTagsFn();
                }
            } catch (err) {
                console.error('autoTagPoll error:', err);
            }
        }, 2000);
    }

    function openSettings(checkForUpdatesFn, updateInfo) {
        fetchLibraries();
        fetchSettings();
        showSettings.value = true;
        document.body.classList.add('modal-open');
        // Auto-check for updates if not checked yet
        if (checkForUpdatesFn && updateInfo && !updateInfo.checked && !updateInfo.checking) {
            checkForUpdatesFn();
        }
    }

    function closeSettings(showDetail) {
        showSettings.value = false;
        if (!showDetail) {
            document.body.classList.remove('modal-open');
        }
    }

    return {
        // State
        showSettings,
        libraries,
        newLibName,
        newLibPath,
        addingLibrary,
        thumbnailMode,
        regeneratingThumbnails,
        regenProgress,
        autoTagging,
        autoTagProgress,

        // Actions
        fetchLibraries,
        addLibrary,
        deleteLibrary,
        fetchSettings,
        setThumbnailMode,
        regenerateThumbnails,
        autoTagAll,
        openSettings,
        closeSettings,
    };
}
