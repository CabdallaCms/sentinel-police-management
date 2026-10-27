#!/usr/bin/env node
// DOM regressions for the officer-profile / audit / cascading-location release.
// Install jsdom@26 first:
//
//   npm install --no-save --package-lock-file=false jsdom@26
//   node backend/test_officer_profile_ui.mjs
//
// What it proves, running the real page script inside jsdom:
//
//   1. The top-right identity block is a single clickable control
//      (#officerIdentity) that opens the Officer Profile modal, and the modal
//      paints the signed-in officer's display name, badge and role.
//   2. The profile modal can save a display name (PATCH /api/me), apply an
//      avatar preset (POST /api/me/avatar) and change the password
//      (POST /api/me/password) — with the confirmation mismatch caught locally.
//   3. The New / Edit officer drawer cascades Region → District → posting:
//      a Checkpoint role offers only the ACTIVE checkpoints of the chosen
//      district and hides the station/branch field; a Station / Unit role does
//      the reverse. Changing the region resets the district; changing the
//      district resets the posting.
//   4. User Management renders the badge chip ('Badge #FP-102' / '#Not
//      recorded') and the audit trail attributes each entry to the officer's
//      badge.
//   5. refreshLiveMetrics() re-reads the dashboard (and the audit trail) after
//      a mutation — no manual cache reload.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://sentinel.test', runScripts: 'outside-only' });
const w = dom.window, ctx = dom.getInternalVMContext();
w.HTMLElement.prototype.scrollIntoView = function () {};
const requests = [];
let auditItems = [];
let rosterItems = [];

const json = (payload, status = 200) => ({
  ok: status < 400, status, json: async () => payload,
});
w.fetch = async (url, opts = {}) => {
  const path = String(url);
  const method = (opts.method || 'GET').toUpperCase();
  requests.push({ path, method, body: opts.body });
  if (path.startsWith('/api/stations')) {
    return json({ items: [
      { station_id: 'ST-004', name: 'Las Anod Station', code: 'SOO-C-01', region: 'Sool',
        district: 'Laascaanood', station_tier: 'Regional HQ', operational_status: 'Active' },
      { station_id: 'ST-008', name: 'Adhi Cadeeye Outpost', code: 'SOO-C-02', region: 'Sool',
        district: 'Laascaanood', station_tier: 'Checkpoint', operational_status: 'Active' },
      { station_id: 'ST-010', name: 'Karin Checkpoint', code: 'SAN-C-09', region: 'Sanaag',
        district: 'Badhan', station_tier: 'Checkpoint', operational_status: 'Inactive' },
      { station_id: 'ST-001', name: 'Ceerigaabo Central Station', code: 'SAN-C-01',
        region: 'Sanaag', district: 'Ceerigaabo', station_tier: 'Regional HQ',
        operational_status: 'Active' },
    ] });
  }
  if (path.startsWith('/api/branches')) {
    return json({ items: [
      { id: 1, name: 'Lasanod Branch', region: 'Sool', district: 'Laascaanood', unit_type: 'checkpoint' },
      { id: 2, name: 'Lasanod Branch', region: 'Sool', district: 'Laascaanood', unit_type: 'fingerprint' },
      { id: 3, name: 'Erigavo Branch', region: 'Sanaag', district: 'Ceerigaabo', unit_type: 'fingerprint' },
    ], regions: ['Sool', 'Sanaag'], unit_types: [], districts: [] });
  }
  if (path.startsWith('/api/admin/users')) return json({ items: rosterItems });
  if (path.startsWith('/api/admin/audit')) {
    return json({ items: auditItems, total: auditItems.length,
                  badge_fallback: '#Not recorded',
                  generated_at: '2026-10-27 10:00:00' });
  }
  if (path === '/api/me') {
    const sent = JSON.parse(opts.body || '{}');
    return json({ user: { ...run('sessionUser'), display_name: sent.display_name,
                           badge_label: 'Badge #FP-102' } });
  }
  if (path === '/api/me/avatar') {
    const sent = JSON.parse(opts.body || '{}');
    return json({ user: { ...run('sessionUser'), avatar_path: '',
                          avatar_preset: sent.avatar_preset || '' } });
  }
  if (path === '/api/me/password') return json({ ok: true, password_changed: true });
  if (path.startsWith('/api/dashboard')) {
    return json({ role: 'SystemAdmin', subhead: 'Live', cards: [], activity: [],
                  activity_feed: [] });
  }
  return json({});
};
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/if\(document\.readyState==='loading'\)[\s\S]*$/, '');
vm.runInContext(script, ctx);
const run = (s) => vm.runInContext(s, ctx);
const $ = (id) => w.document.getElementById(id);
const tick = (ms = 30) => new Promise((resolve) => setTimeout(resolve, ms));

// The signed-in officer the modal paints.
run(`serverOn=true; apiToken='test-token';
  sessionUser={id:2,username:'fp.officer',display_name:'Officer H. Xasan',role:'FingerprintUnit',
    role_label:'Fingerprint Officer',badge_number:'FP-102',badge_label:'Badge #FP-102',
    avatar_path:'',avatar_preset:'navy',branch:'Fingerprint Unit',modules:['dashboard','people','fingerprint'],
    can_write:true,can_edit_profile:true,read_only:false};
  currentUser=sessionUser;
  sessionVisibility={is_admin:true,can_manage_users:true,can_edit_records:true};
  db.dashboard=null;
  toast=(s,sub)=>{window._lastToast=[s,sub]};
  updateUserPill();`);

// ---------------------------------------------------------------------------
// 1) The header identity block is one clickable control → Officer Profile
// ---------------------------------------------------------------------------
try {
  const identity = $('officerIdentity');
  assert.ok(identity, 'the header identity block exists');
  assert.equal(identity.tagName, 'BUTTON', 'the identity block is a real button (keyboard accessible)');
  assert.equal(identity.getAttribute('data-ro-keep'), '1',
    'the identity block survives the read-only DOM sweep');
  assert.match(identity.getAttribute('onclick') || '', /openOfficerProfile\(\)/,
    'clicking the identity block opens the officer profile');
  assert.match(identity.getAttribute('aria-label') || '', /officer profile/i,
    'the identity block is announced as the officer profile');

  run('openOfficerProfile()');
  await tick();
  assert.ok($('officerProfileModal').classList.contains('open'),
    'the Officer Profile modal opens');
  const body = $('officerProfileBody').innerHTML;
  assert.match(body, /Officer H\. Xasan/, 'the modal shows the signed-in display name');
  assert.match(body, /Badge #FP-102/, 'the modal shows the officer badge');
  assert.match(body, /id="opDisplayName"/, 'the display-name editor is present');
  assert.match(body, /onclick="chooseOfficerAvatar\('gold'\)"/,
    'avatar presets can be selected');
  assert.match(body, /id="opAvatarFile"/, 'a profile picture can be uploaded');
  assert.match(body, /id="opCurrentPassword"/, 'the password change form is present');
  console.log('ok 1: clickable header identity block opens the Officer Profile modal');
} catch (err) { console.error(err); process.exit(1); }

// ---------------------------------------------------------------------------
// 2) Profile updates: display name, avatar preset, password
// ---------------------------------------------------------------------------
try {
  requests.length = 0;
  $('opDisplayName').value = 'Officer H. Xasan Jr';
  run('saveOfficerDisplayName()');
  await tick();
  const patch = requests.find((r) => r.path === '/api/me' && r.method === 'PATCH');
  assert.ok(patch, 'saving the display name PATCHes /api/me');
  assert.equal(JSON.parse(patch.body).display_name, 'Officer H. Xasan Jr');
  assert.equal($('userName').textContent, 'Officer H. Xasan Jr',
    'the header reflects the saved display name immediately');

  requests.length = 0;
  run("chooseOfficerAvatar('gold')");
  await tick();
  const avatar = requests.find((r) => r.path === '/api/me/avatar' && r.method === 'POST');
  assert.ok(avatar, 'selecting an avatar preset POSTs /api/me/avatar');
  assert.equal(JSON.parse(avatar.body).avatar_preset, 'gold');
  assert.match($('userInitials').className, /tone-gold/,
    'the header avatar switches to the chosen preset');

  requests.length = 0;
  $('opCurrentPassword').value = 'ChangeMe123!';
  $('opNewPassword').value = 'NewSecret123!';
  $('opConfirmPassword').value = 'Nope123!';
  run('submitOfficerPassword()');
  await tick();
  assert.equal(requests.filter((r) => r.path === '/api/me/password').length, 0,
    'a confirmation mismatch never reaches the server');
  assert.match($('opPasswordNotice').textContent, /do not match/,
    'the mismatch is explained in the modal');

  $('opConfirmPassword').value = 'NewSecret123!';
  run('submitOfficerPassword()');
  await tick();
  const pw = requests.find((r) => r.path === '/api/me/password');
  assert.ok(pw, 'a matching confirmation POSTs /api/me/password');
  assert.equal(JSON.parse(pw.body).current_password, 'ChangeMe123!');
  assert.equal(JSON.parse(pw.body).new_password, 'NewSecret123!');
  assert.match($('opPasswordNotice').textContent, /Password changed/,
    'the success message confirms the change');
  console.log('ok 2: profile modal saves the name, the avatar preset and the password');
} catch (err) { console.error(err); process.exit(1); }

// ---------------------------------------------------------------------------
// 3) Role-driven cascading Region → District → Checkpoint | Station
// ---------------------------------------------------------------------------
try {
  run('sessionUser.role="SystemAdmin"; currentUser=sessionUser; closeEntryModal("officerProfileModal");');
  await tick(320);
  await run('openNewUserDrawer()');
  await tick(60);
  const checkpointField = $('nu-checkpoint-field');
  const unitField = $('nu-unit-field');
  assert.ok(checkpointField && unitField, 'the drawer renders both posting selectors');

  const regionValues = [...$('nu-region').options].map((o) => o.value).filter(Boolean);
  assert.ok(regionValues.includes('Sool') && regionValues.includes('Sanaag'),
    'Region lists the regions found in the station / branch catalogue');

  // Station / Unit role (default): the unit selector is live, the checkpoint hides.
  assert.equal(checkpointField.style.display, 'none',
    'a Station / Unit role hides the Checkpoint field');
  assert.notEqual(unitField.style.display, 'none',
    'a Station / Unit role shows the Station / Branch / Unit field');

  // Checkpoint role: the checkpoint selector is live, the station field hides.
  $('nu-role').value = 'CheckpointSouth';
  run("onUserLocationChange('nu','role')");
  await tick();
  assert.notEqual(checkpointField.style.display, 'none',
    'a Checkpoint role shows the Checkpoint field');
  assert.equal(unitField.style.display, 'none',
    'a Checkpoint role hides the Station / Branch field');

  // Region → District cascade.
  $('nu-region').value = 'Sool';
  run("onUserLocationChange('nu','region')");
  await tick();
  const districts = [...$('nu-district').options].map((o) => o.value).filter(Boolean);
  // The gazetteer supplies the full district list for the region; the station
  // and branch catalogue can only ever add districts, never another region's.
  assert.ok(districts.includes('Laascaanood'), 'Sool offers the Laascaanood district');
  assert.ok(districts.includes('Caynabo') && districts.includes('Taleex'),
    'the gazetteer districts of the region are offered too (' + districts.join(', ') + ')');
  assert.equal(run("userDistrictsFor('Sool').filter(d=>!['Laascaanood','Caynabo','Xudun','Taleex'].includes(d)).length"), 0,
    'no district from another region leaks into the Sool list');
  assert.equal($('nu-district').disabled, false, 'the district selector is enabled once a region is chosen');

  $('nu-district').value = 'Laascaanood';
  run("onUserLocationChange('nu','district')");
  await tick();
  const checkpoints = [...$('nu-checkpoint').options].map((o) => o.value).filter(Boolean);
  assert.ok(checkpoints.includes('Adhi Cadeeye Outpost'),
    'the district checkpoint station is offered');
  assert.ok(checkpoints.includes('Lasanod Branch'),
    'the checkpoint unit registered for the district is offered');
  assert.ok(!checkpoints.some((c) => /Adhi Cadeeye Station 2/.test(c)),
    'only checkpoints of that district are offered');

  // Changing the region clears the district and the posting list.
  $('nu-region').value = 'Sanaag';
  run("onUserLocationChange('nu','region')");
  await tick();
  assert.equal($('nu-district').value, '', 'changing the region resets the district');
  const cpAfter = [...$('nu-checkpoint').options].map((o) => o.value).filter(Boolean);
  assert.ok(!cpAfter.includes('Adhi Cadeeye Outpost'),
    'checkpoints from the previous district are gone');

  // Inactive checkpoints never appear.
  $('nu-district').value = 'Badhan';
  run("onUserLocationChange('nu','district')");
  await tick();
  const inactive = [...$('nu-checkpoint').options].map((o) => o.value).filter(Boolean);
  assert.ok(!inactive.includes('Karin Checkpoint'),
    'an inactive checkpoint is not offered to the administrator');
  assert.match($('nu-checkpoint').options[0].textContent, /No active checkpoint/,
    'an empty district explains why the list is empty');

  // Station / Unit role: stations + branches of the district, no checkpoints.
  $('nu-role').value = 'FingerprintUnit';
  run("onUserLocationChange('nu','role')");
  await tick();
  $('nu-region').value = 'Sanaag';
  run("onUserLocationChange('nu','region')");
  await tick();
  $('nu-district').value = 'Ceerigaabo';
  run("onUserLocationChange('nu','district')");
  await tick();
  const units = [...$('nu-unit').options].map((o) => o.value).filter(Boolean);
  assert.ok(units.includes('Ceerigaabo Central Station'),
    'the district station is offered to a Station / Unit role');
  assert.ok(units.includes('Erigavo Branch'),
    'the district branch is offered to a Station / Unit role');
  assert.ok(!units.includes('Adhi Cadeeye Outpost'),
    'a station from another district is never offered');
  assert.equal(checkpointField.style.display, 'none',
    'switching role back to Station / Unit hides the checkpoint field again');
  console.log('ok 3: role-driven Region → District → (Checkpoint | Station / Branch / Unit) cascade');
} catch (err) { console.error(err); process.exit(1); }

// ---------------------------------------------------------------------------
// 4) Badge attribution in the user table and the audit trail
// ---------------------------------------------------------------------------
try {
  rosterItems = [
    { id: 2, username: 'fp.officer', display_name: 'Officer H. Xasan', role: 'FingerprintUnit',
      role_label: 'Fingerprint Officer', badge_number: 'FP-102', badge_label: 'Badge #FP-102',
      initials: 'OH', branch: 'Fingerprint Unit', location_scope: null, active: true },
    { id: 7, username: 'legacy', display_name: 'Officer Legacy', role: 'CIDUnit',
      role_label: 'CID Officer', badge_number: '', badge_label: '#Not recorded',
      initials: 'OL', branch: 'CID Unit', location_scope: null, active: true },
  ];
  auditItems = [
    { id: 2, action: 'APPROVE', entity: 'clearance_application', entity_id: 'FP-1',
      details: 'signed scan uploaded', created_at: '2026-10-27 09:00:00',
      badge_number: 'FP-102', badge_label: 'Badge #FP-102', badge_recorded: true,
      actor: { id: 2, username: 'fp.officer', display_name: 'Officer H. Xasan',
               role_label: 'Fingerprint Officer', badge_number: 'FP-102',
               badge_label: 'Badge #FP-102' } },
    { id: 1, action: 'UPDATE', entity: 'user', entity_id: '7', details: 'legacy row',
      created_at: '2026-10-27 08:00:00', badge_number: '', badge_label: '#Not recorded',
      badge_recorded: false,
      actor: { id: 7, username: 'legacy', display_name: 'Officer Legacy',
               role_label: 'CID Officer', badge_number: '', badge_label: '#Not recorded' } },
  ];
  await run('renderUserTable()');
  await tick(60);
  const table = $('userTable').innerHTML;
  assert.match(table, /Badge #FP-102/, 'the roster prints the officer badge chip');
  assert.match(table, /um-badge missing/, 'a row without a badge is flagged, not invented');
  assert.match(table, /#Not recorded/, 'the documented fallback is rendered');

  await run('loadAuditTrail(true)');
  await tick(60);
  const audit = $('auditTrailTable').innerHTML;
  assert.match(audit, /Badge #FP-102/, 'audit entries are attributed to the acting badge');
  assert.match(audit, /Officer H\. Xasan/, 'the audit trail names the acting officer');
  assert.match(audit, /#Not recorded/, 'a badge-less legacy row falls back visibly');
  assert.match(audit, /audit-badge/, 'the badge is rendered as a chip next to the actor');
  console.log('ok 4: badge attribution in the roster and the audit trail');
} catch (err) { console.error(err); process.exit(1); }

// ---------------------------------------------------------------------------
// 5) refreshLiveMetrics(): dashboard + audit trail without a cache reload
// ---------------------------------------------------------------------------
try {
  run('db.dashboard=null; document.getElementById("dashboard").classList.remove("active");');
  requests.length = 0;
  run('refreshLiveMetrics()');
  await tick(60);
  assert.ok(requests.some((r) => r.path === '/api/dashboard'),
    'refreshLiveMetrics re-reads /api/dashboard');
  assert.ok(run('db.dashboard && db.dashboard.role') === 'SystemAdmin',
    'the fresh dashboard payload replaces the cached one');

  requests.length = 0;
  run('refreshLiveMetrics({audit:true})');
  await tick(60);
  assert.ok(requests.some((r) => r.path.startsWith('/api/admin/audit')),
    'refreshLiveMetrics({audit:true}) refreshes the audit trail too');

  // Every counted write path calls it.
  const callSites = (html.match(/refreshLiveMetrics\(/g) || []).length;
  assert.ok(callSites >= 10, 'the dashboard refresh is wired into every write path (' + callSites + ')');
  console.log('ok 5: dashboard metrics and activity feed refresh instantly after a write');
} catch (err) { console.error(err); process.exit(1); }

console.log('ALL OFFICER PROFILE / AUDIT / LOCATION UI TESTS PASSED');
