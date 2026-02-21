<script setup>
/**
 * CollectionModal - Create collection and add-to-collection modals.
 */
import { ICONS } from '../icons.js';

defineProps({
    showCollectionModal: { type: Boolean, default: false },
    showAddToCollectionModal: { type: Boolean, default: false },
    newCollectionName: { type: String, default: '' },
    newCollectionColor: { type: String, default: '#4f8cff' },
    addToCollectionModelId: { default: null },
    collections: { type: Array, default: () => [] },
    COLLECTION_COLORS: { type: Array, default: () => [] },
    inlineNewCollection: { type: Object, default: () => ({ active: false, name: '', color: '#4f8cff' }) },
});

const emit = defineEmits([
    'update:showCollectionModal',
    'update:showAddToCollectionModal',
    'update:newCollectionName',
    'update:newCollectionColor',
    'createCollection',
    'handleCollectionSelect',
    'startInlineNewCollection',
    'confirmInlineNewCollection',
    'cancelInlineNewCollection',
    'pickNextCollectionColor',
    'updateInlineNewCollectionName',
    'updateInlineNewCollectionColor',
]);
</script>

<template>
    <!-- Create Collection Modal -->
    <div v-if="showCollectionModal" class="detail-overlay" @click.self="emit('update:showCollectionModal', false)">
        <div class="mini-modal">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
                <h3 style="margin:0">New Collection</h3>
                <button class="close-btn" @click="emit('update:showCollectionModal', false)">&times;</button>
            </div>
            <div class="form-row">
                <label class="form-label">Name</label>
                <input class="form-input" :value="newCollectionName"
                       @input="emit('update:newCollectionName', $event.target.value)"
                       placeholder="Collection name"
                       @keydown.enter="emit('createCollection')">
            </div>
            <div class="form-row">
                <label class="form-label">Color</label>
                <div class="color-swatch-grid">
                    <button v-for="c in COLLECTION_COLORS" :key="c"
                            class="color-swatch" :class="{ active: newCollectionColor === c }"
                            :style="{ background: c }"
                            @click="emit('update:newCollectionColor', c)"
                            type="button"></button>
                </div>
            </div>
            <div class="form-actions">
                <button class="btn btn-secondary" @click="emit('update:showCollectionModal', false)">Cancel</button>
                <button class="btn btn-primary" @click="emit('createCollection')">Create</button>
            </div>
        </div>
    </div>

    <!-- Add to Collection Modal -->
    <div v-if="showAddToCollectionModal" class="detail-overlay" @click.self="emit('update:showAddToCollectionModal', false)">
        <div class="mini-modal">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
                <h3 style="margin:0">Add to Collection</h3>
                <button class="close-btn" @click="emit('update:showAddToCollectionModal', false)">&times;</button>
            </div>
            <div v-for="col in collections" :key="col.id"
                 class="sidebar-item" @click="emit('handleCollectionSelect', col.id)">
                <span class="collection-dot" :style="{ background: col.color || '#666' }"></span>
                <span>{{ col.name }}</span>
                <span class="item-count">{{ col.model_count }}</span>
            </div>
            <!-- Inline new collection -->
            <div v-if="inlineNewCollection.active" class="inline-new-collection">
                <div style="display:flex;gap:8px;align-items:center">
                    <span class="collection-dot" :style="{ background: inlineNewCollection.color }" style="flex-shrink:0;cursor:pointer"
                          @click="emit('pickNextCollectionColor')"></span>
                    <input class="form-input" :value="inlineNewCollection.name"
                           @input="emit('updateInlineNewCollectionName', $event.target.value)"
                           placeholder="Collection name"
                           @keydown.enter="emit('confirmInlineNewCollection', 'addToCollection')"
                           @keydown.escape="emit('cancelInlineNewCollection')"
                           style="flex:1;padding:4px 8px;font-size:0.85rem" autofocus>
                    <button class="btn btn-primary btn-sm" @click="emit('confirmInlineNewCollection', 'addToCollection')"
                            :disabled="!inlineNewCollection.name.trim()">Add</button>
                    <button class="btn btn-ghost btn-sm" @click="emit('cancelInlineNewCollection')">&times;</button>
                </div>
                <div class="color-swatch-grid" style="margin-top:6px">
                    <button v-for="c in COLLECTION_COLORS" :key="c"
                            class="color-swatch color-swatch-sm" :class="{ active: inlineNewCollection.color === c }"
                            :style="{ background: c }"
                            @click="emit('updateInlineNewCollectionColor', c)"
                            type="button"></button>
                </div>
            </div>
            <div v-else class="sidebar-item" @click="emit('startInlineNewCollection')" style="color:var(--color-primary, #4f8cff)">
                <span v-html="ICONS.plus"></span>
                <span>New Collection</span>
            </div>
        </div>
    </div>
</template>
