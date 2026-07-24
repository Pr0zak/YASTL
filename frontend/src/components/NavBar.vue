<script setup>
/**
 * NavBar - Top navigation bar with search, view mode toggle, and action buttons.
 */
import { ICONS } from '../icons.js';

defineProps({
    searchQuery: { type: String, default: '' },
    viewMode: { type: String, default: 'grid' },
    gridDensity: { type: String, default: 'comfortable' },
    scanStatus: { type: Object, required: true },
    systemStatus: { type: Object, required: true },
    selectionMode: { type: Boolean, default: false },
    sidebarOpen: { type: Boolean, default: false },
});

const emit = defineEmits([
    'update:searchQuery',
    'update:viewMode',
    'toggleGridDensity',
    'update:sidebarOpen',
    'openSettings',
    'openImportModal',
    'toggleSelectionMode',
    'openStats',
    'openFilament',
    'searchInput',
    'clearSearch',
    'quickScan',
]);

function statusDotClass(status) {
    if (['ok', 'idle', 'watching'].includes(status)) return 'status-dot-ok';
    if (['busy', 'scanning', 'degraded', 'regenerating'].includes(status)) return 'status-dot-warn';
    if (['error', 'stopped', 'unavailable'].includes(status)) return 'status-dot-error';
    return 'status-dot-unknown';
}

function onSearchInput(e) {
    emit('searchInput', e);
}
</script>

<template>
    <nav class="navbar">
        <!-- Mobile sidebar toggle -->
        <button class="btn-icon sidebar-toggle" @click="emit('update:sidebarOpen', !sidebarOpen)"
                title="Toggle sidebar" v-html="ICONS.menu"></button>

        <!-- Brand -->
        <div class="navbar-brand">
            <svg class="navbar-logo" width="26" height="29" viewBox="0 0 100 110" aria-hidden="true">
                <g stroke="#2a3a5c" stroke-width="2" stroke-linejoin="round">
                    <polygon points="50,55 50,5 93,30" fill="#61afef"/>
                    <polygon points="50,55 93,30 93,80" fill="#44aacc"/>
                    <polygon points="50,55 93,80 50,105" fill="#2ec4b6"/>
                    <polygon points="50,55 50,105 7,80" fill="#12b5a6"/>
                    <polygon points="50,55 7,80 7,30" fill="#0f9b8e"/>
                    <polygon points="50,55 7,30 50,5" fill="#16213e"/>
                </g>
            </svg>
            <h1><span>YA</span>STL</h1>
            <a href="https://github.com/Pr0zak/YASTL" target="_blank" rel="noopener"
               class="btn-icon navbar-github" title="View on GitHub" v-html="ICONS.github"></a>
        </div>

        <!-- Search -->
        <div class="search-container">
            <span class="search-icon" v-html="ICONS.search"></span>
            <input type="text"
                   :value="searchQuery"
                   @input="onSearchInput"
                   placeholder="Search models..."
                   aria-label="Search models">
            <button v-if="searchQuery"
                    class="search-clear"
                    @click="emit('clearSearch')"
                    title="Clear search">&times;</button>
        </div>

        <!-- Actions -->
        <div class="navbar-actions">
            <div class="view-toggle">
                <button class="btn-ghost"
                        :class="{ active: viewMode === 'grid' }"
                        @click="emit('update:viewMode', 'grid')"
                        title="Grid view"
                        v-html="ICONS.grid"></button>
                <button class="btn-ghost"
                        :class="{ active: viewMode === 'list' }"
                        @click="emit('update:viewMode', 'list')"
                        title="List view"
                        v-html="ICONS.list"></button>
                <button v-if="viewMode === 'grid'" class="btn-ghost"
                        :class="{ active: gridDensity !== 'comfortable' }"
                        @click="emit('toggleGridDensity')"
                        :title="{
                            comfortable: 'Comfortable grid (click for compact)',
                            compact: 'Compact grid (click for minimal)',
                            minimal: 'Minimal grid — thumbnail + name only (click for comfortable)'
                        }[gridDensity] || 'Grid density'"
                        v-html="ICONS.menu"></button>
            </div>
            <!-- Stats & Status -->
            <div class="status-wrapper">
                <button class="btn-icon status-btn" :class="statusDotClass(systemStatus.health)"
                        @click="emit('openStats')" title="Stats &amp; Status">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                    <span class="status-dot" :class="statusDotClass(systemStatus.health)"></span>
                </button>
            </div>
            <button class="btn-icon" @click="emit('quickScan')" :disabled="scanStatus.scanning"
                    :title="scanStatus.scanning ? 'Scan in progress...' : 'Check for new files'">
                <span v-html="ICONS.refresh"></span>
            </button>
            <button class="btn-icon" @click="emit('openFilament')" title="Filament Inventory" v-html="ICONS.spool"></button>
            <button class="btn-icon" @click="emit('openImportModal')" title="Import Models">
                <span v-html="ICONS.upload"></span>
            </button>
            <button class="btn-icon" :class="{ active: selectionMode }" @click="emit('toggleSelectionMode')" title="Selection mode">
                <span v-html="ICONS.select"></span>
            </button>
            <button class="btn-icon" @click="emit('openSettings')" title="Settings" v-html="ICONS.settings"></button>
        </div>
    </nav>
</template>
