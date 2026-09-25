<script setup>
/**
 * StatsModal - Library statistics dashboard with system status.
 */
import { ICONS } from '../icons.js';
import AppDialog from './AppDialog.vue';

defineProps({
    showStats: { type: Boolean, default: false },
    stats: { type: Object, default: null },
    statsLoading: { type: Boolean, default: false },
    systemStatus: { type: Object, default: () => ({ health: 'unknown', scanner: { status: 'unknown' }, watcher: { status: 'unknown' }, database: { status: 'unknown' }, thumbnails: { status: 'unknown' } }) },
    printInventory: { type: Array, default: () => [] },
});

// 'filter' asks the app to close this dialog and show the library narrowed to
// one format / library / collection / tag / duplicates; 'openModel' opens one.
const emit = defineEmits(['close', 'restartApp', 'filter', 'openModel']);

function formatSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}

function barWidth(value, max) {
    if (!max || !value) return '0%';
    return Math.max(2, Math.round((value / max) * 100)) + '%';
}

function statusLabel(status) {
    const labels = {
        ok: 'Healthy', busy: 'Busy', idle: 'Idle', scanning: 'Scanning',
        watching: 'Watching', regenerating: 'Regenerating', stopped: 'Stopped',
        degraded: 'Degraded', error: 'Error', unavailable: 'Unavailable', unknown: 'Unknown',
    };
    return labels[status] || status;
}

function statusDotClass(status) {
    if (['ok', 'idle', 'watching'].includes(status)) return 'status-dot-ok';
    if (['busy', 'scanning', 'degraded', 'regenerating'].includes(status)) return 'status-dot-warn';
    if (['error', 'stopped', 'unavailable'].includes(status)) return 'status-dot-error';
    return 'status-dot-unknown';
}

function tagFontSize(count, tags) {
    if (!tags || tags.length === 0) return '0.8rem';
    const max = tags[0].count;
    const min = tags[tags.length - 1].count;
    if (max === min) return '0.9rem';
    const t = (count - min) / (max - min);
    const size = 0.7 + t * 1.1;
    return size.toFixed(2) + 'rem';
}

function tagOpacity(count, tags) {
    if (!tags || tags.length === 0) return 1;
    const max = tags[0].count;
    const min = tags[tags.length - 1].count;
    if (max === min) return 1;
    const t = (count - min) / (max - min);
    return (0.5 + t * 0.5).toFixed(2);
}
</script>

<template>
    <AppDialog :show="showStats" title="Library stats" size="md" full-height-mobile @close="emit('close')">
            <div v-if="stats && !statsLoading">
                <!-- System Health -->
                <div class="stats-health">
                    <div class="stats-health-header">
                        <span>System</span>
                        <span class="status-badge" :class="statusDotClass(systemStatus.health)">
                            {{ statusLabel(systemStatus.health) }}
                        </span>
                        <button class="btn btn-secondary btn-sm stats-restart"
                                @click="emit('restartApp')" title="Restart the YASTL service">
                            <span v-html="ICONS.refresh"></span> Restart service
                        </button>
                    </div>
                    <div class="stats-health-items">
                        <div class="stats-health-item">
                            <span class="stats-health-icon" v-html="ICONS.scan"></span>
                            <span class="stats-health-label">Scanner</span>
                            <span class="stats-health-value" :class="statusDotClass(systemStatus.scanner.status)">
                                {{ statusLabel(systemStatus.scanner.status) }}
                            </span>
                        </div>
                        <div class="stats-health-item">
                            <span class="stats-health-icon" v-html="ICONS.eye"></span>
                            <span class="stats-health-label">Watcher</span>
                            <span class="stats-health-value" :class="statusDotClass(systemStatus.watcher.status)">
                                {{ statusLabel(systemStatus.watcher.status) }}
                            </span>
                        </div>
                        <div class="stats-health-item">
                            <span class="stats-health-icon" v-html="ICONS.database"></span>
                            <span class="stats-health-label">Database</span>
                            <span class="stats-health-value" :class="statusDotClass(systemStatus.database.status)">
                                {{ statusLabel(systemStatus.database.status) }}
                            </span>
                        </div>
                        <div class="stats-health-item">
                            <span class="stats-health-icon" v-html="ICONS.image"></span>
                            <span class="stats-health-label">Thumbnails</span>
                            <span class="stats-health-value" :class="statusDotClass(systemStatus.thumbnails.status)">
                                {{ systemStatus.thumbnails.regenerating ? 'Regenerating' : statusLabel(systemStatus.thumbnails.status) }}
                            </span>
                        </div>
                    </div>
                </div>

                <!-- Overview Cards -->
                <div class="stats-cards">
                    <div class="stats-card">
                        <div class="stats-card-value">{{ stats.total_models.toLocaleString() }}</div>
                        <div class="stats-card-label">Models</div>
                    </div>
                    <div class="stats-card">
                        <div class="stats-card-value">{{ formatSize(stats.total_size) }}</div>
                        <div class="stats-card-label">On disk</div>
                    </div>
                    <div class="stats-card">
                        <div class="stats-card-value">{{ stats.total_tags.toLocaleString() }}</div>
                        <div class="stats-card-label">Tags</div>
                    </div>
                    <div class="stats-card">
                        <div class="stats-card-value">{{ stats.total_favorites.toLocaleString() }}</div>
                        <div class="stats-card-label">Favourites</div>
                    </div>
                </div>

                <!-- Activity -->
                <div class="stats-row">
                    <div class="stats-card stats-card-sm">
                        <div class="stats-card-value">{{ stats.added_7d }}</div>
                        <div class="stats-card-label">Added (7d)</div>
                    </div>
                    <div class="stats-card stats-card-sm">
                        <div class="stats-card-value">{{ stats.added_30d }}</div>
                        <div class="stats-card-label">Added (30d)</div>
                    </div>
                    <div class="stats-card stats-card-sm">
                        <div class="stats-card-value">{{ stats.total_collections }}</div>
                        <div class="stats-card-label">Collections</div>
                    </div>
                    <div class="stats-card stats-card-sm">
                        <div class="stats-card-value">{{ stats.total_categories }}</div>
                        <div class="stats-card-label">Categories</div>
                    </div>
                </div>

                <!-- Coverage -->
                <div class="settings-section">
                    <div class="settings-section-title">Coverage</div>
                    <div class="stats-coverage-row">
                        <span class="stats-coverage-label">Thumbnails</span>
                        <div class="stats-bar-track">
                            <div class="stats-bar-fill" :style="{ width: stats.thumbnail_coverage + '%' }"></div>
                        </div>
                        <span class="stats-coverage-value">{{ stats.thumbnail_coverage }}%</span>
                    </div>
                    <div class="stats-coverage-row">
                        <span class="stats-coverage-label">Tagged</span>
                        <div class="stats-bar-track">
                            <div class="stats-bar-fill stats-bar-accent"
                                 :style="{ width: (stats.total_models ? (stats.tagged_models / stats.total_models * 100) : 0) + '%' }"></div>
                        </div>
                        <span class="stats-coverage-value">{{ stats.tagged_models }} / {{ stats.total_models }}</span>
                    </div>
                    <div class="stats-coverage-row">
                        <span class="stats-coverage-label">Source URLs</span>
                        <div class="stats-bar-track">
                            <div class="stats-bar-fill stats-bar-accent"
                                 :style="{ width: (stats.total_models ? (stats.sourced_models / stats.total_models * 100) : 0) + '%' }"></div>
                        </div>
                        <span class="stats-coverage-value">{{ stats.sourced_models }} / {{ stats.total_models }}</span>
                    </div>
                    <div class="stats-coverage-row">
                        <span class="stats-coverage-label">From Zips</span>
                        <div class="stats-bar-track">
                            <div class="stats-bar-fill stats-bar-purple"
                                 :style="{ width: (stats.total_models ? (stats.zip_models / stats.total_models * 100) : 0) + '%' }"></div>
                        </div>
                        <span class="stats-coverage-value">{{ stats.zip_models }}</span>
                    </div>
                    <button type="button" class="stats-coverage-row stats-link" v-if="stats.duplicate_groups > 0"
                            @click="emit('filter', { type: 'duplicates' })" title="Show duplicate files in the library">
                        <span class="stats-coverage-label">Duplicates</span>
                        <div class="stats-bar-track">
                            <div class="stats-bar-fill stats-bar-warn"
                                 :style="{ width: (stats.total_models ? (stats.duplicate_models / stats.total_models * 100) : 0) + '%' }"></div>
                        </div>
                        <span class="stats-coverage-value">{{ stats.duplicate_models }} files in {{ stats.duplicate_groups }} groups</span>
                        <span class="stats-link-chevron" v-html="ICONS.chevron"></span>
                    </button>
                </div>

                <!-- Formats -->
                <div class="settings-section">
                    <div class="settings-section-title">Formats</div>
                    <div class="stats-bar-list">
                        <button type="button" v-for="fmt in stats.formats" :key="fmt.file_format" class="stats-bar-row stats-link"
                                @click="emit('filter', { type: 'format', value: fmt.file_format })" :title="'Show ' + fmt.file_format + ' models'">
                            <span class="stats-bar-label">
                                <span class="format-badge">
                                    {{ fmt.file_format }}
                                </span>
                            </span>
                            <div class="stats-bar-track">
                                <div class="stats-bar-fill" :style="{ width: barWidth(fmt.count, stats.formats[0]?.count) }"></div>
                            </div>
                            <span class="stats-bar-value">{{ fmt.count }} <span class="text-muted">({{ formatSize(fmt.total_size) }})</span></span>
                            <span class="stats-link-chevron" v-html="ICONS.chevron"></span>
                        </button>
                    </div>
                </div>

                <!-- Libraries -->
                <div class="settings-section" v-if="stats.libraries.length > 0">
                    <div class="settings-section-title">Libraries</div>
                    <div class="stats-bar-list">
                        <button type="button" v-for="lib in stats.libraries" :key="lib.id" class="stats-bar-row stats-link"
                                @click="emit('filter', { type: 'library', value: lib.id })" :title="'Show ' + lib.name">
                            <span class="stats-bar-label stats-bar-label-wide">{{ lib.name }}</span>
                            <div class="stats-bar-track">
                                <div class="stats-bar-fill stats-bar-accent"
                                     :style="{ width: barWidth(lib.count, stats.libraries[0]?.count) }"></div>
                            </div>
                            <span class="stats-bar-value">{{ lib.count }} <span class="text-muted">({{ formatSize(lib.total_size) }})</span></span>
                            <span class="stats-link-chevron" v-html="ICONS.chevron"></span>
                        </button>
                    </div>
                </div>

                <!-- Prints by location (print pipeline) -->
                <div class="settings-section" v-if="printInventory.length > 0">
                    <div class="settings-section-title">Prints by location</div>
                    <div class="stats-bar-list">
                        <div v-for="loc in printInventory" :key="loc.location" class="stats-bar-row">
                            <span class="stats-bar-label stats-bar-label-wide" :title="loc.models.join(', ')">{{ loc.location }}</span>
                            <div class="stats-bar-track">
                                <div class="stats-bar-fill stats-bar-accent"
                                     :style="{ width: barWidth(loc.total_quantity, printInventory[0]?.total_quantity) }"></div>
                            </div>
                            <span class="stats-bar-value">
                                {{ loc.total_quantity }}
                                <span class="text-muted">({{ loc.distinct_models }} model{{ loc.distinct_models === 1 ? '' : 's' }})</span>
                            </span>
                        </div>
                    </div>
                </div>

                <!-- Collections -->
                <div class="settings-section" v-if="stats.collection_stats && stats.collection_stats.length > 0">
                    <div class="settings-section-title">Collections</div>
                    <div class="stats-bar-list">
                        <button type="button" v-for="col in stats.collection_stats" :key="col.id" class="stats-bar-row stats-link"
                                @click="emit('filter', { type: 'collection', value: col.id })" :title="'Show ' + col.name">
                            <span class="stats-bar-label stats-bar-label-wide stats-col-label" :title="col.name">
                                <span class="collection-dot" :style="{ background: col.color || 'var(--text-muted)' }"></span>
                                {{ col.name }}
                            </span>
                            <div class="stats-bar-track">
                                <div class="stats-bar-fill"
                                     :style="{ width: barWidth(col.count, stats.collection_stats[0]?.count), background: col.color || 'var(--accent)' }"></div>
                            </div>
                            <span class="stats-bar-value">{{ col.count }}</span>
                            <span class="stats-link-chevron" v-html="ICONS.chevron"></span>
                        </button>
                    </div>
                </div>

                <!-- Largest Models -->
                <div class="settings-section" v-if="stats.largest_models.length > 0">
                    <div class="settings-section-title">Largest Models</div>
                    <div class="stats-bar-list">
                        <button type="button" v-for="model in stats.largest_models" :key="model.id" class="stats-bar-row stats-link"
                                @click="emit('openModel', model.id)" :title="'Open ' + model.name">
                            <span class="stats-bar-label stats-bar-label-wide" :title="model.name">
                                {{ model.name }}
                            </span>
                            <div class="stats-bar-track">
                                <div class="stats-bar-fill stats-bar-purple"
                                     :style="{ width: barWidth(model.file_size, stats.largest_models[0]?.file_size) }"></div>
                            </div>
                            <span class="stats-bar-value">{{ formatSize(model.file_size) }}</span>
                            <span class="stats-link-chevron" v-html="ICONS.chevron"></span>
                        </button>
                    </div>
                </div>
                <!-- Tag Cloud -->
                <div class="settings-section" v-if="stats.top_tags.length > 0">
                    <div class="settings-section-title">Tag Cloud</div>
                    <div class="stats-tag-cloud">
                        <button type="button" v-for="tag in stats.top_tags" :key="tag.name"
                              class="cloud-tag"
                              :style="{ fontSize: tagFontSize(tag.count, stats.top_tags), opacity: tagOpacity(tag.count, stats.top_tags) }"
                              :title="tag.name + ': ' + tag.count + ' models'"
                              @click="emit('filter', { type: 'tag', value: tag.name })">
                            {{ tag.name }}
                        </button>
                    </div>
                </div>

            </div>

            <!-- Loading -->
            <div v-else class="stats-loading">
                <div class="spinner"></div>
                <span>Loading stats…</span>
            </div>
    </AppDialog>
</template>

<style scoped>
.stats-loading { display: flex; align-items: center; justify-content: center; gap: 12px; min-height: 200px; }
.stats-restart { margin-left: auto; min-height: 32px; }
.stats-link {
    width: 100%; background: none; color: inherit; font: inherit; text-align: left;
    border-radius: var(--radius-sm); padding: 4px 6px; margin: 0 -6px; box-sizing: content-box;
    min-height: 28px;
}
.stats-link:hover { background: var(--bg-hover); }
.stats-link:hover .stats-link-chevron { opacity: 1; }
.stats-link-chevron { display: flex; color: var(--text-muted); opacity: 0.4; flex: none; }
.stats-col-label { display: flex; align-items: center; gap: 6px; }

.stats-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 16px;
}

.stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 16px;
}

.stats-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 10px;
    text-align: center;
}

.stats-card-sm {
    padding: 10px 8px;
}

.stats-card-value {
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
}

.stats-card-sm .stats-card-value {
    font-size: 1.1rem;
}

.stats-card-label {
    font-size: 0.7rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 4px;
}

/* Coverage & bar charts */
.stats-coverage-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
}

.stats-coverage-label {
    width: 90px;
    font-size: 0.8rem;
    color: var(--text-secondary);
    flex-shrink: 0;
}

.stats-coverage-value {
    font-size: 0.8rem;
    color: var(--text-muted);
    flex-shrink: 0;
    min-width: 60px;
    text-align: right;
}

.stats-bar-track {
    flex: 1;
    height: 8px;
    background: var(--bg-primary);
    border-radius: 4px;
    overflow: hidden;
}

.stats-bar-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 4px;
    transition: width 0.3s ease;
    min-width: 2px;
}

.stats-bar-accent { background: var(--info); }
.stats-bar-purple { background: var(--purple); }
.stats-bar-warn { background: var(--warning); }

.stats-bar-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.stats-bar-row {
    display: flex;
    align-items: center;
    gap: 10px;
}

.stats-bar-label {
    width: 60px;
    flex-shrink: 0;
    font-size: 0.8rem;
}

.stats-bar-label-wide {
    width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.stats-bar-value {
    font-size: 0.8rem;
    color: var(--text-secondary);
    flex-shrink: 0;
    min-width: 80px;
    text-align: right;
}

.stats-tag-cloud {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 10px;
    padding: 8px 4px;
    line-height: 1.6;
}

.cloud-tag {
    background: none;
    font-family: inherit;
    color: var(--accent-hover);
    cursor: pointer;
    transition: opacity 0.2s;
    white-space: nowrap;
}

.cloud-tag:hover {
    opacity: 1 !important;
    text-decoration: underline;
}

/* System health */
.stats-health {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px 14px;
    margin-bottom: 16px;
}

.stats-health-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
    font-weight: 600;
    font-size: 0.85rem;
}

.stats-health-items {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
}

.stats-health-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    font-size: 0.75rem;
}

.stats-health-icon {
    opacity: 0.5;
}

.stats-health-icon :deep(svg) {
    width: 14px;
    height: 14px;
}

.stats-health-label {
    color: var(--text-muted);
}

.stats-health-value {
    font-weight: 600;
    font-size: 0.7rem;
}

.stats-health-value.status-dot-ok { color: var(--success); }
.stats-health-value.status-dot-warn { color: var(--warning); }
.stats-health-value.status-dot-error { color: var(--danger); }
.stats-health-value.status-dot-unknown { color: var(--text-muted); }

@media (max-width: 640px) {
    .stats-cards,
    .stats-row {
        grid-template-columns: repeat(2, 1fr);
    }
    .stats-health-items {
        grid-template-columns: repeat(2, 1fr);
    }
}
</style>
