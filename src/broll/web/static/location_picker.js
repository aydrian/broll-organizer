/**
 * Reusable location picker component.
 * Provides a modal interface for setting video locations.
 *
 * Usage:
 *   LocationPicker.init({
 *     onConfirm: (lat, lon, name) => { ... },
 *     onCancel: () => { ... }
 *   });
 *   LocationPicker.open();
 */
const LocationPicker = (function() {
    // DOM elements (populated on init)
    let modal = null;
    let urlInput = null;
    let urlParseBtn = null;
    let urlError = null;
    let searchInput = null;
    let resultsContainer = null;
    let latInput = null;
    let lonInput = null;
    let nameInput = null;
    let confirmBtn = null;
    let cancelBtn = null;

    // State
    let callbacks = {};
    let searchTimeout = null;
    let selectedLocation = null;

    function init(options = {}) {
        callbacks = {
            onConfirm: options.onConfirm || (() => {}),
            onCancel: options.onCancel || (() => {})
        };

        // Get DOM elements
        modal = document.getElementById('location-picker-modal');
        if (!modal) {
            console.error('[LocationPicker] Modal not found in DOM');
            return;
        }

        urlInput = modal.querySelector('#location-url-input');
        urlParseBtn = modal.querySelector('#location-parse-url-btn');
        urlError = modal.querySelector('#location-url-error');
        searchInput = modal.querySelector('#location-search');
        resultsContainer = modal.querySelector('#location-results');
        latInput = modal.querySelector('#location-lat');
        lonInput = modal.querySelector('#location-lon');
        nameInput = modal.querySelector('#location-name');
        confirmBtn = modal.querySelector('#confirm-set-location');
        cancelBtn = modal.querySelector('#cancel-location-picker');

        bindEvents();
    }

    function bindEvents() {
        // URL parsing
        if (urlParseBtn) {
            urlParseBtn.addEventListener('click', parseGoogleMapsUrl);
        }

        if (urlInput) {
            urlInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    parseGoogleMapsUrl();
                }
            });
        }

        // Search with debounce
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(searchTimeout);
                const query = searchInput.value.trim();

                if (!query) {
                    // Show recent locations when search is empty
                    loadRecentLocations();
                    return;
                }

                searchTimeout = setTimeout(doSearch, 300);
            });

            // Show recent locations when focused and empty
            searchInput.addEventListener('focus', () => {
                if (!searchInput.value.trim()) {
                    loadRecentLocations();
                }
            });
        }

        // Cancel
        if (cancelBtn) {
            cancelBtn.addEventListener('click', close);
        }

        // Close on backdrop click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                close();
            }
        });

        // Confirm
        if (confirmBtn) {
            confirmBtn.addEventListener('click', confirmLocation);
        }

        // Manual coordinate inputs
        if (latInput) {
            latInput.addEventListener('input', updateSelectedFromManual);
        }
        if (lonInput) {
            lonInput.addEventListener('input', updateSelectedFromManual);
        }
        if (nameInput) {
            nameInput.addEventListener('input', updateSelectedFromManual);
        }
    }

    async function parseGoogleMapsUrl() {
        const url = urlInput.value.trim();
        if (!url) return;

        urlError.classList.add('hidden');
        urlParseBtn.disabled = true;
        const originalContent = urlParseBtn.innerHTML;
        urlParseBtn.innerHTML = '<span class="spinner" aria-hidden="true">⏳</span>';

        try {
            const response = await fetch('/api/location/parse-url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            const data = await response.json();

            if (response.ok && data.lat !== undefined && data.lon !== undefined) {
                latInput.value = data.lat;
                lonInput.value = data.lon;
                // Use the name from the API (extracted from URL) or fall back to default
                const extractedName = data.name || 'Location from URL';
                nameInput.value = extractedName;
                selectedLocation = {
                    lat: data.lat,
                    lon: data.lon,
                    name: extractedName
                };
                // Clear search since we have coordinates
                searchInput.value = '';
                resultsContainer.innerHTML = '';
                // Focus name input for user to edit
                nameInput.focus();
                // Show success feedback briefly
                urlParseBtn.innerHTML = '<span aria-hidden="true">✓</span>';
                setTimeout(() => {
                    urlParseBtn.innerHTML = originalContent;
                }, 1000);
            } else {
                urlError.textContent = data.error || 'Could not parse URL';
                urlError.classList.remove('hidden');
                urlParseBtn.innerHTML = originalContent;
            }
        } catch (err) {
            urlError.textContent = 'Failed to parse URL';
            urlError.classList.remove('hidden');
            urlParseBtn.innerHTML = originalContent;
        } finally {
            urlParseBtn.disabled = false;
        }
    }

    async function loadRecentLocations() {
        resultsContainer.innerHTML = '<p class="text-muted">Loading recent...</p>';

        try {
            const response = await fetch('/api/location/recent');
            const data = await response.json();

            if (!Array.isArray(data) || data.length === 0) {
                resultsContainer.innerHTML = '<p class="text-muted">Type to search for locations</p>';
                return;
            }

            renderResults(data, 'Recent Locations');
        } catch (err) {
            resultsContainer.innerHTML = '<p class="text-muted">Type to search for locations</p>';
        }
    }

    function renderResults(data, headerText) {
        let html = '';
        if (headerText) {
            html += `<div class="location-results-header">${escapeHtml(headerText)}</div>`;
        }

        html += data.map(item => `
            <div class="location-result-item" data-lat="${item.lat}" data-lon="${item.lon}" data-name="${escapeHtml(item.name)}" data-type="${item.type || 'unknown'}">
                <div class="location-name">${escapeHtml(item.name)}</div>
                <div class="location-coords">${item.lat.toFixed(4)}, ${item.lon.toFixed(4)}</div>
            </div>
        `).join('');

        resultsContainer.innerHTML = html;

        // Add click handlers
        resultsContainer.querySelectorAll('.location-result-item').forEach(item => {
            item.addEventListener('click', () => {
                resultsContainer.querySelectorAll('.location-result-item').forEach(i => i.classList.remove('selected'));
                item.classList.add('selected');
                selectedLocation = {
                    lat: parseFloat(item.dataset.lat),
                    lon: parseFloat(item.dataset.lon),
                    name: item.dataset.name,
                    type: item.dataset.type
                };
                latInput.value = selectedLocation.lat;
                lonInput.value = selectedLocation.lon;
                nameInput.value = selectedLocation.name;

                // Cache this location for future searches (only if it's not already from cache/recent)
                if (selectedLocation.type !== 'cached' && selectedLocation.type !== 'recent') {
                    cacheSelectedLocation(selectedLocation.name, selectedLocation.lat, selectedLocation.lon);
                }
            });
        });

        // Auto-select first result
        const first = resultsContainer.querySelector('.location-result-item');
        if (first) {
            first.classList.add('selected');
            selectedLocation = {
                lat: parseFloat(first.dataset.lat),
                lon: parseFloat(first.dataset.lon),
                name: first.dataset.name,
                type: first.dataset.type
            };
            latInput.value = selectedLocation.lat;
            lonInput.value = selectedLocation.lon;
            nameInput.value = selectedLocation.name;
        }
    }

    async function cacheSelectedLocation(name, lat, lon) {
        if (!name || !lat || !lon) return;

        // Use the search query as the cache key if available, otherwise use the location name
        const searchKey = searchInput.value.trim() || name;
        try {
            await fetch('/api/location/cache', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    search_key: searchKey,
                    display_name: name,
                    lat: lat,
                    lon: lon
                })
            });
            // Silent success - don't need to show anything
        } catch (e) {
            // Silent fail - caching is just for convenience
            console.log('Failed to cache location:', e);
        }
    }

    async function doSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        resultsContainer.innerHTML = '<p class="text-muted">Searching...</p>';

        try {
            const response = await fetch(`/api/location/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();

            if (data.error) {
                resultsContainer.innerHTML = `<p class="error">${data.error}</p>`;
                return;
            }

            if (!Array.isArray(data) || data.length === 0) {
                resultsContainer.innerHTML = '<p class="text-muted">No results found</p>';
                return;
            }

            renderResults(data, 'Search Results');
        } catch (err) {
            resultsContainer.innerHTML = '<p class="error">Search failed</p>';
        }
    }

    function updateSelectedFromManual() {
        const lat = parseFloat(latInput.value);
        const lon = parseFloat(lonInput.value);
        const name = nameInput.value.trim();

        if (!isNaN(lat) && !isNaN(lon)) {
            selectedLocation = { lat, lon, name };
        }
    }

    async function confirmLocation() {
        const lat = parseFloat(latInput.value);
        const lon = parseFloat(lonInput.value);
        const name = nameInput.value.trim();

        if (isNaN(lat) || isNaN(lon)) {
            alert('Please enter valid latitude and longitude');
            return;
        }

        if (!name) {
            alert('Please enter a location name');
            return;
        }

        // Cache this location for future searches (using the display name as search key)
        await cacheSelectedLocation(name, lat, lon);

        callbacks.onConfirm(lat, lon, name);
        close();
    }

    function open() {
        // Reset state
        selectedLocation = null;
        if (urlInput) urlInput.value = '';
        if (urlError) urlError.classList.add('hidden');
        if (searchInput) searchInput.value = '';
        if (resultsContainer) resultsContainer.innerHTML = '';
        if (latInput) latInput.value = '';
        if (lonInput) lonInput.value = '';
        if (nameInput) nameInput.value = '';

        modal.classList.add('show');
        if (searchInput) searchInput.focus();
    }

    function close() {
        modal.classList.remove('show');
        callbacks.onCancel();
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Public API
    return {
        init,
        open,
        close
    };
})();

// Make available globally
window.LocationPicker = LocationPicker;