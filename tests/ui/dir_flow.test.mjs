// Drives the REAL operations page (web/directorate.html + operations.js + identity-intake.js) against the REAL API,
// REAL database (row-level security on) and real uploads.  Started by:  python -m tests.run_ui_flow
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(path.join(process.env.JSDOM_DIR || '.', 'x.js'));
const { JSDOM, VirtualConsole } = require('jsdom');
const vc = new VirtualConsole(); vc.sendTo(console, { omitJSDOMErrors: false });
const BASE = process.env.BASE_URL;

const dom = await JSDOM.fromURL(BASE + '/directorate.html', {
  virtualConsole: vc, runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
  beforeParse(w) { w.fetch = (u, o) => fetch(new URL(u, BASE), o); w.Element.prototype.scrollIntoView = () => {}; },
});
const w = dom.window, d = w.document;
const $ = s => d.querySelector(s);
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, what, ms = 5000) {
  const t0 = Date.now();
  for (;;) {
    let v; try { v = fn(); } catch (_) { v = null; }
    if (v) return v;
    if (Date.now() - t0 > ms) throw new Error('timeout waiting for: ' + what + '\n' + $('body').textContent.replace(/\s+/g, ' ').slice(0, 700));
    await sleep(40);
  }
}
const type = (sel, val) => { const el = $(sel); el.value = val; el.dispatchEvent(new w.Event('input', { bubbles: true })); };
const set = (sel, val) => { const el = $(sel); el.value = val; el.dispatchEvent(new w.Event('change', { bubbles: true })); };
const click = sel => $(sel).dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(40)]);
const PDF = Buffer.from('%PDF-1.4 demo');
let fileSeq = 0;
function attach(sel, ...files) {                                   // jsdom cannot open a file picker: give the input real "files"
  const list = files.map(([name, buf]) => ({ name, size: buf.length, lastModified: 1000 + (fileSeq++),
    arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.length) }));
  Object.defineProperty($(sel), 'files', { value: list, configurable: true });
}
async function api(p, user = 'admin', opts = {}) {
  const r = await fetch(BASE + p, { ...opts, headers: { 'X-Dev-User': user, 'Content-Type': 'application/json', ...(opts.headers || {}) } });
  return { status: r.status, ...(await r.json()) };
}
const result = id => $('#' + id + '-result');
let n = 0;
const step = async (name, fn) => { await fn(); n++; console.log('ok -', name); };
async function signIn(user) {
  await waitFor(() => $('#user').options.length > 2, 'user list');
  $('#who').textContent = '';
  set('#user', user);
  await waitFor(() => /./.test($('#who').textContent), 'session for ' + user);
  await sleep(150);                                               // units + vocabularies arrive together with /api/me
}
const tab = name => { click('[data-tab=' + name + ']'); };
const fillTraveler = (p, v) => { for (const [k, x] of Object.entries(v)) type('#' + p + '-' + k, x); };


const fillP = (p, v) => { for (const [k, x] of Object.entries(v)) type('#' + p + '-' + k, x); };

await step('page loads; a bureau intake officer can file clearances but cannot decide them', async () => {
  assert.match($('title').textContent, /Directorate/);
  await signIn('fp.sanaag');
  assert.deepEqual([...$('#cl-unit').options].map(o => o.value), ['BR-FP-SANAAG']);
  assert.equal($('#cl-save').disabled, false);
  assert.ok([...$('#cl-purpose').options].some(o => o.value === 'Travel'));
  assert.match($('#cl-gpolicy').textContent, /required for every applicant/);
  assert.equal($('#cl-list').querySelectorAll('[data-act=approve]').length, 0);
  assert.equal($('#cs-save').disabled, true);
});

await step('clearance intake: validation first, then a real filing with photo, documents and guardian', async () => {
  click('#cl-save');
  await waitFor(() => result('cl').classList.contains('bad'), 'validation message');
  assert.match(result('cl').textContent, /First name is required/);
  fillP('c', { first_name: 'Sagal', second_name: 'Yuusuf', third_name: 'Warsame', date_of_birth: '1998-07-09', national_id: 'UI-FP-0001', mother_name: 'Hibo Cali', residence: 'Ceerigaabo', phone: '+252 63 5550101' });
  set('#cl-purpose', 'Education');
  attach('#cl-photo', ['face.png', PNG]); attach('#cl-docs', ['id.pdf', PDF], ['form.pdf', PDF]);
  fillP('cg', { first_name: 'Cali', second_name: 'Warsame', third_name: 'Nuur', national_id: 'UI-FP-0002' });
  set('#cl-grel', 'Parent'); attach('#cl-gdocs', ['g1.pdf', PDF], ['g2.pdf', PDF]);
  click('#cl-save');
  await waitFor(() => result('cl').classList.contains('good'), 'filed: ' + result('cl').textContent, 8000);
  assert.match(result('cl').textContent, /FP-BR-FP-SANAAG-\d{4}-\d+ filed at Fingerprint Intake — Sanaag/);
  await waitFor(() => /Sagal/.test($('#cl-list').textContent), 'new application in the queue');
  assert.match($('#cl-list').textContent, /locked/);
});

await step('the national Fingerprint officer approves the 13-hour-old application, prints it, and anyone can verify it', async () => {
  await signIn('fp.officer');
  await waitFor(() => $('#cl-list').querySelector('[data-act=approve]'), 'approve button');
  assert.equal($('#cl-list').querySelectorAll('[data-act=approve]').length, 1, 'only the application past the review window can be decided');
  $('#cl-list').querySelector('[data-act=approve]').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await waitFor(() => /approved and signed: CL-/.test($('#cl-cert').textContent), 'approved');
  const num = $('#cl-cert').textContent.match(/CL-[A-Z0-9-]+/)[0];
  await waitFor(() => $('#cl-list').querySelector('[data-act=print]'), 'print button');
  $('#cl-list').querySelector('[data-act=print]').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await waitFor(() => /CERTIFICATE CL-/.test($('#cl-cert').textContent), 'printed');
  assert.match($('#cl-cert').textContent, /signature [A-Za-z0-9+\/=_-]{16}/);
  const v = await (await fetch(BASE + '/api/verify/' + num)).json();            // no sign-in at all
  assert.equal(v.valid, true); assert.match(v.holder, /^Ayaan C\. /);   /* masked: initials only */
});

await step('CID: a case with a suspect raises an alert; evidence and status changes work; alerts can be lifted', async () => {
  await signIn('cid.sool'); tab('cid');
  await waitFor(() => $('#cs-owner').options.length && $('#cs-owner').value, 'owner unit');
  assert.equal($('#cs-owner').value, 'BR-CID-SOOL');
  type('#cs-category', 'Burglary'); type('#cs-location', 'Laascaanood market'); type('#cs-summary', 'DEMO — shop broken into overnight.');
  const row = d.querySelector('#cs-parts .cs-part');
  const put = (k, v) => { const el = row.querySelector('[data-k=' + k + ']'); el.value = v; };
  put('role', 'Suspect'); put('first_name', 'Nuuradiin'); put('second_name', 'Geele'); put('third_name', 'Faarax'); put('national_id', 'UI-CID-0001');
  click('#cs-save');
  await waitFor(() => result('cs').classList.contains('good'), 'case opened: ' + result('cs').textContent, 8000);
  assert.match(result('cs').textContent, /CS-BR-CID-SOOL-\d{4}-\d+ opened with 1 participant\(s\) · ALERT raised for Nuuradiin/);
  await waitFor(() => /Nuuradiin/.test($('#al-list').textContent), 'alert listed');
  const ref = result('cs').textContent.match(/CS-[A-Z0-9-]+/)[0];
  d.querySelector('#cs-list [data-act=open-case][data-id="' + ref + '"]').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await waitFor(() => !$('#cs-detail-panel').classList.contains('hidden') && /Nuuradiin/.test($('#cs-detail').textContent), 'case detail');
  attach('#cs-evfile', ['photo.png', PNG]); set('#cs-evtype', $('#cs-evtype').options[0].value); type('#cs-evcap', 'CCTV still');
  click('#cs-addev');
  await waitFor(() => /attached/.test($('#cs-detail-result').textContent), 'evidence attached');
  set('#cs-newstatus', 'Under Investigation'); click('#cs-update');
  await waitFor(() => /Status saved/.test($('#cs-detail-result').textContent), 'status saved');
  const lift = d.querySelector('[data-act=lift]'); const alertRef = lift.dataset.id;
  d.querySelector('[data-reason="' + alertRef + '"]').value = 'Cleared by the investigating officer';
  lift.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await waitFor(() => /lifted/.test(result('al').textContent), 'lifted');
});

await step('HR: the filer cannot review; the HR reviewer approves the promotion and the officer’s rank changes', async () => {
  await signIn('cmd.laas'); tab('hr');
  await waitFor(() => /OFF-DEMO-001/.test($('#of-list').textContent), 'officer in own unit');
  assert.equal($('#cd-list').querySelectorAll('[data-act=cd-approve]').length, 0, 'the filer cannot review their own file');
  assert.equal($('#of-new-panel').classList.contains('hidden'), true);
  await signIn('hr.reviewer'); tab('hr');
  await waitFor(() => $('#cd-list').querySelector('[data-act=cd-approve]'), 'approve button');
  $('#cd-list').querySelector('[data-act=cd-approve]').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await waitFor(() => /Verified & Approved/.test(result('cd-review').textContent) || /Approved/.test(result('cd-review').textContent), 'approved: ' + result('cd-review').textContent);
  assert.match(result('cd-review').textContent, /officer is now Inspector/);
});

await step('Admin: a data-only bureau and a role assignment; unlisted regions are refused', async () => {
  await signIn('admin'); tab('admin');
  await waitFor(() => $('#ad-parent').options.length > 2, 'parents');
  set('#ad-parent', 'DIR-CID'); set('#ad-type', 'bureau'); type('#ad-code', 'BR-CID-ETOG'); type('#ad-name', 'CID — East Togdheer'); set('#ad-region', 'ETOG');
  click('#ad-save');
  await waitFor(() => result('ad').classList.contains('good'), 'unit created: ' + result('ad').textContent);
  assert.match(result('ad').textContent, /BR-CID-ETOG created under DIR-CID \(East Togdheer\)/);
  await waitFor(() => /BR-CID-ETOG/.test($('#ad-units').textContent), 'unit in tree');
  type('#as-user', 'cid.sool'); set('#as-role', 'cid_officer'); set('#as-unit', 'BR-CID-ETOG'); click('#as-save');
  await waitFor(() => result('as').classList.contains('good'), 'granted: ' + result('as').textContent);
  await waitFor(() => /BR-CID-ETOG/.test($('#as-list').textContent), 'assignment listed');
  const bad = await api('/api/admin/units', 'admin', { method: 'POST', body: JSON.stringify({ parent: 'HQ', unit_type: 'region', code: 'ELSEWHERE', name: 'Nowhere' }) });
  assert.equal(bad.status, 422);
});

console.log(n + ' directorate UI steps passed');
dom.window.close();
process.exit(0);
