/**
 * Project Detail Page JavaScript - handles clip management, timeline, and editing.
 */

document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const clipsTimeline = document.getElementById('clips-timeline');
    const emptyTimeline = document.getElementById('empty-timeline');
    const addClipBtn = document.getElementById('add-clip-btn');
    const deleteProjectBtn = document.getElementById('delete-project-btn');
    const exportBtn = document.getElementById('export-btn');
    const projectName = document.getElementById('project-name');
    const voiceoverScript = document.getElementById('voiceover-script');
    const projectNotes = document.getElementById('project-notes');
    const usageList = document.getElementById('usage-list');

    // Modals
    const addClipModal = document.getElementById('add-clip-modal');
    const exportModal = document.getElementById('export-modal');

    let currentClips = [];
    let dragStartIndex = null;

    // Load project data
    loadProject();

    // Event listeners
    if (addClipBtn) {
        addClipBtn.addEventListener('click', showAddClipModal);
    }

    if (deleteProjectBtn) {
        deleteProjectBtn.addEventListener('click', handleDeleteProject);
    }

    if (exportBtn) {
        exportBtn.addEventListener('click', showExportModal);
    }

    // Editable project name
    if (projectName) {
        projectName.addEventListener('blur', () => {
            const newName = projectName.textContent.trim();
            if (newName && newName !== window.initialProjectName) {
                updateProject({ name: newName });
            }
        });

        projectName.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                projectName.blur();
            }
        });
    }

    // Auto-save for textareas
    setupAutoSave(voiceoverScript, 'description', 'script-save-status');
    setupAutoSave(projectNotes, 'notes', 'notes-save-status');

    // Modal close handlers
    document.getElementById('close-add-clip')?.addEventListener('click', hideAddClipModal);
    document.getElementById('close-export')?.addEventListener('click', hideExportModal);
    document.getElementById('cancel-export')?.addEventListener('click', hideExportModal);
    document.getElementById('confirm-export')?.addEventListener('click', handleExport);

    // Close on backdrop click
    addClipModal?.addEventListener('click', (e) => {
        if (e.target === addClipModal) hideAddClipModal();
    });
    exportModal?.addEventListener('click', (e) => {
        if (e.target === exportModal) hideExportModal();
    });

    // Search handling
    const clipSearch = document.getElementById('clip-search');
    const unusedOnly = document.getElementById('unused-only');

    let searchTimeout = null;
    if (clipSearch) {
        clipSearch.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                searchClips(clipSearch.value, unusedOnly?.checked);
            }, 300);
        });
    }

    if (unusedOnly) {
        unusedOnly.addEventListener('change', () => {
            searchClips(clipSearch.value, unusedOnly.checked);
        });
    }

    async function loadProject() {
        try {
            const response = await fetch(`/api/projects/${PROJECT_ID}`);

            if (!response.ok) {
                if (response.status === 404) {
                    window.location.href = '/projects';
                    return;
                }
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            currentClips = data.clips || [];

            renderClips(currentClips);
            renderUsageHeatmap(data.clips || []);

            // Store initial name for comparison
            window.initialProjectName = data.project?.name;
        } catch (error) {
            console.error('Error loading project:', error);
            clipsTimeline.innerHTML = `<div class="error">Error loading project: ${error.message}</div>`;
        }
    }

    function renderClips(clips) {
        if (clips.length === 0) {
            clipsTimeline.style.display = 'none';
            emptyTimeline.style.display = 'block';
            return;
        }

        clipsTimeline.style.display = 'flex';
        emptyTimeline.style.display = 'none';

        clipsTimeline.innerHTML = clips.map((clip, index) => {
            const thumbnail = clip.thumbnail_url || '/static/placeholder.jpg';
            const title = clip.marker_label || clip.file_name || `Video ${clip.video_id}`;
            const hasMarker = clip.video_marker_id !== null;
            const duration = hasMarker && clip.in_seconds !== null
                ? formatDuration(clip.out_seconds - clip.in_seconds)
                : 'Full video';

            const usageClass = getUsageClass(clip.usage_count || 0);
            const usageTooltip = clip.usage_count > 0
                ? `Used in ${clip.usage_count} projects`
                : 'Not used';

            return `
                <div class="clip-item" data-clip-id="${clip.id}" data-index="${index}" draggable="true">
                    <div class="clip-drag-handle">⋮⋮</div>
                    <img class="clip-thumbnail" src="${thumbnail}" alt="${escapeHtml(title)}">
                    <div class="clip-info">
                        <div class="clip-title">${escapeHtml(title)}</div>
                        <div class="clip-meta">
                            ${hasMarker ? `⏱️ ${duration}` : '🎬 Full video'}
                            <span class="clip-usage ${usageClass}" title="${usageTooltip}">
                                <span class="usage-dot"></span>
                                ${clip.usage_count || 0}
                            </span>
                        </div>
                    </div>
                    <div class="clip-actions">
                        <button class="btn-icon" title="View video" onclick="viewVideo(${clip.video_id}, ${clip.video_marker_id || 'null'})">👁️</button>
                        <button class="btn-icon delete-clip-btn" title="Remove from project" data-clip-id="${clip.id}">🗑️</button>
                    </div>
                </div>
            `;
        }).join('');

        // Add drag-drop handlers
        setupDragAndDrop();

        // Add delete handlers
        document.querySelectorAll('.delete-clip-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const clipId = btn.dataset.clipId;
                removeClip(clipId);
            });
        });
    }

    function getUsageClass(count) {
        if (count === 0) return 'usage-fresh';
        if (count <= 2) return 'usage-used';
        return 'usage-overused';
    }

    function setupDragAndDrop() {
        const items = clipsTimeline.querySelectorAll('.clip-item');

        items.forEach(item => {
            item.addEventListener('dragstart', handleDragStart);
            item.addEventListener('dragover', handleDragOver);
            item.addEventListener('drop', handleDrop);
            item.addEventListener('dragenter', handleDragEnter);
            item.addEventListener('dragleave', handleDragLeave);
        });
    }

    function handleDragStart(e) {
        dragStartIndex = parseInt(this.dataset.index);
        this.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
    }

    function handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    }

    function handleDragEnter(e) {
        this.classList.add('drag-over');
    }

    function handleDragLeave(e) {
        this.classList.remove('drag-over');
    }

    function handleDrop(e) {
        e.preventDefault();
        this.classList.remove('drag-over');

        const dragEndIndex = parseInt(this.dataset.index);

        if (dragStartIndex !== dragEndIndex) {
            reorderClips(dragStartIndex, dragEndIndex);
        }

        document.querySelectorAll('.clip-item.dragging').forEach(el => {
            el.classList.remove('dragging');
        });
    }

    async function reorderClips(fromIndex, toIndex) {
        // Reorder the array
        const newClips = [...currentClips];
        const [moved] = newClips.splice(fromIndex, 1);
        newClips.splice(toIndex, 0, moved);

        // Update UI immediately
        renderClips(newClips);

        // Send new order to server
        const clipIds = newClips.map(c => c.id);

        try {
            const response = await fetch(`/api/projects/${PROJECT_ID}/reorder`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ clip_ids: clipIds })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            currentClips = newClips;
        } catch (error) {
            console.error('Error reordering clips:', error);
            // Revert on error
            renderClips(currentClips);
            alert('Failed to reorder clips. Please try again.');
        }
    }

    function renderUsageHeatmap(clips) {
        if (clips.length === 0) {
            usageList.innerHTML = '<div class="placeholder">No clips to show usage</div>';
            return;
        }

        usageList.innerHTML = clips.map(clip => {
            const title = clip.marker_label || clip.file_name || `Video ${clip.video_id}`;
            const count = clip.usage_count || 0;
            const usageClass = getUsageClass(count);

            return `
                <div class="usage-item ${usageClass}">
                    <span class="usage-dot"></span>
                    <span class="usage-title">${escapeHtml(title.substring(0, 30))}</span>
                    <span class="usage-count">${count}</span>
                </div>
            `;
        }).join('');
    }

    async function updateProject(updates) {
        try {
            const response = await fetch(`/api/projects/${PROJECT_ID}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            return true;
        } catch (error) {
            console.error('Error updating project:', error);
            return false;
        }
    }

    function setupAutoSave(element, fieldName, statusId) {
        if (!element) return;

        let timeout = null;
        const statusEl = document.getElementById(statusId);

        element.addEventListener('input', () => {
            if (statusEl) {
                statusEl.textContent = 'Unsaved';
                statusEl.className = 'save-status';
            }

            clearTimeout(timeout);
            timeout = setTimeout(async () => {
                if (statusEl) {
                    statusEl.textContent = 'Saving...';
                    statusEl.className = 'save-status saving';
                }

                const success = await updateProject({ [fieldName]: element.value });

                if (statusEl) {
                    if (success) {
                        statusEl.textContent = 'Saved';
                        statusEl.className = 'save-status saved';
                        setTimeout(() => {
                            statusEl.textContent = '';
                        }, 2000);
                    } else {
                        statusEl.textContent = 'Failed to save';
                        statusEl.className = 'save-status';
                    }
                }
            }, 1000);
        });
    }

    async function removeClip(clipId) {
        if (!confirm('Remove this clip from the project?')) return;

        try {
            const response = await fetch(`/api/projects/${PROJECT_ID}/clips/${clipId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            // Remove from current clips and re-render
            currentClips = currentClips.filter(c => c.id != clipId);
            renderClips(currentClips);
            renderUsageHeatmap(currentClips);
        } catch (error) {
            console.error('Error removing clip:', error);
            alert('Failed to remove clip. Please try again.');
        }
    }

    function showAddClipModal() {
        addClipModal.style.display = 'flex';
        document.getElementById('clip-search')?.focus();
    }

    function hideAddClipModal() {
        addClipModal.style.display = 'none';
        document.getElementById('clip-search').value = '';
        document.getElementById('search-results').innerHTML = '<div class="placeholder">Enter a search term to find clips</div>';
    }

    async function searchClips(query, unusedOnly) {
        const resultsContainer = document.getElementById('search-results');

        if (!query || query.length < 2) {
            resultsContainer.innerHTML = '<div class="placeholder">Enter at least 2 characters to search</div>';
            return;
        }

        resultsContainer.innerHTML = '<div class="loading">Searching...</div>';

        try {
            const params = new URLSearchParams({ q: query });
            if (unusedOnly) {
                params.append('unused_in_project', PROJECT_ID);
            }
            params.append('show_usage', 'true');

            const response = await fetch(`/api/search?${params.toString()}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            renderSearchResults(data.results || []);
        } catch (error) {
            console.error('Error searching clips:', error);
            resultsContainer.innerHTML = `<div class="error">Search failed: ${error.message}</div>`;
        }
    }

    function renderSearchResults(results) {
        const container = document.getElementById('search-results');

        if (results.length === 0) {
            container.innerHTML = '<div class="placeholder">No clips found</div>';
            return;
        }

        container.innerHTML = results.map(result => {
            const title = result.marker_label || result.file_name || `Video ${result.video_id}`;
            const usageCount = result.usage_count || 0;
            const usageClass = getUsageClass(usageCount);

            return `
                <div class="result-item">
                    <span class="result-title">${escapeHtml(title)}</span>
                    <span class="usage-badge ${usageClass}">${usageCount} uses</span>
                    <button class="add-btn" onclick="addClipToProject(${result.video_id}, ${result.marker_id || 'null'})">
                        + Add
                    </button>
                </div>
            `;
        }).join('');
    }

    async function addClipToProject(videoId, markerId) {
        try {
            const response = await fetch(`/api/projects/${PROJECT_ID}/clips`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_id: videoId,
                    video_marker_id: markerId
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            hideAddClipModal();
            loadProject(); // Refresh the clips
        } catch (error) {
            console.error('Error adding clip:', error);
            alert('Failed to add clip. Please try again.');
        }
    }

    // Expose to window for inline handlers
    window.viewVideo = function(videoId, markerId) {
        const url = markerId
            ? `/video/${videoId}?marker=${markerId}`
            : `/video/${videoId}`;
        window.open(url, '_blank');
    };

    window.addClipToProject = addClipToProject;

    async function handleDeleteProject() {
        if (!confirm('Are you sure you want to delete this project? This cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch(`/api/projects/${PROJECT_ID}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            window.location.href = '/projects';
        } catch (error) {
            console.error('Error deleting project:', error);
            alert('Failed to delete project. Please try again.');
        }
    }

    function showExportModal() {
        exportModal.style.display = 'flex';
    }

    function hideExportModal() {
        exportModal.style.display = 'none';
    }

    async function handleExport() {
        const pathInput = document.getElementById('export-path');
        const outputPath = pathInput?.value?.trim();

        if (!outputPath) {
            alert('Please enter an output file path');
            return;
        }

        try {
            // Note: Export is currently a CLI-only feature
            // Web export would require additional backend implementation
            alert('Export is available via CLI: broll project export ' + PROJECT_ID + ' --drive /path/to/drive --output ' + outputPath);
            hideExportModal();
        } catch (error) {
            console.error('Error exporting:', error);
            alert('Export failed: ' + error.message);
        }
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatDuration(seconds) {
        if (!seconds) return '0s';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        if (mins > 0) {
            return `${mins}m ${secs}s`;
        }
        return `${secs}s`;
    }
});
