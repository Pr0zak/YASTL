/**
 * YASTL - Collections composable
 *
 * Manages collection state, CRUD operations, inline creation,
 * and smart collection support.
 */

import {
    apiGetCollections,
    apiCreateCollection,
    apiUpdateCollection,
    apiDeleteCollection,
    apiAddToCollection,
    apiRemoveFromCollection,
} from '../api.js';

import { ref, reactive, computed } from 'vue';

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

    // Smart collection creation/editing state
    const showSmartCollectionModal = ref(false);
    const editingSmartCollection = ref(null); // null = creating new, object = editing existing
    const smartCollectionForm = reactive({
        name: '',
        color: '#0f9b8e',
        rules: {
            format: '',
            tags: [],
            categories: [],
            library_id: null,
            favoritesOnly: false,
            duplicatesOnly: false,
            sizeMin: null,
            sizeMax: null,
            dateRange: '',
        },
    });

    // Split collections into regular and smart
    const regularCollections = computed(() =>
        collections.value.filter(c => !c.is_smart)
    );

    const smartCollections = computed(() =>
        collections.value.filter(c => c.is_smart)
    );

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
            if (filters && filters.smartCollection === id) {
                filters.smartCollection = null;
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

    // ---- Smart Collection CRUD ----

    function openSmartCollectionModal(existing = null) {
        if (existing) {
            editingSmartCollection.value = existing;
            smartCollectionForm.name = existing.name;
            smartCollectionForm.color = existing.color || '#0f9b8e';
            const rules = typeof existing.rules === 'string'
                ? JSON.parse(existing.rules || '{}')
                : (existing.rules || {});
            smartCollectionForm.rules.format = rules.format || '';
            smartCollectionForm.rules.tags = rules.tags || [];
            smartCollectionForm.rules.categories = rules.categories || [];
            smartCollectionForm.rules.library_id = rules.library_id || null;
            smartCollectionForm.rules.favoritesOnly = rules.favoritesOnly || false;
            smartCollectionForm.rules.duplicatesOnly = rules.duplicatesOnly || false;
            smartCollectionForm.rules.sizeMin = rules.sizeMin || null;
            smartCollectionForm.rules.sizeMax = rules.sizeMax || null;
            smartCollectionForm.rules.dateRange = rules.dateRange || '';
        } else {
            editingSmartCollection.value = null;
            smartCollectionForm.name = '';
            smartCollectionForm.color = pickNextCollectionColor();
            smartCollectionForm.rules.format = '';
            smartCollectionForm.rules.tags = [];
            smartCollectionForm.rules.categories = [];
            smartCollectionForm.rules.library_id = null;
            smartCollectionForm.rules.favoritesOnly = false;
            smartCollectionForm.rules.duplicatesOnly = false;
            smartCollectionForm.rules.sizeMin = null;
            smartCollectionForm.rules.sizeMax = null;
            smartCollectionForm.rules.dateRange = '';
        }
        showSmartCollectionModal.value = true;
    }

    async function saveSmartCollection() {
        const name = smartCollectionForm.name.trim();
        if (!name) return;

        // Build clean rules object (omit empty values)
        const rules = {};
        if (smartCollectionForm.rules.format) rules.format = smartCollectionForm.rules.format;
        if (smartCollectionForm.rules.tags.length > 0) rules.tags = [...smartCollectionForm.rules.tags];
        if (smartCollectionForm.rules.categories.length > 0) rules.categories = [...smartCollectionForm.rules.categories];
        if (smartCollectionForm.rules.library_id) rules.library_id = smartCollectionForm.rules.library_id;
        if (smartCollectionForm.rules.favoritesOnly) rules.favoritesOnly = true;
        if (smartCollectionForm.rules.duplicatesOnly) rules.duplicatesOnly = true;
        if (smartCollectionForm.rules.sizeMin) rules.sizeMin = smartCollectionForm.rules.sizeMin;
        if (smartCollectionForm.rules.sizeMax) rules.sizeMax = smartCollectionForm.rules.sizeMax;
        if (smartCollectionForm.rules.dateRange) rules.dateRange = smartCollectionForm.rules.dateRange;

        try {
            if (editingSmartCollection.value) {
                // Update existing
                await apiUpdateCollection(editingSmartCollection.value.id, {
                    name,
                    color: smartCollectionForm.color,
                    rules,
                });
            } else {
                // Create new
                await apiCreateCollection({
                    name,
                    color: smartCollectionForm.color,
                    is_smart: true,
                    rules,
                });
            }
            showSmartCollectionModal.value = false;
            await fetchCollections();
            showToast(editingSmartCollection.value ? 'Smart collection updated' : 'Smart collection created', 'success');
        } catch (e) {
            showToast('Failed to save smart collection', 'error');
        }
    }

    return {
        // State
        collections,
        regularCollections,
        smartCollections,
        COLLECTION_COLORS,
        showCollectionModal,
        newCollectionName,
        newCollectionColor,
        addToCollectionModelId,
        showAddToCollectionModal,
        editingCollectionId,
        editCollectionName,
        inlineNewCollection,
        showSmartCollectionModal,
        editingSmartCollection,
        smartCollectionForm,

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
        openSmartCollectionModal,
        saveSmartCollection,
    };
}
