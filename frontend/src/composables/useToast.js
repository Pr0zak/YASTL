/**
 * YASTL - Toast notification composable
 */

import { ref } from 'vue';

export function useToast() {
    const toasts = ref([]);

    function showToast(message, type = 'success') {
        const id = Date.now() + Math.random();
        toasts.value.push({ id, message, type });
        setTimeout(() => {
            toasts.value = toasts.value.filter((t) => t.id !== id);
        }, 3500);
    }

    return { toasts, showToast };
}
