#!/usr/bin/env node
/**
 * Approve / Print button end-to-end regression test (backend + Node VM,
 * no browser).
 *
 * Boots backend/server.py against a temporary SQLite database, then drives
 * the REAL scripts of index.html, application.html and certificate.html
 * inside Node VM sandboxes with a minimal DOM stub. It reproduces the exact
 * bug report — "the approve/print button does not work for either users or
 * administrators" — and pins the three mandated rules:
 *
 *   1. 12-HOUR RULE: a standard officer's Approve control is rendered
 *      disabled ("Review Locked (12h)") on a fresh application, the click
 *      handler approveFP() refuses to even call the API, and the server
 *      answers 400 with the spec message. Backdating the submission past
 *      +12h re-renders an ENABLED Approve button and the very same click
 *      handler now approves successfully (201 -> certificate unlocked).
 *   2. ADMIN BYPASS: the admin register row renders an enabled
 *      "Approve Application (Admin bypass)" button IMMEDIATELY after
 *      submission, and clicking it approves instantly (201,
 *      review_period_bypassed=true). The printable page shows the same
 *      bypass for an admin session.
 *   3. WORKING CLICK HANDLERS: syncServer() merges the server register into
 *      db.fingerprint (the old stray `cd` ReferenceError aborted it before
 *      any row was painted), checkBackendBuild()/renderStaleBackendBanner()
 *      no longer throw (`seen is not defined`), the stale-backend banner is
 *      created/removed correctly, and certificate.html releases the Print
 *      button only after an approval.
 *
 * Usage:  node backend/test_approval_flow.mjs
 */
import { spawn, execFileSync } from 'node:child_process';
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

async function waitFor(fn, what, timeoutMs = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (await fn()) return;
    await new Promise((r) => setTimeout(r, 40));
  }
  throw new Error('timed out waiting for: ' + what);
}

// --------------------------------------------------------------------------
// Minimal DOM stub (same surface as test_frontend_session.mjs, plus
// attribute tracking + a remove() flag so the banner lifecycle is testable).
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
    _attrs: {},
    _removed: false,
    _listeners: {},
    addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); },
    removeEventListener() {},
    dispatchEvent() { return true; },
    querySelectorAll() { return []; },
    querySelector() { return null; },
    closest() { return null; },
    appendChild(child) { (this._children ||= []).push(child); return child; },
    insertBefore(child) { (this._children ||= []).unshift(child); return child; },
    remove() { this._removed = true; },
    focus() {},
    reset() {},
    setAttribute(k, v) { this._attrs[String(k)] = String(v); },
    getAttribute(k) { return (k in this._attrs) ? this._attrs[k] : null; },
    removeAttribute(k) { delete this._attrs[String(k)]; },
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

function extractInlineScript(file) {
  const html = readFileSync(path.join(PROJECT_ROOT, file), 'utf8');
  const m = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!m) throw new Error('inline script not found in ' + file);
  return m[1];
}

function extractElementIds(file) {
  const html = readFileSync(path.join(PROJECT_ROOT, file), 'utf8');
  return [...html.matchAll(/id="([A-Za-z0-9_-]+)"/g)].map((m) => m[1]);
}

function makeFetchProxy(port, consoleSink) {
  return async (p, opts = {}) => {
    const url = String(p).startsWith('http') ? p : `http://127.0.0.1:${port}${p}`;
    let res;
    try {
      res = await fetch(url, {
        method: opts.method || 'GET',
        headers: opts.headers || {},
        body: opts.body,
      });
    } catch (netErr) {
      consoleSink.push(['warn', 'harness fetch failed: ' + (netErr && netErr.message) + ' url=' + url]);
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
}

// Sandbox for the main app (index.html). Pre-creates every id'd element so
// bare-global references (fpTable, fpNotice, ...) resolve like in a browser.
function buildAppSandbox({ port, storageDump, consoleSink }) {
  const els = new Map();
  const getElementById = (id) => {
    if (!els.has(id)) els.set(id, makeElement(id));
    return els.get(id);
  };
  for (const id of extractElementIds('index.html')) getElementById(id);

  const localStorage = makeLocalStorage();
  Object.entries(storageDump || {}).forEach(([k, v]) => localStorage.setItem(k, v));

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
    navigator: { userAgent: 'approval-flow-test' },
    devicePixelRatio: 1,
    alert: () => {},
    confirm: () => true,
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
  for (const [id, el] of els) {
    if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(id)) sandbox[id] = el;
  }
  sandbox.fetch = makeFetchProxy(port, consoleSink);
  vm.createContext(sandbox);
  return { sandbox, els, getElementById, localStorage };
}

// Sandbox for the printable pages (application.html / certificate.html).
// These drive everything through document.getElementById, so on-demand
// creation is enough; they also need `location.search` and document.cookie.
function buildPageSandbox({ file, port, storageDump, search, consoleSink }) {
  const els = new Map();
  const getElementById = (id) => {
    if (!els.has(id)) els.set(id, makeElement(id));
    return els.get(id);
  };
  const pageEl = makeElement('.page');
  const localStorage = makeLocalStorage();
  Object.entries(storageDump || {}).forEach(([k, v]) => localStorage.setItem(k, v));
  const sandbox = {
    console: {
      log: (...a) => consoleSink.push(['log', a.map(String).join(' ')]),
      warn: (...a) => consoleSink.push(['warn', a.map(String).join(' ')]),
      error: (...a) => consoleSink.push(['error', a.map(String).join(' ')]),
      info: (...a) => consoleSink.push(['info', a.map(String).join(' ')]),
    },
    setTimeout, clearTimeout, setInterval, clearInterval,
    localStorage, URLSearchParams,
    location: { search: search || '', href: 'http://127.0.0.1/' + file },
    navigator: { userAgent: 'approval-flow-test' },
    document: {
      readyState: 'complete',
      title: '',
      cookie: '',
      getElementById,
      createElement: (tag) => makeElement('<' + tag + '>'),
      querySelector: (sel) => (sel === '.page' ? pageEl : null),
      querySelectorAll: () => [],
      addEventListener() {},
      body: makeElement('body'),
    },
  };
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.fetch = makeFetchProxy(port, consoleSink);
  vm.createContext(sandbox);
  return { sandbox, els, getElementById, localStorage, pageEl };
}

const probe = (sandbox, expr) => vm.runInContext(expr, sandbox);

// Wrap sandbox.fetch to record every URL/method while still hitting the
// real backend — used to prove (or disprove) that a click handler actually
// executed the approval request.
function trackFetches(sb) {
  const calls = [];
  const orig = sb.sandbox.fetch;
  sb.sandbox.fetch = (p, o) => {
    calls.push({ url: String(p), method: (o && o.method) || 'GET' });
    return orig(p, o);
  };
  return { calls, restore: () => { sb.sandbox.fetch = orig; } };
}

async function main() {
  const port = await freePort();
  const tmp = `/tmp/sentinel-approval-test-${Date.now()}`;
  mkdirSync(tmp, { recursive: true });
  const dbFile = `${tmp}/db.sqlite`;
  const proc = spawn('python3', [path.join(ROOT, 'server.py')], {
    env: {
      ...process.env,
      SENTINEL_DB: dbFile,
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

    // ---- helpers -----------------------------------------------------------
    const loginAs = async (user) => (await (await fetch(base + '/api/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: 'ChangeMe123!' }),
    })).json());

    const storageFor = (auth) => ({
      sentinel_token: auth.token,
      sentinel_user: JSON.stringify(auth.user),
      sentinelSession: JSON.stringify({ token: auth.token, user: auth.user }),
    });

    let seq = 0;
    const createClearance = async (user) => {
      const auth = typeof user === 'string' ? await loginAs(user) : user;
      seq += 1;
      const fd = new FormData();
      const fields = {
        first_name: 'Flow', second_name: 'Test', third_name: 'Case', fourth_name: String(seq),
        date_of_birth: '1992-02-02', national_id: `888${String(seq).padStart(5, '0')}`,
        mother_name: 'Hooyo Flow', residence: 'Hargeisa, Flow Ward',
        phone: '+252 63 555 0100', sex: 'Male', email: 'flow@example.com',
        purpose: 'Employment',
        guardian_name: 'Guardian Flow', guardian_relationship: 'Uncle', guardian_id: 'GD-2',
        guardian_occupation: 'Trader', guardian_address: 'Burao', guardian_phone: '+252 63 555 0101',
      };
      Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
      const pdf = new Blob(['%PDF-flow-test'], { type: 'application/pdf' });
      ['doc_app_0', 'doc_app_1', 'doc_guard_0', 'doc_guard_1'].forEach((n) => fd.append(n, pdf, n + '.pdf'));
      const r = await fetch(base + '/api/clearance-applications', {
        method: 'POST', headers: { Authorization: 'Bearer ' + auth.token }, body: fd,
      });
      if (!r.ok) throw new Error(`clearance create failed ${r.status}: ${await r.text()}`);
      return await r.json();
    };

    const backdate = (aid, hours) => {
      const py = [
        'import sqlite3, datetime',
        `conn = sqlite3.connect(${JSON.stringify(dbFile)}, timeout=10)`,
        `stamp = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=${hours}))`,
        `conn.execute("UPDATE clearance_applications SET created_at=? WHERE application_id=?",`,
        `             (stamp.strftime("%Y-%m-%d %H:%M:%S"), ${JSON.stringify(aid)}))`,
        'conn.commit()',
      ].join('\n');
      execFileSync('python3', ['-c', py]);
    };

    const fpRow = (sb, aid) => {
      const html = sb.getElementById('fpTable').innerHTML;
      return (html.match(/<tr>[\s\S]*?<\/tr>/g) || []).find((r) => r.includes(aid)) || '';
    };

    // ======================================================================
    // A) index.html — officer journey: locked -> +12h -> approve executes
    // ======================================================================
    const oSink = [];
    const sbO = buildAppSandbox({ port, storageDump: {}, consoleSink: oSink });
    vm.runInContext(extractInlineScript('index.html'), sbO.sandbox, { filename: 'index-inline.js' });
    sbO.getElementById('loginUser').value = 'fp.officer';
    sbO.getElementById('loginPassword').value = 'ChangeMe123!';
    await probe(sbO.sandbox, 'submitLogin')({ preventDefault() {} });
    await waitFor(() => probe(sbO.sandbox, 'serverOn === true && !!sessionUser'), 'officer signed in');
    // Regression for the corrupted renderStaleBackendBanner(): the health
    // check chain must RESOLVE (it used to reject with "seen is not defined").
    const buildOk = await probe(sbO.sandbox, 'checkBackendBuild()');
    if (buildOk !== true) throw new Error('checkBackendBuild() must resolve true against the locked build');
    if (oSink.some(([lvl, m]) => lvl === 'error' && /is not defined/.test(m)))
      throw new Error('boot logged a ReferenceError: ' + JSON.stringify(oSink));

    const app1 = await createClearance('fp.officer');
    await probe(sbO.sandbox, 'syncServer()');
    await waitFor(() => probe(sbO.sandbox,
      `(db.fingerprint||[]).some(x => x.id === '${app1.application_id}')`),
      'officer register synced with the new application');
    // Regression for the stray `cd is not defined` line: syncServer must NOT
    // log the transient-error fallback any more.
    if (oSink.some(([, m]) => /transient error/.test(m) && /is not defined/.test(m)))
      throw new Error('syncServer still aborts with a ReferenceError: ' + JSON.stringify(oSink));

    // Rule 1 — fresh application: the officer's control is physically locked.
    let row = fpRow(sbO, app1.application_id);
    if (!row) throw new Error('application row missing from the officer register');
    if (!/disabled="disabled"/.test(row)) throw new Error('officer button must be disabled: ' + row);
    if (!/pointer-events:none/.test(row) || !/opacity:0\.5/.test(row))
      throw new Error('officer button must be unclickable (pointer-events/opacity): ' + row);
    if (!/Review Locked \(12h\)/.test(row)) throw new Error('officer button label wrong: ' + row);
    if (!/Review Lock \(12h Required\) - 1[0-2](\.\d)? hours remaining/.test(row))
      throw new Error('remaining-hours badge missing: ' + row);
    if (!/application\.html\?id=/.test(row)) throw new Error('Review/Print link missing: ' + row);

    // Rule 1 — the click handler refuses without touching the network.
    let trk = trackFetches(sbO);
    await probe(sbO.sandbox, `approveFP('${app1.application_id}')`);
    trk.restore();
    if (trk.calls.some((c) => c.url.includes('/approve')))
      throw new Error('locked approveFP() must not call the API, saw: ' + JSON.stringify(trk.calls));
    if (!/Review Lock \(12h Required\)/.test(sbO.getElementById('fpNotice').textContent))
      throw new Error('officer must see the review-lock notice, got: ' +
        sbO.getElementById('fpNotice').textContent);

    // Rule 1 — defence in depth: the server rejects the same click with 400.
    const oAuth = await loginAs('fp.officer');
    const rejected = await fetch(base + '/api/fingerprint/applications/' + app1.application_id + '/approve', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + oAuth.token },
      body: '{}',
    });
    if (rejected.status !== 400) throw new Error('server must answer 400, got ' + rejected.status);
    const rejectedBody = await rejected.json();
    if (rejectedBody.detail !== 'Review period active. Standard officers must wait 12 hours before approving.')
      throw new Error('unexpected 400 payload: ' + JSON.stringify(rejectedBody));
    console.log('ok A1: officer — fresh application locked (12h), handler refuses, server 400');

    // Rule 1 — after +12h the SAME handler executes successfully.
    backdate(app1.application_id, 13);
    await probe(sbO.sandbox, 'syncServer()');
    await waitFor(() => {
      const r2 = fpRow(sbO, app1.application_id);
      return r2 && !/disabled="disabled"/.test(r2) && /approveFP\(/.test(r2);
    }, 'officer Approve button enabled after 12h');
    trk = trackFetches(sbO);
    await probe(sbO.sandbox, `approveFP('${app1.application_id}')`);
    trk.restore();
    const approveCall = trk.calls.find((c) => c.url.includes(`/applications/${app1.application_id}/approve`));
    if (!approveCall || approveCall.method !== 'POST')
      throw new Error('approveFP() must POST the approval, saw: ' + JSON.stringify(trk.calls));
    await waitFor(() => probe(sbO.sandbox,
      `(db.fingerprint||[]).find(x => x.id === '${app1.application_id}')?.status === 'Approved'`),
      'officer approval flipped the row to Approved');
    row = fpRow(sbO, app1.application_id);
    if (!/certificate\.html\?id=/.test(row)) throw new Error('approved row must offer the certificate: ' + row);
    console.log('ok A2: officer — after 12h the Approve click executes (201) and unlocks the certificate');

    // ======================================================================
    // B) index.html — admin journey: instant bypass on a fresh application
    // ======================================================================
    const app2 = await createClearance('fp.officer');   // fresh: submitted seconds ago
    const aSink = [];
    const sbA = buildAppSandbox({ port, storageDump: {}, consoleSink: aSink });
    vm.runInContext(extractInlineScript('index.html'), sbA.sandbox, { filename: 'index-inline.js' });
    sbA.getElementById('loginUser').value = 'admin';
    sbA.getElementById('loginPassword').value = 'ChangeMe123!';
    await probe(sbA.sandbox, 'submitLogin')({ preventDefault() {} });
    await waitFor(() => probe(sbA.sandbox, 'serverOn === true && !!sessionUser'), 'admin signed in');
    await waitFor(() => probe(sbA.sandbox, 'backendBuildOk()'), 'admin health check confirmed the locked build');
    await probe(sbA.sandbox, 'syncServer()');
    await waitFor(() => probe(sbA.sandbox,
      `(db.fingerprint||[]).some(x => x.id === '${app2.application_id}')`),
      'admin register synced');
    row = fpRow(sbA, app2.application_id);
    if (!row) throw new Error('application row missing from the admin register');
    if (/disabled="disabled"/.test(row))
      throw new Error('admin Approve button must NOT be disabled inside the window: ' + row);
    if (!/Approve Application \(Admin bypass\)/.test(row))
      throw new Error('admin button must advertise the bypass: ' + row);
    trk = trackFetches(sbA);
    await probe(sbA.sandbox, `approveFP('${app2.application_id}')`);
    trk.restore();
    if (!trk.calls.some((c) => c.method === 'POST' && c.url.includes(`/applications/${app2.application_id}/approve`)))
      throw new Error('admin approveFP() must POST the approval: ' + JSON.stringify(trk.calls));
    await waitFor(() => probe(sbA.sandbox,
      `(db.fingerprint||[]).find(x => x.id === '${app2.application_id}')?.status === 'Approved'`),
      'admin bypass approval flipped the row to Approved');
    const detail2 = await (await fetch(base + '/api/clearance-applications/' + app2.application_id, {
      headers: { Authorization: 'Bearer ' + (await loginAs('admin')).token },
    })).json();
    if (!detail2.certificate_number) throw new Error('admin approval must issue a certificate');
    row = fpRow(sbA, app2.application_id);
    if (!/certificate\.html\?id=/.test(row)) throw new Error('admin row must offer the certificate: ' + row);
    console.log('ok B: admin — instant bypass click executes (201, certificate issued, no 12h wait)');

    // ======================================================================
    // C) stale-backend banner lifecycle (the rebuilt renderStaleBackendBanner)
    // ======================================================================
    const created = [];
    const origCreate = sbA.sandbox.document.createElement;
    sbA.sandbox.document.createElement = (tag) => { const el = origCreate(tag); created.push(el); return el; };
    const origGet = sbA.sandbox.document.getElementById;
    // Force the createElement branch: no #staleBackendBanner exists yet.
    sbA.sandbox.document.getElementById = (id) => (id === 'staleBackendBanner' ? null : origGet(id));
    probe(sbA.sandbox, "backendBuild={build:'sentinel-legacy',review_lock_active:true}; backendBuildChecked=true;");
    probe(sbA.sandbox, 'renderStaleBackendBanner()');          // must not throw
    if (created.length !== 1 || created[0].id !== 'staleBackendBanner')
      throw new Error('stale banner element was not created: ' + JSON.stringify(created.map((c) => c.id)));
    if (!/not the review-lock build/.test(created[0].innerHTML)
        || !/sentinel-fingerprint-review-lock-12h/.test(created[0].innerHTML)
        || !/sentinel-legacy/.test(created[0].innerHTML))
      throw new Error('stale banner message wrong: ' + created[0].innerHTML);
    // Register must be locked while stale — even for the admin.
    probe(sbA.sandbox, 'renderAll()');
    row = fpRow(sbA, app2.application_id);
    const freshRow = (sbA.getElementById('fpTable').innerHTML.match(/<tr>[\s\S]*?<\/tr>/g) || [])
      .find((r) => /Stale backend/.test(r));
    if (!freshRow) throw new Error('stale backend must lock the register rows');
    // Recovery: the banner is removed once the right build answers again.
    sbA.sandbox.document.getElementById = (id) => (id === 'staleBackendBanner' ? created[0] : origGet(id));
    probe(sbA.sandbox, "backendBuild={build:'sentinel-fingerprint-review-lock-12h',review_lock_active:true}; backendBuildChecked=true;");
    probe(sbA.sandbox, 'renderStaleBackendBanner()');
    if (!created[0]._removed) throw new Error('banner must be removed once the locked build answers');
    probe(sbA.sandbox, 'renderAll()');
    if (/Stale backend/.test(sbA.getElementById('fpTable').innerHTML))
      throw new Error('register must unlock after the correct build answers');
    sbA.sandbox.document.createElement = origCreate;
    sbA.sandbox.document.getElementById = origGet;
    console.log('ok C: stale-backend banner renders/removes without throwing; register locks and recovers');

    // ======================================================================
    // D) application.html — the printable page's Approve button
    // ======================================================================
    const app3 = await createClearance('fp.officer');          // fresh
    const officerStorage = storageFor(oAuth);

    // D1 — officer on a fresh application: disabled, click refuses silently.
    const pSink1 = [];
    const pgO = buildPageSandbox({ file: 'application.html', port, storageDump: officerStorage,
      search: '?id=' + app3.application_id, consoleSink: pSink1 });
    vm.runInContext(extractInlineScript('application.html'), pgO.sandbox, { filename: 'application.js' });
    await waitFor(() => probe(pgO.sandbox, '!!app'), 'application.html loaded for the officer');
    const oBtn = pgO.getElementById('approveBtn');
    await waitFor(() => /Review Locked \(12h\)/.test(oBtn.innerHTML), 'officer page button locked');
    if (oBtn.disabled !== true || oBtn._attrs.disabled !== 'disabled'
        || !/pointer-events:none/.test(oBtn._attrs.style || ''))
      throw new Error('officer page Approve button must be physically disabled: ' + JSON.stringify(oBtn._attrs));
    if (!/System Administrator can bypass/.test(pgO.getElementById('lockbar').innerHTML))
      throw new Error('officer lockbar must explain the admin bypass');
    let ptrk = trackFetches(pgO);
    await probe(pgO.sandbox, 'approve()');
    ptrk.restore();
    if (ptrk.calls.some((c) => c.url.includes('/approve')))
      throw new Error('page approve() must not call the API while locked: ' + JSON.stringify(ptrk.calls));
    if (!/approval blocked/.test(pgO.getElementById('lockbar').innerHTML))
      throw new Error('page approve() must report the block');
    console.log('ok D1: application.html — officer locked (disabled button, no API call, bypass hint)');

    // D2 — officer after +12h: the same page approves successfully.
    backdate(app3.application_id, 13);
    const pgO2 = buildPageSandbox({ file: 'application.html', port, storageDump: officerStorage,
      search: '?id=' + app3.application_id, consoleSink: pSink1 });
    vm.runInContext(extractInlineScript('application.html'), pgO2.sandbox, { filename: 'application.js' });
    await waitFor(() => probe(pgO2.sandbox, '!!app'), 'application.html reload for the officer');
    const oBtn2 = pgO2.getElementById('approveBtn');
    await waitFor(() => /Approve Application/.test(oBtn2.innerHTML) && oBtn2.disabled === false,
      'officer page button enabled after 12h');
    if (/Admin bypass/.test(oBtn2.innerHTML)) throw new Error('officer must not see the admin bypass label');
    ptrk = trackFetches(pgO2);
    await probe(pgO2.sandbox, 'approve()');
    ptrk.restore();
    if (!ptrk.calls.some((c) => c.method === 'POST' && c.url.includes('/approve')))
      throw new Error('page approve() must POST after the window elapsed: ' + JSON.stringify(ptrk.calls));
    await waitFor(() => /Approved\. Certificate/.test(pgO2.getElementById('toast').textContent),
      'officer page approval toast');
    await waitFor(() => pgO2.getElementById('statusBadge').textContent === 'Approved',
      'officer page badge flips to Approved');
    console.log('ok D2: application.html — officer approves after 12h (toast + badge + certificate)');

    // D3 — admin on a FRESH application: enabled "(Admin bypass)" -> approves.
    const app4 = await createClearance('fp.officer');
    const adminAuth = await loginAs('admin');
    const adminStorage = storageFor(adminAuth);
    const pSink2 = [];
    const pgA = buildPageSandbox({ file: 'application.html', port, storageDump: adminStorage,
      search: '?id=' + app4.application_id, consoleSink: pSink2 });
    vm.runInContext(extractInlineScript('application.html'), pgA.sandbox, { filename: 'application.js' });
    await waitFor(() => probe(pgA.sandbox, '!!app'), 'application.html loaded for the admin');
    if (probe(pgA.sandbox, 'isAdmin') !== true) throw new Error('admin session must resolve isAdmin=true');
    const aBtn = pgA.getElementById('approveBtn');
    await waitFor(() => /Approve Application \(Admin bypass\)/.test(aBtn.innerHTML) && aBtn.disabled === false,
      'admin page button enabled instantly');
    ptrk = trackFetches(pgA);
    await probe(pgA.sandbox, 'approve()');
    ptrk.restore();
    if (!ptrk.calls.some((c) => c.method === 'POST' && c.url.includes('/approve')))
      throw new Error('admin page approve() must POST: ' + JSON.stringify(ptrk.calls));
    await waitFor(() => /Approved\. Certificate/.test(pgA.getElementById('toast').textContent),
      'admin page approval toast');
    await waitFor(() => aBtn.style.display === 'none', 'approved page hides the Approve button');
    if (!/unlocked for printing/.test(pgA.getElementById('lockbar').innerHTML))
      throw new Error('approved page must announce the printable certificate');
    console.log('ok D3: application.html — admin bypass approves a fresh application instantly');

    // ======================================================================
    // E) certificate.html — Print unlocks only after approval
    // ======================================================================
    const app5 = await createClearance('fp.officer');          // fresh, pending
    const pSink3 = [];
    const pgC = buildPageSandbox({ file: 'certificate.html', port, storageDump: officerStorage,
      search: '?id=' + app5.application_id, consoleSink: pSink3 });
    vm.runInContext(extractInlineScript('certificate.html'), pgC.sandbox, { filename: 'certificate.js' });
    await waitFor(() => /Certificate locked/.test(pgC.getElementById('sheet').innerHTML),
      'certificate locked screen');
    if (pgC.getElementById('printBtn').style.display !== 'none')
      throw new Error('Print button must stay hidden before approval');
    if (!/Review Lock \(12h Required\)/.test(pgC.getElementById('sheet').innerHTML))
      throw new Error('locked certificate must show the 12h review-lock note');

    const pgC2 = buildPageSandbox({ file: 'certificate.html', port, storageDump: officerStorage,
      search: '?id=' + app2.application_id, consoleSink: pSink3 });   // admin-approved above
    vm.runInContext(extractInlineScript('certificate.html'), pgC2.sandbox, { filename: 'certificate.js' });
    await waitFor(() => pgC2.getElementById('printBtn').style.display === '',
      'certificate Print button unlocked after approval');
    if (pgC2.getElementById('statusBadge').textContent !== 'Approved')
      throw new Error('certificate badge must read Approved');
    if (!/^CL-/.test(pgC2.getElementById('certNumber').innerHTML))
      throw new Error('certificate number must render, got: ' + pgC2.getElementById('certNumber').innerHTML);
    console.log('ok E: certificate.html — Print locked while pending, unlocked with CL-number after approval');

    console.log('ALL APPROVAL-FRONTEND TESTS PASSED');
    return 0;
  } finally {
    proc.kill('SIGTERM');
  }
}

main().then((code) => process.exit(code)).catch((e) => {
  console.error('APPROVAL FLOW TEST FAILED:', e.stack || e.message || e);
  process.exit(1);
});
