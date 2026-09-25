<script setup>
/**
 * SettingsModal - Settings panel: Libraries, Appearance, Printing, Maintenance, Advanced.
 */
import { computed, ref, watch, onBeforeUnmount } from 'vue';
import { ICONS } from '../icons.js';
import { BED_PRESETS } from '../composables/useSettings.js';

const showAdvanced = ref(true);


const showConnectSteps = ref(false);
const addFormOpen = ref(false);

// The address to paste into the extension is simply where this page is served
// from, so show it rather than asking the user to work it out.
const serverOrigin = window.location.origin;

const props = defineProps({
    showSettings: { type: Boolean, default: false },
    libraries: { type: Array, default: () => [] },
    newLibName: { type: String, default: '' },
    newLibPath: { type: String, default: '' },
    addingLibrary: { type: Boolean, default: false },
    thumbnailMode: { type: String, default: 'solid' },
    previewDetail: { type: String, default: 'detailed' },
    regeneratingThumbnails: { type: Boolean, default: false },
    regenProgress: { type: Object, default: () => ({ completed: 0, total: 0 }) },
    generatingPreviews: { type: Boolean, default: false },
    previewProgress: { type: Object, default: () => ({ completed: 0, total: 0, generated: 0 }) },
    autoTagging: { type: Boolean, default: false },
    autoTagProgress: { type: Object, default: () => ({ completed: 0, total: 0, tags_added: 0 }) },
    extractingMetadata: { type: Boolean, default: false },
    metadataProgress: { type: Object, default: () => ({ completed: 0, total: 0, updated: 0 }) },
    updateInfo: { type: Object, required: true },
    scanStatus: { type: Object, required: true },
    importCredentials: { type: Object, default: () => ({}) },
    credentialInputs: { type: Object, default: () => ({}) },
    bedConfig: { type: Object, default: () => ({ enabled: false, shape: 'rectangular', width: 256, depth: 256, height: 256 }) },
    bedPreset: { type: String, default: 'Custom' },
    colorTheme: { type: String, default: 'default' },
    favoritesFirst: { type: Boolean, default: false },
    collectionCardTint: { type: Boolean, default: false },
    preferredSlicer: { type: String, default: 'none' },
    autoTagOnScan: { type: Boolean, default: false },
    scanIntervalMinutes: { type: String, default: '0' },
    webhookUrl: { type: String, default: '' },
    connect: { type: Object, default: () => ({ enabled: false, token: '' }) },
    connectFullToken: { type: String, default: '' },
    ai: { type: Object, default: () => ({}) },
    aiTesting: { type: Boolean, default: false },
    aiTestResult: { type: Object, default: null },
    buildingEmbeddings: { type: Boolean, default: false },
    embedProgress: { type: Object, default: () => ({ running: false, total: 0, completed: 0, in_memory: 0 }) },
    aiTaggingAll: { type: Boolean, default: false },
    aiTagProgress: { type: Object, default: () => ({ running: false, total: 0, completed: 0, tags_added: 0 }) },
    lastSavedAt: { type: Number, default: 0 },
});

// Steps start open until a token exists, since that is the first-run case, and
// collapse to a single line once Connect is set up.
const stepsOpen = computed(() => showConnectSteps.value || !props.connect?.token);

const emit = defineEmits([
    'close',
    'update:newLibName',
    'update:newLibPath',
    'addLibrary',
    'deleteLibrary',
    'triggerScan',
    'scanLibrary',
    'setThumbnailMode',
    'setPreviewDetail',
    'regenerateThumbnails',
    'generatePreviews',
    'autoTagAll',
    'extractMetadata',
    'cleanupTags',
    'checkForUpdates',
    'applyUpdate',
    'saveImportCredential',
    'deleteImportCredential',
    'updateCredentialInput',
    'setBedPreset',
    'updateBedConfig',
    'saveBedSettings',
    'setColorTheme',
    'toggleFavoritesFirst',
    'toggleCollectionCardTint',
    'setPreferredSlicer',
    'toggleAutoTagOnScan',
    'setScanInterval',
    'setWebhookUrl',
    'testWebhook',
    'saveConnectSettings',
    'rotateConnectToken',
    'copyText',
    'saveAiSettings',
    'testAi',
    'buildEmbeddings',
    'aiAutoTagAll',
]);

/* ---- Page navigation ----
   Settings was one modal scroll of eight sections, about four and a half
   phone screens, with no way to jump between them. It is now a page: a
   section list on the left (on a phone, a list you tap into and back out
   of), one section shown at a time. */
const SECTIONS = [
    { key: 'libraries', label: 'Libraries', icon: 'folder', hint: 'Folders YASTL scans' },
    { key: 'appearance', label: 'Appearance', icon: 'sun', hint: 'Theme, thumbnails, grid' },
    { key: 'printing', label: 'Printing', icon: 'slicer', hint: 'Slicer and print bed' },
    { key: 'maintenance', label: 'Maintenance', icon: 'wrench', hint: 'Scans, webhooks, bulk jobs' },
    { key: 'ai', label: 'AI', icon: 'zap', hint: 'Optional, your own key' },
    { key: 'extension', label: 'Browser extension', icon: 'link', hint: 'YASTL Connect' },
    { key: 'backup', label: 'Backup and sites', icon: 'database', hint: 'Export, site logins' },
    { key: 'updates', label: 'Updates', icon: 'refresh', hint: 'Check and install' },
];
const LAST_KEY = 'yastl-settings-section';
let initial = 'libraries';
try { initial = localStorage.getItem(LAST_KEY) || 'libraries'; } catch { /* storage unavailable */ }
const current = ref(SECTIONS.some((x) => x.key === initial) ? initial : 'libraries');
/** Phones show either the list or one section. */
const mobileShowing = ref(false);
function openSection(key) {
    current.value = key;
    mobileShowing.value = true;
    try { localStorage.setItem(LAST_KEY, key); } catch { /* storage unavailable */ }
}
function show(key) {
    return current.value === key;
}
const currentLabel = computed(() => SECTIONS.find((x) => x.key === current.value)?.label || 'Settings');

/* ---- "Saved" tick ---- */
const savedVisible = ref(false);
let savedTimer = null;
watch(() => props.lastSavedAt, (t) => {
    if (!t) return;
    savedVisible.value = true;
    clearTimeout(savedTimer);
    savedTimer = setTimeout(() => { savedVisible.value = false; }, 2200);
});

/* Bed and AI fields save themselves shortly after a change, like every
   other setting here; they used to need their own Save buttons. */
let bedTimer = null;
let aiTimer = null;
function autosaveBed() {
    clearTimeout(bedTimer);
    bedTimer = setTimeout(() => emit('saveBedSettings'), 500);
}
function autosaveAi() {
    clearTimeout(aiTimer);
    aiTimer = setTimeout(() => emit('saveAiSettings'), 500);
}
onBeforeUnmount(() => { clearTimeout(savedTimer); clearTimeout(bedTimer); clearTimeout(aiTimer); });

watch(() => props.showSettings, (open) => { if (open) { mobileShowing.value = false; addFormOpen.value = false; } });
// Close the add form once the new library appears.
watch(() => props.libraries.length, (n, old) => { if (n > old) addFormOpen.value = false; });

function onPageKey(e) {
    if (e.key === 'Escape' && mobileShowing.value && window.matchMedia('(max-width: 768px)').matches) {
        e.stopImmediatePropagation();
        mobileShowing.value = false;
    }
}
watch(() => props.showSettings, (open) => {
    document[open ? 'addEventListener' : 'removeEventListener']('keydown', onPageKey, true);
});

function timeAgo(dateStr) {
    if (!dateStr) return 'Never scanned';
    const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}
</script>

<template>
    <!--
        eslint-disable vue/no-mutating-props

        `ai` and `bedConfig` are not value props — they are the reactive
        settings objects created by useSettings(), handed to this modal because
        it is their editor. Binding v-model straight to their fields is the
        intended design, the same way a store slice is edited in place. The rule
        cannot tell that apart from an accidental write to a value prop, so it
        is declared off here rather than routed through nine emit handlers that
        would only copy values back into the same object.
    -->
    <div v-if="showSettings" class="settings-page" :class="{ 'is-showing': mobileShowing }"
         role="dialog" aria-modal="true" aria-labelledby="settings-page-title">
        <header class="settings-page-header">
            <button class="btn-icon settings-back" @click="mobileShowing ? (mobileShowing = false) : emit('close')"
                    :aria-label="mobileShowing ? 'Back to all settings' : 'Back to library'"
                    v-html="ICONS.back"></button>
            <h2 id="settings-page-title" class="settings-page-title">
                <span class="settings-title-root">Settings</span>
                <span class="settings-title-section">{{ currentLabel }}</span>
            </h2>
            <span class="settings-saved" :class="{ on: savedVisible }" aria-live="polite">
                <span v-html="ICONS.check"></span>{{ savedVisible ? 'Saved' : '' }}
            </span>
            <button class="btn btn-secondary settings-done" @click="emit('close')">Done</button>
        </header>

        <div class="settings-page-body">
            <nav class="settings-nav" aria-label="Settings sections">
                <button v-for="sec in SECTIONS" :key="sec.key" class="settings-nav-item"
                        :class="{ active: current === sec.key }" :aria-current="current === sec.key ? 'page' : undefined"
                        @click="openSection(sec.key)">
                    <span class="settings-nav-icon" v-html="ICONS[sec.icon]"></span>
                    <span class="settings-nav-text">
                        <span class="settings-nav-label">{{ sec.label }}</span>
                        <span class="settings-nav-hint">{{ sec.hint }}</span>
                    </span>
                    <span class="settings-nav-chev" v-html="ICONS.chevron"></span>
                </button>
            </nav>

            <div class="settings-content">

                <!-- ========== 1. Libraries ========== -->
                <div v-show="show('libraries')" id="settings-libraries" class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.folder"></span>
                        Libraries
                    </div>
                    <div class="settings-section-desc">
                        Add local directories containing your 3D model files.
                    </div>

                    <!-- Existing Libraries -->
                    <div v-if="libraries.length > 0" class="library-list">
                        <div v-for="lib in libraries" :key="lib.id" class="library-item">
                            <div class="library-info">
                                <div class="library-name">{{ lib.name }}</div>
                                <div class="library-path">{{ lib.path }}</div>
                                <div class="library-meta">
                                    {{ lib.model_count ?? 0 }} models
                                    <span style="opacity:0.5;margin:0 4px">&middot;</span>
                                    {{ timeAgo(lib.last_scanned_at) }}
                                </div>
                            </div>
                            <button class="btn-icon" @click="emit('scanLibrary', lib.id)"
                                    :disabled="scanStatus.scanning"
                                    :title="scanStatus.scanning ? 'Scan in progress' : 'Scan this library'">
                                <span v-html="ICONS.refresh"></span>
                            </button>
                            <button class="btn-icon btn-icon-danger" @click="emit('deleteLibrary', lib)" title="Remove library">
                                <span v-html="ICONS.trash"></span>
                            </button>
                        </div>
                    </div>
                    <div v-else class="text-muted text-sm" style="padding:12px 0">
                        No libraries configured yet. Add one below to get started.
                    </div>

                    <!-- Scan Libraries -->
                    <div v-if="libraries.length > 0" class="settings-btn-row library-actions">
                        <button class="btn btn-secondary"
                                @click="emit('triggerScan')"
                                :disabled="scanStatus.scanning"
                                title="Scan libraries for new models">
                            <span v-html="ICONS.refresh"></span>
                            {{ scanStatus.scanning ? 'Scanning…' : 'Scan all libraries' }}
                        </button>
                        <button v-if="!addFormOpen" class="btn btn-secondary" @click="addFormOpen = true">
                            <span v-html="ICONS.plus"></span> Add a folder
                        </button>
                        <div v-if="scanStatus.scanning" class="text-muted text-sm" style="margin-top:6px">
                            {{ scanStatus.processed_files }} / {{ scanStatus.total_files }} files processed
                        </div>
                    </div>

                    <!-- Add Library Form: folded away once you have a library. -->
                    <form v-if="addFormOpen || !libraries.length" class="add-library-form" @submit.prevent="emit('addLibrary')">
                        <div class="form-row">
                            <label class="form-label" for="new-lib-name">Library name</label>
                            <input type="text" id="new-lib-name"
                                   :value="newLibName"
                                   @input="emit('update:newLibName', $event.target.value)"
                                   placeholder="e.g. My 3D Models"
                                   class="form-input">
                        </div>
                        <div class="form-row">
                            <label class="form-label" for="new-lib-path">Folder path on the server</label>
                            <input type="text" id="new-lib-path"
                                   :value="newLibPath"
                                   @input="emit('update:newLibPath', $event.target.value)"
                                   placeholder="e.g. /home/user/models"
                                   class="form-input">
                        </div>
                        <div class="settings-btn-row">
                            <button v-if="libraries.length" type="button" class="btn btn-ghost" @click="addFormOpen = false">Cancel</button>
                            <button type="submit" class="btn btn-primary"
                                    :disabled="addingLibrary || !newLibName.trim() || !newLibPath.trim()">
                                <span v-html="ICONS.plus"></span>
                                {{ addingLibrary ? 'Adding…' : 'Add library' }}
                            </button>
                        </div>
                    </form>
                </div>

                <!-- ========== 2. Appearance ========== -->
                <div v-show="show('appearance')" id="settings-appearance" class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.sun"></span>
                        Appearance
                    </div>

                    <div style="display:flex;gap:8px;margin-bottom:12px">
                        <label class="thumbnail-mode-option" style="flex:0;padding:6px 14px"
                               :class="{ active: colorTheme === 'default' }"
                               @click="emit('setColorTheme', 'default')">
                            <input type="radio" name="colorTheme" value="default" :checked="colorTheme === 'default'" style="display:none">
                            Dark
                        </label>
                        <label class="thumbnail-mode-option" style="flex:0;padding:6px 14px"
                               :class="{ active: colorTheme === 'light' }"
                               @click="emit('setColorTheme', 'light')">
                            <input type="radio" name="colorTheme" value="light" :checked="colorTheme === 'light'" style="display:none">
                            Light
                        </label>
                    </div>

                    <div class="settings-section-desc">Thumbnail rendering mode</div>
                    <div class="thumbnail-mode-options">
                        <label class="thumbnail-mode-option" :class="{ active: thumbnailMode === 'wireframe' }" @click="emit('setThumbnailMode', 'wireframe')">
                            <input type="radio" name="thumbnailMode" value="wireframe" :checked="thumbnailMode === 'wireframe'">
                            <div class="thumbnail-mode-info">
                                <div class="thumbnail-mode-label">Wireframe</div>
                                <div class="thumbnail-mode-desc">Edges and outlines only</div>
                            </div>
                        </label>
                        <label class="thumbnail-mode-option" :class="{ active: thumbnailMode === 'solid' }" @click="emit('setThumbnailMode', 'solid')">
                            <input type="radio" name="thumbnailMode" value="solid" :checked="thumbnailMode === 'solid'">
                            <div class="thumbnail-mode-info">
                                <div class="thumbnail-mode-label">Solid</div>
                                <div class="thumbnail-mode-desc">Filled faces with lighting</div>
                            </div>
                        </label>
                    </div>

                    <div style="margin-bottom:14px">
                        <label class="form-label">3D preview detail</label>
                        <select class="form-input" :value="previewDetail"
                                @change="emit('setPreviewDetail', $event.target.value)">
                            <option value="fast">Fast — 150k faces</option>
                            <option value="balanced">Balanced — 300k faces</option>
                            <option value="detailed">Detailed — 500k faces</option>
                        </select>
                        <div class="settings-hint" style="margin-top:6px">
                            How much detail the 3D viewer keeps for models too large to
                            show whole. Only affects those &mdash; most models are well
                            under the threshold and are always shown in full. A lower
                            setting mainly cuts download and phone-side load time, since
                            the conversion itself is dominated by reading the original
                            file. Each level is cached separately, so switching back is
                            instant.
                        </div>
                    </div>

                    <label class="settings-toggle-row">
                        <input type="checkbox" :checked="favoritesFirst"
                               @change="emit('toggleFavoritesFirst')">
                        Show favorites at top of model list
                    </label>
                    <label class="settings-toggle-row" style="margin-top:8px">
                        <input type="checkbox" :checked="collectionCardTint"
                               @change="emit('toggleCollectionCardTint')">
                        Colour models by their collection
                    </label>
                </div>

                <!-- ========== 3. Printing ========== -->
                <div v-show="show('printing')" id="settings-printing" class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.slicer"></span>
                        Printing
                    </div>

                    <div class="form-row" style="margin-bottom:12px">
                        <label class="form-label">Slicer Integration</label>
                        <select class="form-input"
                                :value="preferredSlicer"
                                @change="emit('setPreferredSlicer', $event.target.value)">
                            <option value="none">None</option>
                            <option value="orcaslicer">OrcaSlicer</option>
                            <option value="cura">UltiMaker Cura</option>
                            <option value="bambustudio">Bambu Studio</option>
                            <option value="prusaslicer">PrusaSlicer</option>
                            <option value="superslicer">SuperSlicer</option>
                        </select>
                        <div class="settings-hint" style="margin-top:4px">
                            Adds a slicer button to the detail panel (STL, 3MF, OBJ).
                            <strong>OrcaSlicer</strong> and <strong>Cura</strong> open in one click via their URL scheme;
                            Prusa/Bambu/SuperSlicer download the file to open manually (their schemes reject self-hosted URLs).
                        </div>
                    </div>

                    <div class="bed-settings" @change="autosaveBed" @click="$event.target.closest('.thumbnail-mode-option') && autosaveBed()">
                    <label class="settings-toggle-row" style="margin-bottom:12px">
                        <input type="checkbox" :checked="bedConfig.enabled"
                               @change="emit('updateBedConfig', 'enabled', $event.target.checked)">
                        Show bed overlay in viewer
                    </label>

                    <div class="form-row">
                        <label class="form-label">Printer Preset</label>
                        <select class="form-input"
                                :value="bedPreset"
                                @change="emit('setBedPreset', $event.target.value)">
                            <option v-for="p in BED_PRESETS" :key="p.name" :value="p.name">
                                {{ p.name }}{{ p.width ? ` (${p.width}\u00d7${p.depth}\u00d7${p.height})` : '' }}
                            </option>
                        </select>
                    </div>

                    <div class="settings-dim-row">
                        <div class="form-row" style="flex:1">
                            <label class="form-label">Width (mm)</label>
                            <input type="number" class="form-input" :value="bedConfig.width" min="50" max="1000"
                                   @input="emit('updateBedConfig', 'width', parseInt($event.target.value) || 0)">
                        </div>
                        <div class="form-row" style="flex:1">
                            <label class="form-label">Depth (mm)</label>
                            <input type="number" class="form-input" :value="bedConfig.depth" min="50" max="1000"
                                   @input="emit('updateBedConfig', 'depth', parseInt($event.target.value) || 0)">
                        </div>
                        <div class="form-row" style="flex:1">
                            <label class="form-label">Height (mm)</label>
                            <input type="number" class="form-input" :value="bedConfig.height" min="50" max="1000"
                                   @input="emit('updateBedConfig', 'height', parseInt($event.target.value) || 0)">
                        </div>
                    </div>

                    <div class="settings-shape-row">
                        <span class="form-label" style="margin-bottom:0">Shape:</span>
                        <label class="thumbnail-mode-option" style="flex:0;padding:6px 14px"
                               :class="{ active: bedConfig.shape === 'rectangular' }"
                               @click="emit('updateBedConfig', 'shape', 'rectangular')">
                            <input type="radio" name="bedShape" value="rectangular" :checked="bedConfig.shape === 'rectangular'" style="display:none">
                            Rectangular
                        </label>
                        <label class="thumbnail-mode-option" style="flex:0;padding:6px 14px"
                               :class="{ active: bedConfig.shape === 'circular' }"
                               @click="emit('updateBedConfig', 'shape', 'circular')">
                            <input type="radio" name="bedShape" value="circular" :checked="bedConfig.shape === 'circular'" style="display:none">
                            Circular
                        </label>
                    </div>

                    </div>
                </div>

                <!-- ========== 4. Maintenance ========== -->
                <div v-show="show('maintenance')" id="settings-maintenance" class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.wrench"></span>
                        Maintenance
                    </div>

                    <label class="settings-toggle-row">
                        <input type="checkbox" :checked="autoTagOnScan"
                               @change="emit('toggleAutoTagOnScan')">
                        Auto-tag new models during scan
                    </label>
                    <div class="settings-hint">
                        Automatically adds tags based on filename, format, size, and complexity
                    </div>

                    <!-- Automation: scheduled scans -->
                    <div class="settings-dim-row" style="margin-top:12px">
                        <label class="form-label">Auto-scan interval</label>
                        <select class="form-input" :value="scanIntervalMinutes"
                                @change="emit('setScanInterval', $event.target.value)">
                            <option value="0">Off</option>
                            <option value="60">Every hour</option>
                            <option value="360">Every 6 hours</option>
                            <option value="720">Every 12 hours</option>
                            <option value="1440">Daily</option>
                        </select>
                    </div>
                    <div class="settings-hint">
                        Periodically runs an update scan to pick up new/changed files.
                    </div>

                    <!-- Automation: webhook -->
                    <div style="margin-top:12px">
                        <label class="form-label">Webhook URL (Home Assistant, etc.)</label>
                        <div class="settings-btn-row">
                            <input type="url" class="form-input" style="flex:1"
                                   :value="webhookUrl"
                                   placeholder="https://ha.local/api/webhook/yastl"
                                   @change="emit('setWebhookUrl', $event.target.value)">
                            <button class="btn btn-secondary" @click="emit('testWebhook')"
                                    :disabled="!webhookUrl">Test</button>
                        </div>
                        <div class="settings-hint">
                            POSTs a JSON event (e.g. <code>scan_complete</code>) when scans finish.
                        </div>
                    </div>

                    <div class="settings-btn-row">
                        <button class="btn btn-secondary"
                                @click="emit('regenerateThumbnails')"
                                :disabled="regeneratingThumbnails">
                            <span v-html="ICONS.refresh"></span>
                            Regenerate thumbnails
                        </button>
                        <button class="btn btn-secondary"
                                @click="emit('autoTagAll')"
                                :disabled="autoTagging">
                            <span v-html="ICONS.refresh"></span>
                            Auto-tag all
                        </button>
                        <button class="btn btn-secondary"
                                @click="emit('extractMetadata')"
                                :disabled="extractingMetadata"
                                title="Extract descriptions and tags from README files in zips and folders">
                            <span v-html="ICONS.refresh"></span>
                            Extract metadata
                        </button>
                        <button class="btn btn-secondary"
                                @click="emit('cleanupTags')"
                                title="Delete tags not attached to any model">
                            <span v-html="ICONS.wrench"></span>
                            Clean up tags
                        </button>
                        <button class="btn btn-secondary"
                                @click="emit('generatePreviews')"
                                :disabled="generatingPreviews"
                                title="Pre-build decimated 3D previews for large models so they open instantly">
                            <span class="btn-icon-sm" v-html="ICONS.cube"></span>
                            Generate previews
                        </button>
                    </div>

                    <div v-if="regeneratingThumbnails && regenProgress.total > 0" class="regen-progress" style="margin-top:12px">
                        <div class="regen-progress-bar">
                            <div class="regen-progress-fill" :style="{ width: Math.round((regenProgress.completed / regenProgress.total) * 100) + '%' }"></div>
                        </div>
                        <span class="text-muted text-sm" style="margin-top:4px;display:block">
                            Thumbnails: {{ regenProgress.completed }} / {{ regenProgress.total }} models
                        </span>
                    </div>
                    <div v-if="autoTagging && autoTagProgress.total > 0" class="regen-progress" style="margin-top:12px">
                        <div class="regen-progress-bar">
                            <div class="regen-progress-fill" :style="{ width: Math.round((autoTagProgress.completed / autoTagProgress.total) * 100) + '%' }"></div>
                        </div>
                        <span class="text-muted text-sm" style="margin-top:4px;display:block">
                            Tags: {{ autoTagProgress.completed }} / {{ autoTagProgress.total }} models &middot; {{ autoTagProgress.tags_added }} tags added
                        </span>
                    </div>
                    <div v-if="extractingMetadata && metadataProgress.total > 0" class="regen-progress" style="margin-top:12px">
                        <div class="regen-progress-bar">
                            <div class="regen-progress-fill" :style="{ width: Math.round((metadataProgress.completed / metadataProgress.total) * 100) + '%' }"></div>
                        </div>
                        <span class="text-muted text-sm" style="margin-top:4px;display:block">
                            Metadata: {{ metadataProgress.completed }} / {{ metadataProgress.total }} models &middot; {{ metadataProgress.updated }} updated
                        </span>
                    </div>
                    <div v-if="generatingPreviews && previewProgress.total > 0" class="regen-progress" style="margin-top:12px">
                        <div class="regen-progress-bar">
                            <div class="regen-progress-fill" :style="{ width: Math.round((previewProgress.completed / previewProgress.total) * 100) + '%' }"></div>
                        </div>
                        <span class="text-muted text-sm" style="margin-top:4px;display:block">
                            Previews: {{ previewProgress.completed }} / {{ previewProgress.total }} large models &middot; {{ previewProgress.generated }} built
                        </span>
                    </div>
                </div>

                <!-- ========== 5. AI (optional, bring your own key) ========== -->
                <div v-show="show('ai')" id="settings-ai" @change="autosaveAi" class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.zap"></span>
                        AI <span class="settings-optional-tag">optional · bring your own key</span>
                    </div>
                    <div class="settings-hint" style="margin-bottom:10px">
                        Off by default. Adds AI auto-tagging and natural-language
                        semantic search using your own API key. Requests go directly
                        from this server to your provider; keys are stored locally.
                    </div>

                    <label class="checkbox-item" style="margin-bottom:10px">
                        <input type="checkbox" v-model="ai.enabled">
                        <span>Enable AI features</span>
                    </label>

                    <div class="ai-settings-grid">
                        <div>
                            <label class="form-label">Chat / vision provider</label>
                            <select class="form-input" v-model="ai.provider">
                                <option value="openrouter">OpenRouter</option>
                                <option value="anthropic">Anthropic (Claude)</option>
                                <option value="openai">OpenAI</option>
                            </select>
                        </div>
                        <div>
                            <label class="form-label">API key</label>
                            <input type="password" class="form-input" v-model="ai.api_key"
                                   placeholder="sk-…" autocomplete="off">
                        </div>
                        <div>
                            <label class="form-label">Vision model <span class="text-muted">(blank = default)</span></label>
                            <input type="text" class="form-input" v-model="ai.vision_model"
                                   placeholder="e.g. claude-haiku-4-5">
                        </div>
                        <div>
                            <label class="form-label">Embeddings provider</label>
                            <select class="form-input" v-model="ai.embed_provider">
                                <option value="openrouter">OpenRouter</option>
                                <option value="openai">OpenAI</option>
                                <option value="voyage">Voyage (for Anthropic key)</option>
                            </select>
                        </div>
                        <div>
                            <label class="form-label">Embeddings key <span class="text-muted">(if different)</span></label>
                            <input type="password" class="form-input" v-model="ai.embed_key"
                                   placeholder="(reuses chat key if blank)" autocomplete="off">
                        </div>
                        <div>
                            <label class="form-label">Embeddings model <span class="text-muted">(blank = default)</span></label>
                            <input type="text" class="form-input" v-model="ai.embed_model"
                                   placeholder="e.g. text-embedding-3-small">
                        </div>
                        <div>
                            <label class="form-label">Auto-tag vocabulary</label>
                            <select class="form-input" v-model="ai.vocab_mode">
                                <option value="controlled">Controlled (existing tags only)</option>
                                <option value="open">Open (allow new tags)</option>
                            </select>
                        </div>
                        <div>
                            <label class="form-label">Monthly cost cap (USD, 0 = none)</label>
                            <input type="number" min="0" class="form-input" v-model="ai.monthly_cost_cap_usd">
                        </div>
                    </div>

                    <div class="settings-btn-row" style="margin-top:12px">
                        <button class="btn btn-secondary" @click="emit('testAi')"
                                :disabled="aiTesting || !ai.enabled">
                            {{ aiTesting ? 'Testing…' : 'Test connection' }}
                        </button>
                        <span v-if="aiTestResult" class="ai-test-result"
                              :class="aiTestResult.ok ? 'ok' : 'err'">
                            {{ aiTestResult.ok ? '✓ ' : '✗ ' }}{{ aiTestResult.detail }}
                        </span>
                    </div>

                    <div class="settings-subsection-title" style="margin-top:18px">Semantic search</div>
                    <div class="settings-hint" style="margin-bottom:8px">
                        Builds embeddings so search matches meaning — e.g. "articulated dragon"
                        finds <code>dragon_v2_final.stl</code>. Re-run after adding models.
                        <strong>{{ embedProgress.in_memory || 0 }}</strong> models indexed.
                    </div>
                    <button class="btn btn-secondary" @click="emit('buildEmbeddings')"
                            :disabled="buildingEmbeddings || !ai.enabled">
                        <span v-html="ICONS.refresh"></span>
                        {{ buildingEmbeddings ? 'Building…' : 'Build embeddings' }}
                    </button>
                    <div v-if="buildingEmbeddings && embedProgress.total > 0" class="regen-progress" style="margin-top:10px">
                        <div class="regen-progress-bar">
                            <div class="regen-progress-fill"
                                 :style="{ width: Math.round((embedProgress.completed / embedProgress.total) * 100) + '%' }"></div>
                        </div>
                        <span class="text-muted text-sm" style="margin-top:4px;display:block">
                            Embeddings: {{ embedProgress.completed }} / {{ embedProgress.total }}
                        </span>
                    </div>

                    <div class="settings-subsection-title" style="margin-top:18px">Auto-tagging</div>
                    <div class="settings-hint" style="margin-bottom:8px">
                        Sends each thumbnail to the vision model for tag + description suggestions
                        (honours the vocabulary mode above). You can also use "AI suggest tags" on a
                        single model in its detail panel.
                    </div>
                    <button class="btn btn-secondary" @click="emit('aiAutoTagAll')"
                            :disabled="aiTaggingAll || !ai.enabled">
                        <span v-html="ICONS.zap"></span>
                        {{ aiTaggingAll ? 'Tagging…' : 'AI auto-tag all models' }}
                    </button>
                    <div v-if="aiTaggingAll && aiTagProgress.total > 0" class="regen-progress" style="margin-top:10px">
                        <div class="regen-progress-bar">
                            <div class="regen-progress-fill"
                                 :style="{ width: Math.round((aiTagProgress.completed / aiTagProgress.total) * 100) + '%' }"></div>
                        </div>
                        <span class="text-muted text-sm" style="margin-top:4px;display:block">
                            Tagged: {{ aiTagProgress.completed }} / {{ aiTagProgress.total }}
                            · {{ aiTagProgress.tags_added }} tags added
                        </span>
                    </div>
                </div>


                <!-- ========== 5. Connect (browser extension) ========== -->
                <div v-show="show('extension')" id="settings-extension" class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.link"></span>
                        Connect <span class="settings-optional-tag">optional · browser extension</span>
                    </div>
                    <div class="settings-hint" style="margin-bottom:10px">
                        Off by default. Lets the YASTL Connect browser extension push model
                        downloads from Printables, Thingiverse, MakerWorld, Thangs,
                        MyMiniFactory and Cults3D straight into a library, with the source
                        page&rsquo;s title, description, tags and licence attached.
                        <strong>Your browser does the downloading</strong>, so files behind a
                        site login, or on sites that block servers, work the same as clicking
                        Download yourself.
                    </div>

                    <label class="checkbox-item" style="margin-bottom:10px">
                        <input type="checkbox" v-model="connect.enabled"
                               @change="emit('saveConnectSettings')">
                        <span>Enable Connect</span>
                    </label>

                    <div v-if="connect.enabled">
                        <div class="connect-steps-head">
                            <div class="settings-subsection-title">Setup</div>
                            <button class="btn-link" type="button"
                                    @click="showConnectSteps = !showConnectSteps">
                                {{ stepsOpen ? 'Hide steps' : 'Show steps' }}
                            </button>
                        </div>

                        <ol v-if="stepsOpen" class="connect-steps">
                            <li>
                                <div class="connect-step-title">Generate an access token</div>
                                <div class="settings-btn-row" style="align-items:center">
                                    <input type="text" class="form-input mono" readonly
                                           :value="connectFullToken || connect.token"
                                           placeholder="No token yet"
                                           @focus="$event.target.select()">
                                    <button class="btn btn-secondary" :disabled="!connectFullToken"
                                            :title="connectFullToken
                                                ? 'Copy the token to the clipboard'
                                                : 'The stored token is masked and cannot be copied. Regenerate to get a new one you can copy.'"
                                            @click="emit('copyText', { text: connectFullToken, label: 'Token' })">
                                        <span v-html="ICONS.copy"></span> Copy
                                    </button>
                                    <button class="btn btn-primary" @click="emit('rotateConnectToken')">
                                        {{ connect.token ? 'Regenerate' : 'Generate' }}
                                    </button>
                                </div>
                                <div class="connect-step-hint">
                                    <template v-if="connectFullToken">
                                        <strong>Copy it now.</strong> This is the only time the full
                                        token is shown &mdash; from here on it reads back masked.
                                    </template>
                                    <template v-else-if="connect.token">
                                        A token is set but hidden. Regenerate to see a new one; that
                                        immediately stops any browser still using the old one.
                                    </template>
                                    <template v-else>
                                        Press Generate. You will paste this into the extension in
                                        step&nbsp;5.
                                    </template>
                                </div>
                            </li>

                            <li>
                                <div class="connect-step-title">Download and unpack the extension</div>
                                <div class="settings-btn-row">
                                    <a class="btn btn-primary" href="/api/connect/extension.zip" download>
                                        <span v-html="ICONS.download"></span> Download extension (.zip)
                                    </a>
                                </div>
                                <div class="connect-step-hint">
                                    Save it on <strong>the machine your browser runs on</strong>, and
                                    unzip it somewhere it can stay &mdash; your browser reads the
                                    folder from disk every time it starts, so moving or deleting it
                                    later breaks the extension. Your Documents folder is fine; a
                                    temporary or Downloads folder is not.
                                </div>
                            </li>

                            <li>
                                <div class="connect-step-title">Load it into your browser</div>
                                <div class="connect-step-hint">
                                    In <strong>Chrome, Edge or Brave</strong>: open
                                    <code>chrome://extensions</code>, turn on
                                    <strong>Developer mode</strong> (top right), choose
                                    <strong>Load unpacked</strong>, and select the unzipped folder
                                    &mdash; the one that <em>contains</em> <code>manifest.json</code>,
                                    not the file itself and not the <code>src</code> folder inside it.
                                    <br><br>
                                    In <strong>Firefox</strong>: open
                                    <code>about:debugging#/runtime/this-firefox</code>, choose
                                    <strong>Load Temporary Add-on</strong>, and pick
                                    <code>manifest.json</code>. Firefox drops a temporary add-on when
                                    it closes, so this has to be repeated each session.
                                </div>
                            </li>

                            <li>
                                <div class="connect-step-title">Give it this server&rsquo;s address</div>
                                <div class="settings-btn-row" style="align-items:center">
                                    <input type="text" class="form-input mono" readonly
                                           :value="serverOrigin" @focus="$event.target.select()">
                                    <button class="btn btn-secondary"
                                            @click="emit('copyText', { text: serverOrigin, label: 'Address' })">
                                        <span v-html="ICONS.copy"></span> Copy
                                    </button>
                                </div>
                                <div class="connect-step-hint">
                                    That is the address you are reading this page on. If your browser
                                    is on another machine, use one that machine can reach &mdash;
                                    <code>localhost</code> will not work from elsewhere.
                                </div>
                            </li>

                            <li>
                                <div class="connect-step-title">Configure the extension</div>
                                <div class="connect-step-hint">
                                    Open its options page (the puzzle-piece menu &rarr; YASTL Connect
                                    &rarr; Options; it also opens itself on first install), then:
                                    <ol class="connect-substeps">
                                        <li>Paste the address from step&nbsp;4 and the token from step&nbsp;1.</li>
                                        <li>Press <strong>Test connection</strong>.</li>
                                        <li>
                                            Press <strong>Grant site access</strong> and accept the
                                            prompt. <strong>Do not skip this.</strong> Model sites
                                            redirect downloads to a CDN on another host, and the
                                            extension can only fetch from hosts it has permission for.
                                            Your browser only grants that from a button press, so it
                                            cannot be asked for later while a download is in flight.
                                        </li>
                                        <li>Choose a destination <strong>Library</strong>, then press <strong>Save</strong>.</li>
                                    </ol>
                                </div>
                            </li>

                            <li>
                                <div class="connect-step-title">Capture something</div>
                                <div class="connect-step-hint">
                                    Open a model page on a supported site and click the site&rsquo;s own
                                    Download button. The capture appears in the extension&rsquo;s popup
                                    and the model lands here a few seconds later. The toolbar badge
                                    counts captures in flight in blue, and anything needing you in red.
                                </div>
                            </li>
                        </ol>

                        <div class="settings-hint connect-note">
                            <strong>Keeping it up to date.</strong> An unpacked extension never
                            updates itself. When you update YASTL, download the zip again, replace
                            the folder, then reload the extension at
                            <code>chrome://extensions</code> &mdash; its options page also tells you
                            when this server is offering a newer build than the one you have loaded.
                            <br><br>
                            After any reload, <strong>reload any model page you already had
                            open</strong>. Browsers only inject an extension&rsquo;s page reader when
                            a page loads, so a tab opened beforehand has none, and captures from it
                            arrive with no title or tags.
                        </div>

                        <div class="settings-hint connect-note warn">
                            <strong>About the token.</strong> It is a shared secret sent with every
                            capture. Over plain <code>http://</code> on your LAN it is readable by
                            anything already watching that network &mdash; it stops a web page
                            writing into your library, not someone already on your own wire.
                            Regenerate it to revoke a browser that has it.
                        </div>
                    </div>
                </div>

                <!-- ========== 6. Advanced (collapsible) ========== -->
                <div v-show="show('backup')" id="settings-backup" class="settings-section" :class="{ 'settings-section-collapsed': !showAdvanced }">
                    <div class="settings-section-title">
                        <span v-html="ICONS.database"></span>
                        Backup and sites
                    </div>

                    <template v-if="showAdvanced">
                        <!-- Backup / Export -->
                        <div class="settings-advanced-subsection">
                            <div class="settings-subsection-title">Backup &amp; Export</div>
                            <div class="settings-section-desc">
                                Export your curated metadata (tags, categories, collections, print history)
                                or a full snapshot of the database.
                            </div>
                            <div class="settings-btn-row">
                                <a class="btn btn-secondary" href="/api/backup/manifest" download>
                                    <span v-html="ICONS.download"></span> Export Manifest (JSON)
                                </a>
                                <a class="btn btn-secondary" href="/api/backup/database" download>
                                    <span v-html="ICONS.database"></span> Backup Database
                                </a>
                            </div>
                        </div>

                        <!-- Import Credentials -->
                        <div class="settings-advanced-subsection">
                            <div class="settings-subsection-title">Import Credentials</div>
                            <div class="settings-section-desc">
                                API keys or cookies for 3D model hosting sites to enable richer metadata extraction during URL import.
                            </div>

                            <div class="import-cred-list">
                                <div class="import-cred-item" v-for="site in ['thingiverse', 'makerworld', 'printables', 'myminifactory', 'cults3d', 'thangs']" :key="site">
                                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                                        <span style="font-weight:600;text-transform:capitalize;font-size:0.85rem">{{ site }}</span>
                                        <button v-if="importCredentials[site]" class="btn btn-sm btn-ghost text-danger"
                                                @click="emit('deleteImportCredential', site)">Remove</button>
                                    </div>
                                    <div v-if="site === 'thingiverse'" class="form-row">
                                        <label class="form-label">API Key</label>
                                        <div style="display:flex;gap:6px">
                                            <input type="text" class="form-input" :value="credentialInputs[site]"
                                                   @input="emit('updateCredentialInput', site, $event.target.value)"
                                                   :placeholder="importCredentials.thingiverse ? importCredentials.thingiverse.api_key || 'Not set' : 'Not set'"
                                                   style="flex:1">
                                            <button class="btn btn-sm btn-primary"
                                                    @click="emit('saveImportCredential', site, 'api_key')">Save</button>
                                        </div>
                                    </div>
                                    <div v-else-if="site === 'makerworld'" class="form-row">
                                        <label class="form-label">Token</label>
                                        <div style="display:flex;gap:6px">
                                            <input type="text" class="form-input" :value="credentialInputs[site]"
                                                   @input="emit('updateCredentialInput', site, $event.target.value)"
                                                   :placeholder="importCredentials[site] ? importCredentials[site].token || 'Not set' : 'Not set'"
                                                   style="flex:1">
                                            <button class="btn btn-sm btn-primary"
                                                    @click="emit('saveImportCredential', site, 'token')">Save</button>
                                        </div>
                                        <div class="settings-hint" style="margin-top:4px">
                                            In your browser on makerworld.com: press F12 &rarr; Application &rarr; Cookies &rarr; copy the <strong>token</strong> value (starts with AAB_). Valid for 90 days.
                                        </div>
                                    </div>
                                    <div v-else class="form-row">
                                        <label class="form-label">Cookie</label>
                                        <div style="display:flex;gap:6px">
                                            <input type="text" class="form-input" :value="credentialInputs[site]"
                                                   @input="emit('updateCredentialInput', site, $event.target.value)"
                                                   :placeholder="importCredentials[site] ? importCredentials[site].cookie || 'Not set' : 'Not set'"
                                                   style="flex:1">
                                            <button class="btn btn-sm btn-primary"
                                                    @click="emit('saveImportCredential', site, 'cookie')">Save</button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                    </template>
                </div>

                <!-- ========== 6. Updates ========== -->
                <div v-show="show('updates')" id="settings-updates" class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.refresh"></span>
                        Updates
                    </div>

                    <!-- Not a git repo -->
                    <div v-if="updateInfo.checked && !updateInfo.is_git_repo" class="update-status update-status-unavailable">
                        <div class="update-status-icon">
                            <span v-html="ICONS.warning"></span>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Updates unavailable</div>
                            <div class="update-status-detail">
                                Not running from a git repository.
                            </div>
                        </div>
                    </div>

                    <!-- Restarting -->
                    <div v-else-if="updateInfo.restarting" class="update-status update-status-restarting">
                        <div class="update-status-icon">
                            <div class="spinner spinner-sm"></div>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Restarting...</div>
                            <div class="update-status-detail">
                                This page will reload automatically.
                            </div>
                        </div>
                    </div>

                    <!-- Applying update -->
                    <div v-else-if="updateInfo.applying" class="update-status update-status-applying">
                        <div class="update-status-icon">
                            <div class="spinner spinner-sm"></div>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Applying update...</div>
                        </div>
                    </div>

                    <!-- Checking -->
                    <div v-else-if="updateInfo.checking" class="update-status update-status-checking">
                        <div class="update-status-icon">
                            <div class="spinner spinner-sm"></div>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Checking for updates...</div>
                        </div>
                    </div>

                    <!-- Update available -->
                    <div v-else-if="updateInfo.update_available" class="update-status update-status-available">
                        <div class="update-status-header">
                            <div class="update-status-icon update-icon-available">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="12" y2="16"/><line x1="16" y1="12" x2="12" y2="16"/></svg>
                            </div>
                            <div class="update-status-text">
                                <div class="update-status-title">Update available</div>
                                <div class="update-status-detail">
                                    {{ updateInfo.commits_behind }} new commit{{ updateInfo.commits_behind !== 1 ? 's' : '' }}
                                    on <code>{{ updateInfo.branch }}</code>
                                </div>
                            </div>
                        </div>
                        <div v-if="updateInfo.commits.length" class="update-commits">
                            <div v-for="commit in updateInfo.commits" :key="commit.sha" class="update-commit">
                                <code class="commit-sha">{{ commit.sha }}</code>
                                <span class="commit-message">{{ commit.message }}</span>
                                <span class="commit-meta">{{ commit.author }} &middot; {{ commit.date }}</span>
                            </div>
                        </div>
                        <button class="btn btn-primary update-apply-btn"
                                @click="emit('applyUpdate')"
                                :disabled="updateInfo.applying">
                            <span v-html="ICONS.download"></span>
                            Update &amp; Restart
                        </button>
                    </div>

                    <!-- Up to date -->
                    <div v-else-if="updateInfo.checked && !updateInfo.error" class="update-status update-status-current">
                        <div class="update-status-icon update-icon-current">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="8 12 11 15 16 9"/></svg>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Up to date</div>
                            <div class="update-status-detail">
                                v{{ updateInfo.current_version }}
                                <span v-if="updateInfo.current_sha" class="text-muted">
                                    &middot; {{ updateInfo.current_sha.substring(0, 8) }}
                                </span>
                            </div>
                        </div>
                    </div>

                    <!-- Error -->
                    <div v-if="updateInfo.error" class="update-error">
                        <span v-html="ICONS.warning"></span>
                        {{ updateInfo.error }}
                    </div>

                    <!-- Check button -->
                    <button class="btn btn-secondary update-check-btn"
                            @click="emit('checkForUpdates')"
                            :disabled="updateInfo.checking || updateInfo.applying || updateInfo.restarting">
                        <span v-html="ICONS.refresh"></span>
                        Check for updates
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>
