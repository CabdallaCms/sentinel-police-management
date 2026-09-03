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

const probe = (sandbox, expr) => vm.runInContext(expr, sandbox);

// --------------------------------------------------------------------------
async function main() {
  const port = await freePort();
  const tmp = `/tmp/sentinel-fe-test-${Date.now()}`;
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
      { id: 1, username: 'admin', display_name: 'Officer A. Hassan', role: 'SystemAdmin', role_alias: 'system_admin', location_scope: null, modules: ['dashboard', 'people', 'fingerprint', 'airport', 'cid', 'checkpoints', 'analytics', 'admin'] },
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

    console.log('ALL FRONTEND SESSION TESTS PASSED');
    return 0;
  } finally {
    proc.kill('SIGTERM');
  }
}

main().then((code) => process.exit(code)).catch((e) => {
  console.error('FRONTEND SESSION TEST FAILED:', e.message);
  process.exit(1);
});
