/* Server-mode DOM smoke test: real backend/server.py + jsdom browser talking to it over HTTP.
   Verifies the modal/table refactor renders and behaves identically against the central database. */
const { JSDOM, VirtualConsole } = require('jsdom');
const { spawn } = require('child_process');
const net = require('net');
const fs = require('fs');
const os = require('os');
const path = require('path');

const REPO = path.join(__dirname, '..', '..');
const SERVER = path.join(REPO, 'backend', 'server.py');
let failures = 0, checks = 0;
const ok = (n, c, extra) => { checks++; if (c) console.log('  PASS  ' + n); else { failures++; console.log('  FAIL  ' + n + (extra ? '  -> ' + extra : '')); } };
const section = t => console.log('\n== ' + t + ' ==');
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sentinel-ui-server-'));
  const port = await freePort();
  const BASE = `http://127.0.0.1:${port}`;
  const proc = spawn('python3', [SERVER], {
    env: { ...process.env, SENTINEL_DB: path.join(tmp, 'ui.db'), PORT: String(port), SENTINEL_UPLOADS: path.join(tmp, 'uploads') },
    stdio: ['ignore', 'pipe', 'pipe']
  });
  let serverLog = '';
  proc.stdout.on('data', d => serverLog += d);
  proc.stderr.on('data', d => serverLog += d);
  for (let i = 0; i < 60; i++) {
    try { const r = await fetch(BASE + '/api/health'); if (r.ok) break; } catch (e) { /* not up yet */ }
    await new Promise(r => setTimeout(r, 250));
  }
  const health = await fetch(BASE + '/api/health').then(r => r.json()).catch(() => null);
  section('0 · backend up');
  ok('backend/server.py answering /api/health', !!health, JSON.stringify(health));

  const vc = new VirtualConsole();
  const unexpected = [];
  vc.on('jsdomError', e => unexpected.push('jsdomError: ' + e.message));
  vc.on('error', (...a) => unexpected.push('console.error: ' + a.join(' ')));

  const dom = await JSDOM.fromFile(path.join(REPO, 'index.html'), {
    runScripts: 'dangerously', pretendToBeVisual: true, url: BASE + '/', virtualConsole: vc,
    beforeParse(w) {
      // Bridge the browser's fetch to the real backend (jsdom FormData -> Node FormData).
      w.fetch = async (url, opts = {}) => {
        const o = { ...opts };
        if (o.body && typeof o.body.entries === 'function' && typeof o.body.append === 'function') {
          const nfd = new globalThis.FormData();
          for (const [k, v] of o.body.entries()) {
            if (typeof v === 'string') nfd.append(k, v);
            else nfd.append(k, new globalThis.File([Buffer.from(await v.arrayBuffer())], v.name, { type: v.type || 'application/octet-stream' }), v.name);
          }
          o.body = nfd;
        }
        return globalThis.fetch(new URL(url, BASE).href, o);
      };
    }
  });
  const { window } = dom;
  const { document } = window;
  await new Promise(r => window.addEventListener('load', r));
  for (let i = 0; i < 40 && window.eval('serverOn') !== true; i++) await new Promise(r => setTimeout(r, 100));
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const ev = c => window.eval(c);
  const wait = (n = 40) => new Promise(r => setTimeout(r, n));
  const apiGet = async (p, token) => (await fetch(BASE + p, { headers: token ? { Authorization: 'Bearer ' + token } : {} })).json();
  const login = await fetch(BASE + '/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'admin', password: 'ChangeMe123!' }) }).then(r => r.json());
  const token = login.token;

  section('1 · connected to the central backend');
  ok('serverOn === true', ev('serverOn') === true, 'serverLog: ' + serverLog.slice(-300));
  ok('env badge reads central database', /central database/.test(document.getElementById('envBadge').textContent), document.getElementById('envBadge').textContent);
  ok('central persons loaded from server', ev('db').people.length >= 3, String(ev('db').people.length));
  ok('no unexpected runtime errors', unexpected.length === 0, unexpected.join(' | '));

  section('2 · every register table renders from server data with an Actions column');
  const TABLES = [['peopleTable', 'Central Person Registry'], ['caseTable', 'Crime cases'], ['suspectTable', 'Suspect list'], ['cpTable', 'Checkpoint register'], ['airTable', 'Airport logs'], ['fpTable', 'Fingerprint register']];
  for (const [id, label] of TABLES) {
    const tb = document.getElementById(id), table = tb.closest('table'), wrap = table.closest('.table-wrap');
    const ths = [...table.querySelectorAll('thead th')];
    ok(`${label}: .table-wrap card + sticky thead (${ths.length} cols)`, !!wrap && ths.length > 0);
    ok(`${label}: rightmost column is Actions`, ths[ths.length - 1].textContent.trim() === 'Actions' && ths[ths.length - 1].classList.contains('col-actions'));
  }

  section('3 · create a crime case through the centered modal (server round trip)');
  window.go('cid');
  window.openCaseModal();
  await wait();
  ok('case modal centered + open', $('#overlay').classList.contains('on') && !$('#modal').classList.contains('wide'));
  document.getElementById('cdCategory').value = 'Aggravated burglary';
  document.getElementById('cdLocation').value = 'Hargeisa Central';
  document.getElementById('cdStatus').value = 'Under Investigation';
  document.getElementById('cdSummary').value = 'Night break-in at a hardware store; safe forced open.';
  await window.submitCaseModal();
  await wait(200);
  const serverCases = (await apiGet('/api/crime-cases', token)).items;
  const newCase = serverCases.find(c => c.category === 'Aggravated burglary');
  ok('modal closed after submit', !$('#overlay').classList.contains('on'));
  ok('case persisted on the server', !!newCase, JSON.stringify(serverCases.map(c => c.case_id)));
  ok('case workspace opened for the new case', ev('cwCase') === newCase.case_id && document.getElementById('cwCaseId').value === newCase.case_id,
    ev('cwCase') + ' vs ' + newCase.case_id);
  const newRow = [...document.getElementById('caseTable').querySelectorAll('tr')].find(r => r.children[0].textContent.trim() === newCase.case_id);
  ok('new case appears in the crime-cases register', !!newRow, [...document.getElementById('caseTable').querySelectorAll('tr')].map(r => r.children[0].textContent.trim()).join(','));
  ok('its status cell is an amber "Under Investigation" pill',
    !!newRow && newRow.children[3].querySelector('.badge.amber') && newRow.children[3].textContent.trim() === 'Under Investigation',
    newRow && newRow.children[3].innerHTML);
  ok('its Actions cell has a View button', !!newRow && !!newRow.querySelector('.col-actions button'));

  section('4 · add a suspect WITH a linked case (purple pill)');
  const setF = (id, v) => { document.getElementById(id).value = v; };
  window.go('cid');
  window.openAddSuspect();
  await wait();
  ok('add-suspect modal is wide + centered', $('#overlay').classList.contains('on') && $('#modal').classList.contains('wide'));
  setF('sp-first', 'Liban'); setF('sp-second', 'Yusuf'); setF('sp-third', 'Mahdi'); setF('sp-fourth', 'Omar');
  setF('sp-dob', '1991-03-09'); setF('sp-national', '10055661'); setF('sp-mother', 'Amina Warsame'); setF('sp-address', 'Hargeisa, 26 June');
  document.getElementById('spCase').value = newCase.case_id;
  await wait(20);
  await window.submitAddSuspect();
  await wait(250);
  const linked = ev('db').suspects.find(s => s.case === newCase.case_id);
  ok('suspect saved against the case on the server', !!linked, JSON.stringify(ev('db').suspects.map(s => [s.person, s.case])));
  ok('origin recorded as Case Link', linked && linked.origin === 'Case Link', linked && linked.origin);
  ok('linked case renders as a purple pill',
    [...document.getElementById('suspectTable').querySelectorAll('.badge.purple')].some(b => b.textContent === newCase.case_id),
    [...document.getElementById('suspectTable').querySelectorAll('.badge')].map(b => b.className + ':' + b.textContent).join(' | '));
  ok('alert renders as a red pill',
    [...document.getElementById('suspectTable').querySelectorAll('.badge.red')].some(b => b.textContent === 'Active alert'));

  section('5 · add a suspect WITHOUT a case (blue Manual Entry pill)');
  window.openAddSuspect();
  await wait();
  setF('sp-first', 'Nimco'); setF('sp-second', 'Ali'); setF('sp-third', 'Farah'); setF('sp-fourth', 'Hassan');
  setF('sp-dob', '1995-12-25'); setF('sp-national', '10077882'); setF('sp-mother', 'Sahra Hussein'); setF('sp-address', 'Hargeisa, New Hargeisa');
  document.getElementById('spCase').value = '';
  document.getElementById('spOrigin').value = 'Manual Entry';
  setF('spNote', 'Direct field report — repeat offender, vehicle plate 4421.');
  await window.submitAddSuspect();
  await wait(250);
  const unlinked = ev('db').suspects.find(s => !s.case && s.reason && s.reason.includes('plate 4421'));
  ok('unlinked suspect saved with Manual Entry origin', !!unlinked && unlinked.origin === 'Manual Entry', JSON.stringify(ev('db').suspects.map(s => [s.person, s.case, s.origin])));
  ok('server stored the reason as notes', !!(await apiGet('/api/suspect-alerts', token)).items.find(s => (s.notes || '').includes('plate 4421')));
  ok('Manual Entry renders as a blue pill',
    [...document.getElementById('suspectTable').querySelectorAll('.badge.blue')].some(b => b.textContent === 'Manual Entry'),
    [...document.getElementById('suspectTable').querySelectorAll('.badge')].map(b => b.className + ':' + b.textContent).join(' | '));

  section('6 · record a checkpoint stop through the wide modal (server screening)');
  window.go('checkpoints');
  const cpBefore = ev('db').checkpoints.length;
  window.openCheckpointModal();
  await wait();
  ok('checkpoint modal is wide + centered', $('#overlay').classList.contains('on') && $('#modal').classList.contains('wide'));
  setF('cp-first', 'Liban'); setF('cp-second', 'Yusuf'); setF('cp-third', 'Mahdi'); setF('cp-fourth', 'Omar');
  setF('cp-dob', '1991-03-09'); setF('cp-national', '10055661');
  setF('cp-address', 'Hargeisa, 26 June'); setF('cp-permanent', 'Hargeisa, 26 June'); setF('cp-purpose', 'Transit');
  setF('gd-first', 'Yusuf'); setF('gd-second', 'Mahdi'); setF('gd-third', 'Omar'); setF('gd-fourth', 'Adan');
  setF('gd-relationship', 'Parent'); setF('gd-phone', '+252 63 555 7788');
  setF('gd-permanent', 'Hargeisa, 26 June'); setF('gd-occupation', 'Shopkeeper');
  const put = (sel, n) => {
    const inp = sel === 'cp-photo' ? document.getElementById('cp-photo') : document.querySelector(`input[data-slot="${sel}"]`);
    Object.defineProperty(inp, 'files', { value: [new window.File(['dummy-bytes'], n, { type: 'image/png' })], configurable: true });
    inp.dispatchEvent(new window.Event('change', { bubbles: true }));
  };
  put('tdoc0', 'traveler-doc-1.png'); put('tdoc1', 'traveler-doc-2.png');
  put('gdoc0', 'guardian-doc-1.png'); put('cp-photo', 'traveler-live.png');
  document.getElementById('cpLoc').value = 'West';
  document.getElementById('cpNotes').value = 'Minibus, heading to Berbera.';
  await window.submitCheckpoint();
  await wait(300);
  ok('checkpoint modal closed after submit', !$('#overlay').classList.contains('on'));
  ok('checkpoint event stored on the server', ev('db').checkpoints.length === cpBefore + 1, cpBefore + ' -> ' + ev('db').checkpoints.length);
  const stop = ev('db').checkpoints[0];
  ok('server computed "Flagged match" for the listed suspect', stop.screen === 'Flagged match', stop.screen);
  ok('server action is "Supervisor contacted"', stop.action === 'Supervisor contacted', stop.action);
  ok('Flagged match renders as a red pill',
    [...document.getElementById('cpTable').querySelectorAll('.badge.red')].some(b => b.textContent === 'Flagged match'));
  ok('Supervisor contacted renders as an amber pill',
    [...document.getElementById('cpTable').querySelectorAll('.badge.amber')].some(b => b.textContent === 'Supervisor contacted'));
  const uploads = (await apiGet('/api/checkpoint-events', token)).items[0];
  ok('uploaded traveler photo served from /uploads/', /\/uploads\//.test(uploads.traveler_photo || ''), uploads.traveler_photo);

  section('7 · airport + fingerprint registers from the server');
  window.go('airport');
  setF('air-first', 'Ayaan'); setF('air-second', 'Cabdi'); setF('air-third', 'Xasan'); setF('air-fourth', 'Axmed');
  setF('air-dob', '1997-04-18'); setF('air-national', '10012345'); setF('air-mother', 'Faadumo Cali'); setF('air-address', 'Hargeisa, Jigjiga Yar');
  setF('airFlight', 'HL-204'); setF('airRoute', 'Berbera / Hargeisa');
  await window.saveAirport({ preventDefault() {} });
  await wait(250);
  ok('airport record saved on the server', ev('db').airport.length >= 1, String(ev('db').airport.length));
  ok('airport row has the standardized cells', document.getElementById('airTable').querySelector('tr').children.length === 6);
  ok('airport screening pill present', !!document.getElementById('airTable').querySelector('.badge.green, .badge.red'));
  window.go('fingerprint');
  setF('fp-first', 'Sahra'); setF('fp-second', 'Yuusuf'); setF('fp-third', 'Axmed'); setF('fp-fourth', 'Aadan');
  setF('fp-dob', '2001-02-26'); setF('fp-national', '10024680'); setF('fp-mother', 'Amina Maxamed'); setF('fp-address', 'Hargeisa, 26 June');
  document.getElementById('gName').value = 'Yuusuf Axmed Aadan';
  document.getElementById('gRelation').value = 'Father';
  put('appDoc0', 'applicant-id.png'); put('appDoc1', 'applicant-form.png');
  put('guardDoc0', 'guardian-id.png'); put('guardDoc1', 'guardian-letter.png');
  await window.saveFingerprint({ preventDefault() {} });
  await wait(300);
  ok('clearance application saved on the server', ev('db').fingerprint.length >= 1, String(ev('db').fingerprint.length));
  ok('fingerprint row has 5 standardized cells', document.getElementById('fpTable').querySelector('tr').children.length === 5);
  ok('fingerprint status pill present', !!document.getElementById('fpTable').querySelector('.badge'));

  section('8 · View modals render server-backed records');
  const views = [['peopleTable', 'Identity profile'], ['fpTable', 'Clearance application'], ['airTable', 'Airport passenger record'], ['suspectTable', 'Suspect alert'], ['cpTable', 'Checkpoint stop']];
  for (const [id, title] of views) {
    window.closeModal();
    document.getElementById(id).querySelector('.col-actions button').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await wait();
    ok(`${id}: centered modal "${$('#modalTitle').textContent}"`, $('#overlay').classList.contains('on') && $('#modalTitle').textContent.includes(title), $('#modalTitle').textContent);
    ok(`${id}: body has content`, $('#modalBody').innerHTML.length > 80);
    ok(`${id}: footer pinned with buttons`, $('#modalFoot').querySelectorAll('.btn').length >= 1);
  }
  window.closeModal();

  section('9 · case workspace participants (server) + participant View modal');
  window.openCase(newCase.case_id);
  await wait(250);
  const partRows = document.getElementById('cwPartTable').querySelectorAll('tr');
  ok('participant rows rendered from the server', partRows.length >= 1, String(partRows.length));
  ok('participant row has 5 cells incl. Actions', partRows[0] && partRows[0].children.length === 5, partRows[0] && String(partRows[0].children.length));
  window.viewParticipant(0);
  await wait();
  ok('participant modal opens', $('#overlay').classList.contains('on') && $('#modalTitle').textContent.includes('Case participant'), $('#modalTitle').textContent);
  window.closeModal();

  section('10 · badge palette audit across all server-rendered tables');
  const allowed = new Set(['red', 'green', 'blue', 'purple', 'amber', 'gray']);
  const badges = $$('tbody .badge');
  const illegal = badges.filter(b => ![...b.classList].some(c => allowed.has(c)));
  ok(`${badges.length} badges, all standard`, illegal.length === 0, illegal[0] && illegal[0].outerHTML);
  const counts = {};
  badges.forEach(b => { const t = [...b.classList].find(c => allowed.has(c)); counts[t] = (counts[t] || 0) + 1; });
  ok('all four semantic colours present in the rendered tables', ['red', 'green', 'blue', 'purple'].every(k => counts[k]), JSON.stringify(counts));
  ok('no unexpected runtime errors', unexpected.length === 0, unexpected.join(' | '));

  console.log(`\n${checks - failures}/${checks} checks passed` + (failures ? `  (${failures} FAILED)` : ''));
  proc.kill('SIGTERM');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error('HARNESS ERROR', e); process.exit(2); });
