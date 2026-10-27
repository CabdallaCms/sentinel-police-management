#!/usr/bin/env node
// Hierarchical sidebar + dynamic unit tree + locked branch selectors (jsdom).
//
//   npm install --no-save --package-lock=false jsdom@26
//   node backend/test_sidebar_navigation.mjs
//
// What this pins:
//   * the four operational categories (Command Center · Operational Units ·
//     Agency & Personnel · Administration) and the accordions inside them;
//   * RBAC is untouched: the same module deny list / admin flag removes whole
//     entries and collapses empty categories, and a denied module still never
//     renders a link — nor a unit tree;
//   * the DYNAMIC unit tree: every operational accordion paints
//     Region → District → unit from /api/branches + the live registers, and a
//     new branch / checkpoint appears without a reload;
//   * scalable labels: long unit names render short, the full name stays in the
//     tooltip, and the Unit Directory is a CATEGORY-LEVEL utility (no longer
//     nested under Checkpoint Units);
//   * auto-locked branch selectors: a posted officer has the branch selector
//     pre-selected and disabled; a System Administrator keeps a free choice;
//   * every navigation link still opens its page under its RBAC gate.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://sentinel.test', runScripts: 'outside-only' });
const w = dom.window;
const ctx = dom.getInternalVMContext();
let mobile = false;
w.matchMedia = () => ({ matches: mobile });
w.fetch = async () => { throw new Error('Network must be mocked in this DOM test'); };
const run = (source) => vm.runInContext(source, ctx);
const tick = (ms = 300) => new Promise((resolve) => setTimeout(resolve, ms));
const $ = (id) => w.document.getElementById(id);
const query = (sel) => w.document.querySelector(sel);
const queryAll = (sel) => [...w.document.querySelectorAll(sel)];

const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/if\(document\.readyState==='loading'\)[\s\S]*$/, '');
run(script);

const ALL_MODULES = ['dashboard', 'people', 'fingerprint', 'airport', 'cid', 'checkpoints',
  'policesearch', 'admin', 'stations', 'crimes', 'officers', 'conduct', 'cars',
  'executive', 'oversight'];

function signIn(role, modules, isAdmin = false, extra = {}) {
  const user = { role, modules, display_name: 'Test Officer', role_label: role, ...extra };
  run(`sessionUser=${JSON.stringify(user)};
    currentUser=sessionUser;sessionVisibility={is_admin:${isAdmin},
      can_manage_users:${isAdmin},can_manage_records:${isAdmin},can_manage_stations:${isAdmin}};
    applyNavForRole();updateUserPill();`);
}
function setCatalogue(items) {
  run(`branchCatalog={loaded:true,items:${JSON.stringify(items)},regions:[],unit_types:[],districts:[]};
    renderUnitNavTrees();`);
}
function sectionOf(name) { return query(`#nav .nav-section[data-section="${name}"]`); }
function visibleSections() {
  return queryAll('#nav .nav-section').filter((s) => s.style.display !== 'none')
    .map((s) => s.dataset.section);
}
function visibleGroups() {
  return queryAll('#nav .nav-group').filter((g) => g.style.display !== 'none')
    .map((g) => g.dataset.group);
}
function visiblePages() {
  return queryAll('#nav button[data-page]')
    .filter((b) => b.style.display !== 'none' && !b.closest('.nav-group[style*="display: none"]'))
    .map((b) => b.dataset.page);
}
function tree(type) { return query(`#nav [data-nav-regions="${type}"]`); }
function treeRegions(type) {
  const mount = tree(type);
  return mount ? [...mount.querySelectorAll('.nav-region')] : [];
}
function treeUnits(type) {
  const mount = tree(type);
  return mount ? [...mount.querySelectorAll('.nav-unit')] : [];
}

const BRANCHES = [
  { id: 'b1', name: 'Buuhoodle Border Crossing Checkpoint', region: 'East Togdheer', district: 'Buuhoodle', unit_type: 'checkpoint' },
  { id: 'b2', name: 'Lasanod Central Checkpoint', region: 'Sool', district: 'Laascaanood', unit_type: 'checkpoint' },
  { id: 'b3', name: 'Yagoori Village Checkpoint', region: 'Sool', district: 'Xudun', unit_type: 'checkpoint' },
  { id: 'b4', name: 'Erigavo Branch', region: 'Sanaag', district: 'Ceerigaabo', unit_type: 'fingerprint' },
  { id: 'b5', name: 'Badhan Branch', region: 'Sanaag', district: 'Badhan', unit_type: 'fingerprint' },
  { id: 'b6', name: 'Burao Branch', region: 'East Togdheer', district: 'Burao', unit_type: 'fingerprint' },
  { id: 'b7', name: 'Burao Airport Desk', region: 'East Togdheer', district: 'Burao', unit_type: 'airport' },
  { id: 'b8', name: 'Laascaanood CID Office', region: 'Sool', district: 'Laascaanood', unit_type: 'crime' },
  { id: 'b10', name: 'Lasanod Branch', region: 'Sool', district: 'Laascaanood', unit_type: 'fingerprint' },
  { id: 'b11', name: 'Lasanod Station', region: 'Sool', district: 'Laascaanood', unit_type: 'police_station' },
  { id: 'b12', name: 'Laascaanood Airport Desk', region: 'Sool', district: 'Laascaanood', unit_type: 'airport' },
];

try {
  // ---- 1) the authored hierarchy -----------------------------------------
  const sections = queryAll('#nav .nav-section');
  assert.deepEqual(sections.map((s) => s.dataset.section),
    ['command-center', 'operational-units', 'agency-personnel', 'administration'],
    'the sidebar must open with the four operational categories in order');
  assert.deepEqual(sections.map((s) => s.querySelector('.nav-section-name').textContent.trim()),
    ['Command Center', 'Operational Units', 'Agency & Personnel', 'Administration']);
  assert.equal(queryAll('#nav > button[data-page]').length, 0,
    'no page button may sit outside a category section');
  sections.forEach((sec) => {
    const toggle = sec.querySelector('.nav-section-toggle');
    assert.ok(toggle, 'each category needs a collapse toggle');
    assert.equal(toggle.getAttribute('aria-expanded'), 'true');
    assert.equal(toggle.getAttribute('aria-controls'), sec.querySelector('.nav-section-body').id);
  });
  assert.deepEqual(queryAll('#nav .nav-group').map((g) => g.dataset.group),
    ['search', 'command', 'fingerprint', 'cid', 'airport', 'checkpoints',
      'registrations', 'personnel', 'transport', 'admin']);
  assert.deepEqual(queryAll('#nav .nav-group-toggle .nav-group-modern-title')
    .map((s) => s.textContent.trim().replace(/\s+/g, ' ')),
    ['Search & Intelligence', 'HQ Command', 'Fingerprint Units', 'Crime Units',
      'Airport Control', 'Checkpoint Units', 'Stations & Registers',
      'Police Personnel', 'Transport / Fleet', 'System Administration']);
  assert.ok(!/Dep\. of Police Personnel \(Registration Police Office\)/
    .test(query('#nav').innerHTML), 'the long department strings belong in tooltips, not the rail');
  console.log('ok: four collapsible categories with the unit accordions inside them');

  // ---- 2) the Unit Directory is a CATEGORY-LEVEL utility ------------------
  const utility = query('#nav .nav-section[data-section="operational-units"] .nav-utility[data-unit-directory="all"]');
  assert.ok(utility, 'Unit Directory must be a top-level utility under Operational Units');
  assert.equal(utility.parentNode.dataset.sectionBody, 'operational-units',
    'the utility button lives directly in the Operational Units category body');
  assert.ok(!utility.closest('.nav-group'),
    'Unit Directory must NOT be nested inside the Checkpoint Units accordion');
  assert.equal(query('#nav .nav-group[data-group="checkpoints"] [data-unit-directory]'), null,
    'the checkpoint accordion no longer hosts a directory button');
  assert.ok(utility.textContent.includes('Unit Directory'), 'the utility is labelled Unit Directory');
  assert.equal(utility.querySelector('i').getAttribute('aria-hidden'), 'true');
  // Every operational accordion owns a tree mount.
  ['fingerprint', 'crime', 'airport', 'checkpoint', 'police_station'].forEach((type) => {
    assert.ok(tree(type), `the ${type} accordion is missing its Region → District mount`);
    assert.ok(tree(type).closest('.nav-group'),
      `the ${type} tree must live inside its unit accordion`);
  });
  assert.deepEqual(tree('checkpoint').dataset.navRegions, 'checkpoint');
  // Every unit type the directory knows also has a tree (no dangling type).
  assert.equal(new Set(['fingerprint', 'crime', 'airport', 'checkpoint', 'police_station'])
    .size, queryAll('#nav [data-nav-regions]').length,
    'each unit type owns exactly one tree mount');
  console.log('ok: Unit Directory is a top-level Operational Units utility; every unit owns a tree mount');

  // ---- 3) RBAC: a SystemAdmin sees the whole hierarchy --------------------
  signIn('SystemAdmin', ALL_MODULES, true);
  assert.deepEqual(visibleSections(),
    ['command-center', 'operational-units', 'agency-personnel', 'administration']);
  assert.ok(query('#nav [data-page="branches"]'), 'an admin keeps Branch Management');
  assert.ok(query('#nav [data-page="policesearch"]'), 'an admin keeps Central Police Search');
  visiblePages().forEach((page) => {
    assert.ok($(page), `nav entry ${page} has no <section class="page" id="${page}">`);
  });
  console.log('ok: SystemAdmin sees all four categories and every entry resolves to a page');

  // ---- 4) RBAC: an operational unit loses the modules it may not read -----
  signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint']);
  assert.equal(query('#nav [data-page="policesearch"]'), null,
    'Central Police Search must be REMOVED for Fingerprint, not hidden');
  assert.equal(query('#nav [data-page="branches"]'), null);
  assert.equal(visibleSections().includes('administration'), false,
    'the Administration category must disappear for a non-admin');
  assert.deepEqual(visibleGroups(), ['search', 'fingerprint'],
    'a fingerprint officer keeps Central Person Search but no checkpoint/CID accordion');
  assert.equal(query('#nav [data-module-label="checkpoints"]').style.display, 'none',
    'the checkpoint subgroup label follows its link');
  console.log('ok: unit roles keep their own accordion and lose every other category');

  // ---- 5) DYNAMIC tree: Region → District → unit -------------------------
  signIn('SystemAdmin', ALL_MODULES, true);
  setCatalogue(BRANCHES);
  const fpRegions = treeRegions('fingerprint');
  assert.deepEqual(fpRegions.map((r) => r.dataset.navRegion),
    ['Sool', 'Sanaag', 'East Togdheer'],
    'the fingerprint tree is grouped by region in gazetteer order');
  const sanaag = fpRegions.find((r) => r.dataset.navRegion === 'Sanaag');
  assert.deepEqual([...sanaag.querySelectorAll('.nav-district')].map((d) => d.dataset.navDistrict),
    ['Ceerigaabo', 'Badhan'], 'the second level is the district');
  const sanaagDistricts = [...sanaag.querySelectorAll('.nav-district')].map((d) => ({
    district: d.dataset.navDistrict,
    units: [...d.querySelectorAll('.nav-unit')].map((u) => u.dataset.unitLabel),
  }));
  assert.deepEqual(sanaagDistricts, [
    { district: 'Ceerigaabo', units: ['Erigavo Branch'] },
    { district: 'Badhan', units: ['Badhan Branch'] },
  ], 'the third level lists only the branches of that district');
  // Checkpoint tree: Sool → Laascaanood / Xudun → the postings.
  const cpRegions = treeRegions('checkpoint');
  assert.deepEqual(cpRegions.map((r) => r.dataset.navRegion),
    ['Sool', 'East Togdheer', 'Checkpoint areas'],
    'Sool first (gazetteer order), then East Togdheer, then the canonical areas');
  const sool = cpRegions.find((r) => r.dataset.navRegion === 'Sool');
  assert.deepEqual([...sool.querySelectorAll('.nav-district')].map((d) => d.dataset.navDistrict),
    ['Laascaanood', 'Xudun']);
  const lasanod = [...sool.querySelectorAll('.nav-district')]
    .find((d) => d.dataset.navDistrict === 'Laascaanood');
  assert.deepEqual([...lasanod.querySelectorAll('.nav-unit')].map((u) => u.dataset.unitLabel),
    ['Lasanod Central Checkpoint']);
  // Long names never wrap the rail: short label + full tooltip.
  treeUnits('checkpoint').forEach((btn) => {
    const short = btn.querySelector('.nav-unit-short').textContent;
    assert.ok(short.length <= 20, `sidebar unit label too long: ${short}`);
    assert.ok(btn.getAttribute('title').length >= short.length);
  });
  assert.ok(treeUnits('checkpoint').some((b) => b.textContent.includes('Buuhoodle')),
    'the short label keeps the distinguishing part of the name');
  console.log('ok: each operational unit paints a Region → District → unit tree of short labels');

  // ---- 6) a new branch / checkpoint appears without a reload -------------
  const beforeFp = treeUnits('fingerprint').length;
  run(`branchCatalog.items.push({id:'b9',name:'Dhahar Branch',region:'Sanaag',district:'Dhahar',unit_type:'fingerprint'});
    renderUnitNavTrees();`);
  assert.equal(treeUnits('fingerprint').length, beforeFp + 1,
    'a branch created in the system must appear in the tree immediately');
  assert.ok(treeUnits('fingerprint').some((b) => b.dataset.unitLabel === 'Dhahar Branch'));
  const dhahar = treeRegions('fingerprint')
    .find((r) => r.dataset.navRegion === 'Sanaag').querySelectorAll('.nav-district');
  assert.deepEqual([...dhahar].map((d) => d.dataset.navDistrict), ['Ceerigaabo', 'Badhan', 'Dhahar'],
    'the new district joins its region in gazetteer order');
  // A checkpoint recorded at a location that exists only in the register.
  const cpBefore = treeUnits('checkpoint').length;
  run(`db.checkpoints.unshift({checkpoint_location:'Adhi Cadeeye Outpost',location_code:'Adhi Cadeeye',
      branch:'Adhi Cadeeye Outpost · Laascaanood',screen:'No active alert'});
    renderUnitNavTrees();`);
  assert.equal(treeUnits('checkpoint').length, cpBefore + 1,
    'a checkpoint used in the register must appear in the tree immediately');
  const adhi = treeUnits('checkpoint').find((b) => b.dataset.unitLabel === 'Adhi Cadeeye Outpost');
  assert.ok(adhi, 'the register-only checkpoint is listed');
  assert.ok(adhi.closest('.nav-district').dataset.navDistrict === 'Laascaanood',
    'its district is taken from the branch catalogue / composed branch label');
  console.log('ok: new branches and checkpoint postings populate the tree immediately');

  // ---- 7) region + district expand/collapse (persisted, ARIA) -----------
  const soolNow = treeRegions('checkpoint').find((r) => r.dataset.navRegion === 'Sool');
  const soolToggle = soolNow.querySelector('.nav-region-toggle');
  run(`toggleNavRegion('Sool','checkpoint')`);
  assert.equal(soolNow.classList.contains('open'), true);
  assert.equal(soolToggle.getAttribute('aria-expanded'), 'true');
  assert.equal(JSON.parse(w.localStorage.getItem('sentinelNavRegions'))['checkpoint|Sool'], true);
  run(`toggleNavDistrict('Laascaanood','Sool','checkpoint')`);
  const district = soolNow.querySelector('.nav-district[data-nav-district="Laascaanood"]');
  assert.equal(district.classList.contains('open'), true);
  assert.equal(district.querySelector('.nav-district-toggle').getAttribute('aria-expanded'), 'true');
  assert.equal(JSON.parse(w.localStorage.getItem('sentinelNavRegions'))['checkpoint|Sool|Laascaanood'], true);
  run(`toggleNavRegion('Sool','checkpoint')`);
  assert.equal(soolToggle.getAttribute('aria-expanded'), 'false');
  console.log('ok: region and district levels expand/collapse with persisted ARIA state');

  // ---- 8) clicking a unit opens its register -----------------------------
  run(`openUnitNavUnit('fingerprint','Erigavo Branch','')`);
  assert.equal($('fingerprint').classList.contains('active'), true,
    'a fingerprint unit opens the fingerprint register');
  assert.equal($('fpSearch').value, 'Erigavo Branch',
    'the register is filtered to that branch through its search box');
  assert.equal(treeUnits('fingerprint').filter((b) => b.classList.contains('is-current')).length, 1,
    'the active unit is highlighted in the tree');
  run(`openUnitNavUnit('checkpoint','East Checkpoint','East')`);
  assert.equal(run('cpLocationFilter'), 'East');
  assert.equal($('checkpoints').classList.contains('active'), true);
  console.log('ok: a unit link opens its register scoped to that unit');

  // A station-scoped checkpoint officer keeps their RBAC posting.
  signIn('checkpoint_officer', ['dashboard', 'people', 'checkpoints'], false,
    { location_scope: 'South', branch: 'Lasanod Central Checkpoint · Laascaanood · Sool' });
  run(`openCheckpointUnit('East Checkpoint','East')`);
  assert.equal(run('cpLocationFilter'), 'South',
    'a checkpoint officer stays locked to their assigned posting');
  console.log('ok: unit links never widen a station-scoped officer beyond their posting');

  // ---- 9) Unit Directory (category utility) ------------------------------
  signIn('SystemAdmin', ALL_MODULES, true);
  run(`openUnitDirectory('')`);
  assert.equal($('unitDir').classList.contains('open'), true, 'the directory opens in a modal');
  assert.deepEqual(queryAll('#udUnitType option').map((o) => o.value),
    ['', 'checkpoint', 'fingerprint', 'crime', 'airport', 'police_station'],
    'the category-level directory lists every permitted unit type plus "All"');
  const allRows = queryAll('#udTable tr').length;
  assert.ok(allRows >= BRANCHES.length, 'the all-types view lists every unit');
  // Unit type → region → district → free text.
  $('udUnitType').value = 'checkpoint';
  run(`populateUnitDirectoryFilters(true);renderUnitDirectory();`);
  assert.deepEqual(queryAll('#udRegion option').map((o) => o.value),
    ['', 'Checkpoint areas', 'East Togdheer', 'Sool'],
    'the directory filter lists the regions that actually carry units');
  $('udRegion').value = 'Sool';
  run(`populateUnitDirectoryDistricts();renderUnitDirectory();`);
  assert.deepEqual(queryAll('#udDistrict option').map((o) => o.value),
    ['', 'Laascaanood', 'Xudun']);
  $('udDistrict').value = 'Xudun';
  run(`renderUnitDirectory()`);
  assert.equal(queryAll('#udTable tr').length, 1);
  assert.ok($('udTable').textContent.includes('Yagoori'));
  $('udSearch').value = 'lasanod';
  run(`renderUnitDirectory()`);
  assert.equal(queryAll('#udTable tr').length, 0, 'district + search are ANDed');
  assert.equal($('udEmpty').style.display, '', 'the empty state explains the dead end');
  // Clicking a row opens that unit (and closes the directory).
  $('udSearch').value = '';
  $('udDistrict').value = '';
  $('udRegion').value = '';
  $('udUnitType').value = '';
  run(`populateUnitDirectoryFilters(true);renderUnitDirectory()`);
  const fpRow = queryAll('#udTable tr').find((tr) => tr.dataset.udOpen === 'fingerprint');
  assert.ok(fpRow, 'the directory lists fingerprint units too');
  fpRow.click();
  await tick();
  assert.equal($('unitDir').classList.contains('open'), false,
    'opening a unit closes the directory');
  assert.equal($('fingerprint').classList.contains('active'), true);
  console.log('ok: the Unit Directory browses every unit with type / region / district / search filters');

  // A Commander (read-only) may browse the directory: it is a read surface.
  signIn('chief_commander', ['dashboard', 'fingerprint', 'airport', 'cid', 'checkpoints',
    'executive', 'oversight'], false, {});
  run(`openUnitDirectory('')`);
  assert.equal($('unitDir').classList.contains('open'), true,
    'a read-only Commander must be able to browse the unit directory');
  run(`closeEntryModal('unitDir')`);
  console.log('ok: the directory stays a read-only surface for a Commander session');

  // ---- 10) auto-locked branch selectors ---------------------------------
  signIn('checkpoint_officer', ['dashboard', 'people', 'checkpoints'], false,
    { location_scope: 'South', branch: 'Lasanod Central Checkpoint · Laascaanood · Sool' });
  run(`openCheckpointDrawer()`);
  await run(`refreshBranchSelect('cpBranch','checkpoint')`);
  const cpBranch = $('cpBranch');
  assert.equal(cpBranch.disabled, true, 'a posted checkpoint officer cannot change the branch');
  assert.equal(cpBranch.value, 'b2', 'the selector is pre-selected to their own branch');
  assert.equal(cpBranch.dataset.branchLocked, 'b2');
  assert.ok($('cpBranch-lock').textContent.includes('Lasanod Central Checkpoint'),
    'the lock explains why the field is fixed');
  assert.equal($('cpLoc').disabled, true, 'the canonical checkpoint location stays locked too');
  assert.equal($('cpLoc').value, 'South');
  run(`closeDrawer()`);

  signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint'], false,
    { branch: 'Erigavo Branch · Sanaag' });
  run(`openEntryModal('fpDrawer')`);
  await run(`refreshBranchSelect('fpBranch','fingerprint')`);
  assert.equal($('fpBranch').disabled, true, 'a posted fingerprint officer is locked to their branch');
  assert.equal($('fpBranch').value, 'b4');
  assert.equal($('fpBranch-lock').textContent.includes('Erigavo Branch'), true);
  run(`closeEntryModal('fpDrawer')`);

  // The locked note is a clean chip with the documented wording — never a
  // yellow warning banner, and never the old 'Assigned to …' warning.
  const lockHint = $('fpBranch-lock');
  assert.ok(lockHint.textContent.includes('Locked to assigned branch'),
    'the locked selector shows the clean 🔒 Locked to assigned branch indicator');
  assert.equal(lockHint.classList.contains('is-note'), false);
  assert.equal(w.getComputedStyle(lockHint).backgroundColor.includes('255, 247, 230'), false,
    'the lock indicator must not use the yellow warning palette');

  // ---- 10b) fuzzy / canonical posting matching -------------------------
  // 'Lasanod Branch' (clean), '  lasanod branch ' (noise),
  // 'Lasanod' (suffix dropped) and 'Erigavo Branch · Sanaag' all resolve.
  const matchCases = [
    ['Lasanod Branch', 'b10', 'a clean branch name'],
    ['  LASANOD branch ', 'b10', 'case + padding noise'],
    ['Lasanod', 'b10', 'the administrative suffix omitted'],
    ['Erigavo Branch · Sanaag', 'b4', 'the composed Name · Region label'],
    ['Erigavo Branch · Ceerigaabo · Sanaag', 'b4', 'the composed Name · District · Region label'],
  ];
  for (const [posting, expectedId, why] of matchCases) {
    signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint'], false, { branch: posting });
    run(`openEntryModal('fpDrawer')`);
    await run(`refreshBranchSelect('fpBranch','fingerprint')`);
    assert.equal($('fpBranch').disabled, true, `a fingerprint officer is locked for ${why}`);
    assert.equal($('fpBranch').value, expectedId, `${why} resolves to the right branch`);
    run(`closeEntryModal('fpDrawer')`);
  }

  // A legacy UNIT-LEVEL posting ('Fingerprint Unit') resolves through the
  // officer's geography; with no geography it stays unambiguous-by-rule and
  // the selector stays open (a branch is never invented).
  signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint'], false,
    { branch: 'Fingerprint Unit · Sool' });
  run(`openEntryModal('fpDrawer')`);
  await run(`refreshBranchSelect('fpBranch','fingerprint')`);
  assert.equal($('fpBranch').disabled, true,
    'a legacy unit posting narrowed by its region still locks');
  assert.equal($('fpBranch').value, 'b10', 'the Sool fingerprint branch is selected');
  run(`closeEntryModal('fpDrawer')`);

  signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint'], false,
    { branch: 'Fingerprint Unit' });
  run(`openEntryModal('fpDrawer')`);
  await run(`refreshBranchSelect('fpBranch','fingerprint')`);
  assert.equal($('fpBranch').disabled, false,
    'an ambiguous unit-level posting (four branches, no region) never guesses');
  assert.equal($('fpBranch').dataset.branchLocked, undefined);

  // A unit officer whose posting is not in the catalogue keeps the choice, and
  // is told — in muted text, not a warning — that the branch has to be
  // registered first.
  signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint'], false,
    { branch: 'Nowhere Branch · Sanaag' });
  run(`openEntryModal('fpDrawer')`);
  await run(`refreshBranchSelect('fpBranch','fingerprint')`);
  assert.equal($('fpBranch').disabled, false, 'an unknown posting cannot fabricate a branch id');
  assert.equal($('fpBranch').dataset.branchLocked, undefined);
  assert.ok($('fpBranch-lock').textContent.includes('does not name one registered branch'),
    'the officer is told the posting has to be registered first');
  assert.equal($('fpBranch-lock').classList.contains('is-note'), true,
    'the unresolvable posting is information, not a warning');
  run(`closeEntryModal('fpDrawer')`);

  // The API's resolved posting (session payload) is authoritative: a legacy
  // branch label with a server-side resolution locks to that branch id even
  // when the label alone would not match.
  signIn('AirportUnit', ['dashboard', 'airport'], false,
    { branch: 'Yagoori Village Checkpoint', branch_scope_status: {
      resolved: true, posting: 'Yagoori Village Checkpoint',
      branch: { branch_id: 'b7', branch_name: 'Burao Airport Desk',
                region: 'East Togdheer', district: 'Burao', unit_type: 'airport' },
    } });
  run(`openEntryModal('airDrawer')`);
  await run(`refreshBranchSelect('airBranch','airport')`);
  assert.equal($('airBranch').disabled, true,
    'the server-resolved posting locks the selector');
  assert.equal($('airBranch').value, 'b7');
  assert.ok($('airBranch-lock').textContent.includes('Locked to assigned branch'));
  run(`closeEntryModal('airDrawer')`);

  // System Administrators stay free to pick any branch.
  signIn('SystemAdmin', ALL_MODULES, true);
  run(`openCheckpointDrawer()`);
  await run(`refreshBranchSelect('cpBranch','checkpoint')`);
  assert.equal($('cpBranch').disabled, false, 'a System Administrator can select any branch');
  assert.equal($('cpBranch').dataset.branchLocked, undefined);
  assert.equal($('cpLoc').disabled, false, 'an admin can record any checkpoint location');
  run(`closeDrawer()`);
  console.log('ok: posted officers are locked to their own branch; administrators keep a free choice');

  // ---- 10c) contextual module headers ----------------------------------
  // The module banner names the officer's POSTING, not just the unit.
  signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint'], false,
    { branch: 'Lasanod Branch' });
  const fpHead = query('[data-unit-head="fingerprint"]');
  assert.equal(fpHead.textContent, 'Fingerprint Unit — Lasanod Branch Operations',
    'the fingerprint banner names the officer\'s branch');
  assert.ok(query('[data-unit-head-sub="fingerprint"]').textContent.includes('Laascaanood · Sool'),
    'the banner detail line carries the district and region');
  assert.equal(query('[data-unit-head="airport"]').textContent, 'Airport Control · overview',
    'a unit the session cannot reach never borrows the officer\'s posting');

  signIn('checkpoint_officer', ['dashboard', 'people', 'checkpoints'], false,
    { location_scope: 'South', branch: 'Lasanod Central Checkpoint · Laascaanood · Sool' });
  assert.equal(query('[data-unit-head="checkpoints"]').textContent,
    'Checkpoint Unit — Lasanod Central Checkpoint Operations',
    'the checkpoint banner names the assigned checkpoint');

  signIn('SystemAdmin', ALL_MODULES, true);
  assert.equal(query('[data-unit-head="fingerprint"]').textContent, 'Fingerprint Unit — all branches',
    'an administrator sees the cross-branch label');
  signIn('chief_commander', ['dashboard', 'fingerprint', 'checkpoints', 'executive', 'oversight'], false);
  assert.equal(query('[data-unit-head="fingerprint"]').textContent,
    'Fingerprint Unit — cross-region command',
    'the multi-branch Commander keeps the override label');

  // The dashboard heading is contextual too (never the generic page title).
  signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint'], false,
    { branch: 'Lasanod Branch' });
  run(`go('dashboard')`);
  assert.equal($('pageTitle').textContent, 'Fingerprint Unit — Lasanod Branch Operations',
    'the operations dashboard heading names unit + branch');
  signIn('SystemAdmin', ALL_MODULES, true);
  run(`go('dashboard')`);
  assert.equal($('pageTitle').textContent, 'Cross-unit Operations',
    'an administrator keeps the cross-unit dashboard heading');
  console.log('ok: module + dashboard headers name the officer\'s posting, not a generic unit title');

  // ---- 11) restore ordering --------------------------------------------
  signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint']);
  signIn('checkpoint_officer', ['dashboard', 'people', 'checkpoints'], false,
    { location_scope: 'South', branch: 'South Checkpoint' });
  const cpGroupBody = query('#nav .nav-group-body[data-group-body="checkpoints"]');
  const checkpointLink = query('#nav [data-page="checkpoints"]');
  const label = query('#nav [data-module-label="checkpoints"]');
  assert.equal(label.nextElementSibling, checkpointLink,
    'a restored checkpoint link sits directly under its subgroup label');
  assert.equal(cpGroupBody.lastElementChild, tree('checkpoint'),
    'the runtime tree stays at the bottom of the accordion');
  console.log('ok: denied entries are removed and restored into their authored slot');

  // ---- 12) category + accordion collapse and navigation -----------------
  run(`setNavSectionOpen('operational-units',false)`);
  assert.equal(sectionOf('operational-units').querySelector('.nav-section-toggle')
    .getAttribute('aria-expanded'), 'false');
  run(`toggleNavSection('operational-units')`);
  assert.equal(sectionOf('operational-units').classList.contains('open'), true);
  assert.equal(JSON.parse(w.localStorage.getItem('sentinelNavSections'))['operational-units'], true);
  run(`setNavSectionOpen('operational-units',false)`);
  run(`go('checkpoints')`);
  assert.equal(sectionOf('operational-units').classList.contains('open'), true);
  assert.equal(query('#nav .nav-group[data-group="checkpoints"]').classList.contains('open'), true);
  console.log('ok: navigating expands the owning category and accordion');

  signIn('SystemAdmin', ALL_MODULES, true);
  const failures = [];
  queryAll('#nav button[data-page]').forEach((btn) => {
    const page = btn.dataset.page;
    if (!$(page)) { failures.push(`${page}: no page section`); return; }
    try { run(`go(${JSON.stringify(page)})`); } catch (_) { /* renderers may need the API */ }
    if (!$(`${page}`).classList.contains('active')) failures.push(`${page}: did not open`);
    if (btn.closest('.nav-group') && !query('#nav .nav-group.open button[data-page="' + page + '"]'))
      failures.push(`${page}: owning accordion stayed collapsed`);
    const sec = btn.closest('.nav-section');
    if (sec && !sec.classList.contains('open')) failures.push(`${page}: owning category stayed collapsed`);
  });
  assert.deepEqual(failures, [], 'every navigation link must remain functional');
  console.log('ok: every navigation link opens its page and reveals its category');

  // ---- 13) short-label helper -------------------------------------------
  assert.equal(run(`shortUnitLabel('Buuhoodle Border Crossing Checkpoint')`), 'Buuhoodle Border C…');
  assert.equal(run(`shortUnitLabel('Lasanod Branch')`), 'Lasanod');
  assert.ok(run(`shortUnitLabel('A very long unit name that would wrap the rail').length`) <= 20);
  assert.ok(run(`shortUnitLabel('X')`).length >= 1);
  console.log('ok: short unit labels strip administrative suffixes and never wrap the rail');

  // ---- 14) branch-scoped sidebar: isolated trees + hidden Unit Directory --
  // The drawer's close animation keeps `.open` for ~220ms; settle it first.
  await tick(260);
  const scopedPosting = 'Lasanod Branch · Laascaanood · Sool';
  const expectedUnit = {
    fingerprint: 'Lasanod Branch',
    crime: 'Laascaanood CID Office',
    airport: 'Laascaanood Airport Desk',
    checkpoint: 'Lasanod Central Checkpoint',
    police_station: 'Lasanod Station',
  };
  setCatalogue(BRANCHES);
  signIn('FingerprintUnit', ALL_MODULES, false, { branch: scopedPosting });
  Object.entries(expectedUnit).forEach(([type, label]) => {
    assert.deepEqual(treeRegions(type).map((r) => r.dataset.navRegion), ['Sool'],
      `the ${type} tree shows only the officer's own region`);
    const districts = [...treeRegions(type)[0].querySelectorAll('.nav-district')];
    assert.deepEqual(districts.map((d) => d.dataset.navDistrict), ['Laascaanood'],
      `the ${type} tree shows only the officer's own district`);
    assert.deepEqual(districts[0].querySelectorAll('.nav-unit').length === 1
      ? [...districts[0].querySelectorAll('.nav-unit')].map((u) => u.dataset.unitLabel) : [],
      [label], `the ${type} tree shows only the officer's own branch`);
    assert.equal(treeUnits(type).length, 1,
      `no external ${type} branch leaks into a scoped rail`);
    assert.deepEqual(treeRegions(type).filter((r) => ['Unassigned region', 'Checkpoint areas']
      .includes(r.dataset.navRegion)), [],
      `the ${type} tree never shows an unassigned / cross-area group`);
    assert.ok(treeUnits(type).every((u) => (u.getAttribute('title') || '').includes('Sool')),
      'every remaining unit really belongs to the officer region');
  });
  assert.equal(queryAll('#nav [data-unit-directory]').length, 1);
  assert.equal(query('#nav [data-unit-directory]').style.display, 'none',
    'the Unit Directory launcher is hidden for a branch-scoped officer');
  assert.equal(query('#nav [data-unit-directory]').getAttribute('aria-hidden'), 'true');
  assert.equal($('navUnitCount').hidden, true, 'the directory badge is cleared too');
  $('toast').textContent = '';
  run(`openUnitDirectory('')`);
  assert.equal($('unitDir').classList.contains('open'), false,
    'the Unit Directory drawer refuses to open for a branch-scoped officer');
  assert.match($('toast').textContent, /Unit Directory is restricted/,
    'the officer is told the directory is a cross-branch surface');
  // The scoped trees still open the officer's own register.
  run(`openUnitNavUnit('fingerprint','Lasanod Branch','')`);
  assert.equal($('fingerprint').classList.contains('active'), true);
  assert.equal($('fpSearch').value, 'Lasanod Branch');
  console.log('ok: a branch-scoped officer gets an isolated tree and no Unit Directory');

  // A posted checkpoint officer is scoped the same way, in every category.
  signIn('checkpoint_officer', ALL_MODULES, false,
    { branch: 'Lasanod Central Checkpoint · Laascaanood · Sool', location_scope: 'South' });
  ['fingerprint', 'crime', 'airport', 'checkpoint', 'police_station'].forEach((type) => {
    assert.deepEqual(treeRegions(type).map((r) => r.dataset.navRegion), ['Sool'],
      `the checkpoint officer's ${type} tree stays inside Sool`);
  });
  assert.equal(query('#nav [data-unit-directory]').style.display, 'none',
    'a posted checkpoint officer has no Unit Directory launcher');
  console.log('ok: the scoping rule is identical for every unit category');

  // The override roles keep full national visibility and the directory.
  signIn('SystemAdmin', ALL_MODULES, true, { branch: scopedPosting });
  const adminFpRegions = treeRegions('fingerprint').map((r) => r.dataset.navRegion);
  assert.ok(adminFpRegions.length > 1 && adminFpRegions.includes('Sanaag'),
    'the System Administrator sees every region in the tree');
  assert.equal(query('#nav [data-unit-directory]').style.display, '',
    'the System Administrator keeps the Unit Directory launcher');
  run(`openUnitDirectory('')`);
  assert.equal($('unitDir').classList.contains('open'), true);
  run(`closeEntryModal('unitDir')`);

  signIn('chief_commander', ALL_MODULES, false, { branch: scopedPosting });
  assert.ok(treeRegions('fingerprint').map((r) => r.dataset.navRegion).includes('Sanaag'),
    'the multi-branch Commander keeps national visibility');
  assert.equal(query('#nav [data-unit-directory]').style.display, '',
    'the cross-branch command role keeps the Unit Directory');
  signIn('chief_commander', ALL_MODULES, false, { branch: '' });
  assert.equal(query('#nav [data-unit-directory]').style.display, '',
    'the Commander keeps the directory even without a posting');
  console.log('ok: administrators and commanders retain the national tree and directory');

  // A standard officer with no resolvable posting is not "scoped", but the
  // directory is still restricted to the command authority.
  signIn('FingerprintUnit', ALL_MODULES, false, { branch: 'Fingerprint Unit' });
  assert.ok(treeRegions('fingerprint').length > 1,
    'an unresolved unit-level posting keeps the legacy national view');
  assert.equal(query('#nav [data-unit-directory]').style.display, 'none',
    'the Unit Directory is reserved for the admin / command authority');
  console.log('ok: the directory is restricted to the admin / cross-branch command roles');

  console.log('PASS: hierarchical sidebar, dynamic unit tree, RBAC gates and locked branch selectors');
} finally {
  // Let pending render promises (page painters fired by go()) settle before the
  // window is torn down, so a late repaint cannot throw after the suite passes.
  await new Promise((resolve) => setTimeout(resolve, 150));
  w.close();
}
