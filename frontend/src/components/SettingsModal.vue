<script setup>
/**
 * SettingsModal - Settings panel with libraries, thumbnails, import credentials, and updates.
 */
import { ICONS } from '../icons.js';

defineProps({
    showSettings: { type: Boolean, default: false },
    libraries: { type: Array, default: () => [] },
    newLibName: { type: String, default: '' },
    newLibPath: { type: String, default: '' },
    addingLibrary: { type: Boolean, default: false },
    thumbnailMode: { type: String, default: 'wireframe' },
    regeneratingThumbnails: { type: Boolean, default: false },
    regenProgress: { type: Object, default: () => ({ completed: 0, total: 0 }) },
    updateInfo: { type: Object, required: true },
    scanStatus: { type: Object, required: true },
    importCredentials: { type: Object, default: () => ({}) },
    credentialInputs: { type: Object, default: () => ({}) },
});

const emit = defineEmits([
    'close',
    'update:newLibName',
    'update:newLibPath',
    'addLibrary',
    'deleteLibrary',
    'triggerScan',
    'setThumbnailMode',
    'regenerateThumbnails',
    'checkForUpdates',
    'applyUpdate',
    'saveImportCredential',
    'deleteImportCredential',
    'updateCredentialInput',
]);
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
                <!-- Libraries Section -->
                <div class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.folder"></span>
                        Libraries
                    </div>
                    <div class="settings-section-desc">
                        Add local directories containing your 3D model files. YASTL will scan these paths to discover and index models.
                    </div>

                    <!-- Existing Libraries -->
                    <div v-if="libraries.length > 0" class="library-list">
                        <div v-for="lib in libraries" :key="lib.id" class="library-item">
                            <div class="library-info">
                                <div class="library-name">{{ lib.name }}</div>
                                <div class="library-path">{{ lib.path }}</div>
                            </div>
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
                            {{ scanStatus.scanning ? 'Scanning...' : 'Scan Libraries' }}
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

                <!-- Thumbnails Section -->
                <div class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.image"></span>
                        Thumbnails
                    </div>
                    <div class="settings-section-desc">
                        Choose how model preview thumbnails are rendered. Solid mode shows filled faces with lighting; wireframe shows edges only.
                    </div>

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

                    <div class="thumbnail-regen-row">
                        <button class="btn btn-secondary"
                                @click="emit('regenerateThumbnails')"
                                :disabled="regeneratingThumbnails">
                            <span v-html="ICONS.refresh"></span>
                            Regenerate All Thumbnails
                        </button>
                        <span class="text-muted text-sm">Re-render existing thumbnails with the current mode</span>
                    </div>
                    <div v-if="regeneratingThumbnails && regenProgress.total > 0" class="regen-progress" style="margin-top:12px">
                        <div class="regen-progress-bar">
                            <div class="regen-progress-fill" :style="{ width: Math.round((regenProgress.completed / regenProgress.total) * 100) + '%' }"></div>
                        </div>
                        <span class="text-muted text-sm" style="margin-top:4px;display:block">
                            {{ regenProgress.completed }} / {{ regenProgress.total }} models
                        </span>
                    </div>
                </div>

                <!-- Import Credentials Section -->
                <div class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.link"></span>
                        Import Credentials
                    </div>
                    <div class="settings-section-desc">
                        Configure API keys or cookies for 3D model hosting sites to enable richer metadata extraction during URL import.
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
                                <div class="text-muted" style="font-size:0.7rem;margin-top:4px">
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

                <!-- Update Section -->
                <div class="settings-section">
                    <div class="settings-section-title">
                        <span v-html="ICONS.refresh"></span>
                        Updates
                    </div>
                    <div class="settings-section-desc">
                        Check for and apply updates from the remote repository. The service will restart automatically after updating.
                    </div>

                    <!-- Not a git repo -->
                    <div v-if="updateInfo.checked && !updateInfo.is_git_repo" class="update-status update-status-unavailable">
                        <div class="update-status-icon">
                            <span v-html="ICONS.warning"></span>
                        </div>
                        <div class="update-status-text">
                            <div class="update-status-title">Updates unavailable</div>
                            <div class="update-status-detail">
                                Not running from a git repository. Updates require a git-based installation.
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
                                YASTL is restarting with the latest changes. This page will reload automatically.
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
                            <div class="update-status-detail">
                                Pulling changes and reinstalling dependencies.
                            </div>
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
                        <!-- Commit list -->
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
                                <span v-if="updateInfo.branch" class="text-muted">
                                    &middot; {{ updateInfo.branch }}
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
            </div>
        </div>
    </div>
</template>
