<script setup>
/**
 * FacetPicker - a searchable overlay for choosing values of one facet.
 *
 * The sidebar used to render every facet inline. With 1,605 tags and 756
 * categories that is not a list anyone can browse: expanding Tags produced up
 * to 70,000px of DOM, and the category tree was hand-unrolled to three levels,
 * so 99 categories could not be reached at all. A picker searches the whole
 * set regardless of size or depth, and only mounts when asked for.
 */
import { computed, ref, watch, nextTick } from 'vue';
import { ICONS } from '../icons.js';

const props = defineProps({
    open: { type: Boolean, default: false },
    title: { type: String, default: '' },
    /** [{ id, name, count, depth, path }] — depth/path optional. */
    items: { type: Array, default: () => [] },
    /** ids (or names) already applied. */
    selected: { type: Array, default: () => [] },
    /** Whether picking one replaces the selection instead of adding to it. */
    single: { type: Boolean, default: false },
});

const emit = defineEmits(['close', 'pick', 'clear']);

const query = ref('');
const inputEl = ref(null);

watch(() => props.open, async (open) => {
    if (!open) return;
    query.value = '';
    await nextTick();
    inputEl.value?.focus();
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

const selectedSet = computed(() => new Set(props.selected));

function onKeydown(e) {
    if (e.key === 'Escape') {
        e.stopPropagation();
        emit('close');
    }
}
</script>

<template>
    <div v-if="open" class="facet-overlay" @click.self="emit('close')" @keydown="onKeydown">
        <div class="facet-panel" role="dialog" :aria-label="title">
            <div class="facet-head">
                <span class="facet-title">{{ title }}</span>
                <button class="close-btn" @click="emit('close')" title="Close">&times;</button>
            </div>

            <div class="facet-search">
                <span v-html="ICONS.search"></span>
                <input ref="inputEl" type="text" v-model="query"
                       :placeholder="`Search ${items.length.toLocaleString()}…`"
                       :aria-label="`Search ${title}`" @keydown="onKeydown">
            </div>

            <div v-if="selected.length" class="facet-selected">
                <span>{{ selected.length }} selected</span>
                <button class="btn btn-sm btn-ghost" @click="emit('clear')">Clear</button>
            </div>

            <div class="facet-list">
                <button v-for="item in matches" :key="item.id ?? item.name"
                        class="facet-item" :class="{ on: selectedSet.has(item.id ?? item.name) }"
                        :style="item.depth ? { paddingLeft: (14 + item.depth * 14) + 'px' } : null"
                        @click="emit('pick', item)">
                    <span class="facet-item-name">{{ item.name }}</span>
                    <span v-if="item.path && item.depth" class="facet-item-path">{{ item.path }}</span>
                    <span v-if="item.count != null" class="facet-item-count">{{ item.count.toLocaleString() }}</span>
                </button>
                <div v-if="!matches.length" class="facet-empty">
                    Nothing matches “{{ query }}”.
                </div>
            </div>
        </div>
    </div>
</template>
