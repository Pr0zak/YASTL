<script setup>
/**
 * ModelGrid - Grid and list views of model cards.
 */
import { ICONS } from '../icons.js';
import { formatFileSize, formatDate } from '../search.js';
import TagChip from './TagChip.vue';

const props = defineProps({
    models: { type: Array, default: () => [] },
    viewMode: { type: String, default: 'grid' },
    selectionMode: { type: Boolean, default: false },
    selectedModels: { type: Set, default: () => new Set() },
    thumbnailMode: { type: String, default: 'solid' },
    collectionCardTint: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    density: { type: String, default: 'comfortable' },
});

const emit = defineEmits([
    'viewModel',
    'filterByTag',
    'toggleSelect',
    'toggleFavorite',
    'expandZipGroup',
    'dragStart',
    'dragEnd',
]);

function isZipGroup(model) {
    return model.zip_model_count != null && model.zip_model_count > 1;
}

function isError(model) {
    return model.status === 'error';
}

function onDragStart(model, event) {
    if (isZipGroup(model)) {
        event.preventDefault();
        return;
    }
    event.dataTransfer.effectAllowed = 'copy';
    event.dataTransfer.setData('text/plain', String(model.id));
    emit('dragStart', model);
}

function onCardClick(model, idx, event) {
    if (isZipGroup(model)) {
        emit('expandZipGroup', model.zip_path);
    } else if (props.selectionMode) {
        emit('toggleSelect', model.id, idx, event && event.shiftKey);
    } else {
        emit('viewModel', model);
    }
}

function thumbUrl(model) {
    if (model.thumbnail_path) {
        return `/thumbnails/${model.thumbnail_path}`;
    }
    return `/api/models/${model.id}/thumbnail`;
}

function onThumbError(e) {
    e.target.style.display = 'none';
    const fallback = e.target.closest('.tile-media')?.querySelector('.no-thumbnail');
    if (fallback) fallback.style.display = 'flex';
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

/**
 * Colour lives in the model: the thumbnail is recoloured in its first
 * collection's hue. Thumbnails are transparent PNGs, so a layer masked by
 * the image itself and blended with `mix-blend-mode: color` keeps the
 * render's shading and swaps only hue and saturation — no re-render, and it
 * follows collection changes instantly. Models in no collection keep teal.
 */
function tintStyle(model) {
    if (!props.collectionCardTint || !model.collection_colors?.length) return null;
    const url = `url("${thumbUrl(model)}")`;
    return { '--tint': model.collection_colors[0], maskImage: url, WebkitMaskImage: url };
}

function tileLabel(model) {
    if (isZipGroup(model)) return `${model.zip_group_name}, zip archive with ${model.zip_model_count} models`;
    const parts = [model.name, model.file_format, formatFileSize(model.file_size)];
    if (isError(model)) parts.push('failed to process');
    return parts.filter(Boolean).join(', ');
}

function onTileKey(model, idx, e) {
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onCardClick(model, idx, e);
    }
}
</script>

<template>
    <!-- Skeleton grid while the first page loads -->
    <div v-if="loading && !models.length && viewMode === 'grid'"
         class="models-grid" :class="'density-' + density" aria-busy="true">
        <div v-for="n in 12" :key="'sk' + n" class="tile skeleton-tile skeleton-shimmer"></div>
    </div>

    <!-- Grid: a gallery wall. The picture is the card; the name sits on a
         gradient at the bottom, and size, format and tags slide up on hover. -->
    <div v-else-if="viewMode === 'grid'" class="models-grid" :class="'density-' + density" role="list">
        <div v-for="(model, idx) in models" :key="model.id" role="listitem"
             class="tile"
             :class="{
                 selected: selectionMode && isSelected(model.id),
                 'tile-zip': isZipGroup(model),
                 'tile-error': isError(model),
                 'tile-selecting': selectionMode,
             }"
             :draggable="!isZipGroup(model)"
             @dragstart="onDragStart(model, $event)"
             @dragend="emit('dragEnd')">
            <div class="tile-media">
                <div class="tile-pic">
                    <img :src="thumbUrl(model)" alt="" class="tile-img"
                         @load="(e) => e.target.classList.add('loaded')"
                         @error="onThumbError"
                         loading="lazy">
                    <span v-if="tintStyle(model)" class="tile-tint" :style="tintStyle(model)" aria-hidden="true"></span>
                </div>
                <div class="no-thumbnail" style="display:none">
                    <span v-html="ICONS.cube"></span>
                    <span>{{ model.file_format }}</span>
                </div>
            </div>

            <!-- One real button covers the tile: keyboard and screen readers get
                 a single named control instead of a clickable div. -->
            <button type="button" class="tile-open" :aria-label="tileLabel(model)"
                    :aria-pressed="selectionMode && !isZipGroup(model) ? String(isSelected(model.id)) : undefined"
                    @click="onCardClick(model, idx, $event)" @keydown="onTileKey(model, idx, $event)"></button>

            <div class="tile-info" aria-hidden="true">
                <div class="tile-name" :title="isZipGroup(model) ? model.zip_group_name : model.name">
                    {{ isZipGroup(model) ? model.zip_group_name : model.name }}
                </div>
                <div class="tile-meta">
                    <template v-if="isZipGroup(model)">{{ model.zip_model_count }} models in a zip</template>
                    <template v-else-if="isError(model)"><span class="tile-err">Failed</span> {{ model.error_reason }}</template>
                    <template v-else>
                        <span class="format-badge">{{ model.file_format }}</span>
                        {{ formatFileSize(model.file_size) }}
                        <span v-if="model.zip_path" class="zip-badge" :title="zipName(model)">zip</span>
                        <span v-if="model.is_duplicate" class="dup-badge" title="Duplicate file (same hash)">dup</span>
                    </template>
                </div>
                <div v-if="!isZipGroup(model) && model.tags && model.tags.length" class="tile-tags">
                    <span v-for="t in model.tags.slice(0, 3)" :key="t" class="tile-tag">{{ t }}</span>
                    <span v-if="model.tags.length > 3" class="tile-tag">+{{ model.tags.length - 3 }}</span>
                </div>
            </div>

            <!-- Badges -->
            <span v-if="isZipGroup(model)" class="tile-badge tile-badge-zip">
                <span v-html="ICONS.folder"></span>{{ model.zip_model_count }}
            </span>
            <span v-else-if="model.plate_count > 1" class="tile-badge"
                  :title="model.plate_count + ' build plates (Bambu/Orca project)'">{{ model.plate_count }} plates</span>
            <span v-if="!isZipGroup(model) && model.print_count > 0" class="tile-badge tile-badge-printed"
                  :class="{ 'tile-badge-second': model.plate_count > 1 }"
                  :title="'Printed ' + model.print_count + ' time' + (model.print_count === 1 ? '' : 's')">
                <span v-html="ICONS.check"></span>{{ model.print_count > 1 ? model.print_count : '' }}
            </span>

            <button v-if="!selectionMode && !isZipGroup(model)" type="button" class="tile-fav" :class="{ active: model.is_favorite }"
                    @click.stop="emit('toggleFavorite', model, $event)"
                    :aria-pressed="String(!!model.is_favorite)"
                    :aria-label="(model.is_favorite ? 'Remove from favourites: ' : 'Add to favourites: ') + model.name"
                    :title="model.is_favorite ? 'Remove from favourites' : 'Add to favourites'">
                <span v-html="model.is_favorite ? ICONS.heartFilled : ICONS.heart"></span>
            </button>
            <span v-if="selectionMode && !isZipGroup(model)" class="tile-check" aria-hidden="true" v-html="ICONS.check"></span>
        </div>
    </div>

    <!-- List View -->
    <div v-else class="models-list">
        <table class="models-table">
            <thead>
                <tr>
                    <th class="col-thumb"><span class="visually-hidden">Preview</span></th>
                    <th>Name</th>
                    <th class="col-format">Format</th>
                    <th class="col-size">Size</th>
                    <th class="col-date">Modified</th>
                    <th class="col-tags">Tags</th>
                    <th class="col-fav"><span class="visually-hidden">Favourite</span></th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="(model, idx) in models" :key="model.id"
                    :class="{ selected: selectionMode && isSelected(model.id), 'zip-group-row': isZipGroup(model) }"
                    @click="onCardClick(model, idx, $event)">
                    <td class="col-thumb">
                        <span class="row-thumb">
                            <img :src="thumbUrl(model)" alt="" loading="lazy" @error="(e) => (e.target.style.visibility = 'hidden')">
                            <span v-if="tintStyle(model)" class="tile-tint" :style="tintStyle(model)" aria-hidden="true"></span>
                            <span v-if="selectionMode && !isZipGroup(model)" class="row-check" v-html="ICONS.check"></span>
                        </span>
                    </td>
                    <td class="col-name">
                        <button type="button" class="row-open" @click.stop="onCardClick(model, idx, $event)"
                                :aria-pressed="selectionMode && !isZipGroup(model) ? String(isSelected(model.id)) : undefined">
                            <span class="row-name">
                                <span v-if="isZipGroup(model)" class="zip-badge">zip</span>
                                {{ isZipGroup(model) ? model.zip_group_name : model.name }}
                                <span v-if="isError(model)" class="error-badge" :title="model.error_reason">failed</span>
                                <span v-if="model.is_duplicate" class="dup-badge" title="Duplicate">dup</span>
                            </span>
                            <span class="row-sub">
                                <template v-if="isZipGroup(model)">{{ model.zip_model_count }} models</template>
                                <template v-else>
                                    <span v-for="col in (model.collections || [])" :key="col.name" class="row-col">
                                        <span class="sb-dot" :style="{ background: col.color || 'var(--text-muted)' }"></span>{{ col.name }}
                                    </span>
                                    <span class="row-sub-phone">{{ model.file_format }} · {{ formatFileSize(model.file_size) }} · {{ formatDate(model.updated_at || model.created_at) }}</span>
                                </template>
                            </span>
                        </button>
                    </td>
                    <td class="col-format"><span class="format-badge">{{ model.file_format }}</span></td>
                    <td class="col-size">{{ formatFileSize(model.file_size) }}</td>
                    <td class="col-date">{{ formatDate(model.updated_at || model.created_at) }}</td>
                    <td class="col-tags">
                        <TagChip v-for="t in (model.tags || []).slice(0, 2)" :key="t" :name="t" class="row-tag" />
                        <span v-if="(model.tags || []).length > 2" class="text-muted text-sm">
                            +{{ model.tags.length - 2 }}
                        </span>
                    </td>
                    <td class="col-fav">
                        <button v-if="!isZipGroup(model)" type="button" class="row-fav" :class="{ active: model.is_favorite }"
                                @click.stop="emit('toggleFavorite', model, $event)"
                                :aria-pressed="String(!!model.is_favorite)"
                                :aria-label="(model.is_favorite ? 'Remove from favourites: ' : 'Add to favourites: ') + model.name"
                                v-html="model.is_favorite ? ICONS.heartFilled : ICONS.heart"></button>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
</template>
