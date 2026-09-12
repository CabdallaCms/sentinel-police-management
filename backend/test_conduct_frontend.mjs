#!/usr/bin/env node
/**
 * Officer Conduct, Promotions & Disciplinary Management — frontend
 * integration test (standard-library backend + Node VM, no browser).
 *
 * Boots backend/server.py against a temporary SQLite database, then runs
 * the real inline <script> from index.html inside a Node VM sandbox with a
 * minimal DOM stub. It exercises the Officers Registration Office journey:
 *
 *   1. Sign in as hr.officer (OfficerRegistration / HR Directorate) — the
 *      conduct module appears in the session's module list and the nav.
 *   2. Register a target officer, then open the HR Action Modal, search the
 *      officer by Service ID (POL-YYYY-XXXX), pick the green Promotion
 *      category + Rank Advancement, write the mandatory narrative and
 *      submit — the split-view table gains the ACT-YYYY-XXXX file with
 *      status 'Submitted to HR'.
 *   3. Validation: submitting without an officer / narrative keeps the
 *      modal open with the inline error banner (no request is sent).
 *   4. HR Approval Desk: the pending file renders with the one-click
 *      Approve action; approving executes the rank change (Sergeant ->
 *      Inspector), the officers register refreshes and the conduct badge
 *      counts update.
 *   5. Disciplinary (red) tab: a rejected Rank Demotion leaves the rank
 *      untouched.
 *   6. RBAC: a Fingerprint officer never sees the conduct module.
 *
 * Usage:  node backend/test_conduct_frontend.mjs
 */
import { spawn } from 'node:child_process';
import { readFileSync, mkdirSync } from 'node:fs';
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.dirname(ROOT);

function freePort() {
  return new Promise((resolve) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => {
      const p = s.address().port;
      s.close(() => resolve(p));
    });
  });
}

async function waitFor(fn, what, timeoutMs = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (await fn()) return;
    await new Promise((r) => setTimeout(r, 40));
  }
  throw new Error('timed out waiting for: ' + what);
}

// --------------------------------------------------------------------------
// Minimal DOM stub — the same surface as test_frontend_session.mjs, plus
// confirm() for the approval desk.
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
    files: [],
    checked: false,
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
  for (const id of extractElementIds()) getElementById(id);

  // Persistent pseudo-elements for the selector families the RBAC code
  // queries. The sidebar buttons have no element ids, so they cannot be
  // pre-created from the HTML — the harness fabricates one stub per nav
  // entry (data-page + data-modules) plus the in-page module gates
  // ([data-requires-module], e.g. the Conduct & Discipline shortcut on the
  // Police Officers page). applyNavForRole()/doLogout() write style.display
  // onto exactly these stubs, so the tests can assert real visibility.
  const NAV_ENTRIES = [
    ['dashboard', 'dashboard'], ['people', 'people'], ['policesearch', 'policesearch'],
    ['fingerprint', 'fingerprint'], ['cid', 'cid'], ['checkpoints', 'checkpoints'],
    ['airport', 'airport'], ['stations', 'stations'], ['officers', 'officers'],
    ['conduct', 'conduct'], ['cars', 'cars'], ['crimes', 'crimes'],
    ['analytics', 'analytics'], ['admin', 'admin'],
  ];
  const navButtons = NAV_ENTRIES.map(([page, modules]) => {
    const el = makeElement('nav-' + page);
    el.dataset.page = page;
    el.dataset.modules = modules;
    return el;
  });
  const officersConductLink = getElementById('officersConductLink');
  officersConductLink.dataset.requiresModule = 'conduct';
  const requiresModuleEls = [officersConductLink];

  const localStorage = makeLocalStorage();
  if (storageDump) {
    Object.entries(storageDump).forEach(([k, v]) => localStorage.setItem(k, v));
  }

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
    navigator: { userAgent: 'conduct-test' },
    devicePixelRatio: 1,
    alert: () => {},
    confirm: () => true,
    document: {
      readyState: 'complete',
      getElementById,
      createElement: (tag) => makeElement('<' + tag + '>'),
      querySelector: () => null,
      querySelectorAll: (sel) => {
        if (sel === '#nav button[data-page]') return navButtons;
        if (sel === '[data-requires-module]') return requiresModuleEls;
        return [];
      },
      addEventListener() {},
      body: makeElement('body'),
    },
  };
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox._navButtons = navButtons;   // exposed to the test assertions
  sandbox._requiresModuleEls = requiresModuleEls;
  for (const [id, el] of els) {
    if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(id)) sandbox[id] = el;
  }
  sandbox.fetch = async (p, opts = {}) => {
    const url = String(p).startsWith('http') ? p : `http://127.0.0.1:${port}${p}`;
    const res = await fetch(url, {
      method: opts.method || 'GET',
      headers: opts.headers || {},
      body: opts.body,
    });
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
  vm.runInContext(extractInlineScript(), sandbox, { filename: 'index-inline.js' });
}

const probe = (sandbox, expr) => vm.runInContext(expr, sandbox);

async function main() {
  const port = await freePort();
  const tmp = `/tmp/sentinel-conduct-test-${Date.now()}`;
  mkdirSync(tmp, { recursive: true });
  const proc = spawn('python3', [path.join(ROOT, 'server.py')], {
    env: {
      ...process.env,
      SENTINEL_DB: `${tmp}/db.sqlite`,
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

    // A target officer for the conduct files (registered via the API — the
    // officers register form is covered by the backend suite).
    const adminLogin = await (await fetch(base + '/api/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'ChangeMe123!' }),
    })).json();
    const boundary = '----conduct-fe';
    const mp = (fields, files) => {
      const parts = [];
      for (const [k, v] of Object.entries(fields)) {
        parts.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="${k}"\r\n\r\n${v}\r\n`));
      }
      for (const [k, [fn, content]] of Object.entries(files || {})) {
        parts.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="${k}"; filename="${fn}"\r\nContent-Type: application/octet-stream\r\n\r\n`));
        parts.push(Buffer.from(content, 'latin1'));
        parts.push(Buffer.from('\r\n'));
      }
      parts.push(Buffer.from(`--${boundary}--\r\n`));
      return Buffer.concat(parts);
    };
    const officerRes = await fetch(base + '/api/officers', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + adminLogin.token,
        'Content-Type': `multipart/form-data; boundary=${boundary}`,
      },
      body: mp({
        rank: 'Sergeant', unit: 'General Patrol', station_id: 'ST-001',
        date_of_enlistment: '2020-05-01', full_name: 'Cabdi Xasan Cali',
        mother_name: 'Faadumo', date_of_birth: '1990-01-01',
        place_of_birth: 'Laascaanood', contact_number: '+252 63 555 0123',
        guarantor_name: 'Xasan Cali', guarantor_address: 'Las Anod Main St',
        guarantor_contact: '+252 63 555 0999', doc1_type: 'National ID',
      }, { photo: ['p.jpg', '\xff\xd8\xff\xe0x'], doc1_file: ['id.pdf', '%PDF x'] }),
    });
    const officerJson = await officerRes.json();
    if (officerRes.status !== 201) throw new Error('officer registration failed: ' + JSON.stringify(officerJson));
    const serviceId = officerJson.service_id;

    // ---- 1) Sign in as the HR / Officer Registration Office -------------
    let sink = [];
    const s1 = buildSandbox({ port, storageDump: {}, consoleSink: sink });
    loadApp(s1.sandbox);
    await waitFor(() => probe(s1.sandbox, '_initDone === true'), 'initApp ran');
    s1.getElementById('loginUser').value = 'hr.officer';
    s1.getElementById('loginPassword').value = 'ChangeMe123!';
    await probe(s1.sandbox, 'submitLogin')({ preventDefault() {} });
    await waitFor(() => probe(s1.sandbox, 'serverOn === true && !!sessionUser'), 'HR sign-in');
    if (probe(s1.sandbox, "sessionUser.role") !== 'OfficerRegistration')
      throw new Error('hr.officer role mismatch: ' + JSON.stringify(probe(s1.sandbox, 'sessionUser')));
    if (!probe(s1.sandbox, "sessionUser.modules.includes('conduct')"))
      throw new Error('conduct module missing from HR session');

    // ---- 1b) HR lands directly on the Conduct & Disciplinary desk -------
    // defaultLandingPage() must send the Officer Registration Office to its
    // conduct desk (not the generic dashboard) on every sign-in.
    await waitFor(() => probe(s1.sandbox, "document.getElementById('conduct').classList.contains('active')"),
      'HR lands on the conduct desk');
    if (probe(s1.sandbox, "document.getElementById('dashboard').classList.contains('active')"))
      throw new Error('hr.officer must not land on the dashboard');
    // The sidebar shows the Conduct & Discipline entry for the HR role.
    const hrConductBtn = s1.sandbox._navButtons.find(b => b.dataset.page === 'conduct');
    if (!hrConductBtn || hrConductBtn.style.display === 'none')
      throw new Error('conduct sidebar entry hidden for hr.officer');
    await waitFor(() => probe(s1.sandbox, '(db.officers||[]).length >= 1'), 'officers synced');
    console.log('ok 1: hr.officer signed in — lands on the Conduct desk, sidebar entry visible, officers register synced');

    // ---- 2) Navigate to the conduct page and open the HR Action Modal ---
    await probe(s1.sandbox, "go('conduct')");
    if (probe(s1.sandbox, "(db.conduct||[]).length") !== 0)
      throw new Error('conduct register should start empty');
    probe(s1.sandbox, 'openConductModal()');
    if (!s1.getElementById('drawer').classList.contains('on'))
      throw new Error('HR action modal did not open');

    // Validation first: submit empty -> inline error, no request sent.
    const before = probe(s1.sandbox, '(db.conduct||[]).length');
    await probe(s1.sandbox, 'submitConductAction')({ preventDefault() {} });
    await new Promise(r => setTimeout(r, 150));
    if (!s1.getElementById('drawer').classList.contains('on'))
      throw new Error('modal must stay open on validation failure');
    if (!String(s1.getElementById('modalError').innerHTML).includes('Complete the required fields'))
      throw new Error('inline validation banner missing: ' + s1.getElementById('modalError').innerHTML);
    if (probe(s1.sandbox, '(db.conduct||[]).length') !== before)
      throw new Error('no submission should have been created');
    console.log('ok 2: empty HR action modal is rejected inline (no request sent)');

    // Fill the modal: officer search by Service ID, green promotion
    // category, Rank Advancement, narrative, station, datetime.
    s1.getElementById('cdOfficerSearch').value = serviceId;
    probe(s1.sandbox, `cdOfficerInput(${JSON.stringify(serviceId)})`);
    const suggestions = String(s1.getElementById('cdOfficerSuggest').innerHTML);
    if (!suggestions.includes(serviceId)) throw new Error('officer search suggestions missing: ' + suggestions);
    probe(s1.sandbox, `cdSelectOfficer(${JSON.stringify(serviceId)})`);
    if (probe(s1.sandbox, 'cdSelectedOfficer') !== serviceId)
      throw new Error('officer not selected');
    s1.getElementById('cdType').value = 'Promotion / Commendation';
    probe(s1.sandbox, 'cdTypeChanged()');
    if (!String(s1.getElementById('cdClassification').innerHTML).includes('Rank Advancement'))
      throw new Error('promotion classifications not offered');
    s1.getElementById('cdClassification').value = 'Rank Advancement';
    probe(s1.sandbox, 'cdClassificationChanged()');
    if (s1.getElementById('cdRankRow').style.display === 'none')
      throw new Error('rank row must appear for Rank Advancement');
    // Only ranks ABOVE Sergeant are selectable for the advancement.
    const rankOptions = String(s1.getElementById('cdRank').innerHTML);
    if (rankOptions.includes('"Constable"') || rankOptions.includes('"Sergeant"'))
      throw new Error('rank options must exclude the current rank and below: ' + rankOptions);
    s1.getElementById('cdRank').value = 'Inspector';
    probe(s1.sandbox, 'cdRankHint()');
    if (!s1.getElementById('cdRankHint').value.includes('Sergeant → Inspector'))
      throw new Error('rank transition hint wrong: ' + s1.getElementById('cdRankHint').value);
    s1.getElementById('cdNarrative').value =
      'Station report SR-2026-114: led the Caynabo recovery operation with distinction, recovering all stolen property.';
    s1.getElementById('cdStation').value = 'ST-001';
    s1.getElementById('cdSubmittedAt').value = '2026-09-10T08:30';
    await probe(s1.sandbox, 'submitConductAction')({ preventDefault() {} });
    await waitFor(() => probe(s1.sandbox, '(db.conduct||[]).length === 1'), 'conduct submission synced');
    const filed = probe(s1.sandbox, 'db.conduct[0]');
    if (filed.action_id !== 'ACT-2026-0001' || filed.status !== 'Submitted to HR')
      throw new Error('filed action wrong: ' + JSON.stringify(filed));
    if (filed.classification !== 'Rank Advancement' || filed.proposed_rank !== 'Inspector')
      throw new Error('filed classification/rank wrong: ' + JSON.stringify(filed));
    if (s1.getElementById('drawer').classList.contains('on'))
      throw new Error('modal must close after a successful submission');
    console.log('ok 3: HR action modal filed ACT-2026-0001 (Rank Advancement, Submitted to HR)');

    // ---- 3) Split view: green promotion tab + badge counts --------------
    probe(s1.sandbox, "cdTab('promotion')");
    const promoTable = String(s1.getElementById('cdPromoTable').innerHTML);
    if (!promoTable.includes('ACT-2026-0001') || !promoTable.includes(serviceId))
      throw new Error('promotion tab missing the new file: ' + promoTable);
    if (!promoTable.includes('▲') || !promoTable.includes('Inspector'))
      throw new Error('proposed rank not rendered in the promotion table');
    if (String(s1.getElementById('cdPromoCount').textContent) !== '1')
      throw new Error('green tab badge count wrong: ' + s1.getElementById('cdPromoCount').textContent);
    if (String(s1.getElementById('cdDeskCount').textContent) !== '1')
      throw new Error('approval-desk badge count wrong');
    console.log('ok 4: Promotions & Commendations tab lists the nominated officer (green badge = 1)');

    // ---- 4) HR Approval Desk: one-click approve executes the change -----
    probe(s1.sandbox, "cdTab('desk')");
    const deskTable = String(s1.getElementById('cdDeskTable').innerHTML);
    if (!deskTable.includes('ACT-2026-0001'))
      throw new Error('approval desk missing the pending file');
    // Pick the reviewing HR officer, then approve with one click.
    s1.getElementById('cdReviewerSelect').value = serviceId;
    probe(s1.sandbox, `conductReviewDecision('ACT-2026-0001','approve')`);
    await waitFor(() => probe(s1.sandbox, "(db.conduct||[]).find(a=>a.action_id==='ACT-2026-0001')?.status") === 'Verified & Approved',
      'approval applied');
    const approved = probe(s1.sandbox, "(db.conduct||[]).find(a=>a.action_id==='ACT-2026-0001')");
    if (approved.rank_applied !== true) throw new Error('rank_applied flag missing: ' + JSON.stringify(approved));
    await waitFor(() => probe(s1.sandbox,
      `(db.officers||[]).find(o=>o.service_id===${JSON.stringify(serviceId)})?.rank`) === 'Inspector',
      'officers register refreshed with the new rank');
    if (String(s1.getElementById('cdDeskCount').textContent) !== '0')
      throw new Error('desk badge must drop to 0 after approval');
    if (!String(s1.getElementById('cdPromoTable').innerHTML).includes('applied'))
      throw new Error('applied badge missing in the promotion table');
    console.log('ok 5: one-click approval executed Sergeant → Inspector and refreshed the officer register');

    // ---- 5) Disciplinary tab: rejected demotion leaves the rank alone ---
    probe(s1.sandbox, 'openConductModal()');
    probe(s1.sandbox, `cdSelectOfficer(${JSON.stringify(serviceId)})`);
    s1.getElementById('cdType').value = 'Disciplinary / Penalty';
    probe(s1.sandbox, 'cdTypeChanged()');
    if (!String(s1.getElementById('cdClassification').innerHTML).includes('Rank Demotion'))
      throw new Error('disciplinary classifications not offered');
    s1.getElementById('cdClassification').value = 'Rank Demotion';
    probe(s1.sandbox, 'cdClassificationChanged()');
    const demoteOptions = String(s1.getElementById('cdRank').innerHTML);
    if (demoteOptions.includes('"General"') || demoteOptions.includes('"Commander"'))
      throw new Error('demotion options must exclude ranks above the current one');
    s1.getElementById('cdRank').value = 'Sergeant';
    s1.getElementById('cdNarrative').value =
      'Case ref CID-2026-019: unauthorised release of a suspect from custody, logged in the station day-book.';
    s1.getElementById('cdCommander').value = serviceId;
    await probe(s1.sandbox, 'submitConductAction')({ preventDefault() {} });
    await waitFor(() => probe(s1.sandbox, '(db.conduct||[]).length === 2'), 'second conduct file');
    probe(s1.sandbox, "cdTab('disciplinary')");
    const discTable = String(s1.getElementById('cdDiscTable').innerHTML);
    if (!discTable.includes('ACT-2026-0002') || !discTable.includes('Rank Demotion'))
      throw new Error('disciplinary tab missing the new file: ' + discTable);
    if (String(s1.getElementById('cdDiscCount').textContent) !== '1')
      throw new Error('red tab badge count wrong');
    probe(s1.sandbox, `conductReviewDecision('ACT-2026-0002','reject')`);
    await waitFor(() => probe(s1.sandbox, "(db.conduct||[]).find(a=>a.action_id==='ACT-2026-0002')?.status") === 'Rejected',
      'rejection applied');
    const rankAfter = probe(s1.sandbox,
      `(db.officers||[]).find(o=>o.service_id===${JSON.stringify(serviceId)})?.rank`);
    if (rankAfter !== 'Inspector') throw new Error('rejected demotion must not change the rank, got ' + rankAfter);
    console.log('ok 6: Disciplinary & Misconduct tab (red) — rejected Rank Demotion leaves the rank untouched');

    // ---- 6) File view modal shows the immutable service history ---------
    probe(s1.sandbox, `openConductView('ACT-2026-0001')`);
    await waitFor(() => String(s1.getElementById('drawerBody').innerHTML).includes('service history'), 'detail drawer');
    const detail = String(s1.getElementById('drawerBody').innerHTML);
    if (!detail.includes('Sergeant') || !detail.includes('Inspector'))
      throw new Error('service history not rendered in the file view');
    if (!detail.includes('ACT-2026-0001')) throw new Error('detail view missing action id');
    console.log('ok 7: conduct file view shows the officer service history (Sergeant → Inspector)');

    // ---- 7) RBAC: fingerprint officer never sees the conduct module -----
    const meRes = await fetch(base + '/api/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'fp.officer', password: 'ChangeMe123!' }),
    });
    const fpLogin = await meRes.json();
    const condRes = await fetch(base + '/api/conduct', {
      headers: { 'Authorization': 'Bearer ' + fpLogin.token },
    });
    if (condRes.status !== 401) throw new Error('fingerprint officer must be denied /api/conduct, got ' + condRes.status);
    if (fpLogin.user.modules.includes('conduct'))
      throw new Error('fingerprint officer must not carry the conduct module');
    console.log('ok 8: RBAC — /api/conduct is denied to non-HR roles (401)');

    // ---- 9) Admin access: sidebar entry, officers-page shortcut --------
    // A SystemAdmin must see the Conduct & Discipline sidebar entry under
    // Police Registrations & Management, reach the desk, and find the
    // shortcut on the Police Officers page.
    const s2 = buildSandbox({ port, storageDump: {}, consoleSink: [] });
    loadApp(s2.sandbox);
    await waitFor(() => probe(s2.sandbox, '_initDone === true'), 'initApp ran (admin)');
    s2.getElementById('loginUser').value = 'admin';
    s2.getElementById('loginPassword').value = 'ChangeMe123!';
    await probe(s2.sandbox, 'submitLogin')({ preventDefault() {} });
    await waitFor(() => probe(s2.sandbox, 'serverOn === true && !!sessionUser'
      + " && sessionUser.role === 'SystemAdmin'"), 'admin sign-in');
    const adminConductBtn = s2.sandbox._navButtons.find(b => b.dataset.page === 'conduct');
    if (!adminConductBtn || adminConductBtn.style.display === 'none')
      throw new Error('conduct sidebar entry hidden for admin');
    probe(s2.sandbox, "go('conduct')");
    if (!probe(s2.sandbox, "document.getElementById('conduct').classList.contains('active')"))
      throw new Error("go('conduct') must keep the admin on the conduct desk");
    if (!String(s2.getElementById('cdSummaryStrip').innerHTML).includes('Pending HR review'))
      throw new Error('conduct summary strip not rendered for admin');
    // Police Officers page carries the Conduct & Discipline shortcut.
    probe(s2.sandbox, "go('officers')");
    if (!probe(s2.sandbox, "document.getElementById('officers').classList.contains('active')"))
      throw new Error("go('officers') must open the officers page for admin");
    if (s2.getElementById('officersConductLink').style.display === 'none')
      throw new Error('Conduct & Discipline shortcut hidden on the officers page for admin');
    // The shortcut badge mirrors the pending queue count (both files created
    // earlier in this run are closed — one approved, one rejected).
    if (String(s2.getElementById('officersConductPending').textContent) !== '0')
      throw new Error('officers-page conduct badge must mirror the pending count, got '
        + s2.getElementById('officersConductPending').textContent);
    console.log('ok 9: admin — conduct sidebar entry visible, desk reachable, officers-page shortcut with pending badge');

    // ---- 10) Stale-profile defense -------------------------------------
    // A profile cached BEFORE the conduct module existed (modules list
    // without 'conduct') must never hide the desk from a SystemAdmin.
    probe(s2.sandbox, "sessionUser = Object.assign({}, sessionUser, "
      + "{modules: ['dashboard','people','fingerprint','airport','cid','checkpoints',"
      + "'policesearch','stations','officers','cars','crimes','admin','analytics']}); "
      + "sessionVisibility = null; applyNavForRole();");
    if (adminConductBtn.style.display === 'none')
      throw new Error('stale cached profile must not hide the conduct nav entry from an admin');
    if (s2.getElementById('officersConductLink').style.display === 'none')
      throw new Error('stale cached profile must not hide the officers-page shortcut from an admin');
    probe(s2.sandbox, "go('conduct')");
    if (!probe(s2.sandbox, "document.getElementById('conduct').classList.contains('active')"))
      throw new Error('stale cached profile must not redirect an admin away from conduct');
    console.log('ok 10: stale cached admin profile (no conduct module) still sees and reaches the conduct desk');

    // ---- 11) Non-HR roles keep the desk hidden -------------------------
    // A CID officer has no conduct module: the sidebar entry stays hidden
    // and go('conduct') redirects — while the CID case workspace (a
    // sub-page without its own module key) still opens.
    const s3 = buildSandbox({ port, storageDump: {}, consoleSink: [] });
    loadApp(s3.sandbox);
    await waitFor(() => probe(s3.sandbox, '_initDone === true'), 'initApp ran (cid)');
    s3.getElementById('loginUser').value = 'cid.officer';
    s3.getElementById('loginPassword').value = 'ChangeMe123!';
    await probe(s3.sandbox, 'submitLogin')({ preventDefault() {} });
    await waitFor(() => probe(s3.sandbox, "serverOn === true && !!sessionUser && sessionUser.role === 'CIDUnit'"),
      'cid sign-in');
    const cidConductBtn = s3.sandbox._navButtons.find(b => b.dataset.page === 'conduct');
    if (!cidConductBtn || cidConductBtn.style.display !== 'none')
      throw new Error('conduct sidebar entry must stay hidden for a CID officer');
    if (s3.getElementById('officersConductLink').style.display !== 'none')
      throw new Error('officers-page conduct shortcut must stay hidden for a CID officer');
    probe(s3.sandbox, "go('conduct')");
    if (probe(s3.sandbox, "document.getElementById('conduct').classList.contains('active')"))
      throw new Error("go('conduct') must redirect a CID officer away from the desk");
    if (!probe(s3.sandbox, "document.getElementById('dashboard').classList.contains('active')"))
      throw new Error('CID officer should be redirected to the dashboard');
    // Sub-page inheritance: the case workspace belongs to the cid module.
    probe(s3.sandbox, "go('caseworkspace')");
    if (!probe(s3.sandbox, "document.getElementById('caseworkspace').classList.contains('active')"))
      throw new Error("go('caseworkspace') must open the case workspace for a CID officer");
    console.log('ok 11: CID officer — conduct desk hidden and redirected; case workspace still opens');

    console.log('ALL CONDUCT FRONTEND TESTS PASSED');
    return 0;
  } finally {
    proc.kill();
  }
}

const exitCode = await main();
process.exit(exitCode);
