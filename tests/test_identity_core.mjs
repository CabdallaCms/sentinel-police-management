// Node tests for the pure UI logic (web/identity-core.js).   Run: node tests/test_identity_core.mjs
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const I = require('../web/identity-core.js');

let n = 0;
const t = (name, fn) => { fn(); n++; console.log('ok -', name); };

const person = (over = {}) => ({
  person_ref: 'P-2026-000001', full_name: 'Ayaan Cabdi Xasan Axmed', first_name: 'Ayaan', second_name: 'Cabdi',
  third_name: 'Xasan', fourth_name: 'Axmed', date_of_birth: '1990-05-17', place_of_birth: 'Laascaanood',
  national_id: 'SO1001', passport_id: null, mother_name: 'Hodan Cali', phone: null, residence: null, occupation: null,
  registered_at: { code: 'DIR-FP', name: 'Fingerprint & Clearance Directorate' },
  missing_fields: [{ field: 'residence', label: 'Address' }, { field: 'phone', label: 'Phone' }],
  field_states: {
    first_name: { state: 'locked', mutability: 'core' }, second_name: { state: 'locked', mutability: 'core' },
    third_name: { state: 'locked', mutability: 'core' }, fourth_name: { state: 'locked', mutability: 'core' },
    date_of_birth: { state: 'locked', mutability: 'core' }, place_of_birth: { state: 'locked', mutability: 'core' },
    national_id: { state: 'locked', mutability: 'identifier' }, passport_id: { state: 'fillable', mutability: 'identifier' },
    mother_name: { state: 'locked', mutability: 'protected' }, phone: { state: 'fillable', mutability: 'dynamic' },
    residence: { state: 'fillable', mutability: 'dynamic' }, occupation: { state: 'fillable', mutability: 'dynamic' } },
  ...over });

t('exists -> green "Person already exists in registry" banner with the record and unit', () => {
  const b = I.bannerModel({ status: 'exists', tier: 1, tier_label: 'Tier 1', reason: 'Exact National ID / Passport match',
    person: person(), core_differences: [], conflicts: [], has_active_alert: false });
  assert.equal(b.kind, 'ok');
  assert.equal(b.title, 'Person already exists in registry');
  assert.equal(b.headline, 'P-2026-000001 · Ayaan Cabdi Xasan Axmed');
  assert.ok(b.lines.some(l => l.includes('Fingerprint & Clearance Directorate')));
  assert.ok(b.extra.some(e => e.kind === 'incomplete' && e.text.includes('Address, Phone')));
  assert.equal(b.chips.length, 0);
});
t('active alert shows a red yes/no chip, never case detail', () => {
  const b = I.bannerModel({ status: 'exists', person: person(), reason: 'x', has_active_alert: true });
  assert.deepEqual(b.chips.map(c => c.kind), ['danger']);
});
t('typed-differently locked values are surfaced, not silently kept', () => {
  const b = I.bannerModel({ status: 'exists', person: person(), reason: 'x',
    core_differences: [{ field: 'date_of_birth', stored: '1990-05-17', entered: '1991-05-17' }] });
  const d = b.extra.find(e => e.kind === 'diff');
  assert.match(d.text, /Date of birth entered as "1991-05-17" but the registry has "1990-05-17"/);
});
t('possible duplicate -> amber warning, not an automatic match', () => {
  const b = I.bannerModel({ status: 'confirm', person: person(), reason: 'Similar name', conflicts: [] });
  assert.equal(b.kind, 'warn');
  assert.match(b.title, /Possible duplicate/);
});
t('suggestions -> blue info; new -> "No existing record"; empty input -> no banner', () => {
  assert.equal(I.bannerModel({ status: 'suggestions', reason: 'r', candidates: [{}] }).kind, 'info');
  assert.equal(I.bannerModel({ status: 'new', candidates: [], reason: 'No existing record found — a new person record will be created.' }).title, 'No existing record');
  assert.equal(I.bannerModel({ status: 'new', candidates: [], reason: 'Enter a name, National ID or Passport.' }), null);
});
t('lookup failure is reported, not swallowed', () => {
  assert.equal(I.bannerModel({ error: 'permission_denied', message: 'nope' }).kind, 'warn');
});
t('form plan locks exactly what the server says is locked (core + set identifiers + mother)', () => {
  const plan = I.formPlan(person());
  for (const f of ['first_name', 'second_name', 'third_name', 'fourth_name', 'date_of_birth', 'place_of_birth', 'national_id', 'mother_name']) {
    assert.equal(plan[f].readonly, true, f); assert.equal(plan[f].padlock, true, f);
  }
  for (const f of ['passport_id', 'phone', 'residence', 'occupation']) assert.equal(plan[f].readonly, false, f);
});
t('a blank core field is NOT padlocked (can be completed once)', () => {
  const p = person({ place_of_birth: null });
  p.field_states.place_of_birth = { state: 'fillable', mutability: 'core' };
  const plan = I.formPlan(p);
  assert.equal(plan.place_of_birth.readonly, false); assert.equal(plan.place_of_birth.padlock, false);
});
t('national admin sees core fields editable with an audit note', () => {
  const p = person(); Object.values(p.field_states).forEach(s => { s.state = 'editable'; });
  const plan = I.formPlan(p);
  assert.equal(plan.first_name.readonly, false);
  assert.match(plan.first_name.note, /reason/);
});
t('patch diff sends only changed, permitted fields; locked attempts are reported as blocked', () => {
  const values = { first_name: 'Nuur', second_name: 'Cabdi', date_of_birth: '1990-05-17', national_id: ' so1001 ',
    residence: 'Burao', occupation: '', phone: '+252 63', passport_id: 'A1' };
  const d = I.diffForPatch(person(), values);
  assert.deepEqual(d.changes, { residence: 'Burao', phone: '+252 63', passport_id: 'A1' });
  assert.deepEqual(d.blocked, ['first_name']);
  assert.deepEqual(d.coreChanged, []);
});
t('posting the whole unchanged form produces an empty patch', () => {
  const p = person(); const values = Object.fromEntries(I.FIELDS.map(f => [f, p[f] || '']));
  assert.deepEqual(I.diffForPatch(p, values), { changes: {}, coreChanged: [], blocked: [] });
});
t('admin core change is flagged so the UI asks for a reason', () => {
  const p = person(); Object.values(p.field_states).forEach(s => { s.state = 'editable'; });
  const d = I.diffForPatch(p, { first_name: 'Ayaana', second_name: 'Cabdi' });
  assert.deepEqual(d.coreChanged, ['first_name']);
});
t('validation mirrors the server (3 names, DoB, an ID unless minor)', () => {
  assert.equal(I.validateNew({}, {}).length, 5);
  assert.equal(I.validateNew({ first_name: 'a', second_name: 'b', third_name: 'c', date_of_birth: '2000-01-01', national_id: 'x' }, {}).length, 0);
  assert.equal(I.validateNew({ first_name: 'a', second_name: 'b', third_name: 'c', date_of_birth: '2000-01-01' }, { allowNoId: true }).length, 0);
  assert.equal(I.validateNew({ first_name: 'a', second_name: 'b', third_name: 'c' }, { requireDob: false, allowNoId: true }).length, 0);
});
t('payload drops blanks and collapses whitespace', () => {
  assert.deepEqual(I.personPayload({ first_name: '  Ayaan  ', second_name: '', national_id: 'x y' }, { confirm_new: true }),
    { person: { first_name: 'Ayaan', national_id: 'x y' }, confirm_new: true });
});
t('result summary distinguishes linked vs created and lists locked leftovers', () => {
  assert.match(I.resultSummary({ created: true, person: { person_ref: 'P-1' } }), /New person registered: P-1/);
  const s = I.resultSummary({ created: false, exists: true, person: { person_ref: 'P-1' }, filled: ['residence'],
    updated: ['phone'], ignored: [{ field: 'date_of_birth' }] });
  assert.match(s, /no duplicate was created/); assert.match(s, /Added: Address/); assert.match(s, /Not changed \(locked\): Date of birth/);
});
t('html is escaped', () => assert.equal(I.esc('<img src=x onerror=1>"\''), '&lt;img src=x onerror=1&gt;&quot;&#39;'));

console.log(`\n${n} passed`);
