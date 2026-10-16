(() => {
  'use strict';

  // ==========================================================================
  // CITIDY & MUNICIPAL OPERATIONS ENGINE
  // Product: Citidy Civic Complaint Management Platform
  // Tagline: "Your City. Your Voice. Tracked to Resolution."
  // ==========================================================================

  const data = window.CITYFIX_DATA;
  if (!data || !Array.isArray(data.locations)) {
    console.error('Citidy: Dataset window.CITYFIX_DATA is not available.');
    return;
  }

  const fmt = new Intl.NumberFormat('en-US');
  const locations = data.locations;

  // DOM helper with safe fallback
  const $ = (id) => document.getElementById(id);

  // --------------------------------------------------------------------------
  // PRIORITY ENGINE (5-Factor Weighted Analytical Heuristic)
  // Factors: Incident volume 30%, Avg severity 25%, Complaint volume 20%,
  //          Open backlog 15%, Street risk context 10%
  // --------------------------------------------------------------------------
  const percentile95 = (values) => {
    const sorted = [...values].filter(v => typeof v === 'number' && !isNaN(v)).sort((a, b) => a - b);
    if (!sorted.length) return 1;
    const index = Math.max(0, Math.ceil(sorted.length * 0.95) - 1);
    return sorted[index] || 1;
  };

  const scale = (value, ceiling) => Math.min(1.0, Math.max(0.0, value / Math.max(1, ceiling)));

  const ceilings = {
    incidents: percentile95(locations.map(x => x.incidentCount)),
    complaints: percentile95(locations.map(x => x.complaintCount)),
    backlog: percentile95(locations.map(x => x.unresolved + x.openComplaints)),
    density: percentile95(locations.map(x => x.density)),
  };

  const roadRisk = { Good: 0.20, Fair: 0.45, Poor: 0.75, Critical: 1.00 };
  const pedestrianRisk = { Low: 0.35, Medium: 0.65, High: 1.00 };
  const weights = [0.30, 0.25, 0.20, 0.15, 0.10];
  const factorLabels = ['Incident Volume', 'Average Severity', 'Complaint Volume', 'Open Backlog', 'Street Risk Context'];

  locations.forEach((loc) => {
    const exposure = (loc.school ? 0.5 : 0) + (loc.hospital ? 0.5 : 0);
    const context = (roadRisk[loc.condition] || 0.40) * 0.40
      + (pedestrianRisk[loc.pedestrian] || 0.50) * 0.30
      + exposure * 0.20
      + scale(loc.density, ceilings.density) * 0.10;

    const values = [
      scale(loc.incidentCount, ceilings.incidents),
      Math.min(1.0, loc.avgSeverity / 4.0),
      scale(loc.complaintCount, ceilings.complaints),
      scale(loc.unresolved + loc.openComplaints, ceilings.backlog),
      Math.min(1.0, Math.max(0.0, context)),
    ];

    loc.components = values;
    loc.factorPoints = values.map((val, idx) => Math.round(val * weights[idx] * 100));
    loc.priority = Math.min(100, Math.max(0, loc.factorPoints.reduce((sum, p) => sum + p, 0)));
    loc.openWork = loc.unresolved + loc.openComplaints;
    loc.topIssue = Object.entries(loc.incidentTypes || {}).sort((a, b) => b[1] - a[1])[0]?.[0] || 'No incidents';
    loc.predictedQ4 = null;
    loc.actualQ4 = null;
  });

  // Storage keys
  const reviewStorageKey = 'citidy-review-decisions-v2';
  const tokenStorageKey = 'citidy_auth_token';
  const userStorageKey = 'citidy_auth_user';

  const reviewDecisions = (() => {
    try {
      const saved = JSON.parse(localStorage.getItem(reviewStorageKey) || '{}');
      return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
    } catch (_) { return {}; }
  })();

  // Platform state
  const state = {
    // Priority queue filters
    zone: 'all',
    issue: 'all',
    severity: 'all',
    search: '',
    selected: null,
    sortField: 'priority',
    sortAsc: false,
    currentPage: 1,
    pageSize: 15,

    // Citidy Portal & Auth state
    portal: 'citizen', // 'citizen' | 'admin'
    citizenTab: 'complaints', // 'complaints' | 'report' | 'map'
    adminTab: 'triage', // 'triage' | 'queue' | 'analytics' | 'limitations'
    user: null,
    token: null,

    // Data collections
    citizenComplaints: [],
    adminComplaints: [],
    mapComplaints: [],
    notifications: [],
    unreadNotifCount: 0,
    complaintFilter: 'all',

    // Photo uploads
    reportPhotoBase64: null,
    reportPhotoName: null,
    resolvePhotoBase64: null,
    resolvePhotoName: null,
  };

  // Restore stored session if present
  try {
    state.token = localStorage.getItem(tokenStorageKey) || null;
    state.user = JSON.parse(localStorage.getItem(userStorageKey) || 'null');
  } catch (_) {}

  // --------------------------------------------------------------------------
  // CITIDY REST & SUPABASE CLIENT (SAFE PARSING & ERROR HANDLING)
  // --------------------------------------------------------------------------
  const isSupabaseConfigured = () => {
    return Boolean(
      window.CITIDY_SUPABASE_URL &&
      window.CITIDY_SUPABASE_ANON_KEY &&
      window.CITIDY_SUPABASE_URL.startsWith('https://') &&
      !window.CITIDY_SUPABASE_URL.includes('your-project-id')
    );
  };

  const apiCall = async (endpoint, method = 'GET', body = null) => {
    const baseUrl = (window.CITIDY_API_BASE_URL || '').replace(/\/$/, '');
    const url = `${baseUrl}${endpoint}`;

    const headers = { 'Content-Type': 'application/json' };
    if (state.token) {
      headers['Authorization'] = `Bearer ${state.token}`;
    }
    const config = { method, headers };
    if (body) {
      config.body = JSON.stringify(body);
    }

    let res;
    try {
      res = await fetch(url, config);
    } catch (networkErr) {
      console.error(`[Citidy API Error] Network connection failed for ${method} ${endpoint}:`, networkErr.message);
      throw new Error(`Unable to connect to the Citidy backend server. Ensure 'python server.py --port 8000' is running locally, or configure a production backend URL.`);
    }

    const contentType = (res.headers.get('content-type') || '').toLowerCase();
    const isJson = contentType.includes('application/json');

    // Handle non-JSON responses (HTML error pages, 404s, 501s from static servers)
    if (!isJson) {
      const rawText = await res.text();
      console.error(`[Citidy API Error] Non-JSON response received from ${method} ${endpoint}. Status: ${res.status}, Content-Type: "${contentType}"`);

      if (res.status === 404) {
        throw new Error(`Endpoint '${endpoint}' was not found (HTTP 404). If you are running locally, make sure server.py is running on port 8000. If hosted on GitHub Pages, connect a backend API or Supabase.`);
      }
      if (res.status === 501) {
        throw new Error(`Backend server returned HTTP 501 (Method Not Allowed). Please restart the Citidy server ('python server.py --port 8000') so updated API routes take effect.`);
      }
      if (res.status >= 500) {
        throw new Error(`Citidy server returned an internal error (HTTP ${res.status}). Check server console logs.`);
      }
      if (rawText.includes('<!DOCTYPE') || rawText.includes('<html')) {
        throw new Error(`Server returned an HTML response (HTTP ${res.status}) instead of JSON from ${endpoint}. Ensure the Citidy API server is running on port 8000.`);
      }
      throw new Error(`Unexpected non-JSON response from server (HTTP ${res.status}): ${rawText.slice(0, 100)}`);
    }

    let json;
    try {
      json = await res.json();
    } catch (parseErr) {
      console.error(`[Citidy API Error] Failed to parse JSON from ${method} ${endpoint}:`, parseErr.message);
      throw new Error(`Invalid JSON received from server (HTTP ${res.status}).`);
    }

    if (!res.ok) {
      const errMsg = json.error || `Request failed with HTTP status ${res.status}`;
      console.error(`[Citidy API Error] ${method} ${endpoint} returned error: ${errMsg} (Status: ${res.status})`);
      throw new Error(errMsg);
    }

    return json;
  };

  // Dedicated Authentication Dispatcher (Supports Custom Backend or Supabase Cloud)
  const performLogin = async (email, password) => {
    if (isSupabaseConfigured()) {
      try {
        const authRes = await fetch(`${window.CITIDY_SUPABASE_URL}/auth/v1/token?grant_type=password`, {
          method: 'POST',
          headers: {
            'apikey': window.CITIDY_SUPABASE_ANON_KEY,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ email, password }),
        });
        const authData = await authRes.json();
        if (!authRes.ok || !authData.access_token) {
          throw new Error(authData.error_description || authData.msg || 'Invalid email or password');
        }

        const profileRes = await fetch(`${window.CITIDY_SUPABASE_URL}/rest/v1/profiles?id=eq.${authData.user.id}&select=*`, {
          method: 'GET',
          headers: {
            'apikey': window.CITIDY_SUPABASE_ANON_KEY,
            'Authorization': `Bearer ${authData.access_token}`,
          },
        });
        const profiles = await profileRes.json();
        const profile = Array.isArray(profiles) ? profiles[0] : null;

        if (!profile) {
          throw new Error('User profile record not found in Supabase database.');
        }

        return {
          token: authData.access_token,
          user: {
            id: profile.id,
            fullName: profile.full_name || email,
            email: profile.email || email,
            role: profile.role || 'citizen',
            phone: profile.phone || '',
          },
        };
      } catch (sbErr) {
        console.error('[Citidy Supabase Auth Error]:', sbErr.message);
        throw sbErr;
      }
    }

    // Default: Custom Python / SQLite Backend
    return await apiCall('/api/auth/login', 'POST', { email, password });
  };

  const showToast = (message, isError = false) => {
    const toast = $('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = `toast visible ${isError ? 'toast-error' : 'toast-success'}`;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => {
      toast.className = 'toast';
    }, 4000);
  };

  // --------------------------------------------------------------------------
  // POPULATE DOM FILTER CONTROLS (SAFE ACCESS)
  // --------------------------------------------------------------------------
  const zoneFilter = $('zoneFilter');
  const issueFilter = $('issueFilter');
  const severityFilter = $('severityFilter');
  const searchInput = $('searchInput');
  const matchingCount = $('matchingCount');
  const adminZoneFilter = $('adminZoneFilter');

  const zones = [...new Set(locations.map(x => x.zone))].sort((a, b) => a.localeCompare(b));
  if (zoneFilter && zoneFilter.add) {
    zones.forEach((zone) => zoneFilter.add(new Option(zone.replace('_', ' '), zone)));
  }
  if (adminZoneFilter && adminZoneFilter.add) {
    zones.forEach((zone) => adminZoneFilter.add(new Option(zone.replace('_', ' '), zone)));
  }

  if (issueFilter && issueFilter.add && Array.isArray(data.incidentTypes)) {
    data.incidentTypes.forEach((type) => {
      issueFilter.add(new Option(type, type));
    });
  }

  const scoreClass = (score) => score >= 66 ? 'high' : score >= 40 ? 'mid' : 'low';

  // --------------------------------------------------------------------------
  // AUTHENTICATION & SESSION UI
  // --------------------------------------------------------------------------
  const updateAuthUI = () => {
    const userChipName = $('userChipName');
    const userChipAvatar = $('userChipAvatar');
    const dropdownUserTitle = $('dropdownUserTitle');
    const dropdownUserEmail = $('dropdownUserEmail');
    const citizenLoggedOutNotice = $('citizenLoggedOutNotice');
    const adminStaffName = $('adminStaffName');
    const adminAuthGuard = $('adminAuthGuard');
    const adminWorkspace = $('adminWorkspace');

    if (state.user) {
      if (userChipName) userChipName.textContent = state.user.fullName;
      if (userChipAvatar) userChipAvatar.textContent = state.user.role === 'admin' ? '🛡️' : '👤';
      if (dropdownUserTitle) dropdownUserTitle.textContent = `${state.user.fullName} (${state.user.role.toUpperCase()})`;
      if (dropdownUserEmail) dropdownUserEmail.textContent = state.user.email;
      if (adminStaffName) adminStaffName.textContent = state.user.fullName;
      if (citizenLoggedOutNotice) citizenLoggedOutNotice.style.display = 'none';

      if (state.portal === 'admin') {
        if (state.user.role === 'admin') {
          if (adminAuthGuard) adminAuthGuard.style.display = 'none';
          if (adminWorkspace) adminWorkspace.style.display = 'block';
        } else {
          if (adminAuthGuard) adminAuthGuard.style.display = 'flex';
          if (adminWorkspace) adminWorkspace.style.display = 'none';
        }
      }
    } else {
      if (userChipName) userChipName.textContent = 'Sign In / Register';
      if (userChipAvatar) userChipAvatar.textContent = '👤';
      if (dropdownUserTitle) dropdownUserTitle.textContent = 'Guest Visitor';
      if (dropdownUserEmail) dropdownUserEmail.textContent = 'Not authenticated';
      if (citizenLoggedOutNotice) citizenLoggedOutNotice.style.display = 'flex';

      if (state.portal === 'admin') {
        if (adminAuthGuard) adminAuthGuard.style.display = 'flex';
        if (adminWorkspace) adminWorkspace.style.display = 'none';
      }
    }
  };

  const setSession = (token, user) => {
    state.token = token;
    state.user = user;
    try {
      localStorage.setItem(tokenStorageKey, token);
      localStorage.setItem(userStorageKey, JSON.stringify(user));
    } catch (_) {}
    updateAuthUI();
    loadUserData();
  };

  const clearSession = () => {
    state.token = null;
    state.user = null;
    try {
      localStorage.removeItem(tokenStorageKey);
      localStorage.removeItem(userStorageKey);
      localStorage.removeItem('citidy_last_portal');
    } catch (_) {}
    updateAuthUI();
    switchPortal('citizen');
    loadUserData();
    showToast('Signed out successfully.');
  };

  // --------------------------------------------------------------------------
  // PORTAL SWITCHING
  // --------------------------------------------------------------------------
  const switchPortal = (portalName) => {
    state.portal = portalName;
    try {
      localStorage.setItem('citidy_last_portal', portalName);
    } catch (_) {}
    const btnSwitchCitizen = $('btnSwitchCitizen');
    const btnSwitchAdmin = $('btnSwitchAdmin');
    const citizenPortal = $('citizenPortal');
    const adminPortal = $('adminPortal');

    if (portalName === 'citizen') {
      if (btnSwitchCitizen) btnSwitchCitizen.classList.add('active');
      if (btnSwitchAdmin) btnSwitchAdmin.classList.remove('active');
      if (citizenPortal) citizenPortal.style.display = 'block';
      if (adminPortal) adminPortal.style.display = 'none';
    } else {
      if (btnSwitchCitizen) btnSwitchCitizen.classList.remove('active');
      if (btnSwitchAdmin) btnSwitchAdmin.classList.add('active');
      if (citizenPortal) citizenPortal.style.display = 'none';
      if (adminPortal) adminPortal.style.display = 'block';
      loadAdminStats();
      loadAdminTriage();
    }
    updateAuthUI();
  };

  const switchCitizenTab = (tabName) => {
    state.citizenTab = tabName;
    const tabs = {
      complaints: { tab: $('tabCitizenComplaints'), sec: $('sectionCitizenComplaints') },
      report: { tab: $('tabCitizenReport'), sec: $('sectionCitizenReport') },
      map: { tab: $('tabCitizenMap'), sec: $('sectionCitizenMap') },
    };
    Object.keys(tabs).forEach((key) => {
      const item = tabs[key];
      if (item.tab) item.tab.classList.toggle('active', key === tabName);
      if (item.sec) item.sec.style.display = key === tabName ? 'block' : 'none';
    });

    if (tabName === 'complaints') loadCitizenComplaints();
    if (tabName === 'map') loadPublicMap();
  };

  const switchAdminTab = (tabName) => {
    state.adminTab = tabName;
    const tabs = {
      triage: { tab: $('tabAdminTriage'), sec: $('sectionAdminTriage') },
      queue: { tab: $('tabAdminQueue'), sec: $('sectionAdminQueue') },
      analytics: { tab: $('tabAdminAnalytics'), sec: $('sectionAdminAnalytics') },
      limitations: { tab: $('tabAdminLimitations'), sec: $('sectionAdminLimitations') },
    };
    Object.keys(tabs).forEach((key) => {
      const item = tabs[key];
      if (item.tab) item.tab.classList.toggle('active', key === tabName);
      if (item.sec) item.sec.style.display = key === tabName ? 'block' : 'none';
    });

    if (tabName === 'triage') loadAdminTriage();
  };

  // --------------------------------------------------------------------------
  // CITIZEN COMPLAINTS LOGIC & MILESTONE RENDERING
  // --------------------------------------------------------------------------
  const formatIsoDate = (isoStr) => {
    if (!isoStr) return '—';
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch (_) {
      return isoStr;
    }
  };

  const getSlaIndicator = (complaint) => {
    if (complaint.status === 'Resolved' || complaint.status === 'Closed') {
      return {
        className: 'on-schedule',
        html: `<span>✓ <strong>Resolved</strong> on ${formatIsoDate(complaint.resolved_at)}</span>`,
      };
    }
    if (!complaint.estimated_resolution_at) {
      return { className: 'on-schedule', html: '<span>Target Date Pending Verification</span>' };
    }

    const now = new Date();
    const target = new Date(complaint.estimated_resolution_at);
    const diffHours = (target - now) / 3600000;
    const diffDays = Math.round(diffHours / 24);

    if (diffHours < 0) {
      const overdueDays = Math.abs(diffDays);
      return {
        className: 'overdue',
        html: `<span>⚠️ <strong class="text-danger">OVERDUE by ${overdueDays || 1} day${overdueDays === 1 ? '' : 's'}</strong> (Target: ${formatIsoDate(complaint.estimated_resolution_at)})</span>`,
      };
    } else {
      return {
        className: 'on-schedule',
        html: `<span>⏱️ <strong>On Schedule</strong> — Target: ${formatIsoDate(complaint.estimated_resolution_at)} (${diffDays || 1} day${diffDays === 1 ? '' : 's'} remaining)</span>`,
      };
    }
  };

  const renderMilestoneStepper = (complaint) => {
    const milestones = [
      { name: 'Submitted', pct: 0 },
      { name: 'Under Review', pct: 10 },
      { name: 'Verified', pct: 20 },
      { name: 'Assigned', pct: 30 },
      { name: 'In Progress', pct: 50 },
      { name: 'Resolved', pct: 100 },
    ];

    const currentPct = complaint.progress_percentage || 0;
    const isResolved = complaint.status === 'Resolved' || complaint.status === 'Closed';

    let stepsHtml = '';
    milestones.forEach((m, idx) => {
      const isCompleted = currentPct > m.pct || isResolved;
      const isActive = !isCompleted && complaint.status === m.name;
      const cls = isCompleted ? 'completed' : isActive ? 'active' : '';
      const checkIcon = isCompleted ? '✓' : idx + 1;

      stepsHtml += `
        <div class="stepper-step ${cls}">
          <div class="step-node">${checkIcon}</div>
          <span class="step-name">${m.name}</span>
          <span class="step-meta">${m.pct}%</span>
        </div>
      `;
    });

    return `
      <div class="milestone-stepper">
        <div class="stepper-progress-bar-wrap">
          <div class="stepper-progress-bar-fill" style="width: ${Math.min(100, currentPct)}%;"></div>
        </div>
        <div class="stepper-steps-row">
          ${stepsHtml}
        </div>
      </div>
    `;
  };

  const renderCitizenComplaints = () => {
    const container = $('citizenComplaintsList');
    if (!container) return;

    let items = state.citizenComplaints || [];
    if (state.complaintFilter === 'active') {
      items = items.filter(c => !['Resolved', 'Closed', 'Rejected'].includes(c.status));
    } else if (state.complaintFilter === 'resolved') {
      items = items.filter(c => ['Resolved', 'Closed'].includes(c.status));
    } else if (state.complaintFilter === 'overdue') {
      items = items.filter(c => c.is_overdue);
    }

    const countBadge = $('myComplaintsCount');
    if (countBadge) countBadge.textContent = state.citizenComplaints.length;

    if (!items.length) {
      container.innerHTML = `
        <div class="empty-state card">
          <span style="font-size: 2.2rem; margin-bottom: 8px;">📭</span>
          <strong>No civic complaints found for this view</strong>
          <p style="color: var(--text-muted); font-size: 0.86rem; margin-top: 4px;">Click "Report a Problem" to submit a new civic issue with photographic evidence.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map((c) => {
      const sla = getSlaIndicator(c);
      const stepper = renderMilestoneStepper(c);
      const isResolved = c.status === 'Resolved' || c.status === 'Closed';

      let proofHtml = '';
      if (isResolved && (c.after_photo || c.before_photo)) {
        proofHtml = `
          <div class="proof-of-work-box">
            <div class="proof-header">
              <strong><span>✓</span> Verified Proof of Resolution</strong>
              <small style="color: var(--text-muted);">Inspection evidence uploaded by municipal staff</small>
            </div>
            <div class="evidence-side-by-side">
              <div class="evidence-column">
                <span class="evidence-tag before">1. Problem (Reported)</span>
                <div class="evidence-img-frame" onclick="window.citidyViewImage('${c.before_photo || 'favicon.svg'}')">
                  <img src="${c.before_photo || 'favicon.svg'}" alt="Citizen reported problem photograph" loading="lazy">
                </div>
              </div>
              <div class="evidence-column">
                <span class="evidence-tag after">2. Resolution (Verified Fix)</span>
                <div class="evidence-img-frame" onclick="window.citidyViewImage('${c.after_photo || 'favicon.svg'}')">
                  <img src="${c.after_photo || 'favicon.svg'}" alt="Verified resolution photograph" loading="lazy">
                </div>
              </div>
            </div>
            ${c.resolution_notes ? `<blockquote class="resolution-notes-quote"><strong>Field Resolution Notes:</strong> ${c.resolution_notes}</blockquote>` : ''}
          </div>
        `;
      }

      return `
        <article class="complaint-card" id="card-${c.id}">
          <div class="card-top-row">
            <div class="card-id-block">
              <span class="complaint-num-badge">${c.complaint_number}</span>
              <span class="complaint-cat-badge">📁 ${c.category}</span>
            </div>
            <div class="card-top-right">
              <span class="status-pill status-${c.status.replace(/\s+/g, '-')}">${c.status}</span>
              <span class="priority-pill priority-${c.priority.toLowerCase()}">${c.priority}</span>
            </div>
          </div>

          <div class="card-title-row">
            <h3>${c.title}</h3>
          </div>

          <div class="card-meta-row">
            <span class="card-meta-item">📍 ${c.address || 'Location Coordinates Pin'}</span>
            <span class="card-meta-item">🏛️ ${c.zone}</span>
            <span class="card-meta-item">📅 Reported: ${formatIsoDate(c.created_at)}</span>
          </div>

          <div class="sla-status-banner ${sla.className}">
            ${sla.html}
          </div>

          ${stepper}

          ${proofHtml}

          <div class="card-actions-bar">
            <button type="button" class="button button-sm button-secondary" onclick="window.citidyViewEvidence('${c.id}')">
              View Full Timeline & Evidence
            </button>
            ${isResolved ? `
              <button type="button" class="button button-sm button-danger" onclick="window.citidyOpenReopenModal('${c.id}')">
                Dispute / Reopen Complaint
              </button>
            ` : ''}
          </div>
        </article>
      `;
    }).join('');
  };

  const loadCitizenComplaints = async () => {
    if (!state.token) {
      state.citizenComplaints = [];
      renderCitizenComplaints();
      return;
    }
    const loading = $('citizenComplaintsLoading');
    if (loading) loading.style.display = 'flex';
    try {
      const res = await apiCall('/api/complaints');
      state.citizenComplaints = res.complaints || [];
      renderCitizenComplaints();
    } catch (err) {
      showToast('Could not fetch complaints from server.', true);
    } finally {
      if (loading) loading.style.display = 'none';
    }
  };

  // --------------------------------------------------------------------------
  // CITIZEN PROBLEM SUBMISSION WIZARD
  // --------------------------------------------------------------------------
  const setupCitizenReportWizard = () => {
    // Category selection
    const grid = $('categoryGrid');
    const reportCatInput = $('reportCategory');
    if (grid && reportCatInput) {
      grid.querySelectorAll('.cat-card').forEach((card) => {
        card.addEventListener('click', () => {
          grid.querySelectorAll('.cat-card').forEach(c => c.classList.remove('active'));
          card.classList.add('active');
          reportCatInput.value = card.dataset.category;
        });
      });
    }

    // Photo Dropzone
    const dropzone = $('photoDropzone');
    const fileInput = $('reportPhotoInput');
    const promptBox = $('dropzonePrompt');
    const previewBox = $('dropzonePreview');
    const previewImg = $('photoPreviewImg');
    const previewName = $('photoPreviewName');
    const btnRemove = $('btnRemovePhoto');

    const handleFile = (file) => {
      if (!file || !file.type.startsWith('image/')) {
        showToast('Please select a valid image file (JPG, PNG, WEBP).', true);
        return;
      }
      if (file.size > 15 * 1024 * 1024) {
        showToast('Image file exceeds 15MB limit.', true);
        return;
      }
      state.reportPhotoName = file.name;
      const reader = new FileReader();
      reader.onload = (e) => {
        state.reportPhotoBase64 = e.target.result;
        if (previewImg) previewImg.src = state.reportPhotoBase64;
        if (previewName) previewName.textContent = file.name;
        if (promptBox) promptBox.style.display = 'none';
        if (previewBox) previewBox.style.display = 'flex';
      };
      reader.readAsDataURL(file);
    };

    if (dropzone && fileInput) {
      dropzone.addEventListener('click', (e) => {
        if (e.target !== btnRemove) fileInput.click();
      });
      fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files[0]) handleFile(fileInput.files[0]);
      });
      dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
      dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
      dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
      });
    }

    if (btnRemove) {
      btnRemove.addEventListener('click', (e) => {
        e.stopPropagation();
        state.reportPhotoBase64 = null;
        state.reportPhotoName = null;
        if (fileInput) fileInput.value = '';
        if (promptBox) promptBox.style.display = 'flex';
        if (previewBox) previewBox.style.display = 'none';
      });
    }

    // Map coordinate picker
    const pickerCanvas = $('pickerMapCanvas');
    const pickerPin = $('pickerPinCrosshair');
    const coordsLabel = $('pickerCoordsLabel');
    const latInput = $('reportLat');
    const lonInput = $('reportLon');

    if (pickerCanvas) {
      pickerCanvas.addEventListener('click', (e) => {
        const rect = pickerCanvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const pctX = x / rect.width;
        const pctY = y / rect.height;

        // Map to realistic city bounding box
        const lat = (37.79 - (pctY * 0.08)).toFixed(6);
        const lon = (-122.48 + (pctX * 0.09)).toFixed(6);

        if (pickerPin) {
          pickerPin.style.left = `${pctX * 100}%`;
          pickerPin.style.top = `${pctY * 100}%`;
        }
        if (latInput) latInput.value = lat;
        if (lonInput) lonInput.value = lon;
        if (coordsLabel) coordsLabel.textContent = `Latitude: ${lat} · Longitude: ${lon}`;
      });
    }

    // Form submission
    const form = $('complaintForm');
    const successCard = $('reportSuccessCard');

    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!state.token) {
          showToast('Please sign in with a citizen account to submit a report.');
          openAuthModal('login');
          return;
        }

        const category = $('reportCategory')?.value;
        const title = $('reportTitle')?.value.trim();
        const description = $('reportDescription')?.value.trim();
        const address = $('reportAddress')?.value.trim();
        const zone = $('reportZone')?.value;
        const priority = $('reportPriority')?.value;
        const lat = parseFloat($('reportLat')?.value || '37.7749');
        const lon = parseFloat($('reportLon')?.value || '-122.4194');

        if (!title || !description || !address) {
          showToast('Please fill out all required fields.', true);
          return;
        }
        if (!state.reportPhotoBase64) {
          showToast('Please upload a photograph showing the issue.', true);
          return;
        }

        const btnSubmit = $('btnSubmitComplaint');
        if (btnSubmit) {
          btnSubmit.disabled = true;
          btnSubmit.textContent = 'Submitting Complaint…';
        }

        try {
          const res = await apiCall('/api/complaints', 'POST', {
            category,
            title,
            description,
            address,
            zone,
            priority,
            latitude: lat,
            longitude: lon,
            photoBase64: state.reportPhotoBase64,
            photoName: state.reportPhotoName || 'problem.jpg',
          });

          // Show success card
          if (form) form.style.display = 'none';
          if (successCard) {
            successCard.style.display = 'block';
            $('successComplaintId').textContent = res.complaintNumber;
            $('successTargetDate').textContent = formatIsoDate(res.estimatedResolutionAt);
          }

          showToast(`Complaint ${res.complaintNumber} recorded successfully!`);
          loadCitizenComplaints();
          loadNotifications();
        } catch (err) {
          showToast(err.message || 'Submission failed.', true);
        } finally {
          if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = `<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M2.5 10 17.5 3l-4 14-4-5.5L2.5 10z" fill="currentColor"/></svg> Submit Civic Complaint`;
          }
        }
      });
    }

    $('btnTrackNewComplaint')?.addEventListener('click', () => {
      if (form) form.style.display = 'block';
      if (successCard) successCard.style.display = 'none';
      switchCitizenTab('complaints');
    });

    $('btnSubmitAnother')?.addEventListener('click', () => {
      if (form) {
        form.reset();
        form.style.display = 'block';
      }
      if (successCard) successCard.style.display = 'none';
      state.reportPhotoBase64 = null;
      state.reportPhotoName = null;
      if (promptBox) promptBox.style.display = 'flex';
      if (previewBox) previewBox.style.display = 'none';
    });
  };

  // --------------------------------------------------------------------------
  // PUBLIC CITY ISSUE MAP
  // --------------------------------------------------------------------------
  const loadPublicMap = async () => {
    const pinsContainer = $('publicMapPinsContainer');
    const statsLabel = $('publicMapStats');
    if (!pinsContainer) return;

    try {
      const res = await apiCall('/api/map/complaints');
      state.mapComplaints = res.features || [];

      if (statsLabel) {
        statsLabel.textContent = `Displaying ${state.mapComplaints.length} civic complaints across all 20 municipal zones. Click any pin to inspect photographic proof.`;
      }

      pinsContainer.innerHTML = state.mapComplaints.map((c, i) => {
        // Map lat/lon to percentage position on canvas
        const pctX = Math.max(5, Math.min(95, ((c.longitude + 122.48) / 0.09) * 100));
        const pctY = Math.max(5, Math.min(95, ((37.79 - c.latitude) / 0.08) * 100));
        const statusCls = `status-${c.status.replace(/\s+/g, '-')}`;

        return `
          <div class="map-pin-marker ${statusCls}" style="left: ${pctX}%; top: ${pctY}%;" title="${c.complaint_number}: ${c.title}" onclick="window.citidyViewEvidence('${c.id}')">
            <div class="map-pin-icon">
              <span>📍</span>
            </div>
          </div>
        `;
      }).join('');
    } catch (_) {
      if (statsLabel) statsLabel.textContent = 'Public map preview loaded in offline simulated mode.';
    }
  };

  // --------------------------------------------------------------------------
  // IN-APP NOTIFICATIONS CENTER
  // --------------------------------------------------------------------------
  const loadNotifications = async () => {
    if (!state.token) {
      state.notifications = [];
      state.unreadNotifCount = 0;
      updateNotificationUI();
      return;
    }
    try {
      const res = await apiCall('/api/notifications');
      state.notifications = res.notifications || [];
      state.unreadNotifCount = res.unread_count || 0;
      updateNotificationUI();
    } catch (_) {}
  };

  const updateNotificationUI = () => {
    const badge = $('notifBadge');
    if (badge) {
      badge.textContent = state.unreadNotifCount;
      badge.style.display = state.unreadNotifCount > 0 ? 'flex' : 'none';
    }

    const list = $('notifListContainer');
    if (!list) return;

    if (!state.notifications.length) {
      list.innerHTML = `<div class="empty-state" style="padding: 24px; text-align: center; color: var(--text-muted);">No civic notifications received yet.</div>`;
      return;
    }

    list.innerHTML = state.notifications.map((n) => `
      <div class="notif-item ${n.is_read ? '' : 'unread'}" onclick="window.citidyReadNotif('${n.id}', '${n.complaint_id}')">
        <span class="notif-item-icon">${n.notification_type === 'resolved' ? '🎉' : n.notification_type === 'estimate_change' ? '⏱️' : '🔔'}</span>
        <div class="notif-item-body">
          <div class="notif-item-title">${n.title}</div>
          <div class="notif-item-msg">${n.message}</div>
          <div class="notif-item-time">${formatIsoDate(n.created_at)}</div>
        </div>
      </div>
    `).join('');
  };

  window.citidyReadNotif = async (notifId, complaintId) => {
    try {
      await apiCall(`/api/notifications/${notifId}/read`, 'POST');
      loadNotifications();
      if (complaintId) {
        $('notifModal')?.close();
        window.citidyViewEvidence(complaintId);
      }
    } catch (_) {}
  };

  $('btnMarkAllNotifsRead')?.addEventListener('click', async () => {
    try {
      await apiCall('/api/notifications/all/read', 'POST');
      loadNotifications();
      showToast('All notifications marked as read.');
    } catch (_) {}
  });

  // --------------------------------------------------------------------------
  // ADMIN OPERATIONS: TRIAGE, ASSIGNMENT & MANDATORY RESOLUTION
  // --------------------------------------------------------------------------
  const loadAdminStats = async () => {
    if (!state.token || state.user?.role !== 'admin') return;
    try {
      const stats = await apiCall('/api/admin/stats');
      if ($('kpiAdminTotal')) $('kpiAdminTotal').textContent = fmt.format(stats.total);
      if ($('kpiAdminSubmitted')) $('kpiAdminSubmitted').textContent = fmt.format(stats.submitted);
      if ($('kpiAdminInProgress')) $('kpiAdminInProgress').textContent = fmt.format(stats.in_progress);
      if ($('kpiAdminResolved')) $('kpiAdminResolved').textContent = fmt.format(stats.resolved);
      if ($('kpiAdminOverdue')) $('kpiAdminOverdue').textContent = fmt.format(stats.overdue);
      if ($('kpiAdminAvgDuration')) {
        $('kpiAdminAvgDuration').textContent = stats.avg_resolution_hours ? `${stats.avg_resolution_hours} hrs` : 'N/A';
      }
    } catch (_) {}
  };

  const loadAdminTriage = async () => {
    if (!state.token || state.user?.role !== 'admin') return;
    const query = new URLSearchParams();
    const searchVal = $('adminSearchInput')?.value.trim();
    const statusVal = $('adminStatusFilter')?.value;
    const zoneVal = $('adminZoneFilter')?.value;
    const catVal = $('adminCategoryFilter')?.value;

    if (searchVal) query.set('search', searchVal);
    if (statusVal && statusVal !== 'all') query.set('status', statusVal);
    if (zoneVal && zoneVal !== 'all') query.set('zone', zoneVal);
    if (catVal && catVal !== 'all') query.set('category', catVal);

    try {
      const res = await apiCall(`/api/complaints?${query.toString()}`);
      state.adminComplaints = res.complaints || [];
      renderAdminTriage();
    } catch (err) {
      showToast(err.message || 'Failed to load triage queue.', true);
    }
  };

  const renderAdminTriage = () => {
    const tbody = $('adminTriageRows');
    const badge = $('adminTriageCount');
    if (badge) badge.textContent = state.adminComplaints.length;
    if (!tbody) return;

    if (!state.adminComplaints.length) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 32px; color: var(--text-muted);">No complaints match the triage criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = state.adminComplaints.map((c) => {
      const photoSrc = c.after_photo || c.before_photo || 'favicon.svg';
      const isOverdue = c.is_overdue;
      return `
        <tr>
          <td><strong class="complaint-num-badge">${c.complaint_number}</strong></td>
          <td>
            <div class="table-thumb-frame" onclick="window.citidyViewImage('${photoSrc}')">
              <img src="${photoSrc}" alt="Thumbnail" loading="lazy">
            </div>
          </td>
          <td>
            <strong>${c.title}</strong><br>
            <small style="color: var(--text-muted);">${c.category}</small>
          </td>
          <td>
            <span>${c.address || '—'}</span><br>
            <small style="font-weight: 600; color: var(--primary);">${c.zone}</small>
          </td>
          <td><span class="priority-pill priority-${c.priority.toLowerCase()}">${c.priority}</span></td>
          <td>
            <span class="status-pill status-${c.status.replace(/\s+/g, '-')}">${c.status}</span>
            <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">${c.progress_percentage}% completed</div>
          </td>
          <td>
            <span style="font-size: 0.78rem;">${formatIsoDate(c.estimated_resolution_at)}</span>
            ${isOverdue ? `<br><strong class="text-danger" style="font-size: 0.7rem;">⚠️ OVERDUE</strong>` : ''}
          </td>
          <td>
            <div class="actions-btn-group">
              <button type="button" class="button button-xs button-secondary" onclick="window.citidyOpenAssignModal('${c.id}')" title="Assign Department">Assign</button>
              <button type="button" class="button button-xs button-secondary" onclick="window.citidyOpenEstimateModal('${c.id}')" title="Adjust Target Date">Date</button>
              <button type="button" class="button button-xs button-success" onclick="window.citidyOpenResolveModal('${c.id}')" title="Resolve with After Photo">Resolve</button>
              <button type="button" class="button button-xs button-secondary" onclick="window.citidyViewEvidence('${c.id}')" title="Audit Trail">View</button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  };

  // --------------------------------------------------------------------------
  // ADMIN MODALS: ASSIGNMENT, ESTIMATE & MANDATORY RESOLUTION
  // --------------------------------------------------------------------------
  window.citidyOpenAssignModal = (complaintId) => {
    $('assignComplaintId').value = complaintId;
    $('assignModal')?.showModal();
  };

  $('assignForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const cid = $('assignComplaintId').value;
    const department = $('assignDepartment').value;
    const assignedTo = $('assignWorker').value.trim();

    try {
      await apiCall(`/api/complaints/${cid}/status`, 'POST', {
        status: 'Assigned',
        progressPercentage: 30,
        department,
        assignedTo,
        note: `Assigned to ${department} (Lead: ${assignedTo})`,
      });
      $('assignModal')?.close();
      showToast('Department assigned and citizen notified.');
      loadAdminTriage();
      loadAdminStats();
    } catch (err) {
      showToast(err.message, true);
    }
  });

  window.citidyOpenEstimateModal = (complaintId) => {
    $('estimateComplaintId').value = complaintId;
    $('estimateNewDate').value = new Date(Date.now() + 86400000 * 4).toISOString().split('T')[0];
    $('estimateReason').value = '';
    $('estimateModal')?.showModal();
  };

  $('estimateForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const cid = $('estimateComplaintId').value;
    const newDate = $('estimateNewDate').value;
    const reason = $('estimateReason').value.trim();

    if (!newDate || !reason) {
      showToast('Both target date and reason are mandatory.', true);
      return;
    }

    try {
      await apiCall(`/api/complaints/${cid}/estimate`, 'POST', {
        newEstimate: new Date(newDate).toISOString(),
        reason,
      });
      $('estimateModal')?.close();
      showToast('Resolution estimate revised and logged to audit trail.');
      loadAdminTriage();
    } catch (err) {
      showToast(err.message, true);
    }
  });

  // MANDATORY RESOLUTION: Strictly requires AFTER photo & resolution notes
  window.citidyOpenResolveModal = (complaintId) => {
    $('resolveComplaintId').value = complaintId;
    state.resolvePhotoBase64 = null;
    state.resolvePhotoName = null;
    if ($('resolveNotes')) $('resolveNotes').value = '';
    if ($('resolveDropzonePrompt')) $('resolveDropzonePrompt').style.display = 'flex';
    if ($('resolveDropzonePreview')) $('resolveDropzonePreview').style.display = 'none';
    $('resolveModal')?.showModal();
  };

  // Setup resolve photo dropzone
  const resolveDropzone = $('resolvePhotoDropzone');
  const resolveFileInput = $('resolvePhotoInput');
  const resolvePrompt = $('resolveDropzonePrompt');
  const resolvePreview = $('resolveDropzonePreview');
  const resolveImg = $('resolvePreviewImg');
  const resolveName = $('resolvePreviewName');

  const handleResolveFile = (file) => {
    if (!file || !file.type.startsWith('image/')) {
      showToast('Please select a valid image file.', true);
      return;
    }
    state.resolvePhotoName = file.name;
    const reader = new FileReader();
    reader.onload = (e) => {
      state.resolvePhotoBase64 = e.target.result;
      if (resolveImg) resolveImg.src = state.resolvePhotoBase64;
      if (resolveName) resolveName.textContent = file.name;
      if (resolvePrompt) resolvePrompt.style.display = 'none';
      if (resolvePreview) resolvePreview.style.display = 'flex';
    };
    reader.readAsDataURL(file);
  };

  if (resolveDropzone && resolveFileInput) {
    resolveDropzone.addEventListener('click', (e) => {
      if (e.target !== $('btnRemoveResolvePhoto')) resolveFileInput.click();
    });
    resolveFileInput.addEventListener('change', () => {
      if (resolveFileInput.files && resolveFileInput.files[0]) handleResolveFile(resolveFileInput.files[0]);
    });
  }

  $('btnRemoveResolvePhoto')?.addEventListener('click', (e) => {
    e.stopPropagation();
    state.resolvePhotoBase64 = null;
    state.resolvePhotoName = null;
    if (resolveFileInput) resolveFileInput.value = '';
    if (resolvePrompt) resolvePrompt.style.display = 'flex';
    if (resolvePreview) resolvePreview.style.display = 'none';
  });

  $('resolveForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const cid = $('resolveComplaintId').value;
    const notes = $('resolveNotes').value.trim();

    if (!state.resolvePhotoBase64) {
      showToast('MANDATORY REQUIREMENT: You must upload the final resolution photograph before marking as resolved.', true);
      return;
    }
    if (!notes) {
      showToast('MANDATORY REQUIREMENT: Work description and resolution notes must be provided.', true);
      return;
    }

    const btn = $('btnSubmitResolve');
    if (btn) btn.disabled = true;

    try {
      await apiCall(`/api/complaints/${cid}/resolve`, 'POST', {
        photoBase64: state.resolvePhotoBase64,
        photoName: state.resolvePhotoName || 'resolution.jpg',
        resolutionNotes: notes,
      });
      $('resolveModal')?.close();
      showToast('Issue marked Resolved with verified photographic proof!');
      loadAdminTriage();
      loadAdminStats();
    } catch (err) {
      showToast(err.message, true);
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  // Dispute / Reopen resolution
  window.citidyOpenReopenModal = (complaintId) => {
    $('reopenComplaintId').value = complaintId;
    $('reopenReason').value = '';
    $('reopenModal')?.showModal();
  };

  $('reopenForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const cid = $('reopenComplaintId').value;
    const reason = $('reopenReason').value.trim();

    if (!reason) {
      showToast('Please provide a reason why this resolution is being disputed.', true);
      return;
    }

    try {
      await apiCall(`/api/complaints/${cid}/reopen`, 'POST', { reason });
      $('reopenModal')?.close();
      showToast('Complaint reopened for administrative review.');
      loadCitizenComplaints();
    } catch (err) {
      showToast(err.message, true);
    }
  });

  // --------------------------------------------------------------------------
  // COMPLAINT TIMELINE & EVIDENCE MODAL
  // --------------------------------------------------------------------------
  window.citidyViewEvidence = async (complaintId) => {
    const modal = $('evidenceModal');
    const title = $('evidenceModalTitle');
    const body = $('evidenceModalBody');
    if (!modal || !body) return;

    body.innerHTML = `<div class="loading-spinner-wrap"><div class="spinner"></div><span>Loading verified evidence and audit trail…</span></div>`;
    modal.showModal();

    try {
      const res = await apiCall(`/api/complaints/${complaintId}`);
      const c = res.complaint;
      if (title) title.textContent = `Complaint ${c.complaint_number}`;

      const historyHtml = (c.status_history || []).map(h => `
        <div style="display: flex; gap: 12px; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid var(--border-subtle); font-size: 0.82rem;">
          <span style="color: var(--primary); font-weight: 700;">${h.new_status}</span>
          <div style="flex: 1;">
            <div>${h.note || 'Status updated'}</div>
            <small style="color: var(--text-muted);">Recorded ${formatIsoDate(h.created_at)} by ${h.changed_by_name || 'System'}</small>
          </div>
        </div>
      `).join('') || '<p style="color: var(--text-muted);">No transition history recorded.</p>';

      const estimateHtml = (c.estimate_history || []).map(e => `
        <div style="background-color: var(--bg-subtle); padding: 8px 12px; border-radius: var(--radius-sm); margin-bottom: 8px; font-size: 0.8rem;">
          <strong>Target Revised:</strong> ${formatIsoDate(e.new_estimate)}<br>
          <span style="color: var(--text-muted);">Reason: ${e.reason}</span>
        </div>
      `).join('') || '<p style="color: var(--text-muted); font-size: 0.82rem;">Original target date maintained.</p>';

      body.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 20px;">
          <div>
            <h3 style="margin: 0 0 6px 0;">${c.title}</h3>
            <p style="color: var(--text-muted); font-size: 0.86rem; margin: 0;">${c.description}</p>
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
            <div>
              <span class="evidence-tag before">Initial Problem Photo</span>
              <div class="evidence-img-frame" style="height: 200px; margin-top: 6px;" onclick="window.citidyViewImage('${c.before_photo || 'favicon.svg'}')">
                <img src="${c.before_photo || 'favicon.svg'}" alt="Problem" style="width: 100%; height: 100%; object-fit: cover;">
              </div>
            </div>
            <div>
              <span class="evidence-tag after">Final Resolution Photo</span>
              <div class="evidence-img-frame" style="height: 200px; margin-top: 6px;" onclick="window.citidyViewImage('${c.after_photo || 'favicon.svg'}')">
                ${c.after_photo ? `<img src="${c.after_photo}" alt="Resolution" style="width: 100%; height: 100%; object-fit: cover;">` : '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #94a3b8; font-size: 0.8rem;">Pending Resolution Verification</div>'}
              </div>
            </div>
          </div>

          <div>
            <h4 style="margin: 0 0 8px 0; font-size: 0.95rem;">Milestone Audit Trail</h4>
            <div style="background-color: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px;">
              ${historyHtml}
            </div>
          </div>

          <div>
            <h4 style="margin: 0 0 8px 0; font-size: 0.95rem;">Target Date Revisions & Reasons</h4>
            ${estimateHtml}
          </div>
        </div>
      `;
    } catch (err) {
      body.innerHTML = `<p style="color: var(--danger);">Failed to load complaint details: ${err.message}</p>`;
    }
  };

  window.citidyViewImage = (src) => {
    window.open(src, '_blank');
  };

  // --------------------------------------------------------------------------
  // AUTH MODAL LISTENERS & 1-CLICK DEMO FILL
  // --------------------------------------------------------------------------
  const openAuthModal = (mode = 'login') => {
    const modal = $('authModal');
    const tabLogin = $('btnTabLogin');
    const tabRegister = $('btnTabRegister');
    const loginForm = $('loginForm');
    const registerForm = $('registerForm');
    const modalTitle = $('authModalTitle');

    if (mode === 'login') {
      if (tabLogin) tabLogin.classList.add('active');
      if (tabRegister) tabRegister.classList.remove('active');
      if (loginForm) loginForm.style.display = 'flex';
      if (registerForm) registerForm.style.display = 'none';
      if (modalTitle) modalTitle.textContent = 'Citizen Sign In';
    } else {
      if (tabLogin) tabLogin.classList.remove('active');
      if (tabRegister) tabRegister.classList.add('active');
      if (loginForm) loginForm.style.display = 'none';
      if (registerForm) registerForm.style.display = 'flex';
      if (modalTitle) modalTitle.textContent = 'Register Citizen Account';
    }
    modal?.showModal();
  };

  $('btnTabLogin')?.addEventListener('click', () => openAuthModal('login'));
  $('btnTabRegister')?.addEventListener('click', () => openAuthModal('register'));
  $('closeAuthModal')?.addEventListener('click', () => $('authModal')?.close());

  $('userChipBtn')?.addEventListener('click', () => {
    if (state.user) {
      const drop = $('userDropdown');
      if (drop) drop.style.display = drop.style.display === 'none' ? 'block' : 'none';
    } else {
      openAuthModal('login');
    }
  });

  $('dropdownLogout')?.addEventListener('click', () => {
    $('userDropdown').style.display = 'none';
    clearSession();
  });

  $('btnPromptCitizenLogin')?.addEventListener('click', () => openAuthModal('login'));

  // 1-Click Demo Citizen
  $('btnFillDemoCitizen')?.addEventListener('click', async () => {
    $('loginEmail').value = 'citizen@citidy.gov';
    $('loginPassword').value = 'Citizen2026!';
    $('loginForm').dispatchEvent(new Event('submit'));
  });

  $('btnUseDemoCitizen')?.addEventListener('click', async () => {
    $('loginEmail').value = 'citizen@citidy.gov';
    $('loginPassword').value = 'Citizen2026!';
    $('loginForm').dispatchEvent(new Event('submit'));
  });

  // Citizen Login Submit
  $('loginForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = $('loginEmail').value.trim();
    const password = $('loginPassword').value;

    if (!email || !password) {
      showToast('Please enter both email and password.', true);
      return;
    }

    const btn = $('btnLoginSubmit');
    const prevText = btn ? btn.textContent : '';
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Signing in…';
    }

    try {
      const res = await performLogin(email, password);
      setSession(res.token, res.user);
      try {
        localStorage.setItem('citidy_last_portal', 'citizen');
      } catch (_) {}
      $('authModal')?.close();
      showToast(`Welcome back, ${res.user.fullName}!`);
    } catch (err) {
      console.error('[Citidy Auth Error] Citizen sign in failed:', err.message);
      showToast(err.message || 'Login failed.', true);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = prevText || 'Sign In to Citidy';
      }
    }
  });

  // Citizen Register Submit
  $('registerForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fullName = $('regFullName').value.trim();
    const email = $('regEmail').value.trim();
    const phone = $('regPhone').value.trim();
    const password = $('regPassword').value;

    if (!fullName || !email || !password) {
      showToast('Full name, email, and password are required.', true);
      return;
    }

    const btn = $('btnRegisterSubmit');
    const prevText = btn ? btn.textContent : '';
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Creating account…';
    }

    try {
      const res = await apiCall('/api/auth/register', 'POST', { fullName, email, phone, password });
      setSession(res.token, res.user);
      try {
        localStorage.setItem('citidy_last_portal', 'citizen');
      } catch (_) {}
      $('authModal')?.close();
      showToast(`Account created! Welcome to Citidy, ${fullName}.`);
    } catch (err) {
      console.error('[Citidy Auth Error] Registration failed:', err.message);
      showToast(err.message || 'Registration failed.', true);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = prevText || 'Create Citizen Account';
      }
    }
  });

  // Admin Login Guard Form Submit
  $('adminLoginForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = $('adminLoginEmail').value.trim();
    const password = $('adminLoginPassword').value;

    if (!email || !password) {
      showToast('Please enter both staff email and password.', true);
      return;
    }

    const btn = $('btnAdminLoginSubmit');
    const prevText = btn ? btn.textContent : '';
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Verifying Administrative Credentials…';
    }

    try {
      const res = await performLogin(email, password);

      // Strict role verification: Role MUST be verified as 'admin'
      if (!res.user || res.user.role !== 'admin') {
        showToast('Access Denied: This account is registered as a Citizen and does not possess municipal administrator privileges.', true);
        return;
      }

      setSession(res.token, res.user);
      try {
        localStorage.setItem('citidy_last_portal', 'admin');
      } catch (_) {}
      showToast(`Administrative privileges verified. Welcome, ${res.user.fullName}!`);
      switchPortal('admin');
    } catch (err) {
      console.error('[Citidy Auth Error] Admin login failed:', err.message);
      showToast(err.message || 'Admin login failed.', true);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = prevText || 'Authorize Administrative Access';
      }
    }
  });

  // Subnavigation event listeners
  $('btnSwitchCitizen')?.addEventListener('click', () => switchPortal('citizen'));
  $('btnSwitchAdmin')?.addEventListener('click', () => switchPortal('admin'));

  $('tabCitizenComplaints')?.addEventListener('click', () => switchCitizenTab('complaints'));
  $('tabCitizenReport')?.addEventListener('click', () => switchCitizenTab('report'));
  $('tabCitizenMap')?.addEventListener('click', () => switchCitizenTab('map'));
  $('btnQuickReport')?.addEventListener('click', () => switchCitizenTab('report'));
  $('dropdownMyReports')?.addEventListener('click', () => {
    $('userDropdown').style.display = 'none';
    switchPortal('citizen');
    switchCitizenTab('complaints');
  });
  $('dropdownNewReport')?.addEventListener('click', () => {
    $('userDropdown').style.display = 'none';
    switchPortal('citizen');
    switchCitizenTab('report');
  });

  $('tabAdminTriage')?.addEventListener('click', () => switchAdminTab('triage'));
  $('tabAdminQueue')?.addEventListener('click', () => switchAdminTab('queue'));
  $('tabAdminAnalytics')?.addEventListener('click', () => switchAdminTab('analytics'));
  $('tabAdminLimitations')?.addEventListener('click', () => switchAdminTab('limitations'));

  $('notifBellBtn')?.addEventListener('click', () => {
    loadNotifications();
    $('notifModal')?.showModal();
  });
  $('closeNotifModal')?.addEventListener('click', () => $('notifModal')?.close());

  // Close modals
  $('closeEvidenceModal')?.addEventListener('click', () => $('evidenceModal')?.close());
  $('closeAssignModal')?.addEventListener('click', () => $('assignModal')?.close());
  $('closeEstimateModal')?.addEventListener('click', () => $('estimateModal')?.close());
  $('closeResolveModal')?.addEventListener('click', () => $('resolveModal')?.close());
  $('closeReopenModal')?.addEventListener('click', () => $('reopenModal')?.close());

  // Filter pills in citizen complaints
  document.querySelectorAll('.filter-pill').forEach((pill) => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.complaintFilter = pill.dataset.filter;
      renderCitizenComplaints();
    });
  });

  // Admin filter inputs
  $('adminSearchInput')?.addEventListener('input', () => loadAdminTriage());
  $('adminStatusFilter')?.addEventListener('change', () => loadAdminTriage());
  $('adminZoneFilter')?.addEventListener('change', () => loadAdminTriage());
  $('adminCategoryFilter')?.addEventListener('change', () => loadAdminTriage());
  $('btnAdminRefresh')?.addEventListener('click', () => {
    loadAdminTriage();
    loadAdminStats();
    showToast('Triage queue refreshed.');
  });

  // --------------------------------------------------------------------------
  // PRESERVED MUNICIPAL PRIORITY QUEUE (CITYFIX AI ENGINE)
  // --------------------------------------------------------------------------
  const getFilteredRows = () => {
    return locations.filter((loc) => {
      if (state.zone !== 'all' && loc.zone !== state.zone) return false;
      if (state.issue !== 'all' && (loc.incidentTypes[state.issue] || 0) === 0) return false;
      if (state.severity !== 'all') {
        if (state.severity === 'Critical' && (loc.severityDistribution?.Critical || 0) === 0) return false;
        if (state.severity === 'High' && (loc.severityDistribution?.High || 0) === 0) return false;
        if (state.severity === 'Medium' && (loc.severityDistribution?.Medium || 0) === 0) return false;
        if (state.severity === 'Low' && (loc.severityDistribution?.Low || 0) === 0) return false;
      }
      if (state.search) {
        const query = state.search;
        const haystack = `${loc.id} ${loc.zone} ${loc.road} ${loc.condition} ${loc.topIssue}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
  };

  const getSortedRows = (rows) => {
    return [...rows].sort((a, b) => {
      let valA, valB;
      switch (state.sortField) {
        case 'id': valA = a.id; valB = b.id; break;
        case 'zone': valA = a.zone; valB = b.zone; break;
        case 'priority': valA = a.priority; valB = b.priority; break;
        case 'incidents': valA = a.incidentCount; valB = b.incidentCount; break;
        case 'severity': valA = a.avgSeverity; valB = b.avgSeverity; break;
        case 'complaints': valA = a.complaintCount; valB = b.complaintCount; break;
        case 'backlog': valA = a.openWork; valB = b.openWork; break;
        default: valA = a.priority; valB = b.priority;
      }
      if (typeof valA === 'string') {
        return state.sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return state.sortAsc ? valA - valB : valB - valA;
    });
  };

  const currentRows = () => getSortedRows(getFilteredRows());

  const renderKpis = (rows) => {
    const totalLocations = locations.length;
    const viewLocations = rows.length;
    const totalIncidents = rows.reduce((sum, r) => sum + r.incidentCount, 0);
    const totalComplaints = rows.reduce((sum, r) => sum + r.complaintCount, 0);
    const totalOpen = rows.reduce((sum, r) => sum + r.openWork, 0);

    if ($('metricLocations')) $('metricLocations').textContent = fmt.format(viewLocations);
    if ($('metricLocationShare')) {
      const share = totalLocations ? Math.round((viewLocations / totalLocations) * 100) : 0;
      $('metricLocationShare').textContent = `${share}% of municipal locations`;
    }
    if ($('metricIncidents')) $('metricIncidents').textContent = fmt.format(totalIncidents);
    if ($('metricIncidentDetails')) {
      const avgInc = viewLocations ? (totalIncidents / viewLocations).toFixed(1) : 0;
      $('metricIncidentDetails').textContent = `avg ${avgInc} incidents / location`;
    }
    if ($('metricComplaints')) $('metricComplaints').textContent = fmt.format(totalComplaints);
    if ($('metricComplaintDetails')) {
      const avgComp = viewLocations ? (totalComplaints / viewLocations).toFixed(1) : 0;
      $('metricComplaintDetails').textContent = `avg ${avgComp} citizen reports`;
    }
    if ($('metricOpen')) $('metricOpen').textContent = fmt.format(totalOpen);
    if ($('metricOpenDetails')) {
      const avgBacklog = viewLocations ? (totalOpen / viewLocations).toFixed(1) : 0;
      $('metricOpenDetails').textContent = `avg backlog ${avgBacklog} open items`;
    }
    if (matchingCount) matchingCount.textContent = fmt.format(viewLocations);
  };

  const renderQueue = (rows) => {
    const queueRows = $('queueRows');
    const queuePageInfo = $('queuePageInfo');
    const prevPage = $('prevPage');
    const nextPage = $('nextPage');
    if (!queueRows) return;

    if (!rows.length) {
      queueRows.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 32px; color: var(--text-muted);">No locations match current filters.</td></tr>`;
      if (queuePageInfo) queuePageInfo.textContent = '0 locations';
      if (prevPage) prevPage.disabled = true;
      if (nextPage) nextPage.disabled = true;
      return;
    }

    const pageSize = state.pageSize === 'all' ? rows.length : parseInt(state.pageSize, 10);
    const totalPages = Math.ceil(rows.length / pageSize);
    state.currentPage = Math.min(state.currentPage, totalPages);
    const startIdx = (state.currentPage - 1) * pageSize;
    const pageRows = rows.slice(startIdx, startIdx + pageSize);

    if (queuePageInfo) {
      queuePageInfo.textContent = `Showing ${fmt.format(startIdx + 1)}–${fmt.format(Math.min(startIdx + pageSize, rows.length))} of ${fmt.format(rows.length)} locations`;
    }
    if (prevPage) prevPage.disabled = state.currentPage <= 1;
    if (nextPage) nextPage.disabled = state.currentPage >= totalPages;

    if (!state.selected || !rows.find(x => x.id === state.selected)) {
      state.selected = pageRows[0]?.id || null;
    }

    queueRows.innerHTML = pageRows.map((loc) => {
      const isSel = loc.id === state.selected;
      const dec = reviewDecisions[loc.id];
      const decBadge = dec
        ? `<span class="decision-pill status-${dec.status}">${dec.status}</span>`
        : `<span class="decision-pill status-unreviewed">Review</span>`;

      return `
        <tr class="queue-row ${isSel ? 'selected' : ''}" data-id="${loc.id}">
          <td class="cell-id"><strong>${loc.id}</strong></td>
          <td class="cell-zone">${loc.zone.replace('_', ' ')}</td>
          <td class="cell-priority"><span class="priority-badge ${scoreClass(loc.priority)}">${loc.priority}</span></td>
          <td class="cell-num">${loc.incidentCount}</td>
          <td class="cell-num">${loc.avgSeverity.toFixed(2)}</td>
          <td class="cell-num">${loc.complaintCount}</td>
          <td class="cell-num">${loc.openWork}</td>
          <td class="cell-status">${decBadge}</td>
        </tr>
      `;
    }).join('');

    queueRows.querySelectorAll('.queue-row').forEach((row) => {
      row.addEventListener('click', () => {
        state.selected = row.dataset.id;
        queueRows.querySelectorAll('.queue-row').forEach(r => r.classList.remove('selected'));
        row.classList.add('selected');
        const loc = locations.find(x => x.id === state.selected);
        if (loc) renderDetail(loc);
      });
    });

    const selLoc = locations.find(x => x.id === state.selected);
    if (selLoc) renderDetail(selLoc);
  };

  const renderDetail = (loc) => {
    if ($('detailLocationId')) $('detailLocationId').textContent = `${loc.id} · ${loc.zone.replace('_', ' ')}`;
    if ($('detailAddress')) $('detailAddress').textContent = `${loc.road} (${loc.condition} condition, ${loc.pedestrian} pedestrian traffic)`;
    if ($('detailPriority')) {
      $('detailPriority').textContent = loc.priority;
      $('detailPriority').className = `priority-val ${scoreClass(loc.priority)}`;
    }

    const factorBars = $('detailFactorBars');
    if (factorBars) {
      factorBars.innerHTML = loc.factorPoints.map((pts, idx) => `
        <div class="factor-breakdown-row">
          <div class="factor-breakdown-meta">
            <span>${factorLabels[idx]}</span>
            <strong>${pts} pts</strong>
          </div>
          <div class="factor-progress-track">
            <div class="factor-progress-bar" style="width: ${(pts / (weights[idx] * 100)) * 100}%;"></div>
          </div>
        </div>
      `).join('');
    }

    const reasonsList = $('detailReasons');
    if (reasonsList) {
      const signals = [
        `${loc.incidentCount} incidents recorded (Historical rate: ${loc.incidentCount} reports)`,
        `Average incident severity rating: ${loc.avgSeverity.toFixed(2)} / 4.0`,
        `${loc.complaintCount} verified citizen complaints filed`,
        `${loc.openWork} total open work items (${loc.unresolved} unresolved incidents + ${loc.openComplaints} active complaints)`,
        `Road condition assessed as ${loc.condition} with ${loc.pedestrian.toLowerCase()} pedestrian activity`,
      ];
      if (loc.school) signals.push('High-risk sensitive zone: Located within 250m of an active school');
      if (loc.hospital) signals.push('Emergency route priority: Located within 500m of a municipal hospital');
      reasonsList.innerHTML = signals.map(s => `<li>${s}</li>`).join('');
    }

    const dec = reviewDecisions[loc.id] || { status: 'pending', notes: '' };
    if ($('decisionSelect')) $('decisionSelect').value = dec.status || 'pending';
    if ($('decisionNotes')) $('decisionNotes').value = dec.notes || '';

    // Update map link and label
    const latVal = typeof loc.lat === 'number' ? loc.lat : typeof loc.latitude === 'number' ? loc.latitude : 0;
    const lonVal = typeof loc.lon === 'number' ? loc.lon : typeof loc.longitude === 'number' ? loc.longitude : 0;
    if ($('mapCoordinates')) {
      $('mapCoordinates').textContent = `Latitude: ${latVal.toFixed(6)}, Longitude: ${lonVal.toFixed(6)}`;
    }
    if ($('googleMapsLink')) {
      $('googleMapsLink').href = `https://www.google.com/maps/search/?api=1&query=${latVal},${lonVal}`;
    }
  };

  const saveReviewDecision = () => {
    if (!state.selected) return;
    const status = $('decisionSelect')?.value || 'pending';
    const notes = $('decisionNotes')?.value.trim() || '';

    reviewDecisions[state.selected] = {
      status,
      notes,
      updatedAt: new Date().toISOString(),
    };

    try {
      localStorage.setItem(reviewStorageKey, JSON.stringify(reviewDecisions));
    } catch (_) {}

    const statusMsg = $('decisionStatusMessage');
    if (statusMsg) {
      statusMsg.textContent = `Decision saved for ${state.selected}`;
      statusMsg.style.display = 'block';
      setTimeout(() => { statusMsg.style.display = 'none'; }, 3000);
    }
    renderQueue(currentRows());
  };

  const renderZoneLeaders = () => {
    const tbody = $('zoneLeadersRows');
    if (!tbody) return;

    const zoneStats = {};
    locations.forEach((loc) => {
      if (!zoneStats[loc.zone]) {
        zoneStats[loc.zone] = { locations: 0, incidents: 0, complaints: 0, backlog: 0 };
      }
      zoneStats[loc.zone].locations++;
      zoneStats[loc.zone].incidents += loc.incidentCount;
      zoneStats[loc.zone].complaints += loc.complaintCount;
      zoneStats[loc.zone].backlog += loc.openWork;
    });

    const sortedZones = Object.entries(zoneStats).sort((a, b) => b[1].incidents - a[1].incidents);
    tbody.innerHTML = sortedZones.map(([z, s]) => `
      <tr>
        <td><strong>${z.replace('_', ' ')}</strong></td>
        <td>${s.locations}</td>
        <td>${fmt.format(s.incidents)}</td>
        <td>${fmt.format(s.complaints)}</td>
        <td><strong>${fmt.format(s.backlog)}</strong></td>
      </tr>
    `).join('');
  };

  const renderBriefing = (rows) => {
    const el = $('briefingText');
    if (!el) return;
    const total = rows.length;
    if (!total) {
      el.textContent = 'No locations currently in scope. Try resetting exploration filters.';
      return;
    }
    const avgScore = (rows.reduce((sum, r) => sum + r.priority, 0) / total).toFixed(1);
    const topLoc = [...rows].sort((a, b) => b.priority - a.priority)[0];
    const highSevCount = rows.filter(r => (r.severityDistribution?.Critical || 0) > 0 || (r.severityDistribution?.High || 0) > 0).length;

    el.innerHTML = `
      Viewing <strong>${fmt.format(total)}</strong> locations with an average priority score of <strong>${avgScore}</strong>.
      Top ranked item is <strong>${topLoc.id}</strong> in ${topLoc.zone.replace('_', ' ')} (Score: ${topLoc.priority}).
      <strong>${fmt.format(highSevCount)}</strong> locations currently report High or Critical active hazards.
    `;
  };

  // Assistant Question Answering
  const answerQuestion = (query) => {
    const q = (query || '').toLowerCase().trim();
    const box = $('assistantResponse');
    const content = $('assistantResponseContent');
    if (!box || !content) return;

    box.style.display = 'block';

    if (q.includes('top priority') || q.includes('highest priority') || q.includes('fix first')) {
      const top = [...locations].sort((a, b) => b.priority - a.priority).slice(0, 5);
      content.innerHTML = `
        <strong>Top 5 Priority Locations:</strong>
        <ol style="margin: 8px 0 0 18px; padding: 0;">
          ${top.map(l => `<li><strong>${l.id}</strong> (${l.zone.replace('_', ' ')}): Priority ${l.priority} · ${l.road} (${l.openWork} open items)</li>`).join('')}
        </ol>
      `;
    } else if (q.includes('zone') || q.includes('most recorded')) {
      const zCounts = {};
      locations.forEach(l => { zCounts[l.zone] = (zCounts[l.zone] || 0) + l.incidentCount; });
      const topZ = Object.entries(zCounts).sort((a, b) => b[1] - a[1])[0];
      content.innerHTML = `<strong>Zone with highest incidents:</strong> ${topZ[0].replace('_', ' ')} with ${fmt.format(topZ[1])} total incidents across its municipal sectors.`;
    } else if (q.includes('backlog') || q.includes('unresolved')) {
      const totalUnres = locations.reduce((s, l) => s + l.unresolved, 0);
      const topBacklog = [...locations].sort((a, b) => b.unresolved - a.unresolved).slice(0, 3);
      content.innerHTML = `
        There are <strong>${fmt.format(totalUnres)}</strong> unresolved incident work orders across the city.
        Top backlog locations: ${topBacklog.map(l => `<strong>${l.id}</strong> (${l.unresolved} open)`).join(', ')}.
      `;
    } else if (q.includes('complaints') || q.includes('citizen')) {
      const totalComp = locations.reduce((s, l) => s + l.complaintCount, 0);
      const totalOpenComp = locations.reduce((s, l) => s + l.openComplaints, 0);
      content.innerHTML = `Citizens have submitted <strong>${fmt.format(totalComp)}</strong> total complaints, with <strong>${fmt.format(totalOpenComp)}</strong> currently pending field resolution.`;
    } else if (q.includes('model') || q.includes('baseline') || q.includes('ml')) {
      content.innerHTML = `
        <strong>Machine Learning Evaluation:</strong> The 36-tree Random Forest achieves Holdout MAE of <strong>1.260</strong> vs the Mean Baseline MAE of <strong>1.255</strong>.
        Because synthetic quarterly incident counts follow a Poisson distribution, machine learning models achieve parity with historical mean baselines.
      `;
    } else {
      content.innerHTML = `
        Citidy analyzes 1,000 municipal locations across 20 zones, combining incident severity, citizen complaints, and street risk context into an auditable 0–100 priority index.
      `;
    }
  };

  // CSV Exporters
  const exportPriorityQueue = () => {
    const rows = currentRows();
    const headers = ['Location_ID', 'Zone', 'Road', 'Condition', 'Pedestrian', 'Incidents', 'Avg_Severity', 'Complaints', 'Open_Backlog', 'Priority_Score'];
    const csvContent = [headers.join(',')].concat(
      rows.map(r => [r.id, r.zone, `"${r.road}"`, r.condition, r.pedestrian, r.incidentCount, r.avgSeverity.toFixed(2), r.complaintCount, r.openWork, r.priority].join(','))
    ).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `citidy_priority_queue_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
  };

  const exportDecisionLog = () => {
    const entries = Object.entries(reviewDecisions);
    if (!entries.length) {
      showToast('No review decisions have been logged yet.');
      return;
    }
    const headers = ['Location_ID', 'Status', 'Notes', 'Updated_At'];
    const csvContent = [headers.join(',')].concat(
      entries.map(([id, d]) => [id, d.status, `"${(d.notes || '').replace(/"/g, '""')}"`, d.updatedAt].join(','))
    ).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `citidy_decision_log_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
  };

  // Filter Event Handlers
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      state.search = e.target.value.toLowerCase().trim();
      state.currentPage = 1;
      render();
    });
  }

  if (zoneFilter) {
    zoneFilter.addEventListener('change', (e) => {
      state.zone = e.target.value;
      state.currentPage = 1;
      render();
    });
  }

  if (issueFilter) {
    issueFilter.addEventListener('change', (e) => {
      state.issue = e.target.value;
      state.currentPage = 1;
      render();
    });
  }

  if (severityFilter) {
    severityFilter.addEventListener('change', (e) => {
      state.severity = e.target.value;
      state.currentPage = 1;
      render();
    });
  }

  $('resetFilters')?.addEventListener('click', () => {
    state.zone = 'all';
    state.issue = 'all';
    state.severity = 'all';
    state.search = '';
    state.currentPage = 1;
    if (zoneFilter) zoneFilter.value = 'all';
    if (issueFilter) issueFilter.value = 'all';
    if (severityFilter) severityFilter.value = 'all';
    if (searchInput) searchInput.value = '';
    render();
  });

  // Table sorting headers
  document.querySelectorAll('th.sortable').forEach((th) => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (state.sortField === field) {
        state.sortAsc = !state.sortAsc;
      } else {
        state.sortField = field;
        state.sortAsc = false;
      }
      render();
    });
  });

  // Pagination buttons
  $('prevPage')?.addEventListener('click', () => {
    if (state.currentPage > 1) {
      state.currentPage--;
      renderQueue(currentRows());
    }
  });

  $('nextPage')?.addEventListener('click', () => {
    const totalPages = Math.ceil(currentRows().length / state.pageSize);
    if (state.currentPage < totalPages) {
      state.currentPage++;
      renderQueue(currentRows());
    }
  });

  $('saveDecision')?.addEventListener('click', saveReviewDecision);
  $('exportTop')?.addEventListener('click', exportPriorityQueue);
  $('exportActions')?.addEventListener('click', exportDecisionLog);

  // Assistant query form
  $('assistantForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    answerQuestion($('assistantInput')?.value);
  });

  $('closeAssistantResponse')?.addEventListener('click', () => {
    if ($('assistantResponse')) $('assistantResponse').style.display = 'none';
  });

  document.querySelectorAll('.ask-suggestions button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const q = btn.dataset.question;
      if ($('assistantInput')) $('assistantInput').value = q;
      answerQuestion(q);
    });
  });

  // Scoring Method Dialog
  const methodDialog = $('methodDialog');
  $('methodButton')?.addEventListener('click', () => {
    if (methodDialog) {
      if (methodDialog.showModal) methodDialog.showModal();
      else methodDialog.setAttribute('open', '');
    }
  });

  $('closeMethodDialog')?.addEventListener('click', () => {
    if (methodDialog) {
      if (methodDialog.close) methodDialog.close();
      else methodDialog.removeAttribute('open');
    }
  });

  // Main Render of Municipal Operations
  const render = () => {
    const filtered = currentRows();
    renderKpis(filtered);
    renderQueue(filtered);
    renderBriefing(filtered);
    renderZoneLeaders();
  };

  // --------------------------------------------------------------------------
  // INITIAL STARTUP & DATA SYNCHRONIZATION
  // --------------------------------------------------------------------------
  const loadUserData = async () => {
    if (state.token) {
      try {
        const res = await apiCall('/api/auth/me');
        state.user = res.user;
        try {
          localStorage.setItem(userStorageKey, JSON.stringify(res.user));
        } catch (_) {}
      } catch (_) {
        // If token expired or invalid, clear session
        state.token = null;
        state.user = null;
        try {
          localStorage.removeItem(tokenStorageKey);
          localStorage.removeItem(userStorageKey);
          localStorage.removeItem('citidy_last_portal');
        } catch (_) {}
      }
    }
    updateAuthUI();

    // Restore active portal on page refresh if authorized
    try {
      const lastPortal = localStorage.getItem('citidy_last_portal');
      if (lastPortal === 'admin' && state.user && state.user.role === 'admin') {
        switchPortal('admin');
      } else {
        switchPortal('citizen');
      }
    } catch (_) {}

    loadNotifications();
    loadCitizenComplaints();
    loadPublicMap();
  };

  // Initial execution
  render();
  setupCitizenReportWizard();
  loadUserData();

  // Background notification check every 30 seconds
  if (typeof setInterval !== 'undefined') {
    setInterval(() => {
      if (state.token) loadNotifications();
    }, 30000);
  }

})();