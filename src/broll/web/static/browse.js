document.addEventListener('DOMContentLoaded', () => {
    const state = {
        path: new URLSearchParams(window.location.search).get('path') || '',
        page: 1,
        loading: false,
        hasMore: true,
        limit: 24,
        multiSelect: false,
        selectedItems: new Set(),
        touchStartY: 0,
        pullToRefreshEnabled: true
    };

    const elements = {
        breadcrumbs: document.getElementById('breadcrumbs'),
        folderGrid: document.getElementById('folder-grid'),
        videoGrid: document.getElementById('video-grid'),
        loader: document.getElementById('loader'),
        sentinel: document.getElementById('sentinel'),
        main: document.querySelector('main')
    };

    // Initial load
    loadContent(true);

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

    // Pull to refresh for mobile
    setupPullToRefresh();
    
    // Long press for multi-select on mobile
    setupLongPress();
    
    // Keyboard navigation
    setupKeyboardNavigation();

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
            }

            renderVideos(data.videos);

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
                observer.unobserve(elements.sentinel); // Stop observing if no more
            } else {
                observer.observe(elements.sentinel); // Re-observe if needed
            }

        } catch (error) {
            console.error('Error loading content:', error);
            elements.videoGrid.innerHTML += '<div class="error" role="alert">Error loading videos.</div>';
        } finally {
            state.loading = false;
            if (!state.hasMore) elements.loader.style.display = 'none';
        }
    }

    function navigateTo(path) {
        state.path = path;
        state.page = 1;
        state.hasMore = true;

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
                state.multiSelect = false;
                state.selectedItems.clear();
                document.querySelectorAll('.folder-card.selected, .video-card.selected').forEach(card => {
                    card.classList.remove('selected');
                    card.setAttribute('aria-selected', 'false');
                });
                updateMultiSelectToolbar();
            }
        });
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
