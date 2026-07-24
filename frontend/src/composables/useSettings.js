/**
 * YASTL - Settings composable
 *
 * Manages settings modal state, library management, and thumbnail settings.
 */

import {
    apiGetLibraries,
    apiAddLibrary,
    apiRemoveLibrary,
    apiGetSettings,
    apiUpdateSettings,
    apiTestWebhook,
    apiTestAi,
    apiEmbedBackfill,
    apiGetEmbedBackfillStatus,
    apiRegenerateThumbnails,
    apiGetRegenStatus,
    apiGeneratePreviews,
    apiGetGeneratePreviewsStatus,
    apiAutoTagAll,
    apiGetAutoTagStatus,
    apiExtractMetadata,
    apiGetMetadataStatus,
} from '../api.js';

import { ref, reactive } from 'vue';

/** Common printer bed presets. */
export const BED_PRESETS = [
    { name: 'Ender 3', width: 220, depth: 220, height: 250, shape: 'rectangular' },
    { name: 'Prusa MK3S+', width: 250, depth: 210, height: 210, shape: 'rectangular' },
    { name: 'Bambu Lab P1S', width: 256, depth: 256, height: 256, shape: 'rectangular' },
    { name: 'Bambu Lab A1', width: 256, depth: 256, height: 256, shape: 'rectangular' },
    { name: 'Voron 2.4 350', width: 350, depth: 350, height: 340, shape: 'rectangular' },
    { name: 'Custom', width: null, depth: null, height: null, shape: null },
];

/**
 * @param {Function} showToast - Toast notification function
 * @param {Function} fetchModelsFn - Callback to refresh models after regen
 * @param {Function} showConfirm - Confirm dialog function
 * @param {Function} fetchTagsFn - Callback to refresh tags after auto-tag
 */
export function useSettings(showToast, fetchModelsFn, showConfirm, fetchTagsFn) {
    const showSettings = ref(false);
    const libraries = ref([]);
    const newLibName = ref('');
    const newLibPath = ref('');
    const addingLibrary = ref(false);
    const thumbnailMode = ref('solid');
    const regeneratingThumbnails = ref(false);
    const regenProgress = reactive({ running: false, total: 0, completed: 0 });
    const autoTagging = ref(false);
    const autoTagProgress = reactive({ running: false, total: 0, completed: 0, tags_added: 0 });
    const extractingMetadata = ref(false);
    const metadataProgress = reactive({ running: false, total: 0, completed: 0, updated: 0 });
    const generatingPreviews = ref(false);
    const previewProgress = reactive({ running: false, total: 0, completed: 0, generated: 0 });

    // Print bed config
    const bedConfig = reactive({
        enabled: false,
        shape: 'rectangular',
        width: 256,
        depth: 256,
        height: 256,
    });
    const bedPreset = ref('Custom');

    // Color theme
    const colorTheme = ref('default');

    // Favorites first
    const favoritesFirst = ref(false);

    // Collection card tint
    const collectionCardTint = ref(false);

    // Preferred slicer
    const preferredSlicer = ref('none');

    // Auto-tag on scan
    const autoTagOnScan = ref(false);

    // Automation: scheduled scans + webhook
    const scanIntervalMinutes = ref('0');
    const webhookUrl = ref('');

    // AI (optional, bring-your-own-key). Keys arrive masked from the server.
    const ai = reactive({
        enabled: false,
        provider: 'openrouter',
        api_key: '',
        vision_model: '',
        embed_provider: 'openrouter',
        embed_key: '',
        embed_model: '',
        vocab_mode: 'controlled',
        monthly_cost_cap_usd: '0',
    });
    const aiTesting = ref(false);
    const aiTestResult = ref(null); // { ok, detail } | null
    const buildingEmbeddings = ref(false);
    const embedProgress = reactive({ running: false, total: 0, completed: 0, embedded: 0, in_memory: 0 });
    let embedPollTimer = null;

    let regenPollTimer = null;
    let autoTagPollTimer = null;
    let metadataPollTimer = null;
    let previewPollTimer = null;

    async function fetchLibraries() {
        try {
            const data = await apiGetLibraries();
            libraries.value = data.libraries || [];
        } catch (err) {
            console.error('fetchLibraries error:', err);
        }
    }

    async function addLibrary() {
        const name = newLibName.value.trim();
        const path = newLibPath.value.trim();
        if (!name || !path) {
            showToast('Name and path are required', 'error');
            return;
        }
        addingLibrary.value = true;
        try {
            const { ok, data } = await apiAddLibrary(name, path);
            if (ok) {
                libraries.value.push(data);
                newLibName.value = '';
                newLibPath.value = '';
                showToast(`Library "${name}" added`);
            } else {
                showToast(data.detail || 'Failed to add library', 'error');
            }
        } catch (err) {
            showToast('Failed to add library', 'error');
            console.error('addLibrary error:', err);
        } finally {
            addingLibrary.value = false;
        }
    }

    async function deleteLibrary(lib) {
        if (!await showConfirm({
            title: 'Remove Library',
            message: `Remove "${lib.name}"? Scanned models stay in database.`,
            action: 'Remove',
            danger: true,
        })) return;
        try {
            await apiRemoveLibrary(lib.id);
            libraries.value = libraries.value.filter((l) => l.id !== lib.id);
            showToast(`Library "${lib.name}" removed`);
        } catch (err) {
            showToast('Failed to remove library', 'error');
        }
    }

    async function fetchSettings() {
        try {
            const data = await apiGetSettings();
            thumbnailMode.value = data.thumbnail_mode || 'solid';
            // Bed settings
            bedConfig.enabled = data.bed_enabled === 'true';
            bedConfig.shape = data.bed_shape || 'rectangular';
            bedConfig.width = parseInt(data.bed_width) || 256;
            bedConfig.depth = parseInt(data.bed_depth) || 256;
            bedConfig.height = parseInt(data.bed_height) || 256;
            // Detect preset
            _detectPreset();
            // Color theme
            colorTheme.value = data.color_theme || 'default';
            applyTheme(colorTheme.value);
            // Favorites first
            favoritesFirst.value = data.favorites_first === 'true';
            // Collection card tint
            collectionCardTint.value = data.collection_card_tint === 'true';
            // Preferred slicer
            preferredSlicer.value = data.preferred_slicer || 'none';
            // Auto-tag on scan
            autoTagOnScan.value = data.auto_tag_on_scan === 'true';
            // Automation
            scanIntervalMinutes.value = data.scan_interval_minutes || '0';
            webhookUrl.value = data.webhook_url || '';
            applyAiFromData(data);
        } catch (err) {
            console.error('fetchSettings error:', err);
        }
    }

    function applyTheme(theme) {
        if (theme === 'default') {
            document.documentElement.removeAttribute('data-theme');
        } else {
            document.documentElement.setAttribute('data-theme', theme);
        }
    }

    async function toggleFavoritesFirst() {
        favoritesFirst.value = !favoritesFirst.value;
        try {
            await apiUpdateSettings({ favorites_first: favoritesFirst.value ? 'true' : 'false' });
        } catch (err) {
            showToast('Failed to save setting', 'error');
            console.error('toggleFavoritesFirst error:', err);
        }
    }

    async function toggleCollectionCardTint() {
        collectionCardTint.value = !collectionCardTint.value;
        try {
            await apiUpdateSettings({ collection_card_tint: collectionCardTint.value ? 'true' : 'false' });
        } catch (err) {
            showToast('Failed to save setting', 'error');
            console.error('toggleCollectionCardTint error:', err);
        }
    }

    async function toggleAutoTagOnScan() {
        autoTagOnScan.value = !autoTagOnScan.value;
        try {
            await apiUpdateSettings({ auto_tag_on_scan: autoTagOnScan.value ? 'true' : 'false' });
        } catch (err) {
            showToast('Failed to save setting', 'error');
            console.error('toggleAutoTagOnScan error:', err);
        }
    }

    async function setPreferredSlicer(slicer) {
        preferredSlicer.value = slicer;
        try {
            await apiUpdateSettings({ preferred_slicer: slicer });
        } catch (err) {
            showToast('Failed to save slicer setting', 'error');
            console.error('setPreferredSlicer error:', err);
        }
    }

    async function setScanInterval(minutes) {
        const val = String(parseInt(minutes) || 0);
        scanIntervalMinutes.value = val;
        try {
            await apiUpdateSettings({ scan_interval_minutes: val });
            showToast(val === '0' ? 'Scheduled scans off' : `Auto-scan every ${val} min`, 'info');
        } catch {
            showToast('Failed to save scan interval', 'error');
        }
    }

    async function setWebhookUrl(url) {
        webhookUrl.value = url;
        try {
            await apiUpdateSettings({ webhook_url: url });
        } catch {
            showToast('Failed to save webhook URL', 'error');
        }
    }

    async function testWebhook() {
        try {
            await apiTestWebhook();
            showToast('Test webhook delivered', 'success');
        } catch (err) {
            showToast(err.message || 'Webhook test failed', 'error');
        }
    }

    function applyAiFromData(data) {
        ai.enabled = data.ai_enabled === 'true';
        ai.provider = data.ai_provider || 'openrouter';
        ai.api_key = data.ai_api_key || '';           // masked if set
        ai.vision_model = data.ai_vision_model || '';
        ai.embed_provider = data.ai_embed_provider || 'openrouter';
        ai.embed_key = data.ai_embed_key || '';       // masked if set
        ai.embed_model = data.ai_embed_model || '';
        ai.vocab_mode = data.ai_autotag_vocab_mode || 'controlled';
        ai.monthly_cost_cap_usd = data.ai_monthly_cost_cap_usd || '0';
    }

    async function saveAiSettings() {
        // Send the current AI form. Masked keys ("••••…") are ignored server-side,
        // so unchanged keys are preserved.
        try {
            const data = await apiUpdateSettings({
                ai_enabled: ai.enabled ? 'true' : 'false',
                ai_provider: ai.provider,
                ai_api_key: ai.api_key,
                ai_vision_model: ai.vision_model,
                ai_embed_provider: ai.embed_provider,
                ai_embed_key: ai.embed_key,
                ai_embed_model: ai.embed_model,
                ai_autotag_vocab_mode: ai.vocab_mode,
                ai_monthly_cost_cap_usd: String(ai.monthly_cost_cap_usd || '0'),
            });
            applyAiFromData(data); // refresh masked keys
            aiTestResult.value = null;
            showToast('AI settings saved', 'success');
        } catch (err) {
            showToast(err.message || 'Failed to save AI settings', 'error');
        }
    }

    async function testAiConnection() {
        aiTesting.value = true;
        aiTestResult.value = null;
        try {
            aiTestResult.value = await apiTestAi();
        } catch (err) {
            aiTestResult.value = { ok: false, detail: err.message || 'Test failed' };
        } finally {
            aiTesting.value = false;
        }
    }

    async function refreshEmbedStatus() {
        try {
            const data = await apiGetEmbedBackfillStatus();
            embedProgress.running = data.running;
            embedProgress.total = data.total;
            embedProgress.completed = data.completed;
            embedProgress.embedded = data.embedded;
            embedProgress.in_memory = data.in_memory;
            return data;
        } catch { return null; }
    }

    async function buildEmbeddings() {
        buildingEmbeddings.value = true;
        try {
            await apiEmbedBackfill();
            showToast('Building embeddings…', 'info');
            if (embedPollTimer) clearInterval(embedPollTimer);
            embedPollTimer = setInterval(async () => {
                const data = await refreshEmbedStatus();
                if (data && !data.running) {
                    clearInterval(embedPollTimer);
                    embedPollTimer = null;
                    buildingEmbeddings.value = false;
                    if (data.error) showToast('Embedding backfill error: ' + data.error, 'error');
                    else showToast(`Embeddings ready (${data.in_memory} models)`, 'success');
                }
            }, 1500);
        } catch (err) {
            showToast(err.message || 'Failed to build embeddings', 'error');
            buildingEmbeddings.value = false;
        }
    }

    async function setColorTheme(theme) {
        colorTheme.value = theme;
        applyTheme(theme);
        try {
            await apiUpdateSettings({ color_theme: theme });
        } catch (err) {
            showToast('Failed to save theme', 'error');
            console.error('setColorTheme error:', err);
        }
    }

    function _detectPreset() {
        const match = BED_PRESETS.find(p =>
            p.width === bedConfig.width && p.depth === bedConfig.depth &&
            p.height === bedConfig.height && p.shape === bedConfig.shape
        );
        bedPreset.value = match ? match.name : 'Custom';
    }

    function setBedPreset(name) {
        const preset = BED_PRESETS.find(p => p.name === name);
        if (preset && preset.width !== null) {
            bedConfig.width = preset.width;
            bedConfig.depth = preset.depth;
            bedConfig.height = preset.height;
            bedConfig.shape = preset.shape;
        }
        bedPreset.value = name;
    }

    async function saveBedSettings() {
        try {
            await apiUpdateSettings({
                bed_enabled: bedConfig.enabled ? 'true' : 'false',
                bed_shape: bedConfig.shape,
                bed_width: String(bedConfig.width),
                bed_depth: String(bedConfig.depth),
                bed_height: String(bedConfig.height),
            });
            _detectPreset();
            showToast('Print bed settings saved');
        } catch (err) {
            showToast('Failed to save bed settings', 'error');
            console.error('saveBedSettings error:', err);
        }
    }

    async function setThumbnailMode(mode) {
        try {
            const data = await apiUpdateSettings({ thumbnail_mode: mode });
            thumbnailMode.value = data.thumbnail_mode || mode;
            showToast(`Thumbnail mode set to ${mode}`);
        } catch (err) {
            showToast('Failed to update setting', 'error');
            console.error('setThumbnailMode error:', err);
        }
    }

    async function regenerateThumbnails() {
        if (!await showConfirm({
            title: 'Regenerate Thumbnails',
            message: 'Re-render all thumbnails using current mode? Runs in background.',
            action: 'Regenerate',
        })) return;
        regeneratingThumbnails.value = true;
        try {
            await apiRegenerateThumbnails();
            showToast('Thumbnail regeneration started', 'info');
            startRegenPolling();
        } catch (err) {
            showToast(err.message || 'Failed to start thumbnail regeneration', 'error');
            console.error('regenerateThumbnails error:', err);
            regeneratingThumbnails.value = false;
        }
    }

    function startRegenPolling() {
        if (regenPollTimer) clearInterval(regenPollTimer);
        regenPollTimer = setInterval(async () => {
            try {
                const data = await apiGetRegenStatus();
                regenProgress.running = data.running;
                regenProgress.total = data.total;
                regenProgress.completed = data.completed;
                if (!data.running) {
                    clearInterval(regenPollTimer);
                    regenPollTimer = null;
                    regeneratingThumbnails.value = false;
                    showToast('Thumbnail regeneration complete');
                    fetchModelsFn();
                }
            } catch (err) {
                console.error('regenPoll error:', err);
            }
        }, 2000);
    }

    async function generatePreviews() {
        if (!await showConfirm({
            title: 'Generate 3D Previews',
            message: 'Pre-build decimated previews for large models so they open '
                + 'instantly? Runs in background.',
            action: 'Generate',
        })) return;
        generatingPreviews.value = true;
        try {
            await apiGeneratePreviews();
            showToast('Preview generation started', 'info');
            startPreviewPolling();
        } catch (err) {
            showToast(err.message || 'Failed to start preview generation', 'error');
            console.error('generatePreviews error:', err);
            generatingPreviews.value = false;
        }
    }

    function startPreviewPolling() {
        if (previewPollTimer) clearInterval(previewPollTimer);
        previewPollTimer = setInterval(async () => {
            try {
                const data = await apiGetGeneratePreviewsStatus();
                previewProgress.running = data.running;
                previewProgress.total = data.total;
                previewProgress.completed = data.completed;
                previewProgress.generated = data.generated;
                if (!data.running) {
                    clearInterval(previewPollTimer);
                    previewPollTimer = null;
                    generatingPreviews.value = false;
                    showToast('Preview generation complete');
                }
            } catch (err) {
                console.error('previewPoll error:', err);
            }
        }, 2000);
    }

    async function autoTagAll() {
        if (!await showConfirm({
            title: 'Auto-Tag All Models',
            message: 'Generate and apply suggested tags to all models? Runs in background.',
            action: 'Auto-Tag',
        })) return;
        autoTagging.value = true;
        try {
            await apiAutoTagAll();
            showToast('Auto-tagging started', 'info');
            startAutoTagPolling();
        } catch (err) {
            showToast(err.message || 'Failed to start auto-tagging', 'error');
            console.error('autoTagAll error:', err);
            autoTagging.value = false;
        }
    }

    function startAutoTagPolling() {
        if (autoTagPollTimer) clearInterval(autoTagPollTimer);
        autoTagPollTimer = setInterval(async () => {
            try {
                const data = await apiGetAutoTagStatus();
                autoTagProgress.running = data.running;
                autoTagProgress.total = data.total;
                autoTagProgress.completed = data.completed;
                autoTagProgress.tags_added = data.tags_added;
                if (!data.running) {
                    clearInterval(autoTagPollTimer);
                    autoTagPollTimer = null;
                    autoTagging.value = false;
                    showToast(`Auto-tagging complete: ${data.tags_added} tags added`);
                    fetchModelsFn();
                    if (fetchTagsFn) fetchTagsFn();
                }
            } catch (err) {
                console.error('autoTagPoll error:', err);
            }
        }, 2000);
    }

    async function extractMetadata() {
        if (!await showConfirm({
            title: 'Extract Metadata',
            message: 'Extract descriptions and tags from README files in zips and folders? Only updates models with empty descriptions. Runs in background.',
            action: 'Extract',
        })) return;
        extractingMetadata.value = true;
        try {
            await apiExtractMetadata();
            showToast('Metadata extraction started', 'info');
            startMetadataPolling();
        } catch (err) {
            showToast(err.message || 'Failed to start metadata extraction', 'error');
            console.error('extractMetadata error:', err);
            extractingMetadata.value = false;
        }
    }

    function startMetadataPolling() {
        if (metadataPollTimer) clearInterval(metadataPollTimer);
        metadataPollTimer = setInterval(async () => {
            try {
                const data = await apiGetMetadataStatus();
                metadataProgress.running = data.running;
                metadataProgress.total = data.total;
                metadataProgress.completed = data.completed;
                metadataProgress.updated = data.updated;
                if (!data.running) {
                    clearInterval(metadataPollTimer);
                    metadataPollTimer = null;
                    extractingMetadata.value = false;
                    showToast(`Metadata extraction complete: ${data.updated} models updated`);
                    fetchModelsFn();
                    if (fetchTagsFn) fetchTagsFn();
                }
            } catch (err) {
                console.error('metadataPoll error:', err);
            }
        }, 2000);
    }

    function openSettings(checkForUpdatesFn, updateInfo) {
        fetchLibraries();
        fetchSettings();
        showSettings.value = true;
        document.body.classList.add('modal-open');
        // Auto-check for updates if not checked yet
        if (checkForUpdatesFn && updateInfo && !updateInfo.checked && !updateInfo.checking) {
            checkForUpdatesFn();
        }
    }

    function closeSettings(showDetail) {
        showSettings.value = false;
        if (!showDetail) {
            document.body.classList.remove('modal-open');
        }
    }

    return {
        // State
        showSettings,
        libraries,
        newLibName,
        newLibPath,
        addingLibrary,
        thumbnailMode,
        regeneratingThumbnails,
        regenProgress,
        generatingPreviews,
        previewProgress,
        generatePreviews,
        autoTagging,
        autoTagProgress,
        extractingMetadata,
        metadataProgress,
        bedConfig,
        bedPreset,
        colorTheme,
        favoritesFirst,
        collectionCardTint,
        preferredSlicer,
        autoTagOnScan,

        // Actions
        fetchLibraries,
        addLibrary,
        deleteLibrary,
        fetchSettings,
        setThumbnailMode,
        regenerateThumbnails,
        autoTagAll,
        extractMetadata,
        setBedPreset,
        saveBedSettings,
        setColorTheme,
        toggleFavoritesFirst,
        toggleCollectionCardTint,
        setPreferredSlicer,
        toggleAutoTagOnScan,
        scanIntervalMinutes,
        webhookUrl,
        setScanInterval,
        setWebhookUrl,
        testWebhook,
        ai,
        aiTesting,
        aiTestResult,
        saveAiSettings,
        testAiConnection,
        buildingEmbeddings,
        embedProgress,
        buildEmbeddings,
        refreshEmbedStatus,
        openSettings,
        closeSettings,
    };
}
