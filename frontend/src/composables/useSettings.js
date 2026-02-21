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
} from '../api.js';

import { ref, reactive } from 'vue';

/**
 * @param {Function} showToast - Toast notification function
 * @param {Function} fetchModelsFn - Callback to refresh models after regen
 */
export function useSettings(showToast, fetchModelsFn) {
    const showSettings = ref(false);
    const libraries = ref([]);
    const newLibName = ref('');
    const newLibPath = ref('');
    const addingLibrary = ref(false);
    const thumbnailMode = ref('wireframe');
    const regeneratingThumbnails = ref(false);
    const regenProgress = reactive({ running: false, total: 0, completed: 0 });

    let regenPollTimer = null;

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
        if (!confirm(`Remove library "${lib.name}"?\n\nModels already scanned from this library will remain in the database.`)) {
            return;
        }
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
        if (!confirm('Regenerate all thumbnails?\n\nThis will re-render every model thumbnail using the current mode. This runs in the background.')) {
            return;
        }
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

        // Actions
        fetchLibraries,
        addLibrary,
        deleteLibrary,
        fetchSettings,
        setThumbnailMode,
        regenerateThumbnails,
        openSettings,
        closeSettings,
    };
}
