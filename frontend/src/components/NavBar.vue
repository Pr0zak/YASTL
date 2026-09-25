<script setup>
/**
 * NavBar - Top navigation bar with search, view mode toggle, and action buttons.
 */
import { ref, watch, nextTick, onBeforeUnmount } from 'vue';
import { ICONS } from '../icons.js';

const props = defineProps({
    searchQuery: { type: String, default: '' },
    scanStatus: { type: Object, required: true },
    queueCount: { type: Number, default: 0 },
    systemStatus: { type: Object, required: true },
    selectionMode: { type: Boolean, default: false },
    sidebarOpen: { type: Boolean, default: false },
});

const emit = defineEmits([
    'update:searchQuery',
    'update:sidebarOpen',
    'openSettings',
    'openImportModal',
    'toggleSelectionMode',
    'openStats',
    'openFilament',
    'openQueue',
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

// Everything that is not search, Import or the health/stats button lives in
// one menu at every width. The bar used to carry seven unlabelled icons, whose
// names only appeared as hover tooltips — which a touch screen never shows.
const MENU_ACTIONS = [
    { key: 'scan', label: 'Check for new files', icon: 'refresh', event: 'quickScan' },
    { key: 'queue', label: 'Print queue', icon: 'queue', event: 'openQueue' },
    { key: 'filament', label: 'Filament', icon: 'spool', event: 'openFilament' },
    { key: 'select', label: 'Select models', icon: 'select', event: 'toggleSelectionMode' },
    { key: 'stats', label: 'Library stats', icon: 'stats', event: 'openStats', phoneOnly: true },
    { key: 'settings', label: 'Settings', icon: 'settings', event: 'openSettings' },
];

const HEALTH_LABEL = {
    'status-dot-ok': 'healthy', 'status-dot-warn': 'busy', 'status-dot-error': 'needs attention', 'status-dot-unknown': 'status unknown',
};

const navOverflowOpen = ref(false);
const navOverflowEl = ref(null);

const menuBtn = ref(null);
function fireAction(a) {
    navOverflowOpen.value = false;
    emit(a.event);
}
function onMenuKey(e) {
    const items = [...(navOverflowEl.value?.querySelectorAll('.nav-overflow-item:not(:disabled)') || [])];
    const i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length]?.focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length]?.focus(); }
}

function onNavOutside(e) {
    if (navOverflowEl.value && !navOverflowEl.value.contains(e.target)) navOverflowOpen.value = false;
}
function onNavKey(e) {
    if (e.key === 'Escape' && navOverflowOpen.value) {
        e.stopPropagation();
        navOverflowOpen.value = false;
        menuBtn.value?.focus();
    }
}
watch(navOverflowOpen, async (open) => {
    if (open) {
        await nextTick();
        navOverflowEl.value?.querySelector('.nav-overflow-item')?.focus();
    }
    const m = open ? 'addEventListener' : 'removeEventListener';
    document[m]('pointerdown', onNavOutside, true);
    document[m]('keydown', onNavKey, true);
});
onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', onNavOutside, true);
    document.removeEventListener('keydown', onNavKey, true);
});
</script>

<template>
    <nav class="navbar" aria-label="Main">
        <button class="btn-icon sidebar-toggle" @click="emit('update:sidebarOpen', !sidebarOpen)"
                :aria-expanded="String(sidebarOpen)"
                :title="sidebarOpen ? 'Hide collections' : 'Show collections'"
                :aria-label="sidebarOpen ? 'Hide collections' : 'Show collections'" v-html="ICONS.sidebar"></button>

        <div class="navbar-brand">
            <svg class="navbar-logo" width="26" height="29" viewBox="0 0 100 110" aria-hidden="true">
                <g stroke="var(--logo-edge)" stroke-width="2" stroke-linejoin="round">
                    <polygon points="50,55 50,5 93,30" fill="#61afef"/>
                    <polygon points="50,55 93,30 93,80" fill="#44aacc"/>
                    <polygon points="50,55 93,80 50,105" fill="#2ec4b6"/>
                    <polygon points="50,55 50,105 7,80" fill="#12b5a6"/>
                    <polygon points="50,55 7,80 7,30" fill="#0f9b8e"/>
                    <polygon points="50,55 7,30 50,5" fill="var(--logo-deep)"/>
                </g>
            </svg>
            <h1><span>YA</span>STL</h1>
        </div>

        <div class="search-container" role="search">
            <span class="search-icon" v-html="ICONS.search"></span>
            <input type="search"
                   :value="searchQuery"
                   @input="onSearchInput"
                   placeholder="Search models…"
                   aria-label="Search models"
                   enterkeyhint="search">
            <button v-if="searchQuery"
                    class="search-clear"
                    @click="emit('clearSearch')"
                    aria-label="Clear search"
                    title="Clear search" v-html="ICONS.close"></button>
        </div>

        <div class="navbar-actions">
            <button class="btn btn-primary nav-import" @click="emit('openImportModal')">
                <span v-html="ICONS.upload"></span><span>Import</span>
            </button>
            <button class="btn-icon status-btn nav-stats" :class="statusDotClass(systemStatus.health)"
                    @click="emit('openStats')"
                    :title="'Library stats (' + HEALTH_LABEL[statusDotClass(systemStatus.health)] + ')'"
                    :aria-label="'Library stats, ' + HEALTH_LABEL[statusDotClass(systemStatus.health)]">
                <span v-html="ICONS.stats"></span>
                <span class="status-dot" :class="statusDotClass(systemStatus.health)"></span>
            </button>

            <div class="nav-overflow" ref="navOverflowEl" @keydown="onMenuKey">
                <button ref="menuBtn" class="btn-icon nav-overflow-btn" :class="{ active: navOverflowOpen || selectionMode }"
                        @click="navOverflowOpen = !navOverflowOpen"
                        aria-haspopup="menu" :aria-expanded="String(navOverflowOpen)"
                        title="More" aria-label="More">
                    <span v-html="ICONS.dots"></span>
                    <span v-if="queueCount" class="nav-badge" aria-hidden="true">{{ queueCount }}</span>
                </button>
                <div v-if="navOverflowOpen" class="nav-overflow-menu" role="menu">
                    <button v-for="a in MENU_ACTIONS" :key="a.key"
                            class="nav-overflow-item" role="menuitem"
                            :class="{ active: a.key === 'select' && selectionMode, 'phone-only': a.phoneOnly }"
                            :disabled="a.key === 'scan' && scanStatus.scanning"
                            @click="fireAction(a)">
                        <span class="nav-overflow-icon" v-html="ICONS[a.icon]"></span>
                        <span class="nav-overflow-label">
                            <template v-if="a.key === 'scan' && scanStatus.scanning">Scan in progress…</template>
                            <template v-else-if="a.key === 'select' && selectionMode">Stop selecting</template>
                            <template v-else>{{ a.label }}</template>
                        </span>
                        <span v-if="a.key === 'queue' && queueCount" class="nav-overflow-count">{{ queueCount }}</span>
                        <span v-if="a.key === 'stats'" class="status-dot status-dot-inline" :class="statusDotClass(props.systemStatus.health)"></span>
                    </button>
                    <a class="nav-overflow-item nav-overflow-link" role="menuitem"
                       href="https://github.com/Pr0zak/YASTL" target="_blank" rel="noopener"
                       @click="navOverflowOpen = false">
                        <span class="nav-overflow-icon" v-html="ICONS.github"></span>
                        <span class="nav-overflow-label">YASTL on GitHub</span>
                    </a>
                </div>
            </div>
        </div>
    </nav>
</template>
