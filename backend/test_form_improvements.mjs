#!/usr/bin/env node
// DOM regressions for global forms and identity provenance. Install jsdom@26.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';
const html=fs.readFileSync(new URL('../index.html',import.meta.url),'utf8');
const dom=new JSDOM(html,{url:'http://sentinel.test',runScripts:'outside-only'});
const w=dom.window, ctx=dom.getInternalVMContext();
let scrolled;
w.HTMLElement.prototype.scrollIntoView=function(){scrolled=this.id};
w.fetch=async()=>{throw new Error('Unexpected network call')};
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/if\(document.readyState==='loading'\)[\s\S]*$/,'');
vm.runInContext(script,ctx);
const run=s=>vm.runInContext(s,ctx);
const $=id=>w.document.getElementById(id);
const tick=()=>new Promise(resolve=>setTimeout(resolve,30));
run(`sessionUser={role:'SystemAdmin',modules:['persons','fingerprint','cid']};currentUser=sessionUser;
  guardReadOnly=()=>false;renderAll=()=>{};syncServer=async()=>{};toast=()=>{};persist=()=>{};
  refreshBranchSelect=async()=>true;`);

try{
  // One bad identity field, optional empty fields stay neutral.
  run(`openPersonDrawer();`);
  for(const [k,v] of Object.entries({first:'Ali',second:'Ahmed',third:'Hassan',fourth:'Omar',dob:'1990-01-01',national:'ID1',mother:'Hooyo',address:'Sool'})) $('pd-'+k).value=v;
  $('pd-third').value='';
  run('submitPersonDrawer(null)');await tick();
  assert.equal(w.document.activeElement.id,'pd-third');
  assert.equal(scrolled,'pd-third');
  assert.deepEqual([...$('personDrawerForm').querySelectorAll('.invalid')].map(e=>e.id),['pd-third']);
  assert.equal($('pd-third').getAttribute('aria-invalid'),'true');
  $('pd-third').value='Hassan';$('pd-third').dispatchEvent(new w.Event('input',{bubbles:true}));
  assert.equal($('pd-third').classList.contains('invalid'),false);
  $('pd-national').value='';
  run('submitPersonDrawer(null)');await tick();
  assert.equal($('pd-national').classList.contains('invalid'),true);
  assert.equal($('pd-passport').classList.contains('invalid'),true);
  $('pd-passport').value='PP1';$('pd-passport').dispatchEvent(new w.Event('input',{bubbles:true}));
  assert.equal($('pd-national').classList.contains('invalid'),false);
  assert.equal($('pd-passport').classList.contains('invalid'),false);
  run('closeDrawer()');
  run(`openPersonDrawer();markInvalid('pd',['first','mother','national','passport']);
    fillIdentity('pd',{first:'Filled',motherName:'Mother',nationalId:'ID-filled'})`);
  assert.equal($('pd-first').classList.contains('invalid'),false);
  assert.equal($('pd-mother').classList.contains('invalid'),false);
  assert.equal($('pd-national').classList.contains('invalid'),false);
  assert.equal($('pd-passport').classList.contains('invalid'),false);
  run('closeDrawer()');
  console.log('ok: only failed identity constraints are red; ID-or-passport revalidates');

  // Native and custom errors ordered together, not a later required select first.
  run(`openEntryModal('fpDrawer');`);
  $('fpForm').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();
  assert.equal(w.document.activeElement.id,'fp-first');
  assert.equal($('fpEmail').classList.contains('invalid'),false);
  assert.equal($('appDocs').classList.contains('invalid'),true);
  assert.equal($('appDocs').querySelectorAll('input.invalid').length,0);
  assert.equal(w.document.querySelectorAll('.page.active > .validation-alert').length,0);
  console.log('ok: submit focuses first error inside the entry modal; optional attachments stay neutral');

  // Wizard must reveal the hidden step before focus, even for native failures.
  run(`clearInvalid();openEntryModal('offDrawer');offStep(1);showFormError('Missing name',{names:['offName'],notice:'offNotice'});`);
  await tick();
  assert.equal($('off-step-2').classList.contains('active'),true);
  assert.equal(w.document.activeElement.id,'offName');
  // The modal's delayed initial focus must not undo the validation focus.
  await new Promise(resolve=>setTimeout(resolve,300));
  assert.equal(w.document.activeElement.id,'offName');
  console.log('ok: hidden officer step is revealed and focused');

  // Group requirement focuses the file input, not the top of the modal.
  run(`clearInvalid();showFormError('Two documents required',{names:['appDocs'],notice:'fpNotice'});`);await tick();
  assert.equal(w.document.activeElement.dataset.slot,'appDoc0');
  const files=$('appDocs').querySelectorAll('input[type="file"]');
  assert.equal(files.length,5,'clearance form renders five applicant upload controls');
  assert.ok($('appDocs').textContent.includes('Document 5 — Officer application scan / supporting clearance documents'));
  Object.defineProperty(files[0],'files',{value:[new w.File(['test'],'test.pdf')]});
  run(`showFormError('Two documents required',{names:['appDocs'],notice:'fpNotice'})`);await tick();
  assert.equal(w.document.activeElement.dataset.slot,'appDoc1');
  Object.defineProperty(files[2],'files',{value:[new w.File(['test'],'test.pdf')]});
  files[2].dispatchEvent(new w.Event('change',{bubbles:true}));
  Object.defineProperty(files[4],'files',{value:[new w.File(['scan'],'officer-application-scan.pdf')]});
  assert.equal(run("collectFiles('appDoc',5)").length,3,'fifth upload slot is collected with other applicant files');
  assert.equal($('appDocs').classList.contains('invalid'),false);
  console.log('ok: file group errors clear when the minimum is met in any slots');

  // Non-empty incorrect optional values, conditional constraints and native
  // fields are evaluated together and clear only when actually valid.
  $('fpEmail').value='not-an-email';
  assert.ok(run("invalidFormFields(fpForm)").includes('fpEmail'));
  run("markInvalid(null,['fpEmail'])");
  $('fpEmail').value='';$('fpEmail').dispatchEvent(new w.Event('input',{bubbles:true}));
  assert.equal($('fpEmail').classList.contains('invalid'),false);
  run("openEntryModal('dscDrawer')");
  $('dscType').value='Demotion';
  run("markInvalid(null,['dscToRank'])");
  $('dscType').value='Warning';$('dscType').dispatchEvent(new w.Event('change',{bubbles:true}));
  assert.equal($('dscToRank').classList.contains('invalid'),false);
  run("clearInvalid();openEntryModal('crmDrawer');validateFormBeforeSave(crmForm)");await tick();
  // Custom-required station comes before native-required branch/description.
  assert.equal(w.document.activeElement.id,'crmStation');
  console.log('ok: optional invalid email, conditional demotion and combined first-error ordering');


  // Failed API save keeps the form; successful save closes it (not its register).
  run(`clearInvalid();openEntryModal('airDrawer');serverOn=true;
       api=async()=>{throw new Error('Save rejected')};`);
  for(const [k,v] of Object.entries({first:'Ali',second:'Ahmed',third:'Hassan',fourth:'Omar',dob:'1990-01-01',national:'ID1',mother:'Hooyo',address:'Sool'})) $('air-'+k).value=v;
  $('airBranch').innerHTML='<option value="1">Branch</option>';
  await run('saveAirport({preventDefault(){}})');await tick();
  assert.equal($('airDrawer').classList.contains('open'),true);
  assert.equal($('airDrawer').classList.contains('closing'),false);
  assert.equal($('airDrawer').querySelectorAll('input.invalid,select.invalid').length,0);
  run(`api=async()=>({identity:{person_id:'P-1',matched:true}})`);
  await run('saveAirport({preventDefault(){}})');
  assert.equal($('airDrawer').classList.contains('closing'),true);
  await new Promise(resolve=>setTimeout(resolve,250));
  assert.equal($('airDrawer').classList.contains('open'),false);
  console.log('ok: successful airport save closes entry; failed save remains open without false field errors');

  // Full save-handler coverage for entry modals plus inline case workspace.
  for(const [handler,id] of [['saveFingerprint','fpDrawer'],['saveAirport','airDrawer'],['saveStation','stDrawer'],['saveOfficer','offDrawer'],['saveCrime','crmDrawer'],['saveCar','carDrawer'],['savePromotionNomination','prmDrawer'],['saveDisciplineAction','dscDrawer']]){
    assert.ok(run(`${handler}.toString()`).includes(`closeEntryModal('${id}')`),handler);
  }
  for(const handler of ['submitPersonDrawer','submitAddSuspect','submitCaseDrawer','submitCheckpoint','submitNewUser','submitEditUser','submitConductAction'])assert.ok(run(`${handler}.toString()`).includes('closeDrawer()'),handler);
  for(const handler of ['saveCaseDetails','addParticipant','uploadEvidence'])assert.ok(run(`${handler}.toString()`).includes("go('cid')"),handler);
  console.log('ok: all registration success paths close their modal or leave the entry workspace');

  // Citizenship row, click guard and review helper; other reasons unchanged.
  run(`currentUser={role:'FingerprintUnit'};sessionUser=currentUser;backendBuild={build:REQUIRED_BUILD_TAG,review_lock_active:true};
      isReadOnlyUser=()=>false;`);
  const fresh=JSON.stringify({id:'FP-1',purpose:'Citizenship',status:'Pending Review',created_at:new Date().toISOString()});
  assert.equal(run(`reviewLockState(${fresh}).locked`),false);
  assert.ok(!run(`renderRegisterRow(${fresh},currentUser)`).includes('disabled='));
  for(const reason of ['Education','Travel','Employment','Licence']){
    assert.equal(run(`reviewLockState({...${fresh},purpose:'${reason}'}).locked`),true);
    assert.ok(run(`renderRegisterRow({...${fresh},purpose:'${reason}'},currentUser)`).includes('disabled='));
  }
  run(`db.fingerprint=[${fresh}];window.approvalCalls=[];api=async(path)=>{approvalCalls.push(path);return {}};`);
  await run(`approveFP('FP-1')`);
  assert.equal(w.approvalCalls.length,1);
  console.log('ok: citizenship can approve immediately; other reasons remain locked');

  const output=run(`renderPersonLinkedRecords({residence:'Sool',proximity_note:'No live coordinates',scope_note:'Scoped',items:[{unit:'Airport',record_id:'AR-1',branch_name:'<img onerror=alert(1)>',branch_region:'Sool',branch_source:'airport_passengers.branch_id',source_table:'airport_passengers',uploaded_by:'Officer',uploader_branch:'HQ',created_at:'2026-10-09'}]})`);
  assert.ok(output.includes('&lt;img'));
  assert.ok(output.includes('airport_passengers.branch_id'));
  assert.ok(output.includes('Nearby branch / current proximity'));
  assert.ok(output.includes('Not determined'));
  assert.ok(output.includes('Sool'));
  $('pvModalBody').innerHTML='<div id="pvLinkedRecords"></div>';
  run(`serverOn=true;window.pendingProfiles={};api=path=>new Promise(resolve=>pendingProfiles[path]=resolve);
    window._viewingPerson={id:'P-1'};loadPersonLinkedRecords('P-1');
    window._viewingPerson={id:'P-2'};loadPersonLinkedRecords('P-2');`);
  run(`pendingProfiles['/api/persons/P-1/linked-records']({residence:'Wrong person',items:[]})`);await tick();
  assert.ok(!$('pvLinkedRecords').textContent.includes('Wrong person'));
  run(`pendingProfiles['/api/persons/P-2/linked-records']({residence:'Correct person',items:[]})`);await tick();
  assert.ok($('pvLinkedRecords').textContent.includes('Correct person'));
  run(`serverOn=false;loadPersonLinkedRecords('P-2')`);await tick();
  assert.ok($('pvLinkedRecords').textContent.includes('unavailable offline'));
  console.log('ok: profile fetch ignores stale responses and reports offline data honestly');
  console.log('ok: linked profile escapes source data and does not invent proximity');

  // Comprehensive #personDetailModal preview layout and the fingerprint
  // signed-application status column / quick-view path.
  assert.ok($('personDetailModal'),'dedicated person detail modal exists');
  assert.ok($('fpReviewModal'),'dedicated clearance review / re-scan modal exists');
  assert.ok(html.includes('Application Scanned Document'));
  assert.ok(html.includes('Signed Application Document · re-scan'));
  assert.match(html, /@media\(max-width:950px\)[\s\S]*?#personDetailModal \.pv-grid\.pd-bio-grid/);
  assert.match(html, /@media\(max-width:680px\)[\s\S]*?#personDetailModal \.cm-body/);
  run(`db.people=[{id:'P-DOC',name:'Ayaan Cabdi Xasan Axmed',first:'Ayaan',second:'Cabdi',third:'Xasan',fourth:'Axmed',
    nationalId:'NID-1',passportId:'PASS-1',dob:'1997-04-18',pob:'Hargeisa',motherName:'Faadumo Cali',phone:'+252 63 555 0199',
    residence:'Laascaanood',occupation:'Officer',fingerprintStatus:'captured',fingerprintHash:'BIO-P-DOC',units:['Fingerprint']}];
    db.fingerprint=[{id:'FP-DOC',person:'P-DOC',purpose:'Travel',status:'Pending Review',signedDocumentPath:'/uploads/signed.pdf',signedDocumentName:'signed-application.pdf'}];
    serverOn=true;currentUser={role:'SystemAdmin'};canWrite=()=>true;renderRegisterRow=()=>'<button>Approve</button>';fingerprintStatusBadge=()=>'<span>Captured</span>';`);
  run('renderFingerprintTable()');
  assert.match($('fpTable').innerHTML,/Signed &amp; Scanned/);
  assert.match($('fpTable').innerHTML,/Quick view/);
  assert.match($('fpTable').innerHTML,/>Re-scan<\/button>/);
  assert.match($('fpTable').innerHTML,/>Print<\/a>/);
  run(`api=async path=>path.endsWith('/documents')?({total_count:1,scope_note:'Fingerprint Unit attachments',documents:[
    {path:'/uploads/passport.jpg',name:'passport-scan.jpg',category:'Passport identity scan',source:'Fingerprint Unit',record_id:'FP-DOC'}
  ]}):({residence:'Laascaanood',proximity_note:'No live coordinates',scope_note:'Scoped',items:[]});openPersonView('P-DOC');`);
  await tick();
  assert.equal($('personDetailModal').classList.contains('open'),true);
  assert.equal($('pvModal').classList.contains('open'),true);
  assert.ok($('pvModalBody').textContent.includes('Fourth Name'));
  assert.ok($('pvModalBody').textContent.includes('National ID'));
  assert.ok($('pvModalBody').textContent.includes('Passport ID'));
  assert.equal($('personDetailDocCount').textContent,'1');
  assert.ok($('personDocumentGrid').querySelector('img'));
  assert.ok($('personDocumentGrid').textContent.includes('Passport identity scan'));
  run(`db.officers=[{service_id:'POL-DOC',full_name:'Maxamed Faarax Nuur',mother_name:'Khadra Faarax',
    date_of_birth:'1985-06-12',place_of_birth:'Ceerigaabo',contact_number:'+252 63 555 0101',rank:'Commander',unit:'General Patrol',
    photo_path:'/uploads/officer.jpg',doc1_type:'National ID',doc1_path:'/uploads/officer-id.pdf'}];openOfficerView('POL-DOC');`);
  assert.equal($('pvModalTitle').textContent,'Police Registration record · POL-DOC');
  assert.ok($('pvModalBody').textContent.includes('Officer photograph'));
  assert.ok($('pvModalBody').textContent.includes('National ID'));
  console.log('ok: responsive person detail, document preview cards, police registration View and signed-scan table status');
  console.log('PASS: form and profile regressions');
} finally {dom.window.close()}
