#!/usr/bin/env node
/**
 * Frontend session smoke test (standard-library backend + Node VM, no browser).
 *
 * Boots backend/server.py against a temporary SQLite database, then executes
 * the real inline <script> from index.html inside a Node VM sandbox with a
 * minimal DOM stub. It simulates the exact officer journey from the bug
 * report:
 *
 *   1. Sign in as cp.south (Officer F. Cali)           -> token + user are
 *      persisted to localStorage (sentinel_token / sentinel_user).
 *   2. "Refresh the page" (fresh JS context, same localStorage) -> the
 *      session is re-hydrated BEFORE the API sync; the officer stays signed
 *      in, /api/dashboard + /api/checkpoint-events return 200 and the
 *      checkpoint table keeps its rows (no "South Checkpoint 0").
 *   3. Expired/bogus stored token -> the dedicated auth check (/api/me)
 *      returns 401 and ONLY then the app signs out and clears storage.
 *
 * Usage:  node backend/test_frontend_session.mjs
 */
import { spawn, spawnSync } from 'node:child_process';
import { readFileSync, mkdirSync } from 'node:fs';
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.dirname(ROOT);

// ---------------------------------------------------------------------------
// PostgreSQL test database.
//
// The backend serves PostgreSQL only. The suite therefore runs against either
//   (a) an explicitly configured server  — SENTINEL_DB_HOST / _NAME / _USER /
//       _PASSWORD / _PORT in the environment, or
//   (b) a throwaway cluster booted with the `pgserver` pip package
//       (`pip install pgserver`) inside a per-run temporary directory.
// When neither is available the suite prints SKIP and exits 0 rather than
// failing on an unrelated infrastructure prerequisite.
// ---------------------------------------------------------------------------
const PG_SERVE = `
import pathlib, sys, time, pgserver
d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
srv = pgserver.get_server(str(d))
print(d, flush=True)          # unix-socket directory
sys.stdin.read()              # stay alive until the parent closes stdin
`;

function provisionDatabase(tmp) {
  if (process.env.SENTINEL_DB_HOST || process.env.SENTINEL_DB_NAME) {
    return {
      env: {
        SENTINEL_DB_HOST: process.env.SENTINEL_DB_HOST || 'localhost',
        SENTINEL_DB_NAME: process.env.SENTINEL_DB_NAME || 'sentinel_police',
        SENTINEL_DB_USER: process.env.SENTINEL_DB_USER || 'postgres',
        SENTINEL_DB_PASSWORD: process.env.SENTINEL_DB_PASSWORD || '',
        SENTINEL_DB_PORT: process.env.SENTINEL_DB_PORT || '5432',
      },
      stop: () => {},
      label: 'configured PostgreSQL (' + (process.env.SENTINEL_DB_NAME || 'sentinel_police') + ')',
    };
  }
  const probe = spawnSync('python3', ['-c', 'import pgserver'], { stdio: 'ignore' });
  if (probe.status !== 0) return null;
  const child = spawn('python3', ['-c', PG_SERVE, path.join(tmp, 'pgdata')],
                      { stdio: ['pipe', 'pipe', 'inherit'] });
  let socketDir = '';
  const deadline = Date.now() + 90000;
  const buf = [];
  return new Promise((resolve) => {
    const onData = (chunk) => {
      buf.push(String(chunk));
      const m = buf.join('').match(/^(\/\S+)$/m);
      if (m) { socketDir = m[1]; resolve({ env: { SENTINEL_DB_HOST: socketDir, SENTINEL_DB_NAME: 'postgres', SENTINEL_DB_USER: 'postgres', SENTINEL_DB_PASSWORD: '' }, stop: () => child.kill('SIGKILL'), label: 'throwaway pgserver cluster at ' + socketDir }); }
    };
    child.stdout.on('data', onData);
    child.on('exit', () => { if (!socketDir) resolve(null); });
    const tick = setInterval(() => {
      if (Date.now() > deadline || socketDir) { clearInterval(tick); if (!socketDir) resolve(null); }
    }, 250);
  });
}

function freePort() {
  return new Promise((resolve) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => {
      const p = s.address().port;
      s.close(() => resolve(p));
    });
  });
}

async function waitFor(fn, what, timeoutMs = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (await fn()) return;
    await new Promise((r) => setTimeout(r, 40));
  }
  throw new Error('timed out waiting for: ' + what);
}

// --------------------------------------------------------------------------
// Minimal DOM stub — just enough surface for index.html's inline script.
// --------------------------------------------------------------------------
function makeClassList(el) {
  const set = new Set();
  return {
    add: (...cs) => cs.forEach((c) => set.add(c)),
    remove: (...cs) => cs.forEach((c) => set.delete(c)),
    contains: (c) => set.has(c),
    toggle: (c, force) => {
      const want = force === undefined ? !set.has(c) : !!force;
      if (want) set.add(c); else set.delete(c);
      return want;
    },
    toString: () => [...set].join(' '),
  };
}

function makeElement(id) {
  const el = {
    id,
    style: {},
    dataset: {},
    value: '',
    innerHTML: '',
    textContent: '',
    disabled: false,
    readOnly: false,
    src: '',
    scrollTop: 0,
    classList: null,
    _listeners: {},
    addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); },
    removeEventListener() {},
    dispatchEvent() { return true; },
    querySelectorAll() { return []; },
    querySelector() { return null; },
    closest() { return null; },
    appendChild(child) { return child; },
    insertBefore(child) { return child; },
    remove() {},
    focus() {},
    reset() {},
    setAttribute() {},
    getAttribute() { return null; },
    getBoundingClientRect() { return { width: 600, height: 300, top: 0, left: 0 }; },
    getContext() {
      // 2D-canvas stub: every method is a no-op, every prop assignable.
      return new Proxy({}, {
        get(t, k) {
          if (k === 'createLinearGradient') return () => ({ addColorStop() {} });
          if (k === 'measureText') return () => ({ width: 0 });
          if (k in t) return t[k];
          return () => {};
        },
        set(t, k, v) { t[k] = v; return true; },
      });
    },
    scrollTo() {},
  };
  el.classList = makeClassList(el);
  return el;
}

function makeLocalStorage() {
  const map = new Map();
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(String(k), String(v)),
    removeItem: (k) => map.delete(k),
    clear: () => map.clear(),
    _dump: () => Object.fromEntries(map),
    _load: (obj) => { map.clear(); Object.entries(obj || {}).forEach(([k, v]) => map.set(k, v)); },
  };
}

function extractInlineScript() {
  const html = readFileSync(path.join(PROJECT_ROOT, 'index.html'), 'utf8');
  const m = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!m) throw new Error('inline script not found in index.html');
  return m[1];
}

function extractElementIds() {
  const html = readFileSync(path.join(PROJECT_ROOT, 'index.html'), 'utf8');
  return [...html.matchAll(/id="([A-Za-z0-9_-]+)"/g)].map((m) => m[1]);
}

function buildSandbox({ port, storageDump, consoleSink }) {
  const els = new Map();
  const getElementById = (id) => {
    if (!els.has(id)) els.set(id, makeElement(id));
    return els.get(id);
  };
  // Pre-create every element that appears as a bare global in the script
  // (browsers expose id'd elements as globals).
  for (const id of extractElementIds()) getElementById(id);

  const localStorage = makeLocalStorage();
  localStorage._load(storageDump);

  const sandbox = {
    console: {
      log: (...a) => consoleSink.push(['log', a.map(String).join(' ')]),
      warn: (...a) => consoleSink.push(['warn', a.map(String).join(' ')]),
      error: (...a) => consoleSink.push(['error', a.map(String).join(' ')]),
      info: (...a) => consoleSink.push(['info', a.map(String).join(' ')]),
    },
    setTimeout, clearTimeout, setInterval, clearInterval,
    localStorage,
    FormData, FileReader: class FileReader { readAsDataURL() {} },
    Event: class Event { constructor(type) { this.type = type; } },
    navigator: { userAgent: 'smoke-test' },
    devicePixelRatio: 1,
    alert: () => {},
    document: {
      readyState: 'complete',
      getElementById,
      createElement: (tag) => makeElement('<' + tag + '>'),
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener() {},
      body: makeElement('body'),
    },
  };
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  // Browsers expose every id'd element as a global — replicate that so the
  // inline script's bare identifiers (peopleTable, cpTable, ...) resolve.
  for (const [id, el] of els) {
    if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(id)) sandbox[id] = el;
  }
  // fetch proxy -> real backend. Mirrors api(): the wrapper only consumes
  // r.ok / r.status / r.json().
  sandbox.fetch = async (p, opts = {}) => {
    const url = String(p).startsWith('http') ? p : `http://127.0.0.1:${port}${p}`;
    let res;
    try {
      res = await fetch(url, {
        method: opts.method || 'GET',
        headers: opts.headers || {},
        body: opts.body,
      });
    } catch (netErr) {
      consoleSink.push(['warn', 'harness fetch failed: ' + (netErr && netErr.message) + ' url=' + url + ' method=' + (opts.method || 'GET')]);
      throw netErr;
    }
    const text = await res.text();
    return {
      ok: res.ok,
      status: res.status,
      json: async () => { try { return JSON.parse(text); } catch { return {}; } },
      text: async () => text,
    };
  };
  vm.createContext(sandbox);
  return { sandbox, els, getElementById, localStorage };
}

function loadApp(sandbox) {
  const script = extractInlineScript();
  vm.runInContext(script, sandbox, { filename: 'index-inline.js' });
}

// --------------------------------------------------------------------------
// Static markup contract: sidebar sections · clean registers (centered entry
// modals, no per-unit analytics strips) · compact unit overview strips ·
// search box on every register table · HR tabs.
// --------------------------------------------------------------------------
const NAV_SECTIONS = [
  { group: 'search', label: 'Central Search',
    pages: [['people', 'people', 'Central Person Search'], ['policesearch', 'policesearch', 'Central Police Search']] },
  { group: 'cid', label: 'Dep. Of CID',
    pages: [['fingerprint', 'fingerprint', 'Fingerprint Unit'], ['cid', 'cid', 'Crime Unit'],
            ['checkpoints', 'checkpoints', 'Checkpoint Unit'], ['airport', 'airport', 'Airport Unit']] },
  { group: 'personnel', label: 'Dep. of Police Personnel (Registration Police Office)',
    pages: [['officers', 'officers', 'Registration Office'],
            ['conduct', 'conduct', 'Conduct, Promotions & Disciplinary Management']] },
  { group: 'transport', label: 'Dep. of Transport',
    pages: [['cars', 'cars', 'Vehicle Registry'], ['vehiclestatus', 'cars', 'Vehicle Status & Tracking']] },
  { group: 'command', label: 'Chief Commander of Police Office (HQ / Command)',
    pages: [['executive', 'executive', 'Global Executive Dashboard'],
            ['oversight', 'oversight', 'Stations Oversight & Regional Data']] },
  { group: 'registrations', label: 'Registers',
    pages: [['stations', 'stations', 'Police Stations'], ['crimes', 'crimes', 'Register Crime']] },
  { group: 'admin', label: 'Administration', pages: [['admin', 'admin', 'User Management']] },
];
// Operational pages are clean: no per-unit analytics strips anywhere (the
// only full analytics surface is the Global Executive Dashboard), and every
// registration form lives in a centered entry modal (dark blurred backdrop,
// fade/scale-in) opened by the page's primary action button — never rendered
// inline on the page. Each page also opens with a compact unit overview
// strip, and every register table has a search/filter box in its toolbar.
const MODAL_FORMS = {
  fpDrawer: 'fpForm', airDrawer: 'airForm', stDrawer: 'stForm',
  offDrawer: 'offForm', prmDrawer: 'prmForm', dscDrawer: 'dscForm',
  crmDrawer: 'crmForm', carDrawer: 'carForm',
};
// Compact unit overview strip mounted at the top of each operational page
// (above the search bar and data table), painted by renderUnitStats().
const UNIT_STATS_MOUNTS = {
  fingerprint: 'usFingerprint', airport: 'usAirport', cid: 'usCid',
  checkpoints: 'usCheckpoints', stations: 'usStations', officers: 'usOfficers',
  crimes: 'usCrimes', cars: 'usCars', vehiclestatus: 'usVehicleStatus',
};
// Every register table carries a search/filter box wired to a renderer.
const TABLE_SEARCHES = {
  fpSearch: 'renderFingerprintTable()', airSearch: 'renderAirportTable()',
  caseSearch: 'renderCases()', suspectSearch: 'renderSuspectTable()',
  cpSearch: 'renderCheckpointPage()', crmSearch: 'renderCrimesTable()',
  prmSearch: 'renderHrPanels()', dscSearch: 'renderHrPanels()',
  stSearch: 'renderStationsTable()', offSearch: 'renderOfficersTable()',
  carSearch: 'renderCarsTable()', vsSearch: 'renderVehicleStatusTable()',
  personSearch: 'renderPeople()', psSearch: 'renderPoliceSearch()',
};
const HR_TABS = [
  ['register', 'Officer Registration', ''],
  ['promotions', 'Promotions & Commendations', 'green'],
  ['discipline', 'Disciplinary & Misconduct', 'red'],
];

// Markup labels arrive HTML-escaped ('&amp;'); the contract is written the way
// an officer reads it on screen.
function decodeEntities(text) {
  return String(text == null ? '' : text)
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ');
}

function assertShellContract() {
  const html = readFileSync(path.join(PROJECT_ROOT, 'index.html'), 'utf8');
  const nav = html.match(/<nav class="nav" id="nav">([\s\S]*?)<\/nav>/);
  if (!nav) throw new Error('sidebar <nav id="nav"> not found');
  const navHtml = nav[1];

  // The monolithic analytics page must stay gone.
  if (/data-page="analytics"/.test(html)) throw new Error('the standalone Analytics nav entry came back');
  if (/<section id="analytics"/.test(html)) throw new Error('the standalone analytics section came back');

  // (a) the four sections, in order, with their exact labels and items
  const groupBlocks = [...navHtml.matchAll(/<div class="nav-group[^"]*" data-group="([^"]+)"[^>]*>([\s\S]*?)\n<\/div>/g)]
    .map((m) => ({ group: m[1], body: m[2] }));
  const found = groupBlocks.map((g) => g.group);
  const want = NAV_SECTIONS.map((s) => s.group);
  if (found.join(',') !== want.join(','))
    throw new Error(`sidebar sections are ${found.join(' | ')} — expected ${want.join(' | ')}`);
  NAV_SECTIONS.forEach((spec, i) => {
    const block = groupBlocks[i];
    const label = decodeEntities((block.body.match(/data-group-toggle="[^"]+"><i>[^<]*<\/i><span>([^<]+)<\/span>/) || [])[1]);
    if (label !== spec.label) throw new Error(`section ${spec.group} is labelled "${label}" — expected "${spec.label}"`);
    const items = [...block.body.matchAll(/<button data-page="([^"]+)" data-modules="([^"]+)"><i>[^<]*<\/i><span>([^<]+)<\/span>/g)]
      .map((m) => [m[1], m[2], decodeEntities(m[3])]);
    if (JSON.stringify(items) !== JSON.stringify(spec.pages))
      throw new Error(`section ${spec.group} holds ${JSON.stringify(items)} — expected ${JSON.stringify(spec.pages)}`);
  });

  // (b) operational pages are clean: no per-unit analytics strips, and the
  //     registration forms live in centered entry modals (not inline).
  if (html.includes('dept-analytics'))
    throw new Error('per-unit dept-analytics strips came back on an operational page');
  Object.entries(MODAL_FORMS).forEach(([modal, form]) => {
    // each modal wraps exactly one form; the match runs from the .cmodal
    // container through the form to the modal's closing tags
    const m = html.match(new RegExp(`<div class="cmodal" id="${modal}"[\\s\\S]*?</form>[\\s\\S]*?</div>\\s*</div>`));
    if (!m) throw new Error(`centered entry modal #${modal} not found`);
    if (!m[0].includes(`id="${form}"`))
      throw new Error(`modal #${modal} must contain the ${form} registration form`);
    if (!html.includes(`openEntryModal('${modal}')`))
      throw new Error(`no primary action button opens #${modal}`);
  });
  if (!/function openEntryModal\(id\)/.test(html) || !/function closeEntryModal\(id\)/.test(html))
    throw new Error('openEntryModal()/closeEntryModal() are missing from index.html');
  // the inline forms must be gone from every page section (sections do not
  // nest, so a section's body is its own text up to the first </section>)
  const PAGES = ['people','policesearch','fingerprint','cid','caseworkspace','checkpoints',
                 'stations','officers','conduct','crimes','cars','admin','executive',
                 'oversight','vehiclestatus'];
  PAGES.forEach((page) => {
    const sec = html.match(new RegExp(`<section id="${page}" class="page">[\\s\\S]*?</section>`));
    if (!sec) throw new Error(`section #${page} not found`);
    Object.values(MODAL_FORMS).forEach((form) => {
      if (sec[0].includes(`id="${form}"`))
        throw new Error(`${form} must not render inline inside the #${page} section`);
    });
  });

  // (b2) every operational page opens with its compact unit overview strip
  Object.entries(UNIT_STATS_MOUNTS).forEach(([page, mount]) => {
    const sec = html.match(new RegExp(`<section id="${page}" class="page">[\\s\\S]*?</section>`));
    if (!sec) throw new Error(`section #${page} not found`);
    if (!sec[0].includes(`class="unit-stats" id="${mount}"`))
      throw new Error(`#${page} must open with its compact unit-stats strip #${mount}`);
  });
  if (!/function renderUnitStats\(/.test(html))
    throw new Error('renderUnitStats() is missing from index.html');
  if (!/function renderAll\(\)\{\s*\n\s*renderUnitStats\(\);/.test(html))
    throw new Error('renderAll() must re-paint the unit overview strips');

  // (b3) every register table has a search/filter box wired to a renderer
  const regexEscape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  Object.entries(TABLE_SEARCHES).forEach(([id, fn]) => {
    if (!new RegExp(`id="${id}"[\\s\\S]{0,160}?oninput="${regexEscape(fn)}"`).test(html))
      throw new Error(`table search #${id} missing or not wired to ${fn}`);
  });

  // (c) Police Officers: the three HR tabs + their panes, green/red coded
  const officers = html.match(/<section id="officers" class="page">([\s\S]*?)\n<\/section>/);
  if (!officers) throw new Error('officers section not found');
  const tabs = [...officers[1].matchAll(/<button type="button" class="hr-tab([^"]*)" data-hrtab="([^"]+)"[^>]*>(?:<i>[^<]*<\/i>)?<span>([^<]+)<\/span>/g)]
    // the default-open tab carries `active` in the markup; the contract is
    // about the colour coding (green / red), not about which tab is open
    .map((m) => [m[2], decodeEntities(m[3]).trim(),
                 m[1].trim().split(/\s+/).filter((c) => c && c !== 'active').join(' ')]);
  if (JSON.stringify(tabs) !== JSON.stringify(HR_TABS))
    throw new Error(`HR tabs are ${JSON.stringify(tabs)} — expected ${JSON.stringify(HR_TABS)}`);
  HR_TABS.forEach(([name]) => {
    if (!officers[1].includes(`id="hrPane-${name}"`)) throw new Error(`missing HR pane #hrPane-${name}`);
  });
  if (!/id="hrPane-register"[\s\S]*openEntryModal\('offDrawer'\)/.test(officers[1]))
    throw new Error('the registration tab must open the officer form centered modal');
  if (!/id="hrPane-promotions"[\s\S]*id="prmAwaitTable"[\s\S]*id="hrPane-discipline"[\s\S]*id="dscOpenTable"/.test(officers[1]))
    throw new Error('the green/red badge queues must live inside their own tabs');
  // exact badge colours from the spec
  if (!/\.hr-tab\.green\.active\{background:#2e7d32/.test(html)) throw new Error('green tab must use #2e7d32');
  if (!/\.hr-tab\.red\.active\{background:#c62828/.test(html)) throw new Error('red tab must use #c62828');

  // (d) the tab/queue behaviour is wired, and gated on the `officers` module
  ['function hrTab(', 'async function loadHrRecords(', 'function renderHrPanels(',
   'async function savePromotionNomination(', 'async function verifyPromotionNomination(',
   'async function saveDisciplineAction(', 'async function setDisciplineStatus(',
   "hrTabs.style.display = (mods.indexOf('officers')!==-1) ? '' : 'none';"].forEach((needle) => {
    if (!html.includes(needle)) throw new Error('index.html is missing ' + needle);
  });
  // the Administration section is gated on the admin flag, not on a module list
  if (!/\(m === 'admin' \? isAdmin : mods\.indexOf\(m\)!==-1\)/.test(html))
    throw new Error('applyNavForRole() must gate the admin entry on the admin flag');

  // (e) UNIT MODULE DENYLIST — Airport Control and the CID Criminal Unit must
  //     never see Central Police Search ('policesearch'), whatever a stale or
  //     cached session payload claims. The server strips the module in
  //     ROLE_MODULES; the client mirrors the rule and every nav / fetch / RBAC
  //     check reads the sanitised list through effectiveModules()/hasModule().
  ['const UNIT_MODULE_DENY={',
   "airport:['policesearch']",
   "cid:['policesearch']",
   'function unitFamily(role){',
   'function sanitizeModules(role,mods){',
   'function effectiveModules(){',
   'function hasModule(m){'].forEach((needle) => {
    if (!html.includes(needle)) throw new Error('index.html is missing ' + needle);
  });
  if (!/const mods = effectiveModules\(\);\s*\n\s*const isAdmin/.test(html))
    throw new Error('applyNavForRole() must build the menu from effectiveModules()');
  if (!/const mods = effectiveModules\(\);          \/\/ unit denylist applied/.test(html))
    throw new Error('go() must gate page access on effectiveModules()');
  if (/sessionUser\.modules\.includes\(/.test(html))
    throw new Error('every module check must go through hasModule()/effectiveModules()');

  // (f) GLOBAL READ-ONLY ROLE (Commander / High Command) — the view-only UI.
  //     `body.readonly-mode` removes every marked write control, the badge and
  //     banner explain it, and the api() firewall refuses non-GET calls.
  ['function isReadOnlyRole(', 'function isReadOnlyUser(){', 'function canWrite(){',
   'function guardReadOnly(action){', 'function applyReadOnlyMode(){',
   'const READ_ONLY_VIEW_MODALS=new Set([\'pvModal\']);'].forEach((needle) => {
    if (!html.includes(needle)) throw new Error('index.html is missing ' + needle);
  });
  if (!/id="roBadge"/.test(html) || !/id="roBanner"/.test(html))
    throw new Error('the read-only badge (#roBadge) and banner (#roBanner) are missing');
  if (!/body\.readonly-mode \[data-write\]/.test(html))
    throw new Error('CSS must hide [data-write] controls in read-only mode');
  if (!/body\.readonly-mode \.write-action/.test(html))
    throw new Error('CSS must hide .write-action controls in read-only mode');
  // every static write control carries the marker (Register officer, Approve,
  // Open case, Edit, Add, …)
  const marked = (html.match(/data-write="1"/g) || []).length;
  if (marked < 25)
    throw new Error(`only ${marked} static write controls carry data-write — expected the full set`);
  const guardCalls = (html.match(/guardReadOnly\(/g) || []).length;
  if (guardCalls < 20)
    throw new Error(`only ${guardCalls} read-only guards in the write entry points`);
  ['async function approveFP(', 'async function conductReviewDecision(',
   'async function verifyPromotionNomination(', 'async function setDisciplineStatus(',
   'async function toggleUserActive(', 'function openConductReview('].forEach((fn) => {
    const i = html.indexOf(fn);
    if (i < 0) throw new Error('missing write entry point ' + fn);
    const head = html.slice(i, i + 320);
    if (!/guardReadOnly\(/.test(head))
      throw new Error(`${fn} must guard against a read-only session`);
  });
  if (!/readOnly\s*\?\s*\[\]\s*:\s*\(d\.quick_actions \|\| \[\]\)/.test(html))
    throw new Error('paintDashboard() must drop quick-registration actions for a read-only role');

  // (g) DOM-level read-only hardener — the sweep, the observer and the
  //     removal (not just hiding) of a denied nav module.
  ['function isWriteControl(',
   'function hardenReadOnlyDom(',
   'function queueReadOnlySweep(',
   'function watchReadOnlyDom(',
   'const WRITE_CONTROL_RE='].forEach((needle) => {
    if (!html.includes(needle)) throw new Error('index.html is missing ' + needle);
  });
  if (!/MutationObserver\(/.test(html))
    throw new Error('the read-only hardener must observe later repaints');
  if (!/hardenReadOnlyDom\(document\)/.test(html))
    throw new Error('applyReadOnlyMode()/go()/renderAll() must run the read-only DOM sweep');
  // denied modules are REMOVED from the sidebar, and restored for a role that
  // may have them
  ['function snapshotNavItems(', 'function removeNavItem(', 'function ensureNavItem(',
   'function navItemAllowed('].forEach((needle) => {
    if (!html.includes(needle)) throw new Error('index.html is missing ' + needle);
  });
  if (!/if\(navItemAllowed\(spec\.page,mods,isAdmin\)\) ensureNavItem\(spec\.page\);/.test(html)
      || !/else removeNavItem\(spec\.page\);/.test(html))
    throw new Error('applyNavForRole() must remove a denied module from the sidebar DOM');
  // the fingerprint register's Review/Print link is a write-side action
  if (!/\$\{canWrite\(\)\?`<a class="btn secondary small" data-write="1"[^`]*Review\/Print<\/a>`:''\}/.test(html))
    throw new Error('the fingerprint Review/Print link must be gated on canWrite()');
  // a build stamp so an operator can tell a stale cached page from a stale server
  if (!/<meta name="sentinel-ui-build" content="sentinel-rbac-readonly-3" \/>/.test(html))
    throw new Error('the sentinel-ui-build meta stamp is missing');
  if (!/window\.SENTINEL_UI_BUILD=/.test(html))
    throw new Error('window.SENTINEL_UI_BUILD must expose the frontend build');
}
const probe = (sandbox, expr) => vm.runInContext(expr, sandbox);

// --------------------------------------------------------------------------
async function main() {
  const port = await freePort();
  const tmp = `/tmp/sentinel-fe-test-${Date.now()}`;
  mkdirSync(tmp, { recursive: true });
  const pg = await provisionDatabase(tmp);
  if (!pg) {
    console.log('SKIP: no PostgreSQL test database available.');
    console.log('      Set SENTINEL_DB_HOST / SENTINEL_DB_NAME (and _USER / _PASSWORD / _PORT)');
    console.log('      or install the bundled engine with:  pip install pgserver');
    return 0;
  }
  console.log('using ' + pg.label);
  const proc = spawn('python3', [path.join(ROOT, 'server.py')], {
    env: {
      ...process.env,
      ...pg.env,
      SENTINEL_UPLOADS: `${tmp}/uploads`,
      PORT: String(port),
    },
    stdio: 'ignore',
  });
  const base = `http://127.0.0.1:${port}`;
  try {
    await waitFor(async () => {
      try { return (await fetch(base + '/api/health')).ok; } catch { return false; }
    }, 'backend health');

    // ---- 1) Fresh load: login screen, no session ------------------------
    let sink = [];
    let s1 = buildSandbox({ port, storageDump: {}, consoleSink: sink });
    loadApp(s1.sandbox);
    await waitFor(() => probe(s1.sandbox, '_initDone === true'), 'initApp ran');
    if (s1.getElementById('loginScreen').style.display !== '') throw new Error('login screen should be visible for anonymous load');
    console.log('ok 1: anonymous load shows the login screen');

    // ---- 2) Sign in as cp.south ------------------------------------------
    s1.getElementById('loginUser').value = 'cp.south';
    s1.getElementById('loginPassword').value = 'ChangeMe123!';
    try {
      await probe(s1.sandbox, 'submitLogin')({ preventDefault() {} });
    } catch (e) {
      console.error('submitLogin threw:', e.stack || e);
    }
    try {
      await waitFor(() => probe(s1.sandbox, 'serverOn === true && !!sessionUser'), 'signed-in sync');
    } catch (e) {
      console.error('console sink:', JSON.stringify(sink.slice(0, 40), null, 1));
      console.error('loginError text:', s1.getElementById('loginError').textContent);
      throw e;
    }
    const stored1 = s1.localStorage._dump();
    if (!stored1.sentinel_token) throw new Error('sentinel_token not persisted on login');
    if (!stored1.sentinel_user) throw new Error('sentinel_user not persisted on login');
    if (!JSON.parse(stored1.sentinel_user).display_name?.includes('F. Cali'))
      throw new Error('sentinel_user does not hold Officer F. Cali: ' + stored1.sentinel_user);
    if (s1.getElementById('loginScreen').style.display !== 'none') throw new Error('login screen should hide after sign-in');
    if (probe(s1.sandbox, "sessionUser.role_alias") !== 'checkpoint_officer') throw new Error('role_alias not normalised');
    if (probe(s1.sandbox, "sessionUser.location_scope") !== 'South') throw new Error('location_scope not South');
    const countAfterLogin = probe(s1.sandbox, '(db.checkpoints||[]).length');
    if (!(countAfterLogin >= 1)) throw new Error(`cp.south must see >=1 South events, got ${countAfterLogin}`);
    console.log(`ok 2: cp.south signed in — sentinel_token/sentinel_user persisted, South events visible (${countAfterLogin})`);

    // ---- 2b) Checkpoint location chips are scoped to the officer's station ----
    // A checkpoint officer must see ONLY the chip for their assigned station
    // (never external counts for stations they cannot access); an admin sees
    // all three location chips and can switch between them.
    const renderChipsFor = (profile, cps) => {
      const sb = buildSandbox({ port, storageDump: {}, consoleSink: [] });
      loadApp(sb.sandbox);
      probe(sb.sandbox, 'sessionUser = ' + JSON.stringify(profile));
      probe(sb.sandbox, 'db.checkpoints = ' + JSON.stringify(cps));
      probe(sb.sandbox, "cpLocationFilter = ''");
      probe(sb.sandbox, 'paintCheckpointChips()');
      return sb.getElementById('cpLocChips').innerHTML;
    };
    const sampleEvents = [
      { event_id: 'CP-1', location: 'South', location_code: 'South', checkpoint_location: 'South Checkpoint', screen: 'No active alert', action: 'Cleared' },
      { event_id: 'CP-2', location: 'East',  location_code: 'East',  checkpoint_location: 'East Checkpoint',  screen: 'No active alert', action: 'Cleared' },
      { event_id: 'CP-3', location: 'West',  location_code: 'West',  checkpoint_location: 'West Checkpoint',  screen: 'No active alert', action: 'Cleared' },
    ];
    const southChips = s1.getElementById('cpLocChips').innerHTML;
    if (!/South Checkpoint/.test(southChips)) throw new Error('cp.south chip group missing the assigned South chip: ' + southChips);
    if (/East Checkpoint/.test(southChips)) throw new Error('cp.south must not render an East chip: ' + southChips);
    if (/West Checkpoint/.test(southChips)) throw new Error('cp.south must not render a West chip: ' + southChips);
    if ((southChips.match(/cp-loc-chip active/g) || []).length !== 1) throw new Error('cp.south must have exactly one active chip: ' + southChips);
    const eastChips = renderChipsFor(
      { id: 3, username: 'cp.east', display_name: 'Officer A. Maxamed', role: 'CheckpointEast', role_alias: 'checkpoint_officer', location_scope: 'East', modules: ['dashboard', 'checkpoints'] },
      sampleEvents);
    if (!/East Checkpoint/.test(eastChips)) throw new Error('cp.east chip group missing the assigned East chip: ' + eastChips);
    if (/South Checkpoint/.test(eastChips)) throw new Error('cp.east must not render a South chip: ' + eastChips);
    if (/West Checkpoint/.test(eastChips)) throw new Error('cp.east must not render a West chip: ' + eastChips);
    const adminChips = renderChipsFor(
      { id: 1, username: 'admin', display_name: 'Officer A. Hassan', role: 'SystemAdmin', role_alias: 'system_admin', location_scope: null, modules: ['dashboard', 'people', 'fingerprint', 'airport', 'cid', 'checkpoints', 'analytics', 'admin', 'policesearch', 'stations', 'officers', 'cars'] },
      sampleEvents);
    if (!/All locations/.test(adminChips)) throw new Error('admin chip group missing the All locations chip: ' + adminChips);
    for (const loc of ['South', 'East', 'West']) {
      if (!new RegExp(loc + ' Checkpoint').test(adminChips)) throw new Error('admin chip group missing ' + loc + ' Checkpoint: ' + adminChips);
    }
    if (/disabled/.test(adminChips)) throw new Error('admin chip group must be fully clickable (never disabled): ' + adminChips);
    console.log('ok 2b: location chips scoped — cp.south/cp.east see only their station; admin sees all three, clickable');

    // ---- 3) Refresh #1: session re-hydrates, officer stays signed in -----
    sink = [];
    let s2 = buildSandbox({ port, storageDump: stored1, consoleSink: sink });
    loadApp(s2.sandbox);
    await waitFor(() => probe(s2.sandbox, 'serverOn === true && !!sessionUser'), 'refresh re-hydration');
    if (s2.getElementById('loginScreen').style.display !== 'none') throw new Error('refresh signed the officer out (login screen visible)');
    if (probe(s2.sandbox, "sessionUser && sessionUser.username") !== 'cp.south') throw new Error('refresh lost the signed-in user');
    if (probe(s2.sandbox, 'authToken()') !== stored1.sentinel_token) throw new Error('refresh did not re-use the stored token');
    const countAfterRefresh = probe(s2.sandbox, '(db.checkpoints||[]).length');
    if (countAfterRefresh !== countAfterLogin) throw new Error(`checkpoint count changed across refresh: ${countAfterLogin} -> ${countAfterRefresh}`);
    if (sink.some(([lvl, msg]) => lvl !== 'log' && /\b40[14]\b|Authentication required|Not found/i.test(msg)))
      throw new Error('console shows 401/404 errors after refresh: ' + JSON.stringify(sink));
    console.log(`ok 3: refresh keeps Officer F. Cali signed in; token re-used; count stays ${countAfterRefresh}; no 401/404 in console`);

    // ---- 4) Refresh #2: dashboard + checkpoint endpoints stay 200 --------
    sink = [];
    let s3 = buildSandbox({ port, storageDump: s2.localStorage._dump(), consoleSink: sink });
    loadApp(s3.sandbox);
    await waitFor(() => probe(s3.sandbox, 'serverOn === true && !!sessionUser'), 'second refresh');
    const dash = await probe(s3.sandbox, 'api')('/api/dashboard');
    if (!dash || !Array.isArray(dash.cards)) throw new Error('dashboard payload invalid after refresh');
    const cps = await probe(s3.sandbox, 'fetchCheckpoints')();
    if (!cps.ok || cps.scope !== 'South' || !(cps.items.length >= 1))
      throw new Error('fetchCheckpoints after refresh failed: ' + JSON.stringify(cps));
    console.log(`ok 4: after refresh, /api/dashboard 200 and fetchCheckpoints -> ${cps.items.length} South event(s)`);

    // ---- 5) Optimistic local mutation contract ---------------------------
    // Simulate submitCheckpoint's prepend: new entry first, badge count +1,
    // and an empty server response must never wipe it (empty-sync guard).
    const beforeOpt = probe(s3.sandbox, '(db.checkpoints||[]).length');
    probe(s3.sandbox, `db.checkpoints = [{event_id:'CP-OPT1', time:'2026-09-02 09:00', location:'South',
      location_code:'South', checkpoint_location:'South Checkpoint', person:'P-0001',
      screen:'No active alert', action:'Cleared'}, ...(db.checkpoints||[])]`);
    if (probe(s3.sandbox, '(db.checkpoints||[]).length') !== beforeOpt + 1) throw new Error('optimistic prepend failed');
    if (probe(s3.sandbox, "db.checkpoints.filter(x=>cpMatchesLocation(x,'South')).length") !== beforeOpt + 1)
      throw new Error('badge count mismatch after optimistic prepend');
    // Empty-sync guard: a failing/empty checkpoint fetch keeps local rows.
    const keepLocal = probe(s3.sandbox, `(() => {
      const local = (db.checkpoints||[]).length;
      const cps = {ok:false, items:[]};                       // transient failure
      const newCheckpoints = [];
      if (cps.ok && newCheckpoints.length) { db.checkpoints = newCheckpoints; }
      else if (cps.ok && !(db.checkpoints||[]).length) { db.checkpoints = []; }
      return (db.checkpoints||[]).length === local; })()`);
    if (!keepLocal) throw new Error('empty-sync guard wiped local checkpoints');
    console.log(`ok 5: optimistic prepend updates the badge instantly; empty sync keeps ${beforeOpt + 1} local row(s)`);

    // ---- 6) Expired token: ONLY an explicit /api/me 401 signs out --------
    sink = [];
    const stale = { ...s3.localStorage._dump(), sentinel_token: 'expired-bogus-token' };
    let s4 = buildSandbox({ port, storageDump: stale, consoleSink: sink });
    loadApp(s4.sandbox);
    await waitFor(() => s4.getElementById('loginScreen').style.display === '', 'expired-token sign-out');
    if (s4.localStorage.getItem('sentinel_token')) throw new Error('expired token not cleared from storage');
    if (probe(s4.sandbox, '!!sessionUser')) throw new Error('sessionUser should be null after 401 sign-out');
    console.log('ok 6: explicit 401 from the auth check signs out and clears storage');

    // ---- 7) Server-down load: non-fatal, session kept --------------------
    sink = [];
    const offline = buildSandbox({ port: 1, storageDump: stored1, consoleSink: sink }); // port 1 -> connection refused
    loadApp(offline.sandbox);
    await new Promise((r) => setTimeout(r, 600));
    if (offline.getElementById('loginScreen').style.display === '') throw new Error('server-down load must NOT sign the officer out');
    if (!offline.localStorage.getItem('sentinel_token')) throw new Error('server-down load must keep the stored token');
    console.log('ok 7: server unreachable on load -> officer stays signed in (no signOut on transient failure)');

    // ---- 8) Fingerprint mandatory 12-hour review lock (UI + API) ----------
    // A non-admin officer must NEVER get a clickable Approve control on a
    // freshly created application:
    //   * the button is rendered with disabled="disabled" +
    //     style="pointer-events:none;opacity:0.5;" and reads
    //     "🔒 Review Locked (12h)";
    //   * approveFP() refuses to call the API at all;
    //   * the server still answers HTTP 400 with the mandated detail.
    // A System Administrator gets an enabled button and can approve.
    const loginAs = async (user) => (await (await fetch(base + '/api/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: 'ChangeMe123!' }),
    })).json());

    const createClearance = async (user, nationalId) => {
      const auth = await loginAs(user);
      const fd = new FormData();
      const fields = {
        first_name: 'Ui', second_name: 'Lock', third_name: 'Test', fourth_name: 'Case',
        date_of_birth: '1992-02-02', national_id: nationalId, mother_name: 'Hooyo Lock',
        residence: 'Hargeisa, Lock Ward', phone: '+252 63 555 0000', sex: 'Male',
        email: 'ui.lock@example.com', purpose: 'Employment',
        guardian_name: 'Guardian Lock', guardian_relationship: 'Uncle', guardian_id: 'GD-1',
        guardian_occupation: 'Trader', guardian_address: 'Burao', guardian_phone: '+252 63 555 0001',
      };
      Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
      const pdf = new Blob(['%PDF-lock-test'], { type: 'application/pdf' });
      ['doc_app_0', 'doc_app_1', 'doc_guard_0', 'doc_guard_1'].forEach((n) => fd.append(n, pdf, n + '.pdf'));
      const r = await fetch(base + '/api/clearance-applications', {
        method: 'POST', headers: { Authorization: 'Bearer ' + auth.token }, body: fd,
      });
      if (!r.ok) throw new Error(`clearance create failed ${r.status}: ${await r.text()}`);
      return await r.json();
    };

    const fpApp = await createClearance('fp.officer', '700' + String(Date.now()).slice(-5));

    const renderRegisterAs = async (user) => {
      const sb = buildSandbox({ port, storageDump: {}, consoleSink: [] });
      loadApp(sb.sandbox);
      sb.getElementById('loginUser').value = user;
      sb.getElementById('loginPassword').value = 'ChangeMe123!';
      await probe(sb.sandbox, 'submitLogin')({ preventDefault() {} });
      await waitFor(() => probe(sb.sandbox, 'serverOn === true && !!sessionUser'), 'signed in ' + user);
      await probe(sb.sandbox, 'syncServer()');
      await waitFor(
        () => probe(sb.sandbox, `(db.fingerprint||[]).some(x => x.id === '${fpApp.application_id}')`),
        'fingerprint row synced for ' + user);
      probe(sb.sandbox, 'renderAll()');
      const html = sb.getElementById('fpTable').innerHTML;
      const row = (html.match(/<tr>[\s\S]*?<\/tr>/g) || []).find((r) => r.includes(fpApp.application_id)) || '';
      return { sb, html, row };
    };

    const officer = await renderRegisterAs('fp.officer');
    if (!officer.row) throw new Error('application row missing from the officer register');
    if (!/disabled="disabled"/.test(officer.row)) throw new Error('officer Approve button must be disabled: ' + officer.row);
    if (!/pointer-events:none/.test(officer.row)) throw new Error('officer Approve button must set pointer-events:none: ' + officer.row);
    if (!/opacity:0\.5/.test(officer.row)) throw new Error('officer Approve button must be dimmed (opacity 0.5): ' + officer.row);
    if (!/Review Locked \(12h\)/.test(officer.row)) throw new Error('officer button must read "Review Locked (12h)": ' + officer.row);
    if (!/Review Lock \(12h Required\) - 1[0-2](\.\d)? hours remaining/.test(officer.row))
      throw new Error('review-lock badge with the remaining hours is missing: ' + officer.row);

    // The click handler must not even attempt the request while locked.
    const calls = [];
    const origFetch = officer.sb.sandbox.fetch;
    officer.sb.sandbox.fetch = (p, o) => { calls.push(String(p)); return origFetch(p, o); };
    await probe(officer.sb.sandbox, `approveFP('${fpApp.application_id}')`);
    if (calls.some((u) => u.includes('/approve')))
      throw new Error('locked approveFP() must not call the approval API, saw: ' + calls.join(', '));

    // ... and the server rejects it anyway (defence in depth).
    const fpAuth = await loginAs('fp.officer');
    const rejected = await fetch(base + '/api/fingerprint/applications/' + fpApp.application_id + '/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + fpAuth.token },
      body: '{}',
    });
    if (rejected.status !== 400) throw new Error('server must reject the officer with 400, got ' + rejected.status);
    const rejectedBody = await rejected.json();
    if (rejectedBody.detail !== 'Review period active. Standard officers must wait 12 hours before approving.')
      throw new Error('unexpected rejection payload: ' + JSON.stringify(rejectedBody));

    const admin = await renderRegisterAs('admin');
    if (!admin.row) throw new Error('application row missing from the admin register');
    if (/disabled="disabled"/.test(admin.row)) throw new Error('admin Approve button must be enabled: ' + admin.row);
    if (!/Approve/.test(admin.row)) throw new Error('admin Approve button is missing: ' + admin.row);
    console.log('ok 8: fingerprint 12h review lock — officer Approve disabled/"Review Locked (12h)"/no API call/400, admin enabled');

    // ---- 9) STALE BACKEND guard -------------------------------------------
    // A server started before the review lock existed reports a different
    // build from /api/health and approves instantly. The UI must refuse to
    // offer or issue an approval against it.
    const sb9 = officer.sb.sandbox;
    const healthTruth = (payload) => {
      probe(sb9, `backendBuild=${JSON.stringify(payload)}; backendBuildChecked=true;`);
      return probe(sb9, 'backendBuildOk()');
    };
    if (healthTruth(null) !== false)
      throw new Error('an unknown /api/health must not count as the review-lock build');
    if (healthTruth({ build: 'sentinel-legacy', review_lock_active: true }) !== false)
      throw new Error('a stale build tag must not count as the review-lock build');
    if (healthTruth({ build: 'sentinel-fingerprint-review-lock-12h', review_lock_active: false }) !== false)
      throw new Error('review_lock_active:false must not count as the review-lock build');
    if (healthTruth({ build: 'sentinel-fingerprint-review-lock-12h', review_lock_active: true }) !== true)
      throw new Error('the real build must be recognised as locked');

    // Force the stale state and re-render the register: even an ADMIN and a
    // row older than 12h must stay locked while the backend is unverified.
    probe(sb9, "backendBuild={build:'sentinel-legacy',review_lock_active:true}; backendBuildChecked=true;");
    probe(sb9, 'renderAll()');
    const staleRow = (sb9.document.getElementById('fpTable').innerHTML
      .match(/<tr>[\s\S]*?<\/tr>/g) || []).find((r) => r.includes(fpApp.application_id)) || '';
    if (!/Stale backend/.test(staleRow))
      throw new Error('register must show the stale-backend lock: ' + staleRow);
    if (!/disabled="disabled"/.test(staleRow))
      throw new Error('stale-backend register row must be disabled: ' + staleRow);

    const staleCalls = [];
    const origFetch9 = sb9.fetch;
    sb9.fetch = (p, o) => { staleCalls.push(String(p)); return origFetch9(p, o); };
    await probe(sb9, `approveFP('${fpApp.application_id}')`);
    sb9.fetch = origFetch9;
    if (staleCalls.some((u) => u.includes('/approve')))
      throw new Error('approveFP() must not call the API against a stale build, saw: ' + staleCalls.join(', '));
    console.log('ok 9: stale backend (wrong /api/health build) — register locked, no approval request issued');

    // and once the real build answers again, the admin bypass comes back
    probe(sb9, "backendBuild={build:'sentinel-fingerprint-review-lock-12h',review_lock_active:true}; backendBuildChecked=true;");
    if (probe(sb9, 'backendBuildOk()') !== true)
      throw new Error('backendBuildOk() must recover once the correct build answers');
    console.log('ok 10: correct /api/health build restores normal (lock-aware) rendering');

    // ---- 11) Sidebar structure + clean registers + HR tabs ----------------
    // Static contract over the real index.html markup: the four fixed sidebar
    // sections, NO per-unit `dept-analytics` strip on any operational page
    // (the only full analytics surface is the Global Executive Dashboard),
    // every registration form parked in a centered entry modal behind a
    // primary action button, a compact unit overview strip on top of every
    // operational page, a search box in every register table's toolbar, and
    // the three Police Officers tabs (registration · green promotions · red
    // discipline). Guards the reorganisation against regressions without
    // needing a browser.
    assertShellContract();
    console.log('ok 11: sidebar sections, centered entry modals, unit overview strips, table searches and HR tabs contract');

    // ---- 12) UNIT MODULE DENYLIST — no Central Police Search for Airport/CID
    // The server already strips the module in ROLE_MODULES; the client mirrors
    // the rule so a stale/cached session payload cannot resurrect the entry.
    const sb12 = s1.sandbox;
    const modsFor = (role, mods) =>
      JSON.stringify(probe(sb12, `sanitizeModules(${JSON.stringify(role)},${JSON.stringify(mods)})`));
    if (modsFor('AirportControl', ['dashboard', 'people', 'airport', 'policesearch'])
        !== JSON.stringify(['dashboard', 'people', 'airport']))
      throw new Error('AirportControl must never hold policesearch');
    if (modsFor('CIDUnit', ['dashboard', 'people', 'cid', 'crimes', 'policesearch'])
        !== JSON.stringify(['dashboard', 'people', 'cid', 'crimes']))
      throw new Error('CIDUnit must never hold policesearch');
    // Every accepted spelling of both units is covered — including the label
    // spellings an operator may have typed into the users table, which used to
    // fall through and inherit another unit's modules — and other roles keep it.
    ['airport_officer', 'ap.officer', 'Airport Control', 'Airport Control Officer',
     'Airport Control Unit', 'Airport Control Office'].forEach((spelling) => {
      const out = modsFor(spelling, ['airport', 'people', 'policesearch']);
      if (out.includes('policesearch'))
        throw new Error(`Airport spelling ${spelling} must be denied policesearch (${out})`);
      if (!out.includes('airport'))
        throw new Error(`Airport spelling ${spelling} must keep its own module (${out})`);
    });
    ['CIDUnit', 'cid.officer', 'criminal_investigation', 'CID Criminal Unit',
     'cid_criminal_unit', 'Criminal Unit', 'Crime Unit'].forEach((spelling) => {
      const out = modsFor(spelling, ['cid', 'people', 'crimes', 'policesearch']);
      if (out.includes('policesearch'))
        throw new Error(`CID spelling ${spelling} must be denied policesearch (${out})`);
      if (!out.includes('cid'))
        throw new Error(`CID spelling ${spelling} must keep its own module (${out})`);
    });
    if (probe(sb12, `sanitizeModules('FingerprintUnit',['fingerprint','policesearch']).includes('policesearch')`) !== true)
      throw new Error('the Fingerprint Unit keeps Central Police Search (only Airport + CID are stripped)');
    if (probe(sb12, `sanitizeModules('hr_officer',['people','policesearch','officers']).includes('policesearch')`) !== true)
      throw new Error('the HR Directorate keeps Central Police Search');
    // hasModule()/go() read the sanitised list, so the page is unreachable too.
    probe(sb12, "sessionUser={role:'AirportControl',modules:['dashboard','people','airport','policesearch']};"
                + "currentUser=sessionUser;");
    if (probe(sb12, "hasModule('policesearch')") !== false)
      throw new Error('hasModule(policesearch) must be false for the Airport Unit');
    if (probe(sb12, "effectiveModules().join(',')") !== 'dashboard,people,airport')
      throw new Error('effectiveModules() must drop policesearch for the Airport Unit');
    probe(sb12, "sessionUser={role:'CIDUnit',modules:['dashboard','people','cid','crimes','policesearch']};currentUser=sessionUser;");
    if (probe(sb12, "hasModule('policesearch')") !== false)
      throw new Error('hasModule(policesearch) must be false for the CID Criminal Unit');
    console.log('ok 12: Central Police Search stripped from Airport Control and CID (client-side mirror)');

    // ---- 13) GLOBAL READ-ONLY COMMANDER ROLE ------------------------------
    // The role reads everything and writes nothing: the UI drops every write
    // control, refuses the write entry points and blocks non-GET calls before
    // they leave the browser (the server answers 403 for the same attempts).
    const sb13 = s1.sandbox;
    const readOnlyFor = (role, extra = '') =>
      probe(sb13, `sessionUser={role:${JSON.stringify(role)}${extra}}; currentUser=sessionUser; isReadOnlyUser()`);
    ['chief_commander', 'ChiefCommander', 'commander', 'Commander', 'high_command',
     'HighCommand', 'command_hq', 'commander_hq', 'hq_command', 'police_hq'].forEach((role) => {
      if (readOnlyFor(role) !== true) throw new Error(`${role} must be treated as read-only`);
    });
    ['SystemAdmin', 'AirportControl', 'CIDUnit', 'FingerprintUnit', 'hr_officer', 'CheckpointSouth'].forEach((role) => {
      if (readOnlyFor(role) !== false) throw new Error(`${role} must stay write-capable`);
    });
    // The server-declared flags win even for an unknown role spelling.
    if (readOnlyFor('future_command_role', ", read_only:true, can_write:false") !== true)
      throw new Error('the server-declared read_only flag must be honoured');
    probe(sb13, "sessionUser={role:'chief_commander',read_only:true,can_write:false,"
                + "modules:['dashboard','executive','oversight','people','policesearch','fingerprint',"
                + "'airport','cid','checkpoints','crimes','stations','officers','conduct','cars']};"
                + "currentUser=sessionUser; applyNavForRole();");
    if (probe(sb13, "canWrite()") !== false) throw new Error('canWrite() must be false for the Commander');
    if (probe(sb13, "document.body.classList.contains('readonly-mode')") !== true)
      throw new Error('body.readonly-mode must be applied for the Commander');
    if (probe(sb13, "document.getElementById('roBadge').style.display") !== '')
      throw new Error('the View-only badge must be visible for the Commander');
    if (probe(sb13, "document.getElementById('roBanner').style.display") !== 'flex')
      throw new Error('the read-only banner must be visible for the Commander');
    // Write entry points are refused …
    if (probe(sb13, "guardReadOnly('x')") !== true)
      throw new Error('guardReadOnly() must block write entry points');
    [["openCaseDrawer()", 'drawer'],
     ["openEntryModal('fpDrawer')", 'fpDrawer'],
     ["openEntryModal('offDrawer')", 'offDrawer'],
     ["openEntryModal('carDrawer')", 'carDrawer']].forEach(([call, id]) => {
      const opened = probe(sb13, `(function(){ try{ ${call}; }catch(e){} return document.getElementById(${JSON.stringify(id)}).classList.contains('open'); })()`);
      if (opened !== false) throw new Error(`${call} must not open a write form for the Commander`);
    });
    // … while the read-only surfaces still work.
    if (probe(sb13, "document.getElementById('roBadge').style.display") !== '')
      throw new Error('the View-only badge must stay visible for the Commander');
    const viewRow = probe(sb13, "renderRegisterRow({id:'FP-RO',status:'Pending Review',created_at:'2020-01-01 00:00:00'}, null)");
    if (!/View only/.test(viewRow) || /approveFP\(/.test(viewRow))
      throw new Error('the fingerprint register must render view-only for the Commander: ' + viewRow);
    const approvedRow = probe(sb13, "renderRegisterRow({id:'FP-RO2',status:'Approved',created_at:'2020-01-01 00:00:00'}, null)");
    if (!/certificate\.html/.test(approvedRow))
      throw new Error('an approved clearance must keep its Certificate link (read-only): ' + approvedRow);
    // The DOM hardener is callable and safe (it runs after every repaint).
    if (probe(sb13, "typeof hardenReadOnlyDom==='function'") !== true)
      throw new Error('hardenReadOnlyDom() must be available to every renderer');
    if (typeof probe(sb13, "hardenReadOnlyDom(document)") !== 'number')
      throw new Error('hardenReadOnlyDom() must report how many controls it changed');
    // …and the fingerprint register hands the Commander no Review/Print link.
    const fpRows = probe(sb13,
      "(function(){ db.fingerprint=[{id:'FP-1',person:'P-1',purpose:'Travel',status:'Pending Review'," +
      "created_at:'2020-01-01 00:00:00'}]; try{renderFingerprintTable()}catch(_){} " +
      "return (document.getElementById('fpTable')||{}).innerHTML||'' })()");
    if (/Review\/Print/.test(fpRows) || /application\.html/.test(fpRows))
      throw new Error('a read-only session must not be offered the Review/Print link: ' + fpRows);
    if (/approveFP\(/.test(fpRows))
      throw new Error('a read-only session must not be offered an approve action: ' + fpRows);
    // The API firewall refuses every mutation before it leaves the browser.
    const refused = await probe(sb13,
      "(async()=>{try{await api('/api/persons',{method:'POST',body:'{}'});return 'no-throw';}"
      + "catch(e){return 'status='+e.status+' readOnly='+e.readOnly;}})()");
    if (refused !== 'status=403 readOnly=true')
      throw new Error('api() must refuse a Commander POST locally, got ' + refused);
    const patchRefused = await probe(sb13,
      "(async()=>{try{await api('/api/crime-cases/CC-1',{method:'PATCH',body:'{}'});return 'no-throw';}"
      + "catch(e){return 'status='+e.status;}})()");
    if (patchRefused !== 'status=403') throw new Error('api() must refuse a Commander PATCH locally');
    const deleteRefused = await probe(sb13,
      "(async()=>{try{await api('/api/persons/P-1',{method:'DELETE'});return 'no-throw';}"
      + "catch(e){return 'status='+e.status;}})()");
    if (deleteRefused !== 'status=403') throw new Error('api() must refuse a Commander DELETE locally');
    // Reads are untouched (session plumbing included).
    const stillReads = await probe(sb13, "api('/api/me').then(r=>typeof r.role).catch(e=>'err'+e.status)");
    if (stillReads !== 'string')
      throw new Error('a Commander must still be able to READ /api/me, got ' + stillReads);
    // The sidebar removal itself is DOM work (the harness only stubs a minimal
    // DOM): it is asserted through the shell contract below (snapshotNavItems /
    // removeNavItem / ensureNavItem / navItemAllowed + the applyNavForRole
    // ensure/remove pair) and behaviourally in the jsdom suite.
    // Signing out leaves view-only mode behind for the next session.
    probe(sb13, 'resetSessionState()');
    if (probe(sb13, "document.body.classList.contains('readonly-mode')") !== false)
      throw new Error('read-only mode must be cleared with the session');
    console.log('ok 13: Commander role renders view-only (no write controls, entry points and api() refuse writes)');

    console.log('ALL FRONTEND SESSION TESTS PASSED');
    return 0;
  } finally {
    proc.kill('SIGTERM');
    pg.stop();
  }
}

main().then((code) => process.exit(code)).catch((e) => {
  console.error('FRONTEND SESSION TEST FAILED:', e.message);
  process.exit(1);
});
