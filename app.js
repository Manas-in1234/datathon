/**
 * CityFix AI — Municipal Command Center JavaScript
 * ===============================================
 * Datathon 2026 — Track 3: Smart City (Where Should We Fix First?)
 */

// Application State
let appData = {
  summary: null,
  locations: [],
  selectedLocation: null,
  map: null,
  markersLayer: null,
  currentPage: 1,
  pageSize: 25,
  filteredLocations: [],
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
  selectLocation(appData.locations[0]?.location_id || "L0965");
});

/**
 * Load dashboard data from API or fallback to static JSON.
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
 * Tab Navigation Setup
 */
function setupNavigation() {
  const navItems = document.querySelectorAll(".nav-item");
  navItems.forEach((item) => {
    item.addEventListener("click", () => {
      const tabId = item.getAttribute("data-tab");
      switchTab(tabId);
    });
  });
}

function switchTab(tabId) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.getAttribute("data-tab") === tabId);
  });

  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === tabId);
  });

  if (tabId === "tab-map" && appData.map) {
    setTimeout(() => appData.map.invalidateSize(), 200);
  }
}

/**
 * Render Executive Dashboard KPI metrics and distributions.
 */
function renderDashboard() {
  if (!appData.summary) return;
  const s = appData.summary;

  // KPI Numbers
  document.getElementById("kpi-locations").textContent = s.total_locations.toLocaleString();
  document.getElementById("kpi-incidents").textContent = s.total_incidents.toLocaleString();
  document.getElementById("kpi-complaints").textContent = s.total_complaints.toLocaleString();
  document.getElementById("kpi-unresolved").textContent = s.total_unresolved_incidents.toLocaleString();
  document.getElementById("kpi-open-comp").textContent = s.total_open_complaints.toLocaleString();
  document.getElementById("kpi-critical-hotspots").textContent = (s.priority_tiers?.Critical || 53).toLocaleString();

  // Populate Zone dropdown
  const zoneSelect = document.getElementById("filter-zone");
  if (zoneSelect && s.zones) {
    zoneSelect.innerHTML = `<option value="">All 20 Zones</option>` +
      s.zones.map((z) => `<option value="${z}">${z}</option>`).join("");
  }

  // 1. Priority Tiers Distribution
  const tierContainer = document.getElementById("chart-tiers");
  if (tierContainer && s.priority_tiers) {
    const tiers = [
      { name: "Critical (≥ 50.0)", count: s.priority_tiers.Critical || 53, color: "var(--crit-color)" },
      { name: "High (40.0 - 50.0)", count: s.priority_tiers.High || 215, color: "var(--high-color)" },
      { name: "Medium (30.0 - 40.0)", count: s.priority_tiers.Medium || 404, color: "var(--med-color)" },
      { name: "Low (< 30.0)", count: s.priority_tiers.Low || 328, color: "var(--low-color)" },
    ];
    renderBarGroup(tierContainer, tiers, s.total_locations);
  }

  // 2. Incident Severity Distribution
  const sevContainer = document.getElementById("chart-severity");
  if (sevContainer && s.severity_distribution) {
    const sevs = [
      { name: "Critical Severity", count: s.severity_distribution.Critical || 470, color: "var(--crit-color)" },
      { name: "High Severity", count: s.severity_distribution.High || 1985, color: "var(--high-color)" },
      { name: "Medium Severity", count: s.severity_distribution.Medium || 3726, color: "var(--med-color)" },
      { name: "Low Severity", count: s.severity_distribution.Low || 3819, color: "var(--low-color)" },
    ];
    renderBarGroup(sevContainer, sevs, s.total_incidents);
  }

  // 3. Incident Categories
  const incCatContainer = document.getElementById("chart-inc-categories");
  if (incCatContainer && s.incident_categories) {
    const cats = Object.entries(s.incident_categories).map(([name, count]) => ({
      name,
      count,
      color: "var(--teal-primary)",
    }));
    renderBarGroup(incCatContainer, cats, s.total_incidents);
  }

  // 4. Complaint Categories
  const compCatContainer = document.getElementById("chart-comp-categories");
  if (compCatContainer && s.complaint_categories) {
    const cats = Object.entries(s.complaint_categories).map(([name, count]) => ({
      name,
      count,
      color: "var(--teal-accent)",
    }));
    renderBarGroup(compCatContainer, cats, s.total_complaints);
  }

  // 5. Spotlight Top 3 Cards
  const spotlightContainer = document.getElementById("spotlight-cards");
  if (spotlightContainer && appData.locations.length >= 3) {
    const top3 = appData.locations.slice(0, 3);
    spotlightContainer.innerHTML = top3.map((loc, idx) => `
      <div style="background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 16px; display: flex; flex-direction: column; justify-content: space-between;">
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-weight: 800; font-size: 16px; color: var(--teal-accent);">#${idx + 1} ${loc.location_id}</span>
            <span class="tier-badge tier-${loc.priority_level.toLowerCase()}">${loc.priority_level} (${loc.priority_score})</span>
          </div>
          <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
            Zone: <strong>${loc.zone}</strong> • Road: <strong style="color: ${loc.road_condition === 'Critical' ? 'var(--crit-color)' : 'var(--text-bright)'};">${loc.road_condition}</strong>
          </div>
          <p style="font-size: 12px; color: var(--text-main); margin-bottom: 12px; line-height: 1.4;">
            ${loc.suggested_next_action.split('.')[0]}.
          </p>
        </div>
        <button class="btn-inspect" onclick="inspectFromSpotlight('${loc.location_id}')">Inspect Full Evidence →</button>
      </div>
    `).join("");
  }
}

function renderBarGroup(container, items, total) {
  container.innerHTML = items.map((item) => {
    const pct = ((item.count / total) * 100).toFixed(1);
    return `
      <div class="dist-bar-item">
        <div class="dist-bar-label">
          <span>${item.name}</span>
          <span><strong>${item.count.toLocaleString()}</strong> (${pct}%)</span>
        </div>
        <div class="dist-bar-track">
          <div class="dist-bar-fill" style="width: ${pct}%; background-color: ${item.color};"></div>
        </div>
      </div>
    `;
  }).join("");
}

function inspectFromSpotlight(locationId) {
  selectLocation(locationId);
  switchTab("tab-evidence");
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
    matchCount.textContent = `Showing ${total.toLocaleString()} location${total === 1 ? "" : "s"}`;
  }

  const start = (appData.currentPage - 1) * appData.pageSize;
  const end = Math.min(start + appData.pageSize, total);
  const pageLocations = appData.filteredLocations.slice(start, end);

  document.getElementById("page-start").textContent = total > 0 ? (start + 1).toLocaleString() : "0";
  document.getElementById("page-end").textContent = end.toLocaleString();
  document.getElementById("page-total").textContent = total.toLocaleString();
  document.getElementById("page-indicator").textContent = `Page ${appData.currentPage} of ${Math.max(1, Math.ceil(total / appData.pageSize))}`;

  document.getElementById("btn-prev-page").disabled = appData.currentPage <= 1;
  document.getElementById("btn-next-page").disabled = end >= total;

  if (pageLocations.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="11" style="text-align: center; padding: 40px; color: var(--text-muted);">
          No locations match the selected criteria. Try resetting the filters.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = pageLocations.map((loc, idx) => {
    const globalRank = start + idx + 1;
    const tierClass = `tier-${loc.priority_level.toLowerCase()}`;
    const keyFactor = loc.contributing_factors?.[0] || "Routine monitoring";

    return `
      <tr onclick="selectLocation('${loc.location_id}')" style="cursor: pointer;">
        <td style="font-weight: 700; color: var(--text-muted); font-family: var(--font-mono);">${globalRank}</td>
        <td style="font-weight: 700; color: var(--teal-accent); font-family: var(--font-mono);">${loc.location_id}</td>
        <td>${loc.zone}</td>
        <td style="font-family: var(--font-mono); font-weight: 800;">${loc.priority_score.toFixed(2)}</td>
        <td><span class="tier-badge ${tierClass}">${loc.priority_level}</span></td>
        <td>${loc.incident_count} <span style="font-size: 11px; color: var(--text-muted);">(${loc.critical_incidents} crit / ${loc.high_incidents} high)</span></td>
        <td>${loc.complaint_count}</td>
        <td style="color: ${loc.unresolved_incidents >= 5 ? 'var(--crit-color)' : 'var(--text-main)'}; font-weight: 700;">${loc.unresolved_incidents}</td>
        <td><span style="color: ${loc.road_condition === 'Critical' ? 'var(--crit-color)' : loc.road_condition === 'Poor' ? 'var(--high-color)' : 'var(--text-main)'};">${loc.road_condition}</span></td>
        <td style="max-width: 260px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${keyFactor}">${keyFactor}</td>
        <td><button class="btn-inspect" onclick="event.stopPropagation(); selectLocation('${loc.location_id}'); switchTab('tab-evidence');">Inspect</button></td>
      </tr>
    `;
  }).join("");
}

/**
 * Interactive Leaflet Map Initialization
 */
function initMap() {
  const mapElement = document.getElementById("city-map");
  if (!mapElement || typeof L === "undefined") return;

  // Center on Vijayawada/Guntur simulated coordinates (16.45 N, 80.50 E)
  appData.map = L.map("city-map").setView([16.446, 80.500], 11);

  // High-contrast dark tile layer
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | Synthetic CityFix AI Data',
  }).addTo(appData.map);

  appData.markersLayer = L.layerGroup().addTo(appData.map);
  updateMapMarkers();
}

function updateMapMarkers() {
  if (!appData.map || !appData.markersLayer) return;
  appData.markersLayer.clearLayers();

  const colorMap = {
    Critical: "#ff4757",
    High: "#ffa502",
    Medium: "#eccc68",
    Low: "#70a1ff",
  };

  // Render locations (up to 300 visible on map for fast rendering)
  const locsToRender = appData.filteredLocations.slice(0, 300);

  locsToRender.forEach((loc) => {
    const color = colorMap[loc.priority_level] || "#00b4d8";
    const radius = loc.priority_level === "Critical" ? 9 : loc.priority_level === "High" ? 7 : 5;

    const marker = L.circleMarker([loc.latitude, loc.longitude], {
      radius: radius,
      fillColor: color,
      color: "#070d1e",
      weight: 1.5,
      opacity: 1,
      fillOpacity: 0.85,
    });

    const popupHtml = `
      <div style="font-family: sans-serif; color: #111;">
        <div style="font-weight: 800; font-size: 14px; margin-bottom: 4px;">
          ${loc.location_id} (${loc.zone})
        </div>
        <div style="font-size: 12px; margin-bottom: 6px;">
          Priority: <strong style="color: ${color};">${loc.priority_level} (${loc.priority_score})</strong><br>
          Road: <strong>${loc.road_condition}</strong> • Incidents: <strong>${loc.incident_count}</strong><br>
          Backlog: <strong>${loc.unresolved_incidents} active</strong>
        </div>
        <button style="background: #00b4d8; color: #fff; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 700;" onclick="selectLocation('${loc.location_id}'); switchTab('tab-evidence');">
          Inspect Evidence →
        </button>
      </div>
    `;

    marker.bindPopup(popupHtml);
    appData.markersLayer.addLayer(marker);
  });
}

/**
 * Evidence Panel Deep-Dive
 */
function populateLocationSelect() {
  const select = document.getElementById("evidence-location-select");
  if (!select) return;

  select.innerHTML = appData.locations.map((loc) => `
    <option value="${loc.location_id}">${loc.location_id} — ${loc.zone} (${loc.priority_level}, ${loc.priority_score})</option>
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

  // If map exists, pan to location
  if (appData.map) {
    appData.map.setView([loc.latitude, loc.longitude], 13);
  }
}

function renderEvidenceContent(loc) {
  const container = document.getElementById("evidence-content");
  if (!container) return;

  const tierClass = `tier-${loc.priority_level.toLowerCase()}`;

  container.innerHTML = `
    <!-- Header Card -->
    <div class="evidence-header-card">
      <div>
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
          <h1 style="font-size: 24px; font-weight: 800; color: var(--text-bright);">${loc.location_id}</h1>
          <span class="tier-badge ${tierClass}">${loc.priority_level} Priority</span>
          <span style="font-size: 13px; color: var(--text-muted);">${loc.zone}</span>
        </div>
        <p style="font-size: 13px; color: var(--text-muted);">
          Coordinates: <code style="font-family: var(--font-mono); color: var(--teal-primary);">${loc.latitude.toFixed(6)}° N, ${loc.longitude.toFixed(6)}° E</code> 
          (Simulated Synthetic Bounding Box)
        </p>
      </div>
      <div class="evidence-score-circle">
        <div class="score-num">${loc.priority_score.toFixed(1)}</div>
        <div class="score-lbl">Priority Score</div>
      </div>
    </div>

    <!-- 4-Pillar Score Breakdown -->
    <div class="chart-card">
      <div class="chart-header">
        <div class="chart-title">4-Pillar Normalized Score Breakdown</div>
      </div>
      <div class="dist-bar-group">
        <div class="dist-bar-item">
          <div class="dist-bar-label"><span>Incident Hazard Subscore (35%)</span><span><strong>${loc.subscore_incident}</strong> / 100</span></div>
          <div class="dist-bar-track"><div class="dist-bar-fill" style="width: ${loc.subscore_incident}%; background-color: var(--crit-color);"></div></div>
        </div>
        <div class="dist-bar-item">
          <div class="dist-bar-label"><span>Backlog Burden Subscore (25%)</span><span><strong>${loc.subscore_backlog}</strong> / 100</span></div>
          <div class="dist-bar-track"><div class="dist-bar-fill" style="width: ${loc.subscore_backlog}%; background-color: var(--high-color);"></div></div>
        </div>
        <div class="dist-bar-item">
          <div class="dist-bar-label"><span>Vulnerability Context Subscore (25%)</span><span><strong>${loc.subscore_vulnerability}</strong> / 100</span></div>
          <div class="dist-bar-track"><div class="dist-bar-fill" style="width: ${loc.subscore_vulnerability}%; background-color: var(--med-color);"></div></div>
        </div>
        <div class="dist-bar-item">
          <div class="dist-bar-label"><span>Citizen Demand Subscore (15%)</span><span><strong>${loc.subscore_complaint}</strong> / 100</span></div>
          <div class="dist-bar-track"><div class="dist-bar-fill" style="width: ${loc.subscore_complaint}%; background-color: var(--teal-primary);"></div></div>
        </div>
      </div>

      <!-- Suggested Next Action Box -->
      <div class="evidence-action-box">
        <div class="action-title">💡 Suggested Municipal Next Action</div>
        <div style="font-size: 13px; font-weight: 600; color: var(--text-bright); line-height: 1.5;">
          ${loc.suggested_next_action}
        </div>
      </div>
    </div>

    <!-- Location Characteristics & Sensitivity -->
    <div class="chart-card">
      <div class="chart-header">
        <div class="chart-title">Physical Context &amp; Receptor Proximity</div>
      </div>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 13px;">
        <div style="background: var(--bg-secondary); padding: 10px; border-radius: var(--radius-sm);">
          <div style="color: var(--text-muted); font-size: 11px;">ROAD CONDITION</div>
          <div style="font-weight: 700; color: ${loc.road_condition === 'Critical' ? 'var(--crit-color)' : loc.road_condition === 'Poor' ? 'var(--high-color)' : 'var(--text-bright)'}; font-size: 15px;">
            ${loc.road_condition}
          </div>
        </div>
        <div style="background: var(--bg-secondary); padding: 10px; border-radius: var(--radius-sm);">
          <div style="color: var(--text-muted); font-size: 11px;">ROAD TYPE</div>
          <div style="font-weight: 700; color: var(--text-bright); font-size: 15px;">${loc.road_type}</div>
        </div>
        <div style="background: var(--bg-secondary); padding: 10px; border-radius: var(--radius-sm);">
          <div style="color: var(--text-muted); font-size: 11px;">PEDESTRIAN ACTIVITY</div>
          <div style="font-weight: 700; color: var(--text-bright); font-size: 15px;">${loc.pedestrian_activity}</div>
        </div>
        <div style="background: var(--bg-secondary); padding: 10px; border-radius: var(--radius-sm);">
          <div style="color: var(--text-muted); font-size: 11px;">POPULATION DENSITY</div>
          <div style="font-weight: 700; color: var(--text-bright); font-size: 15px;">${loc.population_density.toLocaleString()} /km²</div>
        </div>
        <div style="background: var(--bg-secondary); padding: 10px; border-radius: var(--radius-sm);">
          <div style="color: var(--text-muted); font-size: 11px;">NEAR SCHOOL</div>
          <div style="font-weight: 700; color: ${loc.near_school ? 'var(--high-color)' : 'var(--text-muted)'}; font-size: 14px;">
            ${loc.near_school ? 'Yes (Active Corridor)' : 'No'}
          </div>
        </div>
        <div style="background: var(--bg-secondary); padding: 10px; border-radius: var(--radius-sm);">
          <div style="color: var(--text-muted); font-size: 11px;">NEAR HOSPITAL</div>
          <div style="font-weight: 700; color: ${loc.near_hospital ? 'var(--crit-color)' : 'var(--text-muted)'}; font-size: 14px;">
            ${loc.near_hospital ? 'Yes (Emergency Route)' : 'No'}
          </div>
        </div>
      </div>
    </div>

    <!-- Why This Location Ranked High -->
    <div class="chart-card">
      <div class="chart-header">
        <div class="chart-title">Key Contributing Factors</div>
      </div>
      <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
        Algorithmic drivers identified from recorded physical events and spatial attributes:
      </p>
      <ul class="factors-list">
        ${loc.contributing_factors.map((f) => `<li>${f}</li>`).join("")}
      </ul>
    </div>

    <!-- Data Quality & Missing Evidence -->
    <div class="chart-card">
      <div class="chart-header">
        <div class="chart-title">Data Boundaries &amp; Missing Evidence</div>
      </div>
      <ul class="factors-list" style="margin-top: 0;">
        ${loc.missing_evidence_or_limitations.map((lim) => `<li style="color: var(--text-muted);">${lim}</li>`).join("")}
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
  text.textContent = "Querying civic data engine across all 1,000 city locations...";
  matchedCards.innerHTML = "";
  extra.innerHTML = "";

  // Switch to AI tab if not active
  switchTab("tab-ai");

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
        answer: `Location ${loc.location_id} is evaluated at ${loc.priority_level} priority with a score of ${loc.priority_score.toFixed(2)}/100. It has ${loc.incident_count} recorded incidents (${loc.critical_incidents} critical) and ${loc.complaint_count} complaints, with ${loc.unresolved_incidents} unresolved issues. Road condition is rated ${loc.road_condition}.`,
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

  // Drainage
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

  title.innerHTML = `<span>⚡</span> ${data.title}`;
  text.textContent = data.answer;

  if (data.suggested_next_action) {
    extra.innerHTML = `
      <div class="evidence-action-box" style="margin-top: 8px;">
        <div class="action-title">Actionable Recommendation</div>
        <div style="font-size: 13px; color: var(--text-bright);">${data.suggested_next_action}</div>
      </div>
    `;
  }

  if (data.matched_locations && data.matched_locations.length > 0) {
    matchedCards.innerHTML = data.matched_locations.map((loc) => `
      <div class="matched-card" onclick="selectLocation('${loc.location_id}'); switchTab('tab-evidence');">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <strong style="color: var(--teal-accent);">${loc.location_id}</strong>
          <span class="tier-badge tier-${loc.priority_level.toLowerCase()}">${loc.priority_level}</span>
        </div>
        <div style="font-size: 12px; color: var(--text-muted);">
          Score: <strong>${loc.priority_score.toFixed(1)}</strong> • ${loc.zone}<br>
          Road: <strong>${loc.road_condition}</strong> • Backlog: <strong>${loc.unresolved_incidents}</strong>
        </div>
        <div style="font-size: 11px; color: var(--teal-primary); margin-top: 6px; font-weight: 600;">
          Inspect Evidence →
        </div>
      </div>
    `).join("");
  }
}
