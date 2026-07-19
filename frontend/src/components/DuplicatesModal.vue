<script setup>
/**
 * DuplicatesModal - Review duplicate models (same xxh128 hash) and keep one.
 *
 * Each group shows all copies; "Keep this" deletes the others in the group.
 * Built on GET /api/models/duplicates (paginated) + bulk delete.
 */
import { ref, watch } from 'vue';
import { apiFindDuplicates, apiFindNearDuplicates, apiBulkDelete } from '../api.js';
import { formatFileSize, formatNumber } from '../search.js';

const props = defineProps({
    show: { type: Boolean, default: false },
    // Parent-owned confirm dialog: (opts) => Promise<boolean>
    confirmFn: { type: Function, required: true },
});
const emit = defineEmits(['close', 'changed']);

const mode = ref('exact'); // 'exact' | 'near'
const groups = ref([]);
const totalGroups = ref(0);
const loading = ref(false);
const offset = ref(0);
const limit = 25;
const busyKey = ref(null);

function groupKey(group) {
    return group.file_hash || `${group.vertex_count}-${group.face_count}`;
}

async function load() {
    loading.value = true;
    try {
        if (mode.value === 'near') {
            const data = await apiFindNearDuplicates(limit, offset.value);
            groups.value = data.near_duplicate_groups || [];
            totalGroups.value = data.total_groups || 0;
        } else {
            const data = await apiFindDuplicates(limit, offset.value);
            groups.value = data.duplicate_groups || [];
            totalGroups.value = data.total_groups || 0;
        }
    } catch {
        groups.value = [];
    } finally {
        loading.value = false;
    }
}

function setMode(m) {
    if (mode.value === m) return;
    mode.value = m;
    offset.value = 0;
    load();
}

watch(() => props.show, (v) => {
    if (v) {
        mode.value = 'exact';
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
    const noun = group.file_hash ? 'cop' : 'variant';
    const plural = toDelete.length === 1 ? (group.file_hash ? 'y' : '') : (group.file_hash ? 'ies' : 's');
    const confirmed = await props.confirmFn({
        title: group.file_hash ? 'Delete duplicates' : 'Delete near-duplicates',
        message: `Delete ${toDelete.length} ${noun}${plural}, keeping "${keepName}"?`
            + (group.file_hash ? '' : ' (these have identical geometry but different files.)'),
        action: 'Delete',
        danger: true,
    });
    if (!confirmed) return;
    busyKey.value = groupKey(group);
    try {
        await apiBulkDelete(toDelete);
        emit('changed');
        await load();
    } finally {
        busyKey.value = null;
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

            <div class="dup-mode-toggle">
                <button class="tag-match-btn" :class="{ active: mode === 'exact' }" @click="setMode('exact')">Exact</button>
                <button class="tag-match-btn" :class="{ active: mode === 'near' }" @click="setMode('near')">Near-duplicate</button>
            </div>

            <div class="dup-body">
                <p v-if="!loading && !groups.length" class="dup-empty">
                    <template v-if="mode === 'near'">No near-duplicates found (no two models share identical geometry with different file content).</template>
                    <template v-else>No duplicate files found. Every model has a unique hash.</template>
                </p>

                <p v-if="totalGroups" class="dup-count">
                    {{ totalGroups }} group{{ totalGroups === 1 ? '' : 's' }} —
                    <template v-if="mode === 'near'">same geometry (vertex/face count), different file content.</template>
                    <template v-else>files with identical content.</template>
                </p>

                <div v-for="group in groups" :key="groupKey(group)" class="dup-group">
                    <div class="dup-group-head">
                        <code v-if="group.file_hash" class="dup-hash">{{ group.file_hash.slice(0, 12) }}</code>
                        <code v-else class="dup-hash">{{ formatNumber(group.vertex_count) }} verts · {{ formatNumber(group.face_count) }} faces</code>
                        <span class="dup-badge">{{ group.count }} {{ mode === 'near' ? 'variants' : 'copies' }}</span>
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
                                :disabled="busyKey === groupKey(group)"
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
.dup-mode-toggle { display: flex; gap: 6px; padding: 4px 2px 10px; }
</style>
