#!/usr/bin/env node
// DOM regressions for the "Audit history" tab inside the record views.
// Install jsdom@26 first:
//
//   npm install --no-save --package-lock-file=false jsdom@26
//   node backend/test_record_audit_ui.mjs
//
// What it proves, running the real page script inside jsdom:
//
//   1. The Person Details modal carries an "Audit history" tab next to the
//      biographic / documents / linked panels, with an event counter.
//   2. Opening a record loads its chronological log: newest first, each event
//      with a readable action label, the acting officer, the badge chip
//      ('Badge #FP-102') and the record it belongs to.
//   3. Creations, updates, approvals and signed-scan uploads all render in the
//      same timeline (the tab is not limited to one event kind).
//   4. Empty and error states are explicit — never a blank panel and never a
//      silent failure.
//   5. Event text is escaped (no markup injection through an audit detail).
//   6. The Station View drawer shows the same trail for the station record.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://sentinel.test', runScripts: 'outside-only' });
const w = dom.window, ctx = dom.getInternalVMContext();
w.HTMLElement.prototype.scrollIntoView = function () {};

const PERSON_ID = 'P-AUD-1';
const events = [
  { id: 9, action: 'APPROVE', action_label: 'Approved', entity: 'clearance_application',
    entity_label: 'Fingerprint clearance application', entity_id: 'FP-9',
    details: 'CL-12345678 by FingerprintUnit', created_at: '2026-10-27 11:00:00',
    badge_number: 'ADM-101', badge_label: 'Badge #ADM-101',
    actor: { id: 1, username: 'admin', display_name: 'Officer A. Hassan',
             role_label: 'System Administrator', badge_number: 'ADM-101',
             badge_label: 'Badge #ADM-101' } },
  { id: 8, action: 'UPLOAD', action_label: 'Uploaded', entity: 'clearance_signed_document',
    entity_label: 'Signed application scan', entity_id: '12',
    details: 'FP-9 · signed-application.pdf', created_at: '2026-10-27 10:30:00',
    badge_number: 'FP-102', badge_label: 'Badge #FP-102',
    actor: { id: 2, username: 'fp.officer', display_name: 'Officer H. Xasan',
             role_label: 'Fingerprint Unit Officer', badge_number: 'FP-102',
             badge_label: 'Badge #FP-102' } },
  { id: 7, action: 'CREATE', action_label: 'Created', entity: 'clearance_application',
    entity_label: 'Fingerprint clearance application', entity_id: 'FP-9',
    details: PERSON_ID, created_at: '2026-10-27 10:00:00',
    badge_number: 'FP-102', badge_label: 'Badge #FP-102',
    actor: { id: 2, username: 'fp.officer', display_name: 'Officer H. Xasan',
             role_label: 'Fingerprint Unit Officer', badge_number: 'FP-102',
             badge_label: 'Badge #FP-102' } },
  { id: 6, action: 'UPDATE', action_label: 'Updated', entity: 'person', entity_id: PERSON_ID,
    entity_label: 'Central Person Registry',
    details: '<img src=x onerror="window.__pwned=1">', created_at: '2026-10-27 09:00:00',
    badge_number: '', badge_label: '#Not recorded',
    actor: { id: 9, username: 'legacy', display_name: 'Legacy Officer',
             role_label: 'CID Criminal Unit Officer', badge_number: '',
             badge_label: '#Not recorded' } },
  { id: 5, action: 'CREATE', action_label: 'Created', entity: 'person', entity_id: PERSON_ID,
    entity_label: 'Central Person Registry', details: '',
    created_at: '2026-10-26 09:00:00', badge_number: 'FP-102',
    badge_label: 'Badge #FP-102',
    actor: { id: 2, username: 'fp.officer', display_name: 'Officer H. Xasan',
             role_label: 'Fingerprint Unit Officer', badge_number: 'FP-102',
             badge_label: 'Badge #FP-102' } },
];

const calls = [];
let auditPayload = {
  entity: 'person', entity_id: PERSON_ID, person_id: PERSON_ID,
  display_name: 'Audit Trail', items: events, total: events.length,
  counts: { person: 2, clearance_application: 2, clearance_signed_document: 1 },
  badge_fallback: '#Not recorded',
  scope_note: 'Every event recorded against this identity and the unit records your role may read, newest first.',
  generated_at: '2026-10-27 12:00:00',
};
let auditFails = false;

w.fetch = async (url, opts = {}) => {
  const path = String(url);
  calls.push({ path, method: (opts.method || 'GET').toUpperCase() });
  const ok = (payload) => ({ ok: true, status: 200, json: async () => payload });
  if (path.endsWith('/audit-history') || path.includes('/api/audit/entity/')) {
    if (auditFails) return { ok: false, status: 403,
      json: async () => ({ error: 'Audit history for this record is restricted to the role that owns the register' }) };
    return ok(auditPayload);
  }
  if (path.endsWith('/documents')) return ok({ total_count: 0, documents: [], scope_note: 'Scoped' });
  if (path.endsWith('/linked-records')) {
    return ok({ residence: 'Laascaanood', proximity_note: 'No live coordinates',
                scope_note: 'Scoped', items: [] });
  }
  return ok({});
};
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/if\(document\.readyState==='loading'\)[\s\S]*$/, '');
vm.runInContext(script, ctx);
const run = (s) => vm.runInContext(s, ctx);
const $ = (id) => w.document.getElementById(id);
const tick = (ms = 60) => new Promise((resolve) => setTimeout(resolve, ms));

run(`serverOn=true; apiToken='test-token';
  sessionUser={id:2,username:'fp.officer',display_name:'Officer H. Xasan',role:'FingerprintUnit',
    role_label:'Fingerprint Unit Officer',badge_number:'FP-102',badge_label:'Badge #FP-102',
    modules:['dashboard','people','fingerprint'],can_write:true,read_only:false};
  currentUser=sessionUser;
  sessionVisibility={is_admin:false,can_manage_users:false};
  db.people=[{id:'${PERSON_ID}',person_id:'${PERSON_ID}',full_name:'Audit Trail',national_id:'NID-AUD',
    date_of_birth:'1990-05-05',phone:'+252 63 555 0199',mother_name:'Hooyo Audit',
    residence:'Laascaanood',occupation:'Trader'}];
  db.officers=[]; toast=()=>{};`);

// ---------------------------------------------------------------------------
// 1) The tab exists next to the other record panels
// ---------------------------------------------------------------------------
try {
  run(`openPersonView('${PERSON_ID}')`);
  await tick();
  const tabs = [...w.document.querySelectorAll('#personDetailModal [data-detail-tab]')]
    .map((b) => b.getAttribute('data-detail-tab'));
  assert.ok(tabs.includes('audit'), 'the record carries an Audit history tab');
  assert.deepEqual(tabs, ['overview', 'documents', 'linked', 'audit'],
    'Audit history sits alongside the existing record tabs');
  assert.ok($('personAuditCount'), 'the tab shows an event counter');
  assert.ok($('personAuditTrail'), 'the tab has its own panel');
  console.log('ok 1: Person Details carries an Audit history tab with a counter');
} catch (err) { console.error(err); process.exit(1); }

// ---------------------------------------------------------------------------
// 2) + 3) The chronological log renders every event kind with attribution
// ---------------------------------------------------------------------------
try {
  await tick();
  const trail = $('personAuditTrail').innerHTML;
  assert.match(trail, /5 recorded events/, 'the header counts the events');
  assert.match(trail, /Badge #FP-102/, 'events are attributed to the acting badge');
  assert.match(trail, /Badge #ADM-101/, 'administrator actions carry their own badge');
  assert.match(trail, /#Not recorded/, 'a badge-less legacy row falls back visibly');
  assert.match(trail, /Officer H\. Xasan/, 'the acting officer is named');
  assert.match(trail, /Fingerprint clearance application/,
    'each event names the record it belongs to');
  for (const label of ['Created', 'Updated', 'Uploaded', 'Approved']) {
    assert.ok(trail.includes(`<b>${label}</b>`), `the "${label}" event renders`);
  }
  // Newest first: the approved certificate appears before the creation.
  assert.ok(trail.indexOf('CL-12345678') < trail.indexOf('signed-application.pdf'),
    'events are newest first (approval before the signed scan)');
  assert.ok(trail.indexOf('signed-application.pdf') < trail.indexOf('2026-10-26'),
    '…and the signed scan before yesterday’s creation');
  assert.ok(trail.includes('audit-timeline'), 'the log is painted as a timeline');
  assert.equal($('personAuditCount').textContent, '5', 'the counter matches the log');

  run("setPersonDetailTab('audit')");
  const panel = w.document.querySelector('#personDetailModal [data-person-detail-panel="audit"]');
  assert.ok(panel.classList.contains('active'), 'the Audit history panel becomes the active tab');
  console.log("ok 2+3: the record log renders creations, updates, uploads and approvals with badges");
} catch (err) { console.error(err); process.exit(1); }

// ---------------------------------------------------------------------------
// 4) Markup in an audit detail is escaped
// ---------------------------------------------------------------------------
try {
  const trail = $('personAuditTrail').innerHTML;
  assert.ok(!/<img/.test(trail), 'an audit detail can never inject markup');
  assert.match(trail, /&lt;img/, 'the raw text is escaped and still readable');
  assert.equal(run('window.__pwned'), undefined, 'no script from an audit row executes');
  console.log('ok 4: audit details are escaped');
} catch (err) { console.error(err); process.exit(1); }

// ---------------------------------------------------------------------------
// 5) Empty + error states are explicit
// ---------------------------------------------------------------------------
try {
  auditPayload = { ...auditPayload, items: [], total: 0, counts: {} };
  await run(`loadRecordAuditHistory('${PERSON_ID}','person')`);
  await tick();
  assert.match($('personAuditTrail').innerHTML, /No audit history yet/,
    'an empty log says so instead of showing a blank panel');
  assert.equal($('personAuditCount').textContent, '0', 'the counter reads zero');

  auditFails = true;
  await run(`loadRecordAuditHistory('${PERSON_ID}','person')`);
  await tick();
  assert.match($('personAuditTrail').innerHTML, /Audit history unavailable/,
    'a refused read is reported, not swallowed');
  assert.match($('personAuditTrail').innerHTML, /restricted to the role/,
    'the reason from the API is shown');
  auditFails = false;
  console.log('ok 5: empty and refused logs are explicit');
} catch (err) { console.error(err); process.exit(1); }

// ---------------------------------------------------------------------------
// 6) The station drawer shows the same trail for the station record
// ---------------------------------------------------------------------------
try {
  auditPayload = { ...auditPayload, entity: 'police_station', entity_id: 'ST-004',
                   entity_label: 'Police station', items: events, total: events.length };
  calls.length = 0;
  run(`paintStationView({id:'ST-004',station_id:'ST-004',name:'Las Anod Station',code:'SOO-C-01',
        region:'Sool',district:'Laascaanood',village:'Laascaanood',station_tier:'Regional HQ',
        operational_status:'Active'},null,{officers:[],vehicles:[]})`);
  await tick();
  assert.ok(calls.some((c) => c.path === '/api/audit/entity/police_station/ST-004'),
    'the station drawer asks for the station record history');
  const trail = $('stationAuditTrail').innerHTML;
  assert.match(trail, /Badge #FP-102/, 'the station log carries badge attribution');
  assert.match(trail, /audit-timeline/, 'the station log uses the same timeline');
  console.log('ok 6: the Station View drawer renders the same audit history');
} catch (err) { console.error(err); process.exit(1); }

// ---------------------------------------------------------------------------
// 7) The officer (Police Registration) record uses the generic endpoint
// ---------------------------------------------------------------------------
try {
  calls.length = 0;
  auditPayload = { ...auditPayload, entity: 'officer', entity_id: 'POL-2026-0001',
                   entity_label: 'Police Registration record', items: events,
                   total: events.length };
  run(`db.officers=[{service_id:'POL-2026-0001',full_name:'Officer A. Probe',rank:'Constable',
        unit:'General Patrol',photo_path:''}];openOfficerView('POL-2026-0001');`);
  await tick();
  assert.ok(calls.some((c) => c.path === '/api/audit/entity/officer/POL-2026-0001'),
    'the Police Registration record reads its history from the generic endpoint');
  assert.ok($('personAuditTrail').innerHTML.includes('Badge #FP-102'),
    'the officer record history renders with badges');
  console.log('ok 7: Police Registration records share the same audit history');
} catch (err) { console.error(err); process.exit(1); }

console.log('ALL RECORD AUDIT HISTORY UI TESTS PASSED');
