#!/usr/bin/env node
// Fingerprint-only regional hard-pruning and paint-cache regression tests.
//   node backend/test_fingerprint_nav_scope.mjs
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://sentinel.test', runScripts: 'outside-only' });
const w = dom.window;
const ctx = dom.getInternalVMContext();
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/if\(document\.readyState==='loading'\)[\s\S]*$/, '');
vm.runInContext(script, ctx);
const run = source => vm.runInContext(source, ctx);
const mount = w.document.querySelector('[data-nav-regions="fingerprint"]');
const regionLabels = () => [...mount.querySelectorAll('.nav-region')].map(el => el.dataset.navRegion);
const branchLabels = () => [...mount.querySelectorAll('.nav-unit')].map(el => el.dataset.unitLabel);

const branches = [
  { id: 'fp-sool', name: 'Lasanod Branch', region: 'Sool', district: 'Laascaanood', unit_type: 'fingerprint' },
  // Same geography, but a different unit identity must not leak into this officer's tree.
  { id: 'fp-sool-foreign', name: 'Laascaanood Records Desk', region: 'Sool', district: 'Laascaanood', unit_type: 'fingerprint' },
  { id: 'fp-sool-other-district', name: 'Xudun Branch', region: 'Sool', district: 'Xudun', unit_type: 'fingerprint' },
  { id: 'fp-sanaag', name: 'Erigavo Branch', region: 'Sanaag', district: 'Ceerigaabo', unit_type: 'fingerprint' },
  { id: 'fp-east', name: 'Burao Branch', region: 'East Togdheer', district: 'Burao', unit_type: 'fingerprint' },
  { id: 'fp-unassigned', name: 'Unassigned Fingerprint Desk', region: '', district: '', unit_type: 'fingerprint' },
  // Other units can share the officer's region but never enter the fingerprint tree.
  { id: 'crime-sool', name: 'Sool CID Office', region: 'Sool', district: 'Laascaanood', unit_type: 'crime' },
];

function signIn(user) {
  run(`sessionUser=${JSON.stringify(user)};currentUser=sessionUser;
    sessionVisibility={is_admin:${user.role === 'SystemAdmin'},can_manage_records:${user.role === 'SystemAdmin'}};
    applyNavForRole();`);
}
run(`branchCatalog={loaded:true,items:${JSON.stringify(branches)},regions:[],unit_types:[],districts:[]};`);

// First paint a national admin tree. Then ensure the same mount is replaced,
// not reused, with the scoped officer's physically pruned Region → District tree.
signIn({ role: 'SystemAdmin', modules: ['dashboard', 'people', 'fingerprint'] });
run('renderUnitNavTree("fingerprint")');
const nationwideSignature = mount.dataset.navSig;
assert.deepEqual(regionLabels(), ['Sool', 'Sanaag', 'East Togdheer', 'Unassigned region']);

signIn({ role: 'FingerprintUnit', modules: ['dashboard', 'people', 'fingerprint'],
  branch: 'Lasanod Branch · Laascaanood · Sool' });
assert.deepEqual(JSON.parse(JSON.stringify(run('navUnitScope("fingerprint")'))),
  JSON.parse(JSON.stringify(run('fingerprintRegionalNavScope()'))),
  'navUnitScope dispatches Fingerprint through its dedicated regional resolver');
assert.notEqual(run('navUnitScope("crime")').branch_id, run('navUnitScope("fingerprint")').branch_id,
  'the scope is resolved within the requested unit, not borrowed across modules');
run('renderUnitNavTree("fingerprint")');
assert.deepEqual(regionLabels(), ['Sool'], 'foreign parent regions are removed from the DOM');
assert.deepEqual([...mount.querySelectorAll('.nav-district')].map(el => el.dataset.navDistrict),
  ['Laascaanood'], 'foreign and unassigned districts are removed from the DOM');
assert.deepEqual(branchLabels(), ['Lasanod Branch'],
  'a same-region foreign branch id cannot pass the fingerprint identity check');
assert.notEqual(mount.dataset.navSig, nationwideSignature,
  'the fingerprint paint cache signature includes officer scope');
assert.doesNotMatch(mount.innerHTML, /Sanaag|East Togdheer|Ceerigaabo|Burao|Unassigned/,
  'pruning happens before rendering, not by hiding rendered nodes');

// Changing to another Fingerprint branch must invalidate the cache even when
// the officer remains in the same region.
const firstOfficerSignature = mount.dataset.navSig;
signIn({ role: 'FingerprintUnit', modules: ['dashboard', 'people', 'fingerprint'],
  branch: 'Xudun Branch · Xudun · Sool' });
run('renderUnitNavTree("fingerprint")');
assert.notEqual(mount.dataset.navSig, firstOfficerSignature,
  'the cache key changes between two regional Fingerprint identities');
assert.deepEqual(branchLabels(), ['Xudun Branch']);
assert.deepEqual([...mount.querySelectorAll('.nav-district')].map(el => el.dataset.navDistrict), ['Xudun']);

// The scope helpers enforce ID-first rejection explicitly, independent of the
// catalogue paint path, including an impostor row sharing the exact geography.
const check = run(`fingerprintUnitInRegionalNavScope(
  {label:'Foreign',branch_id:'fp-sool-foreign',region:'Sool',district:'Laascaanood'},
  {branch_id:'fp-sool',branch_name:'Lasanod Branch',region:'Sool',district:'Laascaanood'})`);
assert.equal(check, false, 'foreign fingerprint branch IDs lose even with matching geography');
console.log('ok: Fingerprint regional hard-pruning, identity precedence, and scope-aware paint cache');
dom.window.close();
