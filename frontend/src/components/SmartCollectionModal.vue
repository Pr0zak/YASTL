<script setup>
/**
 * SmartCollectionModal - Unified collection modal (supports optional smart rules).
 */
import { ref, computed, watch } from 'vue';
import { ICONS } from '../icons.js';
import { apiPreviewSmartCount } from '../api.js';
import AppDialog from './AppDialog.vue';

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
const showRules = ref(false);

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

// Auto-expand rules section when editing a smart collection or when rules are active
const rulesExpanded = computed(() => {
    return showRules.value || hasActiveRules();
});

// Live match count as rules are edited (debounced)
const previewCount = ref(null);
const previewLoading = ref(false);
let previewTimer = null;
let previewSeq = 0;

watch(
    () => [props.show, JSON.stringify(props.form.rules)],
    () => {
        if (!props.show || !hasActiveRules()) {
            previewCount.value = null;
            return;
        }
        if (previewTimer) clearTimeout(previewTimer);
        previewLoading.value = true;
        const seq = ++previewSeq;
        const rules = JSON.parse(JSON.stringify(props.form.rules));
        previewTimer = setTimeout(async () => {
            try {
                const data = await apiPreviewSmartCount(rules);
                if (seq === previewSeq) previewCount.value = data.count;
            } catch {
                if (seq === previewSeq) previewCount.value = null;
            } finally {
                if (seq === previewSeq) previewLoading.value = false;
            }
        }, 350);
    },
    { immediate: true, deep: true }
);

function toggleRules() {
    showRules.value = !showRules.value;
}
</script>

<template>
    <AppDialog :show="show" :title="editing ? 'Edit collection' : 'New collection'" size="sm"
               :dismiss-on-backdrop="false" @close="emit('close')">
        <form id="smart-collection-form" @submit.prevent="form.name.trim() && emit('save')">
            <div class="form-row">
                <label class="form-label" for="collection-name">Name</label>
                <input id="collection-name" class="form-input" :value="form.name"
                       @input="emit('updateName', $event.target.value)"
                       placeholder="Collection name">
            </div>
            <div class="form-row">
                <span class="form-label" id="collection-colour-label">Colour</span>
                <div class="color-swatch-grid" role="radiogroup" aria-labelledby="collection-colour-label">
                    <button v-for="c in COLLECTION_COLORS" :key="c"
                            class="color-swatch" :class="{ active: form.color === c }"
                            :style="{ background: c }" role="radio" :aria-checked="String(form.color === c)"
                            :aria-label="'Colour ' + c"
                            @click="emit('updateColor', c)"
                            type="button"></button>
                </div>
            </div>

            <!-- Smart Rules (collapsible, optional) -->
            <div class="rules-box">
                <button type="button" class="rules-toggle" :aria-expanded="String(!!rulesExpanded)" @click="toggleRules">
                    <span v-html="ICONS.zap" class="rules-toggle-icon"></span>
                    <span>Smart rules</span>
                    <span class="text-muted rules-optional">{{ hasActiveRules() ? '' : 'optional' }}</span>
                    <span v-if="hasActiveRules()" class="sidebar-section-active-badge">active</span>
                    <span class="sidebar-section-chevron" :class="{ expanded: rulesExpanded }" v-html="ICONS.chevron"></span>
                </button>
                <div v-if="rulesExpanded" class="rules-body">
                    <p class="text-muted text-sm">Models matching every rule appear in this collection automatically.</p>
                    <div class="smart-preview-count" aria-live="polite">
                        <span v-if="previewLoading" class="text-muted">Counting…</span>
                        <span v-else-if="previewCount != null">
                            <strong>{{ previewCount }}</strong> model{{ previewCount === 1 ? '' : 's' }} match
                        </span>
                        <span v-else class="text-muted">Add a rule to preview matches</span>
                    </div>

                    <div class="form-row">
                        <label class="form-label" for="rule-format">Format</label>
                        <select id="rule-format" class="form-input" :value="form.rules.format"
                                @change="emit('updateRule', 'format', $event.target.value)">
                            <option value="">Any format</option>
                            <option v-for="fmt in FORMATS" :key="fmt" :value="fmt">{{ fmt.toUpperCase() }}</option>
                        </select>
                    </div>

                    <div class="form-row" v-if="libraries.length > 0">
                        <label class="form-label" for="rule-library">Library</label>
                        <select id="rule-library" class="form-input" :value="form.rules.library_id || ''"
                                @change="emit('updateRule', 'library_id', $event.target.value ? Number($event.target.value) : null)">
                            <option value="">Any library</option>
                            <option v-for="lib in libraries" :key="lib.id" :value="lib.id">{{ lib.name }}</option>
                        </select>
                    </div>

                    <div class="form-row">
                        <div class="form-label rule-label-row">
                            <label for="rule-tag-input">Tags</label>
                            <span v-if="form.rules.tags && form.rules.tags.length > 1" class="tag-match-toggle" role="group" aria-label="Tag matching">
                                <button type="button" class="btn-ghost tag-match-btn"
                                        :class="{ active: (form.rules.tagMatch || 'and') === 'and' }"
                                        :aria-pressed="String((form.rules.tagMatch || 'and') === 'and')"
                                        @click="emit('updateRule', 'tagMatch', 'and')">ALL</button>
                                <button type="button" class="btn-ghost tag-match-btn"
                                        :class="{ active: form.rules.tagMatch === 'or' }"
                                        :aria-pressed="String(form.rules.tagMatch === 'or')"
                                        @click="emit('updateRule', 'tagMatch', 'or')">ANY</button>
                            </span>
                        </div>
                        <div class="smart-rule-tags">
                            <span v-for="tag in form.rules.tags" :key="tag" class="tag-chip">
                                {{ tag }}
                                <button type="button" class="tag-remove" :aria-label="'Remove ' + tag" @click="emit('removeRuleTag', tag)">&times;</button>
                            </span>
                        </div>
                        <div class="smart-tag-add">
                            <input id="rule-tag-input" class="form-input" v-model="tagInput" placeholder="Add tag…"
                                   autocomplete="off"
                                   @keydown.enter.prevent="tagInput.trim() && onAddTag(tagInput.trim())">
                            <div v-if="tagInput.trim() && availableTags.length" class="smart-tag-dropdown" role="listbox">
                                <button v-for="t in availableTags" :key="t.id" type="button" role="option"
                                        class="smart-tag-option" @click="onAddTag(t.name)">
                                    {{ t.name }}
                                    <span class="text-muted text-sm" v-if="t.model_count">({{ t.model_count }})</span>
                                </button>
                            </div>
                        </div>
                    </div>

                    <div class="form-row">
                        <label class="form-label" for="rule-category">Categories (any match)</label>
                        <div class="smart-rule-tags">
                            <span v-for="cat in form.rules.categories" :key="cat" class="tag-chip">
                                {{ cat }}
                                <button type="button" class="tag-remove" :aria-label="'Remove ' + cat" @click="emit('removeRuleCategory', cat)">&times;</button>
                            </span>
                        </div>
                        <select id="rule-category" class="form-input"
                                @change="$event.target.value && emit('addRuleCategory', $event.target.value); $event.target.value = ''">
                            <option value="">Add category…</option>
                            <option v-for="cat in flatCategories" :key="cat.id" :value="cat.name"
                                    :disabled="form.rules.categories.includes(cat.name)">
                                {{ '\u00A0'.repeat(cat.depth * 2) }}{{ cat.name }}
                            </option>
                        </select>
                    </div>

                    <div class="form-row rule-checks">
                        <label class="checkbox-item">
                            <input type="checkbox" :checked="form.rules.favoritesOnly"
                                   @change="emit('updateRule', 'favoritesOnly', $event.target.checked)">
                            <span>Favourites only</span>
                        </label>
                        <label class="checkbox-item">
                            <input type="checkbox" :checked="form.rules.duplicatesOnly"
                                   @change="emit('updateRule', 'duplicatesOnly', $event.target.checked)">
                            <span>Duplicates only</span>
                        </label>
                    </div>

                    <div class="form-row">
                        <label class="form-label" for="rule-date">Added</label>
                        <select id="rule-date" class="form-input" :value="form.rules.dateRange"
                                @change="emit('updateRule', 'dateRange', $event.target.value)">
                            <option v-for="dr in DATE_RANGES" :key="dr.value" :value="dr.value">{{ dr.label }}</option>
                        </select>
                    </div>
                </div>
            </div>
        </form>

        <template #footer>
            <button type="button" class="btn btn-secondary" @click="emit('close')">Cancel</button>
            <button type="submit" form="smart-collection-form" class="btn btn-primary" :disabled="!form.name.trim()">
                {{ editing ? 'Save changes' : 'Create' }}
            </button>
        </template>
    </AppDialog>
</template>

<style scoped>
.rules-box { border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-card); }
.rules-toggle {
    width: 100%; display: flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 12px;
    background: none; color: var(--text-primary); font-weight: 600; font-size: 0.88rem; text-align: left;
}
.rules-toggle-icon { display: flex; opacity: 0.7; }
.rules-optional { font-weight: 400; font-size: 0.78rem; }
.rules-toggle .sidebar-section-chevron { margin-left: auto; }
.rules-body { padding: 4px 12px 12px; display: flex; flex-direction: column; gap: 4px; }
.rule-label-row { display: flex; align-items: center; justify-content: space-between; }
.rule-checks { display: flex; flex-direction: column; gap: 6px; }

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
    box-shadow: 0 4px 12px var(--shadow);
    z-index: 10;
}

.smart-tag-option {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    color: var(--text-primary);
    min-height: 36px;
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

.tag-match-toggle {
    display: inline-flex;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    overflow: hidden;
}

.tag-match-btn {
    padding: 2px 8px;
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    border-radius: 0;
    border: none;
}

.tag-match-btn + .tag-match-btn {
    border-left: 1px solid var(--border);
}
</style>
