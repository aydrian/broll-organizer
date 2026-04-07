/**
 * Projects page JavaScript - handles project list, filters, and creation.
 */

document.addEventListener('DOMContentLoaded', () => {
    const projectsGrid = document.getElementById('projects-grid');
    const emptyState = document.getElementById('empty-state');
    const statusFilter = document.getElementById('status-filter');
    const aspectFilter = document.getElementById('aspect-filter');
    const applyFiltersBtn = document.getElementById('apply-filters');
    const createProjectBtn = document.getElementById('create-project-btn');
    const createProjectBtnEmpty = document.getElementById('create-project-btn-empty');
    const createModal = document.getElementById('create-modal');
    const createForm = document.getElementById('create-project-form');
    const closeModalBtn = createModal.querySelector('.close-btn');
    const cancelCreateBtn = document.getElementById('cancel-create');

    let currentProjects = [];

    // Load projects on page load
    loadProjects();

    // Event listeners
    if (applyFiltersBtn) {
        applyFiltersBtn.addEventListener('click', loadProjects);
    }

    if (createProjectBtn) {
        createProjectBtn.addEventListener('click', showCreateModal);
    }

    if (createProjectBtnEmpty) {
        createProjectBtnEmpty.addEventListener('click', showCreateModal);
    }

    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', hideCreateModal);
    }

    if (cancelCreateBtn) {
        cancelCreateBtn.addEventListener('click', hideCreateModal);
    }

    if (createForm) {
        createForm.addEventListener('submit', handleCreateProject);
    }

    // Close modal on backdrop click
    createModal.addEventListener('click', (e) => {
        if (e.target === createModal) {
            hideCreateModal();
        }
    });

    async function loadProjects() {
        try {
            projectsGrid.innerHTML = '<div class="loading">Loading projects...</div>';

            const params = new URLSearchParams();
            if (statusFilter?.value) {
                params.append('status', statusFilter.value);
            }
            if (aspectFilter?.value) {
                params.append('aspect', aspectFilter.value);
            }

            const url = `/api/projects?${params.toString()}`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            currentProjects = data.projects || [];

            renderProjects(currentProjects);
        } catch (error) {
            console.error('Error loading projects:', error);
            projectsGrid.innerHTML = `<div class="error">Error loading projects: ${error.message}</div>`;
        }
    }

    function renderProjects(projects) {
        if (projects.length === 0) {
            projectsGrid.style.display = 'none';
            emptyState.style.display = 'block';
            return;
        }

        projectsGrid.style.display = 'grid';
        emptyState.style.display = 'none';

        projectsGrid.innerHTML = projects.map(project => {
            const statusClass = `status-${project.status}`;
            const aspectDisplay = project.aspect_ratio || 'Not set';
            const durationDisplay = project.target_duration_seconds
                ? `${project.target_duration_seconds}s`
                : 'No target';

            return `
                <article class="project-card" data-project-id="${project.id}">
                    <div class="project-header">
                        <h3 class="project-title">${escapeHtml(project.name)}</h3>
                        <span class="project-status ${statusClass}">${project.status}</span>
                    </div>
                    <div class="project-meta">
                        <span class="meta-item">
                            <span class="icon">🎬</span>
                            ${project.clip_count || 0} clips
                        </span>
                        <span class="meta-item">
                            <span class="icon">⏱️</span>
                            ${formatDuration(project.total_duration || 0)}
                        </span>
                    </div>
                    <div class="project-stats">
                        <span class="stat">
                            <strong>Aspect:</strong> ${aspectDisplay}
                        </span>
                        <span class="stat">
                            <strong>Target:</strong> ${durationDisplay}
                        </span>
                    </div>
                </article>
            `;
        }).join('');

        // Add click handlers
        document.querySelectorAll('.project-card').forEach(card => {
            card.addEventListener('click', () => {
                const projectId = card.dataset.projectId;
                window.location.href = `/projects/${projectId}`;
            });
        });
    }

    function showCreateModal() {
        createModal.style.display = 'flex';
        document.getElementById('project-name')?.focus();
    }

    function hideCreateModal() {
        createModal.style.display = 'none';
        createForm?.reset();
    }

    async function handleCreateProject(e) {
        e.preventDefault();

        const formData = new FormData(createForm);
        const data = {
            name: formData.get('name')?.trim(),
            description: formData.get('description')?.trim() || null,
            aspect_ratio: formData.get('aspect_ratio') || null,
            target_duration_seconds: formData.get('target_duration_seconds')
                ? parseInt(formData.get('target_duration_seconds'))
                : null,
            status: 'planning'
        };

        if (!data.name) {
            alert('Project name is required');
            return;
        }

        try {
            const response = await fetch('/api/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || `HTTP ${response.status}`);
            }

            const result = await response.json();

            if (result.success) {
                hideCreateModal();
                // Redirect to the new project
                window.location.href = `/projects/${result.project_id}`;
            } else {
                throw new Error('Failed to create project');
            }
        } catch (error) {
            console.error('Error creating project:', error);
            alert(`Error creating project: ${error.message}`);
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
