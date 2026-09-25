<script setup>
/**
 * CollectionModal - "Add to collection" picker, from the detail panel or
 * the selection bar. New collections are created inline at the bottom.
 */
import { ICONS } from '../icons.js';
import AppDialog from './AppDialog.vue';

defineProps({
    show: { type: Boolean, default: false },
    collections: { type: Array, default: () => [] },
    COLLECTION_COLORS: { type: Array, default: () => [] },
    inlineNewCollection: { type: Object, default: () => ({ active: false, name: '', color: '#0f9b8e' }) },
});

const emit = defineEmits([
    'close',
    'handleCollectionSelect',
    'startInlineNewCollection',
    'confirmInlineNewCollection',
    'cancelInlineNewCollection',
    'updateInlineNewCollectionName',
    'updateInlineNewCollectionColor',
]);
</script>

<template>
    <AppDialog :show="show" title="Add to collection" size="sm" @close="emit('close')">
        <ul class="pick-list">
            <li v-for="col in collections" :key="col.id">
                <button type="button" class="pick-row" @click="emit('handleCollectionSelect', col.id)">
                    <span class="collection-dot" :style="{ background: col.color || 'var(--text-muted)' }"></span>
                    <span class="pick-name">{{ col.name }}</span>
                    <span class="pick-count">{{ col.model_count }}</span>
                </button>
            </li>
        </ul>

        <form v-if="inlineNewCollection.active" class="inline-new-collection"
              @submit.prevent="emit('confirmInlineNewCollection', 'addToCollection')">
            <label class="form-label" for="new-col-name">New collection</label>
            <div class="inline-new-row">
                <input id="new-col-name" class="form-input" :value="inlineNewCollection.name" data-autofocus
                       @input="emit('updateInlineNewCollectionName', $event.target.value)"
                       placeholder="Collection name"
                       @keydown.escape.stop="emit('cancelInlineNewCollection')">
                <button type="submit" class="btn btn-primary" :disabled="!inlineNewCollection.name.trim()">Create</button>
                <button type="button" class="btn btn-ghost" @click="emit('cancelInlineNewCollection')">Cancel</button>
            </div>
            <div class="color-swatch-grid" role="radiogroup" aria-label="Collection colour">
                <button v-for="c in COLLECTION_COLORS" :key="c"
                        class="color-swatch color-swatch-sm" :class="{ active: inlineNewCollection.color === c }"
                        :style="{ background: c }" role="radio" :aria-checked="String(inlineNewCollection.color === c)"
                        :aria-label="'Colour ' + c"
                        @click="emit('updateInlineNewCollectionColor', c)"
                        type="button"></button>
            </div>
        </form>
        <button v-else type="button" class="pick-row pick-new" @click="emit('startInlineNewCollection')">
            <span v-html="ICONS.plus"></span>
            <span class="pick-name">New collection</span>
        </button>
    </AppDialog>
</template>

<style scoped>
.pick-list { list-style: none; display: flex; flex-direction: column; gap: 2px; margin-bottom: 6px; }
.pick-row {
    width: 100%; display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 10px;
    background: none; color: var(--text-primary); border-radius: var(--radius); text-align: left; font-size: 0.9rem;
}
.pick-row:hover { background: var(--bg-hover); }
.pick-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pick-count { color: var(--text-muted); font-size: 0.8rem; font-variant-numeric: tabular-nums; }
.pick-new { color: var(--accent-hover); }
.inline-new-collection { display: flex; flex-direction: column; gap: 8px; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-card); }
.inline-new-row { display: flex; gap: 8px; }
.inline-new-row .form-input { flex: 1; min-width: 0; }
</style>
