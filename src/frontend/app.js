// Global State
let selectedTemplateId = null;
let activeRoute = 'agent';
let currentJobId = null;
let pollInterval = null;
let allTemplates = [];
let adminJobs = [];
let adminJobPollInterval = null;
let activeAdminView = 'templates';
let agentManifest = null;

// API Host - proxied through the frontend container to avoid CORS in ECS/ALB.
const API_HOST = '/api';

document.addEventListener('DOMContentLoaded', () => {
    initRouteNavigation();
    initFileUploads();
    renderCurrentRoute();
});

// 1. Route Navigation
function initRouteNavigation() {
    window.switchTab = (tabName) => {
        navigateTo(tabName === 'admin' ? '/admin' : '/');
    };

    window.addEventListener('popstate', () => {
        renderCurrentRoute();
    });
}

function getRouteFromPath(pathname = window.location.pathname) {
    return pathname === '/admin' || pathname.startsWith('/admin/') ? 'admin' : 'agent';
}

function navigateTo(pathname) {
    if (window.location.pathname !== pathname) {
        window.history.pushState({ pathname }, '', pathname);
    }
    renderCurrentRoute(false);
}

function renderCurrentRoute(triggerLoad = true) {
    const route = getRouteFromPath();
    activeRoute = route;

    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));

    const navButton = document.getElementById(route === 'admin' ? 'nav-admin' : 'nav-agent');
    const tabPane = document.getElementById(route === 'admin' ? 'tab-admin' : 'tab-agent');

    if (navButton) navButton.classList.add('active');
    if (tabPane) tabPane.classList.add('active');

    if (!triggerLoad) {
        return;
    }

    if (route === 'admin') {
        stopAdminJobPolling();
        loadAdminTemplates();
        loadAdminJobs();
        loadAgentManifest();
        startAdminJobPolling();
    } else {
        stopAdminJobPolling();
        loadTemplates();
        loadRecentJobs();
    }
}

function switchAdminView(viewName) {
    activeAdminView = viewName;
    document.querySelectorAll('.admin-rail-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.admin-view').forEach(view => view.classList.remove('active'));

    document.getElementById(`admin-view-${viewName}-btn`).classList.add('active');
    document.getElementById(`admin-view-${viewName}`).classList.add('active');

    if (viewName === 'templates') {
        loadAdminTemplates();
    } else if (viewName === 'resumes') {
        loadAdminJobs();
    } else {
        loadAgentManifest();
    }
}

function startAdminJobPolling() {
    stopAdminJobPolling();
    adminJobPollInterval = setInterval(() => {
        if (activeRoute === 'admin') {
            loadAdminJobs(false);
            if (activeAdminView === 'templates') {
                loadAdminTemplates(false);
            }
        }
    }, 5000);
}

function stopAdminJobPolling() {
    if (adminJobPollInterval) {
        clearInterval(adminJobPollInterval);
        adminJobPollInterval = null;
    }
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatDate(value) {
    if (!value) return '-';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString();
}

function getStatusClass(status) {
    if (status === 'completed') return 'text-success';
    if (status === 'failed') return 'text-danger';
    if (status === 'processing' || status === 'waiting_for_template_selection') return 'text-warning';
    return 'text-primary';
}

function getStatusIcon(status) {
    if (status === 'completed') return 'fa-circle-check';
    if (status === 'failed') return 'fa-circle-xmark';
    if (status === 'processing') return 'fa-spinner fa-spin';
    if (status === 'waiting_for_template_selection') return 'fa-hand-pointer';
    return 'fa-clock';
}

// 2. File Uploads (Drag & Drop + Input Listeners)
function initFileUploads() {
    // Resume Agent CV Upload
    const cvZone = document.getElementById('cv-drop-zone');
    const cvInput = document.getElementById('cv-file-input');
    const cvText = document.getElementById('cv-text-input');

    cvZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        cvZone.classList.add('dragover');
    });

    cvZone.addEventListener('dragleave', () => {
        cvZone.classList.remove('dragover');
    });

    cvZone.addEventListener('drop', (e) => {
        e.preventDefault();
        cvZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            cvInput.files = e.dataTransfer.files;
            handleCVSelection(e.dataTransfer.files[0]);
        }
    });

    cvInput.addEventListener('change', () => {
        if (cvInput.files.length > 0) {
            handleCVSelection(cvInput.files[0]);
        }
    });

    cvText.addEventListener('input', () => {
        validateSubmissionForm();
    });

    // Admin Template Upload
    const tplZone = document.getElementById('template-drop-zone');
    const tplInput = document.getElementById('template-file-input');

    tplZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        tplZone.classList.add('dragover');
    });

    tplZone.addEventListener('dragleave', () => {
        tplZone.classList.remove('dragover');
    });

    tplZone.addEventListener('drop', (e) => {
        e.preventDefault();
        tplZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            tplInput.files = e.dataTransfer.files;
            uploadTemplateFile(e.dataTransfer.files[0]);
        }
    });

    tplInput.addEventListener('change', () => {
        if (tplInput.files.length > 0) {
            uploadTemplateFile(tplInput.files[0]);
        }
    });
}

function handleCVSelection(file) {
    const zone = document.getElementById('cv-drop-zone');
    zone.querySelector('.zone-primary-text').textContent = `CV Selected: ${file.name}`;
    zone.querySelector('.zone-secondary-text').textContent = `Size: ${(file.size / 1024).toFixed(1)} KB`;
    zone.querySelector('.cloud-icon').className = 'fa-solid fa-file-circle-check cloud-icon text-success';
    validateSubmissionForm();
}

function validateSubmissionForm() {
    const fileSelected = document.getElementById('cv-file-input').files.length > 0;
    const textPasted = document.getElementById('cv-text-input').value.trim().length > 0;
    const submitBtn = document.getElementById('btn-submit-job');

    // Allow submitting even if template is not pre-selected (agent will suggest and pause for selection)
    if (fileSelected || textPasted) {
        submitBtn.removeAttribute('disabled');
    } else {
        submitBtn.setAttribute('disabled', 'true');
    }
}

// 3. API Loaders - Templates
async function loadTemplates() {
    const grid = document.getElementById('agent-template-grid');
    try {
        const res = await fetch(`${API_HOST}/templates?limit=100`);
        if (!res.ok) throw new Error("Failed to load templates");
        const data = await res.json();
        allTemplates = data.templates;
        renderAgentTemplates();
    } catch (err) {
        console.error(err);
        grid.innerHTML = `<div class="loading-state text-danger"><i class="fa-solid fa-triangle-exclamation"></i><p>Error loading templates. Check backend connection.</p></div>`;
    }
}

function renderAgentTemplates() {
    const grid = document.getElementById('agent-template-grid');
    if (allTemplates.length === 0) {
        grid.innerHTML = `<div class="loading-state"><i class="fa-solid fa-folder-open"></i><p>No templates created yet. Visit Admin tab to upload some!</p></div>`;
        return;
    }

    grid.innerHTML = allTemplates.map(tpl => {
        const fieldsCount = getManifestFields(tpl).length;
        const isSelected = selectedTemplateId === tpl.template_id ? 'selected' : '';
        return `
            <div class="template-item-card ${isSelected}" onclick="selectTemplate('${escapeHtml(tpl.template_id)}')">
                <div class="template-meta-header">
                    <span class="template-title">${escapeHtml(tpl.template_name)}</span>
                    <span class="template-version">v${escapeHtml(tpl.version)}</span>
                </div>
                <div class="template-item-details">
                    <span class="template-fields-count">
                        <i class="fa-solid fa-list-check"></i> ${fieldsCount} fields in manifest
                    </span>
                </div>
            </div>
        `;
    }).join('');
}

function selectTemplate(templateId) {
    selectedTemplateId = templateId;
    renderAgentTemplates();
    validateSubmissionForm();
}

function filterTemplates() {
    const query = document.getElementById('template-search').value.toLowerCase();
    const cards = document.querySelectorAll('#agent-template-grid .template-item-card');

    cards.forEach((card, idx) => {
        const tplName = allTemplates[idx].template_name.toLowerCase();
        if (tplName.includes(query)) {
            card.classList.remove('hidden');
        } else {
            card.classList.add('hidden');
        }
    });
}

// 4. Job Submission & Polling
async function submitResumeJob() {
    const fileInput = document.getElementById('cv-file-input');
    const textInput = document.getElementById('cv-text-input');
    const submitBtn = document.getElementById('btn-submit-job');

    submitBtn.setAttribute('disabled', 'true');
    submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Submitting...`;

    try {
        let res;
        if (fileInput.files.length > 0) {
            // Multipart Form upload
            const formData = new FormData();
            if (selectedTemplateId) {
                formData.append('template_id', selectedTemplateId);
            }
            formData.append('file', fileInput.files[0]);

            res = await fetch(`${API_HOST}/format`, {
                method: 'POST',
                body: formData
            });
        } else {
            // Paste Text JSON upload
            const payload = {
                resume_text: textInput.value.trim()
            };
            if (selectedTemplateId) {
                payload.template_id = selectedTemplateId;
            }
            res = await fetch(`${API_HOST}/format`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }

        if (!res.ok) throw new Error("Format submission failed");

        const data = await res.json();
        currentJobId = data.job_id;

        // Show Pipeline interface
        showPipeline(currentJobId);
        pollJobStatus();

    } catch (err) {
        console.error(err);
        alert("Failed to submit formatting job: " + err.message);
    } finally {
        submitBtn.removeAttribute('disabled');
        submitBtn.innerHTML = `<i class="fa-solid fa-bolt"></i> Generate Formatted Resume`;
    }
}

function showPipeline(jobId) {
    const card = document.getElementById('pipeline-card');
    card.classList.remove('hidden');
    document.getElementById('pipeline-job-id').textContent = jobId;

    // Reset stages
    document.querySelectorAll('.stage-node').forEach(node => {
        node.className = 'stage-node';
    });
    document.querySelectorAll('.stage-connector').forEach(c => {
        c.className = 'stage-connector';
    });

    document.getElementById('stage-queued').classList.add('active');
    document.getElementById('status-message').textContent = 'Job received and queued in broker...';
    document.getElementById('result-box').classList.add('hidden');
    document.getElementById('extracted-fields-viewer').classList.add('hidden');
    document.getElementById('fields-grid-container').classList.add('hidden');
    document.getElementById('fields-chevron').className = 'fa-solid fa-chevron-down';

    // Scroll pipeline card into view
    card.scrollIntoView({ behavior: 'smooth' });
}

function pollJobStatus(isManual = false) {
    if (pollInterval) clearInterval(pollInterval);

    const fetchStatus = async () => {
        try {
            const res = await fetch(`${API_HOST}/jobs/${currentJobId}`);
            if (!res.ok) return;
            const job = await res.json();

            updatePipelineUI(job);

            if (job.status === 'completed' || job.status === 'failed') {
                clearInterval(pollInterval);
                loadRecentJobs();
            }
        } catch (e) {
            console.error("Polling error", e);
        }
    };

    fetchStatus();
    if (!isManual) {
        pollInterval = setInterval(fetchStatus, 3000);
    }
}

function updatePipelineUI(job) {
    const statusMsg = document.getElementById('status-message');
    const dot = document.getElementById('status-dot');

    // Stage Nodes
    const sq = document.getElementById('stage-queued');
    const sp = document.getElementById('stage-processing');
    const sc = document.getElementById('stage-completed');

    // Connectors
    const cq = document.getElementById('connector-queued');
    const cp = document.getElementById('connector-processing');

    // Reset selection box visibility
    const selectionBox = document.getElementById('selection-box');
    selectionBox.classList.add('hidden');

    if (job.status === 'queued') {
        sq.className = 'stage-node active';
        sp.className = 'stage-node';
        sc.className = 'stage-node';
        cq.className = 'stage-connector';
        cp.className = 'stage-connector';
        statusMsg.textContent = 'Job waiting in pipeline queue...';
    } else if (job.status === 'processing') {
        sq.className = 'stage-node completed';
        sp.className = 'stage-node active';
        sc.className = 'stage-node';
        cq.className = 'stage-connector completed';
        cp.className = 'stage-connector';
        statusMsg.textContent = 'Agent is reading candidate details & injecting variables XML-level...';
    } else if (job.status === 'waiting_for_template_selection') {
        sq.className = 'stage-node completed';
        sp.className = 'stage-node active';
        sc.className = 'stage-node';
        cq.className = 'stage-connector completed';
        cp.className = 'stage-connector';
        statusMsg.textContent = 'Paused: Please select a corporate template below to continue.';
        dot.className = 'status-dot pulsing';

        // Populate and show the selection box
        const select = document.getElementById('pipeline-template-select');
        select.innerHTML = '<option value="" disabled selected>-- Select a Template --</option>';

        // Load all available templates into the select dropdown
        allTemplates.forEach(t => {
            select.innerHTML += `<option value="${escapeHtml(t.template_id)}">${escapeHtml(t.template_name)} (v${escapeHtml(t.version)})</option>`;
        });

        selectionBox.classList.remove('hidden');
    } else if (job.status === 'completed') {
        sq.className = 'stage-node completed';
        sp.className = 'stage-node completed';
        sc.className = 'stage-node completed';
        cq.className = 'stage-connector completed';
        cp.className = 'stage-connector completed';
        dot.className = 'status-dot';
        statusMsg.textContent = 'Completed successfully!';

        // Show Download Result Box
        const resultBox = document.getElementById('result-box');
        resultBox.classList.remove('hidden');
        document.getElementById('btn-download-resume').href = `${API_HOST}/jobs/${job.job_id}/download`;

        // Display Extracted Variables table
        if (job.extracted_data) {
            displayExtractedFields(job.extracted_data);
        }
    } else if (job.status === 'failed') {
        sq.className = 'stage-node completed';
        sp.className = 'stage-node completed';
        sc.className = 'stage-node failed';
        cq.className = 'stage-connector completed';
        cp.className = 'stage-connector';
        dot.className = 'status-dot';
        statusMsg.innerHTML = `<span class="text-danger">Pipeline failed: ${job.error || 'Unknown rendering error'}</span>`;
    }
}

// Handler to resume job processing after selecting a template in the paused pipeline state
async function confirmTemplateSelection() {
    const select = document.getElementById('pipeline-template-select');
    const selectedId = select.value;
    if (!selectedId) {
        alert("Please select a template first.");
        return;
    }

    const confirmBtn = document.getElementById('btn-confirm-selection');
    confirmBtn.setAttribute('disabled', 'true');
    confirmBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Resuming...`;

    try {
        const res = await fetch(`${API_HOST}/jobs/${currentJobId}/select-template`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ template_id: selectedId })
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to resume formatting job.");
        }

        // Hide selection box, show pulsing queued state, and restart polling!
        document.getElementById('selection-box').classList.add('hidden');
        showPipeline(currentJobId);
        pollJobStatus();
    } catch (e) {
        console.error(e);
        alert("Failed to confirm template selection: " + e.message);
    } finally {
        confirmBtn.removeAttribute('disabled');
        confirmBtn.innerHTML = `<i class="fa-solid fa-circle-check"></i> Confirm & Process`;
    }
}

function displayExtractedFields(data) {
    const viewer = document.getElementById('extracted-fields-viewer');
    const tbody = document.getElementById('extracted-fields-body');

    viewer.classList.remove('hidden');
    tbody.innerHTML = '';

    Object.keys(data).forEach(key => {
        let val = data[key];
        let valStr = '';
        let typeStr = 'Scalar';

        if (Array.isArray(val)) {
            typeStr = 'Array/List';
            valStr = escapeHtml(`[${val.length} items] ${JSON.stringify(val)}`);
        } else if (typeof val === 'object' && val !== null) {
            typeStr = 'Object';
            valStr = escapeHtml(JSON.stringify(val));
        } else {
            valStr = val !== null && val !== undefined ? escapeHtml(String(val)) : '<span class="text-muted">empty</span>';
        }

        tbody.innerHTML += `
            <tr>
                <td><strong>${escapeHtml(key)}</strong></td>
                <td><span class="badge">${typeStr}</span></td>
                <td>${valStr}</td>
            </tr>
        `;
    });
}

function toggleExtractedFields() {
    const container = document.getElementById('fields-grid-container');
    const chevron = document.getElementById('fields-chevron');

    if (container.classList.contains('hidden')) {
        container.classList.remove('hidden');
        chevron.classList.add('rotated');
    } else {
        container.classList.add('hidden');
        chevron.classList.remove('rotated');
    }
}

// 5. Recent Jobs Logs
async function loadRecentJobs() {
    const tbody = document.getElementById('recent-jobs-body');
    try {
        const res = await fetch(`${API_HOST}/jobs?limit=10`);
        if (!res.ok) return;
        const data = await res.json();

        const resumeJobs = (data.jobs || []).filter(job => job.job_type === 'resume_format');
        if (resumeJobs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No formatting jobs have been executed yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = resumeJobs.map(job => {
            const statusBadgeClass = getStatusClass(job.status);
            const statusIcon = getStatusIcon(job.status);
            const cvLabel = job.resume_object_key ? job.resume_object_key.split('/').pop() : 'Pasted Raw Text';
            const templateName = getTemplateNameById(job.template_id);
            const formattedDate = formatDate(job.created_at);

            let actionBtn = '';
            if (job.status === 'completed') {
                actionBtn = `<a href="${API_HOST}/jobs/${escapeHtml(job.job_id)}/download" class="btn btn-outline btn-small"><i class="fa-solid fa-download"></i> Download</a>`;
            } else {
                actionBtn = `<button class="btn btn-outline btn-small" onclick="trackExistingJob('${escapeHtml(job.job_id)}')"><i class="fa-solid fa-eye"></i> Track</button>`;
            }

            return `
                <tr>
                    <td><code class="text-primary">${escapeHtml(job.job_id.substring(0, 8))}...</code></td>
                    <td><strong class="${statusBadgeClass}"><i class="fa-solid ${statusIcon}"></i> ${escapeHtml(job.status)}</strong></td>
                    <td>${escapeHtml(cvLabel)}</td>
                    <td>${escapeHtml(templateName)}</td>
                    <td><span class="subtitle">${formattedDate}</span></td>
                    <td>${actionBtn}</td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        console.error(err);
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Error fetching pipeline history.</td></tr>`;
    }
}

function getTemplateNameById(templateId) {
    if (!templateId) return 'Not Selected';
    const found = allTemplates.find(t => t.template_id === templateId);
    return found ? found.template_name : String(templateId).substring(0, 8) + '...';
}

function trackExistingJob(jobId) {
    currentJobId = jobId;
    showPipeline(currentJobId);
    pollJobStatus();
}

// 6. Admin Panel - Template catalog, uploads, and resume jobs
async function loadAdminTemplates(showLoading = true) {
    const list = document.getElementById('admin-template-list');
    const summary = document.getElementById('admin-template-summary');

    if (showLoading) {
        list.innerHTML = `<div class="loading-state"><i class="fa-solid fa-spinner fa-spin"></i><p>Loading template registry...</p></div>`;
    }

    try {
        const res = await fetch(`${API_HOST}/templates?limit=100`);
        if (!res.ok) throw new Error("Failed to load templates");
        const data = await res.json();
        allTemplates = data.templates || [];
        renderAdminTemplateSummary(summary);
        renderAdminTemplateList(list);
    } catch (err) {
        console.error(err);
        list.innerHTML = `<div class="loading-state text-danger"><i class="fa-solid fa-triangle-exclamation"></i><p>Failed to query template catalog.</p></div>`;
    }
}

function renderAdminTemplateSummary(summary) {
    if (!summary) return;

    const totalTemplates = allTemplates.length;
    const totalFields = allTemplates.reduce((sum, tpl) => sum + getManifestFields(tpl).length, 0);
    const readyTemplates = allTemplates.filter(tpl => getManifestFields(tpl).length > 0).length;

    summary.innerHTML = `
        <div class="stat-pill"><span class="stat-num">${totalTemplates}</span><span class="stat-label">Templates</span></div>
        <div class="stat-pill"><span class="stat-num">${totalFields}</span><span class="stat-label">Manifest Fields</span></div>
        <div class="stat-pill"><span class="stat-num">${readyTemplates}</span><span class="stat-label">Ready</span></div>
    `;
}

function renderAdminTemplateList(list) {
    if (allTemplates.length === 0) {
        list.innerHTML = `<div class="loading-state"><i class="fa-solid fa-folder-open"></i><p>No templates registered yet. Use Add New Template to upload your first template.</p></div>`;
        return;
    }

    list.innerHTML = allTemplates.map(tpl => {
        const fields = getManifestFields(tpl);
        const statusLabel = fields.length > 0 ? 'Manifest Ready' : 'Analysis Pending';
        const statusClass = fields.length > 0 ? 'text-success' : 'text-warning';
        return `
            <div class="admin-template-item">
                <div class="admin-item-info">
                    <i class="fa-solid fa-file-word admin-file-icon"></i>
                    <div>
                        <span class="admin-item-title">${escapeHtml(tpl.template_name)}</span>
                        <div class="admin-item-subtitle">ID: ${escapeHtml(tpl.template_id)} · Version: ${escapeHtml(tpl.version)} · <span class="${statusClass}">${statusLabel}</span></div>
                        <div class="admin-item-subtitle">Object: ${escapeHtml(tpl.object_key || '-')}</div>
                    </div>
                </div>
                <div class="admin-item-actions">
                    <span class="badge"><i class="fa-solid fa-list-check"></i> ${fields.length} fields</span>
                    <button class="btn btn-primary btn-small" onclick="inspectManifest('${escapeHtml(tpl.template_id)}')">
                        <i class="fa-solid fa-pen-to-square"></i> Edit / Details
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

async function loadAdminJobs(showLoading = true) {
    const progressList = document.getElementById('template-upload-progress-list');
    const resumeBody = document.getElementById('admin-resume-jobs-body');

    if (showLoading) {
        if (progressList) progressList.innerHTML = `<div class="loading-state"><i class="fa-solid fa-spinner fa-spin"></i><p>Loading template analysis jobs...</p></div>`;
        if (resumeBody) resumeBody.innerHTML = `<tr><td colspan="7" class="text-center">Loading formatted resume jobs...</td></tr>`;
    }

    try {
        const res = await fetch(`${API_HOST}/jobs?limit=100`);
        if (!res.ok) throw new Error("Failed to load jobs");
        const data = await res.json();
        adminJobs = data.jobs || [];
        renderTemplateAnalysisJobs(progressList);
        renderAdminResumeJobs(resumeBody);
    } catch (err) {
        console.error(err);
        if (progressList) progressList.innerHTML = `<div class="loading-state text-danger"><i class="fa-solid fa-triangle-exclamation"></i><p>Unable to load upload progress.</p></div>`;
        if (resumeBody) resumeBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">Unable to load resume jobs.</td></tr>`;
    }
}

function renderTemplateAnalysisJobs(container) {
    if (!container) return;

    const templateJobs = adminJobs.filter(job => job.job_type === 'template_analysis');
    if (templateJobs.length === 0) {
        container.innerHTML = `<div class="loading-state"><i class="fa-solid fa-inbox"></i><p>No template analysis jobs yet. Upload a DOCX to start parsing.</p></div>`;
        return;
    }

    container.innerHTML = templateJobs.map(job => {
        const cls = getStatusClass(job.status);
        const icon = getStatusIcon(job.status);
        return `
            <div class="progress-job-card">
                <div class="progress-job-main">
                    <span class="status-orb ${job.status}"><i class="fa-solid ${icon}"></i></span>
                    <div>
                        <strong>${escapeHtml(job.job_id)}</strong>
                        <p class="subtitle">Template manifest analysis · Updated ${formatDate(job.updated_at)}</p>
                    </div>
                </div>
                <div class="progress-job-side">
                    <span class="${cls}">${escapeHtml(job.status)}</span>
                    ${job.error ? `<small class="text-danger">${escapeHtml(job.error)}</small>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function renderAdminResumeJobs(tbody) {
    if (!tbody) return;

    const resumeJobs = adminJobs.filter(job => job.job_type === 'resume_format');
    if (resumeJobs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">No resume formatting jobs found.</td></tr>`;
        return;
    }

    tbody.innerHTML = resumeJobs.map(job => {
        const cls = getStatusClass(job.status);
        const icon = getStatusIcon(job.status);
        const source = job.resume_object_key ? job.resume_object_key.split('/').pop() : 'Pasted Raw Text';
        const templateName = getTemplateNameById(job.template_id);
        const output = job.output_object_key ? job.output_object_key.split('/').pop() : 'Not available yet';
        const action = job.status === 'completed'
            ? `<a href="${API_HOST}/jobs/${escapeHtml(job.job_id)}/download" class="btn btn-success btn-small"><i class="fa-solid fa-download"></i> Download</a>`
            : `<button class="btn btn-outline btn-small" onclick="trackExistingJobFromAdmin('${escapeHtml(job.job_id)}')"><i class="fa-solid fa-eye"></i> Track</button>`;

        return `
            <tr>
                <td><code class="text-primary">${escapeHtml(job.job_id.substring(0, 8))}...</code></td>
                <td><strong class="${cls}"><i class="fa-solid ${icon}"></i> ${escapeHtml(job.status)}</strong></td>
                <td>${escapeHtml(source)}</td>
                <td>${escapeHtml(templateName)}</td>
                <td><span class="subtitle">${escapeHtml(output)}</span></td>
                <td><span class="subtitle">${formatDate(job.updated_at)}</span></td>
                <td>${action}</td>
            </tr>
        `;
    }).join('');
}

async function loadAgentManifest() {
    const toolList = document.getElementById('agent-tool-list');
    const raw = document.getElementById('agent-manifest-raw');
    const openapiUrl = document.getElementById('agent-openapi-url');
    const manifestUrl = document.getElementById('agent-manifest-url');
    const protocols = document.getElementById('agent-protocols');

    if (toolList) {
        toolList.innerHTML = `<div class="loading-state"><i class="fa-solid fa-spinner fa-spin"></i><p>Loading agent manifest...</p></div>`;
    }

    try {
        const res = await fetch(`${API_HOST}/.well-known/agent.json`);
        if (!res.ok) throw new Error('Failed to load agent manifest');
        agentManifest = await res.json();

        if (openapiUrl) openapiUrl.textContent = agentManifest.openapi_url || '-';
        if (manifestUrl) manifestUrl.textContent = `${API_HOST}/.well-known/agent.json`;
        if (protocols) protocols.textContent = Array.isArray(agentManifest.protocols) ? agentManifest.protocols.join(', ') : '-';
        if (raw) raw.textContent = JSON.stringify(agentManifest, null, 2);

        const tools = agentManifest.tools || [];
        if (tools.length === 0) {
            toolList.innerHTML = `<div class="loading-state"><i class="fa-solid fa-circle-info"></i><p>No tools registered.</p></div>`;
            return;
        }

        toolList.innerHTML = tools.map(tool => `
            <div class="agent-tool-card">
                <div class="agent-tool-main">
                    <strong>${escapeHtml(tool.name)}</strong>
                    <span class="subtitle">${escapeHtml(tool.description)}</span>
                    <code class="agent-tool-path">${escapeHtml(tool.method)} ${escapeHtml(tool.path)}</code>
                </div>
                <span class="badge">${escapeHtml(tool.method)}</span>
            </div>
        `).join('');
    } catch (err) {
        console.error(err);
        if (toolList) {
            toolList.innerHTML = `<div class="loading-state text-danger"><i class="fa-solid fa-triangle-exclamation"></i><p>Failed to load agent discovery metadata.</p></div>`;
        }
    }
}

async function copyAgentManifestUrl() {
    const value = `${window.location.origin}${API_HOST}/.well-known/agent.json`;
    try {
        await navigator.clipboard.writeText(value);
    } catch (err) {
        console.error(err);
    }
}

function trackExistingJobFromAdmin(jobId) {
    window.switchTab('agent');
    trackExistingJob(jobId);
}

async function uploadTemplateFile(file) {
    const zone = document.getElementById('template-drop-zone');
    const primaryText = zone.querySelector('.zone-primary-text');
    const secondaryText = zone.querySelector('.zone-secondary-text');
    const icon = zone.querySelector('.cloud-icon');

    switchAdminView('upload');
    primaryText.textContent = `Uploading: ${file.name}...`;
    secondaryText.textContent = `Sending ${((file.size || 0) / 1024).toFixed(1)} KB to template analyzer`;
    icon.className = 'fa-solid fa-spinner fa-spin cloud-icon';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch(`${API_HOST}/admin/templates`, {
            method: 'POST',
            body: formData
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to upload template");
        }

        const data = await res.json();
        primaryText.textContent = `Queued: ${file.name}`;
        secondaryText.textContent = `Analysis job ${data.analysis_job_id} is now queued`;
        icon.className = 'fa-solid fa-circle-check cloud-icon text-success';

        loadAdminTemplates(false);
        loadAdminJobs(false);
    } catch (err) {
        console.error(err);
        alert("Upload error: " + err.message);
        primaryText.textContent = `Drag & drop DOCX template here`;
        secondaryText.textContent = `Only Microsoft Word (.docx) templates are supported`;
        icon.className = 'fa-solid fa-file-circle-plus cloud-icon';
    }
}

// 7. Modal Manifest Inspector Drawer
async function inspectManifest(templateId) {
    try {
        const res = await fetch(`${API_HOST}/templates/${templateId}`);
        if (!res.ok) throw new Error("Failed to load details");
        const tpl = await res.json();
        const manifest = tpl.manifest || {};

        document.getElementById('modal-template-name').textContent = tpl.template_name || 'Untitled template';
        document.getElementById('modal-template-meta').textContent = `Template ID: ${tpl.template_id} | Version: ${tpl.version}`;
        document.getElementById('modal-template-object-key').textContent = tpl.object_key || '-';
        document.getElementById('modal-manifest-id').textContent = manifest.manifest_id || '-';
        document.getElementById('modal-manifest-created').textContent = formatDate(manifest.created_at);
        document.getElementById('modal-raw-manifest').textContent = JSON.stringify(manifest, null, 2);

        const fields = getManifestFields(tpl);

        document.getElementById('stat-total-fields').textContent = fields.length;
        document.getElementById('stat-scalar-fields').textContent = fields.filter(f => f.field_type === 'scalar').length;
        document.getElementById('stat-array-fields').textContent = fields.filter(f => f.field_type !== 'scalar').length;

        const tbody = document.getElementById('modal-fields-body');
        if (fields.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">No manifest fields detected for this template. Check analysis worker log.</td></tr>`;
        } else {
            tbody.innerHTML = fields.map(f => `
                <tr>
                    <td><strong>${escapeHtml(f.name)}</strong></td>
                    <td><span class="badge">${escapeHtml(f.field_type)}</span></td>
                    <td>${f.required ? '<span class="text-warning">Required</span>' : '<span class="text-muted">Optional</span>'}</td>
                    <td><code>${escapeHtml(f.template_token)}</code></td>
                    <td><span class="subtitle">${escapeHtml(f.source_hint || '-')}</span></td>
                </tr>
            `).join('');
        }

        document.getElementById('modal-raw-manifest').classList.add('hidden');
        document.getElementById('manifest-modal').classList.remove('hidden');
    } catch (err) {
        alert("Error retrieving manifest details: " + err.message);
    }
}

function getManifestFields(tpl) {
    return tpl && tpl.manifest && Array.isArray(tpl.manifest.fields) ? tpl.manifest.fields : [];
}

function toggleRawManifest() {
    document.getElementById('modal-raw-manifest').classList.toggle('hidden');
}

function closeManifestModal() {
    document.getElementById('manifest-modal').classList.add('hidden');
}
