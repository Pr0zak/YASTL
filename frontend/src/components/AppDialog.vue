<script>
/*
 * Open dialogs, oldest first. Only the last one reacts to Escape and owns the
 * focus trap, so a confirm opened on top of another dialog closes on its own
 * rather than taking the dialog underneath with it.
 */
const openStack = [];
let idSeq = 0;
</script>

<script setup>
/**
 * AppDialog - the one shell every modal in the app renders into.
 *
 * Desktop: a centred card. Phone (<=768px): a bottom sheet with a grab
 * handle and a sticky footer, so actions stay in thumb reach. Either way it
 * is a real dialog: role and aria-modal, a focus trap, focus returned to the
 * opener on close, and Escape handled here in the capture phase so the
 * App-level shortcut handler never sees it.
 *
 * Before this, the app had five overlay systems and one (Duplicates) that
 * referenced classes no stylesheet defined, so it rendered in page flow
 * thousands of pixels below the viewport.
 */
import { ref, watch, nextTick, onBeforeUnmount, useSlots } from 'vue';
import { ICONS } from '../icons.js';

const props = defineProps({
    show: { type: Boolean, default: false },
    title: { type: String, default: '' },
    subtitle: { type: String, default: '' },
    /** sm 440px, md 640px, lg 900px */
    size: { type: String, default: 'md' },
    /** alertdialog for confirmations that interrupt the user */
    role: { type: String, default: 'dialog' },
    /** Clicking the backdrop closes. Off for forms that would lose input. */
    dismissOnBackdrop: { type: Boolean, default: true },
    /** Stretch to full height on a phone instead of sizing to content. */
    fullHeightMobile: { type: Boolean, default: false },
    /** Extra class on the panel for per-dialog styling. */
    panelClass: { type: String, default: '' },
});

const emit = defineEmits(['close']);
const slots = useSlots();

const panel = ref(null);
const titleId = `app-dialog-title-${++idSeq}`;
let opener = null;
const self = {};

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function isTop() {
    return openStack[openStack.length - 1] === self;
}

function focusables() {
    if (!panel.value) return [];
    return [...panel.value.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null || el === document.activeElement);
}

function onKeydown(e) {
    if (!isTop()) return;
    if (e.key === 'Escape') {
        e.stopImmediatePropagation();
        e.preventDefault();
        emit('close');
    } else if (e.key === 'Tab') {
        const items = focusables();
        if (!items.length) {
            e.preventDefault();
            panel.value?.focus();
            return;
        }
        const first = items[0];
        const last = items[items.length - 1];
        const active = document.activeElement;
        if (e.shiftKey && (active === first || !panel.value.contains(active))) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && (active === last || !panel.value.contains(active))) {
            e.preventDefault();
            first.focus();
        }
    }
}

async function onOpen() {
    opener = document.activeElement;
    openStack.push(self);
    document.body.classList.add('dialog-open');
    document.addEventListener('keydown', onKeydown, true);
    await nextTick();
    // Prefer an element that asked for focus, then the first form field,
    // then the panel itself — never the close button, which a stray Enter
    // would then activate.
    const target = panel.value?.querySelector('[autofocus], [data-autofocus]')
        || panel.value?.querySelector('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), textarea, select')
        || panel.value;
    target?.focus({ preventScroll: true });
}

function onClosed() {
    const i = openStack.indexOf(self);
    if (i === -1) return;
    openStack.splice(i, 1);
    if (!openStack.length) document.body.classList.remove('dialog-open');
    document.removeEventListener('keydown', onKeydown, true);
    if (opener && typeof opener.focus === 'function' && document.contains(opener)) {
        opener.focus({ preventScroll: true });
    }
    opener = null;
}

watch(() => props.show, (v) => (v ? onOpen() : onClosed()), { immediate: true });
onBeforeUnmount(onClosed);

function onBackdrop() {
    if (props.dismissOnBackdrop) emit('close');
}
</script>

<template>
    <teleport to="body">
        <div v-if="show" class="app-dialog-overlay" @click.self="onBackdrop">
            <div ref="panel"
                 class="app-dialog"
                 :class="['app-dialog-' + size, { 'app-dialog-tall': fullHeightMobile }, panelClass]"
                 :role="role"
                 aria-modal="true"
                 :aria-labelledby="title || slots.title ? titleId : undefined"
                 tabindex="-1">
                <div class="app-dialog-grab" aria-hidden="true"></div>
                <header v-if="title || slots.title || slots.headerExtra" class="app-dialog-header">
                    <div class="app-dialog-heading">
                        <h2 :id="titleId" class="app-dialog-title">
                            <slot name="title">{{ title }}</slot>
                        </h2>
                        <p v-if="subtitle" class="app-dialog-subtitle">{{ subtitle }}</p>
                    </div>
                    <slot name="headerExtra"></slot>
                    <button type="button" class="app-dialog-close" aria-label="Close" title="Close"
                            @click="emit('close')" v-html="ICONS.close"></button>
                </header>
                <div class="app-dialog-body">
                    <slot></slot>
                </div>
                <footer v-if="slots.footer" class="app-dialog-footer">
                    <slot name="footer"></slot>
                </footer>
            </div>
        </div>
    </teleport>
</template>
