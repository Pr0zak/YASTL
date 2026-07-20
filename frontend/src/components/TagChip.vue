<script setup>
/**
 * TagChip - renders a single tag, coloring the `namespace:` prefix when the tag
 * uses the namespace convention (e.g. franchise:starwars). Plain tags render
 * unchanged. Emits `click` when clickable.
 */
import { computed } from 'vue';
import { parseTag, tagColorStyle } from '../tags.js';

const props = defineProps({
    name: { type: String, required: true },
    clickable: { type: Boolean, default: false },
});

defineEmits(['click']);

const parts = computed(() => parseTag(props.name));
const style = computed(() => tagColorStyle(props.name));
</script>

<template>
    <span class="tag-chip" :class="{ 'tag-chip-clickable': clickable, 'tag-chip-ns': parts.namespace }"
          :style="style" @click="clickable && $emit('click')">
        <span v-if="parts.namespace" class="tag-chip-ns-label">{{ parts.namespace }}</span>{{ parts.value }}
    </span>
</template>
