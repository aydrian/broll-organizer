/**
 * Timeline view for B-Roll Catalog
 * 
 * Features:
 * - Year overview with activity heatmap
 * - Month grid showing video counts per day
 * - Day view with all clips from that date
 * - "On this day" feature for past years
 * - Navigation: Year → Month → Day
 */

// State management
const state = {
    view: 'years',  // 'years', 'year', 'month', 'day'
    year: null,
    month: null,
    day: null,
    data: {},
    loading: false
};

// DOM elements
const elements = {
    view: document.getElementById('timeline-view'),
    breadcrumbs: document.getElementById('timeline-breadcrumbs'),
    templates: {
        years: document.getElementById('years-template'),
        year: document.getElementById('year-template'),
        month: document.getElementById('month-template'),
        day: document.getElementById('day-template')
    }
};

// Month names for display
const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
];

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Parse initial URL to determine view
    parseUrlAndLoad();
    
    // Handle browser back/forward
    window.addEventListener('popstate', parseUrlAndLoad);
});

/**
 * Parse current URL and load appropriate view
 */
function parseUrlAndLoad() {
    const path = window.location.pathname;
    const match = path.match(/\/timeline\/?(\d{4})?\/?(\d{1,2})?\/?(\d{1,2})?/);
    
    if (match) {
        const [, year, month, day] = match;
        
        if (day) {
            loadDayView(parseInt(year), parseInt(month), parseInt(day));
        } else if (month) {
            loadMonthView(parseInt(year), parseInt(month));
        } else if (year) {
            loadYearView(parseInt(year));
        } else {
            loadYearsView();
        }
    }
}

/**
 * Update browser URL without reloading
 */
function updateUrl(view, year = null, month = null, day = null) {
    let url = '/timeline';
    if (year) url += `/${year}`;
    if (month) url += `/${month}`;
    if (day) url += `/${day}`;
    
    window.history.pushState({ view, year, month, day }, '', url);
}

/**
 * Update breadcrumbs based on current view
 */
function updateBreadcrumbs(view, year = null, month = null, day = null) {
    let html = '<a href="/timeline" class="breadcrumb-root">Years</a>';
    
    if (year) {
        const yearLink = view === 'year' ? `<span class="breadcrumb-current">${year}</span>` : `<a href="/timeline/${year}">${year}</a>`;
        html += ` <span class="breadcrumb-separator">›</span> ${yearLink}`;
    }
    
    if (month && year) {
        const monthName = MONTH_NAMES[month - 1];
        const monthLink = view === 'month' ? `<span class="breadcrumb-current">${monthName}</span>` : `<a href="/timeline/${year}/${month}">${monthName}</a>`;
        html += ` <span class="breadcrumb-separator">›</span> ${monthLink}`;
    }
    
    if (day && month && year) {
        const dayLink = view === 'day' ? `<span class="breadcrumb-current">${day}</span>` : `<a href="/timeline/${year}/${month}/${day}">${day}</a>`;
        html += ` <span class="breadcrumb-separator">›</span> ${dayLink}`;
    }
    
    elements.breadcrumbs.innerHTML = html;
}

/**
 * Load and render the years overview
 */
async function loadYearsView() {
    if (state.loading) return;
    state.loading = true;
    state.view = 'years';
    
    showLoading();
    updateBreadcrumbs('years');
    
    try {
        const response = await fetch('/api/timeline/years');
        const data = await response.json();
        
        renderYearsView(data);
    } catch (error) {
        console.error('Error loading years:', error);
        showError('Failed to load years');
    } finally {
        state.loading = false;
    }
}

/**
 * Render the years overview
 */
function renderYearsView(data) {
    const template = elements.templates.years.content.cloneNode(true);
    const grid = template.querySelector('.years-grid');
    
    if (!data.years || data.years.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📅</div>
                <h3>No Videos Found</h3>
                <p>No videos with creation dates were found in your catalog.</p>
            </div>
        `;
    } else {
        data.years.forEach(yearData => {
            const yearCard = document.createElement('a');
            yearCard.className = 'year-card';
            yearCard.href = `/timeline/${yearData.year}`;
            
            const hours = Math.round(yearData.total_seconds / 3600 * 10) / 10;
            
            yearCard.innerHTML = `
                <div class="year-card-header">
                    <span class="year-number">${yearData.year}</span>
                    <span class="year-count">${yearData.count} clips</span>
                </div>
                <div class="year-card-stats">
                    <span class="year-duration">${hours} hours</span>
                </div>
                <div class="year-bar" style="--fill: ${Math.min(100, (yearData.count / 50) * 100)}%"></div>
            `;
            
            yearCard.addEventListener('click', (e) => {
                e.preventDefault();
                updateUrl('year', yearData.year);
                loadYearView(parseInt(yearData.year));
            });
            
            grid.appendChild(yearCard);
        });
    }
    
    elements.view.innerHTML = '';
    elements.view.appendChild(template);
}

/**
 * Load and render a specific year view
 */
async function loadYearView(year) {
    if (state.loading) return;
    state.loading = true;
    state.view = 'year';
    state.year = year;
    
    showLoading();
    updateBreadcrumbs('year', year);
    
    try {
        const response = await fetch(`/api/timeline/year/${year}`);
        const data = await response.json();
        
        renderYearView(year, data);
    } catch (error) {
        console.error('Error loading year:', error);
        showError('Failed to load year data');
    } finally {
        state.loading = false;
    }
}

/**
 * Render a year view with activity heatmap and month grid
 */
function renderYearView(year, data) {
    const template = elements.templates.year.content.cloneNode(true);
    
    // Update header
    template.querySelector('.year-title').textContent = year;
    template.querySelector('#year-total-videos').textContent = data.total_videos;
    template.querySelector('#year-active-days').textContent = data.active_days;
    
    // Render activity heatmap
    const heatmap = template.querySelector('#activity-heatmap');
    renderHeatmap(heatmap, data.activity, year);
    
    // Render month grid
    const monthsGrid = template.querySelector('#months-grid');
    renderMonthsGrid(monthsGrid, year);
    
    elements.view.innerHTML = '';
    elements.view.appendChild(template);
}

/**
 * Render activity heatmap
 */
function renderHeatmap(container, activity, year) {
    // Create a map of date -> count for quick lookup
    const activityMap = new Map(activity.map(a => [a.date, a.count]));
    
    // Build heatmap grid (52 weeks x 7 days)
    const grid = document.createElement('div');
    grid.className = 'heatmap-grid';
    
    // Add month labels
    const monthLabels = document.createElement('div');
    monthLabels.className = 'heatmap-months';
    MONTH_NAMES.forEach((month, i) => {
        if (i % 2 === 0) { // Show every other month
            const label = document.createElement('span');
            label.textContent = month.substring(0, 3);
            monthLabels.appendChild(label);
        }
    });
    container.appendChild(monthLabels);
    
    // Build the grid
    const cells = document.createElement('div');
    cells.className = 'heatmap-cells';
    
    // Get first day of year
    const firstDay = new Date(year, 0, 1);
    const startDayOfWeek = firstDay.getDay(); // 0 = Sunday
    
    // Add empty cells for days before Jan 1
    for (let i = 0; i < startDayOfWeek; i++) {
        const empty = document.createElement('div');
        empty.className = 'heatmap-cell empty';
        cells.appendChild(empty);
    }
    
    // Add cells for each day of the year
    const isLeap = (year % 4 === 0 && year % 100 !== 0) || (year % 400 === 0);
    const daysInYear = isLeap ? 366 : 365;
    
    for (let dayOfYear = 1; dayOfYear <= daysInYear; dayOfYear++) {
        const date = new Date(year, 0, dayOfYear);
        const dateStr = date.toISOString().split('T')[0];
        const count = activityMap.get(dateStr) || 0;
        
        const cell = document.createElement('div');
        cell.className = 'heatmap-cell';
        cell.dataset.date = dateStr;
        cell.dataset.count = count;
        
        // Set intensity based on count
        if (count === 0) {
            cell.classList.add('level-0');
        } else if (count <= 2) {
            cell.classList.add('level-1');
        } else if (count <= 5) {
            cell.classList.add('level-2');
        } else if (count <= 10) {
            cell.classList.add('level-3');
        } else {
            cell.classList.add('level-4');
        }
        
        // Tooltip
        cell.title = `${dateStr}: ${count} clip${count !== 1 ? 's' : ''}`;
        
        // Click to navigate to day
        if (count > 0) {
            cell.addEventListener('click', () => {
                const month = date.getMonth() + 1;
                const day = date.getDate();
                updateUrl('day', year, month, day);
                loadDayView(year, month, day);
            });
        }
        
        cells.appendChild(cell);
    }
    
    container.appendChild(cells);
    
    // Add legend
    const legend = document.createElement('div');
    legend.className = 'heatmap-legend';
    legend.innerHTML = `
        <span>Less</span>
        <div class="legend-cell level-0"></div>
        <div class="legend-cell level-1"></div>
        <div class="legend-cell level-2"></div>
        <div class="legend-cell level-3"></div>
        <div class="legend-cell level-4"></div>
        <span>More</span>
    `;
    container.appendChild(legend);
}

/**
 * Render months grid for year view
 */
function renderMonthsGrid(container, year) {
    MONTH_NAMES.forEach((monthName, i) => {
        const month = i + 1;
        const monthCard = document.createElement('a');
        monthCard.className = 'month-card';
        monthCard.href = `/timeline/${year}/${month}`;
        monthCard.innerHTML = `
            <span class="month-name">${monthName}</span>
        `;
        
        monthCard.addEventListener('click', (e) => {
            e.preventDefault();
            updateUrl('month', year, month);
            loadMonthView(year, month);
        });
        
        container.appendChild(monthCard);
    });
}

/**
 * Load and render a specific month view
 */
async function loadMonthView(year, month) {
    if (state.loading) return;
    state.loading = true;
    state.view = 'month';
    state.year = year;
    state.month = month;
    
    showLoading();
    updateBreadcrumbs('month', year, month);
    
    try {
        const response = await fetch(`/api/timeline/month/${year}/${month}`);
        const data = await response.json();
        
        renderMonthView(year, month, data);
    } catch (error) {
        console.error('Error loading month:', error);
        showError('Failed to load month data');
    } finally {
        state.loading = false;
    }
}

/**
 * Render month calendar view
 */
function renderMonthView(year, month, data) {
    const template = elements.templates.month.content.cloneNode(true);
    
    // Update header
    template.querySelector('.month-title').textContent = `${MONTH_NAMES[month - 1]} ${year}`;
    
    // Setup navigation
    const prevBtn = template.querySelector('#prev-month');
    const nextBtn = template.querySelector('#next-month');
    
    prevBtn.addEventListener('click', () => {
        let newMonth = month - 1;
        let newYear = year;
        if (newMonth < 1) {
            newMonth = 12;
            newYear--;
        }
        updateUrl('month', newYear, newMonth);
        loadMonthView(newYear, newMonth);
    });
    
    nextBtn.addEventListener('click', () => {
        let newMonth = month + 1;
        let newYear = year;
        if (newMonth > 12) {
            newMonth = 1;
            newYear++;
        }
        updateUrl('month', newYear, newMonth);
        loadMonthView(newYear, newMonth);
    });
    
    // Render calendar days
    const calendarDays = template.querySelector('#calendar-days');
    renderCalendarDays(calendarDays, year, month, data.days);
    
    elements.view.innerHTML = '';
    elements.view.appendChild(template);
}

/**
 * Render calendar day cells
 */
function renderCalendarDays(container, year, month, dayData) {
    // Get first day of month and number of days
    const firstDay = new Date(year, month - 1, 1);
    const startDayOfWeek = firstDay.getDay(); // 0 = Sunday
    const daysInMonth = new Date(year, month, 0).getDate();
    
    // Add empty cells for days before month starts
    for (let i = 0; i < startDayOfWeek; i++) {
        const empty = document.createElement('div');
        empty.className = 'calendar-day empty';
        container.appendChild(empty);
    }
    
    // Add day cells
    for (let day = 1; day <= daysInMonth; day++) {
        const dayCell = document.createElement('div');
        dayCell.className = 'calendar-day';
        
        const hasVideos = dayData[day] && dayData[day].count > 0;
        const count = hasVideos ? dayData[day].count : 0;
        
        if (hasVideos) {
            dayCell.classList.add('has-videos');
            dayCell.dataset.count = count;
        }
        
        dayCell.innerHTML = `
            <span class="day-number">${day}</span>
            ${hasVideos ? `<span class="day-count">${count}</span>` : ''}
        `;
        
        if (hasVideos) {
            dayCell.addEventListener('click', () => {
                updateUrl('day', year, month, day);
                loadDayView(year, month, day);
            });
        }
        
        container.appendChild(dayCell);
    }
}

/**
 * Load and render a specific day view
 */
async function loadDayView(year, month, day) {
    if (state.loading) return;
    state.loading = true;
    state.view = 'day';
    state.year = year;
    state.month = month;
    state.day = day;
    
    showLoading();
    updateBreadcrumbs('day', year, month, day);
    
    try {
        // Load day videos and "on this day" in parallel
        const [dayResponse, onThisDayResponse] = await Promise.all([
            fetch(`/api/timeline/day/${year}/${month}/${day}`),
            fetch(`/api/timeline/on-this-day?month=${month}&day=${day}&exclude_year=${year}`)
        ]);
        
        const dayData = await dayResponse.json();
        const onThisDayData = await onThisDayResponse.json();
        
        renderDayView(year, month, day, dayData, onThisDayData);
    } catch (error) {
        console.error('Error loading day:', error);
        showError('Failed to load day data');
    } finally {
        state.loading = false;
    }
}

/**
 * Render day view with videos and "on this day"
 */
function renderDayView(year, month, day, dayData, onThisDayData) {
    const template = elements.templates.day.content.cloneNode(true);
    
    // Format date nicely
    const date = new Date(year, month - 1, day);
    const dateStr = date.toLocaleDateString('en-US', { 
        weekday: 'long', 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
    });
    
    template.querySelector('.day-title').textContent = dateStr;
    
    // Setup navigation
    const prevBtn = template.querySelector('#prev-day');
    const nextBtn = template.querySelector('#next-day');
    
    prevBtn.addEventListener('click', () => {
        const prevDate = new Date(year, month - 1, day - 1);
        updateUrl('day', prevDate.getFullYear(), prevDate.getMonth() + 1, prevDate.getDate());
        loadDayView(prevDate.getFullYear(), prevDate.getMonth() + 1, prevDate.getDate());
    });
    
    nextBtn.addEventListener('click', () => {
        const nextDate = new Date(year, month - 1, day + 1);
        updateUrl('day', nextDate.getFullYear(), nextDate.getMonth() + 1, nextDate.getDate());
        loadDayView(nextDate.getFullYear(), nextDate.getMonth() + 1, nextDate.getDate());
    });
    
    // Render videos
    const videosContainer = template.querySelector('#day-videos');
    if (dayData.videos.length === 0) {
        videosContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🎬</div>
                <p>No videos for this date</p>
            </div>
        `;
    } else {
        const grid = document.createElement('div');
        grid.className = 'video-grid';
        
        dayData.videos.forEach(video => {
            const card = createVideoCard(video);
            grid.appendChild(card);
        });
        
        videosContainer.appendChild(grid);
    }
    
    // Render "On This Day" section
    const onThisDayContainer = template.querySelector('#on-this-day-content');
    if (onThisDayData.total === 0) {
        onThisDayContainer.innerHTML = '<p class="empty-hint">No videos from this day in other years</p>';
    } else {
        const yearsList = document.createElement('div');
        yearsList.className = 'on-this-day-years';
        
        Object.entries(onThisDayData.by_year).sort((a, b) => b[0] - a[0]).forEach(([year, videos]) => {
            const yearSection = document.createElement('div');
            yearSection.className = 'on-this-day-year';
            
            const yearHeader = document.createElement('div');
            yearHeader.className = 'on-this-day-year-header';
            yearHeader.innerHTML = `
                <span class="year-label">${year}</span>
                <span class="year-count">${videos.length} clip${videos.length !== 1 ? 's' : ''}</span>
            `;
            yearSection.appendChild(yearHeader);
            
            const thumbs = document.createElement('div');
            thumbs.className = 'on-this-day-thumbs';
            
            videos.slice(0, 4).forEach(video => {
                const thumb = document.createElement('a');
                thumb.className = 'timeline-thumb';
                thumb.href = `/video/${video.id}`;
                
                if (video.thumbnail_url) {
                    thumb.innerHTML = `<img src="${video.thumbnail_url}" alt="" loading="lazy">`;
                } else {
                    thumb.innerHTML = `<div class="no-thumb-sm">No thumb</div>`;
                }
                
                thumb.addEventListener('click', (e) => {
                    e.preventDefault();
                    const videoYear = parseInt(video.year);
                    const videoDate = new Date(video.creation_date);
                    updateUrl('day', videoYear, videoDate.getMonth() + 1, videoDate.getDate());
                    loadDayView(videoYear, videoDate.getMonth() + 1, videoDate.getDate());
                    window.scrollTo(0, 0);
                });
                
                thumbs.appendChild(thumb);
            });
            
            if (videos.length > 4) {
                const more = document.createElement('div');
                more.className = 'more-videos';
                more.textContent = `+${videos.length - 4} more`;
                thumbs.appendChild(more);
            }
            
            yearSection.appendChild(thumbs);
            yearsList.appendChild(yearSection);
        });
        
        onThisDayContainer.appendChild(yearsList);
    }
    
    elements.view.innerHTML = '';
    elements.view.appendChild(template);
}

/**
 * Create a video card element
 */
function createVideoCard(video) {
    const card = document.createElement('a');
    card.className = 'video-card';
    card.href = `/video/${video.id}`;
    
    const duration = video.duration_seconds ? 
        `${Math.floor(video.duration_seconds / 60)}:${String(Math.floor(video.duration_seconds % 60)).padStart(2, '0')}` : 
        '--:--';
    
    let tagsHtml = '';
    if (video.tags) {
        try {
            const tags = JSON.parse(video.tags);
            if (Array.isArray(tags) && tags.length > 0) {
                tagsHtml = `<div class="card-tags">${tags.slice(0, 3).map(t => `<span class="tag">${t}</span>`).join('')}</div>`;
            }
        } catch (e) {
            // Ignore parse errors
        }
    }
    
    card.innerHTML = `
        <div class="card-thumb">
            ${video.thumbnail_url ? 
                `<img src="${video.thumbnail_url}" alt="" loading="lazy">` : 
                `<div class="no-thumb">No thumbnail</div>`
            }
            <span class="card-duration">${duration}</span>
            ${video.source_device ? `<span class="card-device">${video.source_device}</span>` : ''}
        </div>
        <div class="card-info">
            <div class="card-filename">${video.file_name}</div>
            ${video.scene_description ? `<div class="card-desc">${video.scene_description}</div>` : ''}
            ${tagsHtml}
            <div class="card-meta">
                ${video.resolution || ''} ${video.width && video.height ? `(${video.width}x${video.height})` : ''}
            </div>
        </div>
    `;
    
    return card;
}

/**
 * Show loading state
 */
function showLoading() {
    elements.view.innerHTML = '<div class="timeline-loading">Loading...</div>';
}

/**
 * Show error state
 */
function showError(message) {
    elements.view.innerHTML = `
        <div class="timeline-error">
            <div class="error-icon">⚠️</div>
            <p>${message}</p>
            <button onclick="loadYearsView()" class="btn-secondary">Back to Years</button>
        </div>
    `;
}
