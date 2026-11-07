#!/usr/bin/env node
/**
 * WP-45g — the biometric matcher must never fabricate an identification.
 *
 * NEGATIVE regression test for finding FPR-902 / SR-22.
 *
 * Before this work package, matchPersonByFingerprint() accepted a third
 * argument `allowFallbackScan`. When every real comparison failed, it did:
 *
 *     const captured = list.filter(p => ...status==='captured');
 *     const pool = captured.length ? captured : list;
 *     const idx  = (window._bioScanCursor || 0) % pool.length;
 *     window._bioScanCursor = idx + 1;
 *     return pool[idx] || list[0];
 *
 * i.e. it returned an ARBITRARY person by rotating a cursor through the
 * registry, and four call sites — including the "live scan" and the Central
 * Person Registry scan — passed `true` and then announced
 * "Biometric Fingerprint Match Found — Linked to Central Person Record #…".
 *
 * At a checkpoint that is a wrongful-identification, and therefore a
 * potential wrongful-detention, path.
 *
 * These tests pin the corrected behaviour. They are deliberately written so
 * that reintroducing ANY form of guessing — rotation, positional pick,
 * nearest neighbour or "first record" default — fails the suite.
 *
 * Scope note: this is still identifier STRING matching, not biometric
 * template comparison. Genuine matching is WP-45a..f and is not implemented;
 * these tests only prove the system does not lie about a match.
 *
 * Usage:  node backend/test_biometric_no_fabricated_match.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const dom = new JSDOM(html, { url: 'http://sentinel.test', runScripts: 'outside-only' });
const w = dom.window;
const ctx = dom.getInternalVMContext();
w.HTMLElement.prototype.scrollIntoView = function () {};
w.fetch = async () => { throw new Error('Unexpected network call'); };
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/if\(document\.readyState==='loading'\)[\s\S]*$/, '');
vm.runInContext(script, ctx);
const run = (code) => vm.runInContext(code, ctx);

// A registry of three people with captured biometrics, none of which matches
// the probes used below.
run(`
  sessionUser={role:'FingerprintUnit'};
  currentUser=sessionUser;
  guardReadOnly=()=>false;
  renderAll=()=>{};
  renderPeople=()=>{};
  syncServer=async()=>{};
  toast=()=>{};
  persist=()=>{};
  db.people=[
    {id:'P-0001',name:'Ayaan Cabdi Xasan Axmed',first:'Ayaan',second:'Cabdi',third:'Xasan',
     fourth:'Axmed',nationalId:'10012345',passportId:'P0011223',dob:'1997-04-18',
     motherName:'Faadumo Cali',fingerprintStatus:'captured',
     fingerprintHash:'BIO-P0001-10012345',fingerprintFile:'ayaan-right-thumb.wsq'},
    {id:'P-0002',name:'Maxamed Nuur Cali Awil',first:'Maxamed',second:'Nuur',third:'Cali',
     fourth:'Awil',nationalId:'10067890',passportId:'',dob:'1989-11-02',
     motherName:'Khadra Jaamac',fingerprintStatus:'captured',
     fingerprintHash:'BIO-P0002-10067890',fingerprintFile:'maxamed-right-thumb.wsq'},
    {id:'P-0003',name:'Sahra Yuusuf Axmed Aadan',first:'Sahra',second:'Yuusuf',third:'Axmed',
     fourth:'Aadan',nationalId:'10024680',passportId:'',dob:'2001-02-26',
     motherName:'Amina Maxamed',fingerprintStatus:'captured',
     fingerprintHash:'BIO-P0003-10024680',fingerprintFile:'sahra-right-thumb.wsq'}
  ];
`);

let checks = 0;
const ok = (msg) => { checks += 1; console.log('ok ' + checks + ': ' + msg); };

// ---------------------------------------------------------------- 1 -------
// The fabricating code must not exist in the shipped file at all. Comment
// lines are stripped first: the fix deliberately documents what was removed,
// and that prose must not be mistaken for live code.
const codeOnly = script
  .split('\n')
  .filter((line) => !line.trim().startsWith('//'))
  .join('\n');
assert.ok(!/allowFallbackScan/.test(codeOnly),
  'the allowFallbackScan parameter must be gone from index.html');
assert.ok(!/_bioScanCursor/.test(codeOnly),
  'the rotating scan cursor must be gone from index.html');
assert.ok(!/pool\[idx\]/.test(codeOnly),
  'the positional "pick a person from the pool" fallback must be gone');
ok('index.html code contains no allowFallbackScan, _bioScanCursor or pool[idx]');

// ---------------------------------------------------------------- 2 -------
// The matcher takes exactly two parameters — no re-added opt-in flag.
const arity = run('matchPersonByFingerprint.length');
assert.equal(arity, 2,
  `matchPersonByFingerprint must take exactly (queryOrFile, draft); got arity ${arity}`);
ok('matchPersonByFingerprint exposes no third "allow fallback" parameter');

// ---------------------------------------------------------------- 3 -------
// An unknown probe returns null — not a person.
for (const probe of [
  'BIO-UNKNOWN-99999999',
  'completely-unrelated-string',
  'ZZZZZZZZ',
  'scan-from-a-person-not-in-the-registry.wsq',
]) {
  const result = run(`matchPersonByFingerprint(${JSON.stringify(probe)},null)`);
  assert.equal(result, null,
    `probe ${probe} must return null, got ${JSON.stringify(result)}`);
}
ok('unknown probes return null, never a person');

// ---------------------------------------------------------------- 4 -------
// Repeated identical unknown probes stay null. A rotating cursor would start
// returning different people here; this is the specific regression guard.
const repeated = [];
for (let i = 0; i < 10; i += 1) {
  repeated.push(run(`matchPersonByFingerprint('BIO-STILL-UNKNOWN',null)`));
}
assert.ok(repeated.every((r) => r === null),
  'repeated unknown probes must ALL return null — a rotating fallback would '
  + 'return different people on successive calls: '
  + JSON.stringify(repeated.map((r) => (r && r.id) || null)));
ok('ten successive unknown probes all return null (no rotation)');

// ---------------------------------------------------------------- 5 -------
// An empty probe with no draft must not select anybody.
assert.equal(run(`matchPersonByFingerprint('',null)`), null,
  'an empty probe must not match anyone');
assert.equal(run(`matchPersonByFingerprint(null,null)`), null,
  'a null probe must not match anyone');
assert.equal(run(`matchPersonByFingerprint('',{first:'',second:'',third:'',fourth:''})`), null,
  'an empty draft must not match anyone');
ok('empty and null probes match nobody');

// ---------------------------------------------------------------- 6 -------
// Genuine identifier matches still work — the fix must not break real hits.
const byHash = run(`matchPersonByFingerprint('BIO-P0002-10067890',null)`);
assert.equal(byHash && byHash.id, 'P-0002', 'a real biometric-hash probe must still match');
const byNational = run(`matchPersonByFingerprint('arrived with id 10024680',null)`);
assert.equal(byNational && byNational.id, 'P-0003', 'a real national-ID probe must still match');
const byFile = run(`matchPersonByFingerprint('ayaan-right-thumb.wsq',null)`);
assert.equal(byFile && byFile.id, 'P-0001', 'a real biometric-file probe must still match');
ok('genuine identifier matches are preserved (hash, national ID, file)');

// ---------------------------------------------------------------- 7 -------
// A non-matching probe against a registry where NOBODY has captured
// biometrics still returns null. The old fallback used `list` as the pool in
// exactly this case, so this is the second regression guard.
run(`db.people=db.people.map(p=>({...p,fingerprintStatus:'none',
  fingerprintHash:'',fingerprintFile:''}));`);
for (let i = 0; i < 5; i += 1) {
  assert.equal(run(`matchPersonByFingerprint('BIO-NOBODY-HAS-PRINTS',null)`), null,
    'with no captured biometrics the matcher must still return null');
}
ok('no captured biometrics + unknown probe still returns null');

// ---------------------------------------------------------------- 8 -------
// The UI reports the negative result instead of staying silent.
run(`
  db.people=[{id:'P-0001',name:'Ayaan Cabdi Xasan Axmed',first:'Ayaan',second:'Cabdi',
              third:'Xasan',fourth:'Axmed',nationalId:'10012345',
              fingerprintStatus:'captured',fingerprintHash:'BIO-P0001-10012345'}];
  document.body.insertAdjacentHTML('beforeend',
    '<input id="central-fpCode" value="BIO-NO-SUCH-PRINT">'
    + '<div id="central-fpAlert"></div>');
`);
run(`simulateBiometricScan('central')`);
const alertHtml = run(`document.getElementById('central-fpAlert').innerHTML`);
assert.match(alertHtml, /No match in the Central Person Registry/i,
  'a failed scan must tell the officer no match was found');
assert.match(alertHtml, /No identity has been assigned/i,
  'a failed scan must state that no identity was assigned');
const alertClass = run(`document.getElementById('central-fpAlert').className`);
assert.match(alertClass, /warn/, 'the no-match banner must be a warning, not a success');
ok('a failed scan reports "no match" and assigns no identity');

// ---------------------------------------------------------------- 9 -------
// The failed scan must not have written a person reference anywhere.
const highlighted = run(`window._highlightedPersonId || ''`);
assert.equal(highlighted, '',
  'a failed scan must not highlight / select any person record');
ok('a failed scan leaves no person selected');

console.log(`\nALL BIOMETRIC NO-FABRICATED-MATCH TESTS PASSED (${checks} checks)`);
