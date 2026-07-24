<script setup>
/**
 * FilamentModal - Filament spool inventory (print pipeline).
 * Lists spools with color swatch + remaining-weight bar; add/edit/delete.
 */
import { ref, reactive } from 'vue';
import { ICONS } from '../icons.js';

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
    <div v-if="showFilament" class="detail-overlay" @click.self="emit('close')">
        <div class="settings-panel filament-panel">
            <div class="detail-header">
                <div class="detail-title">
                    <span v-html="ICONS.spool"></span>
                    Filament Inventory
                </div>
                <button class="close-btn" @click="emit('close')" title="Close">&times;</button>
            </div>

            <div class="settings-content">
                <!-- Add / Edit form -->
                <div v-if="showForm" class="filament-form">
                    <div class="filament-form-grid">
                        <input class="form-input" v-model="form.brand" placeholder="Brand (e.g. Polymaker)">
                        <input class="form-input" v-model="form.material" placeholder="Material (PLA, PETG…)">
                        <input class="form-input" v-model="form.color_name" placeholder="Color name (Teal)">
                        <div class="filament-color-field">
                            <input type="color" class="filament-color-input" v-model="form.color_hex">
                            <input class="form-input" v-model="form.color_hex" placeholder="#1a9e8f">
                        </div>
                        <input class="form-input" type="number" v-model.number="form.spool_weight_g" placeholder="Spool weight (g)">
                        <input class="form-input" type="number" v-model.number="form.remaining_g" placeholder="Remaining (g)">
                        <input class="form-input" type="number" step="0.01" v-model.number="form.cost" placeholder="Cost">
                        <input class="form-input" v-model="form.vendor" placeholder="Vendor">
                        <select class="form-input" v-model="form.status">
                            <option value="active">Active</option>
                            <option value="empty">Empty</option>
                            <option value="archived">Archived</option>
                        </select>
                    </div>
                    <div class="filament-form-actions">
                        <button class="btn btn-secondary" @click="cancelForm">Cancel</button>
                        <button class="btn btn-primary" :disabled="saving" @click="submit">
                            {{ editingId ? 'Save changes' : 'Add spool' }}
                        </button>
                    </div>
                </div>
                <button v-else class="btn btn-primary filament-add-btn" @click="openAdd">
                    + Add filament spool
                </button>

                <!-- List -->
                <div v-if="filaments.length === 0 && !showForm" class="filament-empty">
                    No filament spools yet. Track your PLA/PETG/… inventory here.
                </div>
                <div v-else class="filament-list">
                    <div v-for="f in filaments" :key="f.id" class="filament-row"
                         :class="{ 'is-inactive': f.status !== 'active' }">
                        <span class="filament-swatch" :style="{ background: f.color_hex || '#888' }"></span>
                        <div class="filament-info">
                            <div class="filament-name">
                                {{ [f.brand, f.material].filter(Boolean).join(' ') || 'Untitled spool' }}
                                <span v-if="f.color_name" class="filament-color-name"> · {{ f.color_name }}</span>
                                <span v-if="f.status !== 'active'" class="filament-status-tag">{{ f.status }}</span>
                            </div>
                            <div class="filament-sub">
                                <template v-if="g(f.remaining_g) != null && f.spool_weight_g">
                                    {{ g(f.remaining_g) }} g / {{ g(f.spool_weight_g) }} g ({{ remainingPct(f) }}%)
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
                            <button class="btn-icon" @click="startEdit(f)" title="Edit">✎</button>
                            <button class="btn-icon" @click="emit('delete', f.id)" title="Delete">&times;</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
