<script setup>
/**
 * DetailPanel - Model detail overlay with 3D viewer and tabbed info panel.
 * Tabs: Info (description, source, file summary, categories), Tags, More (collections, duplicates).
 */
import { ICONS } from '../icons.js';
import { formatFileSize, formatNumber, formatDimensions } from '../search.js';

defineProps({
    selectedModel: { type: Object, default: null },
    showDetail: { type: Boolean, default: false },
    viewerLoading: { type: Boolean, default: false },
    editName: { type: String, default: '' },
    editDesc: { type: String, default: '' },
    editSourceUrl: { type: String, default: '' },
    isEditingName: { type: Boolean, default: false },
    isEditingDesc: { type: Boolean, default: false },
    isEditingSourceUrl: { type: Boolean, default: false },
    tagSuggestions: { type: Array, default: () => [] },
    tagSuggestionsLoading: { type: Boolean, default: false },
    newTagInput: { type: String, default: '' },
    allCategories: { type: Array, default: () => [] },
    collections: { type: Array, default: () => [] },
    detailTab: { type: String, default: 'info' },
    showFileDetails: { type: Boolean, default: false },
});

const emit = defineEmits([
    'close',
    'update:editName',
    'update:editDesc',
    'update:editSourceUrl',
    'update:isEditingName',
    'update:isEditingDesc',
    'update:isEditingSourceUrl',
    'update:newTagInput',
    'update:detailTab',
    'update:showFileDetails',
    'saveName',
    'saveDesc',
    'saveSourceUrl',
    'startEditName',
    'startEditDesc',
    'startEditSourceUrl',
    'resetView',
    'toggleFavorite',
    'openAddToCollection',
    'removeModelFromCollection',
    'addTag',
    'removeTag',
    'fetchTagSuggestions',
    'applyTagSuggestion',
    'renameModelFile',
    'deleteModel',
]);

function formatClass(fmt) {
    if (!fmt) return '';
    const f = fmt.toLowerCase().replace('.', '');
    if (f === '3mf') return '_3mf';
    return f;
}
</script>

<template>
    <div v-if="showDetail && selectedModel" class="detail-overlay" @click.self="emit('close')">
        <div class="detail-panel">
            <!-- Header -->
            <div class="detail-header">
                <div class="detail-title">
                    <template v-if="!isEditingName">
                        <span @dblclick="emit('startEditName')" title="Double-click to edit">
                            {{ selectedModel.name }}
                        </span>
                        <button class="btn-icon btn-edit-inline" @click="emit('startEditName')" title="Rename model">
                            <span v-html="ICONS.edit || '&#9998;'"></span>
                        </button>
                    </template>
                    <template v-else>
                        <input type="text"
                               :value="editName"
                               @input="emit('update:editName', $event.target.value)"
                               @blur="emit('saveName')"
                               @keydown.enter="emit('saveName')"
                               @keydown.escape="emit('update:isEditingName', false)"
                               @vue:mounted="$event.el.focus()"
                               style="flex:1;min-width:0;padding:4px 8px;background:var(--bg-input);border:1px solid var(--accent);border-radius:4px;color:var(--text-primary);font-size:1.1rem;font-weight:600">
                    </template>
                </div>
                <button class="btn btn-sm btn-ghost" :class="{ 'text-danger': selectedModel.is_favorite }"
                        @click="emit('toggleFavorite', selectedModel, $event)" title="Toggle favorite">
                    <span v-html="selectedModel.is_favorite ? ICONS.heartFilled : ICONS.heart"></span>
                </button>
                <button class="btn btn-sm btn-ghost"
                        @click="emit('openAddToCollection', selectedModel.id)" title="Add to collection">
                    <span v-html="ICONS.collection"></span>
                </button>
                <button class="close-btn" @click="emit('close')" title="Close">&times;</button>
            </div>

            <!-- Content: Viewer + Info -->
            <div class="detail-content">
                <!-- 3D Viewer -->
                <div class="detail-viewer">
                    <div id="viewer-container">
                        <!-- Viewer loading -->
                        <div v-if="viewerLoading" class="viewer-loading">
                            <div class="spinner"></div>
                            <span>Loading 3D model...</span>
                        </div>
                    </div>
                    <!-- Viewer toolbar -->
                    <div class="viewer-toolbar">
                        <button class="btn" @click="emit('resetView')">Reset View</button>
                    </div>
                </div>

                <!-- Info Panel (tabbed) -->
                <div class="detail-info">
                    <!-- Tab bar -->
                    <div class="detail-tabs">
                        <button class="detail-tab" :class="{ active: detailTab === 'info' }"
                                @click="emit('update:detailTab', 'info')">Info</button>
                        <button class="detail-tab" :class="{ active: detailTab === 'tags' }"
                                @click="emit('update:detailTab', 'tags')">Tags</button>
                        <button class="detail-tab" :class="{ active: detailTab === 'more' }"
                                @click="emit('update:detailTab', 'more')">More</button>
                    </div>

                    <!-- Tab content (scrollable) -->
                    <div class="detail-tab-content">

                        <!-- ==================== INFO TAB ==================== -->
                        <template v-if="detailTab === 'info'">
                            <!-- Description -->
                            <div class="info-section">
                                <div class="info-section-title">Description</div>
                                <div v-if="!isEditingDesc"
                                     @dblclick="emit('startEditDesc')"
                                     style="cursor:pointer;min-height:36px;font-size:0.85rem;color:var(--text-secondary);padding:4px 0">
                                    {{ selectedModel.description || 'Double-click to add a description...' }}
                                </div>
                                <div v-else class="editable-field">
                                    <textarea :value="editDesc"
                                              @input="emit('update:editDesc', $event.target.value)"
                                              rows="3"
                                              @blur="emit('saveDesc')"
                                              @keydown.escape="emit('update:isEditingDesc', false)"
                                              placeholder="Enter description..."
                                              autofocus></textarea>
                                </div>
                            </div>

                            <!-- Source Link -->
                            <div class="info-section">
                                <div class="info-section-title">Source</div>
                                <template v-if="!isEditingSourceUrl">
                                    <div v-if="selectedModel.source_url"
                                         style="display:flex;align-items:center;gap:6px">
                                        <a :href="selectedModel.source_url" target="_blank" rel="noopener"
                                           class="source-link" style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                                            <span v-html="ICONS.link || '&#128279;'"></span>
                                            {{ selectedModel.source_url }}
                                        </a>
                                        <button class="btn-icon" style="width:20px;height:20px;flex-shrink:0"
                                                @click="emit('startEditSourceUrl')" title="Edit source URL">
                                            <span v-html="ICONS.edit || '&#9998;'"></span>
                                        </button>
                                    </div>
                                    <div v-else @dblclick="emit('startEditSourceUrl')"
                                         style="cursor:pointer;font-size:0.85rem;color:var(--text-secondary);padding:4px 0">
                                        Double-click to add a source URL...
                                    </div>
                                </template>
                                <template v-else>
                                    <div class="editable-field">
                                        <input type="url"
                                               :value="editSourceUrl"
                                               @input="emit('update:editSourceUrl', $event.target.value)"
                                               @blur="emit('saveSourceUrl')"
                                               @keydown.enter="emit('saveSourceUrl')"
                                               @keydown.escape="emit('update:isEditingSourceUrl', false)"
                                               placeholder="https://..."
                                               style="width:100%;padding:4px 8px;background:var(--bg-input);border:1px solid var(--accent);border-radius:4px;color:var(--text-primary);font-size:0.85rem"
                                               autofocus>
                                    </div>
                                </template>
                            </div>

                            <!-- File Summary + Expandable Details -->
                            <div class="info-section">
                                <div class="info-section-title">File</div>
                                <div class="file-summary">
                                    <span class="format-badge" :class="formatClass(selectedModel.file_format)">
                                        {{ selectedModel.file_format }}
                                    </span>
                                    <span class="file-summary-size">{{ formatFileSize(selectedModel.file_size) }}</span>
                                    <button class="file-details-toggle" @click="emit('update:showFileDetails', !showFileDetails)">
                                        <span>{{ showFileDetails ? '\u25BC' : '\u25B6' }}</span> Details
                                    </button>
                                </div>
                                <div v-if="showFileDetails" class="file-details">
                                    <div class="info-field">
                                        <span class="field-label">Vertices</span>
                                        <span class="field-value">{{ formatNumber(selectedModel.vertex_count) }}</span>
                                    </div>
                                    <div class="info-field">
                                        <span class="field-label">Faces</span>
                                        <span class="field-value">{{ formatNumber(selectedModel.face_count) }}</span>
                                    </div>
                                    <div class="info-field">
                                        <span class="field-label">Dimensions</span>
                                        <span class="field-value">
                                            {{ formatDimensions(selectedModel.dimensions_x, selectedModel.dimensions_y, selectedModel.dimensions_z) }}
                                        </span>
                                    </div>
                                    <div v-if="selectedModel.zip_path" class="info-field" style="margin-top:4px">
                                        <span class="field-label">Zip Archive</span>
                                        <span class="field-value field-value-path">
                                            {{ selectedModel.zip_path }}
                                        </span>
                                    </div>
                                    <div v-if="selectedModel.zip_entry" class="info-field">
                                        <span class="field-label">Zip Entry</span>
                                        <span class="field-value field-value-path">
                                            {{ selectedModel.zip_entry }}
                                        </span>
                                    </div>
                                    <div class="info-field" :style="selectedModel.zip_path ? {} : { 'margin-top': '4px' }">
                                        <span class="field-label">Path</span>
                                        <span class="field-value field-value-path">
                                            {{ selectedModel.file_path }}
                                        </span>
                                    </div>
                                    <div v-if="selectedModel.file_hash" class="info-field">
                                        <span class="field-label">Hash</span>
                                        <span class="field-value field-value-hash">
                                            {{ selectedModel.file_hash }}
                                        </span>
                                    </div>
                                    <div v-if="!selectedModel.zip_path" style="margin-top:10px">
                                        <button class="btn btn-sm btn-secondary" @click="emit('renameModelFile')" title="Rename the file on disk to match the model name">
                                            <span v-html="ICONS.edit || '&#9998;'"></span> Rename File on Disk
                                        </button>
                                        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:4px">
                                            Renames the actual file to match the model name above.
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- Categories -->
                            <div class="info-section">
                                <div class="info-section-title">Categories</div>
                                <div class="tags-list">
                                    <span v-for="cat in (selectedModel.categories || [])" :key="cat"
                                          class="tag-chip" style="background:var(--bg-primary);color:var(--text-secondary);border:1px solid var(--border)">
                                        {{ cat }}
                                    </span>
                                    <span v-if="!selectedModel.categories || !selectedModel.categories.length"
                                          class="text-muted text-sm">Uncategorized</span>
                                </div>
                            </div>
                        </template>

                        <!-- ==================== TAGS TAB ==================== -->
                        <template v-if="detailTab === 'tags'">
                            <div class="info-section">
                                <div class="tags-list">
                                    <span v-for="tag in (selectedModel.tags || [])" :key="tag" class="tag-chip">
                                        {{ tag }}
                                        <button class="tag-remove" @click="emit('removeTag', tag)" title="Remove tag">&times;</button>
                                    </span>
                                    <span v-if="!selectedModel.tags || !selectedModel.tags.length"
                                          class="text-muted text-sm">No tags</span>
                                </div>
                                <div class="tag-add-row">
                                    <input type="text"
                                           :value="newTagInput"
                                           @input="emit('update:newTagInput', $event.target.value)"
                                           placeholder="Add tag..."
                                           @keydown.enter="emit('addTag')">
                                    <button class="btn btn-sm btn-primary" @click="emit('addTag')">Add</button>
                                </div>
                                <!-- Tag suggestions -->
                                <div style="margin-top:8px">
                                    <button class="btn btn-sm btn-ghost" @click="emit('fetchTagSuggestions')" :disabled="tagSuggestionsLoading">
                                        Suggest Tags
                                    </button>
                                    <div v-if="tagSuggestions.length > 0" class="tag-suggestions" style="margin-top:6px">
                                        <span v-for="s in tagSuggestions" :key="s" class="tag-chip tag-suggestion"
                                              @click="emit('applyTagSuggestion', s)" style="cursor:pointer">
                                            + {{ s }}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </template>

                        <!-- ==================== MORE TAB ==================== -->
                        <template v-if="detailTab === 'more'">
                            <!-- Duplicate Warning -->
                            <div v-if="selectedModel.file_hash" class="duplicate-warning" style="display:none">
                                <span v-html="ICONS.warning"></span>
                                <span>This file has duplicates in the library.</span>
                            </div>

                            <!-- Collections -->
                            <div class="info-section">
                                <div class="info-section-title" style="display:flex;align-items:center;justify-content:space-between">
                                    Collections
                                    <button class="btn-icon" style="width:20px;height:20px"
                                            @click="emit('openAddToCollection', selectedModel.id)" title="Add to collection">
                                        <span v-html="ICONS.plus"></span>
                                    </button>
                                </div>
                                <div class="tags-list">
                                    <span v-for="col in (selectedModel.collections || [])" :key="col.id"
                                          class="tag-chip" :style="{ background: (col.color || '#666') + '22', color: col.color || '#666', border: '1px solid ' + (col.color || '#666') + '44' }">
                                        <span class="collection-dot" :style="{ background: col.color || '#666' }" style="width:8px;height:8px;margin-right:4px"></span>
                                        {{ col.name }}
                                        <button class="tag-remove" @click="emit('removeModelFromCollection', col.id, selectedModel.id)" title="Remove from collection">&times;</button>
                                    </span>
                                    <span v-if="!selectedModel.collections || !selectedModel.collections.length"
                                          class="text-muted text-sm">No collections</span>
                                </div>
                            </div>
                        </template>

                    </div>

                    <!-- Pinned actions bar -->
                    <div class="detail-actions-pinned">
                        <a class="btn btn-secondary" style="flex:1"
                           :href="'/api/models/' + selectedModel.id + '/download'"
                           download>
                            <span v-html="ICONS.download"></span>
                            Download {{ selectedModel.file_format ? selectedModel.file_format.toUpperCase() : '' }}
                        </a>
                        <button class="btn btn-danger" style="flex:1" @click="emit('deleteModel', selectedModel)">
                            <span v-html="ICONS.trash"></span>
                            Delete
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
