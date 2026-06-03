// Global State
let selectedTemplateId = null;
let activeRoute = 'agent';
let currentJobId = null;
let pollInterval = null;
let allTemplates = [];
let adminJobs = [];
let recentJobsById = {};
let adminJobPollInterval = null;
let activeAdminView = 'templates';
let agentManifest = null;
let selectedTemplateFile = null;
let templateAnalysisInterval = null;
let lastAnalyzedTemplateId = null;

// Wizard Navigation Navigation state
let currentStep = 1;

function goToStep(stepNum) {
    currentStep = stepNum;
    
    document.querySelectorAll('.step-panel').forEach(panel => {
        panel.classList.add('hidden');
    });
    const activePanel = document.getElementById(`step-panel-${stepNum}`);
    if (activePanel) activePanel.classList.remove('hidden');

    for (let i = 1; i <= 3; i++) {
        const ind = document.getElementById(`step-ind-${i}`);
        const line = document.getElementById(`step-line-${i}`);

        if (ind) {
            ind.classList.remove('active', 'completed');
            if (i < stepNum) {
                ind.classList.add('completed');
            } else if (i === stepNum) {
                ind.classList.add('active');
            }
        }

        if (line) {
            line.classList.remove('completed');
            if (i < stepNum) {
                line.classList.add('completed');
            }
        }
    }
}

window.confirmCVSelection = function() {
    const fileInput = document.getElementById('cv-file-input');
    const textInput = document.getElementById('cv-text-input');
    
    let label = 'Pasted Raw Text';
    let size = '-';
    let iconClass = 'fa-solid fa-file-circle-check cv-icon text-success';

    if (fileInput.files.length > 0) {
        const file = fileInput.files[0];
        label = file.name;
        size = `${(file.size / 1024).toFixed(1)} KB`;
        if (file.name.toLowerCase().endsWith('.pdf')) {
            iconClass = 'fa-solid fa-file-pdf cv-icon text-danger';
        } else if (file.name.toLowerCase().endsWith('.docx')) {
            iconClass = 'fa-solid fa-file-word cv-icon text-primary';
        }
    } else if (textInput.value.trim().length === 0) {
        alert("Please upload a CV file or paste the CV text first.");
        return;
    }

    document.getElementById('summary-cv-name').textContent = label;
    document.getElementById('summary-cv-size').textContent = size;
    document.getElementById('summary-cv-icon').className = iconClass;

    goToStep(2);
};

window.backToUpload = function() {
    goToStep(1);
};

window.resetWizard = function() {
    const fileInput = document.getElementById('cv-file-input');
    if (fileInput) fileInput.value = '';
    
    const textInput = document.getElementById('cv-text-input');
    if (textInput) textInput.value = '';

    const zone = document.getElementById('cv-drop-zone');
    if (zone) {
        zone.querySelector('.zone-primary-text').textContent = 'Drag & drop candidate CV here';
        zone.querySelector('.zone-secondary-text').textContent = 'Supports PDF, DOCX or TXT files';
        const icon = zone.querySelector('.cloud-icon');
        if (icon) icon.className = 'fa-solid fa-cloud-arrow-up cloud-icon';
    }

    selectedTemplateId = null;
    const searchInput = document.getElementById('template-search');
    if (searchInput) searchInput.value = '';
    
    document.querySelectorAll('.template-item-card').forEach(card => card.classList.remove('selected'));

    const summaryTplName = document.getElementById('summary-template-name');
    if (summaryTplName) summaryTplName.textContent = 'No template selected';
    const summaryTplVer = document.getElementById('summary-template-version');
    if (summaryTplVer) summaryTplVer.textContent = '-';
    const summaryTplIcon = document.getElementById('summary-template-icon');
    if (summaryTplIcon) summaryTplIcon.className = 'fa-solid fa-file-invoice cv-icon text-muted';
    
    currentJobId = null;
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }

    const pipelineCandidateCard = document.getElementById('pipeline-candidate-card');
    if (pipelineCandidateCard) pipelineCandidateCard.classList.add('hidden');
    
    const recContainer = document.getElementById('recommendations-container');
    if (recContainer) recContainer.innerHTML = '';
    
    const selectionBox = document.getElementById('selection-box');
    if (selectionBox) selectionBox.classList.add('hidden');
    
    const resultBox = document.getElementById('result-box');
    if (resultBox) resultBox.classList.add('hidden');
    
    const extractedFieldsViewer = document.getElementById('extracted-fields-viewer');
    if (extractedFieldsViewer) extractedFieldsViewer.classList.add('hidden');

    const fieldsGrid = document.getElementById('fields-grid-container');
    if (fieldsGrid) fieldsGrid.classList.add('hidden');

    const chevron = document.getElementById('fields-chevron');
    if (chevron) chevron.className = 'fa-solid fa-chevron-down';

    validateSubmissionForm();
    goToStep(1);
};

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
    renderCurrentRoute();
}

function renderCurrentRoute(triggerLoad = true) {
    const route = getRouteFromPath();
    activeRoute = route;

    document.body.classList.toggle('route-agent', route === 'agent');
    document.body.classList.toggle('route-admin', route === 'admin');

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

function getSourceClassificationLabel(value) {
    const normalized = value || 'resume_fact';
    const labels = {
        resume_fact: 'resume_fact',
        generated: 'generated',
        recruiter_input: 'recruiter_input',
        ats_input: 'ats_input',
        input_only: 'input_only'
    };
    return labels[normalized] || normalized;
}

function renderFieldPreviewList(fields, limit = 10) {
    if (!fields.length) {
        return `<div class="admin-field-empty">No manifest fields detected yet.</div>`;
    }

    const visibleFields = fields.slice(0, limit);
    const remainder = fields.length - visibleFields.length;

    const fieldChips = visibleFields.map(field => `
        <span class="admin-field-chip">
            <strong>${escapeHtml(field.name)}</strong>
            <span class="admin-field-chip-meta">${escapeHtml(getSourceClassificationLabel(field.source_classification))}</span>
        </span>
    `).join('');

    const overflow = remainder > 0
        ? `<span class="admin-field-chip admin-field-chip-more">+${remainder} more</span>`
        : '';

    return `<div class="admin-field-chip-list">${fieldChips}${overflow}</div>`;
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

    // Modal Template Upload
    const modalTplZone = document.getElementById('modal-template-drop-zone');
    const modalTplInput = document.getElementById('modal-template-file-input');

    if (modalTplZone && modalTplInput) {
        modalTplZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            modalTplZone.classList.add('dragover');
        });

        modalTplZone.addEventListener('dragleave', () => {
            modalTplZone.classList.remove('dragover');
        });

        modalTplZone.addEventListener('drop', (e) => {
            e.preventDefault();
            modalTplZone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                const file = e.dataTransfer.files[0];
                if (validateTemplateFile(file)) {
                    modalTplInput.files = e.dataTransfer.files;
                    handleModalTemplateSelection(file);
                }
            }
        });

        modalTplInput.addEventListener('change', () => {
            if (modalTplInput.files.length > 0) {
                const file = modalTplInput.files[0];
                if (validateTemplateFile(file)) {
                    handleModalTemplateSelection(file);
                }
            }
        });
    }
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
    
    // Enable Step 1 Next button
    const nextBtn = document.getElementById('btn-next-to-template');
    if (nextBtn) {
        if (fileSelected || textPasted) {
            nextBtn.removeAttribute('disabled');
        } else {
            nextBtn.setAttribute('disabled', 'true');
        }
    }

    // Enable Step 2 Generate button
    const submitBtn = document.getElementById('btn-submit-job');
    if (submitBtn) {
        if (selectedTemplateId) {
            submitBtn.removeAttribute('disabled');
        } else {
            submitBtn.setAttribute('disabled', 'true');
        }
    }
}

// 3. API Loaders - Templates
async function loadTemplates() {
    const grid = document.getElementById('agent-template-grid');
    try {
        const res = await fetch(`${API_HOST}/templates?limit=100`);
        if (!res.ok) throw new Error("Failed to load templates");
        const data = await res.json();
        allTemplates = sortTemplatesLatestFirst(data.templates);
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

    const tpl = allTemplates.find(t => t.template_id === templateId);
    if (tpl) {
        const summaryTplName = document.getElementById('summary-template-name');
        if (summaryTplName) summaryTplName.textContent = tpl.template_name;
        
        const summaryTplVer = document.getElementById('summary-template-version');
        if (summaryTplVer) summaryTplVer.textContent = `Version ${tpl.version}`;
        
        const summaryTplIcon = document.getElementById('summary-template-icon');
        if (summaryTplIcon) {
            summaryTplIcon.className = 'fa-solid fa-file-signature cv-icon text-success animate-bounce-once';
        }
    } else {
        const summaryTplName = document.getElementById('summary-template-name');
        if (summaryTplName) summaryTplName.textContent = 'No template selected';
        
        const summaryTplVer = document.getElementById('summary-template-version');
        if (summaryTplVer) summaryTplVer.textContent = '-';
        
        const summaryTplIcon = document.getElementById('summary-template-icon');
        if (summaryTplIcon) {
            summaryTplIcon.className = 'fa-solid fa-file-invoice cv-icon text-muted';
        }
    }
}

function filterTemplates() {
    const query = document.getElementById('template-search').value.toLowerCase();
    const cards = document.querySelectorAll('#agent-template-grid .template-item-card');

    cards.forEach((card, idx) => {
        const tpl = allTemplates[idx];
        const tplName = tpl.template_name.toLowerCase();
        const tplVer = 'v' + String(tpl.version);
        if (tplName.includes(query) || tplVer.includes(query)) {
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
    goToStep(3);
    
    const jobIdLabel = document.getElementById('pipeline-job-id-lbl');
    if (jobIdLabel) jobIdLabel.textContent = `Job ID: ${jobId}`;

    // Reset stages
    document.querySelectorAll('#step-panel-3 .stage-node').forEach(node => {
        node.className = 'stage-node';
    });
    document.querySelectorAll('#step-panel-3 .stage-connector').forEach(c => {
        c.className = 'stage-connector';
    });

    document.getElementById('stage-queued').classList.add('active');
    document.getElementById('status-message').textContent = 'Job received and queued in broker...';
    document.getElementById('result-box').classList.add('hidden');
    document.getElementById('extracted-fields-viewer').classList.add('hidden');
    document.getElementById('fields-grid-container').classList.add('hidden');
    document.getElementById('fields-chevron').className = 'fa-solid fa-chevron-down';

    // Scroll to top of card
    const card = document.querySelector('.agent-workspace-card');
    if (card) card.scrollIntoView({ behavior: 'smooth' });
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

    // Candidate Profile Card Display Logic
    const candCard = document.getElementById('pipeline-candidate-card');
    if (job.resume_summary) {
        candCard.classList.remove('hidden');
        document.getElementById('candidate-card-summary').textContent = job.resume_summary;

        // Try to retrieve name, town, and skills from extracted_data if present
        let candName = 'Candidate Profile';
        let candLocation = 'Unknown Location';
        let skillsHtml = '';

        if (job.extracted_data) {
            const data = job.extracted_data;
            const nameKey = Object.keys(data).find(k => k.includes('name'));
            if (nameKey && data[nameKey]) candName = data[nameKey];

            const locKey = Object.keys(data).find(k => k.includes('town') || k.includes('city') || k.includes('location'));
            if (locKey && data[locKey]) candLocation = data[locKey];

            const skillsKey = Object.keys(data).find(k => k.includes('skills'));
            if (skillsKey && data[skillsKey]) {
                let skills = [];
                const val = data[skillsKey];
                if (typeof val === 'string') {
                    skills = val.split(/[,;&]|\s{2,}/).map(s => s.trim()).filter(s => s.length > 0);
                } else if (Array.isArray(val)) {
                    skills = val;
                }
                skillsHtml = skills.slice(0, 10).map(s => `<span class="skill-tag">${escapeHtml(s)}</span>`).join('');
            }
        }

        document.getElementById('candidate-card-name').textContent = candName;
        document.getElementById('candidate-card-location').innerHTML = `<i class="fa-solid fa-location-dot"></i> ${escapeHtml(candLocation)}`;
        
        const skillsContainer = document.getElementById('candidate-card-skills');
        if (skillsHtml) {
            skillsContainer.innerHTML = skillsHtml;
            skillsContainer.parentElement.classList.remove('hidden');
        } else {
            skillsContainer.parentElement.classList.add('hidden');
        }
    } else {
        candCard.classList.add('hidden');
    }

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

        // Render the recommended template cards grid
        const recContainer = document.getElementById('recommendations-container');
        recContainer.innerHTML = '';

        const suggested = job.suggested_templates || [];
        if (suggested.length === 0) {
            // Render all templates from database as standard options
            if (allTemplates.length === 0) {
                recContainer.innerHTML = '<div class="loading-state text-warning"><i class="fa-solid fa-circle-info"></i><p>No formatting templates available. Please upload one in the Admin Area.</p></div>';
            } else {
                recContainer.innerHTML = allTemplates.map(tpl => {
                    const fieldsCount = getManifestFields(tpl).length;
                    return `
                        <div class="recommendation-card" onclick="selectRecommendedTemplate(this, '${escapeHtml(tpl.template_id)}')">
                            <div class="rec-header">
                                <span class="rec-title">${escapeHtml(tpl.template_name)}</span>
                                <span class="rec-score-badge rec-score-medium">Standard</span>
                            </div>
                            <p class="rec-reason">Hays standard formatting template. Fits most professional CV profiles.</p>
                            <div class="rec-meta">
                                <span><i class="fa-solid fa-list-check"></i> ${fieldsCount} fields</span>
                                <span>· v${escapeHtml(tpl.version)}</span>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        } else {
            // Render AI recommended template cards
            recContainer.innerHTML = suggested.map(rec => {
                const foundTpl = allTemplates.find(t => t.template_id === rec.template_id);
                const fieldsCount = foundTpl ? getManifestFields(foundTpl).length : 0;
                const scoreClass = rec.match_score >= 80 ? 'rec-score-high' : 'rec-score-medium';
                const scoreText = rec.match_score >= 80 ? 'Highly Match' : 'Match';
                return `
                    <div class="recommendation-card" onclick="selectRecommendedTemplate(this, '${escapeHtml(rec.template_id)}')">
                        <div class="rec-header">
                            <span class="rec-title">${escapeHtml(rec.template_name)}</span>
                            <span class="rec-score-badge ${scoreClass}">
                                <i class="fa-solid fa-fire"></i> ${rec.match_score}% ${scoreText}
                            </span>
                        </div>
                        <p class="rec-reason">${escapeHtml(rec.reason)}</p>
                        <div class="rec-meta">
                            <span><i class="fa-solid fa-list-check"></i> ${fieldsCount} fields</span>
                            <span>· v${escapeHtml(foundTpl ? foundTpl.version : '-')}</span>
                            <span>· ID: ${escapeHtml(rec.template_id.substring(0, 8))}...</span>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // Reset selection hidden input and disable button
        document.getElementById('pipeline-template-select').value = '';
        document.getElementById('btn-confirm-selection').setAttribute('disabled', 'true');

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

        // Display Extracted Variables table grouped by manifest classification
        if (job.extracted_data) {
            displayExtractedFields(job.extracted_data, job.template_id);
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

// Global selection handler for suggested template cards
window.selectRecommendedTemplate = function(cardEl, templateId) {
    document.querySelectorAll('.recommendation-card').forEach(card => {
        card.classList.remove('selected');
    });
    cardEl.classList.add('selected');
    
    const selectEl = document.getElementById('pipeline-template-select');
    selectEl.value = templateId;
    
    const confirmBtn = document.getElementById('btn-confirm-selection');
    confirmBtn.removeAttribute('disabled');
};

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

function displayExtractedFields(data, templateId) {
    const viewer = document.getElementById('extracted-fields-viewer');
    const container = document.getElementById('fields-grid-container');

    viewer.classList.remove('hidden');
    container.innerHTML = '';

    // Find template manifest fields to map classification
    let fieldClassMap = {};
    if (templateId) {
        const found = allTemplates.find(t => t.template_id === templateId);
        if (found && found.manifest && Array.isArray(found.manifest.fields)) {
            found.manifest.fields.forEach(f => {
                fieldClassMap[f.name] = f.source_classification || 'resume_fact';
            });
        }
    }

    // Grouping buckets
    const groups = {
        'resume_fact': {
            title: 'Verifiable Resume Facts',
            icon: 'fa-solid fa-file-invoice',
            badgeClass: 'rec-score-high',
            fields: []
        },
        'generated': {
            title: 'AI Generated Insights',
            icon: 'fa-solid fa-wand-magic-sparkles',
            badgeClass: 'badge-hays',
            fields: []
        },
        'input_only': {
            title: 'Input & ATS Overrides',
            icon: 'fa-solid fa-sliders',
            badgeClass: 'rec-score-medium',
            fields: []
        }
    };

    // Distribute data keys
    Object.keys(data).forEach(key => {
        const val = data[key];
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

        let classification = fieldClassMap[key] || 'resume_fact';
        if (classification === 'recruiter_input' || classification === 'ats_input') {
            classification = 'input_only';
        }
        if (!groups[classification]) {
            classification = 'resume_fact';
        }

        groups[classification].fields.push({
            name: key,
            type: typeStr,
            sourceClassification: getSourceClassificationLabel(fieldClassMap[key] || 'resume_fact'),
            value: valStr
        });
    });

    // Render grouped cards
    let groupHtml = '';
    Object.keys(groups).forEach(gKey => {
        const grp = groups[gKey];
        if (grp.fields.length === 0) return;

        const rowsHtml = grp.fields.map(f => `
            <tr>
                <td style="width: 25%;"><strong>${escapeHtml(f.name)}</strong></td>
                <td style="width: 15%;"><span class="badge">${escapeHtml(f.type)}</span></td>
                <td style="width: 18%;"><span class="badge badge-source-hint">${escapeHtml(f.sourceClassification)}</span></td>
                <td>${f.value}</td>
            </tr>
        `).join('');

        groupHtml += `
            <div class="extracted-group-card animate-slide-down">
                <div class="extracted-group-header">
                    <span class="extracted-group-title">
                        <i class="${grp.icon}"></i> ${escapeHtml(grp.title)}
                    </span>
                    <span class="extracted-group-badge ${grp.badgeClass}">${grp.fields.length} variables</span>
                </div>
                <div class="table-container">
                    <table class="custom-table compact">
                        <thead>
                            <tr>
                                <th>Field Name</th>
                                <th>Type</th>
                                <th>Data Source Hint</th>
                                <th>Extracted Value</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rowsHtml}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    });

    container.innerHTML = groupHtml;
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
        recentJobsById = {};
        resumeJobs.forEach(job => {
            recentJobsById[job.job_id] = job;
        });
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

            const actionButtons = [];
            if (job.extracted_data) {
                actionButtons.push(`<button class="btn btn-outline btn-small" onclick="showRecentJobJson('${escapeHtml(job.job_id)}')"><i class="fa-solid fa-code"></i> View Data</button>`);
                actionButtons.push(`<button class="btn btn-outline btn-small" onclick="showJobDataMapping('${escapeHtml(job.job_id)}')"><i class="fa-solid fa-sitemap"></i> Data Mapping</button>`);
            }
            if (job.status === 'completed') {
                actionButtons.push(`<a href="${API_HOST}/jobs/${escapeHtml(job.job_id)}/download" class="btn btn-outline btn-small"><i class="fa-solid fa-download"></i> Download</a>`);
            } else {
                actionButtons.push(`<button class="btn btn-outline btn-small" onclick="trackExistingJob('${escapeHtml(job.job_id)}')"><i class="fa-solid fa-eye"></i> Track</button>`);
            }
            const actionBtn = `<div class="job-action-group">${actionButtons.join('')}</div>`;

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

function showRecentJobJson(jobId) {
    const job = recentJobsById[jobId];
    if (!job) {
        alert('Job not found in recent list. Please refresh.');
        return;
    }
    if (!job.extracted_data) {
        alert('No extracted_data is available for this job yet.');
        return;
    }

    document.getElementById('recent-job-json-title').textContent = 'Extracted Data JSON';
    document.getElementById('recent-job-json-meta').textContent = `Job ID: ${jobId} | Status: ${job.status}`;
    document.getElementById('recent-job-json-content').textContent = JSON.stringify(job.extracted_data, null, 2);
    document.getElementById('recent-job-json-modal').classList.remove('hidden');
}

function closeRecentJobJsonModal(event) {
    if (event && event.target && event.target.id !== 'recent-job-json-modal') {
        return;
    }
    document.getElementById('recent-job-json-modal').classList.add('hidden');
}

function getTemplateNameById(templateId) {
    if (!templateId) return 'Not Selected';
    const found = allTemplates.find(t => t.template_id === templateId);
    return found ? `${found.template_name} (v${found.version})` : String(templateId).substring(0, 8) + '...';
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
        allTemplates = sortTemplatesLatestFirst(data.templates || []);
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
                <div class="admin-item-main">
                    <div class="admin-item-info">
                    <i class="fa-solid fa-file-word admin-file-icon"></i>
                        <div>
                            <span class="admin-item-title">${escapeHtml(tpl.template_name)} (v${escapeHtml(tpl.version)})</span>
                            <div class="admin-item-subtitle">ID: ${escapeHtml(tpl.template_id)} · Version: ${escapeHtml(tpl.version)} · <span class="${statusClass}">${statusLabel}</span></div>
                            <div class="admin-item-subtitle">Object: ${escapeHtml(tpl.object_key || '-')}</div>
                        </div>
                    </div>
                    <div class="admin-template-fields-block">
                        <div class="admin-template-fields-header">
                            <span>Manifest field list</span>
                            <span class="subtitle">with data source hints</span>
                        </div>
                        ${renderFieldPreviewList(fields)}
                    </div>
                </div>
                <div class="admin-item-actions">
                    <span class="badge"><i class="fa-solid fa-list-check"></i> ${fields.length} fields</span>
                    <button class="btn btn-outline btn-small" onclick="showRawManifestJSON('${escapeHtml(tpl.template_id)}')">
                        <i class="fa-solid fa-code"></i> Show Raw Manifest
                    </button>
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

    // Sort descending by created_at or updated_at so that latest templates/jobs come first
    resumeJobs.sort((a, b) => new Date(b.created_at || b.updated_at) - new Date(a.created_at || a.updated_at));

    tbody.innerHTML = resumeJobs.map(job => {
        const cls = getStatusClass(job.status);
        const icon = getStatusIcon(job.status);
        const source = job.resume_object_key ? job.resume_object_key.split('/').pop() : 'Pasted Raw Text';
        const templateName = getTemplateNameById(job.template_id);
        const output = job.output_object_key ? job.output_object_key.split('/').pop() : 'Not available yet';

        const actionButtons = [];
        if (job.template_id) {
            actionButtons.push(`<button class="btn btn-outline btn-small" onclick="showRawManifestJSON('${escapeHtml(job.template_id)}')"><i class="fa-solid fa-code"></i> Manifest</button>`);
        }
        actionButtons.push(`<button class="btn btn-outline btn-small" onclick="showJobDataMapping('${escapeHtml(job.job_id)}')"><i class="fa-solid fa-sitemap"></i> Data Mapping</button>`);
        
        if (job.status === 'completed') {
            actionButtons.push(`<a href="${API_HOST}/jobs/${escapeHtml(job.job_id)}/download" class="btn btn-success btn-small"><i class="fa-solid fa-download"></i> Download</a>`);
        } else {
            actionButtons.push(`<button class="btn btn-outline btn-small" onclick="trackExistingJobFromAdmin('${escapeHtml(job.job_id)}')"><i class="fa-solid fa-eye"></i> Track</button>`);
        }

        const action = `<div class="job-action-group">${actionButtons.join('')}</div>`;

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

window.openUploadTemplateModal = function() {
    resetUploadModalState();
    document.getElementById('upload-template-modal').classList.remove('hidden');
};

window.closeUploadTemplateModal = function(event) {
    if (event && event.target && event.target.id !== 'upload-template-modal' && !event.target.closest('.btn-close')) {
        return;
    }
    document.getElementById('upload-template-modal').classList.add('hidden');
    if (templateAnalysisInterval) {
        clearInterval(templateAnalysisInterval);
        templateAnalysisInterval = null;
    }
};

function resetUploadModalState() {
    selectedTemplateFile = null;
    if (templateAnalysisInterval) {
        clearInterval(templateAnalysisInterval);
        templateAnalysisInterval = null;
    }
    
    const fileInput = document.getElementById('modal-template-file-input');
    if (fileInput) fileInput.value = '';
    
    const primaryText = document.getElementById('modal-template-primary-text');
    if (primaryText) primaryText.textContent = 'Drag & drop DOCX template here';
    const secondaryText = document.getElementById('modal-template-secondary-text');
    if (secondaryText) secondaryText.textContent = 'Only Microsoft Word (.docx) templates are supported';
    
    const zone = document.getElementById('modal-template-drop-zone');
    if (zone) {
        zone.classList.remove('dragover');
        const icon = zone.querySelector('.cloud-icon');
        if (icon) icon.className = 'fa-solid fa-file-word cloud-icon';
    }
    
    const submitBtn = document.getElementById('btn-submit-template-analysis');
    if (submitBtn) {
        submitBtn.setAttribute('disabled', 'true');
        submitBtn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Generate Template Analysis`;
    }
    
    document.getElementById('upload-modal-stage-select').classList.remove('hidden');
    document.getElementById('upload-modal-stage-progress').classList.add('hidden');
    
    document.getElementById('template-stage-queued').className = 'stage-node';
    document.getElementById('template-stage-processing').className = 'stage-node';
    document.getElementById('template-stage-completed').className = 'stage-node';
    document.getElementById('template-connector-queued').className = 'stage-connector';
    document.getElementById('template-connector-processing').className = 'stage-connector';
    
    document.getElementById('template-status-dot').className = 'status-dot';
    document.getElementById('template-status-message').textContent = 'Job received and queued...';
    document.getElementById('template-analysis-result-actions').classList.add('hidden');
}

function validateTemplateFile(file) {
    if (!file.name.toLowerCase().endsWith('.docx')) {
        alert("Only Microsoft Word (.docx) templates are supported.");
        return false;
    }
    return true;
}

function handleModalTemplateSelection(file) {
    selectedTemplateFile = file;
    const zone = document.getElementById('modal-template-drop-zone');
    const primaryText = document.getElementById('modal-template-primary-text');
    const secondaryText = document.getElementById('modal-template-secondary-text');
    const icon = zone.querySelector('.cloud-icon');
    
    primaryText.textContent = `Template Selected: ${file.name}`;
    secondaryText.textContent = `Size: ${(file.size / 1024).toFixed(1)} KB`;
    icon.className = 'fa-solid fa-file-circle-check cloud-icon text-success';
    
    const submitBtn = document.getElementById('btn-submit-template-analysis');
    submitBtn.removeAttribute('disabled');
}

async function submitTemplateAnalysis() {
    if (!selectedTemplateFile) return;
    
    const submitBtn = document.getElementById('btn-submit-template-analysis');
    submitBtn.setAttribute('disabled', 'true');
    submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Submitting...`;
    
    try {
        const formData = new FormData();
        formData.append('file', selectedTemplateFile);
        
        const res = await fetch(`${API_HOST}/admin/templates`, {
            method: 'POST',
            body: formData
        });
        
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to submit template analysis");
        }
        
        const data = await res.json();
        const jobId = data.analysis_job_id;
        
        document.getElementById('upload-modal-stage-select').classList.add('hidden');
        document.getElementById('upload-modal-stage-progress').classList.remove('hidden');
        
        pollTemplateAnalysisJob(jobId);
    } catch (err) {
        console.error(err);
        alert("Upload error: " + err.message);
        submitBtn.removeAttribute('disabled');
        submitBtn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Generate Template Analysis`;
    }
}

function pollTemplateAnalysisJob(jobId) {
    if (templateAnalysisInterval) clearInterval(templateAnalysisInterval);
    
    const sq = document.getElementById('template-stage-queued');
    const sp = document.getElementById('template-stage-processing');
    const sc = document.getElementById('template-stage-completed');
    const cq = document.getElementById('template-connector-queued');
    const cp = document.getElementById('template-connector-processing');
    const statusDot = document.getElementById('template-status-dot');
    const statusMsg = document.getElementById('template-status-message');
    
    sq.className = 'stage-node active';
    sp.className = 'stage-node';
    sc.className = 'stage-node';
    cq.className = 'stage-connector';
    cp.className = 'stage-connector';
    statusDot.className = 'status-dot pulsing';
    statusMsg.textContent = 'Template analysis queued...';
    
    const checkStatus = async () => {
        try {
            const res = await fetch(`${API_HOST}/jobs/${jobId}`);
            if (!res.ok) return;
            const job = await res.json();
            
            if (job.status === 'queued') {
                sq.className = 'stage-node active';
                sp.className = 'stage-node';
                sc.className = 'stage-node';
                cq.className = 'stage-connector';
                cp.className = 'stage-connector';
                statusDot.className = 'status-dot pulsing';
                statusMsg.textContent = 'Template analysis queued...';
            } else if (job.status === 'processing') {
                sq.className = 'stage-node completed';
                sp.className = 'stage-node active';
                sc.className = 'stage-node';
                cq.className = 'stage-connector completed';
                cp.className = 'stage-connector';
                statusDot.className = 'status-dot pulsing';
                statusMsg.textContent = 'Parsing merge fields, styles, and XML registry...';
            } else if (job.status === 'completed') {
                clearInterval(templateAnalysisInterval);
                templateAnalysisInterval = null;
                
                sq.className = 'stage-node completed';
                sp.className = 'stage-node completed';
                sc.className = 'stage-node completed';
                cq.className = 'stage-connector completed';
                cp.className = 'stage-connector completed';
                statusDot.className = 'status-dot';
                statusMsg.textContent = 'Analysis completed successfully!';
                
                lastAnalyzedTemplateId = job.template_id;
                
                document.getElementById('template-analysis-result-actions').classList.remove('hidden');
                const viewDetailsBtn = document.getElementById('btn-view-analyzed-manifest');
                if (viewDetailsBtn) viewDetailsBtn.classList.remove('hidden');
                
                loadAdminTemplates(false);
                loadAdminJobs(false);
            } else if (job.status === 'failed') {
                clearInterval(templateAnalysisInterval);
                templateAnalysisInterval = null;
                
                sq.className = 'stage-node completed';
                sp.className = 'stage-node completed';
                sc.className = 'stage-node failed';
                cq.className = 'stage-connector completed';
                cp.className = 'stage-connector';
                statusDot.className = 'status-dot';
                statusMsg.innerHTML = `<span class="text-danger">Analysis failed: ${escapeHtml(job.error || 'Unknown error')}</span>`;
                
                document.getElementById('template-analysis-result-actions').classList.remove('hidden');
                const viewDetailsBtn = document.getElementById('btn-view-analyzed-manifest');
                if (viewDetailsBtn) viewDetailsBtn.classList.add('hidden');
            }
        } catch (e) {
            console.error("Error polling template status", e);
        }
    };
    
    checkStatus();
    templateAnalysisInterval = setInterval(checkStatus, 3000);
}

window.viewAnalyzedManifest = function() {
    if (!lastAnalyzedTemplateId) return;
    closeUploadTemplateModal();
    inspectManifest(lastAnalyzedTemplateId);
};

window.resetUploadModalStage = function() {
    resetUploadModalState();
};

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
            tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No manifest fields detected for this template. Check analysis worker log.</td></tr>`;
        } else {
            tbody.innerHTML = fields.map(f => `
                <tr>
                    <td><strong>${escapeHtml(f.name)}</strong></td>
                    <td><span class="badge">${escapeHtml(f.field_type)}</span></td>
                    <td><code>${escapeHtml(f.template_token)}</code></td>
                    <td><span class="badge badge-source-hint">${escapeHtml(getSourceClassificationLabel(f.source_classification || '-'))}</span></td>
                </tr>
            `).join('');
        }

        document.getElementById('modal-raw-manifest').classList.add('hidden');
        const toggleBtn = document.getElementById('modal-toggle-raw-btn');
        if (toggleBtn) {
            toggleBtn.innerHTML = '<i class="fa-solid fa-code"></i> Show Raw Manifest';
            toggleBtn.setAttribute('aria-pressed', 'false');
        }
        document.getElementById('manifest-modal').classList.remove('hidden');
    } catch (err) {
        alert("Error retrieving manifest details: " + err.message);
    }
}

function getManifestFields(tpl) {
    return tpl && tpl.manifest && Array.isArray(tpl.manifest.fields) ? tpl.manifest.fields : [];
}

function toggleRawManifest() {
    const rawManifest = document.getElementById('modal-raw-manifest');
    const toggleBtn = document.getElementById('modal-toggle-raw-btn');
    if (!rawManifest) return;

    const nowVisible = rawManifest.classList.toggle('hidden') === false;
    if (toggleBtn) {
        toggleBtn.innerHTML = nowVisible
            ? '<i class="fa-solid fa-code"></i> Hide Raw Manifest'
            : '<i class="fa-solid fa-code"></i> Show Raw Manifest';
        toggleBtn.setAttribute('aria-pressed', String(nowVisible));
    }
}

function closeManifestModal() {
    document.getElementById('manifest-modal').classList.add('hidden');
}

function sortTemplatesLatestFirst(templates) {
    if (!Array.isArray(templates)) return [];
    return templates;
}

let manifestCache = {};

window.showRawManifestJSON = async function(templateId) {
    if (!templateId) {
        alert("No template selected for this job.");
        return;
    }
    try {
        let tpl;
        if (manifestCache[templateId]) {
            tpl = manifestCache[templateId];
        } else {
            const res = await fetch(`${API_HOST}/templates/${templateId}`);
            if (!res.ok) throw new Error("Failed to load details");
            tpl = await res.json();
            manifestCache[templateId] = tpl;
        }
        const manifest = tpl.manifest || {};

        document.getElementById('raw-manifest-title').textContent = `${tpl.template_name || 'Untitled template'} - Raw Manifest`;
        document.getElementById('raw-manifest-meta').textContent = `Template ID: ${tpl.template_id} | Version: ${tpl.version}`;
        document.getElementById('raw-manifest-content').textContent = JSON.stringify(manifest, null, 2);
        document.getElementById('raw-manifest-modal').classList.remove('hidden');
    } catch (err) {
        alert("Error retrieving manifest details: " + err.message);
    }
};

window.closeRawManifestModal = function(event) {
    if (event && event.target && event.target.id !== 'raw-manifest-modal' && !event.target.closest('.btn-close')) {
        return;
    }
    document.getElementById('raw-manifest-modal').classList.add('hidden');
};

window.showJobDataMapping = async function(jobId) {
    if (!jobId) return;
    try {
        const res = await fetch(`${API_HOST}/jobs/${jobId}`);
        if (!res.ok) throw new Error("Failed to fetch job details");
        const job = await res.json();
        
        const dataToDisplay = job.field_data_mapping || job.extracted_data || { message: "No data mapping available for this job yet." };
        
        document.getElementById('recent-job-json-title').textContent = 'Job Data Mapping JSON';
        document.getElementById('recent-job-json-meta').textContent = `Job ID: ${jobId} | Status: ${job.status}`;
        document.getElementById('recent-job-json-content').textContent = JSON.stringify(dataToDisplay, null, 2);
        document.getElementById('recent-job-json-modal').classList.remove('hidden');
    } catch (err) {
        alert("Error retrieving job data mapping: " + err.message);
    }
};
