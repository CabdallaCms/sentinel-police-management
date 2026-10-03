// Drives the REAL page (web/index.html + identity-intake.js) against the REAL API and database.
// Started by:  python -m tests.run_ui_flow   (it provides BASE_URL and a seeded database)
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(path.join(process.env.JSDOM_DIR || '.', 'x.js'));
const { JSDOM } = require('jsdom');
const BASE = process.env.BASE_URL;

const dom = await JSDOM.fromURL(BASE + '/', {
  runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
  beforeParse(w) {
    w.fetch = (u, o) => fetch(new URL(u, BASE), o);
    w.Element.prototype.scrollIntoView = () => {};
  },
});
const w = dom.window, d = w.document;
const $ = s => d.querySelector(s);
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, what, ms = 4000) {
  const t0 = Date.now();
  for (;;) {
    let v; try { v = fn(); } catch (_) { v = null; }
    if (v) return v;
    if (Date.now() - t0 > ms) throw new Error('timeout waiting for: ' + what + '\n' + $('body').textContent.replace(/\s+/g, ' ').slice(0, 600));
    await sleep(40);
  }
}
const type = (sel, val) => { const el = $(sel); el.value = val; el.dispatchEvent(new w.Event('input', { bubbles: true })); };
const click = sel => $(sel).dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
async function choose(sel, val) { const el = $(sel); el.value = val; el.dispatchEvent(new w.Event('change', { bubbles: true })); }
async function api(path, user = 'admin', opts = {}) {
  const r = await fetch(BASE + path, { ...opts, headers: { 'X-Dev-User': user, 'Content-Type': 'application/json', ...(opts.headers || {}) } });
  return r.json();
}
const banner = () => $('#p-match');
const gbanner = () => $('#g-match');
let n = 0;
const step = async (name, fn) => { await fn(); n++; console.log('ok -', name); };
async function signIn(user, unit) {
  await waitFor(() => $('#user').options.length > 2, 'user list');
  $('#who').textContent = ''; $('#unit').innerHTML = '';          // forget the previous user's state so we wait for a FRESH load
  await choose('#user', user);
  await waitFor(() => /./.test($('#who').textContent) && $('#unit').options.length > 1, 'units for ' + user);
  if (unit) await choose('#unit', unit);
}
async function reset() { click('#new-btn'); await sleep(30); }

await step('page loads, dev users are listed, officer signs in at the airport unit', async () => {
  assert.match($('title').textContent, /Central Person Registry/);
  await signIn('ap.officer');
  assert.equal($('#unit').value, 'AP-LAA');
  assert.doesNotMatch($('#who').textContent, /National Admin|read-only/);
});

await step('typing an existing National ID shows the "Person already exists in registry" banner and auto-selects', async () => {
  type('#p-national_id', ' so-100001 ');
  await waitFor(() => banner().classList.contains('ok') && banner().classList.contains('show'), 'ok banner');
  assert.match(banner().textContent, /Person already exists in registry/);
  assert.match(banner().textContent, /P-\d{4}-\d{6} · Ayaan Cabdi Xasan Axmed/);
  assert.match(banner().textContent, /First registered at Fingerprint/);
  assert.match(banner().textContent, /Exact National ID/);
  assert.equal($('#save-btn').textContent.startsWith('Save updates to P-'), true);
});

await step('core identity fields are filled from the registry and LOCKED; dynamic fields stay editable', async () => {
  for (const f of ['first_name', 'second_name', 'third_name', 'fourth_name', 'date_of_birth', 'place_of_birth', 'national_id', 'mother_name']) {
    const el = $('#p-' + f);
    assert.equal(el.readOnly, true, f + ' should be read-only');
    assert.ok(el.classList.contains('locked'), f + ' should look locked');
    assert.ok(el.value, f + ' should be filled');
  }
  assert.equal($('#p-first_name').value, 'Ayaan');
  assert.equal($('#p-date_of_birth').value, '1990-05-17');
  assert.ok($('#p-first_name-wrap').classList.contains('is-locked'));
  for (const f of ['residence', 'phone', 'occupation', 'passport_id']) assert.equal($('#p-' + f).readOnly, false, f + ' should be editable');
});

await step('the officer enriches a blank field and updates a dynamic field; the save is a field-level PATCH', async () => {
  type('#p-passport_id', 'a 7654321');                 // blank in the registry -> enrichment (fill)
  type('#p-phone', '+252 63 999 0000');                // already set -> dynamic update
  type('#p-occupation', 'Pilot');
  click('#save-btn');
  await waitFor(() => $('#p-result').classList.contains('good'), 'good result');
  assert.match($('#p-result').textContent, /Added: Passport ID/);
  assert.match($('#p-result').textContent, /Updated: Phone, Occupation/);
  const found = await api('/api/persons/search?q=SO-100001', 'ap.officer');
  assert.equal(found.person.occupation, 'Pilot');
  assert.equal(found.person.phone, '+252 63 999 0000');
  assert.equal(found.person.passport_id, 'A 7654321');
  assert.equal(found.person.first_name, 'Ayaan');
});

await step('a typed date of birth that disagrees with the registry is reported and the registry value is kept', async () => {
  await reset();
  for (const [f, v] of [['first_name', 'Ayaan'], ['second_name', 'Cabdi'], ['third_name', 'Xasan']]) type('#p-' + f, v);
  type('#p-date_of_birth', '1991-05-17');
  type('#p-national_id', 'SO100001');
  await waitFor(() => banner().classList.contains('ok'), 'ok banner');
  assert.match(banner().textContent, /Date of birth entered as "1991-05-17" but the registry has "1990-05-17"/);
  assert.equal($('#p-date_of_birth').value, '1990-05-17');
  assert.equal($('#p-date_of_birth').readOnly, true);
});

await step('a locked field cannot be edited by typing into it (read-only attribute)', async () => {
  assert.equal($('#p-first_name').readOnly, true);
  assert.equal($('#p-first_name').getAttribute('aria-readonly'), 'true');
});

await step('a fuzzy "possible duplicate" is an amber warning with a pick list, never an automatic link', async () => {
  await reset();
  for (const [f, v] of [['first_name', 'Ayaan'], ['second_name', 'Cabdii'], ['third_name', 'Xasan'], ['fourth_name', 'Ahmed']]) type('#p-' + f, v);
  type('#p-mother_name', 'hodan cali faarax');
  await waitFor(() => banner().classList.contains('warn') && $('#p-matchlist').classList.contains('show'), 'warn banner + list');
  assert.match(banner().textContent, /Possible duplicate/);
  assert.equal($('#p-first_name').readOnly, false);                 // nothing was auto-selected or locked
  assert.equal($('#save-btn').textContent, 'Register person');
  click('#p-matchlist .m-item[data-i="0"]');                          // officer confirms it is the same person
  await waitFor(() => banner().classList.contains('ok'), 'selected');
  assert.equal($('#p-second_name').value, 'Cabdi');                   // registry spelling replaces the typo
  assert.equal($('#p-second_name').readOnly, true);
});

await step('"It is a different person" unlocks the form and registers a NEW record', async () => {
  await reset();
  for (const [f, v] of [['first_name', 'Ayaan'], ['second_name', 'Cabdii'], ['third_name', 'Xasan'], ['fourth_name', 'Ahmed']]) type('#p-' + f, v);
  type('#p-mother_name', 'hodan cali faarax');
  await waitFor(() => $('#p-matchlist').classList.contains('show'), 'list');
  click('#p-matchlist .m-item.m-new');
  await waitFor(() => /Creating a new person/.test(banner().textContent), 'new-person banner');
  type('#p-date_of_birth', '1995-02-02');
  type('#p-national_id', 'SO-777001');
  type('#p-residence', 'Burao');
  click('#save-btn');
  await waitFor(() => $('#p-result').classList.contains('good'), 'created');
  assert.match($('#p-result').textContent, /New person registered: P-/);
  assert.equal($('#p-second_name').value, 'Cabdii');
  assert.equal($('#p-second_name').readOnly, true);                    // once registered, it is locked too
});

await step('client-side validation highlights what is missing and sends nothing', async () => {
  await reset();
  type('#p-first_name', 'Zeynab');
  click('#save-btn');
  await waitFor(() => $('#p-result').classList.contains('bad'), 'validation message');
  assert.match($('#p-result').textContent, /Second name is required/);
  assert.ok($('#p-second_name-wrap').classList.contains('invalid'));
  assert.ok($('#p-date_of_birth-wrap').classList.contains('invalid'));
});

await step('the central search box finds a child, loads the record and prompts for the missing guardian', async () => {
  await reset();
  type('#q', 'Hodan Nuur Cali');
  await waitFor(() => $('#q-out tr.pick'), 'search results');
  assert.match($('#q-out').textContent, /Hodan Nuur Cali/);
  click('#q-out tr.pick');
  await waitFor(() => !$('#guardian-panel').classList.contains('hidden'), 'guardian panel');
  assert.match($('#g-hint').textContent, /8 years old and has no guardian on record/);
  assert.equal($('#p-first_name').value, 'Hodan');
  assert.equal($('#p-first_name').readOnly, true);
});

await step('a guardian is added at the airport on a later visit, creating a linked person record', async () => {
  for (const [f, v] of [['first_name', 'Cabdi'], ['second_name', 'Faarax'], ['third_name', 'Cali']]) type('#g-' + f, v);
  type('#g-national_id', 'SO-900900');
  type('#g-phone', '+252 63 111');
  type('#g-occupation', 'Trader');
  await choose('#g-relationship', 'Parent');
  await waitFor(() => /No existing record/.test(gbanner().textContent), 'guardian lookup');
  click('#g-save-btn');
  await waitFor(() => $('#g-result').classList.contains('good'), 'guardian result');
  assert.match($('#g-result').textContent, /Guardian added: Cabdi Faarax Cali/);
  assert.match($('#g-list').textContent, /Cabdi Faarax Cali · Parent/);
  assert.doesNotMatch($('#g-hint').textContent, /no guardian on record/);
});

await step('the same guardian typed for a sibling is recognised ("already exists"), not duplicated', async () => {
  await reset();
  type('#q', 'Hodan Nuur Cali'); await waitFor(() => $('#q-out tr.pick'), 'results');
  click('#q-out tr.pick'); await waitFor(() => !$('#guardian-panel').classList.contains('hidden'), 'panel');
  type('#g-national_id', 'so900900');
  await waitFor(() => gbanner().classList.contains('ok'), 'guardian exists banner');
  assert.match(gbanner().textContent, /Person already exists in registry/);
  assert.equal($('#g-first_name').value, 'Cabdi');
  assert.equal($('#g-first_name').readOnly, true);
});

await step('read-only Chief Commander cannot save', async () => {
  await signIn('chief');
  assert.equal($('#save-btn').disabled, true);
  assert.match($('#who').textContent, /read-only/);
});

await step('National Admin sees core fields editable, must give a reason, and the change is audited', async () => {
  await signIn('admin');
  assert.match($('#who').textContent, /National Admin/);
  await reset();
  type('#q', 'SO-777001'); await waitFor(() => $('#q-out tr.pick'), 'results');
  click('#q-out tr.pick'); await waitFor(() => $('#save-btn').textContent.startsWith('Save updates'), 'loaded');
  assert.equal($('#p-first_name').readOnly, false);
  assert.match($('#p-first_name-note').textContent, /reason/);
  type('#p-first_name', 'Ayaana');
  click('#save-btn');
  await waitFor(() => $('#p-result').classList.contains('bad'), 'reason required');
  assert.match($('#p-result').textContent, /Enter the reason/);
  assert.equal($('#reason-row').classList.contains('hidden'), false);
  type('#reason', 'Birth certificate spelling');
  click('#save-btn');
  await waitFor(() => $('#p-result').classList.contains('good'), 'core change saved');
  assert.match($('#p-result').textContent, /Updated: First name/);
  const p = await api('/api/persons/search?q=SO-777001', 'admin');
  assert.equal(p.person.full_name, 'Ayaana Cabdii Xasan Ahmed');
});

await step('a regular officer still cannot touch that same field', async () => {
  await signIn('ap.officer');
  await reset();
  type('#p-national_id', 'SO777001');
  await waitFor(() => banner().classList.contains('ok'), 'exists');
  assert.equal($('#p-first_name').readOnly, true);
  assert.equal($('#p-first_name').value, 'Ayaana');
});

console.log(`\n${n} UI steps passed`);
process.exit(0);
