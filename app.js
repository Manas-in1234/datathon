/**
 * CityFix AI — Clean Modern Light Theme Client Application
 * ========================================================
 * Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)
 */

// Application State
let appData = {
  summary: null,
  locations: [],
  selectedLocation: null,
  map: null,
  markersLayer: null,
  markersMap: new Map(),
  currentPage: 1,
  pageSize: 25,
  filteredLocations: [],
};

// Color Palette Constants
const THEME_COLORS = {
  critical: "#DC2626",
  high: "#EA580C",
  medium: "#D97706",
  low: "#16A34A",
  primary: "#2563EB",
  secondary: "#64748B",
};

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", async () => {
  setupNavigation();
  setupFilterListeners();
  setupAiConsole();
  await loadDashboardData();
  renderDashboard();
  renderTable();
  initMap();
  populateLocationSelect();
  
  // Select top ranked location by default
  const defaultLoc = appData.locations[0]?.location_id || "L0965";
  selectLocation(defaultLoc);
});

/**
 * Load dashboard data from REST API or fallback to precomputed JSON.
 */
async function loadDashboardData() {
  const tryPaths = [
    "/api/stats",
    "reports/dashboard_data.json",
    "data/dashboard_data.json",
  ];

  for (const path of tryPaths) {
    try {
      if (path === "/api/stats") {
        const statsRes = await fetch("/api/stats");
        const locRes = await fetch("/api/locations");
        if (statsRes.ok && locRes.ok) {
          appData.summary = await statsRes.json();
          appData.locations = await locRes.json();
          appData.filteredLocations = [...appData.locations];
          console.log("[CityFix AI] Loaded data via dynamic REST API");
          return;
        }
      } else {
        const res = await fetch(path);
        if (res.ok) {
          const payload = await res.json();
          appData.summary = payload.summary;
          appData.locations = payload.locations;
          appData.filteredLocations = [...appData.locations];
          console.log(`[CityFix AI] Loaded data via static JSON: ${path}`);
          return;
        }
      }
    } catch (e) {
      // Continue to next fallback
    }
  }

  console.error("[CityFix AI] Could not load dashboard payload from any source.");
}

/**
 * Navigation and Smooth Scroll Setup
 */
function setupNavigation() {
  const links = document.querySelectorAll(".nav-link");
  links.forEach((link) => {
    link.addEventListener("click", (e) => {
      links.forEach((l) => l.classList.remove("active"));
      link.classList.add("active");
    });
  });

  // Track scroll position to update active nav link
  window.addEventListener("scroll", () => {
    const sections = ["section-dashboard", "section-matrix", "section-evidence", "section-map", "section-analytics", "section-ai", "section-methodology"];
    let current = "";
    sections.forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        const rect = el.getBoundingClientRect();
        if (rect.top <= 120 && rect.bottom >= 120) {
          current = id;
        }
      }
    });

    if (current) {
      links.forEach((link) => {
        link.classList.toggle("active", link.getAttribute("href") === `#${current}`);
      });
    }
  }, { passive: true });
}

/**
 * Backward compatibility helper for switchTab calls.
 */
function switchTab(tabId) {
  const targetMap = {
    "tab-dashboard": "section-dashboard",
    "tab-rankings": "section-matrix",
    "tab-evidence": "section-evidence",
    "tab-map": "section-map",
    "tab-ai": "section-ai",
    "tab-methodology": "section-methodology",
  };
  const targetId = targetMap[tabId] || tabId;
  const el = document.getElementById(targetId);
  if (el) {
    el.scrollIntoView({ behavior: "smooth" });
  }
}

/**
 * Render Executive Dashboard KPI metrics and distributions.
 */
function renderDashboard() {
  if (!appData.summary) return;
  const s = appData.summary;

  // 4 Primary KPI Numbers
  const locEl = document.getElementById("kpi-locations");
  const incEl = document.getElementById("kpi-incidents");
  const compEl = document.getElementById("kpi-complaints");
  const critEl = document.getElementById("kpi-critical-hotspots");

  if (locEl) locEl.textContent = s.total_locations.toLocaleString();
  if (incEl) incEl.textContent = s.total_incidents.toLocaleString();
  if (compEl) compEl.textContent = s.total_complaints.toLocaleString();
  if (critEl) critEl.textContent = (s.priority_tiers?.Critical || 53).toLocaleString();

  // Populate Zone dropdown
  const zoneSelect = document.getElementById("filter-zone");
  if (zoneSelect && s.zones) {
    zoneSelect.innerHTML = `<option value="">All Zones</option>` +
      s.zones.map((z) => `<option value="${z}">${z}</option>`).join("");
  }

  // 1. Priority Tiers Distribution
  const tierContainer = document.getElementById("chart-tiers");
  if (tierContainer && s.priority_tiers) {
    const tiers = [
      { name: "Critical (≥ 50.0)", count: s.priority_tiers.Critical || 53, color: THEME_COLORS.critical },
      { name: "High (40.0 - 50.0)", count: s.priority_tiers.High || 215, color: THEME_COLORS.high },
      { name: "Medium (30.0 - 40.0)", count: s.priority_tiers.Medium || 404, color: THEME_COLORS.medium },
      { name: "Low (< 30.0)", count: s.priority_tiers.Low || 328, color: THEME_COLORS.low },
    ];
    renderBarGroup(tierContainer, tiers, s.total_locations);
  }

  // 2. Incident Severity Distribution
  const sevContainer = document.getElementById("chart-severity");
  if (sevContainer && s.severity_distribution) {
    const sevs = [
      { name: "Critical Severity", count: s.severity_distribution.Critical || 470, color: THEME_COLORS.critical },
      { name: "High Severity", count: s.severity_distribution.High || 1985, color: THEME_COLORS.high },
      { name: "Medium Severity", count: s.severity_distribution.Medium || 3726, color: THEME_COLORS.medium },
      { name: "Low Severity", count: s.severity_distribution.Low || 3819, color: THEME_COLORS.low },
    ];
    renderBarGroup(sevContainer, sevs, s.total_incidents);
  }

  // 3. Incident Categories
  const incCatContainer = document.getElementById("chart-inc-categories");
  if (incCatContainer && s.incident_categories) {
    const cats = Object.entries(s.incident_categories).map(([name, count]) => ({
      name: formatCategoryName(name),
      count,
      color: THEME_COLORS.primary,
    }));
    renderBarGroup(incCatContainer, cats, s.total_incidents);
  }

  // 4. Complaint Categories
  const compCatContainer = document.getElementById("chart-comp-categories");
  if (compCatContainer && s.complaint_categories) {
    const cats = Object.entries(s.complaint_categories).map(([name, count]) => ({
      name: formatCategoryName(name),
      count,
      color: THEME_COLORS.secondary,
    }));
    renderBarGroup(compCatContainer, cats, s.total_complaints);
  }
}

function formatCategoryName(name) {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function renderBarGroup(container, items, total) {
  container.innerHTML = items.map((item) => {
    const pct = ((item.count / total) * 100).toFixed(1);
    return `
      <div class="chart-bar-item">
        <div class="chart-bar-row">
          <span>${item.name}</span>
          <span><strong>${item.count.toLocaleString()}</strong> (${pct}%)</span>
        </div>
        <div class="chart-bar-track">
          <div class="chart-bar-fill" style="width: ${pct}%; background-color: ${item.color};"></div>
        </div>
      </div>
    `;
  }).join("");
}

/**
 * Filter & Table Rendering Logic
 */
function setupFilterListeners() {
  const searchInput = document.getElementById("filter-search");
  const tierSelect = document.getElementById("filter-tier");
  const zoneSelect = document.getElementById("filter-zone");
  const catSelect = document.getElementById("filter-category");
  const btnReset = document.getElementById("btn-reset-filters");

  const applyFilters = () => {
    const q = searchInput.value.trim().toUpperCase();
    const tier = tierSelect.value;
    const zone = zoneSelect.value;
    const cat = catSelect.value;

    appData.filteredLocations = appData.locations.filter((loc) => {
      if (q && !loc.location_id.toUpperCase().includes(q) && !loc.zone.toUpperCase().includes(q)) {
        return false;
      }
      if (tier && loc.priority_level !== tier) {
        return false;
      }
      if (zone && loc.zone !== zone) {
        return false;
      }
      if (cat) {
        const col = `inc_${cat}`;
        if (!loc[col] || loc[col] <= 0) return false;
      }
      return true;
    });

    appData.currentPage = 1;
    renderTable();
    updateMapMarkers();
  };

  searchInput?.addEventListener("input", applyFilters);
  tierSelect?.addEventListener("change", applyFilters);
  zoneSelect?.addEventListener("change", applyFilters);
  catSelect?.addEventListener("change", applyFilters);

  btnReset?.addEventListener("click", () => {
    searchInput.value = "";
    tierSelect.value = "";
    zoneSelect.value = "";
    catSelect.value = "";
    appData.filteredLocations = [...appData.locations];
    appData.currentPage = 1;
    renderTable();
    updateMapMarkers();
  });

  document.getElementById("btn-prev-page")?.addEventListener("click", () => {
    if (appData.currentPage > 1) {
      appData.currentPage--;
      renderTable();
    }
  });

  document.getElementById("btn-next-page")?.addEventListener("click", () => {
    const maxPage = Math.ceil(appData.filteredLocations.length / appData.pageSize);
    if (appData.currentPage < maxPage) {
      appData.currentPage++;
      renderTable();
    }
  });
}

function renderTable() {
  const tbody = document.getElementById("priority-table-body");
  const matchCount = document.getElementById("filter-match-count");
  if (!tbody) return;

  const total = appData.filteredLocations.length;
  if (matchCount) {
    matchCount.textContent = `${total.toLocaleString()} location${total === 1 ? "" : "s"}`;
  }

  const start = (appData.currentPage - 1) * appData.pageSize;
  const end = Math.min(start + appData.pageSize, total);
  const pageLocations = appData.filteredLocations.slice(start, end);

  const startEl = document.getElementById("page-start");
  const endEl = document.getElementById("page-end");
  const totalEl = document.getElementById("page-total");
  const indicatorEl = document.getElementById("page-indicator");
  const btnPrev = document.getElementById("btn-prev-page");
  const btnNext = document.getElementById("btn-next-page");

  if (startEl) startEl.textContent = total > 0 ? (start + 1).toLocaleString() : "0";
  if (endEl) endEl.textContent = end.toLocaleString();
  if (totalEl) totalEl.textContent = total.toLocaleString();
  if (indicatorEl) indicatorEl.textContent = `Page ${appData.currentPage} of ${Math.max(1, Math.ceil(total / appData.pageSize))}`;

  if (btnPrev) btnPrev.disabled = appData.currentPage <= 1;
  if (btnNext) btnNext.disabled = end >= total;

  if (pageLocations.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; padding: 48px; color: var(--text-secondary);">
          No locations match the selected criteria. Try resetting the filters.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = pageLocations.map((loc) => {
    const isSelected = appData.selectedLocation && appData.selectedLocation.location_id === loc.location_id;
    const tierClass = `tier-${loc.priority_level.toLowerCase()}`;

    return `
      <tr class="${isSelected ? 'selected-row' : ''}" onclick="selectLocation('${loc.location_id}')">
        <td class="col-id">${loc.location_id}</td>
        <td>${loc.zone}</td>
        <td><span class="tier-badge ${tierClass}">${loc.priority_level}</span></td>
        <td><strong>${loc.incident_count}</strong> <span style="font-size: 11px; color: var(--text-secondary);">(${loc.critical_incidents} crit)</span></td>
        <td><strong>${loc.complaint_count}</strong></td>
        <td class="col-score">${loc.priority_score.toFixed(2)}</td>
      </tr>
    `;
  }).join("");
}

/**
 * Interactive Leaflet Map Initialization with Light Basemap
 */
function initMap() {
  const mapElement = document.getElementById("city-map");
  if (!mapElement || typeof L === "undefined") return;

  // Center on Vijayawada/Guntur simulated coordinates (16.45 N, 80.50 E)
  appData.map = L.map("city-map", {
    zoomControl: true,
  }).setView([16.446, 80.500], 11);

  // CartoDB Positron clean light basemap
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    maxZoom: 19,
    subdomains: "abcd",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a> | Synthetic CityFix AI Data',
  }).addTo(appData.map);

  appData.markersLayer = L.layerGroup().addTo(appData.map);
  updateMapMarkers();
}

function updateMapMarkers() {
  if (!appData.map || !appData.markersLayer) return;
  appData.markersLayer.clearLayers();
  appData.markersMap.clear();

  const colorMap = {
    Critical: THEME_COLORS.critical,
    High: THEME_COLORS.high,
    Medium: THEME_COLORS.medium,
    Low: THEME_COLORS.low,
  };

  // Render locations (up to 300 visible on map for crisp performance)
  const locsToRender = appData.filteredLocations.slice(0, 300);

  locsToRender.forEach((loc) => {
    const color = colorMap[loc.priority_level] || THEME_COLORS.primary;
    const radius = loc.priority_level === "Critical" ? 8 : loc.priority_level === "High" ? 6 : 5;

    const marker = L.circleMarker([loc.latitude, loc.longitude], {
      radius: radius,
      fillColor: color,
      color: "#FFFFFF",
      weight: 1.5,
      opacity: 1,
      fillOpacity: 0.85,
    });

    const popupHtml = `
      <div style="font-family: var(--font-sans); color: #1E293B; font-size: 13px; min-width: 170px;">
        <div style="font-weight: 800; font-size: 14px; margin-bottom: 4px; color: #2563EB;">
          ${loc.location_id} (${loc.zone})
        </div>
        <div style="font-size: 12px; color: #64748B; margin-bottom: 8px; line-height: 1.4;">
          Priority: <strong style="color: ${color};">${loc.priority_level} (${loc.priority_score.toFixed(1)})</strong><br>
          Road: <strong style="color: #1E293B;">${loc.road_condition}</strong> &bull; Incidents: <strong style="color: #1E293B;">${loc.incident_count}</strong><br>
          Backlog: <strong style="color: #1E293B;">${loc.unresolved_incidents} active</strong>
        </div>
        <button class="btn btn-primary btn-sm" style="width: 100%;" onclick="selectLocation('${loc.location_id}'); document.getElementById('section-evidence').scrollIntoView({ behavior: 'smooth' });">
          Inspect Evidence &rarr;
        </button>
      </div>
    `;

    marker.bindPopup(popupHtml);
    appData.markersLayer.addLayer(marker);
    appData.markersMap.set(loc.location_id, marker);
  });
}

/**
 * Evidence Panel Deep-Dive
 */
function populateLocationSelect() {
  const select = document.getElementById("evidence-location-select");
  if (!select) return;

  select.innerHTML = appData.locations.map((loc) => `
    <option value="${loc.location_id}">${loc.location_id} (${loc.zone})</option>
  `).join("");

  select.addEventListener("change", (e) => {
    selectLocation(e.target.value);
  });
}

function selectLocation(locationId) {
  const loc = appData.locations.find((l) => l.location_id === locationId);
  if (!loc) return;

  appData.selectedLocation = loc;
  
  const select = document.getElementById("evidence-location-select");
  if (select) select.value = loc.location_id;

  renderEvidenceContent(loc);
  renderTable(); // Update selected-row highlight

  // Pan to map marker if available
  if (appData.map) {
    appData.map.setView([loc.latitude, loc.longitude], 13);
    const marker = appData.markersMap.get(loc.location_id);
    if (marker) {
      marker.openPopup();
    }
  }
}

function renderEvidenceContent(loc) {
  const container = document.getElementById("evidence-content");
  if (!container) return;

  const tierClass = `tier-${loc.priority_level.toLowerCase()}`;

  container.innerHTML = `
    <!-- Top Hero Card -->
    <div class="evidence-hero">
      <div>
        <div class="evidence-id">${loc.location_id}</div>
        <div class="evidence-meta">
          <span class="tier-badge ${tierClass}">${loc.priority_level} Priority</span>
          <span style="font-size: 13px; color: var(--text-secondary);">${loc.zone}</span>
        </div>
      </div>
      <div class="evidence-score-badge">
        <div class="score-display">${loc.priority_score.toFixed(1)}</div>
        <div class="score-label">Priority Score / 100</div>
      </div>
    </div>

    <!-- Quick Stats Grid -->
    <div class="evidence-stats-grid">
      <div class="stat-cell">
        <div class="stat-label">Incidents</div>
        <div class="stat-val">${loc.incident_count} <span style="font-size: 11px; font-weight: 500; color: var(--crit-color);">(${loc.critical_incidents} crit)</span></div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Complaints</div>
        <div class="stat-val">${loc.complaint_count}</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Backlog</div>
        <div class="stat-val" style="color: ${loc.unresolved_incidents >= 5 ? 'var(--crit-color)' : 'var(--text-primary)'};">${loc.unresolved_incidents} active</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Road Condition</div>
        <div class="stat-val" style="color: ${loc.road_condition === 'Critical' ? 'var(--crit-color)' : loc.road_condition === 'Poor' ? 'var(--high-color)' : 'var(--text-primary)'};">${loc.road_condition}</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Near School</div>
        <div class="stat-val">${loc.near_school ? '<span style="color: var(--high-color);">Yes</span>' : 'No'}</div>
      </div>
      <div class="stat-cell">
        <div class="stat-label">Near Hospital</div>
        <div class="stat-val">${loc.near_hospital ? '<span style="color: var(--crit-color);">Yes</span>' : 'No'}</div>
      </div>
    </div>

    <!-- 4-Pillar Score Breakdown -->
    <div>
      <div class="evidence-section-title">4-Pillar Score Breakdown</div>
      <div class="pillar-group">
        <div class="pillar-row">
          <div class="pillar-labels">
            <span>Incident Hazard (35%)</span>
            <strong>${loc.subscore_incident.toFixed(1)} / 100</strong>
          </div>
          <div class="pillar-track">
            <div class="pillar-fill" style="width: ${loc.subscore_incident}%; background-color: var(--crit-color);"></div>
          </div>
        </div>

        <div class="pillar-row">
          <div class="pillar-labels">
            <span>Backlog Burden (25%)</span>
            <strong>${loc.subscore_backlog.toFixed(1)} / 100</strong>
          </div>
          <div class="pillar-track">
            <div class="pillar-fill" style="width: ${loc.subscore_backlog}%; background-color: var(--high-color);"></div>
          </div>
        </div>

        <div class="pillar-row">
          <div class="pillar-labels">
            <span>Vulnerability Context (25%)</span>
            <strong>${loc.subscore_vulnerability.toFixed(1)} / 100</strong>
          </div>
          <div class="pillar-track">
            <div class="pillar-fill" style="width: ${loc.subscore_vulnerability}%; background-color: var(--med-color);"></div>
          </div>
        </div>

        <div class="pillar-row">
          <div class="pillar-labels">
            <span>Citizen Demand (15%)</span>
            <strong>${loc.subscore_complaint.toFixed(1)} / 100</strong>
          </div>
          <div class="pillar-track">
            <div class="pillar-fill" style="width: ${loc.subscore_complaint}%; background-color: var(--accent-primary);"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Suggested Municipal Action Box -->
    <div class="action-box">
      <div class="action-header">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="16" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>
        Suggested Municipal Action
      </div>
      <div class="action-text">${loc.suggested_next_action}</div>
    </div>

    <!-- Contributing Factors -->
    <div>
      <div class="evidence-section-title">Key Contributing Factors</div>
      <ul class="factors-list">
        ${loc.contributing_factors.map((f) => `<li>${f}</li>`).join("")}
      </ul>
    </div>

    <!-- Data Boundaries & Limitations -->
    <div>
      <div class="evidence-section-title" style="color: var(--text-muted);">Data Boundaries &amp; Limitations</div>
      <ul class="limitations-list">
        ${loc.missing_evidence_or_limitations.map((lim) => `<li>${lim}</li>`).join("")}
      </ul>
    </div>
  `;
}

/**
 * AI City Intelligence Console
 */
function setupAiConsole() {
  const btn = document.getElementById("btn-run-ai");
  const input = document.getElementById("ai-query-input");

  const submit = () => {
    const q = input.value.trim();
    if (q) runAiQuery(q);
  };

  btn?.addEventListener("click", submit);
  input?.addEventListener("keypress", (e) => {
    if (e.key === "Enter") submit();
  });
}

async function runAiQuery(prompt) {
  const input = document.getElementById("ai-query-input");
  const title = document.getElementById("ai-result-title");
  const text = document.getElementById("ai-result-text");
  const matchedCards = document.getElementById("ai-matched-container");
  const extra = document.getElementById("ai-result-extra");

  if (input) input.value = prompt;
  title.innerHTML = `<span>⏳</span> Analyzing: "${prompt}"...`;
  text.textContent = "Querying civic prioritization engine across all 1,000 city locations...";
  matchedCards.innerHTML = "";
  extra.innerHTML = "";

  document.getElementById("section-ai")?.scrollIntoView({ behavior: "smooth" });

  try {
    // Try REST API first
    const res = await fetch(`/api/query?q=${encodeURIComponent(prompt)}`);
    if (res.ok) {
      const data = await res.json();
      renderAiResponse(data);
      return;
    }
  } catch (e) {
    // Fall back to client-side deterministic response
  }

  // Client-side fallback query engine
  const clientData = clientSideQuery(prompt);
  renderAiResponse(clientData);
}

function clientSideQuery(q) {
  const query = q.toLowerCase();
  const locs = appData.locations;

  // Single location check
  for (const loc of locs) {
    if (query.includes(loc.location_id.toLowerCase())) {
      return {
        title: `Analysis for Location ${loc.location_id} (${loc.zone})`,
        answer: `Location ${loc.location_id} is evaluated at ${loc.priority_level} priority with a score of ${loc.priority_score.toFixed(2)}/100. It has ${loc.incident_count} recorded incidents (${loc.critical_incidents} critical) and ${loc.complaint_count} public complaints, with ${loc.unresolved_incidents} unresolved issues. Road condition is rated '${loc.road_condition}'.`,
        suggested_next_action: loc.suggested_next_action,
        matched_locations: [loc],
      };
    }
  }

  // Backlog
  if (query.includes("unresolved") || query.includes("backlog")) {
    const top = [...locs].sort((a, b) => b.unresolved_incidents - a.unresolved_incidents).slice(0, 5);
    return {
      title: "Locations with Worst Unresolved Incident Backlogs",
      answer: "The following locations have the highest count of unresolved physical incidents lingering without closed work orders:",
      suggested_next_action: "Prioritize clearing active work orders at these backlogged locations.",
      matched_locations: top,
    };
  }

  // Drainage & flooding
  if (query.includes("drain") || query.includes("flood")) {
    const top = [...locs].sort((a, b) => (b.inc_blocked_drain + b.inc_flooding) - (a.inc_blocked_drain + a.inc_flooding)).slice(0, 5);
    return {
      title: "Severe Stormwater & Drainage Bottlenecks",
      answer: "These locations record the highest concentration of blocked drainage and flooding disruptions:",
      suggested_next_action: "Dispatch stormwater maintenance crews for culvert desilting and storm drain clearing.",
      matched_locations: top,
    };
  }

  // Schools / Hospitals
  if (query.includes("school") || query.includes("hospital")) {
    const top = locs.filter((l) => (l.near_school || l.near_hospital) && (l.road_condition === "Critical" || l.road_condition === "Poor")).slice(0, 5);
    return {
      title: "Vulnerable School & Hospital Corridors with Road Degradation",
      answer: "Identified locations with sensitive pedestrian receptors and degraded road surfaces:",
      suggested_next_action: "Conduct pedestrian safety review and emergency corridor pavement repair.",
      matched_locations: top,
    };
  }

  // Default Top Priority
  return {
    title: "Top 5 High-Priority Repair Hotspots",
    answer: "The top 5 overall highest-priority locations requiring immediate municipal triage are:",
    suggested_next_action: "Deploy field inspection teams to assess pavement and drainage conditions.",
    matched_locations: locs.slice(0, 5),
  };
}

function renderAiResponse(data) {
  const title = document.getElementById("ai-result-title");
  const text = document.getElementById("ai-result-text");
  const matchedCards = document.getElementById("ai-matched-container");
  const extra = document.getElementById("ai-result-extra");

  title.innerHTML = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
    <span>${data.title}</span>
  `;
  text.textContent = data.answer;

  if (data.suggested_next_action) {
    extra.innerHTML = `
      <div class="action-box">
        <div class="action-header">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="16" x2="12" y2="12"></line>
            <line x1="12" y1="8" x2="12.01" y2="8"></line>
          </svg>
          Actionable Recommendation
        </div>
        <div class="action-text">${data.suggested_next_action}</div>
      </div>
    `;
  }

  if (data.matched_locations && data.matched_locations.length > 0) {
    matchedCards.innerHTML = data.matched_locations.map((loc) => {
      const tierClass = `tier-${loc.priority_level.toLowerCase()}`;
      return `
        <div class="matched-card" onclick="selectLocation('${loc.location_id}'); document.getElementById('section-evidence').scrollIntoView({ behavior: 'smooth' });">
          <div class="matched-header">
            <span class="matched-id">${loc.location_id}</span>
            <span class="tier-badge ${tierClass}">${loc.priority_level}</span>
          </div>
          <div class="matched-details">
            Score: <strong>${loc.priority_score.toFixed(1)}</strong> &bull; ${loc.zone}<br>
            Road: <strong>${loc.road_condition}</strong> &bull; Backlog: <strong>${loc.unresolved_incidents} active</strong>
          </div>
          <div class="matched-action">
            Inspect Evidence &rarr;
          </div>
        </div>
      `;
    }).join("");
  }
}
