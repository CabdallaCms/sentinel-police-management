#!/usr/bin/env node
/**
 * Reverse sequence column (`#`) — jsdom regression for every primary register.
 *
 * The registers render newest-first, so the leading number counts DOWN the
 * visible rows: the top row shows the filtered total and the bottom row shows
 * 1. These checks pin:
 *
 *   1. Fingerprint register — 4 rows read 4/3/2/1; the search box renumbers the
 *      filtered view; a newly added application increments the top number.
 *   2. Column integrity — every register's header cell count equals its body
 *      row cell count and the `#` cell is the first cell of each row, so no
 *      column (including Actions) shifted.
 *   3. Filtered numbering — the Central Person Registry and Registered Stations
 *      renumber from their own filtered result set, not the full register.
 *   4. Empty states — the placeholder row spans the new header (colspan bump).
 *   5. Police search — all three tabs (officers / stations / vehicles) carry the
 *      sequence column with the same reverse ordering.
 *
 * Usage:  npm install --no-save --package-lock=false jsdom@26
 *         node backend/test_reverse_sequence_ui.mjs
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
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/if\(document\.readyState==='loading'\)[\s\S]*$/, '');
vm.runInContext(script, ctx);
const run = (code) => vm.runInContext(code, ctx);
const $ = (id) => w.document.getElementById(id);

run(`
  sessionUser={role:'SystemAdmin'};
  currentUser=sessionUser; sessionVisibility={is_admin:true}; backendBuildChecked=true;
  guardReadOnly=()=>false; renderAll=()=>{}; persist=()=>{}; toast=()=>{};
  syncServer=async()=>{}; api=async()=>({items:[]});
  branchCatalog={loaded:false,items:[]};
  db.people=[
    {id:'P-1',name:'Ayaan Cabdi Xasan Axmed',dob:'1990-01-01',pob:'Sool',motherName:'Faadumo',
     nationalId:'N1',passportId:'',units:[]},
    {id:'P-2',name:'Maxamed Nuur Cali Awil',dob:'1991-02-02',pob:'Sanaag',motherName:'Hodan',
     nationalId:'N2',passportId:'',units:[]},
    {id:'P-3',name:'Sahra Yuusuf Axmed Aadan',dob:'1992-03-03',pob:'Sool',motherName:'Amina',
     nationalId:'N3',passportId:'',units:[]}
  ];
  db.fingerprint=[
    {id:'FP-4',person:'P-1',purpose:'Travel',status:'Pending Review',created_at:'2026-10-04 09:00'},
    {id:'FP-3',person:'P-2',purpose:'Education',status:'Approved',created_at:'2026-10-03 09:00'},
    {id:'FP-2',person:'P-3',purpose:'Employment',status:'Pending Review',created_at:'2026-10-02 09:00'},
    {id:'FP-1',person:'P-1',purpose:'Citizenship',status:'Approved',created_at:'2026-10-01 09:00'}
  ];
  db.airport=[{person:'P-1',move:'Arrival',date:'2026-10-01',flight:'AX1'},
              {person:'P-2',move:'Departure',date:'2026-10-02',flight:'AX2'}];
  db.cases=[{id:'CID-1',category:'Theft',location:'Sool',status:'Open',participants:[]},
            {id:'CID-2',category:'Fraud',location:'Sanaag',status:'Closed',participants:[]}];
  db.suspects=[{person:'P-1',case:'CID-1',role:'Suspect',alert:'Wanted'},
               {person:'P-3',case:'CID-2',role:'Witness',alert:'Cleared'}];
  db.checkpoints=[{event_id:'CP-1',time:'09:00',checkpoint_location:'South',person:'P-1',screen:'Clear',action:'Cleared'},
                  {event_id:'CP-2',time:'10:00',checkpoint_location:'East',person:'P-2',screen:'Clear',action:'Cleared'},
                  {event_id:'CP-3',time:'11:00',checkpoint_location:'West',person:'P-3',screen:'Clear',action:'Cleared'}];
  db.stations=[
    {id:'ST-1',name:'Las Anod Station',code:'SOO-C-01',region:'Sool',district:'Laascaanood',village:'Laascaanood'},
    {id:'ST-2',name:'Erigavo Station',code:'SAN-01',region:'Sanaag',district:'Erigavo',village:'Erigavo'},
    {id:'ST-3',name:'Burao Station',code:'TOG-01',region:'Togdheer',district:'Burao',village:'Burao'}
  ];
  db.officers=[
    {service_id:'SV-1',full_name:'Officer One',rank:'Sergeant',unit:'Police',station_id:'ST-1',duty_status:'On duty'},
    {service_id:'SV-2',full_name:'Officer Two',rank:'Inspector',unit:'Police',station_id:'ST-2',duty_status:'On duty'}
  ];
  db.cars=[
    {id:'V-1',plate:'AA-111',type:'Pickup',category:'Police Fleet',station:'ST-1',security_alert:'Clean / Normal'},
    {id:'V-2',plate:'BB-222',type:'Sedan',category:'Civilian / Commercial',owner_full_name:'Owner',station:'ST-2',security_alert:'Clean / Normal'}
  ];
  db.crimes=[
    {file_number:'CR-1',category:'Theft',station_code:'SOO-C-01',officer_name:'Officer One',case_status:'Open'},
    {file_number:'CR-2',category:'Fraud',station_code:'SAN-01',officer_name:'Officer Two',case_status:'Closed'}
  ];
  [['fpSearch',''],['personSearch',''],['stSearch',''],['offSearch',''],['carSearch',''],['crmSearch',''],
   ['airSearch',''],['caseSearch',''],['suspectSearch',''],['cpSearch'],['psSearch','']].forEach(([id])=>{
    const el=document.getElementById(id); if(el) el.value='';
  });
  cpLocationFilter='';
`);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const seqOf = (tbodyId) => [...w.document.querySelectorAll(`#${tbodyId} tr`)]
  .filter((tr) => !tr.querySelector('.empty'))
  .map((tr) => {
    const cell = tr.querySelector('td.seq');
    return cell ? Number(cell.getAttribute('data-seq')) : null;
  });
const cellsOf = (tr) => [...tr.children].map((td) => td.tagName);
const headerCount = (tbodyId) => {
  const table = $(tbodyId).closest('table');
  return table.querySelectorAll('thead th').length;
};
const bodyCount = (tbodyId) => {
  const tr = w.document.querySelector(`#${tbodyId} tr`);
  return tr ? tr.children.length : 0;
};
const audit = (tbodyId, label) => {
  const seqs = seqOf(tbodyId);
  assert.ok(seqs.length > 0, `${label}: rows rendered`);
  assert.deepEqual(seqs, seqs.map((_, i) => seqs.length - i),
    `${label}: row numbers run ${seqs.length}…1 top-to-bottom`);
  assert.equal(headerCount(tbodyId), bodyCount(tbodyId),
    `${label}: header/body column count stays aligned (${headerCount(tbodyId)})`);
  const first = w.document.querySelector(`#${tbodyId} tr`);
  assert.equal(first.children[0].tagName, 'TD', `${label}: first cell is a cell`);
  assert.match(first.children[0].className, /\bseq\b/, `${label}: first cell is the # column`);
  const table = $(tbodyId).closest('table');
  const lastHead = table.querySelector('thead th:last-child');
  const lastCell = first.children[first.children.length - 1];
  if (/actions/i.test(lastHead.textContent)) {
    assert.ok(/\bactions\b/.test(lastCell.className) || lastCell.querySelector('button'),
      `${label}: the Actions column is still last`);
  } else {
    assert.equal(table.querySelectorAll('thead th').length - 1,
      [...first.children].indexOf(lastCell),
      `${label}: the last cell still belongs to the last header`);
  }
  return seqs;
};

// ------------------------------------------------------------------ 1 ------
run(`renderFingerprintTable();`);
assert.deepEqual(seqOf('fpTable'), [4, 3, 2, 1],
  'fingerprint register numbers 4,3,2,1 for four applications (newest first)');
assert.match($('fpTable').innerHTML, /data-seq="4"/, 'top row carries the total');
const header = w.document.querySelector('#fpTable').closest('table')
  .querySelector('thead').textContent.replace(/\s+/g, ' ').trim();
assert.ok(header.startsWith('#'), `the heading starts with the # column (${header})`);
assert.match(header, /Actions$/, 'the Actions heading stays last');

// Filtering renumbers from the filtered result set.
$('fpSearch').value = 'travel';
run(`renderFingerprintTable();`);
assert.deepEqual(seqOf('fpTable'), [1], 'a single filtered match is numbered 1');
$('fpSearch').value = 'FP-';
run(`renderFingerprintTable();`);
assert.deepEqual(seqOf('fpTable'), [4, 3, 2, 1], 'clearing the filter restores the full numbering');
$('fpSearch').value = '';

// A newly registered application increments every number.
run(`db.fingerprint.unshift({id:'FP-5',person:'P-3',purpose:'Licence',status:'Pending Review',
  created_at:'2026-10-05 09:00'});renderFingerprintTable();`);
assert.deepEqual(seqOf('fpTable'), [5, 4, 3, 2, 1],
  'a new application becomes row 5 and rewrites the sequence');
run(`db.fingerprint.shift();renderFingerprintTable();`);
console.log('ok 1: fingerprint register numbers 4…1 and follows the search filter + new rows');

// ------------------------------------------------------------------ 2 ------
run(`renderPeople();renderAirportTable();renderCases();renderSuspectTable();
     renderCheckpointTable();renderStationsTable();renderOfficersTable();
     renderCarsTable();renderCrimesTable();`);
audit('peopleTable', 'Central Person Registry');
audit('airTable', 'Airport register');
audit('caseTable', 'CID cases');
audit('suspectTable', 'CID suspects');
audit('cpTable', 'Checkpoint screening');
audit('stationsTable', 'Registered Stations');
audit('officersTable', 'Police Officers');
audit('carsTable', 'Vehicles');
audit('crimesTable', 'Crime intake');
console.log('ok 2: every primary register keeps its column alignment (Actions still last)');

// ------------------------------------------------------------------ 3 ------
$('personSearch').value = 'Maxamed';
run(`renderPeople();`);
assert.deepEqual(seqOf('peopleTable'), [1], 'the filtered person list renumbers from 1 match');
$('personSearch').value = '';
run(`renderPeople();`);
assert.deepEqual(seqOf('peopleTable'), [3, 2, 1]);

$('stSearch').value = 'Erigavo';
run(`renderStationsTable();`);
assert.deepEqual(seqOf('stationsTable'), [1], 'a filtered station is numbered 1');
$('stSearch').value = '';
run(`renderStationsTable();`);
assert.deepEqual(seqOf('stationsTable'), [3, 2, 1]);
console.log('ok 3: filtered registers number from the filtered count');

// ------------------------------------------------------------------ 4 ------
run(`db.fingerprint=[];renderFingerprintTable();`);
const emptyRow = w.document.querySelector('#fpTable tr');
assert.equal(emptyRow.querySelector('.empty').getAttribute('colspan'), '8',
  'the empty fingerprint row spans all 8 columns');
run(`db.crimes=[];renderCrimesTable();`);
assert.equal(w.document.querySelector('#crimesTable').querySelector('.empty').getAttribute('colspan'), '6',
  'the empty crime row spans all 6 columns');
run(`db.cars=[];renderCarsTable();`);
assert.equal(w.document.querySelector('#carsTable').querySelector('.empty').getAttribute('colspan'), '6',
  'the empty vehicle row spans all 6 columns');
run(`db.airport=[];renderAirportTable();`);
assert.equal(w.document.querySelector('#airTable').querySelector('.empty').getAttribute('colspan'), '7',
  'the empty airport row spans all 7 columns');
run(`db.suspects=[];renderSuspectTable();`);
assert.equal(w.document.querySelector('#suspectTable').querySelector('.empty').getAttribute('colspan'), '6',
  'the empty suspect row spans all 6 columns');
run(`db.stations=[];renderStationsTable();`);
assert.equal(w.document.querySelector('#stationsTable').querySelector('.empty').getAttribute('colspan'), '7',
  'the empty station row spans all 7 columns');
run(`db.officers=[];renderOfficersTable();`);
assert.equal(w.document.querySelector('#officersTable').querySelector('.empty').getAttribute('colspan'), '9',
  'the empty officer row spans all 9 columns');
run(`db.cases=[];renderCases();`);
assert.equal(w.document.querySelector('#caseTable').querySelector('.empty').getAttribute('colspan'), '7',
  'the empty case row spans all 7 columns');
console.log('ok 4: empty-state placeholders span the widened tables');

// ------------------------------------------------------------------ 5 ------
run(`db.officers=[
    {service_id:'SV-1',full_name:'Officer One',rank:'Sergeant',unit:'Police',station_id:'ST-1',duty_status:'On duty'},
    {service_id:'SV-2',full_name:'Officer Two',rank:'Inspector',unit:'Police',station_id:'ST-2',duty_status:'On duty'}
  ];
  db.stations=[
    {id:'ST-1',name:'Las Anod Station',code:'SOO-C-01',region:'Sool',district:'Laascaanood',village:'Laascaanood'},
    {id:'ST-2',name:'Erigavo Station',code:'SAN-01',region:'Sanaag',district:'Erigavo',village:'Erigavo'}
  ];
  db.cars=[
    {id:'V-1',plate:'AA-111',type:'Pickup',category:'Police Fleet',station:'ST-1',security_alert:'Clean / Normal'},
    {id:'V-2',plate:'BB-222',type:'Sedan',category:'Civilian / Commercial',owner_full_name:'Owner',station:'ST-2',security_alert:'Clean / Normal'}
  ];
  psType='officers';renderPoliceSearch();`);
assert.deepEqual(seqOf('psTable'), [2, 1], 'police search (officers) numbers 2,1');
assert.equal(w.document.querySelectorAll('#psHead th')[0].textContent.trim(), '#',
  'police search renders the # heading first');
assert.equal(headerCount('psTable'), bodyCount('psTable'), 'police search keeps its column count');

for (const [tab, expected, label] of [['stations', [2, 1], 'stations'], ['cars', [2, 1], 'vehicles']]) {
  run(`psType='${tab}';renderPoliceSearch();`);
  assert.deepEqual(seqOf('psTable'), expected, `police search (${label}) numbers 2,1`);
  audit('psTable', `police search · ${label}`);
}
console.log('ok 5: all three police-search tabs carry the reverse sequence column');

console.log('ALL REVERSE SEQUENCE UI TESTS PASSED');
