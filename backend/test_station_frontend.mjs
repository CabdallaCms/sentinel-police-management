#!/usr/bin/env node
// DOM regressions for the Registered Stations row actions (View / Edit) and the
// role-based permission rules that gate them. Install jsdom@26:
//
//   npm install --no-save --package-lock-file=false jsdom@26
//   node backend/test_station_frontend.mjs
//
// What it proves, in the real page script running inside jsdom:
//
//   1. The Registered Stations table paints an Actions column: every row gets a
//      VIEW button, and only a SystemAdmin / Admin session gets the EDIT button
//      (`.admin-edit`, hidden for every other body class).
//   2. The View drawer renders the full station record — code, name, Region →
//      District → Village, operational status, officer count, vehicle count and
//      the mirrored Police Stations branch lineage — from the authoritative
//      GET /api/stations/<id> payload, and falls back to the locally merged row.
//   3. The Edit modal opens for an administrator, prefills the record, PATCHes
//      /api/stations/<id> and merges the saved row back into the register.
//   4. A non-admin session (HR Directorate, unit officer, read-only Commander)
//      cannot open the Edit modal at all, and a mirrored `BR-<id>` branch entry
//      is view-only even for an administrator.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://sentinel.test', runScripts: 'outside-only' });
const w = dom.window, ctx = dom.getInternalVMContext();
w.HTMLElement.prototype.scrollIntoView = function () {};
const requests = [];
let detailPayload = null;
w.fetch = async (url, opts = {}) => {
  requests.push({ url: String(url), method: (opts.method || 'GET').toUpperCase(), body: opts.body });
  if (opts.method === 'PATCH' || opts.method === 'PUT') {
    const sent = JSON.parse(opts.body || '{}');
    return { ok: true, status: 200, json: async () => ({ updated: true, station: {
      id: 'ST-004', station_id: 'ST-004', code: 'SOO-C-01', name: sent.name,
      region: sent.region, district: sent.district, village: sent.village,
      operational_status: sent.operational_status, notes: sent.notes || '',
      station_tier: 'Regional HQ', contact_phone: '+252 63 555 0100', cell_capacity: 20,
      updated_at: '2026-10-12 10:00:00' } }) };
  }
  return { ok: true, status: 200, json: async () => detailPayload };
};
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/if\(document\.readyState==='loading'\)[\s\S]*$/, '');
vm.runInContext(script, ctx);
const run = (s) => vm.runInContext(s, ctx);
const $ = (id) => w.document.getElementById(id);
const tick = () => new Promise((resolve) => setTimeout(resolve, 30));
// closeEntryModal() plays a 220ms closing animation before removing `.open`.
const settle = () => new Promise((resolve) => setTimeout(resolve, 320));
const rowButtons = (name) => {
  const row = [...w.document.querySelectorAll('#stationsTable tr')]
    .find((tr) => (tr.textContent || '').includes(name));
  return row ? [...row.querySelectorAll('button')] : [];
};
const buttonNamed = (name, label) =>
  rowButtons(name).find((b) => (b.textContent || '').trim() === label);

run(`persist=()=>{}; toast=(s,sub)=>{window._lastToast=[s,sub]};
  refreshBranchSelect=async()=>true; guardReadOnly=()=>false; renderAll=()=>{};
  sessionVisibility=null; serverOn=true; apiToken='test-token';
  db.stations=[
    {id:'ST-004',station_id:'ST-004',name:'Las Anod Station',code:'SOO-C-01',region:'Sool',
     district:'Laascaanood',village:'Laascaanood',station_tier:'Regional HQ',operational_status:'Active',
     contact_phone:'+252 63 555 0100',cell_capacity:20,notes:'Regional headquarters',
     created_at:'2026-01-02 08:00:00',updated_at:'2026-02-03 09:30:00'},
    {id:'BR-12',station_id:'BR-12',name:'Taleex Branch',code:'BR-12',region:'Sool',
     district:'Taleex',village:'Taleex',notes:'Mirrored from branch BR-12',
     station_tier:'Mirrored Branch',operational_status:'Active',cell_capacity:0}
  ];
  db.officers=[{service_id:'POL-1',full_name:'Officer One',rank:'Inspector',station_id:'ST-004',duty_status:'Active'},
               {service_id:'POL-2',full_name:'Officer Two',rank:'Constable',station_id:'ST-004',duty_status:'Active'}];
  db.cars=[{id:'VEH-1',plate:'SL-100',make:'Toyota Hilux',station:'ST-004'}];
  branchCatalog={loaded:true,items:[{id:12,name:'Taleex Branch',region:'Sool',district:'Taleex',unit_type:'police_station'}],regions:[],unit_types:[],districts:[]};
`);

// ---------------------------------------------------------------- markup ----
try {
  assert.ok(/<th>Actions<\/th>/.test(html), 'the Registered Stations table has an Actions column header');
  const header = html.match(/<tbody id="stationsTable">/) ? html.split('<tbody id="stationsTable">')[0] : '';
  assert.ok(header.lastIndexOf('<th>Actions</th>') > header.lastIndexOf('<th>Village/Town</th>'),
    'Actions is the last column of the Registered Stations header');
  assert.ok(/id="stViewModal"/.test(html) && /id="stViewBody"/.test(html),
    'the station View drawer markup exists');
  assert.ok(/id="stEditModal"/.test(html) && /id="stEditForm"/.test(html),
    'the station Edit modal markup exists');
  assert.ok(/body:not\(\.can-edit-records\) \.admin-edit\{display:none !important\}/.test(html),
    'the Edit action is hidden for every non-admin session by CSS');
  assert.ok(/function applyRecordEditMode\(\)/.test(html)
    && /applyRecordEditMode\(\);/.test(html),
    'applyRecordEditMode() paints the management-edit document class');
  assert.ok(!/\.admin-write[\s\S]{0,200}id="stViewModal"/.test(html),
    'the View drawer is not inside the SystemAdmin-only write block');
  assert.ok(/READ_ONLY_VIEW_MODALS=new Set\(\['pvModal', 'stViewModal'\]\)/.test(html),
    'the read-only Commander can open the View drawer (READ_ONLY_VIEW_MODALS)');
  console.log('ok: Actions column + View drawer + Edit modal markup and the non-admin hide rule');
} catch (err) { console.error(err); process.exit(1); }

// -------------------------------------------------- admin: table actions ----
try {
  run(`sessionUser={role:'SystemAdmin',role_label:'System Administrator',can_edit_records:true,can_edit_stations:true,permissions:['stations:manage']};
       currentUser=sessionUser; sessionVisibility={is_admin:true,can_edit_stations:true,can_edit_records:true,can_manage_stations:true};
       renderStationsTable();`);
  const rows = w.document.querySelectorAll('#stationsTable tr');
  assert.equal(rows.length, 2, 'both registry rows render');
  assert.ok(buttonNamed('Las Anod Station', 'View'), 'every row exposes a View button');
  assert.ok(buttonNamed('Las Anod Station', 'Edit'), 'an administrator sees the Edit button');
  assert.equal(buttonNamed('Las Anod Station', 'Edit').classList.contains('admin-edit'), true,
    'the Edit button carries the .admin-edit (SystemAdmin-only) class');
  assert.equal(buttonNamed('Las Anod Station', 'View').getAttribute('data-view'), '1',
    'the View button is marked as a read surface for the read-only sweep');
  assert.equal(buttonNamed('Taleex Branch', 'Edit'), undefined,
    'a mirrored BR-<id> branch entry is view-only even for an administrator');
  assert.ok(buttonNamed('Taleex Branch', 'View'), 'a mirrored branch entry still opens the record');
  // The read-only (Commander) DOM sweep must remove the Edit control from a
  // painted row while leaving the View control (a read surface) in place.
  run(`sessionUser={role:'chief_commander',read_only:true,can_write:false,can_edit_records:false};
       currentUser=sessionUser;
       sessionVisibility={read_only:true,is_read_only:true,can_write:false,can_edit_records:false};
       applyReadOnlyMode();`);
  const roView = buttonNamed('Las Anod Station', 'View');
  const roEdit = buttonNamed('Las Anod Station', 'Edit');
  assert.equal(roView.getAttribute('data-ro-hidden'), null,
    'the read-only sweep keeps the View action (data-view surface)');
  assert.equal(roView.style.display, '', 'the View action stays visible for the Commander');
  assert.ok(roEdit && (roEdit.getAttribute('data-ro-hidden') === '1' || roEdit.style.display === 'none'),
    'the read-only sweep removes the Edit action for the Commander');
  assert.equal(w.document.body.classList.contains('can-edit-records'), false,
    'the Commander session never carries the management-edit document class');
  run(`sessionUser={role:'SystemAdmin',can_edit_records:true,can_edit_stations:true};
       currentUser=sessionUser; sessionVisibility={is_admin:true,can_edit_records:true,can_edit_stations:true};
       applyReadOnlyMode(); renderStationsTable();`);
  assert.ok(buttonNamed('Las Anod Station', 'Edit'),
    'a write-capable administrator signing in on the same tab gets Edit back');
  assert.equal(w.document.body.classList.contains('can-edit-records'), true,
    'the administrator session carries the management-edit document class');
  // Offline / re-hydrated administrator (no /api/me visibility block yet): the
  // role itself must still unlock the row action.
  run(`sessionVisibility=null;
       sessionUser={role:'SystemAdmin'}; currentUser=sessionUser;
       applyReadOnlyMode(); renderStationsTable();`);
  assert.equal(w.document.body.classList.contains('can-edit-records'), true,
    'a re-hydrated SystemAdmin session keeps the edit capability before /api/me answers');
  assert.ok(buttonNamed('Las Anod Station', 'Edit'),
    'the Edit action is available to the re-hydrated administrator');
  run(`sessionUser={role:'hr_officer'}; currentUser=sessionUser;
       sessionVisibility={is_admin:false,can_edit_records:false,can_edit_stations:false};
       applyReadOnlyMode(); renderStationsTable();`);
  assert.equal(w.document.body.classList.contains('can-edit-records'), false,
    'the HR Directorate session clears the management-edit document class');
  run(`sessionUser={role:'SystemAdmin',can_edit_records:true,can_edit_stations:true};
       currentUser=sessionUser; sessionVisibility={is_admin:true,can_edit_records:true,can_edit_stations:true};
       applyReadOnlyMode(); renderStationsTable();`);
  console.log('ok: admin sees View + Edit on registry rows; mirrored branch entries stay view-only');
} catch (err) { console.error(err); process.exit(1); }

// ---------------------------------------------- non-admin: no Edit action ----
try {
  for (const [role, vis] of [
    ['hr_officer', { is_admin: false, can_edit_stations: false, can_edit_records: false }],
    ['cp_south', { is_admin: false, can_edit_stations: false, can_edit_records: false }],
    ['chief_commander', { is_admin: false, can_edit_stations: false, can_edit_records: false, read_only: true }],
  ]) {
    run(`sessionUser={role:${JSON.stringify(role)},can_edit_records:false,can_edit_stations:false};
         currentUser=sessionUser; sessionVisibility=${JSON.stringify(vis)};
         renderStationsTable();`);
    assert.ok(buttonNamed('Las Anod Station', 'View'), `${role}: can still View a station`);
    assert.equal(buttonNamed('Las Anod Station', 'Edit'), undefined,
      `${role}: no Edit button is painted`);
    run(`window._lastToast=null; openStationEdit('ST-004');`);
    assert.ok($('stEditModal').classList.contains('open') === false,
      `${role}: the Edit modal refuses to open`);
    assert.ok(w._lastToast && /Administrator/i.test(w._lastToast[1] || w._lastToast[0]),
      `${role}: the refusal explains the System Administrator requirement`);
  }
  run(`sessionUser={role:'SystemAdmin',can_edit_records:true,can_edit_stations:true};
       currentUser=sessionUser; sessionVisibility={is_admin:true,can_edit_records:true,can_edit_stations:true};
       renderStationsTable();`);
  console.log('ok: HR / checkpoint / read-only Commander sessions render View only and cannot open Edit');
} catch (err) { console.error(err); process.exit(1); }

// ------------------------------------------------------- View: the drawer ----
try {
  detailPayload = { station: {
    id: 'ST-004', station_id: 'ST-004', code: 'SOO-C-01', name: 'Las Anod Station',
    region: 'Sool', district: 'Laascaanood', village: 'Laascaanood', station_tier: 'Regional HQ',
    operational_status: 'Active', contact_phone: '+252 63 555 0100', cell_capacity: 20,
    notes: 'Regional headquarters', created_at: '2026-01-02 08:00:00',
    updated_at: '2026-02-03 09:30:00', officer_count: 14, vehicle_count: 5,
    commander: { service_id: 'POL-9', full_name: 'Insp. Test Commander', rank: 'Inspector' },
    deputy: null, can_edit: true, persisted: true, mirrored: true,
    branch: { id: 12, name: 'Lasanod Branch', region: 'Sool', district: 'Laascaanood', unit_type: 'police_station' },
    branch_lineage: 'Mirrored from the Police Stations branch Lasanod Branch (BR-12)',
    edit_disabled_reason: null } };
  requests.length = 0;
  // jsdom (runScripts: 'outside-only') does not compile inline handler
  // attributes, so the wiring is asserted from the markup and the handler is
  // then driven directly — exactly what a real click does.
  assert.match(buttonNamed('Las Anod Station', 'View').getAttribute('onclick'), /openStationView\('ST-004'\)/,
    'the View button is wired to openStationView(<station id>)');
  run(`openStationView('ST-004');`);
  assert.ok($('stViewModal').classList.contains('open'), 'View opens the station record drawer');
  assert.match($('stViewTitle').textContent, /SOO-C-01/, 'the drawer header names the station code');
  const local = $('stViewBody').textContent;
  assert.ok(/Las Anod Station/.test(local) && /Sool/.test(local) && /Laascaanood/.test(local),
    'the drawer paints name and Region → District → Village immediately (local row)');
  await tick(); await tick();
  const body = $('stViewBody').textContent;
  const detail = requests.find((r) => r.url.startsWith('/api/stations/') && r.method === 'GET');
  assert.ok(detail, 'the drawer loads GET /api/stations/<id>');
  assert.ok(/SOO-C-01/.test(body) && /Las Anod Station/.test(body), 'the drawer shows code + name');
  assert.ok(/Sool/.test(body) && /Laascaanood/.test(body), 'the drawer shows region, district and village');
  assert.ok(/Active/.test(body), 'the drawer shows the operational status');
  assert.ok(/Officers deployed/.test(body) && /14/.test(body), 'the drawer shows the officer count');
  assert.ok(/Vehicles assigned/.test(body) && /5/.test(body), 'the drawer shows the vehicle count');
  assert.ok(/Lasanod Branch/.test(body) && /BR-12/.test(body),
    'the drawer shows the mirrored branch lineage');
  assert.ok(/Test Commander/.test(body), 'the drawer resolves the commander record');
  assert.ok(/data-station-action="edit"/.test(html) && /Edit station/.test(body),
    'the administrator drawer offers the Edit action');
  run(`closeEntryModal('stViewModal');`);
  console.log('ok: View drawer renders the full record, counters and mirrored branch lineage');
} catch (err) { console.error(err); process.exit(1); }

// ------------------------------------------- Edit: prefill, save, re-render ----
try {
  requests.length = 0;
  run(`window._stationDetailCache={'ST-004':${JSON.stringify(detailPayload.station)}};`);
  run(`openStationEdit('ST-004');`);
  assert.ok($('stEditModal').classList.contains('open'), 'Edit opens the administration modal');
  assert.equal($('stEditName').value, 'Las Anod Station', 'the name is prefilled');
  assert.equal($('stEditCode').value, 'SOO-C-01', 'the code is prefilled read-only');
  assert.equal($('stEditStatus').value, 'Active', 'the operational status is prefilled');
  assert.equal($('stEditPhone').value, '+252 63 555 0100', 'the contact phone is prefilled');
  assert.equal($('ste-region').value, 'Sool', 'the region dropdown is prefilled');
  assert.equal($('ste-district').value, 'Laascaanood', 'the district dropdown cascades from the region');
  assert.equal($('ste-village').value, 'Laascaanood', 'the village/town is prefilled');

  assert.match($('stEditForm').getAttribute('onsubmit'), /saveStationEdit\(event\)/,
    'the Edit form is wired to saveStationEdit(event)');
  $('stEditName').value = 'Las Anod Central Station';
  $('stEditStatus').value = 'Maintenance';
  $('ste-village').value = 'Laascaanood Town';
  await run(`saveStationEdit({preventDefault(){},target:document.getElementById('stEditForm')});`);
  await settle();
  const patch = requests.find((r) => r.method === 'PATCH');
  assert.ok(patch, 'Save sends a PATCH');
  assert.equal(patch.url, '/api/stations/ST-004', 'the PATCH targets the station member path');
  const sent = JSON.parse(patch.body);
  assert.equal(sent.name, 'Las Anod Central Station', 'the edited name is sent');
  assert.equal(sent.operational_status, 'Maintenance', 'the edited status is sent');
  assert.equal(sent.region, 'Sool', 'the region is sent');
  assert.equal(sent.district, 'Laascaanood', 'the district is sent');
  assert.equal(sent.village, 'Laascaanood Town', 'the edited village/town is sent');
  assert.equal($('stEditModal').classList.contains('open'), false, 'the modal closes on success');
  const saved = run(`JSON.stringify((db.stations||[]).find(s=>String(s.id)==='ST-004'))`);
  assert.match(saved, /Las Anod Central Station/, 'the saved row is merged back into the register');
  run(`renderStationsTable();`);
  assert.ok(buttonNamed('Las Anod Central Station', 'View'),
    'the table is repainted from the updated register row');
  assert.ok(w._lastToast && /updated/i.test(w._lastToast[0] || ''),
    'the officer is told the station was updated');

  // Validation still applies before any request leaves the browser.
  requests.length = 0;
  run(`openStationEdit('ST-004');`);
  $('stEditName').value = '   ';
  await run(`saveStationEdit({preventDefault(){},target:document.getElementById('stEditForm')});`);
  await settle();
  assert.equal(requests.length, 0, 'an empty station name never reaches the API');
  assert.ok($('stEditName').classList.contains('invalid'), 'the failed field is marked invalid');
  run(`closeEntryModal('stEditModal');`);
  await settle();
  console.log('ok: Edit prefills, PATCHes the station and re-renders the register (validation first)');
} catch (err) { console.error(err); process.exit(1); }

// ------------------------------------------------ offline edit stays honest ----
try {
  requests.length = 0;
  run(`serverOn=false; openStationEdit('ST-004');`);
  $('stEditName').value = 'Las Anod Field Office';
  $('ste-village').value = 'Laascaanood';
  await run(`saveStationEdit({preventDefault(){},target:document.getElementById('stEditForm')});`);
  await settle();
  assert.equal(requests.length, 0, 'an offline save sends nothing to the API');
  const offline = run(`JSON.stringify((db.stations||[]).find(s=>String(s.id)==='ST-004'))`);
  assert.match(offline, /Las Anod Field Office/, 'the offline draft updates the local register');
  assert.ok(w._lastToast && /offline/i.test(w._lastToast[0] || ''),
    'the officer is told the draft was stored offline rather than synced');
  run(`serverOn=true;`);
  console.log('ok: an offline edit is stored locally and reported as a draft (no silent success)');
} catch (err) { console.error(err); process.exit(1); }

console.log('ALL STATION VIEW / EDIT FRONTEND TESTS PASSED');
