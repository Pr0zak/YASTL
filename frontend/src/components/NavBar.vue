<script setup>
/**
 * NavBar - Top navigation bar with search, view mode toggle, and action buttons.
 */
import { ICONS } from '../icons.js';

defineProps({
    searchQuery: { type: String, default: '' },
    viewMode: { type: String, default: 'grid' },
    scanStatus: { type: Object, required: true },
    systemStatus: { type: Object, required: true },
    selectionMode: { type: Boolean, default: false },
    sidebarOpen: { type: Boolean, default: false },
});

const emit = defineEmits([
    'update:searchQuery',
    'update:viewMode',
    'update:sidebarOpen',
    'openSettings',
    'openImportModal',
    'toggleSelectionMode',
    'toggleStatusMenu',
    'searchInput',
    'clearSearch',
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
            <h1><span>YA</span>STL</h1>
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
            </div>
            <!-- Status Indicator -->
            <div class="status-wrapper" @click.stop>
                <button class="btn-icon status-btn" :class="statusDotClass(systemStatus.health)"
                        @click="emit('toggleStatusMenu')" title="System Status">
                    <span v-html="ICONS.activity"></span>
                    <span class="status-dot" :class="statusDotClass(systemStatus.health)"></span>
                </button>
            </div>

            <button class="btn-icon" @click="emit('openImportModal')" title="Import Models">
                <span v-html="ICONS.link"></span>
            </button>
            <button class="btn-icon" :class="{ active: selectionMode }" @click="emit('toggleSelectionMode')" title="Selection mode">
                <span v-html="ICONS.select"></span>
            </button>
            <button class="btn-icon" @click="emit('openSettings')" title="Settings" v-html="ICONS.settings"></button>
        </div>
    </nav>
</template>
