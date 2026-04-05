document.addEventListener('DOMContentLoaded', () => {
    const state = {
        path: new URLSearchParams(window.location.search).get('path') || '',
        page: 1,
        loading: false,
        hasMore: true,
        limit: 24,
        // Multi-select state
        selected: new Set(),
        lastSelected: null,
        isMultiSelectMode: false,
        longPressDuration: 500, // ms for mobile long-press
        allLoadedVideos: [], // Track all loaded video IDs for select-all
        // Keyboard navigation
        focusedCardIndex: -1,
        videoCards: [],
        // Hover preview state
        hoverPreviewTimeout: null,
        currentPreviewVideo: null
    };

    const elements = {
        breadcrumbs: document.getElementById('breadcrumbs'),
        folderGrid: document.getElementById('folder-grid'),
        videoGrid: document.getElementById('video-grid'),
        loader: document.getElementById('loader'),
        sentinel: document.getElementById('sentinel'),
        batchToolbar: document.getElementById('batch-toolbar'),
        selectionCount: document.getElementById('selection-count'),
        selectAllBtn: document.getElementById('select-all-btn'),
        deselectAllBtn: document.getElementById('deselect-all-btn'),
        playlistDropdown: document.getElementById('playlist-dropdown'),
        playlistList: document.getElementById('playlist-list'),
        newPlaylistName: document.getElementById('new-playlist-name'),
        // Modals
        batchLocationModal: document.getElementById('batch-location-modal'),
        batchLocationSearch: document.getElementById('batch-location-search'),
        batchLocationResults: document.getElementById('batch-location-results'),
        batchLocationConfirm: document.getElementById('batch-location-confirm'),
        exportModal: document.getElementById('export-modal')
    };

    // Initial load
    loadContent(true);
    loadPlaylists();
    initKeyboardShortcuts();
    createKeyboardHelpModal();

    // Infinite scroll
    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !state.loading && state.hasMore) {
            state.page++;
            // Update history with new page count so we can restore it
            const url = new URL(window.location);
            window.history.replaceState({ path: state.path, page: state.page }, '', url);
            loadContent(false);
        }
    }, { rootMargin: '200px' });

    observer.observe(elements.sentinel);

    // Save scroll position before navigating away (any navigation)
    window.addEventListener('beforeunload', () => {
        sessionStorage.setItem(`scroll_${state.path || 'root'}`, window.scrollY);
    });

    // History handling
    window.addEventListener('popstate', (e) => {
        if (e.state) {
            state.path = e.state.path || '';
            state.page = e.state.page || 1;
        } else {
            state.path = new URLSearchParams(window.location.search).get('path') || '';
            state.page = 1;
        }
        state.hasMore = true;
        loadContent(true, true); // true for reset, true for restore
    });

    // ESC key to clear selection
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (!elements.batchLocationModal.classList.contains('hidden')) {
                closeBatchLocationModal();
            } else if (!elements.exportModal.classList.contains('hidden')) {
                closeExportModal();
            } else {
                clearSelection();
            }
        }
    });

    // Batch toolbar event listeners
    if (elements.selectAllBtn) elements.selectAllBtn.addEventListener('click', selectAll);
    if (elements.deselectAllBtn) elements.deselectAllBtn.addEventListener('click', clearSelection);
    const clearSelectionBtn = document.getElementById('clear-selection-btn');
    if (clearSelectionBtn) clearSelectionBtn.addEventListener('click', clearSelection);
    
    const addToPlaylistBtn = document.getElementById('add-to-playlist-btn');
    if (addToPlaylistBtn) addToPlaylistBtn.addEventListener('click', togglePlaylistDropdown);
    
    const createPlaylistBtn = document.getElementById('create-playlist-btn');
    if (createPlaylistBtn) createPlaylistBtn.addEventListener('click', createPlaylistAndAdd);
    
    const exportBtn = document.getElementById('export-btn');
    if (exportBtn) exportBtn.addEventListener('click', openExportModal);
    
    const downloadThumbsBtn = document.getElementById('download-thumbs-btn');
    if (downloadThumbsBtn) downloadThumbsBtn.addEventListener('click', downloadThumbnails);
    
    const batchLocationBtn = document.getElementById('batch-location-btn');
    if (batchLocationBtn) batchLocationBtn.addEventListener('click', openBatchLocationModal);

    // Export modal listeners
    const exportCancel = document.getElementById('export-cancel');
    if (exportCancel) exportCancel.addEventListener('click', closeExportModal);
    
    const exportConfirm = document.getElementById('export-confirm');
    if (exportConfirm) exportConfirm.addEventListener('click', exportVideos);

    // Batch location modal listeners
    const batchLocationCancel = document.getElementById('batch-location-cancel');
    if (batchLocationCancel) batchLocationCancel.addEventListener('click', closeBatchLocationModal);
    
    const batchLocationConfirm = document.getElementById('batch-location-confirm');
    if (batchLocationConfirm) batchLocationConfirm.addEventListener('click', setBatchLocation);
    
    if (elements.batchLocationSearch) elements.batchLocationSearch.addEventListener('input', debounce(searchBatchLocation, 300));

    // Close dropdowns when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.dropdown')) {
            if (elements.playlistDropdown) elements.playlistDropdown.classList.remove('show');
        }
    });

    // Multi-select functions
    function toggleSelection(videoId, cardElement, event) {
        if (event.shiftKey && state.lastSelected !== null) {
            // Shift-click: select range
            const videoCards = Array.from(elements.videoGrid.querySelectorAll('.video-card'));
            const currentIndex = videoCards.findIndex(card => card.dataset.id == videoId);
            const lastIndex = videoCards.findIndex(card => card.dataset.id == state.lastSelected);

            if (currentIndex !== -1 && lastIndex !== -1) {
                const [start, end] = currentIndex < lastIndex ? [currentIndex, lastIndex] : [lastIndex, currentIndex];
                for (let i = start; i <= end; i++) {
                    const id = parseInt(videoCards[i].dataset.id);
                    state.selected.add(id);
                    videoCards[i].classList.add('selected');
                    const checkbox = videoCards[i].querySelector('.select-checkbox');
                    if (checkbox) checkbox.checked = true;
                }
            }
        } else {
            // Normal toggle
            if (state.selected.has(videoId)) {
                state.selected.delete(videoId);
                cardElement.classList.remove('selected');
                const checkbox = cardElement.querySelector('.select-checkbox');
                if (checkbox) checkbox.checked = false;
            } else {
                state.selected.add(videoId);
                cardElement.classList.add('selected');
                const checkbox = cardElement.querySelector('.select-checkbox');
                if (checkbox) checkbox.checked = true;
                state.lastSelected = videoId;
            }
        }

        updateBatchToolbar();
    }

    function clearSelection() {
        state.selected.clear();
        state.lastSelected = null;
        state.isMultiSelectMode = false;

        elements.videoGrid.querySelectorAll('.video-card').forEach(card => {
            card.classList.remove('selected');
            const checkbox = card.querySelector('.select-checkbox');
            if (checkbox) checkbox.checked = false;
        });

        updateBatchToolbar();
    }

    function selectAll() {
        elements.videoGrid.querySelectorAll('.video-card').forEach(card => {
            const id = parseInt(card.dataset.id);
            state.selected.add(id);
            card.classList.add('selected');
            const checkbox = card.querySelector('.select-checkbox');
            if (checkbox) checkbox.checked = true;
        });
        updateBatchToolbar();
    }

    function updateBatchToolbar() {
        const count = state.selected.size;
        if (elements.selectionCount) elements.selectionCount.textContent = count;

        if (elements.batchToolbar) {
            if (count > 0) {
                elements.batchToolbar.classList.add('active');
                elements.selectAllBtn.style.display = 'none';
                elements.deselectAllBtn.style.display = 'inline-block';
                elements.videoGrid.classList.add('multi-select-mode');
            } else {
                elements.batchToolbar.classList.remove('active');
                elements.selectAllBtn.style.display = 'inline-block';
                elements.deselectAllBtn.style.display = 'none';
                elements.videoGrid.classList.remove('multi-select-mode');
            }
        }
    }

    function enableMultiSelectMode() {
        state.isMultiSelectMode = true;
        elements.videoGrid.classList.add('multi-select-mode');
    }

    // Long-press detection for mobile
    function setupLongPress(card) {
        let timer;

        const startLongPress = (e) => {
            if (!state.isMultiSelectMode) {
                timer = setTimeout(() => {
                    e.preventDefault();
                    enableMultiSelectMode();
                    const id = parseInt(card.dataset.id);
                    if (!state.selected.has(id)) {
                        toggleSelection(id, card, { shiftKey: false });
                    }
                    // Vibrate if available
                    if (navigator.vibrate) navigator.vibrate(50);
                }, state.longPressDuration);
            }
        };

        const cancelLongPress = () => {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
        };

        card.addEventListener('touchstart', startLongPress, { passive: true });
        card.addEventListener('touchend', cancelLongPress);
        card.addEventListener('touchmove', cancelLongPress);
        card.addEventListener('touchcancel', cancelLongPress);
    }

    // Playlist functions
    async function loadPlaylists() {
        try {
            const response = await fetch('/api/playlists');
            const data = await response.json();
            renderPlaylistDropdown(data.playlists || []);
        } catch (error) {
            console.error('Error loading playlists:', error);
        }
    }

    function renderPlaylistDropdown(playlists) {
        if (!elements.playlistList) return;
        
        if (playlists.length === 0) {
            elements.playlistList.innerHTML = '<div class="dropdown-empty">No playlists yet</div>';
            return;
        }

        elements.playlistList.innerHTML = playlists.map(p => `
            <div class="dropdown-item" data-playlist-id="${p.id}">
                <span class="playlist-name">${escapeHtml(p.name)}</span>
                <span class="playlist-count">${p.video_count} videos</span>
            </div>
        `).join('');

        // Add click handlers to playlist items
        elements.playlistList.querySelectorAll('.dropdown-item').forEach(item => {
            item.addEventListener('click', () => {
                const playlistId = parseInt(item.dataset.playlistId);
                addToPlaylist(playlistId);
            });
        });
    }

    function togglePlaylistDropdown(e) {
        e.stopPropagation();
        if (elements.playlistDropdown) elements.playlistDropdown.classList.toggle('show');
    }

    async function addToPlaylist(playlistId) {
        if (state.selected.size === 0) return;

        try {
            const response = await fetch('/api/batch/add-to-playlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_ids: Array.from(state.selected),
                    playlist_id: playlistId
                })
            });

            const data = await response.json();
            if (data.success) {
                showToast(`Added ${data.count} videos to playlist`);
                if (elements.playlistDropdown) elements.playlistDropdown.classList.remove('show');
                loadPlaylists(); // Refresh counts
            } else {
                showToast(data.error || 'Failed to add to playlist', 'error');
            }
        } catch (error) {
            console.error('Error adding to playlist:', error);
            showToast('Failed to add to playlist', 'error');
        }
    }

    async function createPlaylistAndAdd() {
        const name = elements.newPlaylistName ? elements.newPlaylistName.value.trim() : '';
        if (!name) {
            showToast('Please enter a playlist name', 'error');
            return;
        }

        if (state.selected.size === 0) {
            showToast('No videos selected', 'error');
            return;
        }

        try {
            const response = await fetch('/api/batch/add-to-playlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_ids: Array.from(state.selected),
                    playlist_name: name
                })
            });

            const data = await response.json();
            if (data.success) {
                showToast(`Created playlist "${name}" with ${data.count} videos`);
                if (elements.newPlaylistName) elements.newPlaylistName.value = '';
                if (elements.playlistDropdown) elements.playlistDropdown.classList.remove('show');
                loadPlaylists();
            } else {
                showToast(data.error || 'Failed to create playlist', 'error');
            }
        } catch (error) {
            console.error('Error creating playlist:', error);
            showToast('Failed to create playlist', 'error');
        }
    }

    // Export functions
    function openExportModal() {
        if (state.selected.size === 0) {
            showToast('No videos selected', 'error');
            return;
        }
        if (elements.exportModal) elements.exportModal.classList.remove('hidden');
    }

    function closeExportModal() {
        if (elements.exportModal) elements.exportModal.classList.add('hidden');
    }

    async function exportVideos() {
        const formatInput = document.querySelector('input[name="export-format"]:checked');
        const format = formatInput ? formatInput.value : 'csv';

        try {
            const response = await fetch('/api/batch/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_ids: Array.from(state.selected),
                    format: format
                })
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = format === 'csv' ? 'broll-export.csv' : 'broll-export.txt';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                closeExportModal();
                showToast(`Exported ${state.selected.size} videos`);
            } else {
                const data = await response.json();
                showToast(data.error || 'Export failed', 'error');
            }
        } catch (error) {
            console.error('Error exporting:', error);
            showToast('Export failed', 'error');
        }
    }

    // Thumbnail download
    async function downloadThumbnails() {
        if (state.selected.size === 0) {
            showToast('No videos selected', 'error');
            return;
        }

        try {
            const response = await fetch('/api/batch/download-thumbnails', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_ids: Array.from(state.selected)
                })
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'broll-thumbnails.zip';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                showToast(`Downloaded thumbnails for ${state.selected.size} videos`);
            } else {
                const data = await response.json();
                showToast(data.error || 'Download failed', 'error');
            }
        } catch (error) {
            console.error('Error downloading thumbnails:', error);
            showToast('Download failed', 'error');
        }
    }

    // Batch location functions
    let selectedLocation = null;

    function openBatchLocationModal() {
        if (state.selected.size === 0) {
            showToast('No videos selected', 'error');
            return;
        }
        selectedLocation = null;
        if (elements.batchLocationSearch) elements.batchLocationSearch.value = '';
        if (elements.batchLocationResults) elements.batchLocationResults.innerHTML = '';
        if (elements.batchLocationConfirm) elements.batchLocationConfirm.disabled = true;
        if (elements.batchLocationModal) {
            elements.batchLocationModal.classList.remove('hidden');
            elements.batchLocationSearch.focus();
        }
    }

    function closeBatchLocationModal() {
        if (elements.batchLocationModal) elements.batchLocationModal.classList.add('hidden');
    }

    async function searchBatchLocation(query) {
        if (!query.trim()) {
            if (elements.batchLocationResults) elements.batchLocationResults.innerHTML = '';
            return;
        }

        try {
            const response = await fetch(`/api/location/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();

            if (elements.batchLocationResults) {
                elements.batchLocationResults.innerHTML = data.map(loc => `
                    <div class="location-result" data-lat="${loc.lat}" data-lon="${loc.lon}" data-name="${escapeHtml(loc.name)}">
                        <div class="location-name">${escapeHtml(loc.name)}</div>
                        <div class="location-type">${loc.type}</div>
                    </div>
                `).join('');

                elements.batchLocationResults.querySelectorAll('.location-result').forEach(item => {
                    item.addEventListener('click', () => {
                        selectedLocation = {
                            lat: parseFloat(item.dataset.lat),
                            lon: parseFloat(item.dataset.lon),
                            name: item.dataset.name
                        };
                        elements.batchLocationResults.querySelectorAll('.location-result').forEach(r => r.classList.remove('selected'));
                        item.classList.add('selected');
                        elements.batchLocationConfirm.disabled = false;
                    });
                });
            }
        } catch (error) {
            console.error('Error searching location:', error);
        }
    }

    async function setBatchLocation() {
        if (!selectedLocation || state.selected.size === 0) return;

        try {
            const response = await fetch('/api/batch/set-location', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_ids: Array.from(state.selected),
                    lat: selectedLocation.lat,
                    lon: selectedLocation.lon,
                    name: selectedLocation.name
                })
            });

            const data = await response.json();
            if (data.success) {
                showToast(`Set location for ${data.count} videos`);
                closeBatchLocationModal();
                // Refresh the page to show updated locations
                loadContent(true);
            } else {
                showToast(data.error || 'Failed to set location', 'error');
            }
        } catch (error) {
            console.error('Error setting location:', error);
            showToast('Failed to set location', 'error');
        }
    }

    // Utility functions
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function showToast(message, type = 'success') {
        // Remove existing toasts
        const existing = document.querySelector('.toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);

        // Trigger animation
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // Content loading
    async function loadContent(reset = false, restoring = false) {
        if (state.loading) return;
        state.loading = true;
        elements.loader.style.display = 'block';

        try {
            // If restoring and we have multiple pages, load them all at once
            const effectiveLimit = (restoring && state.page > 1) ? state.limit * state.page : state.limit;
            const effectivePage = (restoring && state.page > 1) ? 1 : state.page;

            const params = new URLSearchParams({
                path: state.path,
                page: effectivePage,
                limit: effectiveLimit
            });

            const response = await fetch(`/api/browse?${params}`);
            const data = await response.json();

            if (reset) {
                renderBreadcrumbs(data.path);
                renderFolders(data.folders);
                elements.videoGrid.innerHTML = '';
                state.allLoadedVideos = [];
            }

            renderVideos(data.videos);
            data.videos.forEach(v => state.allLoadedVideos.push(v.id));

            if (restoring) {
                // Restore scroll position
                const savedScroll = sessionStorage.getItem(`scroll_${state.path || 'root'}`);
                if (savedScroll) {
                    // Slight delay to ensure layout is done
                    setTimeout(() => {
                        window.scrollTo(0, parseInt(savedScroll));
                        sessionStorage.removeItem(`scroll_${state.path || 'root'}`);
                    }, 0);
                }
            }

            state.hasMore = data.has_more;
            if (!state.hasMore) {
                elements.loader.style.display = 'none';
                observer.unobserve(elements.sentinel);
            } else {
                observer.observe(elements.sentinel);
            }

        } catch (error) {
            console.error('Error loading content:', error);
            elements.videoGrid.innerHTML += '<div class="error">Error loading videos.</div>';
        } finally {
            state.loading = false;
            if (!state.hasMore) elements.loader.style.display = 'none';
        }
    }

    function navigateTo(path) {
        state.path = path;
        state.page = 1;
        state.hasMore = true;
        clearSelection();

        // Update URL
        const url = new URL(window.location);
        if (path) {
            url.searchParams.set('path', path);
        } else {
            url.searchParams.delete('path');
        }
        window.history.pushState({ path, page: 1 }, '', url);

        loadContent(true);
    }

    function renderBreadcrumbs(currentPath) {
        const parts = currentPath ? currentPath.split('/') : [];
        let html = '<span class="crumb"><a href="#" data-path="">Home</a></span>';

        let accumPath = '';
        parts.forEach((part, index) => {
            if (!part) return;
            accumPath += (index > 0 ? '/' : '') + part;
            html += ` <span class="separator">/</span> <span class="crumb"><a href="#" data-path="${accumPath}">${part}</a></span>`;
        });

        elements.breadcrumbs.innerHTML = html;

        // Add click handlers
        elements.breadcrumbs.querySelectorAll('a').forEach(a => {
            a.addEventListener('click', (e) => {
                e.preventDefault();
                navigateTo(e.target.dataset.path);
            });
        });
    }

    function renderFolders(folders) {
        if (!folders || folders.length === 0) {
            elements.folderGrid.style.display = 'none';
            return;
        }

        elements.folderGrid.style.display = 'grid';
        elements.folderGrid.innerHTML = folders.map(folder => `
            <div class="folder-card" data-path="${folder.path}">
                <div class="folder-icon">📁</div>
                <div class="folder-name">${folder.name}</div>
            </div>
        `).join('');

        // Add click handlers
        elements.folderGrid.querySelectorAll('.folder-card').forEach(card => {
            card.addEventListener('click', () => {
                const path = card.dataset.path;
                navigateTo(path);
            });
        });
    }

    function renderVideos(videos) {
        if (!videos || videos.length === 0) {
            if (state.page === 1 && (!state.folders || state.folders.length === 0)) {
                if (elements.videoGrid.children.length === 0) {
                    elements.videoGrid.innerHTML = '<div class="empty-state">No videos in this folder.</div>';
                }
            }
            return;
        }

        // Remove empty state if present
        const emptyState = elements.videoGrid.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        const html = videos.map(video => {
            const isSelected = state.selected.has(video.id);
            return `
            <div class="video-card ${isSelected ? 'selected' : ''}" 
                 data-id="${video.id}" data-path="${video.file_path}">
                <div class="select-checkbox-wrapper">
                    <input type="checkbox" class="select-checkbox" 
                           ${isSelected ? 'checked' : ''} 
                           data-id="${video.id}"
                           onclick="event.stopPropagation()">
                </div>
                <a href="/video/${video.id}" class="card-link">
                    <div class="card-thumb">
                        ${video.thumbnail_path
                    ? `<img src="/thumbnail/${video.file_hash}" alt="${video.file_name}" loading="lazy">`
                    : '<div class="no-thumb">No Preview</div>'}
                        ${video.duration_seconds
                    ? `<span class="card-duration">${formatDuration(video.duration_seconds)}</span>`
                    : ''}
                        ${video.source_device
                    ? `<span class="card-device">${video.source_device}</span>`
                    : ''}
                        <button class="add-to-playlist-btn" data-video-id="${video.id}" data-video-name="${escapeHtml(video.file_name)}" title="Add to playlist">+</button>
                    </div>
                    <div class="card-info">
                        <div class="card-filename">${video.file_name}</div>
                        ${video.scene_description && !video.scene_description.startsWith("ERROR")
                    ? `<div class="card-desc">${video.scene_description.substring(0, 100)}</div>`
                    : ''}
                        ${renderTags(video.tags)}
                        <div class="card-meta">
                            ${video.resolution || ''}
                            ${video.gps_location_name ? ` | ${video.gps_location_name}` : ''}
                        </div>
                    </div>
                </a>
            </div>
        `}).join('');

        elements.videoGrid.insertAdjacentHTML('beforeend', html);

        // Update video cards array for keyboard navigation
        state.videoCards = Array.from(elements.videoGrid.querySelectorAll('.video-card'));

        // Add event handlers to new cards
        elements.videoGrid.querySelectorAll('.video-card').forEach((card, index) => {
            const id = parseInt(card.dataset.id);
            const checkbox = card.querySelector('.select-checkbox');

            // Checkbox click
            checkbox.addEventListener('change', (e) => {
                toggleSelection(id, card, e);
            });

            // Card click (prevent navigation when in multi-select mode)
            card.addEventListener('click', (e) => {
                // If clicking the checkbox itself, let it handle it
                if (e.target.classList.contains('select-checkbox')) return;

                // If in multi-select mode or clicking on a selected card, toggle selection
                if (state.isMultiSelectMode || state.selected.has(id) || e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    toggleSelection(id, card, e);
                }
            });

            // Keyboard navigation focus tracking
            card.addEventListener('focus', () => {
                state.focusedCardIndex = index;
                card.classList.add('keyboard-focused');
            });
            card.addEventListener('blur', () => {
                card.classList.remove('keyboard-focused');
            });

            // Make card focusable
            card.setAttribute('tabindex', '0');

            // Hover preview
            setupHoverPreview(card, video);

            // Setup long-press for mobile
            setupLongPress(card);
        });
    }

    // Hover preview functionality
    function setupHoverPreview(card, video) {
        const thumbContainer = card.querySelector('.card-thumb');
        if (!thumbContainer || !video.file_hash) return;

        let previewVideo = null;

        card.addEventListener('mouseenter', () => {
            // Delay start by 300ms to prevent accidental triggers
            state.hoverPreviewTimeout = setTimeout(() => {
                startPreview(thumbContainer, video);
            }, 300);
        });

        card.addEventListener('mouseleave', () => {
            clearTimeout(state.hoverPreviewTimeout);
            stopPreview(thumbContainer);
        });

        // Also handle touch for mobile
        card.addEventListener('touchstart', () => {
            state.hoverPreviewTimeout = setTimeout(() => {
                startPreview(thumbContainer, video);
            }, 500);
        }, { passive: true });

        card.addEventListener('touchend', () => {
            clearTimeout(state.hoverPreviewTimeout);
            stopPreview(thumbContainer);
        });
    }

    function startPreview(container, video) {
        // Don't start if already playing a preview
        if (container.querySelector('.hover-preview-video')) return;

        const img = container.querySelector('img');
        if (!img) return;

        const videoEl = document.createElement('video');
        videoEl.className = 'hover-preview-video';
        videoEl.src = `/video/stream/${video.id}`;
        videoEl.muted = true;
        videoEl.playsInline = true;
        videoEl.loop = false;
        videoEl.style.cssText = `
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            z-index: 5;
        `;

        // Hide the image
        img.style.opacity = '0';

        container.appendChild(videoEl);
        state.currentPreviewVideo = videoEl;

        videoEl.play().catch(() => {
            // Autoplay blocked or failed, restore image
            stopPreview(container);
        });

        // Stop after 3 seconds
        setTimeout(() => {
            if (videoEl.parentElement) {
                stopPreview(container);
            }
        }, 3000);
    }

    function stopPreview(container) {
        const videoEl = container.querySelector('.hover-preview-video');
        if (videoEl) {
            videoEl.pause();
            videoEl.remove();
        }
        const img = container.querySelector('img');
        if (img) {
            img.style.opacity = '1';
        }
        state.currentPreviewVideo = null;
    }

    // Helpers
    function formatDuration(seconds) {
        if (!seconds) return "--:--";
        const total = Math.floor(seconds);
        const mins = Math.floor(total / 60);
        const secs = total % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    function renderTags(tags) {
        if (!tags) return '';
        let parsed = [];
        try {
            parsed = typeof tags === 'string' ? JSON.parse(tags) : tags;
        } catch (e) {
            parsed = [tags];
        }
        if (!Array.isArray(parsed)) return '';

        return `<div class="card-tags">
            ${parsed.slice(0, 4).map(tag => `<span class="tag">${tag}</span>`).join('')}
        </div>`;
    }

    // Keyboard shortcuts
    function initKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Don't trigger shortcuts when typing in inputs
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                // Allow Escape to close modals even in inputs
                if (e.key === 'Escape') {
                    if (!elements.batchLocationModal.classList.contains('hidden')) {
                        closeBatchLocationModal();
                        e.preventDefault();
                    } else if (!elements.exportModal.classList.contains('hidden')) {
                        closeExportModal();
                        e.preventDefault();
                    }
                }
                return;
            }

            switch (e.key) {
                case '/':
                    e.preventDefault();
                    focusSearch();
                    break;
                case 'j':
                case 'J':
                    e.preventDefault();
                    navigateCards(1);
                    break;
                case 'k':
                case 'K':
                    e.preventDefault();
                    navigateCards(-1);
                    break;
                case 'f':
                case 'F':
                    e.preventDefault();
                    toggleFavoriteFocused();
                    break;
                case ' ': // Space
                    e.preventDefault();
                    togglePlayFocused();
                    break;
                case '?':
                    e.preventDefault();
                    showKeyboardHelp();
                    break;
                case 'Escape':
                    if (!elements.batchLocationModal.classList.contains('hidden')) {
                        closeBatchLocationModal();
                    } else if (!elements.exportModal.classList.contains('hidden')) {
                        closeExportModal();
                    } else {
                        hideKeyboardHelp();
                        clearSelection();
                    }
                    break;
            }
        });
    }

    function focusSearch() {
        const searchInput = document.querySelector('input[name="q"]');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }

    function navigateCards(direction) {
        const cards = state.videoCards;
        if (cards.length === 0) return;

        // Update focused index
        state.focusedCardIndex += direction;

        // Clamp to valid range
        if (state.focusedCardIndex < 0) {
            state.focusedCardIndex = 0;
        } else if (state.focusedCardIndex >= cards.length) {
            state.focusedCardIndex = cards.length - 1;
        }

        // Focus the card
        const card = cards[state.focusedCardIndex];
        if (card) {
            card.focus();
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    function toggleFavoriteFocused() {
        const card = state.videoCards[state.focusedCardIndex];
        if (!card) return;

        const id = parseInt(card.dataset.id);
        const checkbox = card.querySelector('.select-checkbox');

        // Trigger the checkbox change
        if (checkbox) {
            checkbox.checked = !checkbox.checked;
            toggleSelection(id, card, { shiftKey: false });
        }
    }

    function togglePlayFocused() {
        // If there's a current preview video, pause/play it
        if (state.currentPreviewVideo) {
            if (state.currentPreviewVideo.paused) {
                state.currentPreviewVideo.play();
            } else {
                state.currentPreviewVideo.pause();
            }
            return;
        }

        // Otherwise, try to play the focused card's preview
        const card = state.videoCards[state.focusedCardIndex];
        if (!card) return;

        const thumbContainer = card.querySelector('.card-thumb');
        const videoId = card.dataset.id;
        const videoData = { id: videoId, file_hash: card.dataset.path };

        if (thumbContainer) {
            startPreview(thumbContainer, videoData);
        }
    }

    // Keyboard help modal
    function createKeyboardHelpModal() {
        const modal = document.createElement('div');
        modal.id = 'keyboard-help-modal';
        modal.className = 'modal hidden';
        modal.innerHTML = `
            <div class="modal-content keyboard-help-content">
                <h3>Keyboard Shortcuts</h3>
                <div class="keyboard-shortcuts-list">
                    <div class="shortcut-item">
                        <kbd>/</kbd>
                        <span>Focus search</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>j</kbd> / <kbd>k</kbd>
                        <span>Navigate videos</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>f</kbd>
                        <span>Toggle favorite/select</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>Space</kbd>
                        <span>Play/pause preview</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>?</kbd>
                        <span>Show this help</span>
                    </div>
                    <div class="shortcut-item">
                        <kbd>Esc</kbd>
                        <span>Close / Clear selection</span>
                    </div>
                </div>
                <div class="modal-actions">
                    <button class="btn-primary" onclick="document.getElementById('keyboard-help-modal').classList.add('hidden')">Got it</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Add keyboard hint
        const hint = document.createElement('div');
        hint.className = 'keyboard-hint';
        hint.innerHTML = 'Press <kbd>?</kbd> for keyboard shortcuts';
        document.body.appendChild(hint);
    }

    function showKeyboardHelp() {
        const modal = document.getElementById('keyboard-help-modal');
        if (modal) {
            modal.classList.remove('hidden');
        }
    }

    function hideKeyboardHelp() {
        const modal = document.getElementById('keyboard-help-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
    }
});
