<script setup>
import AppDialog from './AppDialog.vue';

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
    <!-- Focus lands on Cancel for destructive actions, so a reflexive Enter
         never deletes anything; otherwise on the action itself. -->
    <AppDialog :show="visible" :title="title" size="sm" role="alertdialog"
               panel-class="confirm-dialog" @close="$emit('cancel')">
        <p class="confirm-message">{{ message }}</p>
        <template #footer>
            <button class="btn btn-secondary" :data-autofocus="danger ? '' : null" @click="$emit('cancel')">Cancel</button>
            <button
                class="btn"
                :class="danger ? 'btn-danger' : 'btn-primary'"
                :data-autofocus="danger ? null : ''"
                @click="$emit('confirm')"
            >{{ action }}</button>
        </template>
    </AppDialog>
</template>
