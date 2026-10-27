#!/usr/bin/env node
// JSDOM regressions for Branch Management full CRUD — Edit / Deactivate and the
// legacy "Unassigned district" cleanup — plus the real-time sidebar movement.
//
//   npm install --no-save --package-lock-file=false jsdom@26
//   node backend/test_branch_management_ui.mjs
//
// What it proves, in the real page script running inside jsdom:
//
//   1. The Branch Management table paints an Actions column: every row gets an
//      EDIT button and an Activate / Deactivate toggle, both inside the
//      `.admin-edit` SystemAdmin-only hide rule, and the Status column reports
//      Active / Inactive.
//   2. Actions → Edit opens the Edit Branch modal prefilled from the catalogue
//      (name, Region, District, Unit Department, Status), and Save PATCHes
//      `/api/admin/branches/<id>` with exactly the edited fields.
//   3. A saved Region → District change re-places the unit in the sidebar tree
//      IN REAL TIME: the unit leaves the "Unassigned district" accordion and
//      appears under Sool → Laascaanood without a reload.
//   4. Deactivate PATCHes `{active:false}`, the row turns Inactive and the unit
//      disappears from the sidebar tree / intake dropdown — while the branch
//      stays in the catalogue (records and postings keep their link).
//   5. The legacy cleanup tool lists every unplaced row, batch-assigns the
//      selection through `POST /api/admin/branches/bulk-assign` and the queue
//      empties as the units move into the gazetteer tree.
//   6. A non-admin session cannot open the Edit modal (the server answers 403;
//      the client refuses before the request leaves the browser).
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://sentinel.test', runScripts: 'outside-only' });
const w = dom.window;
const ctx = dom.getInternalVMContext();
w.HTMLElement.prototype.scrollIntoView = function () {};

const GAZETTEER = {
  Sool: ['Laascaanood', 'Caynabo', 'Xudun', 'Taleex'],
  Sanaag: ['Ceerigaabo', 'Ceel Afweyn', 'Garadag', 'Badhan', 'Dhahar'],
  'East Togdheer': ['Burao', 'Oodweyne', 'Buuhoodle'],
};
function legacyReason(row) {
  const placeholders = ['', 'unassigned', 'unassigned region', 'unassigned district',
    'checkpoint areas', 'none', 'n/a', '-', 'unknown'];
  const region = String(row.region || '').trim();
  const district = String(row.district || '').trim();
  if (placeholders.includes(region.toLowerCase())) return 'No region assigned';
  if (placeholders.includes(district.toLowerCase())) return 'No district assigned';
  if (GAZETTEER[region]) {
    return GAZETTEER[region].includes(district)
      ? null : 'District "' + district + '" is not part of ' + region;
  }
  if (district.toLowerCase() === region.toLowerCase()) return 'No district assigned';
  return 'Region "' + region + '" is outside the gazetteer';
}
const state = {
  branches: [
    { id: 1, name: 'Lasanod Branch', region: 'Sool', district: 'Laascaanood', unit_type: 'fingerprint', active: true },
    { id: 2, name: 'East Checkpoint', region: 'Sool', district: '', unit_type: 'checkpoint', active: true },
    { id: 3, name: 'South Checkpoint', region: 'Sool', district: '', unit_type: 'checkpoint', active: true },
    { id: 4, name: 'West Checkpoint', region: 'East', district: '', unit_type: 'checkpoint', active: true },
    { id: 5, name: 'Erigavo Branch', region: 'Sanaag', district: 'Ceerigaabo', unit_type: 'airport', active: true },
  ],
  requests: [],
};
function decorate(row) {
  const active = row.active !== false;
  return {
    ...row,
    active,
    status: active ? 'Active' : 'Inactive',
    unit_label: ({ fingerprint: 'Fingerprint Unit', crime: 'Crime Unit', checkpoint: 'Checkpoint Unit', airport: 'Airport Unit', police_station: 'Police Stations' })[row.unit_type] || row.unit_type,
    legacy_reason: row.legacy_reason !== undefined ? row.legacy_reason : legacyReason(row),
  };
}
function counts() {
  const items = state.branches;
  return {
    total: items.length,
    active: items.filter((b) => b.active !== false).length,
    inactive: items.filter((b) => b.active === false).length,
    unassigned: items.filter((b) => legacyReason(b)).length,
  };
}
function adminPayload() {
  const items = state.branches.map(decorate);
  return {
    items,
    unassigned: items.filter((b) => b.legacy_reason),
    regions: [...new Set(items.map((b) => b.region))],
    districts: [...new Set(items.map((b) => b.district).filter(Boolean))],
    gazetteer: GAZETTEER,
    gazetteer_regions: Object.keys(GAZETTEER),
    unit_types: ['fingerprint', 'crime', 'checkpoint', 'airport', 'police_station'],
    counts: counts(),
  };
}
function publicPayload() {
  const items = state.branches.map(decorate);
  return { items, regions: [...new Set(items.map((b) => b.region))],
    districts: [...new Set(items.map((b) => b.district).filter(Boolean))],
    unit_types: ['fingerprint', 'crime', 'checkpoint', 'airport', 'police_station'] };
}
const reply = (status, data) => ({ ok: status < 400, status, json: async () => data });
w.fetch = async (url, opts = {}) => {
  const path = String(url);
  const method = (opts.method || 'GET').toUpperCase();
  let body = null;
  try { body = opts.body ? JSON.parse(opts.body) : null; } catch (_) { body = null; }
  state.requests.push({ path, method, body });
  const member = path.match(/^\/api\/(?:admin\/)?branches\/(\d+)$/);
  if (member && method === 'PATCH') {
    const id = Number(member[1]);
    const row = state.branches.find((b) => b.id === id);
    if (!row) return reply(404, { error: 'Branch "' + id + '" does not exist' });
    const changed = [];
    for (const key of ['name', 'region', 'district', 'unit_type', 'active']) {
      if (!(key in body)) continue;
      const value = key === 'active' ? body.active !== false : String(body[key]);
      if (row[key] !== value) { row[key] = value; changed.push(key); }
    }
    row.legacy_reason = legacyReason(row);
    return reply(200, { branch: decorate(row), updated: true, changed_fields: changed,
      relabelled_postings: 0, counts: counts(),
      catalogue: state.branches.map(decorate) });
  }
  if (method === 'POST' && path === '/api/admin/branches/bulk-assign') {
    const ids = (body.ids || []).map(Number);
    const updated = [];
    for (const id of ids) {
      const row = state.branches.find((b) => b.id === id);
      if (!row) continue;
      row.region = body.region;
      row.district = body.district;
      row.legacy_reason = legacyReason(row);
      updated.push(decorate(row));
    }
    return reply(200, { ok: true, updated, skipped: [], region: body.region,
      district: body.district, counts: counts() });
  }
  if (path.startsWith('/api/admin/branches')) return reply(200, adminPayload());
  if (path.startsWith('/api/branches')) return reply(200, publicPayload());
  return reply(200, {});
};

const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/if\(document\.readyState==='loading'\)[\s\S]*$/, '');
vm.runInContext(script, ctx);
const run = (source) => vm.runInContext(source, ctx);
const tick = (ms = 60) => new Promise((resolve) => setTimeout(resolve, ms));
const $ = (id) => w.document.getElementById(id);
const queryAll = (sel) => [...w.document.querySelectorAll(sel)];
const rowFor = (name) => queryAll('#branchTable tr')
  .find((tr) => (tr.textContent || '').includes(name));
const rowButton = (name, label) => rowFor(name) ? [...rowFor(name).querySelectorAll('button')]
  .find((b) => (b.textContent || '').trim() === label) : undefined;
const tree = (type) => w.document.querySelector('#nav [data-nav-regions="' + type + '"]');
function treeRegion(type, region) {
  const mount = tree(type);
  return mount ? mount.querySelector('.nav-region[data-nav-region="' + region + '"]') : null;
}
function districtOf(type, region, district) {
  const r = treeRegion(type, region);
  return r ? r.querySelector('.nav-district[data-nav-district="' + district + '"]') : null;
}
function unitLabels(type) {
  const mount = tree(type);
  return mount ? [...mount.querySelectorAll('.nav-unit')].map((b) => b.dataset.unitLabel) : [];
}

run(`persist=()=>{}; toast=(s,sub)=>{window._lastToast=[s,sub]};
  refreshLiveMetrics=()=>{}; guardReadOnly=()=>false; serverOn=true; apiToken='test-token';
  db.checkpoints=[]; db.stations=[]; db.fingerprint=[]; db.airport=[]; db.cases=[];
  sessionRoster=null;`);

const ALL_MODULES = ['dashboard', 'people', 'fingerprint', 'airport', 'cid', 'checkpoints',
  'policesearch', 'admin', 'stations', 'crimes', 'officers', 'conduct', 'cars',
  'executive', 'oversight'];
function signIn(role, modules, isAdmin) {
  const user = { role, modules, display_name: 'Test Officer', role_label: role };
  run(`sessionUser=${JSON.stringify(user)};
    currentUser=sessionUser;
    sessionVisibility={is_admin:${isAdmin},can_manage_users:${isAdmin},
      can_manage_records:${isAdmin},can_manage_stations:${isAdmin},can_edit_records:${isAdmin}};
    applyNavForRole(); updateUserPill(); applyRecordEditMode();
    branchCatalog={loaded:false,items:[],regions:[],unit_types:[],districts:[]};
    renderUnitNavTrees();`);
}

// ---------------------------------------------------------------- markup ----
try {
  const branchSection = html.split('<section id="branches" class="page">')[1];
  const header = branchSection.split('<tbody id="branchTable">')[0];
  assert.ok(/<th>Actions<\/th>/.test(header), 'the Branch Management table has an Actions column');
  assert.ok(header.lastIndexOf('<th>Actions</th>') > header.lastIndexOf('<th>Unit Department</th>'),
    'Actions is the last column of the Branch Management header');
  assert.ok(/<th>Status<\/th>/.test(header), 'the table reports the Active / Inactive status');
  assert.ok(/id="branchEditModal"/.test(html) && /id="branchEditForm"/.test(html),
    'the Edit Branch modal markup exists');
  assert.ok(/id="branchEditActive"/.test(html), 'the modal carries the Active / Inactive toggle');
  assert.ok(/id="branchLegacyPanel"/.test(html) && /id="branchLegacyTable"/.test(html),
    'the legacy placement cleanup tool exists');
  assert.ok(/data-branch-action="bulk-assign"/.test(html), 'the cleanup tool has a batch assign action');
  assert.ok(/body:not\(\.can-edit-records\) \.admin-edit\{display:none !important\}/.test(html),
    'the Edit / toggle controls are hidden for every non-admin session by CSS');
  assert.ok(/\?v=e7c41b90/.test(html), 'the asset version stamp was republished');
  console.log('ok: Actions column + Edit modal + Active toggle + legacy cleanup markup');
} catch (err) { console.error(err); process.exit(1); }

// ------------------------------------------------ admin: table + modal ----
try {
  signIn('SystemAdmin', ALL_MODULES, true);
  const catalog = await run('refreshBranchManagement(true)');
  await tick();
  assert.equal(catalog, true, 'the administration catalogue loads');
  assert.equal(queryAll('#branchTable tr').length, state.branches.length,
    'every branch (active and inactive) is listed for the administrator');
  const editButton = rowButton('East Checkpoint', 'Edit');
  assert.ok(editButton, 'every row exposes an Edit button');
  assert.ok(editButton.classList.contains('admin-edit'),
    'the Edit button carries the .admin-edit (SystemAdmin-only) class');
  assert.equal(editButton.dataset.branchAction, 'edit');
  assert.equal(rowButton('Lasanod Branch', 'Deactivate').dataset.branchAction, 'toggle');
  assert.ok(/Active/.test(rowFor('Lasanod Branch').textContent), 'the Status column prints Active');

  // The legacy cleanup tool lists the rows that land under "Unassigned district".
  assert.notEqual($('branchLegacyPanel').style.display, 'none',
    'the legacy cleanup panel is visible while unplaced rows exist');
  assert.equal($('branchLegacyCount').textContent, '3',
    'the cleanup panel counts every unplaced branch');
  const legacyChecks = queryAll('#branchLegacyTable .branch-legacy-check');
  assert.equal(legacyChecks.length, 3);
  assert.ok(!legacyChecks.some((cb) => cb.value === '1'),
    'a properly placed branch is not offered for cleanup');

  // The sidebar tree paints the legacy checkpoint under "Unassigned district".
  assert.ok(treeRegion('checkpoint', 'Sool'), 'the sidebar has a Sool checkpoint accordion');
  assert.ok(districtOf('checkpoint', 'Sool', 'Unassigned district'),
    'the bare East / South Checkpoint rows sit under Unassigned district');
  assert.ok(unitLabels('checkpoint').includes('East Checkpoint'));

  run("openBranchEdit('2')");
  await tick(30);
  assert.ok($('branchEditModal').classList.contains('open'), 'Actions → Edit opens the modal');
  assert.equal($('branchEditId').value, '2');
  assert.equal($('branchEditName').value, 'East Checkpoint', 'the modal prefills the branch name');
  assert.equal($('branchEditRegion').value, 'Sool', 'the modal prefills the region');
  assert.equal($('branchEditUnitType').value, 'checkpoint', 'the modal prefills the department');
  assert.equal($('branchEditActive').value, '1', 'the modal prefills the Active status');
  assert.ok([...$('branchEditRegion').options].some((o) => o.value === 'Sanaag'),
    'the Region select offers the gazetteer regions');
  console.log('ok: Actions → Edit opens a prefilled Edit Branch modal');
} catch (err) { console.error(err); process.exit(1); }

// ------------------------------------- edit: rename + re-place in the tree ----
try {
  const before = state.requests.length;
  $('branchEditName').value = 'East Lasanod Checkpoint';
  $('branchEditRegion').value = 'Sool';
  run('populateBranchEditDistrictSelect()');
  $('branchEditDistrict').value = 'Laascaanood';
  $('branchEditUnitType').value = 'checkpoint';
  $('branchEditActive').value = '1';
  await run('saveBranchEdit({preventDefault(){}})');
  await tick();

  const patches = state.requests.slice(before).filter((r) => r.method === 'PATCH');
  assert.equal(patches.length, 1, 'Save sends exactly one PATCH');
  assert.equal(patches[0].path, '/api/admin/branches/2',
    'the PATCH targets PATCH /api/admin/branches/<id>');
  assert.deepEqual(patches[0].body, {
    name: 'East Lasanod Checkpoint', region: 'Sool', district: 'Laascaanood',
    unit_type: 'checkpoint', active: true });

  await tick(300);                                   // the modal close animation
  assert.ok(!$('branchEditModal').classList.contains('open'), 'the modal closes on success');

  // REAL-TIME SIDEBAR MOVEMENT (no reload): the unit left Unassigned district
  // and now sits under Sool → Laascaanood.
  const labels = unitLabels('checkpoint');
  assert.ok(labels.includes('East Lasanod Checkpoint'), 'the renamed unit is in the sidebar tree');
  assert.ok(!labels.includes('East Checkpoint'), 'the old label is gone');
  const placed = districtOf('checkpoint', 'Sool', 'Laascaanood');
  assert.ok(placed, 'the unit moved into Sool → Laascaanood');
  assert.ok([...placed.querySelectorAll('.nav-unit')]
    .some((b) => b.dataset.unitLabel === 'East Lasanod Checkpoint'),
    'the moved unit is inside the Laascaanood accordion');
  const unassigned = districtOf('checkpoint', 'Sool', 'Unassigned district');
  if (unassigned) {
    assert.ok(![...unassigned.querySelectorAll('.nav-unit')]
      .some((b) => b.dataset.unitLabel === 'East Lasanod Checkpoint'),
      'the renamed unit left the Unassigned district group');
  }
  assert.equal($('branchEditId').value, '', 'the edit form is reset after a save');
  console.log('ok: Edit renames + re-places the branch and the sidebar tree moves in real time');
} catch (err) { console.error(err); process.exit(1); }

// ------------------------------------------- toggle Active / Inactive -------
try {
  const before = state.requests.length;
  await run("toggleBranchActive('5', false)");
  await tick();
  const patches = state.requests.slice(before).filter((r) => r.method === 'PATCH');
  assert.equal(patches.length, 1);
  assert.deepEqual(patches[0].body, { active: false }, 'Deactivate PATCHes {active:false}');
  assert.ok(!rowFor('Erigavo Branch') || /Inactive/.test(rowFor('Erigavo Branch').textContent),
    'the row turns Inactive');
  assert.ok(unitLabels('airport').indexOf('Erigavo Branch') === -1,
    'a deactivated branch leaves the sidebar tree');
  assert.ok(state.branches.some((b) => b.name === 'Erigavo Branch'),
    'the branch row is kept — records and officer postings keep their link');

  await run("toggleBranchActive('5', true)");
  await tick();
  assert.ok(/Active/.test(rowFor('Erigavo Branch').textContent), 'Activate turns the row back on');
  assert.ok(unitLabels('airport').includes('Erigavo Branch'),
    're-activating restores the unit in the sidebar tree');
  console.log('ok: Deactivate / Activate retires and restores the branch in the sidebar');
} catch (err) { console.error(err); process.exit(1); }

// -------------------------------------- legacy batch placement (cleanup) ----
try {
  const before = state.requests.length;
  run("selectAllLegacyBranches(true)");
  // Branch 2 was placed by the Edit test above, so the queue now holds West and
  // South only — the tool always works from the live queue, never a snapshot.
  assert.equal(JSON.stringify(Array.from(run('selectedLegacyBranchIds()')).sort()),
    JSON.stringify([3, 4]), 'Select all picks every remaining legacy branch');
  $('branchLegacyRegion').value = 'Sool';
  run('populateBranchLegacyDistricts()');
  assert.equal(JSON.stringify([...$('branchLegacyDistrict').options].map((o) => o.value).filter(Boolean)),
    JSON.stringify(['Laascaanood', 'Caynabo', 'Xudun', 'Taleex']),
    'the District list is the Sool gazetteer');
  $('branchLegacyDistrict').value = 'Laascaanood';
  await run('assignLegacyBranches()');
  await tick(80);
  const posts = state.requests.slice(before).filter((r) => r.method === 'POST');
  assert.equal(posts.length, 1, 'the cleanup sends one batch request');
  assert.equal(posts[0].path, '/api/admin/branches/bulk-assign');
  assert.equal(JSON.stringify(Array.from(posts[0].body.ids).sort()), JSON.stringify([3, 4]),
    'the batch carries every selected branch id');
  assert.equal(posts[0].body.region, 'Sool');
  assert.equal(posts[0].body.district, 'Laascaanood');
  assert.equal($('branchLegacyPanel').style.display, 'none',
    'the cleanup panel disappears once every branch is placed');
  assert.ok(districtOf('checkpoint', 'Sool', 'Laascaanood'),
    'the batch-placed units moved into the gazetteer tree');
  console.log('ok: the legacy cleanup tool batch-assigns the unplaced rows');
} catch (err) { console.error(err); process.exit(1); }

// -------------------------------------------- non-admin refused the edit ----
try {
  signIn('FingerprintUnit', ['dashboard', 'fingerprint'], false);
  await run('refreshBranchManagement(true)');
  await tick();
  run('openBranchEdit(1)');
  await tick(30);
  assert.ok(!$('branchEditModal').classList.contains('open'),
    'a non-admin session cannot open the Edit Branch modal');
  assert.ok((w._lastToast || [])[0] === 'Administrator only',
    'the refusal explains that editing is administrator-only');
  assert.equal(rowButton('Lasanod Branch', 'Edit').classList.contains('admin-edit'), true,
    'the Edit control stays behind the .admin-edit hide rule');
  const editRequests = state.requests.filter((r) => r.method === 'PATCH'
    && r.path.startsWith('/api/admin/branches'));
  assert.equal(editRequests.length, 3, 'no extra write left the browser for the refused session');
  console.log('ok: a non-admin session is refused before any PATCH leaves the browser');
} catch (err) { console.error(err); process.exit(1); }

console.log('\nALL BRANCH MANAGEMENT UI TESTS PASSED');
