<script setup>
/**
 * SideBar — search-first filter panel.
 *
 * Replaces five always-expanded sections with three bands: what is currently
 * applied, a short list of places to jump to, and a set of facets that open in
 * a searchable picker. The old shape did not survive real data — expanding
 * Tags rendered up to 70,000px of rows, the category tree hid 99 of its 756
 * nodes behind a hardcoded three-level unroll, and 77% of the column was
 * padding from touch-target floors applied at desktop widths.
 *
 * Collections no longer carry a cover thumbnail or a colour dot. That marker
 * looked arbitrary because it was: a collection got a thumbnail only when it
 * still had rows in collection_models and a dot when it did not, so it encoded
 * leftover manual membership rather than anything about the collection.
 */
import { computed, ref } from 'vue';
import { ICONS } from '../icons.js';
import FacetPicker from './FacetPicker.vue';

const dragOverCollection = ref(null);
/** Which facet picker is open: 'format' | 'tags' | 'categories' | 'library' | null */
const picker = ref(null);

const props = defineProps({
    sidebarOpen: { type: Boolean, default: false },
    filters: { type: Object, required: true },
    allTags: { type: Array, default: () => [] },
    allCategories: { type: Array, default: () => [] },
    collections: { type: Array, default: () => [] },
    libraries: { type: Array, default: () => [] },
    favoritesCount: { type: Number, default: 0 },
    savedSearches: { type: Array, default: () => [] },
    editingCollectionId: { default: null },
    editCollectionName: { type: String, default: '' },
    /** Facet pills for what is applied right now, from App.vue. */
    activeFilters: { type: Array, default: () => [] },
    resultCount: { type: Number, default: 0 },
    totalCount: { type: Number, default: 0 },
    /** [{ file_format, count }] from /api/stats — only formats that exist. */
    formatCounts: { type: Array, default: () => [] },
});

const emit = defineEmits([
    'update:sidebarOpen',
    'update:editCollectionName',
    'setLibraryFilter',
    'setFormatFilter',
    'toggleTagFilter',
    'toggleCategoryFilter',
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
    'removeFilter',
    'clearFilters',
    'clearFacet',
]);

function onDropCollection(col) {
    dragOverCollection.value = null;
    emit('dropOnCollection', col.id);
}

/** Flatten the category tree so a search reaches every depth, not just three. */
const flatCategories = computed(() => {
    const out = [];
    const walk = (nodes, depth, trail) => {
        for (const n of nodes) {
            const path = trail ? `${trail} / ${n.name}` : n.name;
            out.push({ id: n.id, name: n.name, count: n.model_count, depth, path });
            if (n.children?.length) walk(n.children, depth + 1, path);
        }
    };
    walk(props.allCategories, 0, '');
    return out;
});

const tagItems = computed(() =>
    // Most-used first: alphabetical put every punctuation-damaged tag on top.
    [...props.allTags]
        .sort((a, b) => (b.model_count || 0) - (a.model_count || 0))
        .map((t) => ({ id: t.name, name: t.name, count: t.model_count }))
);

const formatItems = computed(() =>
    props.formatCounts.map((f) => ({
        id: (f.file_format || '').toLowerCase(),
        name: (f.file_format || '').toUpperCase(),
        count: f.count,
    }))
);

const libraryItems = computed(() =>
    props.libraries.map((l) => ({ id: l.id, name: l.name, count: l.model_count }))
);

const FACETS = [
    { key: 'format', title: 'Format', items: () => formatItems.value, single: true },
    { key: 'tags', title: 'Tags', items: () => tagItems.value },
    { key: 'categories', title: 'Categories', items: () => flatCategories.value },
    { key: 'library', title: 'Library', items: () => libraryItems.value, single: true },
];

const activePicker = computed(() => FACETS.find((f) => f.key === picker.value) || null);

const pickerItems = computed(() => (activePicker.value ? activePicker.value.items() : []));

const pickerSelected = computed(() => {
    switch (picker.value) {
        case 'format': return props.filters.format ? [props.filters.format] : [];
        case 'tags': return props.filters.tags;
        case 'categories': return props.filters.categoryIds || [];
        case 'library': return props.filters.library_id != null ? [props.filters.library_id] : [];
        default: return [];
    }
});

/** Count shown beside each facet row: how many values are applied, else the size. */
function facetSummary(key) {
    switch (key) {
        case 'format': return props.filters.format ? 1 : formatItems.value.length;
        case 'tags': return props.filters.tags.length || tagItems.value.length;
        case 'categories': return (props.filters.categoryIds || []).length || flatCategories.value.length;
        case 'library': return props.filters.library_id != null ? 1 : libraryItems.value.length;
        default: return 0;
    }
}

function facetActive(key) {
    switch (key) {
        case 'format': return !!props.filters.format;
        case 'tags': return props.filters.tags.length > 0;
        case 'categories': return (props.filters.categoryIds || []).length > 0;
        case 'library': return props.filters.library_id != null;
        default: return false;
    }
}

function onPick(item) {
    switch (picker.value) {
        case 'format': emit('setFormatFilter', item.id); picker.value = null; break;
        case 'tags': emit('toggleTagFilter', item.name); break;
        case 'categories': emit('toggleCategoryFilter', item); break;
        case 'library': emit('setLibraryFilter', item.id); picker.value = null; break;
    }
}
</script>

<template>
    <!-- Sidebar backdrop (mobile) -->
    <div v-if="sidebarOpen" class="sidebar-backdrop" @click="emit('update:sidebarOpen', false)"></div>

    <aside class="sidebar" :class="{ collapsed: !sidebarOpen }">

        <!-- What is applied right now. The app never showed this in one place;
             on a phone the filter was invisible once the drawer was closed. -->
        <div class="sidebar-section sb-applied" v-if="activeFilters.length">
            <div class="sb-label">Filtering by</div>
            <div class="sb-pills">
                <button v-for="(f, i) in activeFilters" :key="i" class="sb-pill"
                        @click="emit('removeFilter', f)" :title="`Remove ${f.label}`">
                    {{ f.label }}<span class="sb-pill-x">&times;</span>
                </button>
            </div>
            <div class="sb-count">
                <strong>{{ resultCount.toLocaleString() }}</strong>
                <span v-if="totalCount"> of {{ totalCount.toLocaleString() }}</span> models
                <button class="sb-clear" @click="emit('clearFilters')">Clear all</button>
            </div>
        </div>

        <!-- Jump to -->
        <div class="sidebar-section">
            <div class="sb-label">Jump to</div>
            <button class="sb-row" :class="{ on: !activeFilters.length }" @click="emit('clearFilters')">
                All models<span class="sb-num">{{ totalCount.toLocaleString() }}</span>
            </button>
            <button class="sb-row" :class="{ on: filters.favoritesOnly }" @click="emit('toggleFavoritesFilter')">
                Favorites<span class="sb-num">{{ favoritesCount }}</span>
            </button>
            <button class="sb-row" :class="{ on: filters.duplicatesOnly }" @click="emit('toggleDuplicatesFilter')">
                Duplicates
                <span class="sb-row-action" @click.stop="emit('openDuplicatesReview')">Review</span>
            </button>
        </div>

        <!-- Collections -->
        <div class="sidebar-section">
            <div class="sb-label">
                Collections
                <button class="sb-add" @click="emit('openCollectionModal')" title="New collection">
                    <span v-html="ICONS.plus"></span>
                </button>
            </div>
            <div v-for="col in collections" :key="col.id"
                 class="sb-row" :class="{ on: filters.collection === col.id, 'drop-target': dragOverCollection === col.id }"
                 @click="emit('setCollectionFilter', col.id)"
                 @dragover.prevent="dragOverCollection = col.id"
                 @dragenter.prevent="dragOverCollection = col.id"
                 @dragleave="dragOverCollection === col.id && (dragOverCollection = null)"
                 @drop.prevent="onDropCollection(col)">
                <template v-if="editingCollectionId === col.id">
                    <input class="sidebar-edit-input" :value="editCollectionName"
                           @input="emit('update:editCollectionName', $event.target.value)"
                           @blur="emit('saveCollectionName', col)"
                           @keydown.enter="emit('saveCollectionName', col)"
                           @keydown.escape.stop="emit('cancelEditCollection')"
                           @click.stop
                           @vue:mounted="$event.el.focus()">
                </template>
                <template v-else>
                    <span class="sb-row-name" @dblclick.stop="emit('startEditCollection', col)">{{ col.name }}</span>
                    <span class="sb-num">{{ col.model_count }}</span>
                    <span class="sb-row-tools">
                        <button @click.stop="emit('togglePinCollection', col)"
                                :class="{ on: col.pinned }"
                                :title="col.pinned ? 'Unpin' : 'Pin to top'" v-html="ICONS.bookmark"></button>
                        <button v-if="col.is_smart" @click.stop="emit('editCollection', col)"
                                title="Edit rules" v-html="ICONS.settings"></button>
                        <button @click.stop="emit('deleteCollection', col.id)" title="Delete collection">&times;</button>
                    </span>
                </template>
            </div>
            <div v-if="!collections.length" class="sb-empty">No collections yet.</div>
        </div>

        <!-- Facets: each opens a searchable picker rather than an endless list -->
        <div class="sidebar-section">
            <div class="sb-label">Narrow by</div>
            <button v-for="f in FACETS" :key="f.key"
                    class="sb-row" :class="{ on: facetActive(f.key) }"
                    @click="picker = f.key">
                {{ f.title }}
                <span class="sb-num">{{ facetSummary(f.key).toLocaleString() }}</span>
                <span class="sb-chev" v-html="ICONS.chevron"></span>
            </button>
        </div>

        <!-- Saved searches -->
        <div class="sidebar-section" v-if="savedSearches.length">
            <div class="sb-label">Saved searches</div>
            <div v-for="search in savedSearches" :key="search.id"
                 class="sb-row" @click="emit('applySavedSearch', search)">
                <span class="sb-row-name">{{ search.name }}</span>
                <span class="sb-row-tools">
                    <button @click.stop="emit('deleteSavedSearch', search.id)" title="Delete saved search">&times;</button>
                </span>
            </div>
        </div>

        <FacetPicker :open="!!activePicker"
                     :title="activePicker ? activePicker.title : ''"
                     :items="pickerItems"
                     :selected="pickerSelected"
                     :single="activePicker ? !!activePicker.single : false"
                     @close="picker = null"
                     @pick="onPick"
                     @clear="emit('clearFacet', picker)" />
    </aside>
</template>
