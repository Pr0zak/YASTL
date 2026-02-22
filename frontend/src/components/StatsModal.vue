<script setup>
/**
 * StatsModal - Library statistics dashboard with system status.
 */
import { ICONS } from '../icons.js';

defineProps({
    showStats: { type: Boolean, default: false },
    stats: { type: Object, default: null },
    statsLoading: { type: Boolean, default: false },
    systemStatus: { type: Object, default: () => ({ health: 'unknown', scanner: { status: 'unknown' }, watcher: { status: 'unknown' }, database: { status: 'unknown' }, thumbnails: { status: 'unknown' } }) },
});

const emit = defineEmits(['close']);

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
</script>

<template>
    <div v-if="showStats" class="detail-overlay" @click.self="emit('close')">
        <div class="settings-panel stats-panel">
            <!-- Header -->
            <div class="detail-header">
                <div class="detail-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                    Library Stats
                </div>
                <button class="close-btn" @click="emit('close')" title="Close">&times;</button>
            </div>

            <div class="settings-content" v-if="stats && !statsLoading">
                <!-- System Health -->
                <div class="stats-health">
                    <div class="stats-health-header">
                        <span>System</span>
                        <span class="status-badge" :class="statusDotClass(systemStatus.health)">
                            {{ statusLabel(systemStatus.health) }}
                        </span>
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
                        <div class="stats-card-label">Total Size</div>
                    </div>
                    <div class="stats-card">
                        <div class="stats-card-value">{{ stats.total_tags.toLocaleString() }}</div>
                        <div class="stats-card-label">Tags</div>
                    </div>
                    <div class="stats-card">
                        <div class="stats-card-value">{{ stats.total_favorites.toLocaleString() }}</div>
                        <div class="stats-card-label">Favorites</div>
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
                    <div class="stats-coverage-row" v-if="stats.duplicate_groups > 0">
                        <span class="stats-coverage-label">Duplicates</span>
                        <div class="stats-bar-track">
                            <div class="stats-bar-fill stats-bar-warn"
                                 :style="{ width: (stats.total_models ? (stats.duplicate_models / stats.total_models * 100) : 0) + '%' }"></div>
                        </div>
                        <span class="stats-coverage-value">{{ stats.duplicate_models }} files in {{ stats.duplicate_groups }} groups</span>
                    </div>
                </div>

                <!-- Formats -->
                <div class="settings-section">
                    <div class="settings-section-title">Formats</div>
                    <div class="stats-bar-list">
                        <div v-for="fmt in stats.formats" :key="fmt.file_format" class="stats-bar-row">
                            <span class="stats-bar-label">
                                <span class="format-badge" :class="fmt.file_format?.toLowerCase().replace('.', '')">
                                    {{ fmt.file_format }}
                                </span>
                            </span>
                            <div class="stats-bar-track">
                                <div class="stats-bar-fill" :style="{ width: barWidth(fmt.count, stats.formats[0]?.count) }"></div>
                            </div>
                            <span class="stats-bar-value">{{ fmt.count }} <span class="text-muted">({{ formatSize(fmt.total_size) }})</span></span>
                        </div>
                    </div>
                </div>

                <!-- Libraries -->
                <div class="settings-section" v-if="stats.libraries.length > 0">
                    <div class="settings-section-title">Libraries</div>
                    <div class="stats-bar-list">
                        <div v-for="lib in stats.libraries" :key="lib.id" class="stats-bar-row">
                            <span class="stats-bar-label stats-bar-label-wide">{{ lib.name }}</span>
                            <div class="stats-bar-track">
                                <div class="stats-bar-fill stats-bar-accent"
                                     :style="{ width: barWidth(lib.count, stats.libraries[0]?.count) }"></div>
                            </div>
                            <span class="stats-bar-value">{{ lib.count }} <span class="text-muted">({{ formatSize(lib.total_size) }})</span></span>
                        </div>
                    </div>
                </div>

                <!-- Top Tags -->
                <div class="settings-section" v-if="stats.top_tags.length > 0">
                    <div class="settings-section-title">Top Tags</div>
                    <div class="stats-tag-cloud">
                        <span v-for="tag in stats.top_tags" :key="tag.name" class="tag-chip">
                            {{ tag.name }} <span class="tag-count">{{ tag.count }}</span>
                        </span>
                    </div>
                </div>

                <!-- Largest Models -->
                <div class="settings-section" v-if="stats.largest_models.length > 0">
                    <div class="settings-section-title">Largest Models</div>
                    <div class="stats-bar-list">
                        <div v-for="model in stats.largest_models" :key="model.id" class="stats-bar-row">
                            <span class="stats-bar-label stats-bar-label-wide" :title="model.name">
                                {{ model.name }}
                            </span>
                            <div class="stats-bar-track">
                                <div class="stats-bar-fill stats-bar-purple"
                                     :style="{ width: barWidth(model.file_size, stats.largest_models[0]?.file_size) }"></div>
                            </div>
                            <span class="stats-bar-value">{{ formatSize(model.file_size) }}</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Loading -->
            <div v-else class="settings-content" style="display:flex;align-items:center;justify-content:center;min-height:200px">
                <div class="spinner"></div>
                <span style="margin-left:12px">Loading stats...</span>
            </div>
        </div>
    </div>
</template>

<style scoped>
.stats-panel {
    max-width: 640px;
}

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
    border-radius: 8px;
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

.stats-bar-accent { background: #44aacc; }
.stats-bar-purple { background: #a855f7; }
.stats-bar-warn { background: #f59e0b; }

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
    gap: 6px;
}

.tag-count {
    font-size: 0.65rem;
    opacity: 0.6;
    margin-left: 2px;
}

/* System health */
.stats-health {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
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

.stats-health-value.status-dot-ok { color: #22c55e; }
.stats-health-value.status-dot-warn { color: #f59e0b; }
.stats-health-value.status-dot-error { color: #ef4444; }
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
