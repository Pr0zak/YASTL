<script setup>
/**
 * FacetPicker - a searchable list for choosing values of one facet.
 *
 * With 1,605 tags and 756 categories an inline list is not browsable:
 * expanding Tags once produced up to 70,000px of DOM, and the category tree
 * was hand-unrolled to three levels, so 99 categories could not be reached.
 * A picker searches the whole set regardless of size or depth, and only
 * mounts when asked for. It renders in the shared dialog shell, so on a
 * phone it is a bottom sheet with a "Done" button in thumb reach.
 */
import { computed, ref, watch } from 'vue';
import { ICONS } from '../icons.js';
import AppDialog from './AppDialog.vue';

const props = defineProps({
    open: { type: Boolean, default: false },
    title: { type: String, default: '' },
    /** [{ id, name, count, depth, path }] — depth/path optional. */
    items: { type: Array, default: () => [] },
    /** ids (or names) already applied. */
    selected: { type: Array, default: () => [] },
    /** Whether picking one replaces the selection instead of adding to it. */
    single: { type: Boolean, default: false },
    /** 'and' | 'or' when the facet supports match-all/any (tags); else null. */
    tagMatch: { type: String, default: null },
    /** Live result count for the footer. */
    resultCount: { type: Number, default: 0 },
});

const emit = defineEmits(['close', 'pick', 'clear', 'setTagMatch']);

const query = ref('');

watch(() => props.open, (open) => {
    if (open) query.value = '';
});

const matches = computed(() => {
    const q = query.value.trim().toLowerCase();
    if (!q) return props.items;
    // Match on the full path when one is supplied, so searching "chess" finds a
    // nested category without the user knowing where it lives.
    return props.items.filter((i) =>
        (i.path || i.name || '').toLowerCase().includes(q)
    );
});

// Long lists render in pages; a 1,605-row list otherwise costs a visible
// stall every time the sheet opens on a phone.
const PAGE = 200;
const shown = ref(PAGE);
watch([() => props.open, query], () => { shown.value = PAGE; });
const visible = computed(() => matches.value.slice(0, shown.value));

const selectedSet = computed(() => new Set(props.selected));
</script>

<template>
    <AppDialog :show="open" :title="title" size="sm" full-height-mobile panel-class="facet-dialog" @close="emit('close')">
        <div class="facet-search">
            <span v-html="ICONS.search"></span>
            <input type="search" v-model="query" data-autofocus
                   :placeholder="`Search ${items.length.toLocaleString()} ${title.toLowerCase()}…`"
                   :aria-label="`Search ${title}`">
        </div>

        <div v-if="selected.length" class="facet-selected">
            <span>{{ selected.length }} selected</span>
            <span v-if="tagMatch && selected.length > 1" class="tag-match-toggle" role="group" aria-label="Match">
                <button type="button" class="btn-ghost tag-match-btn" :class="{ active: tagMatch === 'and' }"
                        :aria-pressed="String(tagMatch === 'and')" @click="emit('setTagMatch', 'and')"
                        title="Show models that have every selected tag">All</button>
                <button type="button" class="btn-ghost tag-match-btn" :class="{ active: tagMatch === 'or' }"
                        :aria-pressed="String(tagMatch === 'or')" @click="emit('setTagMatch', 'or')"
                        title="Show models that have any selected tag">Any</button>
            </span>
            <button class="btn btn-sm btn-ghost" @click="emit('clear')">Clear</button>
        </div>

        <div class="facet-list" role="listbox" :aria-multiselectable="String(!single)" :aria-label="title">
            <button v-for="item in visible" :key="item.id ?? item.name"
                    class="facet-item" :class="{ on: selectedSet.has(item.id ?? item.name) }"
                    role="option" :aria-selected="String(selectedSet.has(item.id ?? item.name))"
                    :style="item.depth ? { paddingLeft: (14 + item.depth * 14) + 'px' } : null"
                    @click="emit('pick', item)">
                <span class="facet-check" v-if="!single" aria-hidden="true" v-html="ICONS.check"></span>
                <span class="facet-item-name">{{ item.name }}</span>
                <span v-if="item.path && item.depth" class="facet-item-path">{{ item.path }}</span>
                <span v-if="item.count != null" class="facet-item-count">{{ item.count.toLocaleString() }}</span>
            </button>
            <button v-if="matches.length > shown" class="btn btn-ghost facet-more" @click="shown += PAGE">
                Show more ({{ (matches.length - shown).toLocaleString() }} left)
            </button>
            <div v-if="!matches.length" class="facet-empty">
                Nothing matches “{{ query }}”.
            </div>
        </div>

        <template v-if="!single" #footer>
            <button class="btn btn-primary" @click="emit('close')">
                Show {{ resultCount.toLocaleString() }} result{{ resultCount === 1 ? '' : 's' }}
            </button>
        </template>
    </AppDialog>
</template>
