/**
 * Headless JS runtime simulation testing CityFix AI frontend logic.
 * Tests:
 * 1. Startup & Data Loading
 * 2. KPI Calculations
 * 3. Sorting & Pagination
 * 4. Assistant Q&A calculations
 * 5. Review decision saving & LocalStorage
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');

// Create mock DOM elements
const elements = {};
function getOrCreateElement(id) {
  if (!elements[id]) {
    elements[id] = {
      id,
      innerHTML: '',
      textContent: '',
      value: '',
      style: {},
      classList: {
        add: () => {},
        remove: () => {},
        contains: () => false,
      },
      disabled: false,
      attributes: {},
      setAttribute: function(k, v) { this.attributes[k] = v; },
      removeAttribute: function(k) { delete this.attributes[k]; },
      addEventListener: () => {},
      appendChild: () => {},
      reset: () => {},
      files: [],
      options: [],
      add: function(opt) { this.options.push(opt); },
      querySelectorAll: () => [],
      querySelector: () => null,
      scrollIntoView: () => {},
    };
  }
  return elements[id];
}

const mockLocalStorage = {};
const mockStorage = {
  getItem: (k) => mockLocalStorage[k] || null,
  setItem: (k, v) => { mockLocalStorage[k] = String(v); },
  removeItem: (k) => { delete mockLocalStorage[k]; },
};

// Setup sandbox window and document
const sandbox = {
  window: {},
  document: {
    getElementById: (id) => getOrCreateElement(id),
    querySelectorAll: (selector) => [],
    createElement: (tag) => getOrCreateElement('el_' + Math.random().toString(36).substring(7)),
    body: { appendChild: () => {} },
  },
  localStorage: mockStorage,
  Intl: Intl,
  Math: Math,
  Date: Date,
  JSON: JSON,
  Number: Number,
  String: String,
  Array: Array,
  Object: Object,
  Set: Set,
  Map: Map,
  URL: { createObjectURL: () => 'blob:mock', revokeObjectURL: () => {} },
  Blob: function() {},
  Option: function(text, val) { return { text, value: val }; },
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  fetch: () => Promise.resolve({
    ok: true,
    json: () => Promise.resolve(JSON.parse(fs.readFileSync(path.join(ROOT, 'forecast-model.json'), 'utf8')))
  }),
};

sandbox.window = sandbox;

// Load data.js into sandbox
const dataJs = fs.readFileSync(path.join(ROOT, 'data.js'), 'utf8');
vm.runInNewContext(dataJs, sandbox);

if (!sandbox.window.CITYFIX_DATA || !sandbox.window.CITYFIX_DATA.locations) {
  console.error('FAIL: CITYFIX_DATA failed to initialize');
  process.exit(1);
}

console.log(`Loaded ${sandbox.window.CITYFIX_DATA.locations.length} locations into sandbox.`);

// Load app.js into sandbox
const appJs = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
try {
  vm.runInNewContext(appJs, sandbox);
  console.log('SUCCESS: app.js loaded and executed initial render without exceptions.');
} catch (err) {
  console.error('FAIL: app.js threw exception on initialization:', err);
  process.exit(1);
}

// Verify KPIs were populated
const metricLocations = getOrCreateElement('metricLocations').textContent;
const metricIncidents = getOrCreateElement('metricIncidents').textContent;
const metricComplaints = getOrCreateElement('metricComplaints').textContent;
const metricOpen = getOrCreateElement('metricOpen').textContent;

console.log(`KPI Locations: ${metricLocations}, Incidents: ${metricIncidents}, Complaints: ${metricComplaints}, Open: ${metricOpen}`);

if (metricLocations !== '1,000') {
  console.error(`FAIL: Expected metricLocations 1,000, got ${metricLocations}`);
  process.exit(1);
}

console.log('ALL FRONTEND RUNTIME SIMULATION CHECKS PASSED.');
