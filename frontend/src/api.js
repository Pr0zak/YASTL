/**
 * YASTL - API wrapper functions
 *
 * Standalone async functions that make fetch calls and return JSON responses.
 * These do NOT reference Vue reactive state — callers handle state updates.
 */

/* ==================================================================
   Models
   ================================================================== */

export async function apiGetModels(params) {
    const res = await fetch(`/api/models?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiGetModel(id) {
    const res = await fetch(`/api/models/${id}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiUpdateModel(id, data) {
    const res = await fetch(`/api/models/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'Update failed');
    return json;
}

export async function apiDeleteModel(id) {
    const res = await fetch(`/api/models/${id}`, { method: 'DELETE' });
    if (!res.ok) {
        const json = await res.json();
        throw new Error(json.detail || 'Delete failed');
    }
    return res.json();
}

export async function apiRenameModelFile(id) {
    const res = await fetch(`/api/models/${id}/rename-file`, { method: 'POST' });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'Rename failed');
    return json;
}

/* ==================================================================
   Tags
   ================================================================== */

export async function apiGetTags() {
    const res = await fetch('/api/tags');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiAddTagsToModel(id, tags) {
    const res = await fetch(`/api/models/${id}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'Failed to add tag');
    return json;
}

export async function apiRemoveTagFromModel(id, tagName) {
    const res = await fetch(`/api/models/${id}/tags/${encodeURIComponent(tagName)}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to remove tag');
    return res.json();
}

export async function apiSuggestTags(id) {
    const res = await fetch(`/api/models/suggest-tags/${id}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

/* ==================================================================
   Categories
   ================================================================== */

export async function apiGetCategories() {
    const res = await fetch('/api/categories');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiAddCategoryToModel(id, categoryId) {
    const res = await fetch(`/api/models/${id}/categories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category_id: categoryId }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'Failed to add category');
    return json;
}

export async function apiRemoveCategoryFromModel(id, categoryId) {
    const res = await fetch(`/api/models/${id}/categories/${categoryId}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to remove category');
    return res.json();
}

/* ==================================================================
   Search
   ================================================================== */

export async function apiSearchModels(params) {
    const res = await fetch(`/api/search?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

/* ==================================================================
   Libraries
   ================================================================== */

export async function apiGetLibraries() {
    const res = await fetch('/api/libraries');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiAddLibrary(name, path) {
    const res = await fetch('/api/libraries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, path }),
    });
    const json = await res.json();
    return { ok: res.ok, data: json };
}

export async function apiRemoveLibrary(id) {
    const res = await fetch(`/api/libraries/${id}`, { method: 'DELETE' });
    if (!res.ok) {
        const json = await res.json();
        throw new Error(json.detail || 'Failed to remove library');
    }
}

/* ==================================================================
   Scan
   ================================================================== */

export async function apiTriggerScan() {
    const res = await fetch('/api/scan', { method: 'POST' });
    const json = await res.json();
    return { ok: res.ok, data: json };
}

export async function apiGetScanStatus() {
    const res = await fetch('/api/scan/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

/* ==================================================================
   Favorites
   ================================================================== */

export async function apiToggleFavorite(id, isFavorite) {
    const method = isFavorite ? 'DELETE' : 'POST';
    const res = await fetch(`/api/models/${id}/favorite`, { method });
    if (!res.ok) throw new Error('Failed to toggle favorite');
    return res.json();
}

export async function apiGetFavoritesCount() {
    const res = await fetch('/api/favorites?limit=1&offset=0');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

/* ==================================================================
   Collections
   ================================================================== */

export async function apiGetCollections() {
    const res = await fetch('/api/collections');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiCreateCollection(data) {
    const res = await fetch('/api/collections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'Failed to create collection');
    return json;
}

export async function apiUpdateCollection(id, data) {
    const res = await fetch(`/api/collections/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update collection');
    return res.json();
}

export async function apiDeleteCollection(id) {
    const res = await fetch(`/api/collections/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete collection');
}

export async function apiAddToCollection(collectionId, modelIds) {
    const res = await fetch(`/api/collections/${collectionId}/models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_ids: modelIds }),
    });
    if (!res.ok) throw new Error('Failed to add to collection');
    return res.json();
}

export async function apiRemoveFromCollection(collectionId, modelId) {
    const res = await fetch(`/api/collections/${collectionId}/models/${modelId}`, {
        method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to remove from collection');
    return res.json();
}

/* ==================================================================
   Saved Searches
   ================================================================== */

export async function apiGetSavedSearches() {
    const res = await fetch('/api/saved-searches');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiSaveSearch(data) {
    const res = await fetch('/api/saved-searches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to save search');
    return res.json();
}

export async function apiDeleteSavedSearch(id) {
    const res = await fetch(`/api/saved-searches/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete saved search');
}

/* ==================================================================
   Settings
   ================================================================== */

export async function apiGetSettings() {
    const res = await fetch('/api/settings');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiUpdateSettings(data) {
    const res = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'Failed to update setting');
    return json;
}

export async function apiRegenerateThumbnails() {
    const res = await fetch('/api/settings/regenerate-thumbnails', { method: 'POST' });
    if (!res.ok) {
        const json = await res.json();
        throw new Error(json.detail || 'Failed to start regeneration');
    }
    return res.json();
}

export async function apiGetRegenStatus() {
    const res = await fetch('/api/settings/regenerate-thumbnails/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiAutoTagAll() {
    const res = await fetch('/api/settings/auto-tag-all', { method: 'POST' });
    if (!res.ok) {
        const json = await res.json();
        throw new Error(json.detail || 'Failed to start auto-tagging');
    }
    return res.json();
}

export async function apiGetAutoTagStatus() {
    const res = await fetch('/api/settings/auto-tag-all/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

/* ==================================================================
   Stats
   ================================================================== */

export async function apiGetStats() {
    const res = await fetch('/api/stats');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

/* ==================================================================
   System Status
   ================================================================== */

export async function apiGetSystemStatus() {
    const res = await fetch('/api/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

/* ==================================================================
   Updates
   ================================================================== */

export async function apiCheckForUpdates() {
    const res = await fetch('/api/update/check');
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'Failed to check for updates');
    return json;
}

export async function apiApplyUpdate() {
    const res = await fetch('/api/update/apply', { method: 'POST' });
    const json = await res.json();
    return { ok: res.ok, data: json };
}

export async function apiHealthCheck() {
    const res = await fetch('/health');
    return res.ok;
}

/* ==================================================================
   Import
   ================================================================== */

export async function apiPreviewImport(url) {
    const res = await fetch('/api/import/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
    });
    if (res.ok) {
        return await res.json();
    }
    const err = await res.json();
    return { error: err.detail || 'Preview failed' };
}

export async function apiStartImport(urls, libraryId, subfolder) {
    const res = await fetch('/api/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls, library_id: libraryId, subfolder: subfolder || null }),
    });
    const json = await res.json();
    return { ok: res.ok, data: json };
}

export async function apiGetImportStatus() {
    const res = await fetch('/api/import/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiUploadFiles(formData) {
    const res = await fetch('/api/import/upload', {
        method: 'POST',
        body: formData,
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'Upload failed');
    return json;
}

export async function apiGetImportCredentials() {
    const res = await fetch('/api/import/credentials');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

export async function apiSaveImportCredential(site, credentials) {
    const res = await fetch('/api/import/credentials', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ site, credentials }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'Failed to save credentials');
    return json;
}

export async function apiDeleteImportCredential(site) {
    const res = await fetch(`/api/import/credentials/${site}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to remove credentials');
    return res.json();
}

/* ==================================================================
   Bulk Operations
   ================================================================== */

export async function apiBulkFavorite(modelIds, favorite) {
    const res = await fetch('/api/bulk/favorite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_ids: modelIds, favorite }),
    });
    if (!res.ok) throw new Error('Bulk favorite failed');
    return res.json();
}

export async function apiBulkAddTags(modelIds, tags) {
    const res = await fetch('/api/bulk/tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_ids: modelIds, tags }),
    });
    if (!res.ok) throw new Error('Bulk tag failed');
    return res.json();
}

export async function apiBulkAutoTag(modelIds) {
    const res = await fetch('/api/bulk/auto-tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_ids: modelIds }),
    });
    if (!res.ok) throw new Error('Auto-tag failed');
    return res.json();
}

export async function apiBulkAddToCollection(modelIds, collectionId) {
    const res = await fetch('/api/bulk/collections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_ids: modelIds, collection_id: collectionId }),
    });
    if (!res.ok) throw new Error('Bulk add to collection failed');
    return res.json();
}

export async function apiBulkDelete(modelIds) {
    const res = await fetch('/api/bulk/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_ids: modelIds }),
    });
    if (!res.ok) throw new Error('Bulk delete failed');
    return res.json();
}
