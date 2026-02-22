<script setup>
/**
 * SideBar - Filters sidebar with libraries, format, tags, categories, collections, saved searches.
 */
import { ICONS } from '../icons.js';

defineProps({
    sidebarOpen: { type: Boolean, default: false },
    filters: { type: Object, required: true },
    allTags: { type: Array, default: () => [] },
    allCategories: { type: Array, default: () => [] },
    collections: { type: Array, default: () => [] },
    libraries: { type: Array, default: () => [] },
    favoritesCount: { type: Number, default: 0 },
    collapsedSections: { type: Object, required: true },
    expandedCategories: { type: Object, required: true },
    savedSearches: { type: Array, default: () => [] },
    editingCollectionId: { default: null },
    editCollectionName: { type: String, default: '' },
});

const emit = defineEmits([
    'update:sidebarOpen',
    'update:editCollectionName',
    'setLibraryFilter',
    'setFormatFilter',
    'toggleTagFilter',
    'toggleCategoryFilter',
    'toggleCategory',
    'toggleCollapsedSection',
    'setCollectionFilter',
    'toggleFavoritesFilter',
    'toggleDuplicatesFilter',
    'openCollectionModal',
    'startEditCollection',
    'saveCollectionName',
    'cancelEditCollection',
    'deleteCollection',
    'applySavedSearch',
    'deleteSavedSearch',
]);

function formatClass(fmt) {
    if (!fmt) return '';
    const f = fmt.toLowerCase().replace('.', '');
    if (f === '3mf') return '_3mf';
    return f;
}
</script>

<template>
    <!-- Sidebar backdrop (mobile) -->
    <div v-if="sidebarOpen" class="sidebar-backdrop" @click="emit('update:sidebarOpen', false)"></div>

    <!-- Sidebar -->
    <aside class="sidebar" :class="{ open: sidebarOpen, collapsed: !sidebarOpen }">

        <!-- Libraries -->
        <div class="sidebar-section" v-if="libraries.length > 0">
            <div class="sidebar-section-title">Libraries</div>
            <div v-for="lib in libraries" :key="lib.id"
                 class="sidebar-item"
                 :class="{ active: filters.library_id === lib.id }"
                 @click="emit('setLibraryFilter', lib.id)">
                <span class="sidebar-item-icon" v-html="ICONS.folder"></span>
                <span>{{ lib.name }}</span>
                <span v-if="lib.model_count != null" class="item-count">{{ lib.model_count }}</span>
            </div>
        </div>

        <!-- Format Filters (collapsible) -->
        <div class="sidebar-section">
            <div class="sidebar-section-title sidebar-section-toggle"
                 @click="emit('toggleCollapsedSection', 'format')">
                <span>Format</span>
                <span v-if="filters.format" class="sidebar-section-active-badge">
                    {{ filters.format.toUpperCase() }}
                </span>
                <span class="sidebar-section-chevron" :class="{ expanded: !collapsedSections.format }"
                      v-html="ICONS.chevron"></span>
            </div>
            <template v-if="!collapsedSections.format">
                <label v-for="fmt in ['stl','obj','gltf','glb','3mf','step','stp','ply','fbx','dae','off']"
                       :key="fmt"
                       class="checkbox-item"
                       @click.prevent="emit('setFormatFilter', fmt)">
                    <input type="checkbox" :checked="filters.format === fmt" readonly>
                    <span class="format-badge" :class="formatClass(fmt)">{{ fmt.toUpperCase() }}</span>
                </label>
            </template>
        </div>

        <!-- Tags -->
        <div class="sidebar-section">
            <div class="sidebar-section-title sidebar-section-toggle"
                 @click="emit('toggleCollapsedSection', 'tags')">
                <span>Tags</span>
                <span v-if="filters.tags.length" class="sidebar-section-active-badge">
                    {{ filters.tags.length }} active
                </span>
                <span class="sidebar-section-chevron" :class="{ expanded: !collapsedSections.tags }"
                      v-html="ICONS.chevron"></span>
            </div>
            <template v-if="!collapsedSections.tags">
                <div v-if="allTags.length === 0" class="text-muted text-sm" style="padding: 4px 10px;">
                    No tags yet
                </div>
                <div v-for="tag in allTags" :key="tag.id"
                     class="sidebar-item"
                     :class="{ active: filters.tags.includes(tag.name) }"
                     @click="emit('toggleTagFilter', tag.name)">
                    <span>{{ tag.name }}</span>
                    <span v-if="tag.model_count != null" class="item-count">{{ tag.model_count }}</span>
                </div>
            </template>
        </div>

        <!-- Categories -->
        <div class="sidebar-section">
            <div class="sidebar-section-title sidebar-section-toggle"
                 @click="emit('toggleCollapsedSection', 'categories')">
                <span>Categories</span>
                <span v-if="filters.categories.length" class="sidebar-section-active-badge">
                    {{ filters.categories.length }} active
                </span>
                <span class="sidebar-section-chevron" :class="{ expanded: !collapsedSections.categories }"
                      v-html="ICONS.chevron"></span>
            </div>
            <template v-if="!collapsedSections.categories">
            <div v-if="allCategories.length === 0" class="text-muted text-sm" style="padding: 4px 10px;">
                No categories yet
            </div>
            <ul class="category-tree">
                <template v-for="cat in allCategories" :key="cat.id">
                    <li>
                        <div class="category-item"
                             :class="{ active: filters.categories.includes(cat.name) }"
                             @click="emit('toggleCategoryFilter', cat.name)">
                            <span v-if="cat.children && cat.children.length"
                                  class="category-toggle"
                                  :class="{ expanded: expandedCategories[cat.id] }"
                                  @click.stop="emit('toggleCategory', cat.id)"
                                  v-html="ICONS.chevron"></span>
                            <span v-else style="width:16px;display:inline-block"></span>
                            <span class="category-name">{{ cat.name }}</span>
                            <span v-if="cat.model_count" class="category-count">({{ cat.model_count }})</span>
                        </div>
                        <ul v-if="cat.children && cat.children.length && expandedCategories[cat.id]"
                            class="category-children">
                            <li v-for="child in cat.children" :key="child.id">
                                <div class="category-item"
                                     :class="{ active: filters.categories.includes(child.name) }"
                                     @click="emit('toggleCategoryFilter', child.name)">
                                    <span v-if="child.children && child.children.length"
                                          class="category-toggle"
                                          :class="{ expanded: expandedCategories[child.id] }"
                                          @click.stop="emit('toggleCategory', child.id)"
                                          v-html="ICONS.chevron"></span>
                                    <span v-else style="width:16px;display:inline-block"></span>
                                    <span class="category-name">{{ child.name }}</span>
                                    <span v-if="child.model_count" class="category-count">({{ child.model_count }})</span>
                                </div>
                                <!-- Third level -->
                                <ul v-if="child.children && child.children.length && expandedCategories[child.id]"
                                    class="category-children">
                                    <li v-for="grandchild in child.children" :key="grandchild.id">
                                        <div class="category-item"
                                             :class="{ active: filters.categories.includes(grandchild.name) }"
                                             @click="emit('toggleCategoryFilter', grandchild.name)">
                                            <span style="width:16px;display:inline-block"></span>
                                            <span class="category-name">{{ grandchild.name }}</span>
                                        </div>
                                    </li>
                                </ul>
                            </li>
                        </ul>
                    </li>
                </template>
            </ul>
            </template>
        </div>

        <!-- Collections -->
        <div class="sidebar-section">
            <div class="sidebar-section-title" style="display:flex;align-items:center;justify-content:space-between">
                Collections
                <button class="btn-icon" style="width:20px;height:20px" @click="emit('openCollectionModal')"
                        title="New collection"><span v-html="ICONS.plus"></span></button>
            </div>
            <div class="sidebar-item" :class="{ active: filters.favoritesOnly }" @click="emit('toggleFavoritesFilter')">
                <span v-html="ICONS.heart"></span>
                <span>Favorites</span>
                <span v-if="favoritesCount > 0" class="item-count">{{ favoritesCount }}</span>
            </div>
            <div class="sidebar-item" :class="{ active: filters.duplicatesOnly }" @click="emit('toggleDuplicatesFilter')">
                <span v-html="ICONS.copy"></span>
                <span>Duplicates</span>
            </div>
            <div v-for="col in collections" :key="col.id"
                 class="sidebar-item" :class="{ active: filters.collection === col.id }"
                 @click="emit('setCollectionFilter', col.id)">
                <span class="collection-dot" :style="{ background: col.color || '#666' }"></span>
                <template v-if="editingCollectionId === col.id">
                    <input class="sidebar-edit-input" :value="editCollectionName"
                           @input="emit('update:editCollectionName', $event.target.value)"
                           @blur="emit('saveCollectionName', col)"
                           @keydown.enter="emit('saveCollectionName', col)"
                           @keydown.escape="emit('cancelEditCollection')"
                           @click.stop
                           autofocus>
                </template>
                <span v-else class="truncate" @dblclick.stop="emit('startEditCollection', col)">{{ col.name }}</span>
                <span class="item-count">{{ col.model_count }}</span>
                <button class="sidebar-item-delete" @click.stop="emit('deleteCollection', col.id)">&times;</button>
            </div>
        </div>

        <!-- Saved Searches -->
        <div class="sidebar-section" v-if="savedSearches.length">
            <div class="sidebar-section-title">Saved Searches</div>
            <div v-for="search in savedSearches" :key="search.id"
                 class="sidebar-item" @click="emit('applySavedSearch', search)">
                <span v-html="ICONS.bookmark"></span>
                <span class="truncate">{{ search.name }}</span>
                <button class="sidebar-item-delete" @click.stop="emit('deleteSavedSearch', search.id)">&times;</button>
            </div>
        </div>
    </aside>
</template>
