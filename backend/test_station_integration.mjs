#!/usr/bin/env node
// End-to-end integration test for the Registered Stations row actions:
// the REAL page script (index.html inside jsdom) against the REAL API on a
// real PostgreSQL database, provisioned the same way as the other suites.
//
//   python3 -m venv .venv && .venv/bin/pip install psycopg2-binary pgserver
//   npm install --no-save --package-lock=false jsdom@26
//   node backend/test_station_integration.mjs
//
// Steps:
//   1. SystemAdmin: the register paints View + Edit, the View drawer shows the
//      server's authoritative record (including the deployment counters), and
//      the Edit modal saves a real PATCH that the API then returns.
//   2. HR Directorate (may READ the register): View only, no Edit control, the
//      Edit entry point refuses locally, and the same write through the page's
//      own `api()` helper surfaces the server's 403 Forbidden.
//   3. Commander (global read-only): the client firewall refuses the write, and
//      a raw request that bypasses it is refused with `code: read_only_role`.
//   4. The refused writes never changed the station row.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import os from 'node:os';
import { JSDOM } from 'jsdom';

const ROOT = path.dirname(new URL(import.meta.url).pathname);
// Interpreter used for the throwaway cluster and the API process. Point PYTHON
// at the virtualenv that has psycopg2 + pgserver when they are not installed
// for the system interpreter (PYTHON="$PWD/.venv/bin/python").
const PYTHON = process.env.PYTHON || 'python3';
const PROJECT_ROOT = path.dirname(ROOT);
const PASSWORD = 'ChangeMe123!';
const PG_SERVE = `
import pathlib, sys, time, pgserver
d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
srv = pgserver.get_server(str(d))
print(d, flush=True)
sys.stdin.read()
`;

function databaseEnvironment() {
  const env = { ...process.env };
  const envPath = path.join(PROJECT_ROOT, '.env');
  if (fs.existsSync(envPath)) {
    for (const raw of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith('#') || !line.includes('=')) continue;
      const i = line.indexOf('=');
      const key = line.slice(0, i).trim();
      if (key && env[key] === undefined) env[key] = line.slice(i + 1).trim();
    }
  }
  return env;
}

function provisionDatabase(tmp, env) {
  if ((env.SENTINEL_DATABASE_URL || '').trim()) return { env, stop: () => {}, label: 'configured (SENTINEL_DATABASE_URL)' };
  if (['SENTINEL_DB_HOST', 'SENTINEL_DB_PORT', 'SENTINEL_DB_USER', 'SENTINEL_DB_PASSWORD',
       'SENTINEL_DB_NAME'].some((k) => env[k])) {
    return { env, stop: () => {}, label: 'configured PostgreSQL' };
  }
  const probe = spawn(PYTHON, ['-c', 'import pgserver'], { stdio: 'ignore' });
  return new Promise((resolve) => {
    probe.on('exit', (code) => {
      if (code !== 0) { resolve(null); return; }
      const child = spawn(PYTHON, ['-c', PG_SERVE, path.join(tmp, 'pgdata')], { stdio: ['pipe', 'pipe', 'inherit'] });
      const buf = [];
      const deadline = Date.now() + 90000;
      const timer = setInterval(() => {
        if (Date.now() > deadline) { clearInterval(timer); child.kill('SIGKILL'); resolve(null); }
      }, 250);
      child.stdout.on('data', (chunk) => {
        buf.push(String(chunk));
        const m = buf.join('').match(/^(\/\S+)$/m);
        if (m) {
          clearInterval(timer);
          resolve({ env: { SENTINEL_DB_HOST: m[1], SENTINEL_DB_NAME: 'postgres', SENTINEL_DB_USER: 'postgres', SENTINEL_DB_PASSWORD: '' },
                    stop: () => child.kill('SIGKILL'), label: 'throwaway pgserver cluster' });
        }
      });
      child.on('exit', () => { if (!buf.length) { clearInterval(timer); resolve(null); } });
    });
  });
}

function freePort() {
  return new Promise((resolve) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); });
  });
}

async function waitFor(fn, what, timeoutMs = 15000) {
  const t0 = Date.now();
  let last;
  while (Date.now() - t0 < timeoutMs) {
    try { if (await fn()) return true; } catch (e) { last = e; }
    await new Promise((r) => setTimeout(r, 50));
  }
  throw new Error(`timed out waiting for: ${what}${last ? ' (' + last.message + ')' : ''}`);
}

async function apiCall(base, method, urlPath, token, body) {
  const res = await fetch(base + urlPath, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let payload = {};
  try { payload = await res.json(); } catch { /* keep {} */ }
  return { status: res.status, body: payload };
}

async function main() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sentinel-station-int-'));
  const dbEnv = databaseEnvironment();
  const pg = await provisionDatabase(tmp, dbEnv);
  if (!pg) {
    console.log('SKIP: no PostgreSQL test database available.');
    console.log('      Set SENTINEL_DATABASE_URL or SENTINEL_DB_HOST / SENTINEL_DB_NAME');
    console.log('      (and optionally SENTINEL_DB_USER / _PASSWORD / _PORT)');
    console.log('      or install the bundled engine with:  pip install pgserver');
    return 0;
  }
  const port = await freePort();
  const server = spawn(PYTHON, [path.join(ROOT, 'server.py')], {
    env: { ...process.env, ...pg.env, SENTINEL_UPLOADS: path.join(tmp, 'uploads'), PORT: String(port) },
    stdio: 'ignore',
  });
  const base = `http://127.0.0.1:${port}`;

  try {
    await waitFor(async () => (await fetch(base + '/api/health')).ok, 'backend health');

    // ---- load the real page script and point its fetch at the live API ----
    const html = fs.readFileSync(path.join(PROJECT_ROOT, 'index.html'), 'utf8');
    const dom = new JSDOM(html, { url: base + '/', runScripts: 'outside-only' });
    const w = dom.window, ctx = dom.getInternalVMContext();
    w.HTMLElement.prototype.scrollIntoView = function () {};
    const relative = (u) => (/^https?:/.test(String(u)) ? String(u) : new URL(String(u), base).href);
    w.fetch = (url, opts) => fetch(relative(url), opts);
    const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
      .replace(/if\(document\.readyState==='loading'\)[\s\S]*$/, '');
    vm.runInContext(script, ctx);
    const run = (code) => vm.runInContext(code, ctx);
    const $ = (id) => w.document.getElementById(id);
    const rowButtons = (name) => {
      const row = [...w.document.querySelectorAll('#stationsTable tr')]
        .find((tr) => (tr.textContent || '').includes(name));
      return row ? [...row.querySelectorAll('button')] : [];
    };
    const buttonNamed = (name, label) => rowButtons(name).find((b) => (b.textContent || '').trim() === label);

    const signIn = async (username) => {
      const res = await apiCall(base, 'POST', '/api/login', null, { username, password: PASSWORD });
      assert.equal(res.status, 200, `${username} signs in (${res.status})`);
      const me = await apiCall(base, 'GET', '/api/me', res.body.token);
      assert.equal(me.status, 200, `${username} /api/me -> 200`);
      run(`apiToken=${JSON.stringify(res.body.token)}; serverOn=true;
           sessionUser=${JSON.stringify(me.body)}; currentUser=sessionUser;
           sessionVisibility=sessionUser.visibility;
           applyReadOnlyMode();`);
      return { token: res.body.token, me: me.body };
    };

    // ================= 1. SystemAdmin: View + Edit =================
    const admin = await signIn('admin');
    await run('syncServer()');
    assert.ok(Array.isArray(run('db.stations')) && run('db.stations.length') >= 8,
      'the register synced the seeded stations from the API');
    run('renderStationsTable();');
    assert.ok(run("document.body.classList.contains('can-edit-records')"),
      'the administrator session carries the management-edit document class');
    const target = run("(db.stations.find(s=>s.name==='Las Anod Station')||{}).id");
    assert.ok(target, 'the seeded station is in the register');
    assert.ok(buttonNamed('Las Anod Station', 'View'), 'admin sees the View action');
    assert.ok(buttonNamed('Las Anod Station', 'Edit'), 'admin sees the Edit action');

    run(`openStationView(${JSON.stringify(target)});`);
    await waitFor(() => /Officers deployed/.test($('stViewBody').textContent), 'the station detail payload');
    const drawn = $('stViewBody').textContent;
    assert.ok(/SOO-C-01/.test(drawn) && /Las Anod Station/.test(drawn), 'the drawer shows code + name');
    assert.ok(/Sool/.test(drawn) && /Laascaanood/.test(drawn), 'the drawer shows Region → District → Village');
    assert.ok(/Active/.test(drawn), 'the drawer shows the operational status');
    assert.ok(/Officers deployed/.test(drawn) && /Vehicles assigned/.test(drawn),
      'the drawer shows the officer / vehicle deployment counters');
    assert.ok(/Registered directly in the station registry/.test(drawn),
      'the drawer states the mirror lineage (none for a seeded row)');
    run("closeEntryModal('stViewModal');");

    run(`openStationEdit(${JSON.stringify(target)});`);
    assert.ok($('stEditModal').classList.contains('open'), 'admin opens the Edit modal');
    assert.equal($('stEditName').value, 'Las Anod Station', 'the modal prefilled the server record');
    const newName = 'Las Anod Central Station (UAT)';
    $('stEditName').value = newName;
    $('stEditStatus').value = 'Maintenance';
    $('stEditPhone').value = '+252 63 555 0199';
    await run("saveStationEdit({preventDefault(){},target:document.getElementById('stEditForm')});");
    await waitFor(() => !$('stEditModal').classList.contains('open') || !$('stEditModal').classList.contains('closing'),
      'the Edit modal closes');
    const saved = await apiCall(base, 'GET', `/api/stations/${target}`, admin.token);
    assert.equal(saved.status, 200, 'the station is readable after the edit');
    assert.equal(saved.body.station.name, newName, 'the API stored the edited name');
    assert.equal(saved.body.station.operational_status, 'Maintenance', 'the API stored the edited status');
    assert.equal(saved.body.station.contact_phone, '+252 63 555 0199', 'the API stored the edited phone');
    assert.equal(saved.body.station.code, 'SOO-C-01', 'the station code stayed immutable');
    assert.ok(saved.body.station.updated_at, 'the edit stamped updated_at');
    run('renderStationsTable();');
    assert.ok(buttonNamed(newName, 'Edit'), 'the table repainted from the saved server row');
    console.log('ok 1: SystemAdmin Views the server record and Edits it through the live API');

    // ================= 2. HR Directorate: View only =================
    const hr = await signIn('hr.officer');
    await run('syncServer()');
    run('renderStationsTable();');
    assert.ok(buttonNamed(newName, 'View'), 'HR Directorate can View a station');
    assert.equal(buttonNamed(newName, 'Edit'), undefined, 'HR Directorate gets no Edit control');
    assert.equal(run("document.body.classList.contains('can-edit-records')"), false,
      'HR Directorate clears the management-edit document class');
    run('document.getElementById("toast").textContent=""; openStationEdit(' + JSON.stringify(target) + ');');
    assert.equal($('stEditModal').classList.contains('open'), false,
      'the Edit modal refuses to open for the HR Directorate');
    assert.match($('toast').textContent, /Administrator/i,
      'the local refusal names the System Administrator requirement');
    const hrPatch = await run(
      `api(${JSON.stringify('/api/stations/' + target)},{method:'PATCH',body:JSON.stringify({name:'HR Rename Attempt'})})
         .then(()=>({status:200})).catch(e=>({status:e.status,message:e.message}))`);
    assert.equal(hrPatch.status, 403, 'the page api() call surfaces the server 403');
    const hrRaw = await apiCall(base, 'PATCH', `/api/stations/${target}`, hr.token, { name: 'HR Rename Attempt' });
    assert.equal(hrRaw.status, 403, 'the raw API call is refused with 403');
    assert.equal(hrRaw.body.code, 'admin_only', 'the refusal carries code: admin_only');
    console.log('ok 2: HR Directorate sees View only; every Edit attempt is refused with 403 (admin_only)');

    // ================= 3. Commander: global read-only =================
    const chief = await signIn('chief');
    const chiefPut = await run(
      `api(${JSON.stringify('/api/stations/' + target)},{method:'PUT',body:JSON.stringify({name:'Chief Rename Attempt'})})
         .then(()=>({status:200})).catch(e=>({status:e.status,readOnly:!!e.readOnly}))`);
    assert.equal(chiefPut.status, 403, 'the client firewall refuses the Commander write');
    assert.equal(chiefPut.readOnly, true, 'the refusal is the read-only role contract');
    const chiefRaw = await apiCall(base, 'PUT', `/api/stations/${target}`, chief.token, { name: 'Chief Rename Attempt' });
    assert.equal(chiefRaw.status, 403, 'a raw Commander PUT is refused with 403');
    assert.equal(chiefRaw.body.code, 'read_only_role', 'the Commander refusal is read_only_role');
    console.log('ok 3: the Commander is refused on both the client and the API (read_only_role)');

    // ================= 4. Nothing leaked through =================
    const finalState = await apiCall(base, 'GET', `/api/stations/${target}`, admin.token);
    assert.equal(finalState.body.station.name, newName, 'the refused writes left the row untouched');
    assert.equal(finalState.body.station.operational_status, 'Maintenance', 'the refused writes left the status untouched');
    const listing = await apiCall(base, 'GET', '/api/stations', admin.token);
    assert.ok(!listing.body.items.some((s) => /Rename Attempt/.test(s.name || '')),
      'no refused write appears in the register');
    console.log('ok 4: refused non-admin writes never altered the station record');
  } finally {
    server.kill('SIGKILL');
    pg.stop();
  }

  console.log('ALL STATION VIEW / EDIT INTEGRATION TESTS PASSED');
  return 0;
}

main().then((code) => process.exit(code)).catch((err) => { console.error(err); process.exit(1); });
