<script setup>
/**
 * DuplicatesModal - Review duplicate models (same xxh128 hash) and keep one.
 *
 * Each group shows all copies; "Keep this" deletes the others in the group.
 * Built on GET /api/models/duplicates (paginated) + bulk delete.
 */
import { ref, watch } from 'vue';
import { apiFindDuplicates, apiBulkDelete } from '../api.js';
import { formatFileSize } from '../search.js';

const props = defineProps({
    show: { type: Boolean, default: false },
    // Parent-owned confirm dialog: (opts) => Promise<boolean>
    confirmFn: { type: Function, required: true },
});
const emit = defineEmits(['close', 'changed']);

const groups = ref([]);
const totalGroups = ref(0);
const loading = ref(false);
const offset = ref(0);
const limit = 25;
const busyHash = ref(null);

async function load() {
    loading.value = true;
    try {
        const data = await apiFindDuplicates(limit, offset.value);
        groups.value = data.duplicate_groups || [];
        totalGroups.value = data.total_groups || 0;
    } catch {
        groups.value = [];
    } finally {
        loading.value = false;
    }
}

watch(() => props.show, (v) => {
    if (v) {
        offset.value = 0;
        load();
    }
});

function thumbUrl(model) {
    if (model.thumbnail_path) return `/thumbnails/${model.thumbnail_path}`;
    return `/api/models/${model.id}/thumbnail`;
}

async function keepOne(group, keepId) {
    const toDelete = group.models.filter((m) => m.id !== keepId).map((m) => m.id);
    if (!toDelete.length) return;
    const keepName = group.models.find((m) => m.id === keepId)?.name;
    const confirmed = await props.confirmFn({
        title: 'Delete duplicates',
        message: `Delete ${toDelete.length} duplicate cop${toDelete.length === 1 ? 'y' : 'ies'}, keeping "${keepName}"?`,
        action: 'Delete copies',
        danger: true,
    });
    if (!confirmed) return;
    busyHash.value = group.file_hash;
    try {
        await apiBulkDelete(toDelete);
        emit('changed');
        await load();
    } finally {
        busyHash.value = null;
    }
}

function nextPage() {
    if (offset.value + limit < totalGroups.value) {
        offset.value += limit;
        load();
    }
}
function prevPage() {
    if (offset.value > 0) {
        offset.value = Math.max(0, offset.value - limit);
        load();
    }
}
</script>

<template>
    <div v-if="show" class="modal-overlay" @click.self="emit('close')">
        <div class="modal-content dup-modal">
            <div class="modal-header">
                <h2>Duplicate Review</h2>
                <button class="btn-icon" @click="emit('close')" aria-label="Close">✕</button>
            </div>

            <div class="dup-body">
                <p v-if="!loading && !groups.length" class="dup-empty">
                    No duplicate files found. Every model has a unique hash.
                </p>

                <p v-if="totalGroups" class="dup-count">
                    {{ totalGroups }} duplicate group{{ totalGroups === 1 ? '' : 's' }}
                    (each is a set of files with identical content)
                </p>

                <div v-for="group in groups" :key="group.file_hash" class="dup-group">
                    <div class="dup-group-head">
                        <code class="dup-hash">{{ group.file_hash.slice(0, 12) }}</code>
                        <span class="dup-badge">{{ group.count }} copies</span>
                    </div>
                    <div class="dup-copies">
                        <div v-for="model in group.models" :key="model.id" class="dup-copy">
                            <img
                                :src="thumbUrl(model)"
                                class="dup-thumb"
                                alt=""
                                @error="(e) => (e.target.style.visibility = 'hidden')"
                            >
                            <div class="dup-info">
                                <div class="dup-name" :title="model.file_path">{{ model.name }}</div>
                                <div class="dup-meta">
                                    {{ model.file_format }} · {{ formatFileSize(model.file_size) }}
                                </div>
                                <div class="dup-path" :title="model.file_path">{{ model.file_path }}</div>
                            </div>
                            <button
                                class="btn btn-sm btn-primary"
                                :disabled="busyHash === group.file_hash"
                                @click="keepOne(group, model.id)"
                            >
                                Keep this
                            </button>
                        </div>
                    </div>
                </div>

                <div v-if="totalGroups > limit" class="dup-pager">
                    <button class="btn btn-sm" :disabled="offset === 0" @click="prevPage">Prev</button>
                    <span>{{ offset + 1 }}–{{ Math.min(offset + limit, totalGroups) }} of {{ totalGroups }}</span>
                    <button class="btn btn-sm" :disabled="offset + limit >= totalGroups" @click="nextPage">Next</button>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.dup-modal { max-width: 760px; width: 92%; max-height: 86vh; display: flex; flex-direction: column; }
.dup-body { overflow-y: auto; padding: 4px 2px; }
.dup-empty { color: var(--text-muted); text-align: center; padding: 40px 0; }
.dup-count { color: var(--text-muted); font-size: 0.85rem; margin: 0 0 12px; }
.dup-group { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
.dup-group-head { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: var(--bg-elevated, rgba(255,255,255,0.03)); }
.dup-hash { font-family: ui-monospace, monospace; font-size: 0.78rem; color: var(--accent, #61afef); }
.dup-badge { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 2px 8px; border-radius: 999px; background: rgba(220,53,69,0.15); color: #dc3545; }
.dup-copies { display: flex; flex-direction: column; }
.dup-copy { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-top: 1px solid var(--border); }
.dup-thumb { width: 48px; height: 48px; object-fit: contain; border-radius: 6px; background: rgba(0,0,0,0.15); flex: none; }
.dup-info { flex: 1; min-width: 0; }
.dup-name { font-weight: 600; font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dup-meta { font-size: 0.78rem; color: var(--text-muted); }
.dup-path { font-size: 0.72rem; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; opacity: 0.7; }
.dup-pager { display: flex; align-items: center; justify-content: center; gap: 14px; padding: 12px 0 4px; font-size: 0.82rem; color: var(--text-muted); }
</style>
