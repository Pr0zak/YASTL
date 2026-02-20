/**
 * YASTL - Yet Another STL - Main Vue 3 Application
 */
import { initViewer, loadModel, disposeViewer, resetCamera } from './viewer.js';
import { debounce, formatFileSize, formatDate, formatNumber, formatDimensions } from './search.js';

const { createApp, ref, reactive, computed, onMounted, watch, nextTick } = Vue;

const app = createApp({
    setup() {
        // ===== State =====
        const models = ref([]);
        const selectedModel = ref(null);
        const searchQuery = ref('');
        const viewMode = ref('grid');
        const loading = ref(false);
        const showDetail = ref(false);
        const allTags = ref([]);
        const allCategories = ref([]);
        const newTagInput = ref('');
        const editingName = ref(false);
        const editingDesc = ref(false);
        const toasts = ref([]);

        const filters = reactive({
            format: '',
            tag: '',
            category: '',
        });

        const pagination = reactive({
            limit: 50,
            offset: 0,
            total: 0,
        });

        const scanStatus = reactive({
            scanning: false,
            total_files: 0,
            processed_files: 0,
        });

        let scanPollTimer = null;

        // ===== Computed =====
        const scanProgress = computed(() => {
            if (!scanStatus.total_files) return 0;
            return Math.round((scanStatus.processed_files / scanStatus.total_files) * 100);
        });

        const totalPages = computed(() => Math.ceil(pagination.total / pagination.limit));
        const currentPage = computed(() => Math.floor(pagination.offset / pagination.limit) + 1);

        const formatOptions = computed(() => {
            const formats = new Set(models.value.map(m => m.file_format));
            return [...formats].sort();
        });

        // ===== API Calls =====
        async function fetchModels() {
            loading.value = true;
            try {
                const params = new URLSearchParams({
                    limit: pagination.limit,
                    offset: pagination.offset,
                });
                if (filters.format) params.append('format', filters.format);
                if (filters.tag) params.append('tag', filters.tag);
                if (filters.category) params.append('category', filters.category);

                const res = await fetch(`/api/models?${params}`);
                const data = await res.json();
                models.value = data.models || [];
                pagination.total = data.total || 0;
            } catch (err) {
                showToast('Failed to load models', 'error');
                console.error(err);
            } finally {
                loading.value = false;
            }
        }

        async function searchModels() {
            if (!searchQuery.value.trim()) {
                pagination.offset = 0;
                return fetchModels();
            }
            loading.value = true;
            try {
                const params = new URLSearchParams({
                    q: searchQuery.value,
                    limit: pagination.limit,
                    offset: pagination.offset,
                });
                if (filters.format) params.append('format', filters.format);

                const res = await fetch(`/api/search?${params}`);
                const data = await res.json();
                models.value = data.models || [];
                pagination.total = data.total || 0;
            } catch (err) {
                showToast('Search failed', 'error');
                console.error(err);
            } finally {
                loading.value = false;
            }
        }

        const debouncedSearch = debounce(() => {
            pagination.offset = 0;
            searchModels();
        }, 300);

        async function fetchTags() {
            try {
                const res = await fetch('/api/tags');
                const data = await res.json();
                allTags.value = data.tags || data || [];
            } catch (err) {
                console.error('Failed to fetch tags:', err);
            }
        }

        async function fetchCategories() {
            try {
                const res = await fetch('/api/categories');
                const data = await res.json();
                allCategories.value = data.categories || data || [];
            } catch (err) {
                console.error('Failed to fetch categories:', err);
            }
        }

        async function fetchScanStatus() {
            try {
                const res = await fetch('/api/scan/status');
                const data = await res.json();
                scanStatus.scanning = data.scanning;
                scanStatus.total_files = data.total_files;
                scanStatus.processed_files = data.processed_files;

                if (data.scanning && !scanPollTimer) {
                    scanPollTimer = setInterval(fetchScanStatus, 2000);
                } else if (!data.scanning && scanPollTimer) {
                    clearInterval(scanPollTimer);
                    scanPollTimer = null;
                    fetchModels();
                    fetchTags();
                    fetchCategories();
                }
            } catch (err) {
                console.error('Failed to fetch scan status:', err);
            }
        }

        // ===== Actions =====
        async function triggerScan() {
            try {
                const res = await fetch('/api/scan', { method: 'POST' });
                const data = await res.json();
                if (res.ok) {
                    showToast('Library scan started');
                    scanStatus.scanning = true;
                    scanPollTimer = setInterval(fetchScanStatus, 2000);
                } else {
                    showToast(data.detail || 'Failed to start scan', 'error');
                }
            } catch (err) {
                showToast('Failed to start scan', 'error');
            }
        }

        async function viewModelDetail(model) {
            selectedModel.value = model;
            showDetail.value = true;
            await nextTick();
            initViewer('viewer-3d');
            const fileUrl = `/api/models/${model.id}/file`;
            loadModel(fileUrl, model.file_format);
        }

        function closeDetail() {
            showDetail.value = false;
            disposeViewer();
            selectedModel.value = null;
            editingName.value = false;
            editingDesc.value = false;
        }

        async function addTag() {
            const tag = newTagInput.value.trim();
            if (!tag || !selectedModel.value) return;
            try {
                const res = await fetch(`/api/models/${selectedModel.value.id}/tags`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tags: [tag] }),
                });
                if (res.ok) {
                    const updated = await res.json();
                    selectedModel.value = updated;
                    updateModelInList(updated);
                    newTagInput.value = '';
                    fetchTags();
                }
            } catch (err) {
                showToast('Failed to add tag', 'error');
            }
        }

        async function removeTag(tagName) {
            if (!selectedModel.value) return;
            try {
                const res = await fetch(
                    `/api/models/${selectedModel.value.id}/tags/${encodeURIComponent(tagName)}`,
                    { method: 'DELETE' }
                );
                if (res.ok) {
                    selectedModel.value.tags = selectedModel.value.tags.filter(t => t !== tagName);
                    updateModelInList(selectedModel.value);
                }
            } catch (err) {
                showToast('Failed to remove tag', 'error');
            }
        }

        async function updateModel(field, value) {
            if (!selectedModel.value) return;
            try {
                const res = await fetch(`/api/models/${selectedModel.value.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ [field]: value }),
                });
                if (res.ok) {
                    const updated = await res.json();
                    selectedModel.value = updated;
                    updateModelInList(updated);
                    showToast('Model updated');
                }
            } catch (err) {
                showToast('Failed to update model', 'error');
            }
            editingName.value = false;
            editingDesc.value = false;
        }

        async function deleteModel(model) {
            if (!confirm(`Delete "${model.name}"? This removes it from the library but not from disk.`)) return;
            try {
                const res = await fetch(`/api/models/${model.id}`, { method: 'DELETE' });
                if (res.ok) {
                    models.value = models.value.filter(m => m.id !== model.id);
                    pagination.total--;
                    if (showDetail.value) closeDetail();
                    showToast('Model removed from library');
                }
            } catch (err) {
                showToast('Failed to delete model', 'error');
            }
        }

        function updateModelInList(updated) {
            const idx = models.value.findIndex(m => m.id === updated.id);
            if (idx !== -1) models.value[idx] = { ...updated };
        }

        function setFilter(type, value) {
            filters[type] = filters[type] === value ? '' : value;
            pagination.offset = 0;
            fetchModels();
        }

        function goToPage(page) {
            pagination.offset = (page - 1) * pagination.limit;
            if (searchQuery.value.trim()) {
                searchModels();
            } else {
                fetchModels();
            }
        }

        function handleResetView() {
            resetCamera();
        }

        // ===== Toasts =====
        function showToast(message, type = 'success') {
            const id = Date.now();
            toasts.value.push({ id, message, type });
            setTimeout(() => {
                toasts.value = toasts.value.filter(t => t.id !== id);
            }, 3000);
        }

        // ===== Thumbnail URL =====
        function thumbUrl(model) {
            return `/api/models/${model.id}/thumbnail`;
        }

        function thumbError(e) {
            e.target.style.display = 'none';
            e.target.nextElementSibling?.style && (e.target.nextElementSibling.style.display = 'flex');
        }

        // ===== Lifecycle =====
        onMounted(() => {
            fetchModels();
            fetchTags();
            fetchCategories();
            fetchScanStatus();
        });

        watch(searchQuery, () => debouncedSearch());

        return {
            models, selectedModel, searchQuery, viewMode, loading, showDetail,
            allTags, allCategories, newTagInput, editingName, editingDesc,
            toasts, filters, pagination, scanStatus, scanProgress,
            totalPages, currentPage, formatOptions,
            fetchModels, triggerScan, viewModelDetail, closeDetail,
            addTag, removeTag, updateModel, deleteModel,
            setFilter, goToPage, handleResetView, showToast,
            thumbUrl, thumbError,
            formatFileSize, formatDate, formatNumber, formatDimensions,
        };
    },

    template: `
    <div class="app-root">
        <!-- Scan Progress Banner -->
        <div v-if="scanStatus.scanning" class="scan-banner">
            <div class="spinner"></div>
            <div class="progress-bar">
                <div class="progress-bar-fill" :style="{ width: scanProgress + '%' }"></div>
            </div>
            <span class="scan-text">
                Scanning... {{ scanStatus.processed_files }} / {{ scanStatus.total_files }}
            </span>
        </div>

        <!-- Navbar -->
        <nav class="navbar">
            <div class="navbar-brand">YASTL <span>Yet Another STL</span></div>

            <div class="search-wrapper">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
                <input class="search-input" type="text" v-model="searchQuery"
                       placeholder="Search models by name or description...">
            </div>

            <div class="navbar-actions">
                <button class="btn-icon" :class="{ active: viewMode === 'grid' }" @click="viewMode = 'grid'" title="Grid view">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                        <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
                        <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
                    </svg>
                </button>
                <button class="btn-icon" :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'" title="List view">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
                    </svg>
                </button>
                <button class="btn btn-primary" @click="triggerScan" :disabled="scanStatus.scanning">
                    Scan Library
                </button>
            </div>
        </nav>

        <!-- Main Layout -->
        <div class="app-layout">
            <!-- Sidebar -->
            <aside class="sidebar">
                <!-- Format Filters -->
                <div class="sidebar-section">
                    <div class="sidebar-title">Format</div>
                    <div v-for="fmt in ['STL','OBJ','glTF','GLB','3MF','STEP','PLY','FBX']" :key="fmt"
                         class="filter-item" :class="{ active: filters.format === fmt }"
                         @click="setFilter('format', fmt)">
                        <span class="format-badge">{{ fmt }}</span>
                    </div>
                </div>

                <!-- Tags -->
                <div class="sidebar-section">
                    <div class="sidebar-title">Tags</div>
                    <div v-if="allTags.length === 0" style="font-size:0.8rem;color:var(--text-muted)">
                        No tags yet
                    </div>
                    <div v-for="tag in allTags" :key="tag.id || tag.name"
                         class="filter-item" :class="{ active: filters.tag === (tag.name || tag) }"
                         @click="setFilter('tag', tag.name || tag)">
                        {{ tag.name || tag }}
                        <span v-if="tag.model_count != null" class="filter-count">{{ tag.model_count }}</span>
                    </div>
                </div>

                <!-- Categories -->
                <div class="sidebar-section">
                    <div class="sidebar-title">Categories</div>
                    <div v-if="allCategories.length === 0" style="font-size:0.8rem;color:var(--text-muted)">
                        No categories yet
                    </div>
                    <ul class="category-tree">
                        <li v-for="cat in allCategories" :key="cat.id">
                            <div class="category-item"
                                 :class="{ active: filters.category === cat.name }"
                                 @click="setFilter('category', cat.name)">
                                {{ cat.name }}
                            </div>
                            <ul v-if="cat.children && cat.children.length">
                                <li v-for="child in cat.children" :key="child.id">
                                    <div class="category-item"
                                         :class="{ active: filters.category === child.name }"
                                         @click="setFilter('category', child.name)">
                                        {{ child.name }}
                                    </div>
                                </li>
                            </ul>
                        </li>
                    </ul>
                </div>
            </aside>

            <!-- Main Content -->
            <main class="main-content">
                <!-- Toolbar -->
                <div class="toolbar">
                    <div class="toolbar-left">
                        <span class="model-count">{{ pagination.total }} model{{ pagination.total !== 1 ? 's' : '' }}</span>
                        <span v-if="filters.format || filters.tag || filters.category"
                              style="font-size:0.8rem;color:var(--text-muted)">
                            (filtered)
                            <button class="btn btn-sm" @click="filters.format=''; filters.tag=''; filters.category=''; fetchModels()">
                                Clear filters
                            </button>
                        </span>
                    </div>
                </div>

                <!-- Loading -->
                <div v-if="loading" class="loading-spinner">
                    <div class="spinner"></div>
                </div>

                <!-- Empty State -->
                <div v-else-if="models.length === 0" class="empty-state">
                    <div class="icon">&#9978;</div>
                    <h3>No models found</h3>
                    <p v-if="searchQuery">No results for "{{ searchQuery }}". Try a different search term.</p>
                    <p v-else>Your library is empty. Click "Scan Library" to import models from your directory.</p>
                    <button v-if="!searchQuery" class="btn btn-primary" @click="triggerScan" :disabled="scanStatus.scanning">
                        Scan Library
                    </button>
                </div>

                <!-- Grid View -->
                <div v-else-if="viewMode === 'grid'" class="model-grid fade-in">
                    <div v-for="model in models" :key="model.id"
                         class="model-card" @click="viewModelDetail(model)">
                        <div class="model-card-thumb">
                            <img :src="thumbUrl(model)" @error="thumbError" :alt="model.name">
                            <div class="placeholder-icon" style="display:none">&#9670;</div>
                        </div>
                        <div class="model-card-info">
                            <div class="model-card-name" :title="model.name">{{ model.name }}</div>
                            <div class="model-card-meta">
                                <span class="format-badge">{{ model.file_format }}</span>
                                <span class="file-size">{{ formatFileSize(model.file_size) }}</span>
                            </div>
                            <div v-if="model.tags && model.tags.length" class="model-card-tags">
                                <span v-for="t in model.tags.slice(0, 3)" :key="t" class="tag-chip">{{ t }}</span>
                                <span v-if="model.tags.length > 3" class="tag-chip">+{{ model.tags.length - 3 }}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- List View -->
                <table v-else class="model-table fade-in">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Format</th>
                            <th>Vertices</th>
                            <th>Faces</th>
                            <th>Size</th>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="model in models" :key="model.id" @click="viewModelDetail(model)">
                            <td style="color:var(--text-primary);font-weight:500">{{ model.name }}</td>
                            <td><span class="format-badge">{{ model.file_format }}</span></td>
                            <td>{{ formatNumber(model.vertex_count) }}</td>
                            <td>{{ formatNumber(model.face_count) }}</td>
                            <td>{{ formatFileSize(model.file_size) }}</td>
                            <td>{{ formatDate(model.created_at) }}</td>
                        </tr>
                    </tbody>
                </table>

                <!-- Pagination -->
                <div v-if="totalPages > 1" class="pagination">
                    <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)">Prev</button>
                    <span style="font-size:0.85rem;color:var(--text-secondary)">
                        Page {{ currentPage }} of {{ totalPages }}
                    </span>
                    <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">Next</button>
                </div>
            </main>
        </div>

        <!-- Detail Overlay -->
        <div v-if="showDetail && selectedModel" class="detail-overlay" @click.self="closeDetail">
            <div class="detail-panel">
                <div class="detail-header">
                    <h2 v-if="!editingName" @dblclick="editingName = true">
                        {{ selectedModel.name }}
                    </h2>
                    <input v-else class="editable-field" :value="selectedModel.name"
                           @blur="updateModel('name', $event.target.value)"
                           @keydown.enter="updateModel('name', $event.target.value)"
                           @keydown.escape="editingName = false"
                           autofocus style="max-width:400px">
                    <div style="display:flex;gap:8px">
                        <button class="btn btn-sm" @click="handleResetView">Reset View</button>
                        <a class="btn btn-sm" :href="'/api/models/' + selectedModel.id + '/file'" download>Download</a>
                        <button class="btn btn-sm btn-danger" @click="deleteModel(selectedModel)">Delete</button>
                        <button class="btn-icon" @click="closeDetail" title="Close">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="detail-body">
                    <div class="detail-viewer">
                        <div id="viewer-3d" style="width:100%;height:100%;min-height:400px"></div>
                    </div>
                    <div class="detail-sidebar">
                        <!-- Description -->
                        <div class="detail-section">
                            <div class="detail-section-title">Description</div>
                            <textarea v-if="editingDesc" class="editable-field" rows="3"
                                      :value="selectedModel.description"
                                      @blur="updateModel('description', $event.target.value)"
                                      @keydown.escape="editingDesc = false"></textarea>
                            <p v-else @dblclick="editingDesc = true"
                               style="font-size:0.85rem;color:var(--text-secondary);cursor:pointer;min-height:24px">
                                {{ selectedModel.description || 'Double-click to add a description...' }}
                            </p>
                        </div>

                        <!-- File Info -->
                        <div class="detail-section">
                            <div class="detail-section-title">File Information</div>
                            <div class="detail-field">
                                <span class="label">Format</span>
                                <span class="value"><span class="format-badge">{{ selectedModel.file_format }}</span></span>
                            </div>
                            <div class="detail-field">
                                <span class="label">File Size</span>
                                <span class="value">{{ formatFileSize(selectedModel.file_size) }}</span>
                            </div>
                            <div class="detail-field">
                                <span class="label">Vertices</span>
                                <span class="value">{{ formatNumber(selectedModel.vertex_count) }}</span>
                            </div>
                            <div class="detail-field">
                                <span class="label">Faces</span>
                                <span class="value">{{ formatNumber(selectedModel.face_count) }}</span>
                            </div>
                            <div class="detail-field">
                                <span class="label">Dimensions</span>
                                <span class="value">{{ formatDimensions(selectedModel.dimensions_x, selectedModel.dimensions_y, selectedModel.dimensions_z) }}</span>
                            </div>
                            <div class="detail-field">
                                <span class="label">Path</span>
                                <span class="value" style="font-size:0.75rem;word-break:break-all">{{ selectedModel.file_path }}</span>
                            </div>
                        </div>

                        <!-- Tags -->
                        <div class="detail-section">
                            <div class="detail-section-title">Tags</div>
                            <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">
                                <span v-for="tag in selectedModel.tags" :key="tag" class="tag-chip">
                                    {{ tag }}
                                    <span class="remove-tag" @click="removeTag(tag)">&times;</span>
                                </span>
                                <span v-if="!selectedModel.tags || !selectedModel.tags.length"
                                      style="font-size:0.8rem;color:var(--text-muted)">No tags</span>
                            </div>
                            <div class="tag-input-wrapper">
                                <input class="tag-input" v-model="newTagInput"
                                       placeholder="Add tag..."
                                       @keydown.enter="addTag">
                                <button class="btn btn-sm btn-primary" @click="addTag">Add</button>
                            </div>
                        </div>

                        <!-- Categories -->
                        <div class="detail-section">
                            <div class="detail-section-title">Categories</div>
                            <div style="display:flex;flex-wrap:wrap;gap:4px">
                                <span v-for="cat in selectedModel.categories" :key="cat" class="tag-chip">
                                    {{ cat }}
                                </span>
                                <span v-if="!selectedModel.categories || !selectedModel.categories.length"
                                      style="font-size:0.8rem;color:var(--text-muted)">Uncategorized</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Toasts -->
        <div class="toast-container">
            <div v-for="toast in toasts" :key="toast.id"
                 class="toast" :class="'toast-' + toast.type">
                {{ toast.message }}
            </div>
        </div>
    </div>
    `
});

app.mount('#app');
