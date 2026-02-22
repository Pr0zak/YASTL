<script setup>
/**
 * SmartCollectionModal - Create/edit smart collection rules.
 */
import { ref, computed } from 'vue';
import { ICONS } from '../icons.js';

const props = defineProps({
    show: { type: Boolean, default: false },
    form: { type: Object, required: true },
    editing: { default: null },
    allTags: { type: Array, default: () => [] },
    allCategories: { type: Array, default: () => [] },
    libraries: { type: Array, default: () => [] },
    COLLECTION_COLORS: { type: Array, default: () => [] },
});

const emit = defineEmits([
    'close',
    'save',
    'updateName',
    'updateColor',
    'updateRule',
    'addRuleTag',
    'removeRuleTag',
    'addRuleCategory',
    'removeRuleCategory',
]);

const tagInput = ref('');

const FORMATS = ['stl', 'obj', 'gltf', 'glb', '3mf', 'step', 'stp', 'ply', 'fbx', 'dae', 'off'];
const DATE_RANGES = [
    { value: '', label: 'Any time' },
    { value: 'last_7d', label: 'Last 7 days' },
    { value: 'last_30d', label: 'Last 30 days' },
    { value: 'last_90d', label: 'Last 90 days' },
    { value: 'last_365d', label: 'Last year' },
];

const flatCategories = computed(() => {
    const result = [];
    function walk(cats, depth = 0) {
        for (const cat of cats) {
            result.push({ ...cat, depth });
            if (cat.children && cat.children.length) {
                walk(cat.children, depth + 1);
            }
        }
    }
    walk(props.allCategories);
    return result;
});

const availableTags = computed(() => {
    const used = new Set(props.form.rules.tags || []);
    const q = tagInput.value.trim().toLowerCase();
    return props.allTags
        .filter(t => !used.has(t.name))
        .filter(t => !q || t.name.toLowerCase().includes(q))
        .slice(0, 20);
});

function onAddTag(tagName) {
    emit('addRuleTag', tagName);
    tagInput.value = '';
}

function hasActiveRules() {
    const r = props.form.rules;
    return r.format || (r.tags && r.tags.length) || (r.categories && r.categories.length) ||
        r.library_id || r.favoritesOnly || r.duplicatesOnly || r.sizeMin || r.sizeMax || r.dateRange;
}
</script>

<template>
    <div v-if="show" class="detail-overlay" @click.self="emit('close')">
        <div class="settings-panel smart-collection-panel">
            <!-- Header -->
            <div class="detail-header">
                <div class="detail-title">
                    <span v-html="ICONS.zap"></span>
                    {{ editing ? 'Edit Smart Collection' : 'New Smart Collection' }}
                </div>
                <button class="close-btn" @click="emit('close')" title="Close">&times;</button>
            </div>

            <div class="settings-content">
                <!-- Name & Color -->
                <div class="form-row">
                    <label class="form-label">Name</label>
                    <input class="form-input" :value="form.name"
                           @input="emit('updateName', $event.target.value)"
                           placeholder="Smart collection name">
                </div>
                <div class="form-row">
                    <label class="form-label">Color</label>
                    <div class="color-swatch-grid">
                        <button v-for="c in COLLECTION_COLORS" :key="c"
                                class="color-swatch" :class="{ active: form.color === c }"
                                :style="{ background: c }"
                                @click="emit('updateColor', c)"
                                type="button"></button>
                    </div>
                </div>

                <div class="settings-section">
                    <div class="settings-section-title">Filter Rules</div>
                    <p class="text-muted text-sm" style="margin-bottom:12px">
                        Models matching all rules below will appear in this collection.
                    </p>

                    <!-- Format -->
                    <div class="form-row">
                        <label class="form-label">Format</label>
                        <select class="form-input" :value="form.rules.format"
                                @change="emit('updateRule', 'format', $event.target.value)">
                            <option value="">Any format</option>
                            <option v-for="fmt in FORMATS" :key="fmt" :value="fmt">{{ fmt.toUpperCase() }}</option>
                        </select>
                    </div>

                    <!-- Library -->
                    <div class="form-row" v-if="libraries.length > 0">
                        <label class="form-label">Library</label>
                        <select class="form-input" :value="form.rules.library_id || ''"
                                @change="emit('updateRule', 'library_id', $event.target.value ? Number($event.target.value) : null)">
                            <option value="">Any library</option>
                            <option v-for="lib in libraries" :key="lib.id" :value="lib.id">{{ lib.name }}</option>
                        </select>
                    </div>

                    <!-- Tags -->
                    <div class="form-row">
                        <label class="form-label">Tags (all must match)</label>
                        <div class="smart-rule-tags">
                            <span v-for="tag in form.rules.tags" :key="tag" class="tag-chip">
                                {{ tag }}
                                <button class="tag-remove" @click="emit('removeRuleTag', tag)">&times;</button>
                            </span>
                        </div>
                        <div class="smart-tag-add">
                            <input class="form-input" v-model="tagInput" placeholder="Add tag..."
                                   @keydown.enter.prevent="tagInput.trim() && onAddTag(tagInput.trim())">
                            <div v-if="tagInput.trim() && availableTags.length" class="smart-tag-dropdown">
                                <div v-for="t in availableTags" :key="t.id" class="smart-tag-option"
                                     @click="onAddTag(t.name)">
                                    {{ t.name }}
                                    <span class="text-muted text-sm" v-if="t.model_count">({{ t.model_count }})</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Categories -->
                    <div class="form-row">
                        <label class="form-label">Categories (any match)</label>
                        <div class="smart-rule-tags">
                            <span v-for="cat in form.rules.categories" :key="cat" class="tag-chip">
                                {{ cat }}
                                <button class="tag-remove" @click="emit('removeRuleCategory', cat)">&times;</button>
                            </span>
                        </div>
                        <select class="form-input"
                                @change="$event.target.value && emit('addRuleCategory', $event.target.value); $event.target.value = ''">
                            <option value="">Add category...</option>
                            <option v-for="cat in flatCategories" :key="cat.id" :value="cat.name"
                                    :disabled="form.rules.categories.includes(cat.name)">
                                {{ '\u00A0'.repeat(cat.depth * 2) }}{{ cat.name }}
                            </option>
                        </select>
                    </div>

                    <!-- Checkboxes -->
                    <div class="form-row">
                        <label class="checkbox-item" style="margin-bottom:6px">
                            <input type="checkbox" :checked="form.rules.favoritesOnly"
                                   @change="emit('updateRule', 'favoritesOnly', $event.target.checked)">
                            <span>Favorites only</span>
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" :checked="form.rules.duplicatesOnly"
                                   @change="emit('updateRule', 'duplicatesOnly', $event.target.checked)">
                            <span>Duplicates only</span>
                        </label>
                    </div>

                    <!-- Date range -->
                    <div class="form-row">
                        <label class="form-label">Added</label>
                        <select class="form-input" :value="form.rules.dateRange"
                                @change="emit('updateRule', 'dateRange', $event.target.value)">
                            <option v-for="dr in DATE_RANGES" :key="dr.value" :value="dr.value">{{ dr.label }}</option>
                        </select>
                    </div>
                </div>

                <!-- Actions -->
                <div class="form-actions" style="margin-top:16px">
                    <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
                    <button class="btn btn-primary" @click="emit('save')"
                            :disabled="!form.name.trim() || !hasActiveRules()">
                        {{ editing ? 'Save Changes' : 'Create' }}
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.smart-collection-panel {
    max-width: 520px;
}

.smart-rule-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 6px;
}

.smart-tag-add {
    position: relative;
}

.smart-tag-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    max-height: 180px;
    overflow-y: auto;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    z-index: 10;
}

.smart-tag-option {
    padding: 6px 10px;
    cursor: pointer;
    font-size: 0.85rem;
}

.smart-tag-option:hover {
    background: var(--bg-hover);
}

.tag-remove {
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 0 2px;
    margin-left: 2px;
    opacity: 0.6;
    font-size: 0.9rem;
}

.tag-remove:hover {
    opacity: 1;
}
</style>
