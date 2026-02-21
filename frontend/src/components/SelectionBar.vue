<script setup>
/**
 * SelectionBar - Bulk actions toolbar shown when models are selected.
 */
import { ICONS } from '../icons.js';

defineProps({
    selectionMode: { type: Boolean, default: false },
    selectedModels: { type: Set, default: () => new Set() },
});

const emit = defineEmits([
    'selectAll',
    'deselectAll',
    'bulkFavorite',
    'showBulkTagModal',
    'bulkAutoTag',
    'openBulkAddToCollection',
    'bulkDelete',
]);
</script>

<template>
    <div v-if="selectionMode && selectedModels.size > 0" class="selection-bar">
        <div class="selection-info">
            <strong>{{ selectedModels.size }}</strong> selected
            <button class="btn btn-sm btn-ghost" @click="emit('selectAll')">Select All</button>
            <button class="btn btn-sm btn-ghost" @click="emit('deselectAll')">Deselect All</button>
        </div>
        <div class="selection-actions">
            <button class="btn btn-sm btn-primary" @click="emit('bulkFavorite')">
                <span v-html="ICONS.heart"></span> Favorite
            </button>
            <button class="btn btn-sm btn-secondary" @click="emit('showBulkTagModal')">
                Tag
            </button>
            <button class="btn btn-sm btn-secondary" @click="emit('bulkAutoTag')">
                Auto-Tag
            </button>
            <button class="btn btn-sm btn-secondary" @click="emit('openBulkAddToCollection')">
                <span v-html="ICONS.collection"></span> Collection
            </button>
            <button class="btn btn-sm btn-danger" @click="emit('bulkDelete')">
                <span v-html="ICONS.trash"></span> Delete
            </button>
        </div>
    </div>
</template>
