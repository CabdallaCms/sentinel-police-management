#!/usr/bin/env node
// UI contract regression for cascading hierarchical User Management selectors.
// Run with: node backend/test_hierarchy_ui.mjs (requires jsdom@26).
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { JSDOM } from 'jsdom';

const html=fs.readFileSync(new URL('../index.html',import.meta.url),'utf8');
const dom=new JSDOM(html,{url:'http://sentinel.test',runScripts:'outside-only'});
const w=dom.window,ctx=dom.getInternalVMContext();
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/if\(document\.readyState==='loading'\)[\s\S]*$/,'');
vm.runInContext(script,ctx);
const hierarchy={regions:[{id:7,name:'Sool',code:'SOO',districts:[{id:71,name:'Laascaanood',code:'LAAS',region_id:7,
  stations:[{id:'ST-004',station_id:'ST-004',location_id:4,name:'Las Anod Station',code:'SOO-C-01'}],
  branches:[{id:18,name:'Lasanod Branch',unit_type:'fingerprint'}],
  checkpoints:[{id:91,name:'Arena North Gate',checkpoint_code:'CP-SOO-001',legacy_code:null,station_id:4,station_name:'Las Anod Station',branch_id:null}]}]}]};
w.fetch=async(url)=>({ok:true,status:200,json:async()=>({hierarchy})});
const run=(code)=>vm.runInContext(code,ctx);
const $=(id)=>w.document.getElementById(id);
run(`api=async()=>({hierarchy:window.__hierarchy});window.__hierarchy=${JSON.stringify(hierarchy)};
  userLocationHierarchyCache=null;sessionUser={role:'PoliceStationOfficer'};
  document.body.insertAdjacentHTML('beforeend',userLocationFields('nu')+
    '<select id="nu-role"><option value="PoliceStationOfficer">Station Officer</option><option value="CheckpointSouth">Checkpoint</option></select>');`);
await run(`refreshUserStationOptions('nu-assignment','')`);
assert.ok($('nu-region').querySelector('option[value="7"]'),'region selector receives live region rows');
$('nu-region').value='7';run(`refreshUserLocationCascade('nu')`);
assert.ok($('nu-district').querySelector('option[value="71"]'),'district options cascade from the selected region');
$('nu-district').value='71';run(`refreshUserLocationCascade('nu')`);
assert.ok($('nu-assignment').querySelector('option[value="station:4"]'),'station assignment uses the stable database location id');
assert.ok($('nu-assignment').querySelector('option[value="branch:18"]'),'branch assignment is included under the selected district');
assert.ok($('nu-checkpoint').querySelector('option[value="91"]'),'checkpoint options cascade under the same region and district');
$('nu-role').value='CheckpointSouth';run(`refreshUserLocationOptions('nu')`);
assert.equal($('nu-assignment-wrap').style.display,'none','checkpoint role hides station/branch assignment');
$('nu-checkpoint').value='91';run(`syncUserLocationSelection('nu')`);
assert.equal($('nu-scope').value,'CP-SOO-001','checkpoint assignment stores the scalable checkpoint code');
assert.equal($('nu-branch').value,'Las Anod Station','checkpoint attribution resolves its real station parent');
const rendered=run(`renderAuditTrail([{action:'APPROVE',entity:'clearance',entity_id:'FP-1',actor_label:'Testuser (Badge #Not recorded, User: test) at Las Anod Station',details:'approved',created_at:'2026-10-26'}])`);
assert.match(rendered,/Badge #Not recorded, User: test\) at Las Anod Station/,'audit history explicitly renders each attribution field');
console.log('ALL HIERARCHY UI TESTS PASSED');
