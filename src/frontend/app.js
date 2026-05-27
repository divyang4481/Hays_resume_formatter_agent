// Global State
let selectedTemplateId = null;
let activeTab = 'agent';
let currentJobId = null;
let pollInterval = null;
let allTemplates = [];

// API Host - default to empty (same host)
const API_HOST = '';

document.addEventListener('DOMContentLoaded', () => {
    initTabNavigation();
    initFileUploads();
    loadTemplates();
    loadRecentJobs();
});

// 1. Tab Navigation
function initTabNavigation() {
    window.switchTab = (tabName) => {
        activeTab = tabName;
        document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
        
        document.getElementById(`nav-${tabName}`).classList.add('active');
        document.getElementById(`tab-${tabName}`).classList.add('active');
        
        if (tabName === 'agent') {
            loadTemplates();
            loadRecentJobs();
        } else if (tabName === 'admin') {
            loadAdminTemplates();
        }
    };
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
    
    if (selectedTemplateId && (fileSelected || textPasted)) {
        submitBtn.removeAttribute('disabled');
    } else {
        submitBtn.setAttribute('disabled', 'true');
    }
}

// 3. API Loaders - Templates
async function loadTemplates() {
    const grid = document.getElementById('agent-template-grid');
    try {
        const res = await fetch(`${API_HOST}/templates`);
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
        const fieldsCount = tpl.manifest && tpl.manifest.fields ? tpl.manifest.fields.length : 0;
        const isSelected = selectedTemplateId === tpl.template_id ? 'selected' : '';
        return `
            <div class="template-item-card ${isSelected}" onclick="selectTemplate('${tpl.template_id}')">
                <div class="template-meta-header">
                    <span class="template-title">${tpl.template_name}</span>
                    <span class="template-version">v${tpl.version}</span>
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
            formData.append('template_id', selectedTemplateId);
            formData.append('file', fileInput.files[0]);
            
            res = await fetch(`${API_HOST}/format`, {
                method: 'POST',
                body: formData
            });
        } else {
            // Paste Text JSON upload
            res = await fetch(`${API_HOST}/format`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    template_id: selectedTemplateId,
                    resume_text: textInput.value.trim()
                })
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
            valStr = `[${val.length} items] ${JSON.stringify(val)}`;
        } else if (typeof val === 'object' && val !== null) {
            typeStr = 'Object';
            valStr = JSON.stringify(val);
        } else {
            valStr = val !== null && val !== undefined ? String(val) : '<span class="text-muted">empty</span>';
        }
        
        tbody.innerHTML += `
            <tr>
                <td><strong>${key}</strong></td>
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
        
        if (data.jobs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No formatting jobs have been executed yet.</td></tr>`;
            return;
        }
        
        tbody.innerHTML = data.jobs.map(job => {
            let statusBadgeClass = 'text-warning';
            if (job.status === 'completed') statusBadgeClass = 'text-success';
            if (job.status === 'failed') statusBadgeClass = 'text-danger';
            
            const cvLabel = job.resume_object_key ? job.resume_object_key.split('/').pop() : 'Pasted Raw Text';
            const templateName = getTemplateNameById(job.template_id);
            const formattedDate = new Date(job.created_at).toLocaleString();
            
            let actionBtn = '';
            if (job.status === 'completed') {
                actionBtn = `<a href="${API_HOST}/jobs/${job.job_id}/download" class="btn btn-outline btn-small"><i class="fa-solid fa-download"></i> Download</a>`;
            } else {
                actionBtn = `<button class="btn btn-outline btn-small" onclick="trackExistingJob('${job.job_id}')"><i class="fa-solid fa-eye"></i> Track</button>`;
            }
            
            return `
                <tr>
                    <td><code class="text-primary">${job.job_id.substring(0, 8)}...</code></td>
                    <td><strong class="${statusBadgeClass}"><i class="fa-solid fa-circle-play"></i> ${job.status}</strong></td>
                    <td>${cvLabel}</td>
                    <td>${templateName}</td>
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
    return found ? found.template_name : templateId.substring(0, 8) + '...';
}

function trackExistingJob(jobId) {
    currentJobId = jobId;
    showPipeline(currentJobId);
    pollJobStatus();
}

// 6. Admin Panel - Load Catalog and Manage Uploads
async function loadAdminTemplates() {
    const list = document.getElementById('admin-template-list');
    try {
        const res = await fetch(`${API_HOST}/templates`);
        if (!res.ok) throw new Error("Failed to load templates");
        const data = await res.json();
        allTemplates = data.templates;
        
        if (allTemplates.length === 0) {
            list.innerHTML = `<div class="loading-state"><i class="fa-solid fa-folder-open"></i><p>No templates registered yet. Use the upload zone to parse your first template.</p></div>`;
            return;
        }
        
        list.innerHTML = allTemplates.map(tpl => {
            const fieldsCount = tpl.manifest && tpl.manifest.fields ? tpl.manifest.fields.length : 0;
            return `
                <div class="admin-template-item">
                    <div class="admin-item-info">
                        <i class="fa-solid fa-file-word admin-file-icon"></i>
                        <div>
                            <span class="admin-item-title">${tpl.template_name}</span>
                            <div class="admin-item-subtitle">ID: ${tpl.template_id} | Version: ${tpl.version}</div>
                        </div>
                    </div>
                    <button class="btn btn-outline btn-small" onclick="inspectManifest('${tpl.template_id}')">
                        <i class="fa-solid fa-folder-tree"></i> View Manifest (${fieldsCount} fields)
                    </button>
                </div>
            `;
        }).join('');
        
    } catch (err) {
        console.error(err);
        list.innerHTML = `<div class="loading-state text-danger"><i class="fa-solid fa-triangle-exclamation"></i><p>Failed to query template catalog.</p></div>`;
    }
}

async function uploadTemplateFile(file) {
    const zone = document.getElementById('template-drop-zone');
    zone.querySelector('.zone-primary-text').textContent = `Uploading: ${file.name}...`;
    zone.querySelector('.cloud-icon').className = 'fa-solid fa-spinner fa-spin cloud-icon';
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const res = await fetch(`${API_HOST}/admin/templates`, {
            method: 'POST',
            body: formData
        });
        
        if (!res.ok) throw new Error("Failed to upload template");
        
        const data = await res.json();
        alert(`Template uploaded successfully. Created analysis Job ID: ${data.analysis_job_id}`);
        
        // Reload list
        loadAdminTemplates();
        
        // Reset zone UI
        zone.querySelector('.zone-primary-text').textContent = `Drag & drop DOCX template here`;
        zone.querySelector('.cloud-icon').className = 'fa-solid fa-file-circle-plus cloud-icon';
        
    } catch (err) {
        console.error(err);
        alert("Upload error: " + err.message);
        zone.querySelector('.zone-primary-text').textContent = `Drag & drop DOCX template here`;
        zone.querySelector('.cloud-icon').className = 'fa-solid fa-file-circle-plus cloud-icon';
    }
}

// 7. Modal Manifest Inspector Drawer
async function inspectManifest(templateId) {
    try {
        const res = await fetch(`${API_HOST}/templates/${templateId}`);
        if (!res.ok) throw new Error("Failed to load details");
        const tpl = await res.json();
        
        document.getElementById('modal-template-name').textContent = tpl.template_name;
        document.getElementById('modal-template-meta').textContent = `Template ID: ${tpl.template_id} | Version: ${tpl.version}`;
        
        const fields = tpl.manifest && tpl.manifest.fields ? tpl.manifest.fields : [];
        
        // Set stats
        document.getElementById('stat-total-fields').textContent = fields.length;
        document.getElementById('stat-scalar-fields').textContent = fields.filter(f => f.field_type === 'scalar').length;
        document.getElementById('stat-array-fields').textContent = fields.filter(f => f.field_type !== 'scalar').length;
        
        const tbody = document.getElementById('modal-fields-body');
        if (fields.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No manifest fields detected for this template. Check analysis worker log.</td></tr>`;
        } else {
            tbody.innerHTML = fields.map(f => {
                return `
                    <tr>
                        <td><strong>${f.name}</strong></td>
                        <td><span class="badge">${f.field_type}</span></td>
                        <td><code>${f.template_token}</code></td>
                        <td><span class="subtitle">${f.source_hint || '-'}</span></td>
                    </tr>
                `;
            }).join('');
        }
        
        document.getElementById('manifest-modal').classList.remove('hidden');
    } catch (err) {
        alert("Error retrieving manifest details: " + err.message);
    }
}

function closeManifestModal() {
    document.getElementById('manifest-modal').classList.add('hidden');
}
