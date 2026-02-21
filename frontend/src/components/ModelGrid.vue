<script setup>
/**
 * ModelGrid - Grid and list views of model cards.
 */
import { ICONS } from '../icons.js';
import { formatFileSize, formatDate, formatNumber } from '../search.js';

const props = defineProps({
    models: { type: Array, default: () => [] },
    viewMode: { type: String, default: 'grid' },
    selectionMode: { type: Boolean, default: false },
    selectedModels: { type: Set, default: () => new Set() },
    thumbnailMode: { type: String, default: 'wireframe' },
});

const emit = defineEmits([
    'viewModel',
    'toggleSelect',
    'toggleFavorite',
]);

function thumbUrl(model) {
    if (model.thumbnail_path) {
        return `/thumbnails/${model.thumbnail_path}`;
    }
    return `/api/models/${model.id}/thumbnail`;
}

function onThumbError(e) {
    e.target.style.display = 'none';
    const fallback = e.target.parentElement?.querySelector('.no-thumbnail');
    if (fallback) fallback.style.display = 'flex';
}

function formatClass(fmt) {
    if (!fmt) return '';
    const f = fmt.toLowerCase().replace('.', '');
    if (f === '3mf') return '_3mf';
    return f;
}

function zipName(model) {
    if (!model.zip_path) return '';
    const parts = model.zip_path.replace(/\\/g, '/').split('/');
    const filename = parts[parts.length - 1] || '';
    return filename.replace(/\.zip$/i, '');
}

function isSelected(modelId) {
    return props.selectedModels.has(modelId);
}
</script>

<template>
    <!-- Grid View -->
    <div v-if="viewMode === 'grid'" class="models-grid">
        <div v-for="model in models" :key="model.id"
             class="model-card" :class="{ selected: selectionMode && isSelected(model.id) }" @click="emit('viewModel', model)">
            <!-- Thumbnail -->
            <div class="card-thumbnail">
                <img :src="thumbUrl(model)"
                     :alt="model.name"
                     @error="onThumbError"
                     loading="lazy">
                <div class="no-thumbnail" style="display:none">
                    <span v-html="ICONS.cube"></span>
                    <span>{{ model.file_format }}</span>
                </div>
                <span class="card-format">
                    <span class="format-badge" :class="formatClass(model.file_format)">
                        {{ model.file_format }}
                    </span>
                </span>
                <button v-if="!selectionMode" class="card-fav-btn" :class="{ active: model.is_favorite }"
                        @click.stop="emit('toggleFavorite', model, $event)" title="Toggle favorite">
                    <span v-html="model.is_favorite ? ICONS.heartFilled : ICONS.heart"></span>
                </button>
                <button v-if="selectionMode" class="card-select-check"
                        @click.stop="emit('toggleSelect', model.id)">
                    <span v-html="ICONS.check"></span>
                </button>
            </div>
            <!-- Body -->
            <div class="card-body">
                <div class="card-name" :title="model.name">{{ model.name }}</div>
                <div class="card-meta">
                    {{ formatFileSize(model.file_size) }}
                    <span v-if="model.zip_path" class="zip-badge" :title="zipName(model)">zip</span>
                    <span v-if="model.is_duplicate" class="dup-badge" title="Duplicate file (same hash)">dup</span>
                </div>
                <div class="card-tags" v-if="model.tags && model.tags.length">
                    <span v-for="t in model.tags.slice(0, 3)" :key="t" class="tag-chip">{{ t }}</span>
                    <span v-if="model.tags.length > 3" class="tag-chip" style="opacity:0.7">
                        +{{ model.tags.length - 3 }}
                    </span>
                </div>
            </div>
        </div>
    </div>

    <!-- List View -->
    <div v-else class="models-list">
        <table class="models-table">
            <thead>
                <tr>
                    <th v-if="selectionMode" class="col-select" style="width:32px"></th>
                    <th class="col-fav" style="width:32px"></th>
                    <th>Name</th>
                    <th class="col-format">Format</th>
                    <th class="col-vertices">Vertices</th>
                    <th class="col-faces">Faces</th>
                    <th class="col-size">Size</th>
                    <th class="col-date">Date</th>
                    <th class="col-tags">Tags</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="model in models" :key="model.id" :class="{ selected: selectionMode && isSelected(model.id) }" @click="emit('viewModel', model)">
                    <td v-if="selectionMode" class="col-select" @click.stop="emit('toggleSelect', model.id)" style="cursor:pointer;text-align:center">
                        <span v-html="ICONS.check" :style="{ opacity: isSelected(model.id) ? 1 : 0.3 }"></span>
                    </td>
                    <td class="col-fav" @click.stop="emit('toggleFavorite', model, $event)" style="cursor:pointer;text-align:center">
                        <span v-html="model.is_favorite ? ICONS.heartFilled : ICONS.heart" :style="{ color: model.is_favorite ? 'var(--danger)' : 'var(--text-muted)' }"></span>
                    </td>
                    <td class="col-name">{{ model.name }} <span v-if="model.zip_path" class="zip-badge" :title="zipName(model)">zip</span><span v-if="model.is_duplicate" class="dup-badge" title="Duplicate">dup</span></td>
                    <td class="col-format">
                        <span class="format-badge" :class="formatClass(model.file_format)">
                            {{ model.file_format }}
                        </span>
                    </td>
                    <td class="col-vertices">{{ formatNumber(model.vertex_count) }}</td>
                    <td class="col-faces">{{ formatNumber(model.face_count) }}</td>
                    <td class="col-size">{{ formatFileSize(model.file_size) }}</td>
                    <td class="col-date">{{ formatDate(model.updated_at || model.created_at) }}</td>
                    <td class="col-tags">
                        <span v-for="t in (model.tags || []).slice(0, 2)" :key="t"
                              class="tag-chip" style="margin-right:4px">{{ t }}</span>
                        <span v-if="(model.tags || []).length > 2" class="text-muted text-sm">
                            +{{ model.tags.length - 2 }}
                        </span>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
</template>
