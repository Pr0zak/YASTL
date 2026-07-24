<script setup>
/**
 * DetailPanel - Model detail overlay with 3D viewer and tabbed info panel.
 * Tabs: Info (description, source, file summary, categories), Tags, More (collections, duplicates).
 */
import { computed, ref, reactive, watch } from 'vue';
import { ICONS } from '../icons.js';
import { formatFileSize, formatNumber, formatDimensions, formatDate } from '../search.js';
import { parseTag, tagColorStyle } from '../tags.js';

// On touch devices the 3D canvas grabs drags for orbit, which fights scrolling
// the detail sheet. Keep the viewer inert until the user taps to interact, so
// the sheet scrolls normally over the model. Desktop (fine pointer) is always live.
const isCoarsePointer = typeof window !== 'undefined'
    && (window.matchMedia?.('(pointer: coarse)')?.matches || 'ontouchstart' in window);
const viewerInteractive = ref(!isCoarsePointer);

const props = defineProps({
    selectedModel: { type: Object, default: null },
    showDetail: { type: Boolean, default: false },
    viewerLoading: { type: Boolean, default: false },
    viewerProgress: { type: Number, default: null },
    viewerDecimated: { type: Boolean, default: false },
    navIndex: { type: Number, default: -1 },
    navTotal: { type: Number, default: 0 },
    viewerClipping: { type: Boolean, default: false },
    viewerClipPos: { type: Number, default: 0.55 },
    viewerOrtho: { type: Boolean, default: false },
    viewerMeasuring: { type: Boolean, default: false },
    viewerMeasuredMm: { type: Number, default: null },
    editName: { type: String, default: '' },
    editDesc: { type: String, default: '' },
    editSourceUrl: { type: String, default: '' },
    editLicense: { type: String, default: '' },
    isEditingName: { type: Boolean, default: false },
    isEditingDesc: { type: Boolean, default: false },
    isEditingSourceUrl: { type: Boolean, default: false },
    isEditingLicense: { type: Boolean, default: false },
    tagSuggestions: { type: Array, default: () => [] },
    tagSuggestionsLoading: { type: Boolean, default: false },
    relatedTags: { type: Array, default: () => [] },
    modelDocs: { type: Object, default: null },
    newTagInput: { type: String, default: '' },
    allTags: { type: Array, default: () => [] },
    allCategories: { type: Array, default: () => [] },
    collections: { type: Array, default: () => [] },
    printHistory: { type: Array, default: () => [] },
    filaments: { type: Array, default: () => [] },
    aiEnabled: { type: Boolean, default: false },
    aiTagging: { type: Boolean, default: false },
    relatedModels: { type: Array, default: () => [] },
    variantCandidates: { type: Array, default: () => [] },
    variantPickerOpen: { type: Boolean, default: false },
    variantQuery: { type: String, default: '' },
    variantSearching: { type: Boolean, default: false },
    detailTab: { type: String, default: 'info' },
    showFileDetails: { type: Boolean, default: false },
    bedConfig: { type: Object, default: () => ({ enabled: false, width: 256, depth: 256, height: 256, shape: 'rectangular' }) },
    bedVisible: { type: Boolean, default: false },
    bedFits: { type: Boolean, default: true },
    preferredSlicer: { type: String, default: 'none' },
});

const emit = defineEmits([
    'close',
    'update:editName',
    'update:editDesc',
    'update:editSourceUrl',
    'update:editLicense',
    'update:isEditingName',
    'update:isEditingDesc',
    'update:isEditingSourceUrl',
    'update:newTagInput',
    'update:detailTab',
    'update:showFileDetails',
    'saveName',
    'saveDesc',
    'saveSourceUrl',
    'update:isEditingLicense',
    'startEditLicense',
    'saveLicense',
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
    'toggleBed',
    'regenerateThumbnail',
    'openRelatedModel',
    'openVariant',
    'linkVariant',
    'unlinkVariant',
    'searchVariants',
    'update:variantPickerOpen',
    'update:variantQuery',
    'filterByTag',
    'loadFullResolution',
    'navigate',
    'setView',
    'toggleClipping',
    'setClipPosition',
    'toggleOrtho',
    'toggleMeasuring',
    'logPrint',
    'undoPrint',
    'deletePrint',
    'clearAutoTags',
    'aiTagModel',
]);

// Re-arm the tap-to-interact gate each time a different model opens on touch.
watch(() => props.selectedModel?.id, () => {
    if (isCoarsePointer) viewerInteractive.value = false;
});

// Log-with-details form state (Print History)
const showPrintForm = ref(false);
const printForm = reactive({ quantity: 1, location: '', filament_id: null, grams_used: null });
function resetPrintForm() {
    showPrintForm.value = false;
    printForm.quantity = 1;
    printForm.location = '';
    printForm.filament_id = null;
    printForm.grams_used = null;
}
function submitPrintForm() {
    emit('logPrint', { ...printForm });
    resetPrintForm();
}

function viewerThumb(model) {
    if (model && model.thumbnail_path) return `/thumbnails/${model.thumbnail_path}`;
    if (model) return `/api/models/${model.id}/thumbnail`;
    return '';
}

function docFileUrl(name) {
    const id = props.selectedModel?.id;
    return `/api/models/${id}/docs/file?name=${encodeURIComponent(name)}`;
}

// Non-README doc files (license, etc.) shown as links, README excluded.
const docLinks = computed(() => {
    const docs = props.modelDocs?.docs || [];
    const readmeName = props.modelDocs?.readme?.name;
    return docs.filter((d) => d.name !== readmeName);
});

function isAutoTag(tag) {
    // Any machine-generated source (heuristic 'auto' or vision 'ai').
    const s = props.selectedModel?.tag_sources?.[tag];
    return !!s && s !== 'manual';
}
const hasAutoTags = computed(() =>
    Object.values(props.selectedModel?.tag_sources || {}).some((s) => s && s !== 'manual')
);

// Autocomplete suggestions for the add-tag input: existing tag names not
// already applied to this model.
const tagAutocomplete = computed(() => {
    const applied = new Set((props.selectedModel?.tags || []).map((t) => t.toLowerCase()));
    return props.allTags
        .map((t) => t.name)
        .filter((name) => name && !applied.has(name.toLowerCase()));
});

const SLICER_FORMATS = ['stl', '3mf', 'obj'];
const SLICER_PROTOCOLS = {
    bambustudio: 'bambustudio://open?file=',
    orcaslicer: 'orcaslicer://open?file=',
    prusaslicer: 'prusaslicer://open?file=',
};
const SLICER_LABELS = {
    bambustudio: 'Bambu Studio',
    orcaslicer: 'OrcaSlicer',
    prusaslicer: 'PrusaSlicer',
};
const baseUrl = globalThis.location?.origin || '';

function slicerHref(model) {
    // Slicers (Bambu/Orca/Prusa) detect the format from the URL path
    // extension, so the download URL must end in the real file extension.
    const ext = (model.file_format || '').toLowerCase().replace('.', '');
    let stem = (model.name || 'model').replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '') || 'model';
    if (stem.toLowerCase().endsWith('.' + ext)) {
        stem = stem.slice(0, -(ext.length + 1));
    }
    const fileUrl = `${baseUrl}/api/models/${model.id}/download/${stem}.${ext}`;
    return (SLICER_PROTOCOLS[props.preferredSlicer] || '') + encodeURIComponent(fileUrl);
}

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
                <div class="detail-nav" v-if="navTotal > 1">
                    <button class="btn-icon" :disabled="navIndex <= 0"
                            @click="emit('navigate', -1)" title="Previous model (←)">
                        <span v-html="ICONS.chevron" style="transform:rotate(90deg);display:inline-flex"></span>
                    </button>
                    <span class="detail-nav-pos">{{ navIndex + 1 }} / {{ navTotal }}</span>
                    <button class="btn-icon" :disabled="navIndex >= navTotal - 1"
                            @click="emit('navigate', 1)" title="Next model (→)">
                        <span v-html="ICONS.chevron" style="transform:rotate(-90deg);display:inline-flex"></span>
                    </button>
                </div>
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
                    <div id="viewer-container" :class="{ 'viewer-inert': !viewerInteractive }">
                        <!-- Tap-to-interact gate: on touch, keep the canvas inert so the
                             sheet scrolls; tapping activates orbit for this model. -->
                        <button v-if="!viewerInteractive && !viewerLoading && selectedModel.status !== 'error'"
                                class="viewer-tap-gate" @click="viewerInteractive = true">
                            <span v-html="ICONS.cube"></span>
                            <span>Tap to interact</span>
                        </button>
                        <!-- Thumbnail underlay so opening feels instant while 3D loads -->
                        <img v-if="viewerLoading && selectedModel.status !== 'error'"
                             :src="viewerThumb(selectedModel)" class="viewer-thumb-underlay" alt=""
                             @error="(e) => (e.target.style.display = 'none')">
                        <!-- Viewer loading -->
                        <div v-if="viewerLoading" class="viewer-loading">
                            <div class="spinner"></div>
                            <span>Loading 3D model…</span>
                            <div v-if="viewerProgress != null" class="viewer-progress">
                                <div class="viewer-progress-fill"
                                     :style="{ width: Math.round(viewerProgress * 100) + '%' }"></div>
                            </div>
                        </div>
                        <!-- Error model: no 3D preview -->
                        <div v-else-if="selectedModel.status === 'error'" class="viewer-error-notice">
                            <span v-html="ICONS.cube"></span>
                            <span>3D preview disabled</span>
                            <span class="viewer-error-reason">{{ selectedModel.error_reason || 'This model failed to process' }}</span>
                        </div>
                    </div>
                    <!-- Viewer toolbar -->
                    <div class="viewer-toolbar">
                        <button class="btn" @click="emit('resetView')">Reset View</button>
                        <select class="btn viewer-view-select" title="Camera angle"
                                @change="emit('setView', $event.target.value); $event.target.selectedIndex = 0">
                            <option value="" disabled selected>View</option>
                            <option value="iso">Isometric</option>
                            <option value="front">Front</option>
                            <option value="back">Back</option>
                            <option value="left">Left</option>
                            <option value="right">Right</option>
                            <option value="top">Top</option>
                            <option value="bottom">Bottom</option>
                        </select>
                        <button class="btn" :class="{ 'btn-active': viewerOrtho }"
                                @click="emit('toggleOrtho')"
                                :title="viewerOrtho ? 'Orthographic (click for perspective)' : 'Perspective (click for orthographic)'">
                            {{ viewerOrtho ? 'Ortho' : 'Persp' }}
                        </button>
                        <button class="btn" :class="{ 'btn-active': viewerMeasuring }"
                                @click="emit('toggleMeasuring')"
                                title="Measure: click two points on the model for a distance">
                            {{ viewerMeasuredMm != null ? (viewerMeasuredMm.toFixed(1) + ' mm') : 'Measure' }}
                        </button>
                        <button class="btn" :class="{ 'btn-active': viewerClipping }"
                                @click="emit('toggleClipping')"
                                title="Cross-section: slice the model to inspect the interior">
                            Clip
                        </button>
                        <input v-if="viewerClipping" type="range" min="0" max="1" step="0.01"
                               class="viewer-clip-slider" :value="viewerClipPos"
                               @input="emit('setClipPosition', parseFloat($event.target.value))"
                               title="Cross-section height">
                        <button v-if="viewerDecimated && !viewerLoading" class="btn"
                                @click="emit('loadFullResolution')"
                                title="Showing a simplified preview — load the full-detail mesh">
                            Full resolution
                        </button>
                        <button class="btn" :class="{ 'btn-active': bedVisible }"
                                @click="emit('toggleBed')"
                                :title="bedConfig.enabled ? bedConfig.width + '×' + bedConfig.depth + '×' + bedConfig.height + 'mm' : 'Enable print bed in Settings first'">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/><line x1="3" y1="15" x2="21" y2="15"/></svg>
                            Bed
                        </button>
                        <button class="btn" @click="emit('regenerateThumbnail')" title="Regenerate thumbnail">
                            <span v-html="ICONS.refresh"></span>
                        </button>
                        <span v-if="bedVisible" class="bed-status" :class="bedFits ? 'bed-fits' : 'bed-too-large'">
                            {{ bedFits ? 'Fits' : 'Too large' }}
                        </span>
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

                            <!-- License -->
                            <div class="info-section">
                                <div class="info-section-title">License</div>
                                <template v-if="!isEditingLicense">
                                    <div v-if="selectedModel.license"
                                         style="display:flex;align-items:center;gap:6px">
                                        <span style="flex:1;font-size:0.85rem;color:var(--text-secondary)">{{ selectedModel.license }}</span>
                                        <button class="btn-icon" style="width:20px;height:20px;flex-shrink:0"
                                                @click="emit('startEditLicense')" title="Edit license">
                                            <span v-html="ICONS.edit || '&#9998;'"></span>
                                        </button>
                                    </div>
                                    <div v-else @dblclick="emit('startEditLicense')"
                                         style="cursor:pointer;font-size:0.85rem;color:var(--text-secondary);padding:4px 0">
                                        Double-click to add a license…
                                    </div>
                                </template>
                                <template v-else>
                                    <input type="text"
                                           :value="editLicense"
                                           @input="emit('update:editLicense', $event.target.value)"
                                           @blur="emit('saveLicense')"
                                           @keydown.enter="emit('saveLicense')"
                                           @keydown.escape="emit('update:isEditingLicense', false)"
                                           placeholder="e.g. CC-BY 4.0"
                                           style="width:100%;padding:4px 8px;background:var(--bg-input);border:1px solid var(--accent);border-radius:4px;color:var(--text-primary);font-size:0.85rem"
                                           autofocus>
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

                        </template>

                        <!-- ==================== TAGS TAB ==================== -->
                        <template v-if="detailTab === 'tags'">
                            <div class="info-section">
                                <div class="tags-list">
                                    <span v-for="tag in (selectedModel.tags || [])" :key="tag"
                                          class="tag-chip"
                                          :class="{ 'tag-chip-auto': isAutoTag(tag), 'tag-chip-ns': parseTag(tag).namespace }"
                                          :style="tagColorStyle(tag)"
                                          :title="isAutoTag(tag) ? 'Auto-generated tag' : ''">
                                        <button class="tag-filter-btn" @click="emit('filterByTag', tag)" title="Filter by this tag"><span
                                              v-if="parseTag(tag).namespace" class="tag-chip-ns-label">{{ parseTag(tag).namespace }}</span>{{ parseTag(tag).value }}</button>
                                        <button class="tag-remove" @click="emit('removeTag', tag)" title="Remove tag">&times;</button>
                                    </span>
                                    <span v-if="!selectedModel.tags || !selectedModel.tags.length"
                                          class="text-muted text-sm">No tags</span>
                                </div>
                                <button v-if="hasAutoTags" class="btn btn-sm btn-ghost" style="margin-top:6px"
                                        @click="emit('clearAutoTags')" title="Remove auto-generated tags">
                                    Clear auto tags
                                </button>
                                <div class="tag-add-row">
                                    <input type="text"
                                           :value="newTagInput"
                                           list="detail-tag-suggestions"
                                           @input="emit('update:newTagInput', $event.target.value)"
                                           placeholder="Add tag..."
                                           @keydown.enter="emit('addTag')">
                                    <datalist id="detail-tag-suggestions">
                                        <option v-for="t in tagAutocomplete" :key="t" :value="t"></option>
                                    </datalist>
                                    <button class="btn btn-sm btn-primary" @click="emit('addTag')">Add</button>
                                </div>
                                <!-- Tag suggestions -->
                                <div style="margin-top:8px">
                                    <button class="btn btn-sm btn-ghost" @click="emit('fetchTagSuggestions')" :disabled="tagSuggestionsLoading">
                                        Suggest Tags
                                    </button>
                                    <button v-if="aiEnabled" class="btn btn-sm btn-ghost" style="margin-left:6px"
                                            @click="emit('aiTagModel')" :disabled="aiTagging"
                                            title="Suggest tags from the thumbnail with AI">
                                        <span v-html="ICONS.zap"></span>
                                        {{ aiTagging ? 'AI tagging…' : 'AI suggest tags' }}
                                    </button>
                                    <div v-if="tagSuggestions.length > 0" class="tag-suggestions" style="margin-top:6px">
                                        <span v-for="s in tagSuggestions" :key="s" class="tag-chip tag-suggestion"
                                              @click="emit('applyTagSuggestion', s)" style="cursor:pointer">
                                            + {{ s }}
                                        </span>
                                    </div>
                                </div>
                                <!-- Co-occurrence suggestions -->
                                <div v-if="relatedTags.length" style="margin-top:12px">
                                    <div class="info-section-title" style="margin-bottom:6px">Often tagged with</div>
                                    <div class="tag-suggestions">
                                        <span v-for="s in relatedTags" :key="s" class="tag-chip tag-suggestion"
                                              @click="emit('applyTagSuggestion', s)" style="cursor:pointer">
                                            + {{ s }}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </template>

                        <!-- ==================== MORE TAB ==================== -->
                        <template v-if="detailTab === 'more'">
                            <!-- Docs / README / photos -->
                            <div v-if="modelDocs && (modelDocs.readme || (modelDocs.images && modelDocs.images.length) || (modelDocs.docs && modelDocs.docs.length))"
                                 class="info-section">
                                <div class="info-section-title">Docs &amp; Files</div>
                                <div v-if="modelDocs.readme" class="doc-readme">
                                    <div class="doc-readme-name">{{ modelDocs.readme.name }}</div>
                                    <pre class="doc-readme-text">{{ modelDocs.readme.text }}<span v-if="modelDocs.readme.truncated" class="text-muted">
… (truncated)</span></pre>
                                </div>
                                <div v-if="modelDocs.images && modelDocs.images.length" class="doc-image-grid">
                                    <a v-for="img in modelDocs.images" :key="img.name"
                                       :href="docFileUrl(img.name)" target="_blank" rel="noopener"
                                       class="doc-image-thumb" :title="img.name">
                                        <img :src="docFileUrl(img.name)" :alt="img.name" loading="lazy">
                                    </a>
                                </div>
                                <div v-if="docLinks.length" class="doc-file-links">
                                    <a v-for="f in docLinks" :key="f.name"
                                       :href="docFileUrl(f.name)" target="_blank" rel="noopener"
                                       class="doc-file-link">
                                        <span v-html="ICONS.folder"></span> {{ f.name }}
                                    </a>
                                </div>
                            </div>

                            <!-- Print tracking -->
                            <div class="info-section">
                                <div class="info-section-title">Print History</div>
                                <div class="print-track-row">
                                    <div class="print-track-stat">
                                        <strong>{{ selectedModel.print_count || 0 }}</strong>
                                        print{{ (selectedModel.print_count || 0) === 1 ? '' : 's' }}
                                        <span v-if="selectedModel.last_printed_at" class="text-muted text-sm">
                                            · last {{ formatDate(selectedModel.last_printed_at) }}
                                        </span>
                                    </div>
                                    <div class="print-track-actions">
                                        <button class="btn btn-sm btn-primary" @click="emit('logPrint', null)">
                                            <span v-html="ICONS.check"></span> Mark printed
                                        </button>
                                        <button class="btn btn-sm btn-ghost" @click="showPrintForm = !showPrintForm"
                                                :title="showPrintForm ? 'Hide details' : 'Log with details'">Details…</button>
                                        <button v-if="selectedModel.print_count" class="btn btn-sm btn-ghost"
                                                @click="emit('undoPrint')" title="Undo last print">Undo</button>
                                    </div>
                                </div>

                                <!-- Log-with-details form -->
                                <div v-if="showPrintForm" class="print-log-form">
                                    <input class="form-input print-log-qty" type="number" min="1"
                                           v-model.number="printForm.quantity" placeholder="Qty" title="Quantity">
                                    <input class="form-input" v-model="printForm.location" placeholder="Location (e.g. Bin A3)">
                                    <select class="form-input" v-model="printForm.filament_id" title="Filament">
                                        <option :value="null">No filament</option>
                                        <option v-for="f in filaments" :key="f.id" :value="f.id">
                                            {{ [f.brand, f.material, f.color_name].filter(Boolean).join(' ') || ('Spool #' + f.id) }}
                                        </option>
                                    </select>
                                    <input class="form-input print-log-grams" type="number" min="0"
                                           v-model.number="printForm.grams_used" placeholder="g" title="Grams used">
                                    <button class="btn btn-sm btn-primary" @click="submitPrintForm">Log</button>
                                </div>

                                <!-- History list -->
                                <div v-if="printHistory && printHistory.length" class="print-history-list">
                                    <div v-for="p in printHistory" :key="p.id" class="print-history-row">
                                        <span class="print-history-date">{{ formatDate(p.printed_at) }}</span>
                                        <span v-if="p.quantity > 1" class="print-history-qty">×{{ p.quantity }}</span>
                                        <span v-if="p.filament_color_hex" class="filament-swatch print-history-swatch"
                                              :style="{ background: p.filament_color_hex }"></span>
                                        <span v-if="p.filament_brand || p.filament_material" class="print-history-fil">
                                            {{ [p.filament_brand, p.filament_material].filter(Boolean).join(' ') }}
                                        </span>
                                        <span v-if="p.location" class="print-history-loc">{{ p.location }}</span>
                                        <span v-if="p.status && p.status !== 'kept'" class="print-history-status">{{ p.status }}</span>
                                        <button class="btn-icon print-history-del" @click="emit('deletePrint', p.id)"
                                                title="Delete entry">&times;</button>
                                    </div>
                                </div>
                            </div>

                            <!-- Variants -->
                            <div class="info-section">
                                <div class="info-section-title" style="display:flex;align-items:center;justify-content:space-between">
                                    Variants
                                    <button class="btn-icon" style="width:20px;height:20px"
                                            @click="emit('update:variantPickerOpen', !variantPickerOpen)"
                                            :title="variantPickerOpen ? 'Close' : 'Link a variant'">
                                        <span v-html="variantPickerOpen ? ICONS.close : ICONS.plus"></span>
                                    </button>
                                </div>

                                <!-- Linked variants -->
                                <div v-if="selectedModel.variants && selectedModel.variants.length"
                                     class="related-models-grid">
                                    <div v-for="v in selectedModel.variants" :key="v.id"
                                         class="related-model-item variant-item"
                                         @click="emit('openVariant', v.id)" :title="v.name">
                                        <button class="variant-unlink" title="Unlink variant"
                                                @click.stop="emit('unlinkVariant', v.id)">&times;</button>
                                        <img v-if="v.thumbnail_path" :src="'/thumbnails/' + v.thumbnail_path"
                                             class="related-model-thumb" loading="lazy" alt=""
                                             @error="$event.target.style.display='none'; $event.target.nextElementSibling && ($event.target.nextElementSibling.style.display='flex')">
                                        <div :style="v.thumbnail_path ? {display:'none'} : {}"
                                             class="related-model-thumb related-model-thumb-placeholder">
                                            <span v-html="ICONS.cube"></span>
                                        </div>
                                        <div class="related-model-name">{{ v.name }}</div>
                                    </div>
                                </div>
                                <div v-else-if="!variantPickerOpen" class="text-muted text-sm">
                                    No variants linked. Use + to link a related model.
                                </div>

                                <!-- Link picker -->
                                <div v-if="variantPickerOpen" class="variant-picker">
                                    <input type="text" class="variant-search-input"
                                           :value="variantQuery" placeholder="Search models to link…"
                                           @input="emit('update:variantQuery', $event.target.value); emit('searchVariants', $event.target.value)">
                                    <div v-if="variantSearching" class="text-muted text-sm" style="padding:6px 2px">Searching…</div>
                                    <div v-else-if="variantCandidates.length" class="variant-candidates">
                                        <button v-for="c in variantCandidates" :key="c.id"
                                                class="variant-candidate" @click="emit('linkVariant', c.id)">
                                            <img v-if="c.thumbnail_path" :src="'/thumbnails/' + c.thumbnail_path"
                                                 class="variant-candidate-thumb" loading="lazy" alt=""
                                                 @error="$event.target.style.display='none'">
                                            <span class="variant-candidate-name">{{ c.name }}</span>
                                            <span class="format-badge" :class="formatClass(c.file_format)">{{ c.file_format }}</span>
                                        </button>
                                    </div>
                                    <div v-else-if="variantQuery" class="text-muted text-sm" style="padding:6px 2px">
                                        No matching models.
                                    </div>
                                </div>
                            </div>

                            <!-- Duplicate Warning -->
                            <div v-if="selectedModel.file_hash" class="duplicate-warning" style="display:none">
                                <span v-html="ICONS.warning"></span>
                                <span>This file has duplicates in the library.</span>
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
                                    <span v-for="col in (selectedModel.collections || [])" :key="col.name"
                                          class="tag-chip" :style="{ background: (col.color || '#666') + '22', color: col.color || '#666', border: '1px solid ' + (col.color || '#666') + '44' }">
                                        <span class="collection-dot" :style="{ background: col.color || '#666' }" style="width:8px;height:8px;margin-right:4px"></span>
                                        <span v-if="col.is_smart" v-html="ICONS.zap" style="width:10px;height:10px;opacity:0.7;margin-right:2px"></span>
                                        {{ col.name }}
                                        <button v-if="!col.is_smart" class="tag-remove" @click="emit('removeModelFromCollection', col.id, selectedModel.id)" title="Remove from collection">&times;</button>
                                    </span>
                                    <span v-if="!selectedModel.collections || !selectedModel.collections.length"
                                          class="text-muted text-sm">No collections</span>
                                </div>
                            </div>

                            <!-- Related Models -->
                            <div v-if="relatedModels.length > 0" class="info-section">
                                <div class="info-section-title">
                                    Related Models
                                    <span class="text-muted" style="font-weight:normal;font-size:0.75rem;margin-left:6px">
                                        {{ relatedModels.length }} in same {{ selectedModel.zip_path ? 'zip' : 'folder' }}
                                    </span>
                                </div>
                                <div class="related-models-grid">
                                    <div v-for="rm in relatedModels" :key="rm.id"
                                         class="related-model-item"
                                         @click="emit('openRelatedModel', rm.id)"
                                         :title="rm.name">
                                        <img v-if="rm.thumbnail_path"
                                             :src="'/thumbnails/' + rm.thumbnail_path"
                                             class="related-model-thumb"
                                             loading="lazy" alt=""
                                             @error="$event.target.style.display='none'; $event.target.nextElementSibling && ($event.target.nextElementSibling.style.display='flex')">
                                        <div :style="rm.thumbnail_path ? {display:'none'} : {}"
                                             class="related-model-thumb related-model-thumb-placeholder">
                                            <span v-html="ICONS.cube"></span>
                                        </div>
                                        <div class="related-model-name">{{ rm.name }}</div>
                                    </div>
                                </div>
                            </div>
                        </template>

                    </div>

                    <!-- Pinned actions bar -->
                    <div class="detail-actions-pinned">
                        <a v-if="preferredSlicer !== 'none' && selectedModel.file_format && SLICER_FORMATS.includes(selectedModel.file_format.toLowerCase().replace('.', ''))"
                           class="btn btn-primary"
                           :href="slicerHref(selectedModel)"
                           :title="'Open in ' + (SLICER_LABELS[preferredSlicer] || preferredSlicer)">
                            <span v-html="ICONS.slicer"></span>
                            Slicer
                        </a>
                        <a class="btn btn-secondary"
                           :href="'/api/models/' + selectedModel.id + '/download'"
                           download>
                            <span v-html="ICONS.download"></span>
                            Download
                        </a>
                        <button class="btn btn-danger" @click="emit('deleteModel', selectedModel)">
                            <span v-html="ICONS.trash"></span>
                            Delete
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
