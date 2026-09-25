<script setup>
/**
 * ImportModal - Import/upload modal for URL imports and file uploads.
 */
import { ref, computed } from 'vue';
import { ICONS } from '../icons.js';
import { formatFileSize } from '../search.js';
import AppDialog from './AppDialog.vue';

const dragOver = ref(false);
const fileInput = ref(null);
const showDetails = ref(false);
const editDest = ref(false);

const props = defineProps({
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
    uploadName: { type: String, default: '' },
    uploadSourceUrl: { type: String, default: '' },
    uploadDescription: { type: String, default: '' },
    uploadZipMeta: { default: null },
    libraries: { type: Array, default: () => [] },
    collections: { type: Array, default: () => [] },
    inlineNewCollection: { type: Object, default: () => ({ active: false, name: '', color: '#4f8cff' }) },
    COLLECTION_COLORS: { type: Array, default: () => [] },
});

function onDrop(e) {
    dragOver.value = false;
    if (e.dataTransfer && e.dataTransfer.files.length) {
        emit('onFilesSelected', { target: { files: e.dataTransfer.files } });
    }
}

const destinationLabel = computed(() => {
    const lib = props.libraries.find((l) => l.id === props.importLibraryId);
    const name = lib ? lib.name : 'Choose a library';
    return props.importSubfolder ? `${name} / ${props.importSubfolder}` : name;
});

const canImport = computed(() => {
    if (props.importRunning || !props.importLibraryId) return false;
    return props.importMode === 'url' ? !!props.importUrls.trim() : props.uploadFiles.length > 0;
});

function onImport() {
    emit(props.importMode === 'url' ? 'startImport' : 'startUpload');
}

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
    'setImportUrls',
    'clearFiles',
    'update:importLibraryId',
    'update:importSubfolder',
    'update:uploadTags',
    'update:uploadCollectionId',
    'update:uploadName',
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
    <AppDialog :show="showImportModal" title="Import models" size="md" :dismiss-on-backdrop="!importRunning"
               @close="emit('close')">
        <template v-if="!importDone">
            <!-- One box: drop files, browse, or paste links -->
            <div class="import-drop"
                 :class="{ 'drag-over': dragOver, 'has-files': uploadFiles.length }"
                 @dragover.prevent="dragOver = true"
                 @dragleave.prevent="dragOver = false"
                 @drop.prevent="onDrop">
                <input ref="fileInput" id="import-file-input" type="file" multiple class="visually-hidden"
                       accept=".stl,.obj,.gltf,.glb,.3mf,.ply,.dae,.off,.step,.stp,.fbx,.zip"
                       @change="emit('onFilesSelected', $event)">
                <template v-if="!uploadFiles.length">
                    <span class="import-drop-icon" v-html="ICONS.upload"></span>
                    <div class="import-drop-title">Drop files here or
                        <button type="button" class="import-browse" @click="fileInput?.click()">browse</button>
                    </div>
                    <div class="import-drop-hint">STL · 3MF · OBJ · STEP · GLB · PLY · FBX · ZIP</div>
                </template>
                <template v-else>
                    <ul class="import-file-list">
                        <li v-for="(f, i) in uploadFiles" :key="i">
                            <span class="import-file-name">{{ f.name }}</span>
                            <span class="import-file-size">{{ formatFileSize(f.size) }}</span>
                        </li>
                    </ul>
                    <div class="import-file-actions">
                        <button type="button" class="btn btn-ghost btn-sm" @click="fileInput?.click()">Choose different files</button>
                        <button type="button" class="btn btn-ghost btn-sm" @click="emit('clearFiles')">Clear</button>
                    </div>
                </template>
            </div>

            <template v-if="!uploadFiles.length">
                <div class="import-or"><span>or paste links</span></div>
                <textarea id="import-urls" class="form-input import-textarea"
                          :value="importUrls"
                          @input="emit('setImportUrls', $event.target.value)"
                          aria-label="Model page links, one per line"
                          placeholder="https://www.printables.com/model/…&#10;One link per line: Printables, Thingiverse, MakerWorld, MyMiniFactory, Cults3D, Thangs, or a direct file"
                          rows="2"
                          @blur="emit('previewImportUrl')"></textarea>
            </template>

            <!-- Link preview -->
            <div v-if="importMode === 'url' && importPreview.loading" class="import-status-line">
                <div class="spinner spinner-sm"></div> Fetching preview…
            </div>
            <div v-else-if="importMode === 'url' && importPreview.data" class="import-preview-card">
                <div v-if="importPreview.data.error" class="text-sm text-danger">{{ importPreview.data.error }}</div>
                <div v-if="importPreview.data.title" class="import-preview-title">{{ importPreview.data.title }}</div>
                <div class="text-muted text-sm">
                    <span v-if="importPreview.data.source_site" class="import-site">{{ importPreview.data.source_site }}</span>
                    <span v-if="importPreview.data.file_count"> · {{ importPreview.data.file_count }} downloadable file{{ importPreview.data.file_count === 1 ? '' : 's' }}</span>
                </div>
                <div v-if="importPreview.data.tags && importPreview.data.tags.length" class="tags-list">
                    <span v-for="t in importPreview.data.tags.slice(0, 8)" :key="t" class="tag-chip">{{ t }}</span>
                    <span v-if="importPreview.data.tags.length > 8" class="tag-chip tag-chip-more">+{{ importPreview.data.tags.length - 8 }}</span>
                </div>
            </div>

            <!-- Zip metadata preview -->
            <div v-if="uploadZipMeta" class="import-preview-card">
                <div v-if="uploadZipMeta.title" class="import-preview-title">{{ uploadZipMeta.title }}</div>
                <a v-if="uploadZipMeta.source_url" :href="uploadZipMeta.source_url" target="_blank" rel="noopener" class="text-sm">
                    {{ uploadZipMeta.source_url }}
                </a>
                <div class="text-sm text-muted">The zip is unpacked and each model inside is imported on its own.</div>
            </div>

            <!-- Optional details for uploads -->
            <div v-if="uploadFiles.length" class="import-details">
                <button type="button" class="import-details-toggle" :aria-expanded="String(showDetails)" @click="showDetails = !showDetails">
                    <span class="sidebar-section-chevron" :class="{ expanded: showDetails }" v-html="ICONS.chevron"></span>
                    Name, tags and collection <span class="text-muted">(optional)</span>
                </button>
                <div v-if="showDetails" class="import-details-body">
                    <div class="form-row">
                        <label class="form-label" for="upload-name">Name</label>
                        <input id="upload-name" type="text" class="form-input" :value="uploadName"
                               @input="emit('update:uploadName', $event.target.value)" placeholder="Defaults to the file name">
                    </div>
                    <div class="form-row">
                        <label class="form-label" for="upload-source">Source link</label>
                        <input id="upload-source" type="url" class="form-input" :value="uploadSourceUrl"
                               @input="emit('update:uploadSourceUrl', $event.target.value)" placeholder="https://www.thingiverse.com/thing:12345">
                    </div>
                    <div class="form-row">
                        <label class="form-label" for="upload-desc">Description</label>
                        <textarea id="upload-desc" class="form-input" :value="uploadDescription" rows="2"
                                  @input="emit('update:uploadDescription', $event.target.value)"></textarea>
                    </div>
                    <div class="form-row">
                        <label class="form-label" for="upload-tags">Tags, separated by commas</label>
                        <input id="upload-tags" type="text" class="form-input" :value="uploadTags"
                               @input="emit('update:uploadTags', $event.target.value)" placeholder="benchy, calibration">
                        <div v-if="uploadTagSuggestions.length" class="tag-suggestions">
                            <button v-for="sug in uploadTagSuggestions" :key="sug" type="button"
                                    class="tag-chip tag-suggestion" @click="emit('addUploadTagSuggestion', sug)">+ {{ sug }}</button>
                        </div>
                    </div>
                    <div class="form-row">
                        <label class="form-label" for="upload-collection">Add to collection</label>
                        <select id="upload-collection" class="form-input" :value="uploadCollectionId" @change="onCollectionSelect">
                            <option :value="null">None</option>
                            <option v-for="col in collections" :key="col.id" :value="col.id">{{ col.name }}</option>
                            <option value="__new__">+ New collection…</option>
                        </select>
                        <div v-if="uploadCollectionId === '__new__'" class="inline-new-collection">
                            <div class="import-inline-row">
                                <input class="form-input" :value="inlineNewCollection.name" aria-label="New collection name"
                                       @input="emit('updateInlineNewCollectionName', $event.target.value)"
                                       placeholder="Collection name"
                                       @keydown.enter.prevent="emit('confirmInlineNewCollection', 'upload')"
                                       @keydown.escape.stop="emit('update:uploadCollectionId', null)">
                                <button type="button" class="btn btn-primary" @click="emit('confirmInlineNewCollection', 'upload')"
                                        :disabled="!inlineNewCollection.name.trim()">Create</button>
                            </div>
                            <div class="color-swatch-grid" role="radiogroup" aria-label="Collection colour">
                                <button v-for="c in COLLECTION_COLORS" :key="c" type="button"
                                        class="color-swatch color-swatch-sm" :class="{ active: inlineNewCollection.color === c }"
                                        :style="{ background: c }" role="radio" :aria-checked="String(inlineNewCollection.color === c)"
                                        :aria-label="'Colour ' + c"
                                        @click="emit('updateInlineNewCollectionColor', c)"></button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Progress (links) -->
            <div v-if="importRunning && importMode === 'url' && importProgress.total > 0" class="import-progress">
                <div class="regen-progress-bar">
                    <div class="regen-progress-fill" :style="{ width: Math.round((importProgress.completed / importProgress.total) * 100) + '%' }"></div>
                </div>
                <span class="text-muted text-sm">
                    {{ importProgress.completed }} of {{ importProgress.total }} links
                    <span v-if="importProgress.current_url" class="import-current"> · {{ importProgress.current_url }}</span>
                </span>
            </div>
        </template>

        <!-- Results -->
        <div v-else class="import-results">
            <template v-if="importMode === 'url'">
                <div v-for="(r, i) in importProgress.results" :key="i" class="import-result-row">
                    <span class="import-status-icon" :class="r.status === 'ok' ? 'import-status-ok' : 'import-status-error'"
                          v-html="r.status === 'ok' ? ICONS.check : ICONS.close"></span>
                    <div class="import-result-detail">
                        <div class="import-result-url">{{ r.url }}</div>
                        <div v-if="r.status === 'ok'" class="text-sm import-ok">{{ r.models.length }} model{{ r.models.length === 1 ? '' : 's' }} imported</div>
                        <div v-else class="text-sm text-danger">{{ r.error || 'Import failed' }}</div>
                    </div>
                </div>
            </template>
            <template v-else>
                <div v-for="(r, i) in uploadResults" :key="i" class="import-result-row">
                    <span class="import-status-icon" :class="r.status === 'ok' ? 'import-status-ok' : 'import-status-error'"
                          v-html="r.status === 'ok' ? ICONS.check : ICONS.close"></span>
                    <div class="import-result-detail">
                        <div class="import-result-url">{{ r.filename }}</div>
                        <div v-if="r.status === 'ok'" class="text-sm import-ok">Imported</div>
                        <div v-else class="text-sm text-danger">{{ r.error || 'Import failed' }}</div>
                    </div>
                </div>
            </template>
        </div>

        <template #footer>
            <template v-if="importDone">
                <button class="btn btn-primary" @click="emit('close')">Done</button>
            </template>
            <template v-else>
                <div class="import-dest">
                    <template v-if="!editDest">
                        <span class="text-muted">Into</span>
                        <button type="button" class="import-dest-btn" @click="editDest = true" title="Change destination">
                            <span v-html="ICONS.folder"></span>{{ destinationLabel }}
                        </button>
                    </template>
                    <template v-else>
                        <select class="form-input import-dest-lib" :value="importLibraryId" aria-label="Library"
                                @change="emit('update:importLibraryId', Number($event.target.value))">
                            <option v-for="lib in libraries" :key="lib.id" :value="lib.id">{{ lib.name }}</option>
                        </select>
                        <input type="text" class="form-input import-dest-sub" :value="importSubfolder" aria-label="Subfolder (optional)"
                               @input="emit('update:importSubfolder', $event.target.value)" placeholder="subfolder (optional)"
                               @keydown.enter.prevent="editDest = false">
                        <button type="button" class="btn btn-ghost btn-sm" @click="editDest = false">OK</button>
                    </template>
                </div>
                <span class="footer-spacer"></span>
                <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
                <button class="btn btn-primary" @click="onImport" :disabled="!canImport">
                    <span v-html="ICONS.download"></span>
                    {{ importRunning ? 'Importing…' : 'Import' }}
                </button>
            </template>
        </template>
    </AppDialog>
</template>

<style scoped>
.import-drop {
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
    min-height: 150px; padding: 20px; text-align: center;
    border: 2px dashed var(--border-light); border-radius: var(--radius-lg);
    background: var(--bg-card); transition: border-color var(--transition), background var(--transition);
}
.import-drop.drag-over { border-color: var(--accent-hover); background: var(--accent-dim); }
.import-drop.has-files { align-items: stretch; text-align: left; border-style: solid; min-height: 0; }
.import-drop-icon { color: var(--accent-hover); display: flex; }
.import-drop-icon :deep(svg) { width: 28px; height: 28px; }
.import-drop-title { font-weight: 600; color: var(--text-primary); }
.import-drop-hint { font-size: 0.75rem; color: var(--text-muted); letter-spacing: 0.03em; }
.import-browse { background: none; color: var(--accent-hover); font-weight: 600; text-decoration: underline; padding: 0; font-size: inherit; }
.import-file-list { list-style: none; display: flex; flex-direction: column; gap: 4px; max-height: 160px; overflow-y: auto; }
.import-file-list li { display: flex; gap: 10px; font-size: 0.85rem; }
.import-file-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.import-file-size { color: var(--text-muted); font-variant-numeric: tabular-nums; }
.import-file-actions { display: flex; gap: 6px; margin-top: 6px; }
.import-or { display: flex; align-items: center; gap: 10px; margin: 14px 0 8px; color: var(--text-muted); font-size: 0.78rem; }
.import-or::before, .import-or::after { content: ''; flex: 1; height: 1px; background: var(--border); }
.import-status-line { display: flex; align-items: center; gap: 8px; padding: 10px 0; font-size: 0.85rem; color: var(--text-muted); }
.import-preview-card { margin-top: 12px; display: flex; flex-direction: column; gap: 4px; }
.import-preview-title { font-weight: 600; }
.import-site { text-transform: capitalize; }
.tag-chip-more { opacity: 0.7; }
.import-details { margin-top: 12px; border: 1px solid var(--border); border-radius: var(--radius); }
.import-details-toggle {
    width: 100%; display: flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 12px;
    background: none; color: var(--text-primary); font-size: 0.85rem; font-weight: 500; text-align: left;
}
.import-details-body { padding: 0 12px 12px; }
.tag-suggestions { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.inline-new-collection { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.import-inline-row { display: flex; gap: 8px; }
.import-inline-row .form-input { flex: 1; min-width: 0; }
.import-progress { margin-top: 14px; display: flex; flex-direction: column; gap: 4px; }
.import-current { opacity: 0.7; word-break: break-all; }
.import-ok { color: var(--success); }
.import-dest { display: flex; align-items: center; gap: 6px; min-width: 0; font-size: 0.85rem; flex-wrap: wrap; }
.import-dest-btn {
    display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 0 10px; max-width: 240px;
    background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); border-radius: 99px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.import-dest-btn:hover { border-color: var(--border-light); }
.import-dest-lib { width: auto; min-height: 36px; }
.import-dest-sub { width: 170px; min-height: 36px; }
@media (max-width: 768px) {
    .import-dest { width: 100%; }
    .import-dest-btn { max-width: none; flex: 1; }
    .import-dest-sub { flex: 1; width: auto; }
}
</style>
