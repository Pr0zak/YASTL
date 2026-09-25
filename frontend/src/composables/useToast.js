/**
 * YASTL - Toast notification composable
 *
 * Successes fade after a few seconds. Errors stay until dismissed: they used
 * to vanish after the same 3.5s as a success, often before anyone read them.
 */

import { ref } from 'vue';

const DURATION = { success: 3500, info: 5000 };

export function useToast() {
    const toasts = ref([]);

    function dismissToast(id) {
        toasts.value = toasts.value.filter((t) => t.id !== id);
    }

    function showToast(message, type = 'success') {
        const id = Date.now() + Math.random();
        toasts.value.push({ id, message, type });
        // Keep at most four on screen; the oldest goes first.
        if (toasts.value.length > 4) toasts.value = toasts.value.slice(-4);
        const ms = DURATION[type];
        if (ms) setTimeout(() => dismissToast(id), ms);
    }

    return { toasts, showToast, dismissToast };
}
