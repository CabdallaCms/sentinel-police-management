/* DOM smoke test for the Sentinel modal/table refactor (local verification harness).
   Loads index.html in jsdom in local-demo mode and exercises the real UI code paths. */
const { JSDOM, VirtualConsole } = require('jsdom');
const path = require('path');

const FILE = process.argv[2] || path.join(__dirname, '..', '..', 'index.html');
let failures = 0, checks = 0;
const ok = (name, cond, extra) => {
  checks++;
  if (cond) console.log('  PASS  ' + name);
  else { failures++; console.log('  FAIL  ' + name + (extra ? '  -> ' + extra : '')); }
};
const section = t => console.log('\n== ' + t + ' ==');

(async () => {
  const vc = new VirtualConsole();
  const unexpected = [];
  vc.on('jsdomError', e => unexpected.push('jsdomError: ' + e.message));
  vc.on('error', (...a) => unexpected.push('console.error: ' + a.join(' ')));

  const dom = await JSDOM.fromFile(FILE, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: 'http://localhost:8000/',
    virtualConsole: vc,
    beforeParse(w) {
      // Force local demo mode: no central backend reachable from the browser.
      w.fetch = () => Promise.reject(new Error('no server (local demo mode)'));
    }
  });
  const { window } = dom;
  const { document } = window;
  await new Promise(r => window.addEventListener('load', r));
  await new Promise(r => setTimeout(r, 60));
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const wait = () => new Promise(r => setTimeout(r, 30));

  section('0 · no unexpected runtime errors');
  ok('no jsdom/console errors during load', unexpected.length === 0, unexpected.join(' | '));
  const ev = code => window.eval(code);           // `let`-declared app globals are lexical, not window props
  ok('local demo mode engaged (serverOn=false)', ev('serverOn') === false);

  section('1 · drawer removal / modal scaffolding');
  ok('no .drawer element in DOM', $$('.drawer').length === 0);
  ok('no openDrawer/closeDrawer globals', typeof window.openDrawer === 'undefined' && typeof window.closeDrawer === 'undefined');
  ok('openModal + closeModal exist', typeof window.openModal === 'function' && typeof window.closeModal === 'function');
  const shell = $('#overlay'), modal = $('#modal');
  ok('overlay backdrop element present', !!shell);
  ok('modal has head/body/foot', !!$('.modal-head') && !!$('#modalBody') && !!$('#modalFoot'));
  ok('modal close button wired', /closeModal\(\)/.test($('.modal-head .iconbtn').getAttribute('onclick')));

  section('2 · modal CSS contract');
  const css = $('style').textContent;
  ok('backdrop-filter: blur(4px)', /backdrop-filter:blur\(4px\)/.test(css));
  ok('overlay is a centered flex container', /\.overlay\{[^}]*display:none[^}]*align-items:center[^}]*justify-content:center/.test(css) || /\.overlay\{[^}]*align-items:center[^}]*justify-content:center/.test(css));
  ok('.overlay.on switches to flex', /\.overlay\.on\{display:flex\}/.test(css));
  ok('modal body max-height 80vh + overflow-y auto', /\.modal-body\{[^}]*max-height:80vh[^}]*overflow-y:auto/.test(css));
  ok('modal head is pinned (sticky top:0)', /\.modal-head\{[^}]*position:sticky[^}]*top:0/.test(css));
  ok('modal foot is sticky bottom:0', /\.modal-foot\{[^}]*position:sticky[^}]*bottom:0/.test(css));
  const cssom = [...document.styleSheets[0].cssRules];
  const rule = sel => cssom.find(r => r.selectorText === sel);
  const ov = rule('.overlay');
  ok('CSSOM: .overlay parsed with centering', !!ov && /center/.test(ov.style.alignItems) && /center/.test(ov.style.justifyContent), ov && ov.style.cssText);

  section('2b · computed styles actually cascade onto the real elements');
  const cs = el => window.getComputedStyle(el);
  const vh = window.innerHeight / 100;
  const st = cs(shell);
  ok('overlay is position:fixed', st.position === 'fixed', st.position);
  ok('overlay backdrop-filter computes to blur(4px)', st.backdropFilter === 'blur(4px)', st.backdropFilter);
  ok('overlay is rgba dark + centered (align/justify center)',
    st.alignItems === 'center' && st.justifyContent === 'center' && /^rgba\(/.test(st.backgroundColor),
    st.alignItems + '/' + st.justifyContent + '/' + st.backgroundColor);
  ok('overlay display:none when closed', st.display === 'none', st.display);
  window.openModal('Computed probe', '<p>x</p>', '<button class="btn">OK</button>');
  ok('overlay display:flex when open', cs(shell).display === 'flex', cs(shell).display);
  const csBody = cs(document.getElementById('modalBody'));
  ok('modal body computed max-height === 80vh (' + Math.round(80 * vh) + 'px)',
    Math.abs(parseFloat(csBody.maxHeight) - 80 * vh) < 1.5, csBody.maxHeight);
  ok('modal body computed overflow-y:auto', csBody.overflowY === 'auto', csBody.overflowY);
  ok('modal head computed position:sticky top:0',
    cs($('.modal-head')).position === 'sticky' && cs($('.modal-head')).top === '0px');
  ok('modal foot computed position:sticky bottom:0',
    cs($('.modal-foot')).position === 'sticky' && cs($('.modal-foot')).bottom === '0px');
  ok('modal is a flex column', cs(modal).flexDirection === 'column', cs(modal).flexDirection);
  window.closeModal();
  const thEl = document.getElementById('cpTable').closest('table').querySelector('thead th');
  ok('thead th computed position:sticky top:0',
    cs(thEl).position === 'sticky' && cs(thEl).top === '0px', cs(thEl).position + '/' + cs(thEl).top);
  ok('thead th computed solid background', /^rgb\(/.test(cs(thEl).backgroundColor), cs(thEl).backgroundColor);
  const wrapEl = document.getElementById('cpTable').closest('.table-wrap');
  ok('table-wrap computed max-height === 100vh - 280px (' + Math.round(100 * vh - 280) + 'px)',
    Math.abs(parseFloat(cs(wrapEl).maxHeight) - (100 * vh - 280)) < 1.5, cs(wrapEl).maxHeight);
  ok('table-wrap computed overflow:auto', cs(wrapEl).overflow === 'auto', cs(wrapEl).overflow);

  section('3 · table CSS contract');
  ok('table-wrap fixed max-height calc(100vh - 280px)', /\.table-wrap\{[^}]*max-height:calc\(100vh - 280px\)/.test(css));
  ok('thead sticky top:0', /\.table thead,\.table thead th\{position:sticky;top:0/.test(css));
  ok('thead solid background', /\.table thead,\.table thead th\{[^}]*background:#f6f9fd/.test(css));
  ok('purple badge class defined', /\.badge\.purple\{background:#f1ebfe/.test(css));

  section('4 · every register table: sticky thead + Actions column');
  const TABLES = [
    ['peopleTable', 'Central Person Registry'],
    ['fpTable', 'Fingerprint register'],
    ['airTable', 'Airport logs'],
    ['caseTable', 'Crime cases'],
    ['suspectTable', 'Suspect list'],
    ['cpTable', 'Checkpoint register'],
    ['cwPartTable', 'Case workspace participants']
  ];
  for (const [id, label] of TABLES) {
    const tb = document.getElementById(id);
    const table = tb && tb.closest('table');
    const wrap = table && table.closest('.table-wrap');
    const ths = table ? [...table.querySelectorAll('thead th')] : [];
    const last = ths[ths.length - 1];
    ok(`${label}: inside .table-wrap card`, !!wrap);
    ok(`${label}: thead exists with ${ths.length} columns`, ths.length > 0);
    ok(`${label}: rightmost column is "Actions"`, !!last && last.textContent.trim() === 'Actions', last && last.textContent);
    ok(`${label}: Actions header has col-actions class`, !!last && last.classList.contains('col-actions'));
  }

  section('5 · rendered rows match header column counts + have a View button');
  for (const [id, label] of TABLES) {
    const tb = document.getElementById(id);
    const table = tb.closest('table');
    const ths = table.querySelectorAll('thead th').length;
    const rows = [...tb.querySelectorAll('tr')].filter(r => !r.querySelector('.empty'));
    if (!rows.length) {
      // cwPartTable is only populated once a case workspace is open (covered in section 8).
      if (id === 'cwPartTable') { ok(`${label}: empty until a case is opened (expected)`, true); continue; }
      ok(`${label}: has at least one row`, false, 'tbody empty'); continue;
    }
    const bad = rows.filter(r => r.children.length !== ths);
    ok(`${label}: ${rows.length} row(s), all with ${ths} cells`, bad.length === 0, bad[0] && bad[0].children.length + ' cells');
    const lastCell = rows[0].children[rows[0].children.length - 1];
    ok(`${label}: last cell is col-actions with a button`, lastCell.classList.contains('col-actions') && !!lastCell.querySelector('button'));
  }

  section('6 · status badge palette is standardized');
  const allowed = new Set(['red', 'green', 'blue', 'purple', 'amber', 'gray']);
  const badges = $$('tbody .badge');
  const illegal = badges.filter(b => ![...b.classList].some(c => allowed.has(c)));
  ok(`${badges.length} table badges, all in the standard palette`, illegal.length === 0, illegal[0] && illegal[0].outerHTML);
  const tone = (tableId, text) => {
    const b = [...document.getElementById(tableId).querySelectorAll('.badge')].find(x => x.textContent.trim() === text);
    return b ? [...b.classList].find(c => allowed.has(c)) : null;
  };
  ok('suspect "Active alert" is red', tone('suspectTable', 'Active alert') === 'red', tone('suspectTable', 'Active alert'));
  ok('suspect linked case pill is purple', tone('suspectTable', 'CID-2026-008') === 'purple', tone('suspectTable', 'CID-2026-008'));
  ok('checkpoint "Flagged match" is red', tone('cpTable', 'Flagged match') === 'red', tone('cpTable', 'Flagged match'));
  ok('case status pill rendered', tone('caseTable', 'Under Investigation') === 'amber', tone('caseTable', 'Under Investigation'));
  ok('fingerprint "Pending Review" pill rendered', tone('fpTable', 'Pending Review') === 'amber', tone('fpTable', 'Pending Review'));

  section('7 · View buttons open centered detail modals');
  const views = [
    ['peopleTable', 'Identity profile'],
    ['fpTable', 'Clearance application'],
    ['airTable', 'Airport passenger record'],
    ['suspectTable', 'Suspect alert'],
    ['cpTable', 'Checkpoint stop']
  ];
  for (const [id, expectTitle] of views) {
    window.closeModal();
    const btn = document.getElementById(id).querySelector('.col-actions button');
    btn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await wait();
    ok(`${id}: modal opened`, shell.classList.contains('on'));
    ok(`${id}: title "${$('#modalTitle').textContent}"`, $('#modalTitle').textContent.includes(expectTitle), $('#modalTitle').textContent);
    ok(`${id}: body rendered`, $('#modalBody').innerHTML.length > 80);
    ok(`${id}: footer has buttons`, $('#modalFoot').querySelectorAll('.btn').length >= 1);
    ok(`${id}: body is the scroll container`, /modal-body/.test($('#modalBody').className));
  }

  section('8 · case table View opens the case workspace');
  window.closeModal();
  document.getElementById('caseTable').querySelector('.col-actions button')
    .dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await new Promise(r => setTimeout(r, 60));
  ok('case workspace page is active', document.getElementById('caseworkspace').classList.contains('active'));
  ok('case workspace loaded a case id', document.getElementById('cwCaseId').value.startsWith('CID-'), document.getElementById('cwCaseId').value);
  const partRows = document.getElementById('cwPartTable').querySelectorAll('tr');
  ok('participant table rendered ' + partRows.length + ' row(s)', partRows.length >= 1);
  window.viewParticipant(0);
  await wait();
  ok('participant View modal opened', shell.classList.contains('on') && $('#modalTitle').textContent.includes('Case participant'), $('#modalTitle').textContent);

  section('9 · Escape + backdrop click close the modal');
  ok('modal open before escape', shell.classList.contains('on'));
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  await wait();
  ok('Escape closed the modal', !shell.classList.contains('on'));
  ok('body scroll lock released', !document.body.classList.contains('modal-open'));
  window.openModal('Backdrop test', '<p>x</p>', '');
  await wait();
  shell.dispatchEvent(new window.MouseEvent('click', { bubbles: false }));
  ok('clicking the backdrop closes the modal', !shell.classList.contains('on'));
  window.openModal('Inner click test', '<p>x</p>', '');
  modal.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  ok('clicking inside the modal keeps it open', shell.classList.contains('on'));
  window.closeModal();

  section('10 · create modals (wide) open with sticky footers');
  window.openPersonModal(null); await wait();
  ok('new person modal open + wide', shell.classList.contains('on') && modal.classList.contains('wide'));
  ok('new person modal has identity form', !!document.getElementById('pd-first'));
  ok('new person footer has Cancel + Save', $('#modalFoot').querySelectorAll('.btn').length === 2 && /Save person/.test($('#modalFoot').textContent), $('#modalFoot').textContent.trim());
  window.closeModal();
  window.openAddSuspect(); await wait();
  ok('add suspect modal open + wide', shell.classList.contains('on') && modal.classList.contains('wide'));
  window.closeModal();
  window.openCheckpointModal(); await wait();
  ok('checkpoint modal open + wide', shell.classList.contains('on') && modal.classList.contains('wide'));
  ok('checkpoint modal holds traveler + guardian forms', !!document.getElementById('cp-first') && !!document.getElementById('gd-first'));
  ok('checkpoint file slots built', document.querySelectorAll('input[data-slot^="tdoc"]').length === 2 && document.querySelectorAll('input[data-slot^="gdoc"]').length === 2);
  window.closeModal();
  window.openCaseModal(); await wait();
  ok('new case modal open (standard width)', shell.classList.contains('on') && !modal.classList.contains('wide'));

  section('11 · end-to-end submit through the modal (new case)');
  const casesBefore = ev('db').cases.length;
  document.getElementById('cdCategory').value = 'Vehicle theft';
  document.getElementById('cdLocation').value = 'Hargeisa West';
  await window.submitCaseModal();
  await wait();
  ok('case created (local demo)', ev('db').cases.length === casesBefore + 1);
  ok('modal closed after submit', !shell.classList.contains('on'));
  ok('case workspace opened for the new case', document.getElementById('cwCaseId').value === ev('db').cases[0].id, document.getElementById('cwCaseId').value + ' vs ' + ev('db').cases[0].id);

  section('12 · end-to-end submit through the modal (suspect without a case)');
  window.go('cid');
  window.openAddSuspect(); await wait();
  const set = (id, v) => { document.getElementById(id).value = v; };
  set('sp-first', 'Cabdixakiin'); set('sp-second', 'Jaamac'); set('sp-third', 'Warsame'); set('sp-fourth', 'Xirsi');
  set('sp-dob', '1993-06-11'); set('sp-national', '10099887'); set('sp-mother', 'Hodan Faarax'); set('sp-address', 'Hargeisa, New Hargeisa');
  document.getElementById('spCase').value = '';
  document.getElementById('spOrigin').value = 'Manual Entry';
  set('spNote', 'Wanted for questioning — burglary ring, New Hargeisa.');
  await window.submitAddSuspect();
  await wait();
  const sus = ev('db').suspects[0];
  ok('suspect saved with Manual Entry origin', sus && sus.origin === 'Manual Entry' && !sus.case, JSON.stringify(sus));
  ok('suspect reason stored', sus.reason.includes('burglary ring'));
  ok('modal closed after submit', !shell.classList.contains('on'));
  ok('suspect table shows blue "Manual Entry" pill',
    tone('suspectTable', 'Manual Entry') === 'blue', tone('suspectTable', 'Manual Entry'));
  ok('suspect table shows red "Active alert" pill', tone('suspectTable', 'Active alert') === 'red');
  window.closeModal();
  document.getElementById('suspectTable').querySelector('.col-actions button')
    .dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await wait();
  ok('suspect detail modal shows the reason', $('#modalBody').textContent.includes('burglary ring'));
  window.closeModal();

  section('13 · end-to-end submit through the wide checkpoint modal');
  window.go('checkpoints');
  const cpBefore = ev('db').checkpoints.length;
  window.openCheckpointModal(); await wait();
  const setf = (id, v) => { document.getElementById(id).value = v; };
  setf('cp-first', 'Ayaan'); setf('cp-second', 'Cabdi'); setf('cp-third', 'Xasan'); setf('cp-fourth', 'Axmed');
  setf('cp-dob', '1997-04-18'); setf('cp-national', '10012345');
  setf('cp-address', 'Hargeisa, Jigjiga Yar'); setf('cp-permanent', 'Hargeisa, Jigjiga Yar'); setf('cp-purpose', 'Family visit');
  setf('gd-first', 'Cabdi'); setf('gd-second', 'Faarax'); setf('gd-third', 'Cali'); setf('gd-fourth', 'Axmed');
  setf('gd-relationship', 'Parent'); setf('gd-phone', '+252 63 555 1000');
  setf('gd-permanent', 'Hargeisa, Jigjiga Yar'); setf('gd-occupation', 'Trader');
  const file = n => new window.File(['dummy'], n, { type: 'image/png' });
  const put = (slot, n) => {
    const inp = slot === 'cp-photo' ? document.getElementById('cp-photo') : document.querySelector(`input[data-slot="${slot}"]`);
    Object.defineProperty(inp, 'files', { value: [file(n)], configurable: true });
    inp.dispatchEvent(new window.Event('change', { bubbles: true }));
  };
  put('tdoc0', 'traveler-doc-1.png');
  put('gdoc0', 'guardian-doc-1.png');
  put('cp-photo', 'traveler-live.png');
  // Validation guard first: submit without the live photo must be refused.
  Object.defineProperty(document.getElementById('cp-photo'), 'files', { value: [], configurable: true });
  await window.submitCheckpoint();
  await wait();
  ok('validation blocks submit without the live photo', ev('db').checkpoints.length === cpBefore && shell.classList.contains('on'));
  put('cp-photo', 'traveler-live.png');
  document.getElementById('cpLoc').value = 'South';
  document.getElementById('cpNotes').value = 'Private vehicle, heading west.';
  await window.submitCheckpoint();
  await wait();
  ok('checkpoint stop recorded', ev('db').checkpoints.length === cpBefore + 1, JSON.stringify(ev('db').checkpoints[0]));
  ok('checkpoint modal closed after submit', !shell.classList.contains('on'));
  const cp = ev('db').checkpoints[0];
  ok('screening computed server-side style (Flagged match / No active alert)',
    ['Flagged match', 'No active alert'].includes(cp.screen), cp.screen);
  ok('screening pill is red for the flagged traveler (P-0001 has no alert -> Cleared)',
    tone('cpTable', cp.screen) === (cp.screen === 'Flagged match' ? 'red' : 'green'), tone('cpTable', cp.screen));
  ok('action pill rendered for ' + cp.action, tone('cpTable', cp.action) !== null, cp.action);
  document.getElementById('cpTable').querySelector('.col-actions button')
    .dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await wait();
  ok('checkpoint detail modal shows traveler + guardian sections',
    $('#modalBody').textContent.includes('Traveler') && $('#modalBody').textContent.includes('Guardian') && $('#modalBody').textContent.includes('Screening'));
  window.closeModal();

  section('14 · dashboard metrics still update');
  window.go('dashboard');
  ok('central persons metric', document.getElementById('mPeople').textContent === String(ev('db').people.length));
  ok('active suspect alerts metric', document.getElementById('mSuspects').textContent ===
    String(ev('db').suspects.filter(x => x.alert === 'Active alert').length));

  section('15 · runtime errors during the whole run');
  ok('no unexpected errors', unexpected.length === 0, unexpected.join(' | '));

  console.log(`\n${checks - failures}/${checks} checks passed` + (failures ? `  (${failures} FAILED)` : ''));
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error('HARNESS ERROR', e); process.exit(2); });
