// Drives the REAL operations page (web/operations.html + operations.js + identity-intake.js) against the REAL API,
// REAL database (row-level security on) and real uploads.  Started by:  python -m tests.run_ui_flow
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(path.join(process.env.JSDOM_DIR || '.', 'x.js'));
const { JSDOM, VirtualConsole } = require('jsdom');
const vc = new VirtualConsole(); vc.sendTo(console, { omitJSDOMErrors: false });
const BASE = process.env.BASE_URL;

const dom = await JSDOM.fromURL(BASE + '/operations.html', {
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

await step('page loads; a checkpoint officer sees only their own checkpoint and no airport / station rights', async () => {
  assert.match($('title').textContent, /Operations/);
  await signIn('cp.south');
  assert.deepEqual([...$('#cp-unit').options].map(o => o.value), ['CP-SOUTH']);
  assert.equal($('#cp-save').disabled, false);
  assert.equal($('#ap-save').disabled, true);
  assert.equal($('#st-save').disabled, true);
  assert.match($('#g-policy').textContent, /required for every traveler/);
});

await step('client validation lists what is missing and sends nothing', async () => {
  fillTraveler('t', { first_name: 'Hodan', second_name: 'Ismaaciil', third_name: 'Nuur', date_of_birth: '1993-02-02', residence: 'Laascaanood' });
  click('#cp-save');
  await waitFor(() => result('cp').classList.contains('bad'), 'bad result');
  assert.match(result('cp').textContent, /Purpose of visit is required/);
  assert.match(result('cp').textContent, /photo is required/i);
  assert.ok($('#cp-purpose').closest('.field').classList.contains('invalid'));
  assert.equal((await api('/api/checkpoint-events', 'chief')).items.length, 0);
});

await step('a full stop registers a NEW traveler + guardian, files the event, screens clear, and lists it', async () => {
  type('#t-national_id', 'SO-55001'); type('#t-place_of_birth', 'Burao');
  type('#cp-purpose', 'Family visit');
  attach('#cp-photo', ['face.png', PNG]); attach('#cp-docs', ['id.pdf', PDF]);
  fillTraveler('g', { first_name: 'Warsame', second_name: 'Nuur', third_name: 'Dhegaweyne', national_id: 'SO-55002', phone: '+252 63 555 0001', residence: 'Burao, Gacan Libaax', occupation: 'Trader' });
  set('#g-relationship', 'Uncle'); attach('#cp-gdocs', ['gid.pdf', PDF]);
  click('#cp-save');
  await waitFor(() => result('cp').classList.contains('good'), 'good result (' + result('cp').textContent + ')', 8000);
  assert.match(result('cp').textContent, /No active alert — cleared/);
  assert.match(result('cp').textContent, /CP-CP-SOUTH-\d{4}-000001 recorded at South Checkpoint/);
  assert.match(result('cp').textContent, /New person registered/);
  assert.match(result('cp').textContent, /Guardian: Warsame Nuur Dhegaweyne \(new record\)/);
  await waitFor(() => /Hodan Ismaaciil Nuur/.test($('#cp-list').textContent), 'row in recent list');
  assert.equal($('#t-first_name').readOnly, true);                // the traveler is now a locked registry record
});

await step('the SAME traveler at the next stop is recognised ("already exists") and the same guardian is not duplicated', async () => {
  click('#cp-new');
  type('#t-national_id', ' so 55001 ');
  await waitFor(() => $('#t-match').classList.contains('ok') && $('#t-match').classList.contains('show'), 'exists banner');
  assert.match($('#t-match').textContent, /Person already exists in registry/);
  assert.equal($('#t-first_name').readOnly, true);
  assert.equal($('#t-first_name').value, 'Hodan');
  type('#t-residence', 'Laascaanood, Xero Awr');                  // dynamic field: editable
  type('#cp-purpose', 'Return trip');
  attach('#cp-photo', ['face2.png', PNG]); attach('#cp-docs', ['id2.pdf', PDF]);
  type('#g-national_id', 'SO-55002');
  await waitFor(() => $('#g-match').classList.contains('ok') && $('#g-match').classList.contains('show'), 'guardian exists banner');
  assert.equal($('#g-first_name').value, 'Warsame');
  set('#g-relationship', 'Uncle'); attach('#cp-gdocs', ['gid2.pdf', PDF]);
  click('#cp-save');
  await waitFor(() => result('cp').classList.contains('good'), 'second stop (' + result('cp').textContent + ')', 8000);
  assert.match(result('cp').textContent, /000002/);
  assert.match(result('cp').textContent, /Linked to the existing record/);
  assert.match(result('cp').textContent, /already in the registry/);
  const found = await api('/api/persons/search?q=SO55001', 'chief');
  assert.equal(found.exists, true);
  const tl = await api('/api/persons/' + found.person.person_ref + '/timeline', 'chief');
  assert.equal(tl.events.length, 2);
  const guardians = await api('/api/persons/' + found.person.person_ref, 'chief');
  assert.equal(guardians.guardians.length, 1);             // linked once, never twice
});

await step('a person with an ACTIVE ALERT gets the red FLAGGED MATCH screen — without any alert details', async () => {
  click('#cp-new');
  type('#t-national_id', 'SO-100004');
  await waitFor(() => $('#t-match').classList.contains('ok'), 'exists banner');
  type('#cp-purpose', 'Transit');
  attach('#cp-photo', ['f3.png', PNG]); attach('#cp-docs', ['i3.pdf', PDF]);
  fillTraveler('g', { first_name: 'Maxamed', second_name: 'Cali', third_name: 'Faarax', phone: '+252 1', residence: 'Oodweyne', occupation: 'Driver' });
  set('#g-relationship', 'Sibling'); attach('#cp-gdocs', ['g3.pdf', PDF]);
  click('#cp-save');
  await waitFor(() => result('cp').classList.contains('flag'), 'flag result (' + result('cp').textContent + ')', 8000);
  assert.match(result('cp').textContent, /FLAGGED MATCH — Supervisor contacted/);
  assert.doesNotMatch(result('cp').textContent, /DEMO ONLY|fictional|AL-/);
  await waitFor(() => /FLAGGED/.test($('#cp-list').textContent), 'flag badge in list');
});

await step('a similar name is an amber pick-list warning, never an automatic link; "different person" then registers a new one', async () => {
  click('#cp-new');
  fillTraveler('t', { first_name: 'Hodan', second_name: 'Ismaaciil', third_name: 'Nuur', fourth_name: 'Cali', date_of_birth: '1993-02-02', residence: 'Burao' });
  await waitFor(() => $('#t-match').classList.contains('warn'), 'amber warning');
  assert.match($('#t-matchlist').textContent, /Hodan Ismaaciil Nuur/);
  type('#cp-purpose', 'Trade'); attach('#cp-photo', ['f4.png', PNG]); attach('#cp-docs', ['i4.pdf', PDF]);
  fillTraveler('g', { first_name: 'Warsame', second_name: 'Nuur', third_name: 'Dhegaweyne' }); // guardian rule is checked by the server
  click('#cp-save');
  await waitFor(() => result('cp').classList.contains('bad'), 'server validation', 8000);
  assert.match(result('cp').textContent, /Guardian|relationship|contact/i);
  assert.ok($('#g-relationship').closest('.field').classList.contains('invalid'));
});

await step('an airport officer logs a passenger already known to another unit; the record links to the master profile', async () => {
  await signIn('ap.officer'); tab('airport');
  assert.equal($('#tab-airport').classList.contains('hidden'), false);
  assert.deepEqual([...$('#ap-unit').options].map(o => o.value), ['AP-LAA']);
  type('#a-national_id', 'SO-100001');
  await waitFor(() => $('#a-match').classList.contains('ok'), 'exists banner');
  assert.equal($('#a-first_name').readOnly, true);
  type('#ap-flight', 'fz 123'); type('#ap-origin', 'Dubai');
  click('#ap-save');
  await waitFor(() => result('ap').classList.contains('good'), 'good (' + result('ap').textContent + ')');
  assert.match(result('ap').textContent, /AR-AP-LAA-\d{4}-000001 — Arrival FZ123 at Laascaanood Airport/);
  assert.match(result('ap').textContent, /Linked to the existing record/);
  await waitFor(() => /FZ123/.test($('#ap-list').textContent), 'row in list');
});

await step('submitting the same passenger / flight / day again is refused as a duplicate', async () => {
  click('#ap-save');
  await waitFor(() => result('ap').classList.contains('bad'), 'duplicate message');
  assert.match(result('ap').textContent, /already logged/);
});

await step('switching to Departure changes which city is required, and the form says so', async () => {
  click('#ap-new');
  set('#ap-movement', 'Departure');
  assert.match($('#ap-dest-wrap label').textContent, /Destination city \*/);
  assert.doesNotMatch($('#ap-origin-wrap label').textContent, /\*/);
  type('#a-national_id', 'SO-100001'); await waitFor(() => $('#a-match').classList.contains('ok'), 'exists');
  type('#ap-flight', 'FZ9');
  click('#ap-save');
  await waitFor(() => result('ap').classList.contains('bad'), 'client validation');
  assert.match(result('ap').textContent, /Destination city is required for a departure/);
});

await step('the DATA-ONLY Buuhoodle airport works for its own officer — same person, different airport, one record', async () => {
  await signIn('ap.buuhoodle'); tab('airport');
  assert.deepEqual([...$('#ap-unit').options].map(o => o.value), ['AP-BUU']);
  type('#a-national_id', 'SO-100001'); await waitFor(() => $('#a-match').classList.contains('ok'), 'exists');
  set('#ap-movement', 'Departure'); type('#ap-flight', 'FZ77'); type('#ap-dest', 'Dubai');
  click('#ap-save');
  await waitFor(() => result('ap').classList.contains('good'), 'good (' + result('ap').textContent + ')');
  assert.match(result('ap').textContent, /AR-AP-BUU-\d{4}-000001 — Departure FZ77 at Buuhoodle Airport/);
  const person = (await api('/api/persons/search?q=SO-100001', 'chief')).person;
  const tl = await api('/api/persons/' + person.person_ref + '/timeline', 'chief');
  assert.deepEqual(tl.events.map(e => e.unit_code).filter(c => c.startsWith('AP-')).sort(), ['AP-BUU', 'AP-LAA']);   // other services (e.g. a clearance filing) may add their own events
  assert.equal((await api('/api/airport-records', 'ap.buuhoodle')).items.length, 1);   // sees only its own airport
});

await step('a station officer files an incident; the victim is linked by National ID but never created', async () => {
  await signIn('st.laas'); tab('station');
  assert.deepEqual([...$('#st-unit').options].map(o => o.value), ['ST-004']);
  assert.ok($('#st-category').options.length > 5, 'categories come from policy data');
  click('#st-save');
  await waitFor(() => result('st').classList.contains('bad'), 'client validation');
  assert.match(result('st').textContent, /Crime category is required/);
  set('#st-category', 'Theft/Burglary'); set('#st-severity', 'Medium');
  type('#st-when', '2026-09-30T14:30'); type('#st-location', 'Central market'); type('#st-desc', 'Shop broken into overnight');
  type('#st-vname', 'Ayaan Cabdi'); type('#st-vnid', 'SO-100001');
  await waitFor(() => /Already in the registry: Ayaan Cabdi Xasan Axmed/.test($('#st-vlink').textContent), 'victim link note');
  type('#st-officer', 'OFF-DEMO-001');
  attach('#st-e1file', ['photo.png', PNG]); set('#st-e1type', 'Photo');
  click('#st-save');
  await waitFor(() => result('st').classList.contains('good'), 'good (' + result('st').textContent + ')', 8000);
  assert.match(result('st').textContent, /CRM-ST-004-\d{4}-000001 at Las Anod Station/);
  assert.match(result('st').textContent, /Victim linked to registry record P-/);
  await waitFor(() => /Central market/.test($('#st-list').textContent), 'row in list');
  const before = (await api('/api/persons/search?q=SO-999999', 'chief')).exists;
  assert.equal(before, false);
});

await step('an unknown victim stays free text (no person is registered) and an anonymous victim keeps no identity', async () => {
  click('#st-new'); attach('#st-e1file');                          // a real browser empties the picker on reset; our fake needs help
  set('#st-category', 'Assault'); type('#st-when', '2026-09-30T20:00'); type('#st-location', 'Hodan'); type('#st-desc', 'Fight');
  type('#st-vname', 'Somebody Else'); type('#st-vnid', 'SO-999999');
  await waitFor(() => /Not in the registry/.test($('#st-vlink').textContent), 'not-in-registry note');
  click('#st-save');
  await waitFor(() => result('st').classList.contains('good'), 'good (' + result('st').className + ': ' + result('st').textContent + ')', 8000);
  assert.doesNotMatch(result('st').textContent, /Victim linked/);
  assert.equal((await api('/api/persons/search?q=SO-999999', 'chief')).exists, false);   // nobody was created
  click('#st-new'); set('#st-category', 'Robbery'); type('#st-when', '2026-09-30T21:00'); type('#st-location', 'Road'); type('#st-desc', 'Robbery');
  $('#st-anon').checked = true; $('#st-anon').dispatchEvent(new w.Event('change', { bubbles: true }));
  assert.ok($('#st-victim').classList.contains('hidden'));
  click('#st-save');
  await waitFor(() => result('st').classList.contains('good'), 'good', 8000);
  assert.match(result('st').textContent, /Victim kept anonymous/);
});

await step('a desk officer who is not posted at this station is rejected with the field highlighted', async () => {
  click('#st-new'); set('#st-category', 'Fraud'); type('#st-when', '2026-09-30T09:00'); type('#st-location', 'Bank'); type('#st-desc', 'Forged cheque');
  type('#st-officer', 'OFF-DEMO-002');                              // posted at Buuhoodle Station, not here
  click('#st-save');
  await waitFor(() => result('st').classList.contains('bad'), 'rejected');
  assert.match(result('st').textContent, /not an active officer posted at Las Anod Station/);
  assert.ok($('#st-officer').closest('.field').classList.contains('invalid'));
});

await step('stations only see their own incidents; a regional commander sees their region; the Chief Commander is read-only', async () => {
  await signIn('st.buuhoodle'); tab('station');
  await waitFor(() => /Nothing recorded yet/.test($('#st-list').textContent), 'empty list for the other station');
  await signIn('rc.sool');
  await waitFor(() => /Central market/.test($('#st-list').textContent), 'regional view');
  assert.equal($('#st-save').disabled, true);                       // commanders view, they do not file
  await signIn('chief');
  assert.equal($('#cp-save').disabled && $('#ap-save').disabled && $('#st-save').disabled, true);
  await waitFor(() => /South Checkpoint/.test($('#cp-list').textContent), 'chief sees checkpoint stops');
  await waitFor(() => /Buuhoodle Airport/.test($('#ap-list').textContent), 'chief sees both airports');
  assert.match($('#cp-unit').innerHTML, /none assigned/);
});

console.log(n + ' operations UI steps passed');
