#!/usr/bin/env node
/**
 * DOM regressions for the clearance/UI hardening round (jsdom, no browser):
 *
 *   1. CLEARANCE PURPOSE — the purpose is a labelled chip in the register, the
 *      clearance review modal header and its summary strip.
 *   2. APPLICANT PHOTOGRAPH — a document whose friendly label carries no
 *      extension ("Applicant photograph") still renders as an <img> preview
 *      from the stored path, never as the generic file icon.
 *   3. CERTIFICATE PRINT LOCK — an approved row offers the certificate to a
 *      regular officer only after a signed scan is present; Admin /
 *      SystemAdmin bypass the lock, and the view-only Commander keeps its
 *      read-only print access.
 *   4. IMAGE VIEWER — clicking a person photograph or document thumbnail opens
 *      the fullscreen lightbox; zoom / reset / close behave.
 *   5. FIELD-LEVEL RBAC — in the person detail modal a regular officer may
 *      edit only phone / residence / occupation (identity inputs disabled and
 *      excluded from the PATCH payload), while an administrator edits all.
 *   6. PERSON PROFILE PURPOSE — the person detail head card names the purpose
 *      of the newest clearance application for that person (with an "earlier"
 *      count) and stays quiet for people with no application.
 *   7. ONE EDIT ACTION — the footer offers a single "Edit Details" action (no
 *      "Edit profile" / "Edit / append details" pair) and no per-field
 *      "Admin only" badges; locked fields are ordinary disabled inputs.
 *
 * Usage:  npm install --no-save --package-lock=false jsdom@26
 *         node backend/test_clearance_rbac_ui.mjs
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
const $ = (id) => w.document.getElementById(id);
const tick = () => new Promise((resolve) => setTimeout(resolve, 30));

run(`
  sessionUser={role:'FingerprintUnit'};
  currentUser=sessionUser;
  sessionVisibility=null;
  guardReadOnly=()=>false;
  backendBuild={build:REQUIRED_BUILD_TAG,review_lock_active:true};
  backendBuildChecked=true;
  renderAll=()=>{};
  syncServer=async()=>{};
  toast=()=>{};
  persist=()=>{};
`);

try {
  // ------------------------------------------------------------------ 1 ----
  // Purpose is first-class in the review modal and the register.
  run(`renderClearanceReview({
    application_id:'FP-UI-1',person_id:'P-1',person:'P-1',full_name:'Ayaan Cabdi Xasan Axmed',
    purpose:'Travel',status:'Pending Review',created_at:'2026-10-20 09:00:00',
    applicant_photo:'/uploads/applicant-photo.jpg',
    applicant_docs:JSON.stringify([{path:'/uploads/passport.jpg',name:'passport.jpg',file_type:'image/jpeg'}]),
    guardian_docs:'[]'
  })`);
  const purposeBadge = $('fpReviewPurposeBadge');
  assert.match(purposeBadge.textContent, /Travel/i, 'review header must name the purpose');
  assert.match(purposeBadge.className, /travel/, 'purpose chip carries the Travel tone');
  assert.match($('fpReviewSummary').innerHTML, /Clearance purpose/,
    'review summary must label the purpose explicitly');
  assert.match($('fpReviewSummary').innerHTML, /purpose-chip travel/,
    'review summary renders the purpose badge');
  console.log('ok 1a: clearance purpose is prominent in the review modal header + summary');

  // The purpose also survives the cached/offline register path.
  run(`db.people=[{id:'P-1',name:'Ayaan Cabdi Xasan Axmed'}];
    db.fingerprint=[{id:'FP-UI-1',person:'P-1',purpose:'Employment',status:'Pending Review',
      created_at:'2026-10-20 09:00:00',signedDocumentPath:'',signedDocumentName:''}];
    renderFingerprintTable();`);
  assert.match($('fpTable').innerHTML, /purpose-chip employment/,
    'register Purpose column renders a labelled purpose chip');
  console.log('ok 1b: register Purpose column renders the purpose badge');

  // The same purpose follows the person: the profile head card answers "why is
  // this person being cleared?" without opening the Fingerprint register.
  run(`db.people=[{id:'P-1',name:'Ayaan Cabdi Xasan Axmed'}];
    db.fingerprint=[
      {id:'FP-UI-2',person:'P-1',purpose:'Travel',status:'Approved',created_at:'2026-10-21 10:00:00'},
      {id:'FP-UI-1',applicantPersonId:'P-1',person:'P-1',purpose:'Employment',
       status:'Pending Review',created_at:'2026-10-20 09:00:00'}
    ];
    serverOn=false;
    window._viewingPerson={id:'P-1',name:'Ayaan Cabdi Xasan Axmed',units:[]};
    window._viewingOfficer=null;window._personDetailMode='person';window._personEditMode=false;
    renderPersonDetail(window._viewingPerson,'person');`);
  const personPurpose = $('pvModalBody').querySelector('.pv-idrow .pv-purpose-line');
  assert.ok(personPurpose, 'the person profile head card carries a purpose line');
  assert.match(personPurpose.textContent, /Clearance/i, 'the line is labelled Clearance');
  assert.match(personPurpose.textContent, /Travel/i, 'the newest application supplies the purpose');
  assert.match(personPurpose.querySelector('.purpose-chip').className, /travel/,
    'the profile chip carries the Travel tone');
  assert.match(personPurpose.textContent, /\+1 earlier/, 'earlier applications are summarised');
  assert.equal(personPurpose.getAttribute('data-clearance-purpose'), 'Travel');
  assert.match(personPurpose.getAttribute('title'), /FP-UI-2/,
    'hovering names the application behind the chip');
  run(`closeEntryModal('personDetailModal')`);

  // A person with no clearance application keeps the header clean.
  run(`window._viewingPerson={id:'P-2',name:'No Clearance Person',units:[]};
    renderPersonDetail(window._viewingPerson,'person');`);
  assert.equal($('pvModalBody').querySelector('.pv-purpose-line'), null,
    'no purpose chip is invented for a person without an application');
  run(`closeEntryModal('personDetailModal');db.people=[{id:'P-1',name:'Ayaan Cabdi Xasan Axmed'}];`);
  console.log('ok 6: person profile header shows the clearance purpose for that person');

  // ------------------------------------------------------------------ 2 ----
  assert.equal(
    run(`documentExtension({name:'Applicant photograph',path:'/uploads/applicant-photo.jpg'})`),
    'jpg', 'the extension must resolve from the stored path when the label has none');
  const photoCard = run(`renderPersonDocuments([{
    path:'/uploads/applicant-photo.jpg',name:'Applicant photograph',
    category:'Applicant photograph',source:'Fingerprint Unit · clearance application',record_id:'FP-UI-1'
  }],'')`);
  assert.match(photoCard, /<img[^>]+src="\/uploads\/applicant-photo\.jpg"/,
    'applicant photograph must render as an image thumbnail');
  assert.match(photoCard, /data-image-zoom="\/uploads\/applicant-photo\.jpg"/,
    'the photograph thumbnail opens the fullscreen viewer');
  assert.doesNotMatch(photoCard, /pd-file-icon/,
    'applicant photograph must never fall back to the generic file icon');
  assert.match($('fpOriginalDocuments').innerHTML, /<img[^>]+applicant-photo\.jpg/,
    'the review modal renders the applicant photograph preview');
  assert.doesNotMatch($('fpOriginalDocuments').innerHTML, /pd-file-icon/,
    'the review modal does not show a generic icon for the photograph');
  const pdfCard = run(`renderPersonDocuments([{path:'/uploads/scan.pdf',name:'scan.pdf'}],'')`);
  assert.match(pdfCard, /<iframe/, 'PDF documents keep their embedded preview');
  console.log('ok 2: applicant photograph renders as an image in the document card + review modal');

  // ------------------------------------------------------------------ 3 ----
  const approvedRow = (extra) => run(`renderRegisterRow(Object.assign({
    id:'FP-UI-1',status:'Approved',certificate:'CL-0001',
    created_at:'2020-01-01 00:00:00',purpose:'Employment'
  },${JSON.stringify(extra)}),currentUser)`);
  let row = approvedRow({ signedDocumentPath: '' });
  assert.match(row, /Certificate \(scan required\)/,
    'an approved row without a signed scan must not offer the certificate');
  assert.match(row, /disabled="disabled"/, 'the locked certificate control is disabled');
  assert.doesNotMatch(row, /certificate\.html/, 'no certificate link may leak while locked');

  row = approvedRow({ signedDocumentPath: '/uploads/signed.pdf', signedDocumentName: 'signed.pdf' });
  assert.match(row, /certificate\.html\?v=[A-Za-z0-9._-]+&id=FP-UI-1/,
    'the certificate unlocks once the signed scan is present');

  run(`currentUser={role:'SystemAdmin'};sessionUser=currentUser;`);
  row = approvedRow({ signedDocumentPath: '' });
  assert.match(row, /certificate\.html/, 'Admin bypasses the certificate print lock');
  run(`currentUser={role:'admin'};sessionUser=currentUser;`);
  row = approvedRow({ signedDocumentPath: '' });
  assert.match(row, /certificate\.html/, 'the "admin" role alias bypasses the print lock');

  // View-only Commander: keeps its existing certificate link but never writes.
  run(`currentUser=null;sessionUser={role:'ChiefCommander'};isReadOnlyUser=()=>true;`);
  row = approvedRow({ signedDocumentPath: '' });
  assert.match(row, /certificate\.html/, 'the read-only Commander keeps view-only print access');
  assert.doesNotMatch(row, /Approve/, 'the read-only Commander never receives an approve control');

  // Server-resolved state is authoritative when it is present.
  run(`currentUser={role:'FingerprintUnit'};sessionUser=currentUser;isReadOnlyUser=()=>false;`);
  row = approvedRow({ signedDocumentPath: '', certificate_print: { unlocked: true, locked: false } });
  assert.match(row, /certificate\.html/, 'the backend certificate_print flag is honoured');
  row = approvedRow({ signedDocumentPath: '/uploads/signed.pdf', certificate_print: { unlocked: false, locked: true } });
  assert.doesNotMatch(row, /certificate\.html/, 'a locked server verdict wins over a stale path');
  console.log('ok 3: certificate printing stays locked for officers until the signed scan exists '
    + '(admins + view-only command bypass)');

  // ------------------------------------------------------------------ 4 ----
  run(`openImageLightbox('/uploads/applicant-photo.jpg','Applicant photograph','Fingerprint Unit · clearance application')`);
  assert.equal($('imageLightbox').classList.contains('open'), true, 'lightbox opens');
  assert.equal($('imageLightbox').getAttribute('aria-hidden'), 'false', 'lightbox is announced');
  assert.equal($('ilbImage').getAttribute('src'), '/uploads/applicant-photo.jpg');
  assert.match($('ilbTitle').textContent, /Applicant photograph/);
  assert.equal($('ilbZoomLevel').textContent, '100%');
  run(`zoomImageLightbox(1)`);
  assert.equal($('ilbZoomLevel').textContent, '135%', 'zoom in changes the level');
  run(`zoomImageLightbox(-1)`);
  assert.equal($('ilbZoomLevel').textContent, '100%', 'zoom out returns to fit');
  run(`zoomImageLightbox(1);resetImageLightbox()`);
  assert.equal($('ilbZoomLevel').textContent, '100%', 'reset restores 100%');
  run(`closeImageLightbox()`);
  assert.equal($('imageLightbox').classList.contains('open'), false, 'lightbox closes');
  assert.equal($('imageLightbox').getAttribute('aria-hidden'), 'true');

  // Clicking a rendered thumbnail (delegated handler) opens the viewer.
  const trigger = w.document.createElement('button');
  trigger.type = 'button';
  trigger.setAttribute('data-image-zoom', '/uploads/passport.jpg');
  trigger.setAttribute('data-image-title', 'passport.jpg');
  trigger.setAttribute('data-image-caption', 'Passport identity scan');
  w.document.body.appendChild(trigger);
  trigger.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
  assert.equal($('imageLightbox').classList.contains('open'), true,
    'clicking an image thumbnail opens the fullscreen viewer');
  assert.equal($('ilbImage').getAttribute('src'), '/uploads/passport.jpg');
  run(`closeImageLightbox()`);
  trigger.remove();

  // The person head-card photograph is itself a viewer trigger.
  run(`serverOn=false;
    window._viewingPerson={id:'P-1',name:'Ayaan Cabdi Xasan Axmed',photoPath:'/uploads/person.jpg',units:[]};
    window._viewingOfficer=null;window._personDetailMode='person';window._personEditMode=false;
    renderPersonDetail(window._viewingPerson,'person');`);
  const headShot = $('pvModalBody').querySelector('.pv-photo[data-image-zoom]');
  assert.ok(headShot, 'the person photograph is a clickable viewer trigger');
  assert.equal(headShot.getAttribute('data-image-zoom'), '/uploads/person.jpg');
  run(`closeEntryModal('personDetailModal')`);
  console.log('ok 4: fullscreen image viewer opens from photographs + document thumbnails with zoom/reset');

  // ------------------------------------------------------------------ 5 ----
  const record = {
    id: 'P-1', name: 'Ayaan Cabdi Xasan Axmed', first: 'Ayaan', second: 'Cabdi',
    third: 'Xasan', fourth: 'Axmed', dob: '1997-04-18', pob: 'Hargeisa',
    motherName: 'Faadumo Cali', nationalId: 'NID-1', passportId: 'PASS-1',
    phone: '+252 63 555 0199', residence: 'Laascaanood', occupation: 'Officer', units: [],
  };
  run(`serverOn=false;
    currentUser={role:'FingerprintUnit'};sessionUser=currentUser;isReadOnlyUser=()=>false;
    window._viewingPerson=${JSON.stringify(record)};window._viewingOfficer=null;
    window._personDetailMode='person';window._personEditMode=true;
    renderPersonDetail(window._viewingPerson,'person');`);
  assert.equal($('pdEdit-phone').disabled, false, 'an officer may edit the contact phone');
  assert.equal($('pdEdit-residence').disabled, false, 'an officer may edit the residence address');
  assert.equal($('pdEdit-occupation').disabled, false, 'an officer may edit the occupation');
  for (const locked of ['first', 'second', 'third', 'fourth', 'dob', 'pob',
    'motherName', 'nationalId', 'passportId']) {
    assert.equal($('pdEdit-' + locked).disabled, true,
      `an officer must not edit the protected field ${locked}`);
  }
  assert.match($('pvModalBody').textContent, /Role-based editing/,
    'the modal explains the field-level restriction');
  assert.equal($('pvModalBody').querySelector('.pv-lock-tag'), null,
    'locked fields carry no per-field indicator badge');
  assert.doesNotMatch($('pvModalBody').textContent, /Admin only/i,
    'the removed "ADMIN ONLY" badge text must not return for a restricted editor');
  assert.match($('pdEdit-first').closest('.pv-field').className, /pv-locked/,
    'a protected field is styled as locked (and disabled), not tagged');
  assert.equal($('pdEdit-first').getAttribute('aria-readonly'), 'true');

  // Save as officer: only the three mutable fields leave the browser.
  $('pdEdit-phone').value = ' +252 63 999 0000 ';
  $('pdEdit-residence').value = 'Burao, Sool';
  $('pdEdit-occupation').value = 'Farmer';
  run(`window.__payload=null;persist=()=>{};renderAll=()=>{};toast=()=>{};
    api=async(path,opts)=>{window.__payload={path,body:JSON.parse(opts.body)};
      return {person:{person_id:'P-1',full_name:'Ayaan Cabdi Xasan Axmed',
        phone:'+252 63 999 0000',residence:'Burao, Sool',occupation:'Farmer'}}};
    serverOn=true;`);
  await run(`savePersonInlineEdit()`);
  await tick();
  const officerPayload = w.__payload;
  assert.ok(officerPayload, 'the officer save reached the API');
  assert.equal(officerPayload.path, '/api/persons/P-1');
  assert.deepEqual(Object.keys(officerPayload.body).sort(),
    ['occupation', 'phone', 'residence'],
    'a regular officer PATCH carries only phone/residence/occupation');
  assert.equal(officerPayload.body.phone, '+252 63 999 0000', 'values are trimmed before sending');
  // After a successful save the modal returns to the read-only grid.
  assert.equal($('pdEdit-first'), null,
    'the editor closes after saving and the read-only grid is restored');

  // Admin: every field is editable and the editor renders enabled inputs.
  run(`currentUser={role:'SystemAdmin'};sessionUser=currentUser;
    window._viewingPerson=${JSON.stringify(record)};
    window._personEditMode=true;
    renderPersonDetail(window._viewingPerson,'person');`);
  assert.equal($('pdEdit-first').disabled, false,
    'an administrator can edit the first name in the modal');
  assert.equal($('pdEdit-dob').disabled, false,
    'an administrator can edit the date of birth');
  assert.equal($('pdEdit-nationalId').disabled, false,
    'an administrator can edit the National ID');
  assert.equal($('pdEdit-passportId').disabled, false,
    'an administrator can edit the Passport ID');
  assert.doesNotMatch($('pvModalBody').textContent, /Admin only/,
    'no field is locked for an administrator');
  assert.equal(run(`personFieldEditAllowed('first')`), true, 'admin field permission helper');
  run(`currentUser={role:'FingerprintUnit'};sessionUser=currentUser;`);
  assert.equal(run(`personFieldEditAllowed('first')`), false);
  assert.equal(run(`personFieldEditAllowed('nationalId')`), false);
  assert.equal(run(`personFieldEditAllowed('phone')`), true);
  assert.equal(run(`personFieldEditAllowed('residence')`), true);
  assert.equal(run(`personFieldEditAllowed('occupation')`), true);

  // The shared identity drawer applies the same policy and sends only the
  // mutable fields for a restricted edit.
  run(`currentUser={role:'FingerprintUnit'};sessionUser=currentUser;isReadOnlyUser=()=>false;
    renderAll=()=>{};toast=()=>{};persist=()=>{};
    window._viewingPerson=${JSON.stringify(record)};
    openPersonDrawer(window._viewingPerson);`);
  assert.equal($('pd-first').readOnly, true, 'drawer: legal name is read-only for an officer');
  assert.equal($('pd-dob').readOnly, true, 'drawer: date of birth is read-only for an officer');
  assert.equal($('pd-national').readOnly, true, 'drawer: National ID is read-only for an officer');
  assert.equal($('pd-phone').readOnly, false, 'drawer: contact phone stays editable');
  assert.equal($('pd-address').readOnly, false, 'drawer: residence stays editable');
  assert.equal($('pd-occupation').readOnly, false, 'drawer: occupation stays editable');
  run(`window.__payload=null;
    api=async(path,opts)=>{window.__payload={path,body:JSON.parse(opts.body)};return {person:{person_id:'P-1'}}};
    serverOn=true;persistPrefixBiometrics=()=>{};closeDrawer=()=>{};`);
  $('pd-phone').value = '+252 63 777 0000';
  await run(`submitPersonDrawer('P-1')`);
  await tick();
  assert.ok(w.__payload, 'the restricted drawer save reached the API');
  assert.deepEqual(Object.keys(w.__payload.body).sort(), ['occupation', 'phone', 'residence'],
    'the identity drawer never sends protected fields for a regular officer');

  // Admin keeps the full identity form (no RBAC lock is applied).
  run(`window._identityEditPolicy={};
    currentUser={role:'SystemAdmin'};sessionUser=currentUser;
    openPersonDrawer(${JSON.stringify(record)});`);
  assert.equal($('pd-first').classList.contains('rbac-locked'), false,
    'an administrator is not subject to the officer identity lock');
  assert.equal($('pd-national').classList.contains('rbac-locked'), false,
    'an administrator keeps the National ID field free of the RBAC lock');
  assert.equal(w._identityEditPolicy.pd, null,
    'no restricted-edit policy is registered for an administrator');
  run(`closeDrawer()`);
  console.log('ok 5: field-level RBAC — officers edit phone/address/occupation only, admins edit all');

  // ------------------------------------------------------------------ 7 ----
  // A single, unambiguous edit entry point on the person profile.
  run(`currentUser={role:'FingerprintUnit'};sessionUser=currentUser;isReadOnlyUser=()=>false;
    window._viewingPerson=${JSON.stringify(record)};window._viewingOfficer=null;
    window._personDetailMode='person';window._personEditMode=false;
    renderPersonDetail(window._viewingPerson,'person');`);
  let foot = $('pvModalBody').querySelector('.pv-foot');
  const editActions = [...foot.querySelectorAll('button')]
    .filter((b) => /edit/i.test(b.textContent) || /openPersonDrawer|startPersonEditMode/.test(b.getAttribute('onclick') || ''));
  assert.equal(editActions.length, 1, 'the footer offers exactly one edit action');
  assert.match(editActions[0].textContent, /Edit Details/);
  assert.match(editActions[0].getAttribute('onclick') || '', /startPersonEditMode\(\)/,
    'the single action opens the inline, role-aware editor');
  assert.doesNotMatch(foot.textContent, /Edit profile|Edit \/ append details/,
    'the old duplicate button labels are gone');

  run(`window._personEditMode=true;renderPersonDetail(window._viewingPerson,'person');`);
  foot = $('pvModalBody').querySelector('.pv-foot');
  assert.equal(foot.querySelectorAll('[data-person-save]').length, 1,
    'exactly one save control in edit mode');
  assert.equal(foot.querySelector('[data-person-save]').textContent, 'Save details',
    'the save control uses the same "details" wording as the entry point');
  assert.match(foot.textContent, /Cancel/, 'the editor keeps a cancel path');
  run(`window._personEditMode=false`);
  console.log('ok 7: one clean "Edit Details" action replaces the duplicate edit entry points');

  console.log('ALL CLEARANCE / RBAC UI TESTS PASSED');
  // Let the identity-match continuations and the modal focus timers settle
  // before the jsdom window is torn down.
  run(`try{cancelEntryFocus()}catch(_){}`);
  await new Promise((resolve) => setTimeout(resolve, 320));
} finally {
  w.close();
}
