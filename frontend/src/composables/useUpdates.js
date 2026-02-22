/**
 * YASTL - Update system composable
 *
 * Manages checking for and applying application updates.
 */

import { apiCheckForUpdates, apiApplyUpdate, apiHealthCheck } from '../api.js';

import { reactive } from 'vue';

/**
 * @param {Function} showToast - Toast notification function
 */
export function useUpdates(showToast, showConfirm) {
    const updateInfo = reactive({
        checked: false,
        checking: false,
        update_available: false,
        current_version: '',
        current_sha: '',
        remote_sha: '',
        commits_behind: 0,
        commits: [],
        is_git_repo: false,
        remote_url: '',
        branch: '',
        error: null,
        applying: false,
        restarting: false,
    });

    async function checkForUpdates() {
        updateInfo.checking = true;
        updateInfo.error = null;
        try {
            const data = await apiCheckForUpdates();
            updateInfo.checked = true;
            updateInfo.update_available = data.update_available;
            updateInfo.current_version = data.current_version;
            updateInfo.current_sha = data.current_sha;
            updateInfo.remote_sha = data.remote_sha;
            updateInfo.commits_behind = data.commits_behind;
            updateInfo.commits = data.commits || [];
            updateInfo.is_git_repo = data.is_git_repo;
            updateInfo.remote_url = data.remote_url;
            updateInfo.branch = data.branch;
            if (data.error) {
                updateInfo.error = data.error;
            }
        } catch (err) {
            updateInfo.error = err.message || 'Failed to check for updates';
            console.error('checkForUpdates error:', err);
        } finally {
            updateInfo.checking = false;
        }
    }

    async function applyUpdate() {
        if (!await showConfirm({
            title: 'Apply Update',
            message: 'Update and restart YASTL? App will be briefly unavailable.',
            action: 'Update',
        })) return;
        updateInfo.applying = true;
        updateInfo.error = null;
        try {
            const { ok, data } = await apiApplyUpdate();
            if (ok) {
                updateInfo.applying = false;
                updateInfo.restarting = true;
                showToast('Update applied. Restarting...', 'info');
                waitForRestart();
            } else {
                updateInfo.error = data.detail || 'Update failed';
                showToast(data.detail || 'Update failed', 'error');
            }
        } catch (err) {
            // Connection may drop during restart - that's expected
            updateInfo.applying = false;
            updateInfo.restarting = true;
            showToast('Update applied. Restarting...', 'info');
            waitForRestart();
        }
    }

    function waitForRestart() {
        let attempts = 0;
        const maxAttempts = 30;
        const interval = setInterval(async () => {
            attempts++;
            try {
                const ok = await apiHealthCheck();
                if (ok) {
                    clearInterval(interval);
                    updateInfo.restarting = false;
                    updateInfo.update_available = false;
                    updateInfo.commits_behind = 0;
                    updateInfo.commits = [];
                    updateInfo.checked = false;
                    showToast('YASTL has been updated and restarted');
                    // Refresh page to load any frontend changes
                    setTimeout(() => window.location.reload(), 1000);
                }
            } catch {
                // Server still down, keep polling
            }
            if (attempts >= maxAttempts) {
                clearInterval(interval);
                updateInfo.restarting = false;
                updateInfo.error = 'Service did not come back after restart. Check server logs.';
                showToast('Restart may have failed. Check server logs.', 'error');
            }
        }, 2000);
    }

    return {
        updateInfo,
        checkForUpdates,
        applyUpdate,
    };
}
