<script setup>
defineProps({
    visible: Boolean,
    title: String,
    message: String,
    action: String,
    danger: Boolean,
});

defineEmits(['confirm', 'cancel']);
</script>

<template>
<teleport to="body">
    <div v-if="visible" class="confirm-overlay" @click.self="$emit('cancel')">
        <div class="confirm-dialog">
            <h3 class="confirm-title">{{ title }}</h3>
            <p class="confirm-message">{{ message }}</p>
            <div class="confirm-actions">
                <button class="btn btn-secondary" @click="$emit('cancel')">Cancel</button>
                <button
                    class="btn"
                    :class="danger ? 'btn-danger' : 'btn-primary'"
                    @click="$emit('confirm')"
                >{{ action }}</button>
            </div>
        </div>
    </div>
</teleport>
</template>
