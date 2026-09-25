<script setup>
/**
 * SelectionBar - a floating action bar shown for the whole of selection
 * mode, not only once something is ticked, so there is always a visible way
 * out. Delete and Auto-tag sit behind "⋯": the old full-width bar put Delete
 * on the right edge of a row that scrolled sideways on a phone, clipped and
 * with no hint it was there.
 */
import { ref, watch, onBeforeUnmount } from 'vue';
import { ICONS } from '../icons.js';

const props = defineProps({
    selectionMode: { type: Boolean, default: false },
    selectedModels: { type: Set, default: () => new Set() },
    total: { type: Number, default: 0 },
});

const emit = defineEmits([
    'selectAll',
    'deselectAll',
    'bulkFavorite',
    'showBulkTagModal',
    'bulkAutoTag',
    'openBulkAddToCollection',
    'bulkDelete',
    'exit',
]);

const moreOpen = ref(false);
const moreEl = ref(null);
function onOutside(e) {
    if (moreEl.value && !moreEl.value.contains(e.target)) moreOpen.value = false;
}
// Escape closes this menu first; without the capture-phase stop it would
// reach the app handler and leave selection mode entirely.
function onEsc(e) {
    if (e.key === 'Escape') { e.stopImmediatePropagation(); moreOpen.value = false; }
}
watch(moreOpen, (open) => {
    const m = open ? 'addEventListener' : 'removeEventListener';
    document[m]('pointerdown', onOutside, true);
    document[m]('keydown', onEsc, true);
});
watch(() => props.selectionMode, (on) => { if (!on) moreOpen.value = false; });
onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', onOutside, true);
    document.removeEventListener('keydown', onEsc, true);
});

function pick(event) {
    moreOpen.value = false;
    emit(event);
}
</script>

<template>
    <Transition name="pill">
        <div v-if="selectionMode" class="selection-pill" role="toolbar" aria-label="Selection">
            <span class="pill-count" aria-live="polite">
                <template v-if="selectedModels.size">{{ selectedModels.size }}<span class="pill-word"> selected</span></template>
                <template v-else><span class="pill-word">Pick models</span><span class="pill-word-short">0</span></template>
            </span>
            <button v-if="selectedModels.size < total" class="pill-link" @click="emit('selectAll')">All</button>
            <button v-if="selectedModels.size" class="pill-link" @click="emit('deselectAll')">None</button>

            <span class="pill-sep" aria-hidden="true"></span>

            <button class="pill-btn" :disabled="!selectedModels.size" @click="emit('bulkFavorite')"
                    title="Favourite" aria-label="Favourite selected">
                <span v-html="ICONS.heart"></span><span class="pill-label">Favourite</span>
            </button>
            <button class="pill-btn" :disabled="!selectedModels.size" @click="emit('showBulkTagModal')"
                    title="Add tags" aria-label="Add tags to selected">
                <span v-html="ICONS.tag"></span><span class="pill-label">Tag</span>
            </button>
            <button class="pill-btn" :disabled="!selectedModels.size" @click="emit('openBulkAddToCollection')"
                    title="Add to collection" aria-label="Add selected to a collection">
                <span v-html="ICONS.collection"></span><span class="pill-label">Collection</span>
            </button>
            <div class="pill-more" ref="moreEl">
                <button class="pill-btn" :disabled="!selectedModels.size" @click="moreOpen = !moreOpen"
                        aria-haspopup="menu" :aria-expanded="String(moreOpen)" title="More" aria-label="More actions">
                    <span v-html="ICONS.dots"></span>
                </button>
                <div v-if="moreOpen" class="pill-menu" role="menu">
                    <button role="menuitem" @click="pick('bulkAutoTag')">
                        <span v-html="ICONS.zap"></span>Auto-tag
                    </button>
                    <button role="menuitem" class="danger" @click="pick('bulkDelete')">
                        <span v-html="ICONS.trash"></span>Delete {{ selectedModels.size }}…
                    </button>
                </div>
            </div>

            <button class="pill-btn pill-exit" @click="emit('exit')" title="Stop selecting (Esc)" aria-label="Stop selecting">
                <span v-html="ICONS.close"></span>
            </button>
        </div>
    </Transition>
</template>
