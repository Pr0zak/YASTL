<script setup>
/**
 * QueueModal - Print queue (print pipeline).
 * Ordered list of queued/printing/done items; advance status, reorder, remove.
 * Marking an item "done" logs a print + bumps the model's print count (server).
 */
import { computed, ref } from 'vue';
import { ICONS } from '../icons.js';
import AppDialog from './AppDialog.vue';

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

// Drag a row by its handle to reorder (mouse). The up/down buttons stay for
// keyboard and touch, where HTML drag-and-drop is not available.
const dragId = ref(null);
const overId = ref(null);
function onDragStart(item, e) {
    dragId.value = item.id;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(item.id));
}
function onDragOver(item, e) {
    if (dragId.value == null) return;
    e.preventDefault();
    overId.value = item.id;
}
function onDrop(item) {
    const from = dragId.value;
    dragId.value = null;
    overId.value = null;
    if (from == null || from === item.id) return;
    const ids = props.queue.map((q) => q.id).filter((id) => id !== from);
    ids.splice(ids.indexOf(item.id), 0, from);
    emit('reorder', ids);
}
function onDragEnd() {
    dragId.value = null;
    overId.value = null;
}
</script>

<template>
    <AppDialog :show="showQueue" title="Print queue" size="md"
               :subtitle="queue.length ? `${counts.queued} queued · ${counts.printing} printing · ${counts.done} done` : ''"
               @close="emit('close')">
        <div v-if="queue.length === 0" class="dialog-empty">
            <div class="dialog-empty-icon" v-html="ICONS.queue"></div>
            <div class="dialog-empty-title">Nothing queued</div>
            <p class="dialog-empty-text">
                Open a model and choose <strong>Queue</strong> to line it up for printing.
                Marking an item done logs the print on that model.
            </p>
        </div>
        <ol v-else class="queue-list">
            <li v-for="(item, idx) in queue" :key="item.id"
                class="queue-row" :class="['q-' + item.status, { 'is-dragging': dragId === item.id, 'is-over': overId === item.id && dragId !== item.id }]"
                @dragover="onDragOver(item, $event)" @drop.prevent="onDrop(item)">
                <span class="queue-grip" draggable="true" title="Drag to reorder" aria-hidden="true"
                      @dragstart="onDragStart(item, $event)" @dragend="onDragEnd" v-html="ICONS.grip"></span>
                <button type="button" class="queue-open" @click="emit('openModel', item.model_id)"
                        :aria-label="'Open ' + item.model_name">
                    <img v-if="thumb(item)" :src="thumb(item)" class="queue-thumb" alt="">
                    <span v-else class="queue-thumb queue-thumb-empty"></span>
                    <span class="queue-info">
                        <span class="queue-name">{{ item.model_name }}</span>
                        <span class="queue-sub">
                            <span v-if="item.printer">{{ item.printer }}</span>
                            <span v-if="item.notes"> · {{ item.notes }}</span>
                        </span>
                    </span>
                </button>
                <select class="form-input queue-status-select" :class="'q-' + item.status" :value="item.status"
                        :aria-label="'Status of ' + item.model_name"
                        @change="emit('updateItem', { id: item.id, payload: { status: $event.target.value } })">
                    <option value="queued">Queued</option>
                    <option value="printing">Printing</option>
                    <option value="done">Done</option>
                    <option value="failed">Failed</option>
                </select>
                <div class="queue-row-actions">
                    <button class="btn-icon" :disabled="idx === 0" @click="move(item, -1)"
                            title="Move up" aria-label="Move up" v-html="ICONS.arrowUp"></button>
                    <button class="btn-icon" :disabled="idx === queue.length - 1" @click="move(item, 1)"
                            title="Move down" aria-label="Move down" v-html="ICONS.arrowDown"></button>
                    <button class="btn-icon btn-icon-danger" @click="emit('removeItem', item.id)"
                            title="Remove from queue" aria-label="Remove from queue" v-html="ICONS.close"></button>
                </div>
            </li>
        </ol>
    </AppDialog>
</template>

<style scoped>
.queue-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.queue-row {
    display: flex; align-items: center; gap: 8px; padding: 8px 8px 8px 4px;
    border: 1px solid var(--border); border-left: 3px solid var(--border);
    border-radius: var(--radius); background: var(--bg-card);
}
.queue-row.q-printing { border-left-color: var(--amber); }
.queue-row.q-done { border-left-color: var(--accent); opacity: 0.75; }
.queue-row.q-failed { border-left-color: var(--danger); opacity: 0.75; }
.queue-row.is-dragging { opacity: 0.4; }
.queue-row.is-over { box-shadow: 0 -2px 0 var(--accent-hover); }
.queue-grip { color: var(--text-muted); cursor: grab; display: flex; padding: 8px 2px; flex: none; }
.queue-open {
    flex: 1; min-width: 0; display: flex; align-items: center; gap: 10px;
    background: none; text-align: left; color: inherit; padding: 0; border-radius: var(--radius-sm);
}
.queue-thumb { width: 44px; height: 44px; border-radius: var(--radius-sm); object-fit: contain; background: var(--bg-input); flex: none; }
.queue-info { display: flex; flex-direction: column; min-width: 0; }
.queue-name {
    font-size: 0.9rem; font-weight: 600; color: var(--text-primary);
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere;
}
.queue-open:hover .queue-name { color: var(--accent-hover); }
.queue-sub { font-size: 0.75rem; color: var(--text-muted); }
.queue-sub:empty { display: none; }
.queue-status-select { width: auto; flex: none; font-size: 0.8rem; min-height: 36px; padding: 4px 8px; }
.queue-status-select.q-printing { color: var(--amber); }
.queue-status-select.q-done { color: var(--accent-hover); }
.queue-status-select.q-failed { color: var(--danger); }
.queue-row-actions { display: flex; flex: none; }
.queue-row-actions .btn-icon { width: 36px; height: 36px; }
@media (max-width: 560px) {
    .queue-row { flex-wrap: wrap; }
    .queue-open { flex-basis: calc(100% - 40px); }
    .queue-grip { display: none; }
    .queue-status-select { flex: 1; }
    .queue-row-actions .btn-icon { width: 40px; height: 40px; }
}
</style>
