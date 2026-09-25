<script setup>
/**
 * FilterBar - the strip under the navbar: filter chips on the left, the
 * result count, sort and view on the right.
 *
 * Filters used to live in two places at once — crumbs in a breadcrumb bar
 * and pills in the sidebar — and the facets themselves were sidebar rows,
 * so on a phone narrowing the grid meant opening a drawer. Each facet is
 * now a chip over the grid that opens a picker (a sheet on a phone), and
 * its current value is shown on the chip itself.
 */
import { computed, ref, watch, onBeforeUnmount } from 'vue';
import { ICONS } from '../icons.js';
import FacetPicker from './FacetPicker.vue';

const props = defineProps({
    filters: { type: Object, required: true },
    /** Applied filters as crumbs: [{ type, label, ... }] */
    activeFilters: { type: Array, default: () => [] },
    hasActiveFilters: { type: Boolean, default: false },
    allTags: { type: Array, default: () => [] },
    allCategories: { type: Array, default: () => [] },
    libraries: { type: Array, default: () => [] },
    collections: { type: Array, default: () => [] },
    formatCounts: { type: Array, default: () => [] },
    total: { type: Number, default: 0 },
    totalFiles: { type: Number, default: 0 },
    loading: { type: Boolean, default: false },
    viewMode: { type: String, default: 'grid' },
    gridDensity: { type: String, default: 'comfortable' },
    searchQuery: { type: String, default: '' },
    aiEnabled: { type: Boolean, default: false },
    searchMode: { type: String, default: 'keyword' },
});

const emit = defineEmits([
    'setFormatFilter',
    'toggleTagFilter',
    'setTagMatch',
    'toggleCategoryFilter',
    'setLibraryFilter',
    'toggleFavoritesFilter',
    'removeFilter',
    'clearFilters',
    'clearFacet',
    'setSortBy',
    'toggleSortOrder',
    'update:viewMode',
    'toggleGridDensity',
    'toggleSearchMode',
    'saveSearch',
    'saveAsCollection',
]);

const SORTS = [
    { value: 'updated_at', label: 'Date modified' },
    { value: 'created_at', label: 'Date added' },
    { value: 'name', label: 'Name' },
    { value: 'file_size', label: 'File size' },
    { value: 'vertex_count', label: 'Vertices' },
    { value: 'face_count', label: 'Faces' },
];

const DENSITY_LABEL = { comfortable: 'Comfortable', compact: 'Compact', minimal: 'Pictures only' };

/* ---- Facets ---- */
const picker = ref(null);

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
    { key: 'categories', title: 'Category', items: () => flatCategories.value },
    { key: 'library', title: 'Library', items: () => libraryItems.value, single: true },
];
const visibleFacets = computed(() =>
    // A one-library install has nothing to choose between.
    FACETS.filter((f) => f.key !== 'library' || props.libraries.length > 1)
);

const activePicker = computed(() => FACETS.find((f) => f.key === picker.value) || null);
const pickerItems = computed(() => (activePicker.value ? activePicker.value.items() : []));
const pickerSelected = computed(() => selectedFor(picker.value));

function selectedFor(key) {
    switch (key) {
        case 'format': return props.filters.format ? [props.filters.format] : [];
        case 'tags': return props.filters.tags;
        case 'categories': return props.filters.categoryIds || [];
        case 'library': return props.filters.library_id != null ? [props.filters.library_id] : [];
        default: return [];
    }
}

/** Chip text: the facet name, or its value once one is applied. */
function chipLabel(f) {
    const sel = selectedFor(f.key);
    if (!sel.length) return f.title;
    let first;
    if (f.key === 'format') first = String(sel[0]).toUpperCase();
    else if (f.key === 'tags') first = sel[0];
    else if (f.key === 'categories') first = flatCategories.value.find((c) => c.id === sel[0])?.name || 'Category';
    else if (f.key === 'library') first = libraryItems.value.find((l) => l.id === sel[0])?.name || 'Library';
    return sel.length > 1 ? `${first} +${sel.length - 1}` : first;
}

function onPick(item) {
    switch (picker.value) {
        case 'format': emit('setFormatFilter', item.id); picker.value = null; break;
        case 'tags': emit('toggleTagFilter', item.name); break;
        case 'categories': emit('toggleCategoryFilter', item); break;
        case 'library': emit('setLibraryFilter', item.id); picker.value = null; break;
    }
}

/* Crumbs that are not one of the four facet chips: collection, zip,
   duplicates and legacy name-based categories. Favourites has its own chip. */
const FACET_TYPES = new Set(['format', 'tag', 'categoryId', 'library', 'favorites']);
const contextChips = computed(() => props.activeFilters.filter((c) => !FACET_TYPES.has(c.type)));

function contextColor(crumb) {
    if (crumb.type !== 'collection') return null;
    return props.collections.find((c) => c.id === props.filters.collection)?.color || null;
}

/* ---- Count ---- */
const countText = computed(() => {
    const n = props.total.toLocaleString();
    if (props.totalFiles && props.totalFiles !== props.total) {
        return `${n} items · ${props.totalFiles.toLocaleString()} files`;
    }
    return `${n} model${props.total === 1 ? '' : 's'}`;
});
const countTitle = computed(() =>
    props.totalFiles && props.totalFiles !== props.total
        ? 'Zip archives with several models show as one card, so there are fewer cards than files.'
        : ''
);

/* ---- Phone "sort & view" menu ---- */
const viewMenuOpen = ref(false);
const viewMenuEl = ref(null);
function onOutside(e) {
    if (viewMenuEl.value && !viewMenuEl.value.contains(e.target)) viewMenuOpen.value = false;
}
function onEsc(e) {
    if (e.key === 'Escape') { e.stopPropagation(); viewMenuOpen.value = false; }
}
watch(viewMenuOpen, (open) => {
    const m = open ? 'addEventListener' : 'removeEventListener';
    document[m]('pointerdown', onOutside, true);
    document[m]('keydown', onEsc, true);
});
onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', onOutside, true);
    document.removeEventListener('keydown', onEsc, true);
});

const sortDirLabel = computed(() => (props.filters.sortOrder === 'asc' ? 'ascending' : 'descending'));
</script>

<template>
    <div class="filter-bar" role="toolbar" aria-label="Filters and view">
        <div class="filter-chips">
            <button v-for="f in visibleFacets" :key="f.key" type="button"
                    class="fchip" :class="{ on: selectedFor(f.key).length }"
                    aria-haspopup="dialog"
                    @click="picker = f.key">
                <span class="fchip-text">{{ chipLabel(f) }}</span>
                <span class="fchip-caret" v-html="ICONS.arrowDown"></span>
            </button>
            <button type="button" class="fchip" :class="{ on: filters.favoritesOnly }"
                    :aria-pressed="String(filters.favoritesOnly)"
                    @click="emit('toggleFavoritesFilter')">
                <span class="fchip-icon" v-html="filters.favoritesOnly ? ICONS.heartFilled : ICONS.heart"></span>
                <span class="fchip-text">Favourites</span>
            </button>

            <span v-for="(c, i) in contextChips" :key="c.type + i" class="fchip on fchip-context">
                <span v-if="contextColor(c)" class="sb-dot" :style="{ background: contextColor(c) }"></span>
                <span v-else-if="c.type === 'zip'" class="fchip-icon" v-html="ICONS.folder"></span>
                <span class="fchip-text">{{ c.label }}</span>
                <button type="button" class="fchip-x" :aria-label="'Remove ' + c.label" :title="'Remove ' + c.label"
                        @click="emit('removeFilter', c)" v-html="ICONS.close"></button>
            </span>

            <button v-if="aiEnabled && searchQuery.trim()" type="button" class="fchip"
                    :class="{ on: searchMode === 'semantic' }" :aria-pressed="String(searchMode === 'semantic')"
                    :title="searchMode === 'semantic' ? 'Semantic (AI) search is on' : 'Search by meaning with AI'"
                    @click="emit('toggleSearchMode')">
                <span class="fchip-icon" v-html="ICONS.zap"></span><span class="fchip-text">Semantic</span>
            </button>

            <template v-if="hasActiveFilters || searchQuery.trim()">
                <button type="button" class="fchip-link" @click="emit('saveSearch')">Save search</button>
                <button v-if="hasActiveFilters" type="button" class="fchip-link" @click="emit('saveAsCollection')">Save as collection</button>
                <button v-if="hasActiveFilters" type="button" class="fchip-link" @click="emit('clearFilters')">Clear all</button>
            </template>
        </div>

        <div class="filter-view">
            <span class="filter-count" :title="countTitle" aria-live="polite">
                <template v-if="loading && !total">Loading…</template>
                <template v-else>{{ countText }}</template>
            </span>

            <!-- Wide screens: inline sort + view controls -->
            <div class="filter-view-inline">
                <select class="sort-select" :value="filters.sortBy" aria-label="Sort by"
                        @change="emit('setSortBy', $event.target.value)">
                    <option v-for="s in SORTS" :key="s.value" :value="s.value">{{ s.label }}</option>
                </select>
                <button class="btn-icon sort-dir-btn" @click="emit('toggleSortOrder')"
                        :title="'Sorted ' + sortDirLabel + ', click to reverse'"
                        :aria-label="'Sorted ' + sortDirLabel + ', reverse order'"
                        v-html="filters.sortOrder === 'asc' ? ICONS.sortAsc : ICONS.sortDesc"></button>
                <div class="view-toggle" role="group" aria-label="View">
                    <button class="btn-ghost" :class="{ active: viewMode === 'grid' }" :aria-pressed="String(viewMode === 'grid')"
                            @click="emit('update:viewMode', 'grid')" title="Grid" aria-label="Grid view" v-html="ICONS.grid"></button>
                    <button class="btn-ghost" :class="{ active: viewMode === 'list' }" :aria-pressed="String(viewMode === 'list')"
                            @click="emit('update:viewMode', 'list')" title="List" aria-label="List view" v-html="ICONS.list"></button>
                    <button v-if="viewMode === 'grid'" class="btn-ghost"
                            @click="emit('toggleGridDensity')"
                            :title="'Tile size: ' + DENSITY_LABEL[gridDensity] + ' (click to change)'"
                            :aria-label="'Tile size: ' + DENSITY_LABEL[gridDensity] + ', change'"
                            v-html="ICONS.density"></button>
                </div>
            </div>

            <!-- Phones: one button for sort + view -->
            <div class="filter-view-menu" ref="viewMenuEl">
                <button class="btn-icon" :class="{ active: viewMenuOpen }" @click="viewMenuOpen = !viewMenuOpen"
                        aria-haspopup="true" :aria-expanded="String(viewMenuOpen)" title="Sort and view" aria-label="Sort and view"
                        v-html="ICONS.filter"></button>
                <div v-if="viewMenuOpen" class="view-menu-panel">
                    <label class="form-label" for="phone-sort">Sort by</label>
                    <div class="view-menu-row">
                        <select id="phone-sort" class="form-input" :value="filters.sortBy"
                                @change="emit('setSortBy', $event.target.value)">
                            <option v-for="s in SORTS" :key="s.value" :value="s.value">{{ s.label }}</option>
                        </select>
                        <button class="btn btn-secondary" @click="emit('toggleSortOrder')"
                                :aria-label="'Sorted ' + sortDirLabel + ', reverse order'">
                            <span v-html="filters.sortOrder === 'asc' ? ICONS.sortAsc : ICONS.sortDesc"></span>
                            {{ filters.sortOrder === 'asc' ? 'Asc' : 'Desc' }}
                        </button>
                    </div>
                    <span class="form-label">View</span>
                    <div class="view-menu-seg" role="group" aria-label="View">
                        <button :class="{ on: viewMode === 'grid' }" :aria-pressed="String(viewMode === 'grid')" @click="emit('update:viewMode', 'grid')">
                            <span v-html="ICONS.grid"></span> Grid</button>
                        <button :class="{ on: viewMode === 'list' }" :aria-pressed="String(viewMode === 'list')" @click="emit('update:viewMode', 'list')">
                            <span v-html="ICONS.list"></span> List</button>
                    </div>
                    <button v-if="viewMode === 'grid'" class="btn btn-secondary view-menu-density" @click="emit('toggleGridDensity')">
                        <span v-html="ICONS.density"></span> Tiles: {{ DENSITY_LABEL[gridDensity] }}
                    </button>
                    <p class="view-menu-count">{{ countText }}</p>
                </div>
            </div>
        </div>

        <FacetPicker :open="!!activePicker"
                     :title="activePicker ? activePicker.title : ''"
                     :items="pickerItems"
                     :selected="pickerSelected"
                     :single="activePicker ? !!activePicker.single : false"
                     :tagMatch="picker === 'tags' ? filters.tagMatch : null"
                     :resultCount="total"
                     @setTagMatch="emit('setTagMatch', $event)"
                     @close="picker = null"
                     @pick="onPick"
                     @clear="emit('clearFacet', picker)" />
    </div>
</template>
