/**
 * Map view for B-Roll Catalog
 * Interactive map with Leaflet.js and marker clustering
 */
document.addEventListener('DOMContentLoaded', () => {
    // State management
    const state = {
        map: null,
        markers: null,
        allVideos: [],
        filteredVideos: [],
        locations: [],
        activeFilters: new Set(),
        popupVideo: null,
        contextMenuLatLng: null,
        nearbyRadius: 5.0, // km
    };

    // DOM elements
    const elements = {
        map: document.getElementById('map'),
        sidebar: document.getElementById('map-sidebar'),
        locationFilters: document.getElementById('location-filters'),
        fitBoundsBtn: document.getElementById('fit-bounds-btn'),
        statsDisplay: document.getElementById('stats-display'),
        visibleCount: document.getElementById('visible-count'),
        emptyState: document.getElementById('map-empty-state'),
        loading: document.getElementById('map-loading'),
        contextMenu: document.getElementById('map-context-menu'),
        findNearbyBtn: document.getElementById('find-nearby-btn'),
    };

    // Initialize the map application
    init();

    async function init() {
        try {
            // Show loading
            elements.loading.classList.remove('hidden');

            // Initialize map
            initMap();

            // Load data
            await Promise.all([
                loadVideos(),
                loadLocations(),
            ]);

            // Render
            renderMarkers();
            renderLocationFilters();

            // Hide loading
            elements.loading.classList.add('hidden');

            // Check if we have any videos with coordinates
            if (state.allVideos.length === 0) {
                showEmptyState();
            } else {
                // Fit bounds to show all markers
                fitBounds();
            }

            // Setup event listeners
            setupEventListeners();

        } catch (error) {
            console.error('Error initializing map:', error);
            elements.loading.innerHTML = `<span class="error">Error loading map: ${error.message}</span>`;
        }
    }

    function initMap() {
        // Create map centered on Japan (default for this catalog)
        state.map = L.map('map', {
            center: [35.6762, 139.6503], // Tokyo
            zoom: 6,
            zoomControl: false, // We'll add it in a better position
        });

        // Add zoom control to top-right
        L.control.zoom({
            position: 'topright'
        }).addTo(state.map);

        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19,
        }).addTo(state.map);

        // Initialize marker cluster group
        state.markers = L.markerClusterGroup({
            chunkedLoading: true,
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            maxClusterRadius: 60,
            iconCreateFunction: function(cluster) {
                const count = cluster.getChildCount();
                let size = 'small';
                if (count >= 100) size = 'large';
                else if (count >= 10) size = 'medium';

                return L.divIcon({
                    html: `<div class="cluster-marker cluster-${size}"><span>${count}</span></div>`,
                    className: 'marker-cluster',
                    iconSize: L.point(40, 40)
                });
            }
        });

        state.map.addLayer(state.markers);

        // Setup map click for context menu
        state.map.on('click', (e) => {
            hideContextMenu();
        });

        state.map.on('contextmenu', (e) => {
            showContextMenu(e.latlng);
        });

        // Hide context menu when clicking elsewhere
        document.addEventListener('click', (e) => {
            if (!elements.contextMenu.contains(e.target)) {
                hideContextMenu();
            }
        });
    }

    async function loadVideos() {
        const response = await fetch('/api/map/videos');
        if (!response.ok) {
            throw new Error('Failed to load videos');
        }
        const data = await response.json();
        state.allVideos = data.videos || [];
        state.filteredVideos = [...state.allVideos];
    }

    async function loadLocations() {
        const response = await fetch('/api/map/locations');
        if (!response.ok) {
            throw new Error('Failed to load locations');
        }
        const data = await response.json();
        state.locations = data.locations || [];

        // Activate all filters by default
        state.locations.forEach(loc => {
            state.activeFilters.add(loc.location_name);
        });
    }

    function renderMarkers() {
        state.markers.clearLayers();

        if (state.filteredVideos.length === 0) {
            updateStats();
            return;
        }

        const markers = [];

        state.filteredVideos.forEach(video => {
            if (!video.gps_latitude || !video.gps_longitude) return;

            const marker = createVideoMarker(video);
            markers.push(marker);
        });

        state.markers.addLayers(markers);
        updateStats();
    }

    function createVideoMarker(video) {
        const lat = video.gps_latitude;
        const lon = video.gps_longitude;

        const marker = L.marker([lat, lon], {
            title: video.file_name,
        });

        // Create popup content
        const popupContent = createPopupContent(video);
        marker.bindPopup(popupContent, {
            maxWidth: 320,
            minWidth: 280,
            className: 'video-popup'
        });

        // Store video reference on marker
        marker.videoId = video.id;

        return marker;
    }

    function createPopupContent(video) {
        const locationName = video.gps_location_name || 'Unknown Location';
        const locationSource = video.location_source || 'gps';

        // Get recent clips from same location (up to 4)
        const relatedVideos = state.allVideos
            .filter(v => {
                const sameLocation = v.gps_location_name === video.gps_location_name;
                const sameFolder = v.folder_location === video.folder_location;
                return (sameLocation || sameFolder) && v.id !== video.id;
            })
            .slice(0, 4);

        let galleryHtml = '';
        if (relatedVideos.length > 0) {
            galleryHtml = `
                <div class="popup-gallery">
                    <div class="gallery-title">Recent clips nearby</div>
                    <div class="gallery-thumbs">
                        ${relatedVideos.map(v => `
                            <a href="/video/${v.id}" class="gallery-thumb" title="${v.file_name}">
                                ${v.thumbnail_url
                                    ? `<img src="${v.thumbnail_url}" alt="${v.file_name}" loading="lazy">`
                                    : '<div class="no-thumb-sm">No Preview</div>'
                                }
                            </a>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        const sourceBadge = locationSource !== 'gps'
            ? `<span class="source-badge source-${locationSource}">${locationSource}</span>`
            : '';

        return `
            <div class="video-popup-content">
                <div class="popup-header">
                    <h3 class="popup-title">${locationName} ${sourceBadge}</h3>
                </div>
                <div class="popup-main">
                    <a href="/video/${video.id}" class="popup-thumb">
                        ${video.thumbnail_url
                            ? `<img src="${video.thumbnail_url}" alt="${video.file_name}">`
                            : '<div class="no-thumb">No Preview</div>'
                        }
                    </a>
                    <div class="popup-info">
                        <div class="popup-filename">${video.file_name}</div>
                        ${video.scene_description && !video.scene_description.startsWith('ERROR')
                            ? `<div class="popup-desc">${video.scene_description.substring(0, 100)}${video.scene_description.length > 100 ? '...' : ''}</div>`
                            : ''
                        }
                        <div class="popup-meta">
                            ${video.duration_seconds ? `<span>⏱️ ${formatDuration(video.duration_seconds)}</span>` : ''}
                            ${video.resolution ? `<span>📐 ${video.resolution}</span>` : ''}
                        </div>
                    </div>
                </div>
                ${galleryHtml}
                <div class="popup-footer">
                    <a href="/?path=${encodeURIComponent(video.file_path.split('/').slice(0, -1).join('/'))}" class="btn-secondary">
                        Show all in folder
                    </a>
                </div>
            </div>
        `;
    }

    function renderLocationFilters() {
        if (state.locations.length === 0) {
            elements.locationFilters.innerHTML = '<div class="empty-locations">No locations found</div>';
            return;
        }

        elements.locationFilters.innerHTML = state.locations.map(loc => {
            const isActive = state.activeFilters.has(loc.location_name);
            return `
                <label class="location-filter-item ${isActive ? 'active' : 'inactive'}">
                    <input type="checkbox"
                        class="location-checkbox"
                        value="${escapeHtml(loc.location_name)}"
                        ${isActive ? 'checked' : ''}
                    >
                    <span class="filter-name">${escapeHtml(loc.location_name)}</span>
                    <span class="filter-count">${loc.count}</span>
                </label>
            `;
        }).join('');

        // Add event listeners to checkboxes
        elements.locationFilters.querySelectorAll('.location-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const locationName = e.target.value;
                const parent = e.target.closest('.location-filter-item');

                if (e.target.checked) {
                    state.activeFilters.add(locationName);
                    parent.classList.remove('inactive');
                    parent.classList.add('active');
                } else {
                    state.activeFilters.delete(locationName);
                    parent.classList.remove('active');
                    parent.classList.add('inactive');
                }

                applyFilters();
            });
        });
    }

    function applyFilters() {
        // Filter videos based on active location filters
        state.filteredVideos = state.allVideos.filter(video => {
            const locationName = video.gps_location_name || video.folder_location || 'Unknown Location';
            return state.activeFilters.has(locationName);
        });

        renderMarkers();
    }

    function fitBounds() {
        if (state.filteredVideos.length === 0) return;

        const validCoords = state.filteredVideos.filter(v =>
            v.gps_latitude && v.gps_longitude
        );

        if (validCoords.length === 0) return;

        const group = new L.featureGroup(
            validCoords.map(v => L.marker([v.gps_latitude, v.gps_longitude]))
        );

        state.map.fitBounds(group.getBounds().pad(0.1));
    }

    function showContextMenu(latlng) {
        state.contextMenuLatLng = latlng;

        // Position context menu near click (converted to container point)
        const containerPoint = state.map.latLngToContainerPoint(latlng);

        elements.contextMenu.style.left = `${containerPoint.x}px`;
        elements.contextMenu.style.top = `${containerPoint.y}px`;
        elements.contextMenu.classList.remove('hidden');
    }

    function hideContextMenu() {
        elements.contextMenu.classList.add('hidden');
        state.contextMenuLatLng = null;
    }

    async function findNearbyVideos() {
        if (!state.contextMenuLatLng) return;

        const lat = state.contextMenuLatLng.lat;
        const lon = state.contextMenuLatLng.lng;

        hideContextMenu();

        // Show loading in sidebar
        elements.locationFilters.innerHTML = '<div class="loading">Searching nearby...</div>';

        try {
            const response = await fetch(
                `/api/map/nearby?lat=${lat}&lon=${lon}&radius_km=${state.nearbyRadius}`
            );

            if (!response.ok) {
                throw new Error('Failed to search nearby videos');
            }

            const data = await response.json();
            const nearbyVideos = data.videos || [];

            // Update filtered videos to show only nearby ones
            state.filteredVideos = nearbyVideos;

            // Add a temporary marker for the search center
            const searchMarker = L.marker([lat, lon], {
                icon: L.divIcon({
                    html: '<div class="search-center-marker"></div>',
                    className: 'search-marker',
                    iconSize: [20, 20]
                })
            }).addTo(state.map);

            searchMarker.bindPopup(`
                <div class="search-popup">
                    <strong>Search Center</strong><br>
                    Radius: ${state.nearbyRadius} km<br>
                    Found: ${nearbyVideos.length} clips
                </div>
            `).openPopup();

            // Remove marker after 5 seconds
            setTimeout(() => {
                state.map.removeLayer(searchMarker);
            }, 5000);

            renderMarkers();

            // Update sidebar to show nearby results
            elements.locationFilters.innerHTML = `
                <div class="nearby-results">
                    <div class="nearby-header">
                        <h4>📍 Nearby Videos</h4>
                        <button id="clear-nearby-btn" class="btn-link">Clear</button>
                    </div>
                    <p class="nearby-info">
                        Found ${nearbyVideos.length} clips within ${state.nearbyRadius} km
                    </p>
                    <ul class="nearby-list">
                        ${nearbyVideos.slice(0, 10).map(v => `
                            <li>
                                <a href="/video/${v.id}">${escapeHtml(v.file_name)}</a>
                                <span class="nearby-distance">${v.distance_km?.toFixed(2) || '?'} km</span>
                            </li>
                        `).join('')}
                        ${nearbyVideos.length > 10 ? `<li class="more-items">...and ${nearbyVideos.length - 10} more</li>` : ''}
                    </ul>
                </div>
            `;

            // Add clear button listener
            document.getElementById('clear-nearby-btn')?.addEventListener('click', () => {
                state.filteredVideos = [...state.allVideos];
                state.activeFilters = new Set(state.locations.map(l => l.location_name));
                renderMarkers();
                renderLocationFilters();
                fitBounds();
            });

            // Pan map to search center
            state.map.setView([lat, lon], 13);

        } catch (error) {
            console.error('Error finding nearby videos:', error);
            elements.locationFilters.innerHTML = `<div class="error">Error: ${error.message}</div>`;
        }
    }

    function showEmptyState() {
        elements.emptyState.classList.remove('hidden');
    }

    function updateStats() {
        elements.visibleCount.textContent = state.filteredVideos.length;
    }

    function setupEventListeners() {
        // Fit bounds button
        elements.fitBoundsBtn.addEventListener('click', fitBounds);

        // Find nearby button
        elements.findNearbyBtn.addEventListener('click', findNearbyVideos);

        // Handle window resize
        window.addEventListener('resize', () => {
            state.map?.invalidateSize();
        });
    }

    // Utility functions
    function formatDuration(seconds) {
        if (!seconds) return '--:--';
        const total = Math.floor(seconds);
        const mins = Math.floor(total / 60);
        const secs = total % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});