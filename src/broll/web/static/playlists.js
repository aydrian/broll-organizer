/**
 * Playlist management functionality for broll-organizer
 * Handles playlists list, detail view, drag-and-drop reordering, and exports
 */

document.addEventListener('DOMContentLoaded', () => {
    // Determine which page we're on
    const playlistsGrid = document.getElementById('playlists-grid');
    const playlistVideos = document.getElementById('playlist-videos');
    
    if (playlistsGrid) {
        initPlaylistsList();
    }
    if (playlistVideos && window.PLAYLIST_ID) {
        initPlaylistDetail(window.PLAYLIST_ID);
    }
});

// ═════════════════════════════════════════════════════════════════
// Playlists List Page
// ═════════════════════════════════════════════════════════════════

function initPlaylistsList() {
    const grid = document.getElementById('playlists-grid');
    const emptyState = document.getElementById('empty-state');
    const createBtn = document.getElementById('create-playlist-btn');
    const createModal = document.getElementById('create-modal');
    
    // Load playlists
    loadPlaylists();
    
    // Create button handler
    createBtn?.addEventListener('click', () => {
        showModal(createModal);
    });
    
    // Modal handlers
    setupModalHandlers(createModal, createPlaylist);
    
    // Color picker
    setupColorPicker(createModal);
    
    async function loadPlaylists() {
        try {
            const response = await fetch('/api/playlists');
            const data = await response.json();
            
            if (!data.playlists || data.playlists.length === 0) {
                grid.style.display = 'none';
                emptyState.style.display = 'block';
                return;
            }
            
            grid.style.display = 'grid';
            emptyState.style.display = 'none';
            
            grid.innerHTML = data.playlists.map(playlist => renderPlaylistCard(playlist)).join('');
            
            // Add click handlers
            grid.querySelectorAll('.playlist-card').forEach(card => {
                card.addEventListener('click', (e) => {
                    if (!e.target.closest('.playlist-card-actions')) {
                        window.location.href = `/playlist/${card.dataset.id}`;
                    }
                });
            });
        } catch (error) {
            console.error('Error loading playlists:', error);
            grid.innerHTML = '<div class="error">Failed to load playlists</div>';
        }
    }
    
    function renderPlaylistCard(playlist) {
        const color = playlist.color || '#3b82f6';
        const videoCount = playlist.video_count || 0;
        const thumbnails = playlist.thumbnails || [];
        
        return `
            <div class="playlist-card" data-id="${playlist.id}" style="border-left-color: ${color}">
                <div class="playlist-thumbnail-mosaic">
                    ${renderMosaic(thumbnails, videoCount, color)}
                </div>
                <div class="playlist-card-info">
                    <h3 class="playlist-card-title">${escapeHtml(playlist.name)}</h3>
                    <p class="playlist-card-desc">${escapeHtml(playlist.description || '')}</p>
                    <div class="playlist-card-meta">
                        <span>${videoCount} video${videoCount !== 1 ? 's' : ''}</span>
                        <span>•</span>
                        <span>${playlist.updated_at?.slice(0, 10) || 'Unknown'}</span>
                    </div>
                </div>
            </div>
        `;
    }
    
    function renderMosaic(thumbnails, count, color) {
        if (count === 0) {
            return `<div class="mosaic-empty" style="background: ${color}20">
                <span class="mosaic-icon">📁</span>
            </div>`;
        }
        
        // Get first 4 thumbnails
        const thumbs = thumbnails.slice(0, 4);
        const positions = count > 1 ? ['top-left', 'top-right', 'bottom-left', 'bottom-right'] : ['full'];
        
        return `
            <div class="mosaic-grid mosaic-count-${Math.min(count, 4)}">
                ${thumbs.map((thumb, i) => `
                    <div class="mosaic-item ${positions[i] || ''}">
                        <img src="${thumb}" alt="" loading="lazy">
                    </div>
                `).join('')}
                ${count > 4 ? `<div class="mosaic-overlay">+${count - 4}</div>` : ''}
            </div>
        `;
    }
    
    async function createPlaylist() {
        const name = document.getElementById('playlist-name').value.trim();
        const description = document.getElementById('playlist-description').value.trim();
        const color = createModal.querySelector('.color-option.active')?.dataset.color || '#3b82f6';
        
        if (!name) {
            alert('Please enter a playlist name');
            return;
        }
        
        try {
            const response = await fetch('/api/playlists', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description, color })
            });
            
            const data = await response.json();
            
            if (data.success) {
                hideModal(createModal);
                // Clear form
                document.getElementById('playlist-name').value = '';
                document.getElementById('playlist-description').value = '';
                // Reload
                loadPlaylists();
            } else {
                alert(data.error || 'Failed to create playlist');
            }
        } catch (error) {
            console.error('Error creating playlist:', error);
            alert('Failed to create playlist');
        }
    }
}

// ═════════════════════════════════════════════════════════════════
// Playlist Detail Page
// ═════════════════════════════════════════════════════════════════

function initPlaylistDetail(playlistId) {
    const videosContainer = document.getElementById('playlist-videos');
    const emptyState = document.getElementById('empty-videos');
    
    // Load playlist data
    loadPlaylist();
    
    // Setup toolbar buttons
    document.getElementById('add-videos-btn')?.addEventListener('click', () => {
        // Navigate to browse page with playlist context
        window.location.href = `/?add_to_playlist=${playlistId}`;
    });
    
    // Export dropdown
    const exportBtn = document.getElementById('export-btn');
    const exportMenu = document.getElementById('export-menu');
    if (exportBtn && exportMenu) {
        exportBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            exportMenu.classList.toggle('hidden');
        });
        document.addEventListener('click', () => {
            exportMenu.classList.add('hidden');
        });
    }
    
    // Edit modal
    const editModal = document.getElementById('edit-modal');
    const editBtn = document.getElementById('edit-playlist-btn');
    if (editBtn) {
        editBtn.addEventListener('click', () => {
            showModal(editModal);
        });
    }
    setupModalHandlers(editModal, savePlaylistEdit);
    setupColorPicker(editModal);
    
    // Delete modal
    const deleteModal = document.getElementById('delete-modal');
    const deleteBtn = document.getElementById('delete-playlist-btn');
    const confirmDeleteBtn = document.getElementById('confirm-delete-btn');
    
    if (deleteBtn) {
        deleteBtn.addEventListener('click', () => showModal(deleteModal));
    }
    setupModalHandlers(deleteModal);
    
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', async () => {
            try {
                const response = await fetch(`/api/playlists/${playlistId}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    window.location.href = '/playlists';
                } else {
                    alert('Failed to delete playlist');
                }
            } catch (error) {
                console.error('Error deleting playlist:', error);
                alert('Failed to delete playlist');
            }
        });
    }
    
    async function loadPlaylist() {
        try {
            const response = await fetch(`/api/playlists/${playlistId}`);
            const data = await response.json();
            
            if (!data.playlist) {
                videosContainer.innerHTML = '<div class="error">Playlist not found</div>';
                return;
            }
            
            const videos = data.videos || [];
            
            if (videos.length === 0) {
                videosContainer.style.display = 'none';
                emptyState.style.display = 'block';
                return;
            }
            
            videosContainer.style.display = 'block';
            emptyState.style.display = 'none';
            
            renderVideos(videos);
            setupDragAndDrop();
        } catch (error) {
            console.error('Error loading playlist:', error);
            videosContainer.innerHTML = '<div class="error">Failed to load playlist</div>';
        }
    }
    
    function renderVideos(videos) {
        videosContainer.innerHTML = videos.map((video, index) => `
            <div class="playlist-video-item" data-video-id="${video.id}" data-position="${video.position}">
                <div class="drag-handle" title="Drag to reorder">⋮⋮</div>
                <div class="video-position">${index + 1}</div>
                <div class="video-thumb">
                    ${video.thumbnail_url 
                        ? `<img src="${video.thumbnail_url}" alt="" loading="lazy">`
                        : '<div class="no-thumb-sm">No preview</div>'
                    }
                </div>
                <div class="video-info">
                    <div class="video-title">${escapeHtml(video.file_name)}</div>
                    <div class="video-meta">
                        ${video.duration_seconds ? formatDuration(video.duration_seconds) : ''}
                        ${video.resolution ? `• ${video.resolution}` : ''}
                        ${video.gps_location_name ? `• ${escapeHtml(video.gps_location_name)}` : ''}
                    </div>
                    ${video.scene_description && !video.scene_description.startsWith('ERROR') 
                        ? `<div class="video-desc">${escapeHtml(video.scene_description.substring(0, 100))}</div>`
                        : ''
                    }
                </div>
                <div class="video-actions">
                    <a href="/video/${video.id}" class="btn-icon" title="View">👁</a>
                    <button class="btn-icon remove-video" title="Remove from playlist" data-video-id="${video.id}">✕</button>
                </div>
            </div>
        `).join('');
        
        // Add remove handlers
        videosContainer.querySelectorAll('.remove-video').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const videoId = btn.dataset.videoId;
                if (confirm('Remove this video from the playlist?')) {
                    await removeVideo(videoId);
                }
            });
        });
    }
    
    async function removeVideo(videoId) {
        try {
            const response = await fetch(`/api/playlists/${playlistId}/items/${videoId}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                loadPlaylist(); // Reload to update positions
            } else {
                alert('Failed to remove video');
            }
        } catch (error) {
            console.error('Error removing video:', error);
            alert('Failed to remove video');
        }
    }
    
    function setupDragAndDrop() {
        const items = videosContainer.querySelectorAll('.playlist-video-item');
        let draggedItem = null;
        
        items.forEach(item => {
            item.draggable = true;
            
            item.addEventListener('dragstart', (e) => {
                draggedItem = item;
                item.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            });
            
            item.addEventListener('dragend', () => {
                item.classList.remove('dragging');
                draggedItem = null;
                
                // Update all positions
                updatePositions();
            });
            
            item.addEventListener('dragover', (e) => {
                e.preventDefault();
                if (!draggedItem || draggedItem === item) return;
                
                const rect = item.getBoundingClientRect();
                const midpoint = rect.top + rect.height / 2;
                
                if (e.clientY < midpoint) {
                    item.parentNode.insertBefore(draggedItem, item);
                } else {
                    item.parentNode.insertBefore(draggedItem, item.nextSibling);
                }
            });
        });
    }
    
    async function updatePositions() {
        const items = videosContainer.querySelectorAll('.playlist-video-item');
        const updates = [];
        
        items.forEach((item, index) => {
            const videoId = item.dataset.videoId;
            const newPosition = index + 1;
            const oldPosition = parseInt(item.dataset.position);
            
            if (newPosition !== oldPosition) {
                updates.push({ video_id: parseInt(videoId), new_position: newPosition });
                item.dataset.position = newPosition;
                item.querySelector('.video-position').textContent = newPosition;
            }
        });
        
        // Send updates to server
        for (const update of updates) {
            try {
                await fetch(`/api/playlists/${playlistId}/reorder`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(update)
                });
            } catch (error) {
                console.error('Error updating position:', error);
            }
        }
    }
    
    async function savePlaylistEdit() {
        const name = document.getElementById('edit-name').value.trim();
        const description = document.getElementById('edit-description').value.trim();
        const color = editModal.querySelector('.color-option.active')?.dataset.color || window.PLAYLIST_COLOR;
        
        if (!name) {
            alert('Please enter a playlist name');
            return;
        }
        
        try {
            const response = await fetch(`/api/playlists/${playlistId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description, color })
            });
            
            if (response.ok) {
                hideModal(editModal);
                // Update UI
                document.getElementById('playlist-name').textContent = name;
                const descEl = document.getElementById('playlist-description');
                if (description) {
                    descEl.textContent = description;
                    descEl.classList.remove('empty');
                } else {
                    descEl.textContent = 'No description';
                    descEl.classList.add('empty');
                }
                document.querySelector('.playlist-header').style.borderLeftColor = color;
                window.PLAYLIST_COLOR = color;
            } else {
                alert('Failed to update playlist');
            }
        } catch (error) {
            console.error('Error updating playlist:', error);
            alert('Failed to update playlist');
        }
    }
}

// ═════════════════════════════════════════════════════════════════
// Shared Utilities
// ═════════════════════════════════════════════════════════════════

function setupModalHandlers(modal, onConfirm = null) {
    const closeBtn = modal.querySelector('.modal-close');
    const cancelBtn = modal.querySelector('.modal-cancel');
    
    closeBtn?.addEventListener('click', () => hideModal(modal));
    cancelBtn?.addEventListener('click', () => hideModal(modal));
    
    modal.addEventListener('click', (e) => {
        if (e.target === modal) hideModal(modal);
    });
    
    if (onConfirm) {
        const confirmBtn = modal.querySelector('.btn-primary');
        confirmBtn?.addEventListener('click', onConfirm);
    }
}

function showModal(modal) {
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function hideModal(modal) {
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}

function setupColorPicker(container) {
    const options = container.querySelectorAll('.color-option');
    options.forEach(option => {
        option.addEventListener('click', () => {
            options.forEach(o => o.classList.remove('active'));
            option.classList.add('active');
        });
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDuration(seconds) {
    if (!seconds) return '';
    const total = Math.floor(seconds);
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// ═════════════════════════════════════════════════════════════════
// Global "Add to Playlist" Modal (used on browse/search pages)
// ═════════════════════════════════════════════════════════════════

window.showAddToPlaylistModal = async function(videoId, videoName) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('add-to-playlist-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'add-to-playlist-modal';
        modal.className = 'modal hidden';
        modal.innerHTML = `
            <div class="modal-content modal-small">
                <div class="modal-header">
                    <h3>Add to Playlist</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    <p class="video-name"></p>
                    <div class="form-group">
                        <label>Select Playlist</label>
                        <div id="playlist-options" class="playlist-options">
                            <div class="loader">Loading...</div>
                        </div>
                    </div>
                    <div class="or-divider">or</div>
                    <div class="form-group">
                        <input type="text" id="new-playlist-name" placeholder="Create new playlist..." autocomplete="off">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn-secondary modal-cancel">Cancel</button>
                    <button class="btn-primary" id="confirm-add-btn">Add</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        setupModalHandlers(modal);
    }
    
    modal.querySelector('.video-name').textContent = videoName;
    const optionsContainer = modal.querySelector('#playlist-options');
    optionsContainer.innerHTML = '<div class="loader">Loading...</div>';
    
    let selectedPlaylistId = null;
    
    // Load playlists
    try {
        const response = await fetch('/api/playlists');
        const data = await response.json();
        
        if (!data.playlists || data.playlists.length === 0) {
            optionsContainer.innerHTML = '<p class="text-muted">No playlists yet. Create one below.</p>';
        } else {
            optionsContainer.innerHTML = data.playlists.map(p => `
                <div class="playlist-option" data-id="${p.id}">
                    <span class="playlist-color" style="background: ${p.color || '#3b82f6'}"></span>
                    <span class="playlist-name">${escapeHtml(p.name)}</span>
                    <span class="playlist-count">${p.video_count || 0}</span>
                </div>
            `).join('');
            
            optionsContainer.querySelectorAll('.playlist-option').forEach(opt => {
                opt.addEventListener('click', () => {
                    optionsContainer.querySelectorAll('.playlist-option').forEach(o => o.classList.remove('selected'));
                    opt.classList.add('selected');
                    selectedPlaylistId = opt.dataset.id;
                    document.getElementById('new-playlist-name').value = '';
                });
            });
        }
    } catch (error) {
        optionsContainer.innerHTML = '<p class="error">Failed to load playlists</p>';
    }
    
    // Confirm handler
    const confirmBtn = modal.querySelector('#confirm-add-btn');
    confirmBtn.onclick = async () => {
        const newName = document.getElementById('new-playlist-name').value.trim();
        
        if (!selectedPlaylistId && !newName) {
            alert('Please select a playlist or enter a new name');
            return;
        }
        
        try {
            const response = await fetch('/api/batch/add-to-playlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_ids: [videoId],
                    playlist_id: selectedPlaylistId ? parseInt(selectedPlaylistId) : null,
                    playlist_name: newName || null
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                hideModal(modal);
                // Show success notification
                showNotification(`Added to "${newName || 'playlist'}"`, 'success');
            } else {
                alert(data.error || 'Failed to add to playlist');
            }
        } catch (error) {
            console.error('Error adding to playlist:', error);
            alert('Failed to add to playlist');
        }
    };
    
    showModal(modal);
};

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}
