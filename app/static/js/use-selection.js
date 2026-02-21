/**
 * YASTL - Selection mode composable
 *
 * Manages multi-select state and bulk operations.
 */

import {
    apiBulkFavorite,
    apiBulkAddTags,
    apiBulkAutoTag,
    apiBulkAddToCollection,
    apiBulkDelete,
} from './api.js';

const { ref, reactive } = Vue;

/**
 * @param {Function} showToast - Toast notification function
 * @param {Function} fetchModels - Callback to refresh model list
 * @param {import('vue').Ref} models - Reactive ref of models
 * @param {Function} fetchTags - Callback to refresh tags
 * @param {Function} fetchFavoritesCount - Callback to refresh favorites count
 * @param {Function} fetchCollections - Callback to refresh collections
 */
export function useSelection(showToast, fetchModels, models, fetchTags, fetchFavoritesCount, fetchCollections) {
    const selectionMode = ref(false);
    const selectedModels = reactive(new Set());
    const showBulkTagModal = ref(false);
    const bulkTagInput = ref('');

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
            await apiBulkFavorite(ids, true);
            selectedModels.clear();
            selectionMode.value = false;
            await fetchModels();
            await fetchFavoritesCount();
            showToast(`${ids.length} model(s) favorited`, 'success');
        } catch {
            showToast('Bulk favorite failed', 'error');
        }
    }

    async function bulkAutoTag() {
        const ids = [...selectedModels];
        if (!ids.length) return;
        try {
            const data = await apiBulkAutoTag(ids);
            showToast(`Auto-tagged ${data.models_tagged} model(s) with ${data.tags_added} tags`, 'success');
            selectedModels.clear();
            selectionMode.value = false;
            await fetchModels();
            await fetchTags();
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
            await apiBulkAddTags(ids, tags);
            showToast(`Tags applied to ${ids.length} model(s)`, 'success');
            showBulkTagModal.value = false;
            bulkTagInput.value = '';
            selectedModels.clear();
            selectionMode.value = false;
            await fetchModels();
            await fetchTags();
        } catch {
            showToast('Bulk tag failed', 'error');
        }
    }

    async function bulkAddToCollection(collectionId, showAddToCollectionModal) {
        const ids = [...selectedModels];
        if (!ids.length || !collectionId) return;
        try {
            await apiBulkAddToCollection(ids, collectionId);
            selectedModels.clear();
            selectionMode.value = false;
            if (showAddToCollectionModal) showAddToCollectionModal.value = false;
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
            await apiBulkDelete(ids);
            selectedModels.clear();
            selectionMode.value = false;
            await fetchModels();
            showToast(`${ids.length} model(s) deleted`, 'success');
        } catch {
            showToast('Bulk delete failed', 'error');
        }
    }

    return {
        // State
        selectionMode,
        selectedModels,
        showBulkTagModal,
        bulkTagInput,

        // Actions
        toggleSelectionMode,
        toggleModelSelection,
        selectAll,
        deselectAll,
        isSelected,
        bulkFavorite,
        bulkAutoTag,
        bulkAddTags,
        bulkAddToCollection,
        bulkDelete,
    };
}
