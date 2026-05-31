(function () {
    'use strict';

    const { useCallback, useEffect, useMemo, useRef, useState } = React;
    const h = React.createElement;
    const runtimeConfig = window.__HAYS_CONFIG__ || {};
    const API_HOST = (runtimeConfig.API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
    const PORTAL_BASE = `/${String(runtimeConfig.PORTAL_BASE_PATH || '/portal').replace(/^\/+|\/+$/g, '')}`;
    const USER_PATH = `${PORTAL_BASE}/app`;
    const ADMIN_PATH = `${PORTAL_BASE}/admin`;

    function icon(name, extraClass) {
        return h('i', { className: `fa-solid ${name}${extraClass ? ` ${extraClass}` : ''}` });
    }

    async function apiFetch(path, options = {}) {
        const response = await fetch(`${API_HOST}${path}`, options);
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
            throw new Error((payload && payload.detail) || `Request failed with HTTP ${response.status}`);
        }
        return payload;
    }

    function formatDate(value) {
        if (!value) return '—';
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
    }

    function statusTone(status) {
        if (status === 'completed') return 'success';
        if (status === 'failed') return 'danger';
        if (status === 'processing' || status === 'waiting_for_template_selection') return 'warning';
        return 'info';
    }

    function extractManifestFields(manifest) {
        if (!manifest) return [];
        if (Array.isArray(manifest.fields)) return manifest.fields;
        if (manifest.field_manifest && Array.isArray(manifest.field_manifest.fields)) return manifest.field_manifest.fields;
        if (manifest.manifest && Array.isArray(manifest.manifest.fields)) return manifest.manifest.fields;
        return [];
    }

    function routeFromLocation() {
        const path = window.location.pathname.replace(/\/+$/, '') || PORTAL_BASE;
        if (path === ADMIN_PATH || path.startsWith(`${ADMIN_PATH}/`)) return 'admin';
        if (path === USER_PATH || path.startsWith(`${USER_PATH}/`)) return 'user';
        return 'home';
    }

    function navigateTo(path) {
        window.history.pushState({}, '', path || PORTAL_BASE);
        window.dispatchEvent(new PopStateEvent('popstate'));
    }

    function useRoute() {
        const [route, setRoute] = useState(routeFromLocation);
        useEffect(() => {
            const onPop = () => setRoute(routeFromLocation());
            window.addEventListener('popstate', onPop);
            return () => window.removeEventListener('popstate', onPop);
        }, []);
        return route;
    }

    function useTemplates(refreshMs) {
        const [templates, setTemplates] = useState([]);
        const [loading, setLoading] = useState(true);
        const [error, setError] = useState('');

        const load = useCallback(async (quiet = false) => {
            if (!quiet) setLoading(true);
            setError('');
            try {
                const data = await apiFetch('/templates?limit=100');
                setTemplates(data.templates || []);
            } catch (err) {
                setError(err.message);
            } finally {
                setLoading(false);
            }
        }, []);

        useEffect(() => { load(); }, [load]);
        useEffect(() => {
            if (!refreshMs) return undefined;
            const timer = setInterval(() => load(true), refreshMs);
            return () => clearInterval(timer);
        }, [load, refreshMs]);

        return { templates, loading, error, load };
    }

    function useJobs(refreshMs) {
        const [jobs, setJobs] = useState([]);
        const [loading, setLoading] = useState(true);
        const [error, setError] = useState('');

        const load = useCallback(async (quiet = false) => {
            if (!quiet) setLoading(true);
            setError('');
            try {
                const data = await apiFetch('/jobs?limit=50');
                setJobs(data.jobs || []);
            } catch (err) {
                setError(err.message);
            } finally {
                setLoading(false);
            }
        }, []);

        useEffect(() => { load(); }, [load]);
        useEffect(() => {
            if (!refreshMs) return undefined;
            const timer = setInterval(() => load(true), refreshMs);
            return () => clearInterval(timer);
        }, [load, refreshMs]);

        return { jobs, loading, error, load };
    }

    function Shell({ route, children }) {
        return h(React.Fragment, null,
            h('div', { className: 'ambient ambient-one' }),
            h('div', { className: 'ambient ambient-two' }),
            h('div', { className: 'app-shell' },
                h('header', { className: 'topbar' },
                    h('button', { className: 'brand', onClick: () => navigateTo(PORTAL_BASE) },
                        h('span', { className: 'brand-mark' }, icon('fa-wand-magic-sparkles')),
                        h('span', { className: 'brand-copy' },
                            h('strong', null, 'HAYS'),
                            h('small', null, 'Agentic Resume Platform')
                        )
                    ),
                    h('nav', { className: 'topnav', 'aria-label': 'Primary' },
                        h('button', { className: route === 'user' ? 'active' : '', onClick: () => navigateTo(USER_PATH) }, icon('fa-user-tie'), ' Candidate formatter'),
                        h('button', { className: route === 'admin' ? 'active' : '', onClick: () => navigateTo(ADMIN_PATH) }, icon('fa-shield-halved'), ' Admin console')
                    )
                ),
                h('main', { className: 'page' }, children),
                h('footer', { className: 'footer' },
                    h('span', null, '© 2026 Hays Agentic Document Platform'),
                    h('span', { className: 'status-online' }, icon('fa-circle-check'), ' API connected')
                )
            )
        );
    }

    function Home() {
        return h('section', { className: 'hero-grid' },
            h('div', { className: 'hero-copy' },
                h('span', { className: 'eyebrow' }, 'Single Page Application'),
                h('h1', null, 'One platform, two focused experiences.'),
                h('p', null, `Recruiters get a clean resume formatter at ${USER_PATH}, while operations teams manage templates and jobs from ${ADMIN_PATH}.`),
                h('div', { className: 'hero-actions' },
                    h('button', { className: 'btn primary', onClick: () => navigateTo(USER_PATH) }, icon('fa-bolt'), ' Start formatting'),
                    h('button', { className: 'btn ghost', onClick: () => navigateTo(ADMIN_PATH) }, icon('fa-sliders'), ' Open admin')
                )
            ),
            h('div', { className: 'role-cards' },
                h('button', { className: 'role-card recruiter', onClick: () => navigateTo(USER_PATH) },
                    h('span', { className: 'role-icon' }, icon('fa-file-signature')),
                    h('strong', null, 'Normal user URL'),
                    h('code', null, USER_PATH),
                    h('p', null, 'Upload a CV, choose a template, and download the finished document.')
                ),
                h('button', { className: 'role-card admin', onClick: () => navigateTo(ADMIN_PATH) },
                    h('span', { className: 'role-icon' }, icon('fa-gears')),
                    h('strong', null, 'Admin URL'),
                    h('code', null, ADMIN_PATH),
                    h('p', null, 'Upload DOCX templates, inspect manifests, and monitor jobs.')
                )
            )
        );
    }

    function UserApp() {
        const { templates, loading, error, load } = useTemplates(0);
        const [selectedTemplateId, setSelectedTemplateId] = useState('');
        const [resumeText, setResumeText] = useState('');
        const [resumeFile, setResumeFile] = useState(null);
        const [query, setQuery] = useState('');
        const [submitting, setSubmitting] = useState(false);
        const [submitError, setSubmitError] = useState('');
        const [jobId, setJobId] = useState('');
        const fileInput = useRef(null);

        const filteredTemplates = useMemo(() => {
            const needle = query.trim().toLowerCase();
            if (!needle) return templates;
            return templates.filter((template) =>
                `${template.template_name} ${template.template_id}`.toLowerCase().includes(needle)
            );
        }, [templates, query]);

        const canSubmit = (resumeFile || resumeText.trim()) && !submitting;

        async function submitJob() {
            setSubmitting(true);
            setSubmitError('');
            try {
                let data;
                if (resumeFile) {
                    const form = new FormData();
                    form.append('file', resumeFile);
                    if (selectedTemplateId) form.append('template_id', selectedTemplateId);
                    if (resumeText.trim()) form.append('resume_text', resumeText.trim());
                    data = await apiFetch('/format', { method: 'POST', body: form });
                } else {
                    data = await apiFetch('/format', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ template_id: selectedTemplateId || null, resume_text: resumeText.trim() })
                    });
                }
                setJobId(data.job_id);
                window.scrollTo({ top: 0, behavior: 'smooth' });
            } catch (err) {
                setSubmitError(err.message);
            } finally {
                setSubmitting(false);
            }
        }

        function onDrop(event) {
            event.preventDefault();
            const file = event.dataTransfer.files && event.dataTransfer.files[0];
            if (file) setResumeFile(file);
        }

        return h('section', { className: 'workspace' },
            h('div', { className: 'section-heading split' },
                h('div', null,
                    h('span', { className: 'eyebrow' }, `Normal user · ${USER_PATH}`),
                    h('h1', null, 'Format candidate resumes with a guided flow'),
                    h('p', null, 'Upload a file or paste text, optionally preselect a template, then track the agent pipeline live.')
                ),
                h('button', { className: 'btn ghost', onClick: load }, icon('fa-arrows-rotate'), ' Refresh templates')
            ),
            jobId ? h(JobMonitor, { jobId, templates, onNewJob: () => setJobId('') }) : null,
            h('div', { className: 'two-column' },
                h('div', { className: 'panel upload-panel' },
                    h('div', { className: 'panel-title' }, h('span', null, '1'), h('h2', null, 'Candidate source')),
                    h('div', {
                        className: 'dropzone',
                        onDragOver: (event) => event.preventDefault(),
                        onDrop
                    },
                        h('input', { ref: fileInput, type: 'file', accept: '.pdf,.docx,.txt', hidden: true, onChange: (event) => setResumeFile(event.target.files[0] || null) }),
                        h('span', { className: 'drop-icon' }, icon(resumeFile ? 'fa-file-circle-check' : 'fa-cloud-arrow-up')),
                        h('strong', null, resumeFile ? resumeFile.name : 'Drag & drop CV here'),
                        h('small', null, resumeFile ? `${(resumeFile.size / 1024).toFixed(1)} KB selected` : 'PDF, DOCX, or TXT supported'),
                        h('button', { className: 'btn ghost', onClick: () => fileInput.current.click() }, icon('fa-folder-open'), ' Browse files')
                    ),
                    h('div', { className: 'divider' }, h('span', null, 'or paste text')),
                    h('label', { className: 'field' },
                        h('span', null, 'Resume text'),
                        h('textarea', { value: resumeText, onChange: (event) => setResumeText(event.target.value), placeholder: 'Paste candidate CV text here...' })
                    )
                ),
                h('div', { className: 'panel' },
                    h('div', { className: 'panel-title' }, h('span', null, '2'), h('h2', null, 'Template selection')),
                    h('label', { className: 'search' }, icon('fa-magnifying-glass'), h('input', { value: query, onChange: (event) => setQuery(event.target.value), placeholder: 'Search templates by name or ID' })),
                    error ? h('div', { className: 'alert danger' }, error) : null,
                    h('div', { className: 'template-grid' },
                        loading ? h(Loading, { label: 'Loading templates...' }) :
                            filteredTemplates.length ? filteredTemplates.map((template) => h(TemplateCard, {
                                key: template.template_id,
                                template,
                                selected: selectedTemplateId === template.template_id,
                                onSelect: () => setSelectedTemplateId(template.template_id)
                            })) : h('div', { className: 'empty-state' }, icon('fa-layer-group'), ' No templates found')
                    ),
                    h('div', { className: 'sticky-action' },
                        submitError ? h('div', { className: 'alert danger' }, submitError) : null,
                        h('button', { className: 'btn primary wide', disabled: !canSubmit, onClick: submitJob },
                            submitting ? icon('fa-spinner', 'fa-spin') : icon('fa-bolt'),
                            submitting ? 'Submitting...' : 'Generate formatted resume'
                        ),
                        h('small', null, selectedTemplateId ? 'Template preselected. The agent will process immediately.' : 'No template selected. The agent can pause for selection if needed.')
                    )
                )
            )
        );
    }

    function TemplateCard({ template, selected, onSelect }) {
        const fields = extractManifestFields(template.manifest);
        return h('button', { className: `template-card ${selected ? 'selected' : ''}`, onClick: onSelect },
            h('span', { className: 'template-icon' }, icon('fa-file-word')),
            h('strong', null, template.template_name),
            h('small', null, `v${template.version} · ${fields.length || 'No'} fields`),
            h('code', null, template.template_id)
        );
    }

    function JobMonitor({ jobId, templates, onNewJob }) {
        const [job, setJob] = useState(null);
        const [error, setError] = useState('');
        const [selectedTemplateId, setSelectedTemplateId] = useState('');
        const [resuming, setResuming] = useState(false);

        const load = useCallback(async () => {
            try {
                const data = await apiFetch(`/jobs/${jobId}`);
                setJob(data);
                setError('');
            } catch (err) {
                setError(err.message);
            }
        }, [jobId]);

        useEffect(() => {
            load();
            const timer = setInterval(load, 3000);
            return () => clearInterval(timer);
        }, [load]);

        async function resumeWithTemplate() {
            if (!selectedTemplateId) return;
            setResuming(true);
            try {
                await apiFetch(`/jobs/${jobId}/select-template`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ template_id: selectedTemplateId })
                });
                await load();
            } catch (err) {
                setError(err.message);
            } finally {
                setResuming(false);
            }
        }

        const status = job ? job.status : 'queued';
        return h('div', { className: 'panel monitor-panel' },
            h('div', { className: 'monitor-header' },
                h('div', null,
                    h('span', { className: `pill ${statusTone(status)}` }, status.replaceAll('_', ' ')),
                    h('h2', null, 'Live agent pipeline'),
                    h('code', null, jobId)
                ),
                h('div', { className: 'row-actions' },
                    h('button', { className: 'btn ghost small', onClick: load }, icon('fa-arrows-rotate'), ' Refresh'),
                    h('button', { className: 'btn ghost small', onClick: onNewJob }, icon('fa-plus'), ' New job')
                )
            ),
            error ? h('div', { className: 'alert danger' }, error) : null,
            h('div', { className: 'steps' },
                ['queued', 'processing', 'completed'].map((step) => h('div', { key: step, className: `step ${stepClass(status, step)}` },
                    h('span', null, icon(step === 'queued' ? 'fa-clock' : step === 'processing' ? 'fa-gears' : 'fa-check')),
                    h('strong', null, step)
                ))
            ),
            job && status === 'waiting_for_template_selection' ? h('div', { className: 'selection-callout' },
                h('div', null, h('strong', null, 'Template needed'), h('p', null, 'Choose a corporate template to resume this paused job.')),
                h('select', { value: selectedTemplateId, onChange: (event) => setSelectedTemplateId(event.target.value) },
                    h('option', { value: '' }, 'Select template'),
                    templates.map((template) => h('option', { key: template.template_id, value: template.template_id }, `${template.template_name} (v${template.version})`))
                ),
                h('button', { className: 'btn primary', disabled: !selectedTemplateId || resuming, onClick: resumeWithTemplate }, resuming ? 'Resuming...' : 'Confirm & process')
            ) : null,
            job && status === 'completed' ? h('div', { className: 'result-card' },
                h('div', null, h('strong', null, 'Formatting complete'), h('p', null, 'Download the generated DOCX output.')),
                h('a', { className: 'btn success', href: `${API_HOST}/jobs/${job.job_id}/download` }, icon('fa-file-arrow-down'), ' Download DOCX')
            ) : null,
            job && job.extracted_data ? h(ExtractedData, { data: job.extracted_data }) : null
        );
    }

    function stepClass(status, step) {
        if (status === 'failed') return step === 'completed' ? 'failed' : 'done';
        const order = ['queued', 'processing', 'completed'];
        const current = status === 'waiting_for_template_selection' ? 1 : order.indexOf(status);
        const idx = order.indexOf(step);
        if (idx < current) return 'done';
        if (idx === current) return 'active';
        return '';
    }

    function ExtractedData({ data }) {
        const entries = Object.entries(data || {});
        const [open, setOpen] = useState(false);
        return h('div', { className: 'extracted' },
            h('button', { className: 'accordion-toggle', onClick: () => setOpen(!open) }, icon(open ? 'fa-chevron-up' : 'fa-chevron-down'), `Extracted variables (${entries.length})`),
            open ? h('div', { className: 'table-wrap' }, h('table', null,
                h('thead', null, h('tr', null, h('th', null, 'Field'), h('th', null, 'Value'))),
                h('tbody', null, entries.map(([key, value]) => h('tr', { key }, h('td', null, key), h('td', null, typeof value === 'string' ? value : JSON.stringify(value)))))
            )) : null
        );
    }

    function AdminApp() {
        const [view, setView] = useState('templates');
        const { templates, loading: templatesLoading, error: templatesError, load: loadTemplates } = useTemplates(6000);
        const { jobs, loading: jobsLoading, error: jobsError, load: loadJobs } = useJobs(5000);
        const [modalTemplate, setModalTemplate] = useState(null);

        return h('section', { className: 'workspace admin-workspace' },
            h('div', { className: 'section-heading split' },
                h('div', null,
                    h('span', { className: 'eyebrow' }, `Admin console · ${ADMIN_PATH}`),
                    h('h1', null, 'Template operations and resume job control'),
                    h('p', null, 'Manage DOCX template ingestion, inspect manifests, and download completed resume outputs.')
                ),
                h('div', { className: 'metric-strip' },
                    h('div', null, h('strong', null, templates.length), h('span', null, 'Templates')),
                    h('div', null, h('strong', null, jobs.length), h('span', null, 'Jobs')),
                    h('div', null, h('strong', null, jobs.filter((job) => job.status === 'completed').length), h('span', null, 'Completed'))
                )
            ),
            h('div', { className: 'admin-layout' },
                h('aside', { className: 'admin-rail' },
                    h('button', { className: view === 'templates' ? 'active' : '', onClick: () => setView('templates') }, icon('fa-layer-group'), ' Templates'),
                    h('button', { className: view === 'jobs' ? 'active' : '', onClick: () => setView('jobs') }, icon('fa-list-check'), ' Resume jobs')
                ),
                view === 'templates'
                    ? h(AdminTemplates, { templates, loading: templatesLoading, error: templatesError, onRefresh: loadTemplates, onInspect: setModalTemplate })
                    : h(AdminJobs, { jobs, loading: jobsLoading, error: jobsError, onRefresh: loadJobs })
            ),
            modalTemplate ? h(ManifestModal, { template: modalTemplate, onClose: () => setModalTemplate(null) }) : null
        );
    }

    function AdminTemplates({ templates, loading, error, onRefresh, onInspect }) {
        const [uploading, setUploading] = useState(false);
        const [uploadError, setUploadError] = useState('');
        const [uploadSuccess, setUploadSuccess] = useState('');
        const input = useRef(null);

        async function uploadFile(file) {
            if (!file) return;
            setUploading(true);
            setUploadError('');
            setUploadSuccess('');
            try {
                const form = new FormData();
                form.append('file', file);
                const data = await apiFetch('/admin/templates', { method: 'POST', body: form });
                setUploadSuccess(`Template queued for analysis. Job ${data.analysis_job_id}`);
                await onRefresh();
            } catch (err) {
                setUploadError(err.message);
            } finally {
                setUploading(false);
                if (input.current) input.current.value = '';
            }
        }

        return h('div', { className: 'admin-main' },
            h('div', { className: 'panel upload-template' },
                h('div', null, h('h2', null, 'Upload DOCX template'), h('p', null, 'Admins maintain reusable corporate layouts for recruiters.')),
                h('input', { ref: input, type: 'file', accept: '.docx', hidden: true, onChange: (event) => uploadFile(event.target.files[0]) }),
                h('button', { className: 'btn primary', disabled: uploading, onClick: () => input.current.click() }, uploading ? icon('fa-spinner', 'fa-spin') : icon('fa-cloud-arrow-up'), uploading ? 'Uploading...' : 'Upload template'),
                uploadError ? h('div', { className: 'alert danger' }, uploadError) : null,
                uploadSuccess ? h('div', { className: 'alert success' }, uploadSuccess) : null
            ),
            h('div', { className: 'panel' },
                h('div', { className: 'panel-header' }, h('h2', null, 'Template library'), h('button', { className: 'btn ghost small', onClick: onRefresh }, icon('fa-arrows-rotate'), ' Refresh')),
                error ? h('div', { className: 'alert danger' }, error) : null,
                loading ? h(Loading, { label: 'Loading templates...' }) : h('div', { className: 'table-wrap' }, h('table', null,
                    h('thead', null, h('tr', null, h('th', null, 'Template'), h('th', null, 'Version'), h('th', null, 'Fields'), h('th', null, 'Object key'), h('th', null, 'Actions'))),
                    h('tbody', null, templates.map((template) => {
                        const fields = extractManifestFields(template.manifest);
                        return h('tr', { key: template.template_id },
                            h('td', null, h('strong', null, template.template_name), h('code', null, template.template_id)),
                            h('td', null, `v${template.version}`),
                            h('td', null, fields.length),
                            h('td', null, h('code', null, template.object_key)),
                            h('td', null, h('button', { className: 'btn ghost small', onClick: () => onInspect(template) }, icon('fa-eye'), ' Inspect'))
                        );
                    }))
                ))
            )
        );
    }

    function AdminJobs({ jobs, loading, error, onRefresh }) {
        return h('div', { className: 'admin-main' },
            h('div', { className: 'panel' },
                h('div', { className: 'panel-header' }, h('h2', null, 'Resume job download center'), h('button', { className: 'btn ghost small', onClick: onRefresh }, icon('fa-arrows-rotate'), ' Refresh')),
                error ? h('div', { className: 'alert danger' }, error) : null,
                loading ? h(Loading, { label: 'Loading jobs...' }) : h('div', { className: 'table-wrap' }, h('table', null,
                    h('thead', null, h('tr', null, h('th', null, 'Job'), h('th', null, 'Type'), h('th', null, 'Status'), h('th', null, 'Template'), h('th', null, 'Updated'), h('th', null, 'Output'))),
                    h('tbody', null, jobs.map((job) => h('tr', { key: job.job_id },
                        h('td', null, h('code', null, job.job_id)),
                        h('td', null, job.job_type.replace('_', ' ')),
                        h('td', null, h('span', { className: `pill ${statusTone(job.status)}` }, job.status.replaceAll('_', ' '))),
                        h('td', null, job.template_id ? h('code', null, job.template_id) : '—'),
                        h('td', null, formatDate(job.updated_at)),
                        h('td', null, job.status === 'completed'
                            ? h('a', { className: 'btn success small', href: `${API_HOST}/jobs/${job.job_id}/download` }, icon('fa-download'), ' Download')
                            : job.error ? h('span', { className: 'text-danger' }, job.error) : '—')
                    )))
                ))
            )
        );
    }

    function ManifestModal({ template, onClose }) {
        const fields = extractManifestFields(template.manifest);
        return h('div', { className: 'modal-backdrop', onClick: onClose },
            h('div', { className: 'modal panel', onClick: (event) => event.stopPropagation() },
                h('div', { className: 'modal-header' },
                    h('div', null, h('h2', null, template.template_name), h('p', null, `${template.template_id} · v${template.version}`)),
                    h('button', { className: 'icon-button', onClick: onClose }, icon('fa-xmark'))
                ),
                h('div', { className: 'manifest-stats' },
                    h('div', null, h('strong', null, fields.length), h('span', null, 'Total fields')),
                    h('div', null, h('strong', null, fields.filter((field) => field.required).length), h('span', null, 'Required')),
                    h('div', null, h('strong', null, fields.filter((field) => String(field.field_type || '').includes('array')).length), h('span', null, 'Repeating'))
                ),
                h('div', { className: 'table-wrap' }, h('table', null,
                    h('thead', null, h('tr', null, h('th', null, 'Name'), h('th', null, 'Type'), h('th', null, 'Required'), h('th', null, 'Token'), h('th', null, 'Source hint'))),
                    h('tbody', null, fields.map((field, index) => h('tr', { key: `${field.name}-${index}` },
                        h('td', null, field.name || '—'),
                        h('td', null, field.field_type || '—'),
                        h('td', null, field.required ? 'Yes' : 'No'),
                        h('td', null, h('code', null, field.template_token || '—')),
                        h('td', null, field.source_hint || '—')
                    )))
                )),
                h('details', { className: 'raw-json' }, h('summary', null, 'Raw manifest'), h('pre', null, JSON.stringify(template.manifest || {}, null, 2)))
            )
        );
    }

    function Loading({ label }) {
        return h('div', { className: 'loading' }, icon('fa-spinner', 'fa-spin'), h('span', null, label));
    }

    function App() {
        const route = useRoute();
        const page = route === 'admin' ? h(AdminApp) : route === 'user' ? h(UserApp) : h(Home);
        return h(Shell, { route }, page);
    }

    ReactDOM.createRoot(document.getElementById('root')).render(h(App));
}());
