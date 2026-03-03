<script setup>
/**
 * SettingsModal - Settings panel: Libraries, Appearance, Printing, Maintenance, Advanced.
 */
import { ref } from 'vue';
import { ICONS } from '../icons.js';
import { BED_PRESETS } from '../composables/useSettings.js';

const showAdvanced = ref(false);

defineProps({
    showSettings: { type: Boolean, default: false },
    libraries: { type: Array, default: () => [] },
    newLibName: { type: String, default: '' },
    newLibPath: { type: String, default: '' },
    addingLibrary: { type: Boolean, default: false },
    thumbnailMode: { type: String, default: 'wireframe' },
    regeneratingThumbnails: { type: Boolean, default: false },
    regenProgress: { type: Object, default: () => ({ completed: 0, total: 0 }) },
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
});

const emit = defineEmits([
    'close',
    'update:newLibName',
    'update:newLibPath',
    'addLibrary',
    'deleteLibrary',
    'triggerScan',
    'scanLibrary',
    'setThumbnailMode',
    'regenerateThumbnails',
    'autoTagAll',
    'extractMetadata',
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
]);

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
    <div v-if="showSettings" class="detail-overlay" @click.self="emit('close')">
        <div class="settings-panel">
            <!-- Header -->
            <div class="detail-header">
                <div class="detail-title">Settings</div>
                <button class="close-btn" @click="emit('close')" title="Close">&times;</button>
            </div>

            <div class="settings-content">

                <!-- ========== 1. Libraries ========== -->
                <div class="settings-section">
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
                    <div v-if="libraries.length > 0" style="padding: 0 0 12px 0;">
                        <button class="btn btn-primary"
                                @click="emit('triggerScan')"
                                :disabled="scanStatus.scanning"
                                title="Scan libraries for new models">
                            <span v-html="ICONS.scan"></span>
                            {{ scanStatus.scanning ? 'Scanning...' : 'Scan All Libraries' }}
                        </button>
                        <div v-if="scanStatus.scanning" class="text-muted text-sm" style="margin-top:6px">
                            {{ scanStatus.processed_files }} / {{ scanStatus.total_files }} files processed
                        </div>
                    </div>

                    <!-- Add Library Form -->
                    <div class="add-library-form">
                        <div class="form-row">
                            <label class="form-label">Library Name</label>
                            <input type="text"
                                   :value="newLibName"
                                   @input="emit('update:newLibName', $event.target.value)"
                                   placeholder="e.g. My 3D Models"
                                   class="form-input">
                        </div>
                        <div class="form-row">
                            <label class="form-label">Local Path</label>
                            <input type="text"
                                   :value="newLibPath"
                                   @input="emit('update:newLibPath', $event.target.value)"
                                   placeholder="e.g. /home/user/models"
                                   class="form-input"
                                   @keydown.enter="emit('addLibrary')">
                        </div>
                        <button class="btn btn-primary"
                                @click="emit('addLibrary')"
                                :disabled="addingLibrary || !newLibName.trim() || !newLibPath.trim()">
                            <span v-html="ICONS.plus"></span>
                            Add Library
                        </button>
                    </div>
                </div>

                <!-- ========== 2. Appearance ========== -->
                <div class="settings-section">
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

                    <label class="settings-toggle-row">
                        <input type="checkbox" :checked="favoritesFirst"
                               @change="emit('toggleFavoritesFirst')">
                        Show favorites at top of model list
                    </label>
                    <label class="settings-toggle-row" style="margin-top:8px">
                        <input type="checkbox" :checked="collectionCardTint"
                               @change="emit('toggleCollectionCardTint')">
                        Tint model cards with collection color
                    </label>
                </div>

                <!-- ========== 3. Printing ========== -->
                <div class="settings-section">
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
                            <option value="bambustudio">Bambu Studio</option>
                            <option value="orcaslicer">OrcaSlicer</option>
                            <option value="prusaslicer">PrusaSlicer</option>
                        </select>
                        <div class="settings-hint" style="margin-top:4px">
                            Adds an "Open in Slicer" button to the model detail panel for STL, 3MF, and OBJ files.
                        </div>
                    </div>

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

                    <div style="margin-top:12px">
                        <button class="btn btn-primary" @click="emit('saveBedSettings')">
                            Save Bed Settings
                        </button>
                    </div>
                </div>

                <!-- ========== 4. Maintenance ========== -->
                <div class="settings-section">
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

                    <div class="settings-btn-row">
                        <button class="btn btn-secondary"
                                @click="emit('regenerateThumbnails')"
                                :disabled="regeneratingThumbnails">
                            <span v-html="ICONS.refresh"></span>
                            Regen Thumbnails
                        </button>
                        <button class="btn btn-secondary"
                                @click="emit('autoTagAll')"
                                :disabled="autoTagging">
                            <span v-html="ICONS.refresh"></span>
                            Auto-Tag All
                        </button>
                        <button class="btn btn-secondary"
                                @click="emit('extractMetadata')"
                                :disabled="extractingMetadata"
                                title="Extract descriptions and tags from README files in zips and folders">
                            <span v-html="ICONS.refresh"></span>
                            Extract Metadata
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
                </div>

                <!-- ========== 5. Advanced (collapsible) ========== -->
                <div class="settings-section">
                    <div class="settings-advanced-header" @click="showAdvanced = !showAdvanced">
                        <div class="settings-section-title">
                            <span v-html="ICONS.settings"></span>
                            Advanced
                            <span class="settings-advanced-arrow">{{ showAdvanced ? '&#x25BC;' : '&#x25B6;' }}</span>
                        </div>
                    </div>

                    <template v-if="showAdvanced">
                        <!-- Import Credentials -->
                        <div style="margin-top:12px">
                            <div style="font-weight:600;font-size:0.85rem;margin-bottom:8px">Import Credentials</div>
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

                        <!-- Updates -->
                        <div style="margin-top:20px;border-top:1px solid var(--border);padding-top:16px">
                            <div style="font-weight:600;font-size:0.85rem;margin-bottom:8px">Updates</div>

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
                                Check for Updates
                            </button>
                        </div>
                    </template>
                </div>
            </div>
        </div>
    </div>
</template>
