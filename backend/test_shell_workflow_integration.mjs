#!/usr/bin/env node
// Integration contract: the refreshed shell and the workflow fixes must coexist.
// npm install --no-save --package-lock=false jsdom@26
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const html=fs.readFileSync(new URL('../index.html',import.meta.url),'utf8');
const dom=new JSDOM(html,{url:'http://sentinel.test',runScripts:'outside-only'});
const w=dom.window, ctx=dom.getInternalVMContext();
let mobile=true, scrolled;
w.matchMedia=()=>({matches:mobile});
w.HTMLElement.prototype.scrollIntoView=function(){scrolled=this.id};
w.fetch=async()=>{throw new Error('Network must be mocked in this DOM test')};
const run=source=>vm.runInContext(source,ctx);
const $=id=>w.document.getElementById(id);
const tick=(ms=30)=>new Promise(resolve=>setTimeout(resolve,ms));
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/if\(document.readyState==='loading'\)[\s\S]*$/,'');
run(script);

function signIn(role,modules,isAdmin=false){
  run(`sessionUser=${JSON.stringify({role,modules,display_name:'Test Officer',role_label:role})};
    currentUser=sessionUser;sessionVisibility={is_admin:${isAdmin}};
    applyNavForRole();updateUserPill();`);
}

try{
  // The newer header-profile layout must not revert to the old/sidebar version.
  assert.equal(w.document.querySelectorAll('#userPill').length,1);
  assert.ok($('topbar').contains($('userPill')));
  assert.equal($('sidebar').contains($('userPill')),false);
  assert.ok($('userPill').classList.contains('header-user'));
  assert.ok($('topbar').querySelector('.top-actions'));
  assert.ok($('sidebar').querySelector('.side-footer-meta'));
  assert.ok($('sidebar').querySelector('.nav-group-modern-title'));
  assert.ok(html.includes('#quickActions>.btn:disabled'));
  assert.ok(html.includes('@media(max-width:680px)'));
  assert.ok(html.includes('grid-template-columns:repeat(2,minmax(0,1fr))'));
  assert.match(html,/body\.sidebar-collapsed \.main\{width:100%;margin-left:0\}/);
  assert.match(html,/body\.sidebar-collapsed \.side\{transform:translateX\(-105%\);pointer-events:none\}/);
  assert.match(html,/@media\(min-width:951px\) and \(max-width:1280px\)/);
  assert.match(html,/\.main\{padding:22px clamp\(14px,2vw,30px\)\}/);
  // Valid controls must not inherit the red styling of invalid siblings.
  assert.ok(html.includes('input.invalid,select.invalid,textarea.invalid'));
  assert.ok(!html.includes('.field.invalid input'));
  signIn('SystemAdmin',['dashboard','people','fingerprint','airport','cid','checkpoints','policesearch','admin'],true);
  assert.equal($('userName').textContent,'Test Officer');
  assert.equal(w.getComputedStyle($('userPill')).display,'flex');
  assert.ok($('topbar').classList.contains('is-admin'));
  assert.ok(w.document.querySelector('#nav [data-page="branches"]'));
  console.log('ok: header profile, command navigation and dashboard-action styling preserved');

  // Collapsible navigation keeps both persistence and ARIA state.
  run(`setNavGroupOpen('cid',false)`);
  const cidToggle=w.document.querySelector('[data-group-toggle="cid"]');
  assert.equal(cidToggle.getAttribute('aria-expanded'),'false');
  assert.equal(cidToggle.getAttribute('aria-controls'),'nav-group-cid');
  run(`setNavGroupOpen('cid',true)`);
  assert.equal(cidToggle.getAttribute('aria-expanded'),'true');
  run('toggleSidebar()');
  assert.equal($('sidebarToggle').getAttribute('aria-expanded'),'true');
  assert.ok(w.document.body.classList.contains('nav-open'));
  run(`go('people')`);
  assert.ok($('people').classList.contains('active'));
  assert.equal($('sidebarToggle').getAttribute('aria-expanded'),'false');
  run('toggleSidebar()');
  w.document.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  assert.equal(w.document.body.classList.contains('nav-open'),false);
  run('toggleSidebar()');
  mobile=false;w.dispatchEvent(new w.Event('resize'));
  assert.equal($('sidebar').classList.contains('is-open'),false);
  assert.equal($('sidebarToggle').getAttribute('aria-expanded'),'true');
  run('toggleSidebar()');
  assert.ok(w.document.body.classList.contains('sidebar-collapsed'));
  assert.equal($('sidebarToggle').getAttribute('aria-expanded'),'false');
  assert.equal(w.localStorage.getItem('sentinelSidebarCollapsed'),'1');
  assert.equal($('sidebar').getAttribute('aria-hidden'),'true');
  run('toggleSidebar()');
  assert.equal(w.document.body.classList.contains('sidebar-collapsed'),false);
  assert.equal($('sidebarToggle').getAttribute('aria-expanded'),'true');
  assert.equal(w.localStorage.getItem('sentinelSidebarCollapsed'),'0');
  w.localStorage.setItem('sentinelSidebarCollapsed','1');run('applySidebarViewport()');
  assert.ok(w.document.body.classList.contains('sidebar-collapsed'),'desktop collapse preference restores');
  run('toggleSidebar()');
  console.log('ok: responsive navigation menu, persisted desktop collapse and full-width workspace');

  // New subgroup labels and restored menu items still obey role gates.
  const checkpointLabel=w.document.querySelector('[data-module-label="checkpoints"]');
  signIn('FingerprintUnit',['dashboard','people','fingerprint']);
  assert.equal(checkpointLabel.style.display,'none');
  assert.equal(w.document.querySelector('#nav [data-page="policesearch"]'),null);
  assert.equal(w.document.querySelector('#nav [data-page="branches"]'),null);
  signIn('CheckpointSouth',['dashboard','people','checkpoints']);
  assert.notEqual(checkpointLabel.style.display,'none');
  assert.ok(w.document.querySelector('#nav [data-page="checkpoints"]'));
  assert.equal($('topbar').classList.contains('is-admin'),false);
  console.log('ok: role-scoped menus and checkpoint headings survive session changes');

  signIn('SystemAdmin',['dashboard','people','fingerprint','airport','cid','checkpoints','policesearch','admin'],true);
  run(`refreshBranchSelect=async()=>true;toast=()=>{};`);
  // Open and immediately validate a later wizard step: the animation's
  // initial-focus timeout must not override error focus at the 240ms mark.
  run(`openEntryModal('offDrawer');offStep(1);
    showFormError('Enter officer name',{names:['offName'],notice:'offNotice'});`);
  await tick(300);
  assert.equal(w.document.activeElement.id,'offName');
  assert.equal(scrolled,'offName');
  assert.ok($('off-step-2').classList.contains('active'));
  assert.equal($('offRank').classList.contains('invalid'),false);
  run(`closeEntryModal('offDrawer')`);await tick(250);
  assert.equal($('offDrawer').classList.contains('open'),false);
  // Opening a different modal supersedes pending focus from the old one.
  run(`openEntryModal('fpDrawer');closeEntryModal('fpDrawer');openPersonDrawer();`);
  $('pd-mother').focus();await tick(300);
  assert.equal(w.document.activeElement.id,'pd-mother');
  run('closeDrawer()');
  console.log('ok: validation focus is stable after animations and modal switches');

  // The actual View entry point includes provenance below the identity grid.
  run(`db.people=[{id:'P-SHELL',name:'Profile Test',units:['Fingerprint']}];serverOn=true;
    api=async()=>({residence:'Lasanod',proximity_note:'Historical context',scope_note:'Scoped records',items:[{
      record_id:'FP-SHELL',unit:'Fingerprint Unit',branch_name:'Lasanod Branch',branch_region:'Sool',
      uploaded_by:'Test Officer',uploader_branch:'HQ',source_table:'clearance_applications',
      branch_source:'clearance_applications.branch_id',uploader_source:'created_by → users',
      created_at:'2026-10-12 09:00:00',location_context:'Recorded location'
    }]});openPersonView('P-SHELL');`);
  await tick();
  assert.ok($('pvModal').classList.contains('open'));
  for(const text of ['Linked Unit Records','Lasanod Branch','Sool','Test Officer','FP-SHELL','2026-10-12 09:00:00','Recorded location']){
    assert.ok($('pvModalBody').textContent.includes(text),text);
  }
  assert.ok($('pvModalBody').querySelector('.pv-grid')
    .compareDocumentPosition($('pvLinkedRecords')) & w.Node.DOCUMENT_POSITION_FOLLOWING);
  assert.ok($('topbar').contains($('userPill')));
  console.log('ok: View opens the identity profile with dated branch/source provenance below identity fields');
  console.log('PASS: refreshed shell and workflow integration');
} finally {w.close()}
