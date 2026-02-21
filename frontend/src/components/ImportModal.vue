<script setup>
/**
 * ImportModal - Import/upload modal for URL imports and file uploads.
 */
import { ICONS } from '../icons.js';
import { formatFileSize } from '../search.js';

defineProps({
    showImportModal: { type: Boolean, default: false },
    importMode: { type: String, default: 'url' },
    importUrls: { type: String, default: '' },
    importLibraryId: { default: null },
    importSubfolder: { type: String, default: '' },
    importRunning: { type: Boolean, default: false },
    importDone: { type: Boolean, default: false },
    importPreview: { type: Object, default: () => ({ loading: false, data: null }) },
    importProgress: { type: Object, default: () => ({ total: 0, completed: 0, results: [], current_url: '' }) },
    uploadFiles: { type: Array, default: () => [] },
    uploadResults: { type: Array, default: () => [] },
    uploadTags: { type: String, default: '' },
    uploadTagSuggestions: { type: Array, default: () => [] },
    uploadCollectionId: { default: null },
    uploadSourceUrl: { type: String, default: '' },
    uploadDescription: { type: String, default: '' },
    uploadZipMeta: { default: null },
    libraries: { type: Array, default: () => [] },
    collections: { type: Array, default: () => [] },
    inlineNewCollection: { type: Object, default: () => ({ active: false, name: '', color: '#4f8cff' }) },
    COLLECTION_COLORS: { type: Array, default: () => [] },
});

function onCollectionSelect(e) {
    const val = e.target.value;
    if (val === '__new__') {
        emit('startInlineNewCollection');
    } else if (val === '' || val === 'null') {
        emit('update:uploadCollectionId', null);
    } else {
        emit('update:uploadCollectionId', isNaN(Number(val)) ? val : Number(val));
    }
}

const emit = defineEmits([
    'close',
    'update:importMode',
    'update:importUrls',
    'update:importLibraryId',
    'update:importSubfolder',
    'update:uploadTags',
    'update:uploadCollectionId',
    'update:uploadSourceUrl',
    'update:uploadDescription',
    'previewImportUrl',
    'startImport',
    'onFilesSelected',
    'startUpload',
    'addUploadTagSuggestion',
    'startInlineNewCollection',
    'confirmInlineNewCollection',
    'cancelInlineNewCollection',
    'pickNextCollectionColor',
    'updateInlineNewCollectionName',
    'updateInlineNewCollectionColor',
]);
</script>

<template>
    <div v-if="showImportModal" class="detail-overlay" @click.self="emit('close')">
        <div class="settings-panel" style="max-width:560px">
            <div class="detail-header">
                <div class="detail-title">Import Models</div>
                <button class="close-btn" @click="emit('close')" title="Close">&times;</button>
            </div>
            <div class="settings-content">
                <!-- Mode tabs -->
                <div class="import-tabs">
                    <button class="import-tab" :class="{ active: importMode === 'url' }" @click="emit('update:importMode', 'url')">
                        <span v-html="ICONS.link"></span> From URL
                    </button>
                    <button class="import-tab" :class="{ active: importMode === 'file' }" @click="emit('update:importMode', 'file')">
                        <span v-html="ICONS.download"></span> Upload Files
                    </button>
                </div>

                <!-- URL mode -->
                <template v-if="importMode === 'url'">
                    <div class="settings-section">
                        <div class="settings-section-desc">
                            Paste one or more URLs (one per line). Supports Thingiverse, MakerWorld, Printables, MyMiniFactory, Cults3D, Thangs, or direct download links.
                        </div>
                        <div class="form-row">
                            <textarea class="form-input import-textarea"
                                      :value="importUrls"
                                      @input="emit('update:importUrls', $event.target.value)"
                                      placeholder="https://www.thingiverse.com/thing/12345&#10;https://example.com/model.stl"
                                      rows="4"
                                      @blur="emit('previewImportUrl')"></textarea>
                        </div>
                    </div>

                    <!-- Preview -->
                    <div v-if="importPreview.loading" class="text-muted text-sm" style="padding:8px 0;display:flex;align-items:center;gap:8px">
                        <div class="spinner spinner-sm"></div> Fetching preview...
                    </div>
                    <div v-else-if="importPreview.data" class="import-preview-card">
                        <div v-if="importPreview.data.error" class="text-sm text-danger" style="padding:4px 0 8px">
                            {{ importPreview.data.error }}
                        </div>
                        <div v-if="importPreview.data.title" style="font-weight:600;margin-bottom:4px">{{ importPreview.data.title }}</div>
                        <div v-if="importPreview.data.source_site" class="text-muted text-sm" style="margin-bottom:4px;text-transform:capitalize">{{ importPreview.data.source_site }}</div>
                        <div v-if="importPreview.data.file_count" class="text-sm">{{ importPreview.data.file_count }} downloadable file(s)</div>
                        <div v-if="importPreview.data.tags && importPreview.data.tags.length" class="tags-list" style="margin-top:6px">
                            <span v-for="t in importPreview.data.tags.slice(0, 8)" :key="t" class="tag-chip">{{ t }}</span>
                            <span v-if="importPreview.data.tags.length > 8" class="tag-chip" style="opacity:0.7">+{{ importPreview.data.tags.length - 8 }}</span>
                        </div>
                    </div>
                </template>

                <!-- File upload mode -->
                <template v-if="importMode === 'file'">
                    <div class="settings-section">
                        <div class="settings-section-desc">
                            Select 3D model files to upload (.stl, .obj, .3mf, .step, .gltf, .glb, .ply, .zip).
                        </div>
                        <div class="form-row">
                            <label class="file-upload-area" :class="{ 'has-files': uploadFiles.length }">
                                <input type="file" multiple
                                       accept=".stl,.obj,.gltf,.glb,.3mf,.ply,.dae,.off,.step,.stp,.fbx,.zip"
                                       @change="emit('onFilesSelected', $event)"
                                       style="display:none">
                                <div v-if="!uploadFiles.length" class="file-upload-placeholder">
                                    <span v-html="ICONS.download"></span>
                                    <span>Click to select files or drag &amp; drop</span>
                                </div>
                                <div v-else class="file-upload-list">
                                    <div v-for="(f, i) in uploadFiles" :key="i" class="text-sm">{{ f.name }} ({{ formatFileSize(f.size) }})</div>
                                </div>
                            </label>
                        </div>
                    </div>

                    <!-- Zip metadata preview -->
                    <div v-if="uploadZipMeta" class="import-preview-card">
                        <div v-if="uploadZipMeta.title" style="font-weight:600;margin-bottom:4px">{{ uploadZipMeta.title }}</div>
                        <div v-if="uploadZipMeta.site" class="text-muted text-sm" style="margin-bottom:4px;text-transform:capitalize">
                            {{ uploadZipMeta.site }}
                        </div>
                        <a v-if="uploadZipMeta.source_url"
                           :href="uploadZipMeta.source_url" target="_blank" rel="noopener"
                           class="text-sm" style="color:var(--color-primary, #4f8cff)">{{ uploadZipMeta.source_url }}</a>
                        <div class="text-sm text-muted" style="margin-top:4px">
                            Zip will be extracted &mdash; model files inside will be imported individually
                        </div>
                    </div>

                    <!-- Source URL -->
                    <div v-if="uploadFiles.length" class="settings-section" style="margin-top:12px">
                        <div class="settings-section-title">Source URL</div>
                        <div class="form-row">
                            <input type="url" class="form-input" :value="uploadSourceUrl"
                                   @input="emit('update:uploadSourceUrl', $event.target.value)"
                                   placeholder="https://www.thingiverse.com/thing:12345">
                        </div>
                    </div>

                    <!-- Description -->
                    <div v-if="uploadFiles.length" class="settings-section" style="margin-top:12px">
                        <div class="settings-section-title">Description</div>
                        <div class="form-row">
                            <textarea class="form-input" :value="uploadDescription"
                                      @input="emit('update:uploadDescription', $event.target.value)"
                                      placeholder="Optional description for the uploaded model(s)"
                                      rows="2"></textarea>
                        </div>
                    </div>

                    <!-- Tags -->
                    <div v-if="uploadFiles.length" class="settings-section" style="margin-top:12px">
                        <div class="settings-section-title">Tags</div>
                        <div class="form-row">
                            <input type="text" class="form-input" :value="uploadTags"
                                   @input="emit('update:uploadTags', $event.target.value)"
                                   placeholder="comma-separated tags, e.g. benchy, calibration">
                        </div>
                        <div v-if="uploadTagSuggestions.length" class="tag-suggestions" style="margin-top:6px">
                            <span v-for="s in uploadTagSuggestions" :key="s"
                                  class="tag-chip tag-suggestion"
                                  @click="emit('addUploadTagSuggestion', s)"
                                  title="Click to add">+ {{ s }}</span>
                        </div>
                    </div>

                    <!-- Collection -->
                    <div v-if="uploadFiles.length" class="settings-section" style="margin-top:12px">
                        <div class="settings-section-title">
                            <span v-html="ICONS.collection"></span>
                            Add to Collection
                        </div>
                        <div class="form-row">
                            <select class="form-input" :value="uploadCollectionId"
                                    @change="onCollectionSelect">
                                <option :value="null">None</option>
                                <option v-for="col in collections" :key="col.id" :value="col.id">{{ col.name }}</option>
                                <option value="__new__">+ New Collection...</option>
                            </select>
                        </div>
                        <div v-if="uploadCollectionId === '__new__'" class="inline-new-collection" style="margin-top:8px">
                            <div style="display:flex;gap:8px;align-items:center">
                                <input class="form-input" :value="inlineNewCollection.name"
                                       @input="emit('updateInlineNewCollectionName', $event.target.value)"
                                       placeholder="Collection name"
                                       @keydown.enter="emit('confirmInlineNewCollection', 'upload')"
                                       @keydown.escape="emit('update:uploadCollectionId', null)"
                                       style="flex:1;padding:4px 8px;font-size:0.85rem" autofocus>
                                <button class="btn btn-primary btn-sm" @click="emit('confirmInlineNewCollection', 'upload')"
                                        :disabled="!inlineNewCollection.name.trim()">Create</button>
                            </div>
                            <div class="color-swatch-grid" style="margin-top:6px">
                                <button v-for="c in COLLECTION_COLORS" :key="c"
                                        class="color-swatch color-swatch-sm" :class="{ active: inlineNewCollection.color === c }"
                                        :style="{ background: c }"
                                        @click="emit('updateInlineNewCollectionColor', c)"
                                        type="button"></button>
                            </div>
                        </div>
                    </div>
                </template>

                <!-- Library + Subfolder (shared) -->
                <div class="settings-section" style="margin-top:16px">
                    <div class="settings-section-title">
                        <span v-html="ICONS.folder"></span>
                        Destination
                    </div>
                    <div class="form-row">
                        <label class="form-label">Library</label>
                        <select class="form-input" :value="importLibraryId"
                                @change="emit('update:importLibraryId', Number($event.target.value))">
                            <option v-for="lib in libraries" :key="lib.id" :value="lib.id">{{ lib.name }}</option>
                        </select>
                    </div>
                    <div class="form-row" style="margin-top:8px">
                        <label class="form-label">Subfolder (optional)</label>
                        <input type="text" class="form-input" :value="importSubfolder"
                               @input="emit('update:importSubfolder', $event.target.value)"
                               placeholder="e.g. imported/thingiverse">
                    </div>
                </div>

                <!-- Progress (URL mode) -->
                <div v-if="importRunning && importMode === 'url' && importProgress.total > 0" style="margin-top:16px">
                    <div class="regen-progress-bar">
                        <div class="regen-progress-fill" :style="{ width: Math.round((importProgress.completed / importProgress.total) * 100) + '%' }"></div>
                    </div>
                    <span class="text-muted text-sm" style="margin-top:4px;display:block">
                        {{ importProgress.completed }} / {{ importProgress.total }} URLs
                        <span v-if="importProgress.current_url" style="opacity:0.7"> &mdash; {{ importProgress.current_url }}</span>
                    </span>
                </div>

                <!-- Results (URL mode) -->
                <div v-if="importDone && importMode === 'url' && importProgress.results.length" class="import-results" style="margin-top:16px">
                    <div class="settings-section-title" style="margin-bottom:8px">Results</div>
                    <div v-for="(r, i) in importProgress.results" :key="i" class="import-result-row">
                        <span v-if="r.status === 'ok'" class="import-status-icon import-status-ok" title="Success">&#10003;</span>
                        <span v-else class="import-status-icon import-status-error" title="Failed">&#10007;</span>
                        <div class="import-result-detail">
                            <div class="import-result-url">{{ r.url }}</div>
                            <div v-if="r.status === 'ok'" class="text-sm" style="color:var(--color-success, #4caf50)">
                                {{ r.models.length }} model(s) imported
                            </div>
                            <div v-else class="text-sm" style="color:var(--color-danger, #ef4444)">
                                {{ r.error || 'Import failed' }}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Results (file upload mode) -->
                <div v-if="importDone && importMode === 'file' && uploadResults.length" class="import-results" style="margin-top:16px">
                    <div class="settings-section-title" style="margin-bottom:8px">Results</div>
                    <div v-for="(r, i) in uploadResults" :key="i" class="import-result-row">
                        <span v-if="r.status === 'ok'" class="import-status-icon import-status-ok" title="Success">&#10003;</span>
                        <span v-else class="import-status-icon import-status-error" title="Failed">&#10007;</span>
                        <div class="import-result-detail">
                            <div class="import-result-url">{{ r.filename }}</div>
                            <div v-if="r.status === 'ok'" class="text-sm" style="color:var(--color-success, #4caf50)">
                                Imported successfully
                            </div>
                            <div v-else class="text-sm" style="color:var(--color-danger, #ef4444)">
                                {{ r.error || 'Import failed' }}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Actions -->
                <div class="form-actions" style="margin-top:20px;display:flex;justify-content:flex-end;gap:8px">
                    <button v-if="importDone" class="btn btn-primary" @click="emit('close')">Done</button>
                    <template v-else-if="importMode === 'url'">
                        <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
                        <button class="btn btn-primary"
                                @click="emit('startImport')"
                                :disabled="importRunning || !importUrls.trim() || !importLibraryId">
                            <span v-html="ICONS.download"></span>
                            {{ importRunning ? 'Importing...' : 'Import' }}
                        </button>
                    </template>
                    <template v-else>
                        <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
                        <button class="btn btn-primary"
                                @click="emit('startUpload')"
                                :disabled="importRunning || !uploadFiles.length || !importLibraryId">
                            <span v-html="ICONS.download"></span>
                            {{ importRunning ? 'Uploading...' : 'Upload' }}
                        </button>
                    </template>
                </div>
            </div>
        </div>
    </div>
</template>
