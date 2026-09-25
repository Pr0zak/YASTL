<script setup>
/**
 * FilamentModal - Filament spool inventory (print pipeline).
 * Lists spools with color swatch + remaining-weight bar; add/edit/delete.
 */
import { ref, reactive } from 'vue';
import { ICONS } from '../icons.js';
import AppDialog from './AppDialog.vue';

const props = defineProps({
    showFilament: { type: Boolean, default: false },
    filaments: { type: Array, default: () => [] },
    saving: { type: Boolean, default: false },
});
const emit = defineEmits(['close', 'save', 'delete']);

const showForm = ref(false);
const editingId = ref(null);
const blank = () => ({
    brand: '', material: '', color_name: '', color_hex: '#1a9e8f',
    diameter: 1.75, spool_weight_g: null, remaining_g: null, cost: null,
    vendor: '', notes: '', status: 'active',
});
const form = reactive(blank());

function resetForm() {
    Object.assign(form, blank());
    editingId.value = null;
}
function openAdd() {
    resetForm();
    showForm.value = true;
}
function startEdit(f) {
    Object.assign(form, blank(), f);
    if (!form.color_hex) form.color_hex = '#1a9e8f';
    editingId.value = f.id;
    showForm.value = true;
}
function cancelForm() {
    showForm.value = false;
    resetForm();
}
function submit() {
    emit('save', { id: editingId.value, data: { ...form } });
    showForm.value = false;
    resetForm();
}

function remainingPct(f) {
    if (!f.spool_weight_g || f.remaining_g == null) return 0;
    return Math.max(0, Math.min(100, Math.round((f.remaining_g / f.spool_weight_g) * 100)));
}
function g(v) { return v == null ? null : Math.round(v); }
</script>

<template>
    <AppDialog :show="showFilament" title="Filament" size="md"
               :subtitle="filaments.length ? `${filaments.filter(f => f.status === 'active').length} active spools` : ''"
               @close="emit('close')">
        <template #headerExtra>
            <button v-if="!showForm && filaments.length" class="btn btn-primary btn-sm filament-add-top" @click="openAdd">
                <span v-html="ICONS.plus"></span> Add spool
            </button>
        </template>

        <!-- Add / Edit form -->
        <form v-if="showForm" class="filament-form" @submit.prevent="submit">
            <div class="filament-form-grid">
                <label class="form-field"><span class="form-label">Brand</span>
                    <input class="form-input" v-model="form.brand" placeholder="Polymaker" data-autofocus></label>
                <label class="form-field"><span class="form-label">Material</span>
                    <input class="form-input" v-model="form.material" placeholder="PLA, PETG…"></label>
                <label class="form-field"><span class="form-label">Colour name</span>
                    <input class="form-input" v-model="form.color_name" placeholder="Teal"></label>
                <div class="form-field"><label class="form-label" for="filament-hex">Colour</label>
                    <div class="filament-color-field">
                        <input type="color" class="filament-color-input" v-model="form.color_hex" aria-label="Pick colour">
                        <input id="filament-hex" class="form-input" v-model="form.color_hex" placeholder="#1a9e8f">
                    </div>
                </div>
                <label class="form-field"><span class="form-label">Spool weight (g)</span>
                    <input class="form-input" type="number" v-model.number="form.spool_weight_g" placeholder="1000"></label>
                <label class="form-field"><span class="form-label">Remaining (g)</span>
                    <input class="form-input" type="number" v-model.number="form.remaining_g" placeholder="750"></label>
                <label class="form-field"><span class="form-label">Cost</span>
                    <input class="form-input" type="number" step="0.01" v-model.number="form.cost" placeholder="19.99"></label>
                <label class="form-field"><span class="form-label">Vendor</span>
                    <input class="form-input" v-model="form.vendor" placeholder="Amazon"></label>
                <label class="form-field"><span class="form-label">Status</span>
                    <select class="form-input" v-model="form.status">
                        <option value="active">Active</option>
                        <option value="empty">Empty</option>
                        <option value="archived">Archived</option>
                    </select></label>
            </div>
            <div class="filament-form-actions">
                <button type="button" class="btn btn-secondary" @click="cancelForm">Cancel</button>
                <button type="submit" class="btn btn-primary" :disabled="saving">
                    {{ editingId ? 'Save changes' : 'Add spool' }}
                </button>
            </div>
        </form>

        <div v-if="filaments.length === 0 && !showForm" class="dialog-empty">
            <div class="dialog-empty-icon" v-html="ICONS.spool"></div>
            <div class="dialog-empty-title">No spools yet</div>
            <p class="dialog-empty-text">Keep track of what's on the shelf and how much is left on each spool.</p>
            <button class="btn btn-primary" @click="openAdd"><span v-html="ICONS.plus"></span> Add your first spool</button>
        </div>
        <ul v-else-if="filaments.length" class="filament-list">
            <li v-for="f in filaments" :key="f.id" class="filament-row"
                :class="{ 'is-inactive': f.status !== 'active' }">
                <span class="filament-swatch" :style="{ background: f.color_hex || 'var(--text-muted)' }"></span>
                <div class="filament-info">
                    <div class="filament-name">
                        {{ [f.brand, f.material].filter(Boolean).join(' ') || 'Untitled spool' }}
                        <span v-if="f.color_name" class="filament-color-name"> · {{ f.color_name }}</span>
                        <span v-if="f.status !== 'active'" class="filament-status-tag">{{ f.status }}</span>
                    </div>
                    <div class="filament-sub">
                        <template v-if="g(f.remaining_g) != null && f.spool_weight_g">
                            {{ g(f.remaining_g) }} g of {{ g(f.spool_weight_g) }} g ({{ remainingPct(f) }}%)
                        </template>
                        <template v-else-if="g(f.remaining_g) != null">{{ g(f.remaining_g) }} g left</template>
                        <span v-if="f.cost"> · ${{ Number(f.cost).toFixed(2) }}</span>
                        <span v-if="f.vendor"> · {{ f.vendor }}</span>
                    </div>
                    <div v-if="g(f.remaining_g) != null && f.spool_weight_g" class="filament-bar">
                        <div class="filament-bar-fill" :style="{
                            width: remainingPct(f) + '%',
                            background: f.color_hex || 'var(--accent)'
                        }"></div>
                    </div>
                </div>
                <div class="filament-actions">
                    <button class="btn-icon" @click="startEdit(f)" title="Edit spool" aria-label="Edit spool" v-html="ICONS.edit"></button>
                    <button class="btn-icon btn-icon-danger" @click="emit('delete', f)" title="Delete spool" aria-label="Delete spool" v-html="ICONS.trash"></button>
                </div>
            </li>
        </ul>
    </AppDialog>
</template>

<style scoped>
.filament-add-top { flex: none; }
.filament-list { list-style: none; display: flex; flex-direction: column; gap: 8px; }
.filament-row {
    display: flex; align-items: center; gap: 12px; padding: 10px 8px 10px 12px;
    border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-card);
}
.filament-row.is-inactive { opacity: 0.6; }
.filament-swatch { width: 28px; height: 28px; border-radius: 50%; flex: none; border: 2px solid var(--border); }
.filament-info { flex: 1; min-width: 0; }
.filament-name { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); }
.filament-color-name { font-weight: 400; color: var(--text-secondary); }
.filament-status-tag {
    font-size: 0.65rem; text-transform: uppercase; color: var(--text-muted);
    border: 1px solid var(--border); border-radius: 3px; padding: 0 5px; margin-left: 6px;
}
.filament-sub { font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }
.filament-bar { height: 5px; border-radius: 3px; background: var(--bg-input); overflow: hidden; margin-top: 6px; }
.filament-bar-fill { height: 100%; border-radius: 3px; transition: width var(--transition); }
.filament-actions { display: flex; flex: none; }
.filament-form {
    border: 1px solid var(--border); border-radius: var(--radius); padding: 14px;
    margin-bottom: 16px; background: var(--bg-card);
}
.filament-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 12px; }
.form-field { display: flex; flex-direction: column; gap: 4px; }
.form-field .form-label { margin: 0; }
.filament-color-field { display: flex; gap: 8px; align-items: center; }
.filament-color-input {
    width: 40px; height: 36px; padding: 2px; border: 1px solid var(--border);
    border-radius: var(--radius-sm); background: var(--bg-input); cursor: pointer; flex: none;
}
.filament-form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
@media (max-width: 560px) {
    .filament-form-grid { grid-template-columns: 1fr; }
    .filament-form-actions .btn { flex: 1; min-height: 44px; }
    .filament-actions .btn-icon { width: 40px; height: 40px; }
}
</style>
