<script setup>
/**
 * SideBar — where you go, not what you filter by.
 *
 * Filters (format, tags, category, library) moved to chips above the grid,
 * so this column holds places: all models, favourites, your collections,
 * saved searches, and a small "Library health" group for the system-made
 * lists (duplicates and files that failed to process) that used to sit
 * among your own collections.
 *
 * Collection tools (pin, rules, rename, delete) live behind one "⋯" per row.
 * They used to be three always-visible 22px buttons on touch screens, with
 * delete a bare × right next to the count.
 */
import { computed, ref, watch, nextTick, onBeforeUnmount } from 'vue';
import { ICONS } from '../icons.js';

const FAILED_COLLECTION = 'Failed to Process';

const dragOverCollection = ref(null);

const props = defineProps({
    sidebarOpen: { type: Boolean, default: false },
    filters: { type: Object, required: true },
    hasActiveFilters: { type: Boolean, default: false },
    collections: { type: Array, default: () => [] },
    favoritesCount: { type: Number, default: 0 },
    savedSearches: { type: Array, default: () => [] },
    editingCollectionId: { default: null },
    editCollectionName: { type: String, default: '' },
    totalCount: { type: Number, default: 0 },
    duplicateGroups: { type: Number, default: 0 },
});

const emit = defineEmits([
    'update:sidebarOpen',
    'update:editCollectionName',
    'setCollectionFilter',
    'toggleFavoritesFilter',
    'toggleDuplicatesFilter',
    'openDuplicatesReview',
    'openCollectionModal',
    'editCollection',
    'togglePinCollection',
    'dropOnCollection',
    'startEditCollection',
    'saveCollectionName',
    'cancelEditCollection',
    'deleteCollection',
    'applySavedSearch',
    'deleteSavedSearch',
    'clearFilters',
]);

const userCollections = computed(() => props.collections.filter((c) => c.name !== FAILED_COLLECTION));
const failedCollection = computed(() => props.collections.find((c) => c.name === FAILED_COLLECTION) || null);

function onDropCollection(col) {
    dragOverCollection.value = null;
    emit('dropOnCollection', col.id);
}

/* ---- Row menu ("⋯") ---- */
const menu = ref(null); // { kind: 'collection' | 'search', id }
const menuEl = ref(null);

function toggleMenu(kind, id) {
    menu.value = menu.value && menu.value.kind === kind && menu.value.id === id ? null : { kind, id };
}
function isMenu(kind, id) {
    return !!menu.value && menu.value.kind === kind && menu.value.id === id;
}
function run(fn) {
    menu.value = null;
    fn();
}
function onOutside(e) {
    const el = Array.isArray(menuEl.value) ? menuEl.value[0] : menuEl.value;
    if (el && !el.contains(e.target) && !e.target.closest('.sb-more')) menu.value = null;
}
function onEsc(e) {
    if (e.key === 'Escape') { e.stopPropagation(); menu.value = null; }
}
watch(menu, async (m) => {
    const fn = m ? 'addEventListener' : 'removeEventListener';
    document[fn]('pointerdown', onOutside, true);
    document[fn]('keydown', onEsc, true);
    if (m) {
        await nextTick();
        const el = Array.isArray(menuEl.value) ? menuEl.value[0] : menuEl.value;
        el?.querySelector('button')?.focus();
    }
});
onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', onOutside, true);
    document.removeEventListener('keydown', onEsc, true);
});
</script>

<template>
    <div v-if="sidebarOpen" class="sidebar-backdrop" @click="emit('update:sidebarOpen', false)"></div>

    <!-- `open` drives the phone drawer (a fixed panel parked off-screen);
         `collapsed` is the desktop width-zero state. Both are needed. -->
    <aside class="sidebar" :class="{ open: sidebarOpen, collapsed: !sidebarOpen }" aria-label="Collections">

        <div class="sidebar-section">
            <div class="sb-label">Library</div>
            <button class="sb-row" :class="{ on: !hasActiveFilters }" @click="emit('clearFilters')">
                <span class="sb-row-icon" v-html="ICONS.home"></span>
                <span class="sb-row-name">All models</span><span class="sb-num">{{ totalCount.toLocaleString() }}</span>
            </button>
            <button class="sb-row" :class="{ on: filters.favoritesOnly }" :aria-pressed="String(filters.favoritesOnly)"
                    @click="emit('toggleFavoritesFilter')">
                <span class="sb-row-icon" v-html="ICONS.heart"></span>
                <span class="sb-row-name">Favourites</span><span class="sb-num">{{ favoritesCount }}</span>
            </button>
        </div>

        <div class="sidebar-section">
            <div class="sb-label">
                Collections
                <button class="sb-add" @click="emit('openCollectionModal')" title="New collection" aria-label="New collection">
                    <span v-html="ICONS.plus"></span>
                </button>
            </div>
            <div v-for="col in userCollections" :key="col.id" class="sb-item"
                 :class="{ 'drop-target': dragOverCollection === col.id }"
                 @dragover.prevent="dragOverCollection = col.id"
                 @dragenter.prevent="dragOverCollection = col.id"
                 @dragleave="dragOverCollection === col.id && (dragOverCollection = null)"
                 @drop.prevent="onDropCollection(col)">
                <input v-if="editingCollectionId === col.id" class="sidebar-edit-input" :value="editCollectionName"
                       :aria-label="'Rename ' + col.name"
                       @input="emit('update:editCollectionName', $event.target.value)"
                       @blur="emit('saveCollectionName', col)"
                       @keydown.enter="emit('saveCollectionName', col)"
                       @keydown.escape.stop="emit('cancelEditCollection')"
                       @vue:mounted="$event.el.focus()">
                <template v-else>
                    <button class="sb-row" :class="{ on: filters.collection === col.id }"
                            :aria-pressed="String(filters.collection === col.id)"
                            @click="emit('setCollectionFilter', col.id)">
                        <span class="sb-dot" :style="{ background: col.color || 'var(--text-muted)' }" aria-hidden="true"></span>
                        <span class="sb-row-name">{{ col.name }}</span>
                        <span v-if="col.pinned" class="sb-pin" title="Pinned" v-html="ICONS.bookmark"></span>
                        <span v-if="col.is_smart" class="sb-smart" title="Smart collection" v-html="ICONS.zap"></span>
                        <span class="sb-num">{{ col.model_count }}</span>
                    </button>
                    <button class="sb-more" :class="{ open: isMenu('collection', col.id) }"
                            :aria-label="'Options for ' + col.name" aria-haspopup="menu"
                            :aria-expanded="String(isMenu('collection', col.id))"
                            @click="toggleMenu('collection', col.id)" v-html="ICONS.dots"></button>
                    <div v-if="isMenu('collection', col.id)" ref="menuEl" class="sb-menu" role="menu">
                        <button role="menuitem" @click="run(() => emit('togglePinCollection', col))">
                            <span v-html="ICONS.bookmark"></span>{{ col.pinned ? 'Unpin' : 'Pin to top' }}
                        </button>
                        <button role="menuitem" @click="run(() => emit('editCollection', col))">
                            <span v-html="ICONS.zap"></span>{{ col.is_smart ? 'Edit rules' : 'Colour and rules' }}
                        </button>
                        <button role="menuitem" @click="run(() => emit('startEditCollection', col))">
                            <span v-html="ICONS.edit"></span>Rename
                        </button>
                        <button role="menuitem" class="danger" @click="run(() => emit('deleteCollection', col.id))">
                            <span v-html="ICONS.trash"></span>Delete collection…
                        </button>
                    </div>
                </template>
            </div>
            <div v-if="!userCollections.length" class="sb-empty">
                No collections yet. Drag models onto one to add them.
            </div>
        </div>

        <div class="sidebar-section" v-if="savedSearches.length">
            <div class="sb-label">Saved searches</div>
            <div v-for="search in savedSearches" :key="search.id" class="sb-item">
                <button class="sb-row" @click="emit('applySavedSearch', search)">
                    <span class="sb-row-icon" v-html="ICONS.search"></span>
                    <span class="sb-row-name">{{ search.name }}</span>
                </button>
                <button class="sb-more" :class="{ open: isMenu('search', search.id) }"
                        :aria-label="'Options for ' + search.name" aria-haspopup="menu"
                        :aria-expanded="String(isMenu('search', search.id))"
                        @click="toggleMenu('search', search.id)" v-html="ICONS.dots"></button>
                <div v-if="isMenu('search', search.id)" ref="menuEl" class="sb-menu" role="menu">
                    <button role="menuitem" class="danger" @click="run(() => emit('deleteSavedSearch', search.id))">
                        <span v-html="ICONS.trash"></span>Delete saved search
                    </button>
                </div>
            </div>
        </div>

        <div class="sidebar-section sb-health">
            <div class="sb-label">Library health</div>
            <div class="sb-item">
                <button class="sb-row" :class="{ on: filters.duplicatesOnly }" :aria-pressed="String(filters.duplicatesOnly)"
                        @click="emit('toggleDuplicatesFilter')">
                    <span class="sb-row-icon" v-html="ICONS.copy"></span>
                    <span class="sb-row-name">Duplicates</span>
                    <span v-if="duplicateGroups" class="sb-num sb-num-warn" :title="duplicateGroups + ' groups of identical files'">{{ duplicateGroups }}</span>
                </button>
                <button class="sb-review" @click="emit('openDuplicatesReview')">Review</button>
            </div>
            <div v-if="failedCollection" class="sb-item">
                <button class="sb-row" :class="{ on: filters.collection === failedCollection.id }"
                        :aria-pressed="String(filters.collection === failedCollection.id)"
                        @click="emit('setCollectionFilter', failedCollection.id)">
                    <span class="sb-row-icon" v-html="ICONS.warning"></span>
                    <span class="sb-row-name">Failed to process</span>
                    <span class="sb-num" :class="{ 'sb-num-danger': failedCollection.model_count }">{{ failedCollection.model_count }}</span>
                </button>
            </div>
        </div>
    </aside>
</template>
