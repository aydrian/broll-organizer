// Connection state management
const ConnectionManager = {
    state: {
        isOnline: true,
        lastState: null,
        pollInterval: 5000,  // Start at 5 seconds
        maxInterval: 60000,  // Max 60 seconds
        pollTimer: null,
        reconnecting: false,
        cachedData: null
    },

    init() {
        // Load cached data from sessionStorage
        this.loadCachedState();
        
        // Start polling
        this.startPolling();
        
        // Listen for online/offline events
        window.addEventListener('online', () => this.handleNetworkChange(true));
        window.addEventListener('offline', () => this.handleNetworkChange(false));
        
        // Handle visibility change (resume polling when tab becomes visible)
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                this.checkConnection();
            }
        });
    },

    loadCachedState() {
        try {
            const cached = sessionStorage.getItem('broll_cached_browse_state');
            if (cached) {
                this.state.cachedData = JSON.parse(cached);
                console.log('[ConnectionManager] Loaded cached browse state');
            }
        } catch (e) {
            console.error('[ConnectionManager] Failed to load cached state:', e);
        }
    },

    saveCachedState(data) {
        try {
            sessionStorage.setItem('broll_cached_browse_state', JSON.stringify({
                timestamp: Date.now(),
                data: data
            }));
        } catch (e) {
            console.error('[ConnectionManager] Failed to save cached state:', e);
        }
    },

    clearCachedState() {
        try {
            sessionStorage.removeItem('broll_cached_browse_state');
            this.state.cachedData = null;
        } catch (e) {
            console.error('[ConnectionManager] Failed to clear cached state:', e);
        }
    },

    async checkConnection() {
        try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 5000);
            
            const response = await fetch('/api/health', {
                method: 'GET',
                signal: controller.signal,
                cache: 'no-store'
            });
            
            clearTimeout(timeout);
            
            const wasOffline = !this.state.isOnline;
            this.state.isOnline = response.ok;
            
            if (wasOffline && this.state.isOnline) {
                // Just reconnected!
                this.handleReconnect();
            } else if (!this.state.isOnline && !wasOffline) {
                // Just went offline
                this.handleDisconnect();
            }
            
            // Reset interval on successful connection
            if (this.state.isOnline) {
                this.state.pollInterval = 5000;
            }
            
            this.updateStatusIndicator();
            return this.state.isOnline;
            
        } catch (error) {
            const wasOffline = !this.state.isOnline;
            this.state.isOnline = false;
            
            if (!wasOffline) {
                this.handleDisconnect();
            }
            
            this.updateStatusIndicator();
            return false;
        }
    },

    startPolling() {
        // Clear any existing timer
        if (this.state.pollTimer) {
            clearTimeout(this.state.pollTimer);
        }
        
        const poll = async () => {
            await this.checkConnection();
            
            // Exponential backoff: double the interval up to max
            if (!this.state.isOnline) {
                this.state.pollInterval = Math.min(
                    this.state.pollInterval * 2,
                    this.state.maxInterval
                );
            }
            
            this.state.pollTimer = setTimeout(poll, this.state.pollInterval);
        };
        
        // Initial check
        this.checkConnection();
        
        // Start the polling loop
        this.state.pollTimer = setTimeout(poll, this.state.pollInterval);
    },

    stopPolling() {
        if (this.state.pollTimer) {
            clearTimeout(this.state.pollTimer);
            this.state.pollTimer = null;
        }
    },

    handleDisconnect() {
        console.log('[ConnectionManager] Drive disconnected');
        this.showOfflineBanner();
        this.disableMutations();
        
        // Dispatch custom event
        window.dispatchEvent(new CustomEvent('drive:disconnected'));
    },

    handleReconnect() {
        console.log('[ConnectionManager] Drive reconnected!');
        this.state.reconnecting = true;
        
        // Show toast notification
        this.showReconnectToast();
        
        // Clear cached state since we're back online
        this.clearCachedState();
        
        // Dispatch custom event
        window.dispatchEvent(new CustomEvent('drive:reconnected'));
        
        // Reload the page after a short delay to refresh with live data
        setTimeout(() => {
            window.location.reload();
        }, 2000);
    },

    handleNetworkChange(isOnline) {
        // Browser online/offline events - trigger a check
        if (isOnline) {
            this.checkConnection();
        }
    },

    showOfflineBanner() {
        // Remove any existing banner first
        const existing = document.getElementById('offline-banner');
        if (existing) existing.remove();
        
        const banner = document.createElement('div');
        banner.id = 'offline-banner';
        banner.className = 'offline-banner';
        banner.innerHTML = `
            <div class="offline-content">
                <span class="offline-icon">⚠️</span>
                <span class="offline-text">Drive disconnected</span>
                <button class="retry-btn" onclick="ConnectionManager.retryNow()">Retry Now</button>
                <button class="cached-btn" onclick="ConnectionManager.showCachedView()">View Cached</button>
            </div>
        `;
        
        document.body.insertBefore(banner, document.body.firstChild);
        
        // Adjust main content to account for banner
        const main = document.querySelector('main');
        if (main) {
            main.style.marginTop = '40px';
        }
    },

    hideOfflineBanner() {
        const banner = document.getElementById('offline-banner');
        if (banner) {
            banner.remove();
        }
        
        const main = document.querySelector('main');
        if (main) {
            main.style.marginTop = '';
        }
    },

    showReconnectToast() {
        // Remove any existing toast
        const existing = document.getElementById('reconnect-toast');
        if (existing) existing.remove();
        
        const toast = document.createElement('div');
        toast.id = 'reconnect-toast';
        toast.className = 'toast toast-success';
        toast.innerHTML = `
            <span class="toast-icon">✅</span>
            <span class="toast-message">Drive connected! Reloading...</span>
        `;
        
        document.body.appendChild(toast);
        
        // Animate in
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    },

    retryNow() {
        // Manual retry - reset interval and check immediately
        this.state.pollInterval = 5000;
        
        const btn = document.querySelector('.retry-btn');
        if (btn) {
            btn.textContent = 'Checking...';
            btn.disabled = true;
        }
        
        this.checkConnection().then(isOnline => {
            if (!isOnline) {
                // Still offline - update button
                if (btn) {
                    btn.textContent = 'Retry Now';
                    btn.disabled = false;
                }
            }
        });
    },

    showCachedView() {
        if (!this.state.cachedData) {
            // Show message if no cached data
            const toast = document.createElement('div');
            toast.className = 'toast toast-info';
            toast.innerHTML = `
                <span class="toast-icon">ℹ️</span>
                <span class="toast-message">No cached view available</span>
            `;
            document.body.appendChild(toast);
            requestAnimationFrame(() => toast.classList.add('show'));
            setTimeout(() => toast.remove(), 3000);
            return;
        }
        
        // Dispatch event for browse.js to handle
        window.dispatchEvent(new CustomEvent('drive:showCached', {
            detail: this.state.cachedData
        }));
    },

    disableMutations() {
        // Hide edit buttons and disable interactive elements
        document.body.classList.add('offline-mode');
        
        // Disable all forms
        document.querySelectorAll('form').forEach(form => {
            form.dataset.wasDisabled = form.disabled || 'false';
            form.disabled = true;
        });
        
        // Disable all buttons with class 'edit-btn' or inside edit containers
        document.querySelectorAll('.edit-btn, .action-btn, [data-mutation]').forEach(btn => {
            btn.dataset.wasDisabled = btn.disabled || 'false';
            btn.disabled = true;
        });
    },

    enableMutations() {
        document.body.classList.remove('offline-mode');
        
        // Re-enable forms
        document.querySelectorAll('form').forEach(form => {
            if (form.dataset.wasDisabled === 'false') {
                form.disabled = false;
            }
        });
        
        // Re-enable buttons
        document.querySelectorAll('.edit-btn, .action-btn, [data-mutation]').forEach(btn => {
            if (btn.dataset.wasDisabled === 'false') {
                btn.disabled = false;
            }
        });
    },

    updateStatusIndicator() {
        const indicator = document.getElementById('connection-status');
        if (indicator) {
            if (this.state.isOnline) {
                indicator.className = 'connection-status online';
                indicator.innerHTML = '[● Online]';
                indicator.title = 'Drive connected';
            } else {
                indicator.className = 'connection-status offline';
                indicator.innerHTML = '[○ Offline]';
                indicator.title = 'Drive disconnected - working offline';
            }
        }
    }
};

// Initialize connection manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    ConnectionManager.init();
});

// Original browse.js content
document.addEventListener('DOMContentLoaded', () => {
    const state = {
        path: new URLSearchParams(window.location.search).get('path') || '',
        page: 1,
        loading: false,
        hasMore: true,
        limit: 24,
        offlineMode: false

    };

    const elements = {
        breadcrumbs: document.getElementById('breadcrumbs'),
        folderGrid: document.getElementById('folder-grid'),
        videoGrid: document.getElementById('video-grid'),
        loader: document.getElementById('loader'),
        sentinel: document.getElementById('sentinel'),
        main: document.querySelector('main'),
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

    // Listen for connection events
    window.addEventListener('drive:disconnected', () => {
        state.offlineMode = true;
        // Save current state before we potentially lose it
        const currentData = {
            path: state.path,
            folders: state.folders || [],
            videos: Array.from(elements.videoGrid.querySelectorAll('.video-card')).map(card => ({
                id: card.href?.match(/\/video\/(\d+)/)?.[1],
                file_name: card.querySelector('.card-filename')?.textContent,
                file_hash: card.querySelector('img')?.src?.match(/\/thumbnail\/(\w+)/)?.[1],
                duration_seconds: card.querySelector('.card-duration')?.textContent,
                scene_description: card.querySelector('.card-desc')?.textContent,
                tags: card.querySelector('.card-tags')?.textContent,
                source_device: card.querySelector('.card-device')?.textContent,
                gps_location_name: card.querySelector('.card-meta')?.textContent?.split(' | ')[1]
            })).filter(v => v.id)
        };
        ConnectionManager.saveCachedState(currentData);
    });

    window.addEventListener('drive:reconnected', () => {
        state.offlineMode = false;
    });

    window.addEventListener('drive:showCached', (e) => {
        const cached = e.detail;
        if (cached && cached.data) {
            renderCachedView(cached.data);
        }
    });

    function renderCachedView(data) {
        // Show a banner indicating we're viewing cached data
        const cachedBanner = document.createElement('div');
        cachedBanner.className = 'cached-banner';
        cachedBanner.innerHTML = `
            <span class="cached-icon">💾</span>
            <span class="cached-text">Viewing cached data from ${new Date(data.timestamp).toLocaleString()}</span>
            <button class="cached-close" onclick="this.parentElement.remove()">×</button>
        `;
        
        const main = document.querySelector('main');
        if (main && !document.querySelector('.cached-banner')) {
            main.insertBefore(cachedBanner, main.firstChild);
        }
        
        // Render the cached content
        if (data.data) {
            state.path = data.data.path || '';
            renderBreadcrumbs(state.path);
            renderFolders(data.data.folders || []);
            
            elements.videoGrid.innerHTML = '';
            if (data.data.videos && data.data.videos.length > 0) {
                renderVideos(data.data.videos);
            }
        }
    }

    // Initial load
    loadContent(true);
    loadPlaylists();
    initKeyboardShortcuts();
    createKeyboardHelpModal();

    // Infinite scroll
    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !state.loading && state.hasMore && !state.offlineMode) {
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

    // Pull to refresh for mobile
    setupPullToRefresh();
    
    // Long press for multi-select on mobile
    setupLongPress();
    
    // Keyboard navigation
    setupKeyboardNavigation();


    async function loadContent(reset = false, restoring = false) {
        if (state.loading || state.offlineMode) return;
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
            
            // If we get a 503, we're offline
            if (response.status === 503) {
                ConnectionManager.handleDisconnect();
                state.offlineMode = true;
                return;
            }
            
            const data = await response.json();

            if (reset) {
                renderBreadcrumbs(data.path);
                renderFolders(data.folders);
                elements.videoGrid.innerHTML = '';
                state.folders = data.folders;

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
            if (!state.offlineMode) {
                elements.videoGrid.innerHTML += '<div class="error">Error loading videos. Drive may be disconnected.</div>';
            }

        } finally {
            state.loading = false;
            if (!state.hasMore) elements.loader.style.display = 'none';
        }
    }

    function navigateTo(path) {
        if (state.offlineMode) {
            // In offline mode, only allow navigation to cached folders
            alert('Cannot browse while drive is disconnected. Please reconnect the drive.');
            return;
        }
        
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
        let html = '<span class="crumb"><a href="#" data-path="" aria-label="Go to Home">Home</a></span>';

        let accumPath = '';
        parts.forEach((part, index) => {
            if (!part) return;
            accumPath += (index > 0 ? '/' : '') + part;
            html += ` <span class="separator" aria-hidden="true">/</span> <span class="crumb"><a href="#" data-path="${accumPath}" aria-label="Go to ${part}">${part}</a></span>`;
        });

        elements.breadcrumbs.innerHTML = html;
        elements.breadcrumbs.setAttribute('aria-label', 'Breadcrumb navigation');

        // Add click handlers
        elements.breadcrumbs.querySelectorAll('a').forEach(a => {
            a.addEventListener('click', (e) => {
                e.preventDefault();
                navigateTo(e.target.dataset.path);
            });
            
            // Keyboard navigation support
            a.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigateTo(e.target.dataset.path);
                }
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
            <div class="folder-card" 
                 data-path="${folder.path}" 
                 role="button"
                 tabindex="0"
                 aria-label="Open folder: ${folder.name}"
                 data-type="folder">
                <div class="folder-icon" aria-hidden="true">📁</div>
                <div class="folder-name">${folder.name}</div>
            </div>
        `).join('');

        // Add click handlers
        elements.folderGrid.querySelectorAll('.folder-card').forEach(card => {
            card.addEventListener('click', () => handleCardClick(card));
            
            // Keyboard navigation
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleCardClick(card);
                }
            });
        });
    }

    function renderVideos(videos) {
        if (!videos || videos.length === 0) {
            if (state.page === 1 && (!state.folders || state.folders.length === 0)) {
                if (elements.videoGrid.children.length === 0) {
                    elements.videoGrid.innerHTML = '<div class="empty-state" role="status">No videos in this folder.</div>';
                }
            }
            return;
        }

        // Remove empty state if present
        const emptyState = elements.videoGrid.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        const html = videos.map(video => {
            const desc = video.scene_description && !video.scene_description.startsWith("ERROR") 
                ? video.scene_description.substring(0, 100) 
                : '';
            const ariaLabel = `${video.file_name}${desc ? ': ' + desc : ''}${video.duration_seconds ? ', Duration: ' + formatDuration(video.duration_seconds) : ''}${video.gps_location_name ? ', Location: ' + video.gps_location_name : ''}`;
            
            return `
            <a href="/video/${video.id}" 
               class="video-card" 
               role="article"
               tabindex="0"
               aria-label="${escapeHtml(ariaLabel)}"
               data-id="${video.id}"
               data-type="video">
                <div class="card-thumb">
                    ${video.thumbnail_path
                ? `<img src="/thumbnail/${video.file_hash}" alt="${escapeHtml(desc || 'Video thumbnail')}" loading="lazy">`
                : '<div class="no-thumb" role="img" aria-label="No preview available">No Preview</div>'}
                    ${video.duration_seconds
                ? `<span class="card-duration" aria-label="Duration: ${formatDuration(video.duration_seconds)}">${formatDuration(video.duration_seconds)}</span>`
                : ''}
                    ${video.source_device
                ? `<span class="card-device" aria-label="Recorded on: ${video.source_device}">${video.source_device}</span>`
                : ''}
                </div>
                <div class="card-info">
                    <div class="card-filename">${video.file_name}</div>
                    ${desc ? `<div class="card-desc">${desc}</div>` : ''}
                    ${renderTags(video.tags)}
                    <div class="card-meta">
                        ${video.resolution || ''}
                        ${video.gps_location_name ? ` | ${video.gps_location_name}` : ''}
                    </div>
                </div>
            </a>
        `}).join('');

        elements.videoGrid.insertAdjacentHTML('beforeend', html);
        
        // Add keyboard navigation to new video cards
        elements.videoGrid.querySelectorAll('.video-card:not([data-keyboard-ready])').forEach(card => {
            card.dataset.keyboardReady = 'true';
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    if (state.multiSelect) {
                        toggleSelection(card);
                    } else {
                        window.location.href = card.href;
                    }
                }
            });
            
            // Long press handler for multi-select
            if ('ontouchstart' in window) {
                setupCardLongPress(card);
            }
        });
    }

    function handleCardClick(card) {
        if (state.multiSelect) {
            toggleSelection(card);
        } else {
            const path = card.dataset.path;
            navigateTo(path);
        }
    }

    function toggleSelection(card) {
        const id = card.dataset.path || card.dataset.id;
        if (state.selectedItems.has(id)) {
            state.selectedItems.delete(id);
            card.classList.remove('selected');
            card.setAttribute('aria-selected', 'false');
        } else {
            state.selectedItems.add(id);
            card.classList.add('selected');
            card.setAttribute('aria-selected', 'true');
        }
        updateMultiSelectToolbar();
    }

    function updateMultiSelectToolbar() {
        const toolbar = document.querySelector('.multi-select-toolbar');
        if (!toolbar) return;
        
        const count = state.selectedItems.size;
        if (count === 0 && state.multiSelect) {
            toolbar.classList.remove('active');
            state.multiSelect = false;
        } else if (count > 0) {
            toolbar.classList.add('active');
            toolbar.querySelector('.multi-select-count').textContent = `${count} selected`;
        }
    }

    function setupPullToRefresh() {
        if (!('ontouchstart' in window)) return;
        
        let startY = 0;
        let currentY = 0;
        let isPulling = false;
        
        // Add pull indicator
        const ptr = document.createElement('div');
        ptr.className = 'ptr-indicator';
        ptr.innerHTML = '<div class="ptr-spinner"></div>';
        ptr.setAttribute('aria-hidden', 'true');
        elements.main.insertBefore(ptr, elements.main.firstChild);
        
        document.addEventListener('touchstart', (e) => {
            if (window.scrollY === 0 && state.pullToRefreshEnabled) {
                startY = e.touches[0].clientY;
                isPulling = true;
            }
        }, { passive: true });
        
        document.addEventListener('touchmove', (e) => {
            if (!isPulling) return;
            
            currentY = e.touches[0].clientY;
            const diff = currentY - startY;
            
            if (diff > 0 && window.scrollY === 0) {
                if (diff > 50) {
                    ptr.classList.add('visible');
                }
                if (diff > 150) {
                    ptr.classList.add('spinning');
                }
            }
        }, { passive: true });
        
        document.addEventListener('touchend', () => {
            if (!isPulling) return;
            
            const diff = currentY - startY;
            if (diff > 150 && window.scrollY === 0) {
                // Trigger refresh
                ptr.classList.add('spinning');
                loadContent(true).then(() => {
                    ptr.classList.remove('visible', 'spinning');
                });
            } else {
                ptr.classList.remove('visible', 'spinning');
            }
            
            isPulling = false;
            startY = 0;
            currentY = 0;
        });
    }

    function setupLongPress() {
        if (!('ontouchstart' in window)) return;
        
        let longPressTimer;
        const longPressDuration = 500;
        
        elements.folderGrid.addEventListener('touchstart', (e) => {
            const card = e.target.closest('.folder-card');
            if (card) {
                longPressTimer = setTimeout(() => {
                    if (!state.multiSelect) {
                        state.multiSelect = true;
                        toggleSelection(card);
                    }
                }, longPressDuration);
            }
        }, { passive: true });
        
        elements.folderGrid.addEventListener('touchend', () => {
            clearTimeout(longPressTimer);
        });
        
        elements.folderGrid.addEventListener('touchmove', () => {
            clearTimeout(longPressTimer);
        });
    }

    function setupCardLongPress(card) {
        let longPressTimer;
        const longPressDuration = 500;
        
        card.addEventListener('touchstart', (e) => {
            longPressTimer = setTimeout(() => {
                if (!state.multiSelect) {
                    state.multiSelect = true;
                    toggleSelection(card);
                    // Vibrate if supported
                    if (navigator.vibrate) {
                        navigator.vibrate(50);
                    }
                }
            }, longPressDuration);
        }, { passive: true });
        
        card.addEventListener('touchend', () => {
            clearTimeout(longPressTimer);
        });
        
        card.addEventListener('touchmove', () => {
            clearTimeout(longPressTimer);
        });
    }

    function setupKeyboardNavigation() {
        // Global keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Escape to exit multi-select mode
            if (e.key === 'Escape' && state.multiSelect) {
                exitMultiSelectMode();
            }
        });
        
        // Multi-select toolbar button handlers
        const cancelBtn = document.getElementById('cancel-selection');
        const addToPlaylistBtn = document.getElementById('add-to-playlist');
        
        if (cancelBtn) {
            cancelBtn.addEventListener('click', exitMultiSelectMode);
        }
        
        if (addToPlaylistBtn) {
            addToPlaylistBtn.addEventListener('click', addSelectedToPlaylist);
        }
    }
    
    function exitMultiSelectMode() {
        state.multiSelect = false;
        state.selectedItems.clear();
        document.querySelectorAll('.folder-card.selected, .video-card.selected').forEach(card => {
            card.classList.remove('selected');
            card.setAttribute('aria-selected', 'false');
        });
        updateMultiSelectToolbar();
    }
    
    function addSelectedToPlaylist() {
        const selectedIds = Array.from(state.selectedItems);
        if (selectedIds.length === 0) return;
        
        // Dispatch custom event for playlist handling
        const event = new CustomEvent('addToPlaylist', {
            detail: { ids: selectedIds }
        });
        document.dispatchEvent(event);
        
        // Show feedback to user
        showNotification(`${selectedIds.length} items ready to add to playlist`);
        exitMultiSelectMode();
    }
    
    function showNotification(message) {
        const existing = document.querySelector('.notification-toast');
        if (existing) existing.remove();
        
        const toast = document.createElement('div');
        toast.className = 'notification-toast';
        toast.setAttribute('role', 'status');
        toast.setAttribute('aria-live', 'polite');
        toast.textContent = message;
        
        Object.assign(toast.style, {
            position: 'fixed',
            bottom: '160px',
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'var(--accent)',
            color: 'white',
            padding: '0.75rem 1.5rem',
            borderRadius: 'var(--radius)',
            zIndex: '1000',
            fontWeight: '500'
        });
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }, 2000);

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

        return `<div class="card-tags" role="list" aria-label="Tags">
            ${parsed.slice(0, 4).map(tag => `<span class="tag" role="listitem">${escapeHtml(tag)}</span>`).join('')}
        </div>`;
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;

    }
});
