#!/usr/bin/env node
// Hierarchical sidebar contract (jsdom).
//
//   npm install --no-save --package-lock=false jsdom@26
//   node backend/test_sidebar_navigation.mjs
//
// What this pins:
//   * the four operational categories (Command Center · Operational Units ·
//     Agency & Personnel · Administration) and the accordions inside them —
//     labels, order and the entries each one carries;
//   * RBAC is untouched: the same module deny list / admin flag removes whole
//     entries and collapses empty categories, and a denied module still never
//     renders a link;
//   * scalable unit lists: long checkpoint names render as short labels, the
//     Checkpoint Units accordion paints a region → district sub-menu, and the
//     Unit Directory browses the same catalogue with Region + District filters;
//   * a restored nav entry lands back in its authored slot (next to its
//     subgroup label and above the runtime-rendered sub-menu);
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
      can_manage_users:${isAdmin},can_manage_stations:${isAdmin}};
    applyNavForRole();updateUserPill();`);
}

function sectionOf(name) {
  return query(`#nav .nav-section[data-section="${name}"]`);
}
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

try {
  // ---- 1) the authored hierarchy -----------------------------------------
  const sections = queryAll('#nav .nav-section');
  assert.deepEqual(sections.map((s) => s.dataset.section),
    ['command-center', 'operational-units', 'agency-personnel', 'administration'],
    'the sidebar must open with the four operational categories in order');
  assert.deepEqual(sections.map((s) => s.querySelector('.nav-section-name').textContent.trim()),
    ['Command Center', 'Operational Units', 'Agency & Personnel', 'Administration']);
  // Every nav entry lives in a category — the flat list is gone.
  assert.equal(queryAll('#nav > button[data-page]').length, 0,
    'no page button may sit outside a category section');
  // Each category is collapsible with ARIA state.
  sections.forEach((sec) => {
    const toggle = sec.querySelector('.nav-section-toggle');
    assert.ok(toggle, 'each category needs a collapse toggle');
    assert.equal(toggle.getAttribute('aria-expanded'), 'true');
    assert.equal(toggle.getAttribute('aria-controls'), sec.querySelector('.nav-section-body').id);
  });
  // Accordions inside the categories, in authored order.
  const groupNames = queryAll('#nav .nav-group').map((g) => g.dataset.group);
  assert.deepEqual(groupNames, ['search', 'command', 'fingerprint', 'cid', 'airport',
    'checkpoints', 'registrations', 'personnel', 'transport', 'admin']);
  assert.deepEqual(queryAll('#nav .nav-group-toggle .nav-group-modern-title')
    .map((s) => s.textContent.trim().replace(/\s+/g, ' ')),
    ['Search & Intelligence', 'HQ Command', 'Fingerprint Units', 'Crime Units',
      'Airport Control', 'Checkpoint Units', 'Stations & Registers',
      'Police Personnel', 'Transport / Fleet', 'System Administration']);
  // The checkpoint accordion owns the scalable unit surface.
  const cpGroup = query('#nav .nav-group[data-group="checkpoints"]');
  assert.ok(cpGroup.querySelector('[data-nav-regions="checkpoint"]'));
  assert.ok(cpGroup.querySelector('[data-unit-directory="checkpoint"]'));
  // Long administrative names are no longer the sidebar labels.
  assert.ok(!/Dep\. of Police Personnel \(Registration Police Office\)/
    .test(query('#nav').innerHTML), 'the long department strings belong in tooltips, not the rail');
  console.log('ok: four collapsible categories with the unit accordions inside them');

  // ---- 2) RBAC: a SystemAdmin sees the whole hierarchy --------------------
  signIn('SystemAdmin', ALL_MODULES, true);
  assert.deepEqual(visibleSections(),
    ['command-center', 'operational-units', 'agency-personnel', 'administration']);
  assert.ok(query('#nav [data-page="branches"]'), 'an admin keeps Branch Management');
  assert.ok(query('#nav [data-page="policesearch"]'), 'an admin keeps Central Police Search');
  // Every visible entry maps to a real page section.
  visiblePages().forEach((page) => {
    assert.ok($(page), `nav entry ${page} has no <section class="page" id="${page}">`);
  });
  console.log('ok: SystemAdmin sees all four categories and every entry resolves to a page');

  // ---- 3) RBAC: an operational unit loses the modules it may not read -----
  signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint']);
  assert.equal(query('#nav [data-page="policesearch"]'), null,
    'Central Police Search must be REMOVED for Fingerprint, not hidden');
  assert.equal(query('#nav [data-page="branches"]'), null);
  assert.equal(visibleSections().includes('administration'), false,
    'the Administration category must disappear for a non-admin');
  assert.deepEqual(visibleGroups(), ['search', 'fingerprint'],
    'a fingerprint officer keeps Central Person Search but no CID/checkpoint accordion');
  assert.equal(query('#nav [data-module-label="checkpoints"]').style.display, 'none',
    'the checkpoint subgroup label follows its link');
  assert.equal(query('#cpNavRegions').innerHTML, '',
    'no checkpoint postings may render for a role without the module');
  assert.equal($('cpNavCount').hidden, true);
  console.log('ok: unit roles keep their own accordion and lose every other category');

  // ---- 4) Checkpoint officers get the regional sub-menu ------------------
  run(`branchCatalog={loaded:true,items:[
      {id:'b1',name:'Buuhoodle Border Crossing Checkpoint',region:'East Togdheer',district:'Buuhoodle',unit_type:'checkpoint'},
      {id:'b2',name:'Lasanod Central Checkpoint',region:'Sool',district:'Laascaanood',unit_type:'checkpoint'},
      {id:'b3',name:'Yagoori Village Checkpoint',region:'Sool',district:'Xudun',unit_type:'checkpoint'},
      {id:'b4',name:'Erigavo Branch',region:'Sanaag',district:'Ceerigaabo',unit_type:'fingerprint'}
    ],regions:['Sool','Sanaag','East Togdheer'],unit_types:['checkpoint','fingerprint'],districts:[]}`);
  signIn('CheckpointSouth', ['dashboard', 'people', 'checkpoints'], false, { location_scope: 'South' });
  assert.equal(query('#nav [data-module-label="checkpoints"]').style.display, '',
    'the checkpoint heading is visible to a checkpoint officer');
  assert.deepEqual(visibleSections(), ['command-center', 'operational-units']);
  assert.ok(visibleGroups().includes('checkpoints'));
  const regions = queryAll('#cpNavRegions .nav-region');
  assert.ok(regions.length >= 2, 'the sub-menu groups postings by region');
  assert.deepEqual(regions.map((r) => r.dataset.navRegion),
    ['Sool', 'East Togdheer', 'Assigned locations'],
    'regions follow the gazetteer order, not the branch insert order; register-only '
    + 'location codes stay visible under their own heading');
  // Long unit names are shortened, the full name survives in the tooltip.
  const unitButtons = queryAll('#cpNavRegions .nav-unit');
  assert.equal(unitButtons.length, 4,
    'every checkpoint branch plus each register location code is listed exactly once');
  unitButtons.forEach((b) => {
    const short = b.querySelector('.nav-unit-short').textContent;
    assert.ok(short.length <= 20, `sidebar unit label too long: ${short}`);
    assert.ok(b.getAttribute('title').length > short.length, 'the full unit name must stay in the tooltip');
  });
  assert.ok(unitButtons.some((b) => b.textContent.includes('Buuhoodle')),
    'the short label keeps the distinguishing part of the name');
  console.log('ok: checkpoint postings collapse into a region → district sub-menu of short labels');

  // Region toggles persist their open state and drive ARIA.
  const sool = query('#cpNavRegions .nav-region[data-nav-region="Sool"]');
  const soolToggle = sool.querySelector('.nav-region-toggle');
  run(`toggleNavRegion('Sool')`);
  assert.equal(sool.classList.contains('open'), true);
  assert.equal(soolToggle.getAttribute('aria-expanded'), 'true');
  assert.equal(JSON.parse(w.localStorage.getItem('sentinelNavRegions')).Sool, true);
  run(`toggleNavRegion('Sool')`);
  assert.equal(soolToggle.getAttribute('aria-expanded'), 'false');
  console.log('ok: region sub-menus expand/collapse with persisted ARIA state');

  // A canonical South / East / West unit drives the location chips …
  run(`openCheckpointUnit('South Checkpoint','South')`);
  assert.equal(run('cpLocationFilter'), 'South');
  assert.equal($('checkpoints').classList.contains('active'), true);
  assert.equal(query('#cpNavRegions .nav-unit.is-current').dataset.unitCode, 'South');
  // … and a named checkpoint scopes the register through its search box. A
  // station-scoped officer keeps their RBAC posting: a click can never widen
  // the register beyond the unit they are assigned to.
  run(`openCheckpointUnit('Buuhoodle Border Crossing Checkpoint','')`);
  assert.equal(run('cpLocationFilter'), 'South',
    'a checkpoint officer stays locked to their assigned posting');
  assert.equal($('cpSearch').value, 'Buuhoodle Border Crossing Checkpoint');
  run(`openCheckpointUnit('East Checkpoint','East')`);
  assert.equal(run('cpLocationFilter'), 'South',
    'clicking another location code must not widen the scope');
  console.log('ok: a unit link opens the register scoped to that unit without widening RBAC scope');

  // An administrator (unscoped) does switch the register to the clicked unit.
  signIn('SystemAdmin', ALL_MODULES, true);
  run(`openCheckpointUnit('Buuhoodle Border Crossing Checkpoint','')`);
  assert.equal(run('cpLocationFilter'), '');
  assert.equal($('cpSearch').value, 'Buuhoodle Border Crossing Checkpoint');
  run(`openCheckpointUnit('East Checkpoint','East')`);
  assert.equal(run('cpLocationFilter'), 'East');
  signIn('CheckpointSouth', ['dashboard', 'people', 'checkpoints'], false, { location_scope: 'South' });
  console.log('ok: an admin unit click switches the checkpoint register to that unit');

  // ---- 5) Unit Directory ------------------------------------------------
  run(`openUnitDirectory('checkpoint')`);
  assert.equal($('unitDir').classList.contains('open'), true, 'the directory opens in a modal');
  assert.ok($('udUnitType').value === 'checkpoint');
  // Unit types are limited to the modules this session holds.
  assert.deepEqual(queryAll('#udUnitType option').map((o) => o.value), ['checkpoint'],
    'a checkpoint officer must not browse units from modules they cannot read');
  const regionOptions = queryAll('#udRegion option').map((o) => o.value);
  assert.deepEqual(regionOptions, ['', 'East Togdheer', 'Sool']);
  assert.equal(queryAll('#udTable tr').length, 4);
  // Region filter → districts narrow to that region, rows follow.
  $('udRegion').value = 'Sool';
  run(`populateUnitDirectoryDistricts();renderUnitDirectory();`);
  assert.deepEqual(queryAll('#udDistrict option').map((o) => o.value),
    ['', 'Laascaanood', 'Xudun']);
  assert.equal(queryAll('#udTable tr').length, 2, 'the region filter must narrow the rows');
  $('udDistrict').value = 'Xudun';
  run(`renderUnitDirectory()`);
  assert.equal(queryAll('#udTable tr').length, 1);
  assert.ok($('udTable').textContent.includes('Yagoori'));
  $('udSearch').value = 'buuhoodle';
  run(`renderUnitDirectory()`);
  assert.equal(queryAll('#udTable tr').length, 0, 'district + search are ANDed');
  assert.equal($('udEmpty').style.display, '', 'the empty state explains the dead end');
  $('udSearch').value = '';
  $('udDistrict').value = '';
  $('udRegion').value = '';
  run(`renderUnitDirectory()`);
  assert.equal(queryAll('#udTable tr').length, 4);
  run(`closeEntryModal('unitDir')`);
  console.log('ok: Unit Directory filters by region, district and free text');

  // A Commander (read-only) may browse the directory; it is a read surface.
  signIn('chief_commander', ['dashboard', 'fingerprint', 'airport', 'cid', 'checkpoints',
    'executive', 'oversight'], false, {});
  run(`openUnitDirectory('checkpoint')`);
  assert.equal($('unitDir').classList.contains('open'), true,
    'a read-only Commander must be able to browse the unit directory');
  run(`closeEntryModal('unitDir')`);
  console.log('ok: the directory stays a read-only surface for a Commander session');

  // ---- 6) restore ordering ----------------------------------------------
  signIn('FingerprintUnit', ['dashboard', 'people', 'fingerprint']);
  signIn('CheckpointSouth', ['dashboard', 'people', 'checkpoints']);
  const cpGroupBody = query('#nav .nav-group-body[data-group-body="checkpoints"]');
  const checkpointLink = query('#nav [data-page="checkpoints"]');
  const label = query('#nav [data-module-label="checkpoints"]');
  assert.equal(label.nextElementSibling, checkpointLink,
    'a restored checkpoint link sits directly under its subgroup label');
  assert.ok(cpGroupBody.children.length >= 3);
  assert.equal(cpGroupBody.lastElementChild.id, 'cpNavRegions',
    'the runtime sub-menu stays at the bottom of the accordion');
  console.log('ok: denied entries are removed and restored into their authored slot');

  // ---- 7) category + accordion collapse and navigation ------------------
  run(`setNavSectionOpen('operational-units',false)`);
  assert.equal(sectionOf('operational-units').querySelector('.nav-section-toggle')
    .getAttribute('aria-expanded'), 'false');
  run(`toggleNavSection('operational-units')`);
  assert.equal(sectionOf('operational-units').classList.contains('open'), true);
  assert.equal(JSON.parse(w.localStorage.getItem('sentinelNavSections'))['operational-units'], true);
  run(`setNavSectionOpen('operational-units',false)`);
  // Opening a page expands the category and the accordion that own it.
  run(`go('checkpoints')`);
  assert.equal(sectionOf('operational-units').classList.contains('open'), true);
  assert.equal(query('#nav .nav-group[data-group="checkpoints"]').classList.contains('open'), true);
  console.log('ok: navigating expands the owning category and accordion');

  // Every link navigates once the role is allowed to hold it.
  signIn('SystemAdmin', ALL_MODULES, true);
  const failures = [];
  queryAll('#nav button[data-page]').forEach((btn) => {
    const page = btn.dataset.page;
    if (!$(page)) { failures.push(`${page}: no page section`); return; }
    try { run(`go(${JSON.stringify(page)})`); } catch (_) { /* renderers may need the API */ }
    if (!$(`${page}`).classList.contains('active')) failures.push(`${page}: did not open`);
    const group = query('#nav .nav-group.open button[data-page="' + page + '"]');
    if (btn.closest('.nav-group') && !group) failures.push(`${page}: owning accordion stayed collapsed`);
    const sec = btn.closest('.nav-section');
    if (sec && !sec.classList.contains('open')) failures.push(`${page}: owning category stayed collapsed`);
  });
  assert.deepEqual(failures, [], 'every navigation link must remain functional');
  console.log('ok: every navigation link opens its page and reveals its category');

  // ---- 8) short-label helper -------------------------------------------
  assert.equal(run(`shortUnitLabel('Buuhoodle Border Crossing Checkpoint')`),
    'Buuhoodle Border C…');
  assert.equal(run(`shortUnitLabel('Lasanod Branch')`), 'Lasanod');
  assert.ok(run(`shortUnitLabel('A very long unit name that would wrap the rail').length`) <= 20);
  assert.ok(run(`shortUnitLabel('X')`).length >= 1);
  console.log('ok: short unit labels strip administrative suffixes and never wrap the rail');

  console.log('PASS: hierarchical sidebar, RBAC gates and scalable unit directory');
} finally {
  // Let pending render promises (page painters fired by go()) settle before the
  // window is torn down, so a late repaint cannot throw after the suite passes.
  await new Promise((resolve) => setTimeout(resolve, 120));
  w.close();
}
