<script setup>
/**
 * QueueModal - Print queue (print pipeline).
 * Ordered list of queued/printing/done items; advance status, reorder, remove.
 * Marking an item "done" logs a print + bumps the model's print count (server).
 */
import { computed } from 'vue';
import { ICONS } from '../icons.js';

const props = defineProps({
    showQueue: { type: Boolean, default: false },
    queue: { type: Array, default: () => [] },
});
const emit = defineEmits(['close', 'updateItem', 'removeItem', 'reorder', 'openModel']);

const counts = computed(() => {
    const c = { queued: 0, printing: 0, done: 0, failed: 0 };
    for (const it of props.queue) c[it.status] = (c[it.status] || 0) + 1;
    return c;
});

function thumb(item) {
    return item.model_thumbnail ? `/api/models/${item.model_id}/thumbnail` : '';
}

function move(item, dir) {
    const ids = props.queue.map((q) => q.id);
    const i = ids.indexOf(item.id);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    emit('reorder', ids);
}
</script>

<template>
    <div v-if="showQueue" class="detail-overlay" @click.self="emit('close')">
        <div class="settings-panel queue-panel">
            <div class="detail-header">
                <div class="detail-title">
                    <span v-html="ICONS.queue"></span>
                    Print Queue
                    <span class="queue-counts">
                        {{ counts.queued }} queued · {{ counts.printing }} printing · {{ counts.done }} done
                    </span>
                </div>
                <button class="close-btn" @click="emit('close')" title="Close">&times;</button>
            </div>

            <div class="settings-content">
                <div v-if="queue.length === 0" class="filament-empty">
                    Queue is empty. Add models from a card or the detail panel.
                </div>
                <div v-else class="queue-list">
                    <div v-for="(item, idx) in queue" :key="item.id"
                         class="queue-row" :class="'q-' + item.status">
                        <img v-if="thumb(item)" :src="thumb(item)" class="queue-thumb"
                             alt="" @click="emit('openModel', item.model_id)">
                        <div v-else class="queue-thumb queue-thumb-empty"></div>
                        <div class="queue-info">
                            <div class="queue-name" @click="emit('openModel', item.model_id)"
                                 :title="item.model_name">{{ item.model_name }}</div>
                            <div class="queue-sub">
                                <span class="queue-status-pill" :class="'q-' + item.status">{{ item.status }}</span>
                                <span v-if="item.printer"> · {{ item.printer }}</span>
                                <span v-if="item.notes"> · {{ item.notes }}</span>
                            </div>
                        </div>
                        <select class="form-input queue-status-select" :value="item.status"
                                @change="emit('updateItem', { id: item.id, payload: { status: $event.target.value } })">
                            <option value="queued">Queued</option>
                            <option value="printing">Printing</option>
                            <option value="done">Done</option>
                            <option value="failed">Failed</option>
                        </select>
                        <div class="queue-reorder">
                            <button class="btn-icon" :disabled="idx === 0" @click="move(item, -1)" title="Move up">&#8593;</button>
                            <button class="btn-icon" :disabled="idx === queue.length - 1" @click="move(item, 1)" title="Move down">&#8595;</button>
                        </div>
                        <button class="btn-icon queue-remove" @click="emit('removeItem', item.id)" title="Remove">&times;</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
