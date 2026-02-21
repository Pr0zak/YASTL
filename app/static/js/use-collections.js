/**
 * YASTL - Collections composable
 *
 * Manages collection state, CRUD operations, and inline creation.
 */

import {
    apiGetCollections,
    apiCreateCollection,
    apiUpdateCollection,
    apiDeleteCollection,
    apiAddToCollection,
    apiRemoveFromCollection,
} from './api.js';

const { ref, reactive } = Vue;

/**
 * @param {Function} showToast - Toast notification function
 */
export function useCollections(showToast) {
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
    const inlineNewCollection = reactive({ active: false, name: '', color: '#0f9b8e' });

    function pickNextCollectionColor() {
        const used = new Set(collections.value.map(c => (c.color || '').toLowerCase()));
        return COLLECTION_COLORS.find(c => !used.has(c.toLowerCase())) || COLLECTION_COLORS[0];
    }

    async function fetchCollections() {
        try {
            const data = await apiGetCollections();
            collections.value = data.collections || [];
        } catch (e) {
            console.error('Failed to fetch collections', e);
        }
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
            await apiCreateCollection({ name, color: newCollectionColor.value });
            showCollectionModal.value = false;
            newCollectionName.value = '';
            newCollectionColor.value = '#0f9b8e';
            await fetchCollections();
            showToast('Collection created', 'success');
        } catch (e) {
            showToast('Failed to create collection', 'error');
        }
    }

    function startInlineNewCollection() {
        inlineNewCollection.active = true;
        inlineNewCollection.name = '';
        inlineNewCollection.color = pickNextCollectionColor();
    }

    /**
     * @param {string} context - 'upload' or 'addToCollection'
     * @param {Function} onCreated - Callback receiving the new collection id
     */
    async function confirmInlineNewCollection(context, onCreated) {
        const name = inlineNewCollection.name.trim();
        if (!name) return;
        try {
            const created = await apiCreateCollection({ name, color: inlineNewCollection.color });
            inlineNewCollection.active = false;
            await fetchCollections();
            if (onCreated) onCreated(created.id, context);
            showToast('Collection created', 'success');
        } catch (e) {
            showToast('Failed to create collection', 'error');
        }
    }

    function cancelInlineNewCollection() {
        inlineNewCollection.active = false;
    }

    async function deleteCollection(id, filters) {
        try {
            await apiDeleteCollection(id);
            if (filters && filters.collection === id) {
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
            await apiUpdateCollection(col.id, { name: newName });
            await fetchCollections();
        } catch (e) {
            showToast('Failed to rename collection', 'error');
        }
    }

    function openAddToCollection(modelId) {
        addToCollectionModelId.value = modelId;
        showAddToCollectionModal.value = true;
    }

    async function addModelToCollection(collectionId, refreshSelectedModel) {
        const modelId = addToCollectionModelId.value;
        if (!modelId) return;
        try {
            await apiAddToCollection(collectionId, [modelId]);
            showAddToCollectionModal.value = false;
            addToCollectionModelId.value = null;
            await fetchCollections();
            if (refreshSelectedModel) await refreshSelectedModel(modelId);
            showToast('Added to collection', 'success');
        } catch (e) {
            showToast('Failed to add to collection', 'error');
        }
    }

    async function removeModelFromCollection(collectionId, modelId, refreshSelectedModel) {
        try {
            await apiRemoveFromCollection(collectionId, modelId);
            await fetchCollections();
            if (refreshSelectedModel) await refreshSelectedModel(modelId);
            showToast('Removed from collection', 'success');
        } catch (e) {
            showToast('Failed to remove from collection', 'error');
        }
    }

    return {
        // State
        collections,
        COLLECTION_COLORS,
        showCollectionModal,
        newCollectionName,
        newCollectionColor,
        addToCollectionModelId,
        showAddToCollectionModal,
        editingCollectionId,
        editCollectionName,
        inlineNewCollection,

        // Actions
        pickNextCollectionColor,
        fetchCollections,
        openCollectionModal,
        createCollection,
        startInlineNewCollection,
        confirmInlineNewCollection,
        cancelInlineNewCollection,
        deleteCollection,
        startEditCollection,
        saveCollectionName,
        openAddToCollection,
        addModelToCollection,
        removeModelFromCollection,
    };
}
