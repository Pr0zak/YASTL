<script setup>
/**
 * DetailPanel - Model detail overlay with 3D viewer and tabbed info panel.
 * Tabs: Info (description, source, file summary, categories), Tags, More (collections, duplicates).
 */
import { computed, ref, reactive, watch, onBeforeUnmount } from 'vue';
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
    viewerRenderMode: { type: String, default: 'shaded' },
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
    modelPlates: { type: Array, default: () => [] },
    activePlate: { type: Number, default: null },
    aiEnabled: { type: Boolean, default: false },
    aiTagging: { type: Boolean, default: false },
    relatedModels: { type: Array, default: () => [] },
    variantCandidates: { type: Array, default: () => [] },
    variantPickerOpen: { type: Boolean, default: false },
    variantQuery: { type: String, default: '' },
    variantSearching: { type: Boolean, default: false },
    detailTab: { type: String, default: 'overview' },
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
    'setRenderMode',
    'toggleClipping',
    'setClipPosition',
    'toggleOrtho',
    'toggleMeasuring',
    'logPrint',
    'undoPrint',
    'deletePrint',
    'addToQueue',
    'selectPlate',
    'clearAutoTags',
    'aiTagModel',
]);

// Re-arm the tap-to-interact gate each time a different model opens on touch.
watch(() => props.selectedModel?.id, () => {
    if (isCoarsePointer) viewerInteractive.value = false;
});

// Heavy sections start collapsed. The panel used to render every one of them
// inline, which is what made the old More tab a 1358px wall of unrelated
// material; a count in the header tells you whether opening one is worth it.
const openSections = reactive({ docs: false, plates: false, variants: false, related: false });
function toggleSection(key) {
    openSections[key] = !openSections[key];
}
// Collapse everything again when a different model opens, so a section left
// open does not silently expand on the next twenty models.
watch(() => props.selectedModel?.id, () => {
    for (const k of Object.keys(openSections)) openSections[k] = false;
    overflowOpen.value = false;
    cameraView.value = 'iso';
});

// Situational viewer controls live behind one overflow button so the toolbar
// fits a phone. Nine controls in a row needed 758px of a 394px viewport.
const overflowOpen = ref(false);
const overflowEl = ref(null);
// Which camera angle the select is showing. Reset View and a new model both
// put the camera back to isometric, so the control follows.
const cameraView = ref('iso');

function onOverflowOutside(e) {
    if (overflowEl.value && !overflowEl.value.contains(e.target)) overflowOpen.value = false;
}
// Escape closes the menu rather than the panel — the panel's own Escape is the
// global handler, and it would otherwise tear everything down from one keypress.
function onOverflowKey(e) {
    if (e.key === 'Escape' && overflowOpen.value) {
        e.stopPropagation();
        overflowOpen.value = false;
    }
}
watch(overflowOpen, (open) => {
    const m = open ? 'addEventListener' : 'removeEventListener';
    document[m]('pointerdown', onOverflowOutside, true);
    document[m]('keydown', onOverflowKey, true);
});
onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', onOverflowOutside, true);
    document.removeEventListener('keydown', onOverflowKey, true);
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

const docsCount = computed(() => {
    const d = props.modelDocs;
    if (!d) return '';
    const n = (d.images?.length || 0) + (d.docs?.length || 0);
    return n || '';
});

// Badge on the Organise tab: how much filing this model already carries.
const organiseCount = computed(() => {
    const m = props.selectedModel;
    if (!m) return 0;
    return (m.tags?.length || 0) + (m.collections?.length || 0);
});

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
// Only OrcaSlicer and Cura accept a self-hosted URL via their URL scheme.
// PrusaSlicer & Bambu Studio hard-code a printables.com / makerworld.com
// whitelist and silently reject other hosts; SuperSlicer has no scheme — so
// those fall back to a plain download the user opens in their slicer.
const SCHEME_SLICERS = {
    orcaslicer: 'orcaslicer://open?file=',
    cura: 'cura://open?file=',
};
const SLICER_LABELS = {
    bambustudio: 'Bambu Studio',
    orcaslicer: 'OrcaSlicer',
    prusaslicer: 'PrusaSlicer',
    cura: 'Cura',
    superslicer: 'SuperSlicer',
};
const baseUrl = globalThis.location?.origin || '';

function _slicerDownloadUrl(model) {
    // The URL must end in the real extension so the slicer/OS recognises it.
    const ext = (model.file_format || '').toLowerCase().replace('.', '');
    let stem = (model.name || 'model').replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '') || 'model';
    if (stem.toLowerCase().endsWith('.' + ext)) {
        stem = stem.slice(0, -(ext.length + 1));
    }
    return `${baseUrl}/api/models/${model.id}/download/${stem}.${ext}`;
}

const slicerAction = computed(() => {
    const slicer = props.preferredSlicer;
    const model = props.selectedModel;
    if (slicer === 'none' || !model) return null;
    const ext = (model.file_format || '').toLowerCase().replace('.', '');
    if (!SLICER_FORMATS.includes(ext)) return null;
    const url = _slicerDownloadUrl(model);
    const label = SLICER_LABELS[slicer] || slicer;
    if (SCHEME_SLICERS[slicer]) {
        return { mode: 'scheme', href: SCHEME_SLICERS[slicer] + encodeURIComponent(url), label, verb: 'Open in' };
    }
    return { mode: 'download', href: url, label, verb: 'Download for' };
});

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
            <!--
                Header. The old row spent ~296px of a 390px screen on chrome —
                two 40px chevrons, a counter, two icon buttons and a close —
                which left the model name so little room it was hard-clipped
                mid-word with no ellipsis, and pushed the rename control off
                the edge entirely. The name now leads, with the facts that
                identify it underneath, and the paging controls collapse into
                one pill.
            -->
            <div class="detail-header">
                <div class="detail-title">
                    <template v-if="!isEditingName">
                        <div class="detail-title-block">
                            <span class="detail-title-text" @click="emit('startEditName')" title="Rename">
                                {{ selectedModel.name }}
                            </span>
                            <div class="detail-title-meta">
                                <span class="format-badge" :class="formatClass(selectedModel.file_format)">{{ selectedModel.file_format }}</span>
                                <span>{{ formatFileSize(selectedModel.file_size) }}</span>
                                <span v-if="selectedModel.dimensions_x">
                                    · {{ Math.round(selectedModel.dimensions_x) }} × {{ Math.round(selectedModel.dimensions_y) }} × {{ Math.round(selectedModel.dimensions_z) }} mm
                                </span>
                            </div>
                        </div>
                        <button class="btn-icon btn-edit-inline" @click="emit('startEditName')" title="Rename model">
                            <span v-html="ICONS.edit"></span>
                        </button>
                    </template>
                    <template v-else>
                        <input type="text"
                               :value="editName"
                               @input="emit('update:editName', $event.target.value)"
                               @blur="emit('saveName')"
                               @keydown.enter="emit('saveName')"
                               @keydown.escape.stop="emit('update:isEditingName', false)"
                               @vue:mounted="$event.el.focus()"
                               style="flex:1;min-width:0;padding:4px 8px;background:var(--bg-input);border:1px solid var(--accent);border-radius:4px;color:var(--text-primary);font-size:1.1rem;font-weight:600">
                    </template>
                </div>

                <button class="btn btn-sm btn-ghost detail-fav" :class="{ 'text-danger': selectedModel.is_favorite }"
                        @click="emit('toggleFavorite', selectedModel, $event)" title="Toggle favourite">
                    <span v-html="selectedModel.is_favorite ? ICONS.heartFilled : ICONS.heart"></span>
                </button>

                <div class="detail-nav" v-if="navTotal > 1">
                    <button class="btn-icon" :disabled="navIndex <= 0"
                            @click="emit('navigate', -1)" :title="'Previous model (←) · ' + (navIndex + 1) + ' of ' + navTotal">
                        <span v-html="ICONS.chevron" style="transform:rotate(180deg);display:inline-flex"></span>
                    </button>
                    <button class="btn-icon" :disabled="navIndex >= navTotal - 1"
                            @click="emit('navigate', 1)" :title="'Next model (→) · ' + (navIndex + 1) + ' of ' + navTotal">
                        <span v-html="ICONS.chevron" style="display:inline-flex"></span>
                    </button>
                </div>

                <button class="close-btn" @click="emit('close')" title="Close">&times;</button>
            </div>

            <!-- Content: Viewer + Info -->
            <div class="detail-content">
                <!-- 3D Viewer -->
                <div class="detail-viewer">
                    <!-- Multi-plate selector: swap the viewer between the whole
                         project and a single build plate. -->
                    <div v-if="modelPlates.length > 1" class="viewer-plate-bar">
                        <button class="viewer-plate-chip" :class="{ active: activePlate === null }"
                                @click="emit('selectPlate', null)">Full project</button>
                        <button v-for="pl in modelPlates" :key="pl.index"
                                class="viewer-plate-chip" :class="{ active: activePlate === pl.index }"
                                @click="emit('selectPlate', pl.index)"
                                :title="pl.name || ('Plate ' + (pl.index + 1))">
                            {{ pl.index + 1 }}
                        </button>
                    </div>
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
                    <!--
                        Viewer toolbar: three verbs plus an overflow.

                        The previous row put nine controls at equal weight in
                        758px of width against a 394px phone viewport, with the
                        scrollbar hidden, so half of them were invisible and
                        unreachable. It also mixed four labelling conventions —
                        "Reset View" named an action, "Persp" named the current
                        state, "Measure" named the mode you would enter, and the
                        circular arrow had no label at all. What stays out here
                        is what you touch on nearly every model; what moves into
                        the menu is situational.
                    -->
                    <div class="viewer-toolbar">
                        <button class="btn viewer-tool" @click="cameraView = 'iso'; emit('resetView')"
                                title="Point the camera back at the model">
                            <span v-html="ICONS.refresh"></span> Reset
                        </button>

                        <select class="btn viewer-tool viewer-view-select" title="Camera angle"
                                :value="cameraView"
                                @change="cameraView = $event.target.value; emit('setView', cameraView)">
                            <option value="iso">Isometric</option>
                            <option value="front">Front</option>
                            <option value="back">Back</option>
                            <option value="left">Left</option>
                            <option value="right">Right</option>
                            <option value="top">Top</option>
                            <option value="bottom">Bottom</option>
                        </select>

                        <!-- Projection and shading are one question: how is this drawn. -->
                        <select class="btn viewer-tool viewer-view-select" title="How the model is drawn"
                                :class="{ 'btn-active': viewerRenderMode !== 'shaded' || viewerOrtho }"
                                :value="viewerRenderMode"
                                @change="emit('setRenderMode', $event.target.value)">
                            <option value="shaded">Shaded</option>
                            <option value="wireframe">Wireframe</option>
                            <option value="normals">Normals</option>
                            <option value="xray">X-ray</option>
                        </select>

                        <!-- Shown from 769px up, where the row has room; the
                             same three live in the overflow menu below 769px. -->
                        <button class="btn viewer-tool viewer-tool-wide" :class="{ 'btn-active': viewerMeasuring }"
                                @click="emit('toggleMeasuring')"
                                title="Tap two points on the model for a distance">
                            {{ viewerMeasuredMm != null ? viewerMeasuredMm.toFixed(1) + ' mm' : 'Measure' }}
                        </button>
                        <button class="btn viewer-tool viewer-tool-wide" :class="{ 'btn-active': viewerClipping }"
                                @click="emit('toggleClipping')"
                                title="Slice the model open to inspect the interior">
                            Slice
                        </button>
                        <input v-if="viewerClipping" type="range" min="0" max="1" step="0.01"
                               class="viewer-clip-slider viewer-tool-wide" :value="viewerClipPos"
                               @input="emit('setClipPosition', parseFloat($event.target.value))"
                               title="Cross-section height" aria-label="Cross-section height">
                        <button class="btn viewer-tool viewer-tool-wide" :class="{ 'btn-active': bedVisible }"
                                @click="emit('toggleBed')"
                                :title="bedConfig.enabled ? bedConfig.width + '×' + bedConfig.depth + '×' + bedConfig.height + 'mm' : 'Enable the print bed in Settings first'">
                            Bed
                        </button>

                        <div class="viewer-overflow" ref="overflowEl">
                            <button class="btn viewer-tool viewer-overflow-btn"
                                    :class="{ 'btn-active': overflowOpen || viewerMeasuring || viewerClipping || bedVisible }"
                                    @click="overflowOpen = !overflowOpen"
                                    :aria-expanded="String(overflowOpen)" title="More viewer tools">
                                <span v-html="ICONS.dots || '&#8943;'"></span>
                            </button>

                            <div v-if="overflowOpen" class="viewer-overflow-menu">
                                <button class="viewer-overflow-item" :class="{ active: viewerOrtho }"
                                        @click="emit('toggleOrtho')">
                                    <span>Flat (orthographic) view</span>
                                    <span class="viewer-overflow-state">{{ viewerOrtho ? 'On' : 'Off' }}</span>
                                </button>

                                <button class="viewer-overflow-item viewer-overflow-narrow" :class="{ active: viewerMeasuring }"
                                        @click="emit('toggleMeasuring')">
                                    <span>Measure a distance</span>
                                    <span class="viewer-overflow-state">
                                        {{ viewerMeasuredMm != null ? viewerMeasuredMm.toFixed(1) + ' mm' : (viewerMeasuring ? 'Tap two points' : '') }}
                                    </span>
                                </button>

                                <button class="viewer-overflow-item viewer-overflow-narrow" :class="{ active: viewerClipping }"
                                        @click="emit('toggleClipping')">
                                    <span>Slice it open</span>
                                    <span class="viewer-overflow-state">{{ viewerClipping ? 'On' : 'Off' }}</span>
                                </button>
                                <div v-if="viewerClipping" class="viewer-overflow-slider viewer-overflow-narrow">
                                    <input type="range" min="0" max="1" step="0.01"
                                           class="viewer-clip-slider" :value="viewerClipPos"
                                           @input="emit('setClipPosition', parseFloat($event.target.value))"
                                           title="Cross-section height"
                                           aria-label="Cross-section height">
                                </div>

                                <button class="viewer-overflow-item viewer-overflow-narrow" :class="{ active: bedVisible }"
                                        @click="emit('toggleBed')"
                                        :title="bedConfig.enabled ? bedConfig.width + '×' + bedConfig.depth + '×' + bedConfig.height + 'mm' : 'Enable the print bed in Settings first'">
                                    <span>Show my print bed</span>
                                    <span class="viewer-overflow-state"
                                          :class="bedVisible ? (bedFits ? 'text-success' : 'text-danger') : ''">
                                        {{ bedVisible ? (bedFits ? 'Fits' : 'Too large') : (bedConfig.enabled ? 'Off' : 'Not set up') }}
                                    </span>
                                </button>

                                <button v-if="viewerDecimated && !viewerLoading" class="viewer-overflow-item"
                                        @click="emit('loadFullResolution')">
                                    <span>Load full detail</span>
                                    <span class="viewer-overflow-state">simplified now</span>
                                </button>

                                <!-- This never touched the 3D view; it redraws the grid card. -->
                                <button class="viewer-overflow-item" @click="emit('regenerateThumbnail')">
                                    <span>Redo the card thumbnail</span>
                                </button>
                            </div>
                        </div>

                        <!-- The measurement has to be readable while the menu is
                             closed — taking it is what closes the menu. -->
                        <span v-if="viewerMeasuredMm != null" class="bed-status viewer-measure-readout">
                            {{ viewerMeasuredMm.toFixed(1) }} mm
                        </span>

                        <!-- Bed verdict stays visible on the toolbar: it answers
                             "will this print" without opening anything. -->
                        <span v-if="bedVisible" class="bed-status" :class="bedFits ? 'bed-fits' : 'bed-too-large'">
                            {{ bedFits ? 'Fits' : 'Too large' }}
                        </span>
                    </div>
                </div>

                <!-- Info Panel (tabbed) -->
                <div class="detail-info">
                    <!-- Tab bar -->
                    <div class="detail-tabs">
                        <button class="detail-tab" :class="{ active: detailTab === 'overview' }"
                                @click="emit('update:detailTab', 'overview')">Overview</button>
                        <button class="detail-tab" :class="{ active: detailTab === 'organise' }"
                                @click="emit('update:detailTab', 'organise')">
                            Organise
                            <span v-if="organiseCount" class="detail-tab-count">{{ organiseCount }}</span>
                        </button>
                    </div>

                    <!-- Tab content (scrollable) -->
                    <div class="detail-tab-content">

                        <!-- ==================== OVERVIEW ==================== -->
                        <template v-if="detailTab === 'overview'">
                            <!-- Size first: the fact that decides whether this gets printed. -->
                            <div class="dims-row" v-if="selectedModel.dimensions_x">
                                <div class="dim-card">
                                    <div class="dim-label">Width</div>
                                    <div class="dim-value">{{ Math.round(selectedModel.dimensions_x) }}<span>mm</span></div>
                                </div>
                                <div class="dim-card">
                                    <div class="dim-label">Depth</div>
                                    <div class="dim-value">{{ Math.round(selectedModel.dimensions_y) }}<span>mm</span></div>
                                </div>
                                <div class="dim-card">
                                    <div class="dim-label">Height</div>
                                    <div class="dim-value">{{ Math.round(selectedModel.dimensions_z) }}<span>mm</span></div>
                                </div>
                            </div>

                            <!-- Description -->
                            <div class="info-section">
                                <div class="info-section-title">Description</div>
                                <div v-if="!isEditingDesc && selectedModel.description"
                                     @click="emit('startEditDesc')"
                                     class="editable-value"
                                     title="Edit description">
                                    {{ selectedModel.description }}
                                </div>
                                <button v-else-if="!isEditingDesc" class="field-add" @click="emit('startEditDesc')">
                                    <span v-html="ICONS.edit"></span> Add a description
                                </button>
                                <div v-else class="editable-field">
                                    <textarea :value="editDesc"
                                              @input="emit('update:editDesc', $event.target.value)"
                                              rows="3"
                                              @blur="emit('saveDesc')"
                                              @keydown.escape.stop="emit('update:isEditingDesc', false)"
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
                                    <button v-else class="field-add" @click="emit('startEditSourceUrl')">
                                        <span v-html="ICONS.edit"></span> Add a source URL
                                    </button>
                                </template>
                                <template v-else>
                                    <div class="editable-field">
                                        <input type="url"
                                               :value="editSourceUrl"
                                               @input="emit('update:editSourceUrl', $event.target.value)"
                                               @blur="emit('saveSourceUrl')"
                                               @keydown.enter="emit('saveSourceUrl')"
                                               @keydown.escape.stop="emit('update:isEditingSourceUrl', false)"
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
                                    <button v-else class="field-add" @click="emit('startEditLicense')">
                                        <span v-html="ICONS.edit"></span> Add a licence
                                    </button>
                                </template>
                                <template v-else>
                                    <input type="text"
                                           :value="editLicense"
                                           @input="emit('update:editLicense', $event.target.value)"
                                           @blur="emit('saveLicense')"
                                           @keydown.enter="emit('saveLicense')"
                                           @keydown.escape.stop="emit('update:isEditingLicense', false)"
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


                            <div class="disclosure" v-if="modelDocs && (modelDocs.readme || (modelDocs.images && modelDocs.images.length) || (modelDocs.docs && modelDocs.docs.length))">
                                <button class="disclosure-head" @click="toggleSection('docs')"
                                        :aria-expanded="String(!!openSections.docs)">
                                    <span class="disclosure-label">Original files</span>
                                    <span class="disclosure-count">{{ docsCount }}</span>
                                    <span class="disclosure-chevron" :class="{ open: openSections.docs }" v-html="ICONS.chevron"></span>
                                </button>
                                <div v-if="openSections.docs" class="disclosure-body">
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
                                </div>
                            </div>

                            <div class="disclosure" v-if="modelPlates.length > 1">
                                <button class="disclosure-head" @click="toggleSection('plates')"
                                        :aria-expanded="String(!!openSections.plates)">
                                    <span class="disclosure-label">Build plates</span>
                                    <span class="disclosure-count">{{ modelPlates.length }}</span>
                                    <span class="disclosure-chevron" :class="{ open: openSections.plates }" v-html="ICONS.chevron"></span>
                                </button>
                                <div v-if="openSections.plates" class="disclosure-body">
                            <!-- Multi-plate 3MF (Bambu/Orca project) -->
                            <div v-if="modelPlates.length > 1" class="info-section">
                                <div class="info-section-title">Plates ({{ modelPlates.length }})</div>
                                <div class="plate-grid">
                                    <div v-for="pl in modelPlates" :key="pl.index" class="plate-cell"
                                         :class="{ active: activePlate === pl.index }"
                                         @click="emit('selectPlate', pl.index)"
                                         title="Show this plate in the viewer">
                                        <img v-if="pl.has_thumbnail"
                                             :src="`/api/models/${selectedModel.id}/plates/${pl.index}/thumbnail`"
                                             class="plate-thumb" alt="" loading="lazy">
                                        <div v-else class="plate-thumb plate-thumb-empty"></div>
                                        <div class="plate-label" :title="pl.name || ('Plate ' + (pl.index + 1))">
                                            {{ pl.name || ('Plate ' + (pl.index + 1)) }}
                                            <span v-if="pl.object_ids && pl.object_ids.length" class="text-muted">· {{ pl.object_ids.length }} obj</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                                </div>
                            </div>

                            <div class="disclosure">
                                <button class="disclosure-head" @click="toggleSection('variants')"
                                        :aria-expanded="String(!!openSections.variants)">
                                    <span class="disclosure-label">Variants</span>
                                    <span class="disclosure-count">{{ (selectedModel.variants || []).length || '' }}</span>
                                    <span class="disclosure-chevron" :class="{ open: openSections.variants }" v-html="ICONS.chevron"></span>
                                </button>
                                <div v-if="openSections.variants" class="disclosure-body">
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
                                </div>
                            </div>

                            <div class="disclosure" v-if="relatedModels.length > 0">
                                <button class="disclosure-head" @click="toggleSection('related')"
                                        :aria-expanded="String(!!openSections.related)">
                                    <span class="disclosure-label">Other models here</span>
                                    <span class="disclosure-count">{{ relatedModels.length }}</span>
                                    <span class="disclosure-chevron" :class="{ open: openSections.related }" v-html="ICONS.chevron"></span>
                                </button>
                                <div v-if="openSections.related" class="disclosure-body">
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
                                </div>
                            </div>
                        </template>

                        <!-- ==================== ORGANISE ==================== -->
                        <template v-if="detailTab === 'organise'">
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
                                        <button class="btn btn-sm btn-ghost" @click="emit('addToQueue')"
                                                title="Add to print queue">
                                            <span v-html="ICONS.queue"></span> Queue
                                        </button>
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
                        </template>

                    </div>

                    <!-- Pinned actions bar -->
                    <div class="detail-actions-pinned">
                        <a v-if="slicerAction"
                           class="btn btn-primary"
                           :href="slicerAction.href"
                           :download="slicerAction.mode === 'download' ? '' : undefined"
                           :title="slicerAction.verb + ' ' + slicerAction.label">
                            <span v-html="ICONS.slicer"></span>
                            {{ slicerAction.mode === 'scheme' ? 'Open in slicer' : 'Download for slicer' }}
                        </a>
                        <a class="btn btn-secondary"
                           :href="'/api/models/' + selectedModel.id + '/download'"
                           download title="Download the file" aria-label="Download the file">
                            <span v-html="ICONS.download"></span>
                            <span class="btn-label">Download</span>
                        </a>
                        <button class="btn btn-danger" @click="emit('deleteModel', selectedModel)"
                                title="Delete this model" aria-label="Delete this model">
                            <span v-html="ICONS.trash"></span>
                            <span class="btn-label">Delete</span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
