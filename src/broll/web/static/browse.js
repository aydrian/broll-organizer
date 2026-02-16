document.addEventListener('DOMContentLoaded', () => {
    const state = {
        path: new URLSearchParams(window.location.search).get('path') || '',
        page: 1,
        loading: false,
        hasMore: true,
        limit: 24
    };

    const elements = {
        breadcrumbs: document.getElementById('breadcrumbs'),
        folderGrid: document.getElementById('folder-grid'),
        videoGrid: document.getElementById('video-grid'),
        loader: document.getElementById('loader'),
        sentinel: document.getElementById('sentinel')
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
            <div class="folder-card" data-subfolder="${folder}">
                <div class="folder-icon">📁</div>
                <div class="folder-name">${folder}</div>
            </div>
        `).join('');

        // Add click handlers
        elements.folderGrid.querySelectorAll('.folder-card').forEach(card => {
            card.addEventListener('click', () => {
                const sub = card.dataset.subfolder;
                const newPath = state.path ? `${state.path}/${sub}` : sub;
                navigateTo(newPath);
            });
        });
    }

    function renderVideos(videos) {
        if (!videos || videos.length === 0) {
            if (state.page === 1 && (!state.folders || state.folders.length === 0)) {
                // Only show "No videos" if there are also no folders, or maybe just if no videos
                // For now, let's just append nothing.
                if (elements.videoGrid.children.length === 0) {
                    elements.videoGrid.innerHTML = '<div class="empty-state">No videos in this folder.</div>';
                }
            }
            return;
        }

        // Remove empty state if present
        const emptyState = elements.videoGrid.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        const html = videos.map(video => `
            <a href="/video/${video.id}" class="video-card">
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
        `).join('');

        elements.videoGrid.insertAdjacentHTML('beforeend', html);
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
});
