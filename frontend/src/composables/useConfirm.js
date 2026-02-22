/**
 * YASTL - Confirmation dialog composable
 *
 * Replaces browser confirm() with a styled in-app modal.
 * Usage: const confirmed = await showConfirm({ title, message, action, danger });
 */

import { ref } from 'vue';

export function useConfirm() {
    const confirmVisible = ref(false);
    const confirmTitle = ref('');
    const confirmMessage = ref('');
    const confirmAction = ref('Confirm');
    const confirmDanger = ref(false);
    let resolveConfirm = null;

    function showConfirm({ title, message, action = 'Confirm', danger = false }) {
        return new Promise(resolve => {
            confirmTitle.value = title;
            confirmMessage.value = message;
            confirmAction.value = action;
            confirmDanger.value = danger;
            confirmVisible.value = true;
            resolveConfirm = resolve;
        });
    }

    function onConfirm() {
        confirmVisible.value = false;
        resolveConfirm?.(true);
        resolveConfirm = null;
    }

    function onCancel() {
        confirmVisible.value = false;
        resolveConfirm?.(false);
        resolveConfirm = null;
    }

    return {
        confirmVisible,
        confirmTitle,
        confirmMessage,
        confirmAction,
        confirmDanger,
        showConfirm,
        onConfirm,
        onCancel,
    };
}
