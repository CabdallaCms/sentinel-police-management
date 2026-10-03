/* Sentinel — Directorate services UI: fingerprint clearance, CID cases & alerts, HR officers & conduct, structure admin.
 * Every list, vocabulary and unit picker is read from the API (policy data and the org tree) — nothing here names a
 * bureau, branch, region or rank.  Person fields reuse IdentityForm, so applicants, guardians and officers are resolved
 * against the Central Person Registry exactly as on the intake screen.  No framework, no build step.
 */
(function () {
  'use strict';
  var U = window.SentinelUI, I = window.SentinelIdentity;
  var api = U.api, session = U.session, setResult = U.setResult, clearResult = U.clearResult, esc = I.esc;
  var $ = function (s) { return document.querySelector(s); };
  var forms = {}, voc = null, pick = null, uploaded = {}, openCase = null, partCount = 0;
  var ID_ROW = ['first_name', 'second_name', 'third_name', 'fourth_name', 'date_of_birth', 'place_of_birth', 'national_id', 'passport_id'];
  var EXTRA = ['mother_name', 'residence', 'phone', 'occupation'];

  // ------------------------------------------------------------------ helpers
  function options(list, placeholder) {
    return (placeholder == null ? '' : '<option value="">' + esc(placeholder) + '</option>') +
      (list || []).map(function (x) { return '<option>' + esc(x) + '</option>'; }).join('');
  }
  function unitOptions(list, placeholder) {
    return (placeholder == null ? '' : '<option value="">' + esc(placeholder) + '</option>') +
      (list || []).map(function (u) { return '<option value="' + esc(u.code) + '">' + esc(u.name) + (u.region ? ' — ' + esc(u.region) : '') + ' (' + esc(u.code) + ')</option>'; }).join('');
  }
  function val(id) { return I.clean(($(id) || {}).value); }
  function fmt(t) { return t ? String(t).replace('T', ' ').slice(0, 16) : ''; }
  function msg(d) { return (d.problems && d.problems.length) ? d.problems.map(function (p) { return p.message; }).join(' · ') : (d.message || 'Request failed'); }
  function table(heads, rows, empty) {
    if (!rows.length) return '<div class="kv">' + (empty || 'Nothing here yet.') + '</div>';
    return '<table class="res"><thead><tr>' + heads.map(function (h) { return '<th>' + h + '</th>'; }).join('') + '</tr></thead><tbody>' +
      rows.map(function (r) { return '<tr>' + r.map(function (c) { return '<td>' + c + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table>';
  }
  function btn(act, id, label, cls) { return '<button type="button" class="btn ' + (cls || '') + '" data-act="' + act + '" data-id="' + esc(id) + '">' + esc(label) + '</button> '; }
  function fill(sel, html, fallback) { var el = $(sel); el.innerHTML = html || '<option value="">' + (fallback || '— none —') + '</option>'; }
  function readBytes(file) {
    if (file.arrayBuffer) return file.arrayBuffer().then(function (b) { return new Uint8Array(b); });
    return new Promise(function (res, rej) { var r = new FileReader(); r.onload = function () { res(new Uint8Array(r.result)); }; r.onerror = rej; r.readAsArrayBuffer(file); });
  }
  function uploadOne(file) {
    var key = [file.name, file.size, file.lastModified].join('|');
    if (uploaded[key]) return Promise.resolve(uploaded[key]);
    return readBytes(file).then(function (bytes) {
      var h = { 'X-Filename': encodeURIComponent(file.name || 'file'), 'Content-Type': 'application/octet-stream' };
      if (session.user) h['X-Dev-User'] = session.user;
      return fetch('/api/uploads', { method: 'POST', headers: h, body: bytes });
    }).then(function (r) { return r.json().then(function (d) {
      if (r.status !== 201) throw { message: (file.name || 'File') + ': ' + (d.message || 'upload failed') };
      uploaded[key] = d.name; return d.name; }); });
  }
  function uploadInput(sel) {
    var files = Array.prototype.slice.call(($(sel) && $(sel).files) || []);
    return files.reduce(function (p, f) { return p.then(function (acc) { return uploadOne(f).then(function (n) { acc.push(n); return acc; }); }); }, Promise.resolve([]));
  }
  function mark(fields, map) {
    document.querySelectorAll('.field.invalid').forEach(function (n) { n.classList.remove('invalid'); });
    (fields || []).forEach(function (f) { var el = $(map[f] || ('#' + f)); var w = el && el.closest && el.closest('.field'); if (w) w.classList.add('invalid'); });
  }
  function personBlock(prefix, container, required) {
    $(container).innerHTML = '<div class="grid2">' + U.fieldsBlock(prefix, ID_ROW, true) + '</div>' +
      '<div id="' + prefix + '-matchlist" class="m-matchlist"></div><div id="' + prefix + '-match" class="match-banner" role="status" aria-live="polite"></div>' +
      '<div class="grid2" style="margin-top:12px">' + U.fieldsBlock(prefix, EXTRA, true) + '</div>';
    forms[prefix] = new U.IdentityForm(prefix, ID_ROW.concat(EXTRA), {});
  }

  // ------------------------------------------------------------------ session
  function loadUsers() {
    return fetch('/api/dev/users').then(function (r) { return r.ok ? r.json() : { users: [] }; }).then(function (d) {
      var sel = $('#user');
      if (!d.users.length) { sel.innerHTML = '<option value="">(sign-in not configured)</option>'; return; }
      sel.innerHTML = '<option value="">— choose a user —</option>' + d.users.map(function (u) {
        return '<option value="' + esc(u.username) + '">' + esc(u.display_name) + ' — ' + esc(u.roles || 'no role') + '</option>'; }).join('');
      sel.value = session.user;
    });
  }
  function loadSession() {
    voc = null; pick = null;
    if (!session.user) { $('#who').textContent = ''; return Promise.resolve(); }
    return Promise.all([api('GET', '/api/me'), api('GET', '/api/directorate/vocabularies'), api('GET', '/api/directorate/units')]).then(function (rs) {
      if (rs[0].status !== 200) { $('#who').textContent = rs[0].data.message || 'Sign-in failed'; return; }
      $('#who').textContent = rs[0].data.user.display_name;
      voc = rs[1].data; pick = rs[2].data; applyVocab(); loadAll();
    });
  }
  function applyVocab() {
    if (!voc || !pick) return;
    var f = pick.filing;
    fill('#cl-unit', unitOptions(f.clearance), '— none assigned to your account —');
    $('#cl-save').disabled = !f.clearance.length;
    fill('#cl-purpose', options(voc.clearance_purposes, '— select —'));
    var g = (voc.clearance_required || {}).guardian || 'all';
    $('#cl-gpolicy').textContent = g === 'all' ? 'required for every applicant' : g === 'minors' ? 'required for under-18s' : 'optional';
    $('#cl-window').textContent = voc.review_window_hours;
    fill('#cs-owner', unitOptions(f.cid), '— none —'); $('#cs-save').disabled = !f.cid.length;
    fill('#cs-status', options(voc.case_statuses)); fill('#cs-newstatus', options(voc.case_statuses)); fill('#cs-evtype', options(voc.evidence_types));
    $('#al-save').disabled = !f.alert.length;
    fill('#of-unit', unitOptions(f.posting), '— none —'); $('#of-new-panel').classList.toggle('hidden', !f.posting.length);
    var o = voc.officer; fill('#of-rank', options(o.ranks, '— select —')); fill('#of-role', options(o.divisions, '— select —'));
    fill('#of-doc1t', options(o.doc_types_primary, '— select —')); fill('#of-grel', options(o.guarantor_relationships, '— not set —'));
    fill('#cd-unit', unitOptions(f.conduct), '— none —'); $('#cd-new-panel').classList.toggle('hidden', !f.conduct.length);
    fill('#cd-type', options(Object.keys(voc.conduct.classifications), '— select —')); onCdType();
    fill('#cd-rank', options(voc.officer.ranks, '— no rank change —'));
    var types = voc.unit_types || [];
    fill('#ad-type', options(types.map(function (t) { return t.code; }), '— select —'));
    fill('#ad-region', options(voc.regions, '— none —'));
    fill('#as-role', options((voc.roles || []).map(function (r) { return r.code; }), '— select —'));
  }
  function loadAll() { return Promise.all([loadClearance(), loadCases(), loadAlerts(), loadOfficers(), loadConduct(), loadAdmin()]); }

  // ------------------------------------------------------------------ CLEARANCE
  var CL_MAP = { purpose: '#cl-purpose', applicant_photo: '#cl-photo', applicant_docs: '#cl-docs', guardian: '#cg-first_name',
    guardian_relationship: '#cl-grel', guardian_docs: '#cl-gdocs', unit: '#cl-unit', date_of_birth: '#c-date_of_birth' };
  function saveClearance() {
    var a = forms.c, g = forms.cg, v = a.values(), gv = g.values(), res = 'cl-result';
    clearResult(res); mark([], {}); a.markInvalid([]); g.markInvalid([]);
    var problems = I.validateNew(v, {});
    if (!$('#cl-purpose').value) problems.push({ field: 'purpose', message: 'Clearance reason is required' });
    if (!($('#cl-photo').files || []).length) problems.push({ field: 'applicant_photo', message: 'Applicant photo is required' });
    if (!($('#cl-docs').files || []).length) problems.push({ field: 'applicant_docs', message: 'Applicant documents are required' });
    if (problems.length) { mark(problems.map(function (p) { return p.field; }), CL_MAP); return setResult(res, 'bad', problems.map(function (p) { return p.message; }).join(' · ')); }
    var b = $('#cl-save'); b.disabled = true;
    return Promise.all([uploadInput('#cl-photo'), uploadInput('#cl-docs'), uploadInput('#cl-gdocs')]).then(function (u) {
      var guardian = I.personPayload(gv).person, has = Object.keys(guardian).length > 0;
      return api('POST', '/api/clearance-applications', { unit: $('#cl-unit').value, purpose: $('#cl-purpose').value,
        applicant: I.personPayload(v).person, link_person_ref: a.person ? a.person.person_ref : undefined, confirm_new: a.confirmNew,
        applicant_photo: u[0][0], applicant_docs: u[1], guardian: has ? guardian : undefined, guardian_relationship: $('#cl-grel').value,
        guardian_person_ref: g.person ? g.person.person_ref : undefined, guardian_confirm_new: g.confirmNew, guardian_docs: u[2] });
    }).then(function (r) {
      var d = r.data;
      if (r.status === 201) {
        var ap = d.application;
        setResult(res, 'good', ap.application_ref + ' filed at ' + ap.intake_unit.name + ' for ' + d.person.full_name + '. Pending national review — eligible after ' + fmt(ap.review_eligible_at) + '.');
        loadClearance();
      } else if (r.status === 409 && d.error === 'possible_duplicate') {
        (d.scope === 'guardian' ? g : a).handleResult(d.search); setResult(res, 'bad', (d.scope === 'guardian' ? 'Guardian: ' : 'Applicant: ') + d.message);
      } else { mark(d.fields, CL_MAP); setResult(res, 'bad', msg(d)); }
    }).catch(function (e) { setResult(res, 'bad', (e && e.message) || String(e)); }).then(function () { b.disabled = !$('#cl-unit').value; });
  }
  function resetClearance() {
    forms.c.clear(); forms.cg.clear(); uploaded = {};
    ['#cl-photo', '#cl-docs', '#cl-gdocs'].forEach(function (s) { try { $(s).value = ''; } catch (e) {} });
    $('#cl-grel').value = ''; clearResult('cl-result'); mark([], {});
  }
  function loadClearance() {
    return api('GET', '/api/clearance-applications?limit=30').then(function (r) {
      if (r.status !== 200) { $('#cl-list').innerHTML = '<div class="kv">' + esc(r.data.message || 'You cannot view applications.') + '</div>'; return; }
      $('#cl-list').innerHTML = table(['Reference', 'Applicant', 'Reason', 'Intake', 'Status', 'Window', ''], r.data.items.map(function (a) {
        var st = a.status === 'Approved' ? '<span class="badge ok">Approved</span> ' + esc(a.certificate_number) : a.status === 'Rejected' ? '<span class="badge alert">Rejected</span>' : esc(a.status);
        var win = a.status !== 'Pending Review' ? '' : (a.review_locked ? 'locked · ' + esc(a.hours_remaining) + ' h left' : 'open');
        var acts = '';
        if (a.can_decide) acts += btn('approve', a.application_ref, 'Approve & sign', 'primary') + btn('reject', a.application_ref, 'Reject');
        if (a.can_print) acts += btn('print', a.application_ref, 'Print');
        return ['<b>' + esc(a.application_ref) + '</b>', esc(a.full_name) + ' <span class="kv">' + esc(a.person_ref) + '</span>', esc(a.purpose), esc(a.intake_code), st, win, acts];
      }), 'No applications.');
    });
  }
  function clearanceAct(act, ref) {
    clearResult('cl-cert');
    var call = act === 'print' ? api('POST', '/api/clearance-applications/' + ref + '/print', {})
      : api('POST', '/api/clearance-applications/' + ref + '/decision', { decision: act, notes: val('#cl-notes') });
    return call.then(function (r) {
      var d = r.data;
      if (r.status !== 200) return setResult('cl-cert', 'bad', d.message || 'Request failed');
      if (act === 'print') {
        var c = d.certificate;
        setResult('cl-cert', 'good', 'CERTIFICATE ' + d.certificate_number + ' — ' + c.holder + ' · ' + c.purpose + ' · issued ' + String(c.issued_at).slice(0, 10) +
          ' by ' + c.issuer_name + ' · key ' + d.key_id + ' · signature ' + String(d.signature).slice(0, 16) + '… · print #' + d.print_count + ' · verify at /verify.html?n=' + d.certificate_number);
      } else setResult('cl-cert', 'good', act === 'approve' ? ref + ' approved and signed: ' + d.certificate_number + (d.review_period_bypassed ? ' (review window overridden — audited)' : '') : ref + ' rejected.');
      loadClearance();
    });
  }

  // ------------------------------------------------------------------ CID
  function addPart() {
    var i = ++partCount;
    var d = document.createElement('div'); d.className = 'grid2 cs-part'; d.dataset.i = i;
    d.innerHTML = '<div class="field"><label>Role</label><select data-k="role">' + options(voc ? voc.participant_roles : ['Suspect']) + '</select></div>' +
      '<div class="field"><label>First name *</label><input data-k="first_name" autocomplete="off"></div>' +
      '<div class="field"><label>Second name *</label><input data-k="second_name" autocomplete="off"></div>' +
      '<div class="field"><label>Third name *</label><input data-k="third_name" autocomplete="off"></div>' +
      '<div class="field"><label>Date of birth</label><input data-k="date_of_birth" type="date"></div>' +
      '<div class="field"><label>National ID</label><input data-k="national_id" autocomplete="off"></div>';
    $('#cs-parts').appendChild(d);
  }
  function partsPayload() {
    return Array.prototype.slice.call(document.querySelectorAll('#cs-parts .cs-part')).map(function (d) {
      var o = {}; d.querySelectorAll('[data-k]').forEach(function (el) { var v = I.clean(el.value); if (v) o[el.dataset.k] = v; });
      var confirm = d.dataset.confirm === '1'; if (confirm) o.confirm_new = true; return o;
    }).filter(function (o) { return o.first_name || o.second_name || o.third_name; });
  }
  function saveCase() {
    clearResult('cs-result'); mark([], {});
    if (!val('#cs-category')) return setResult('cs-result', 'bad', 'Crime category is required');
    return api('POST', '/api/crime-cases', { owner_unit: $('#cs-owner').value, category: val('#cs-category'), location: val('#cs-location'),
      status: $('#cs-status').value, incident_summary: val('#cs-summary'), participants: partsPayload() }).then(function (r) {
      var d = r.data;
      if (r.status === 201) {
        setResult('cs-result', 'good', d.case.case_ref + ' opened with ' + d.participants.length + ' participant(s)' + d.participants.filter(function (p) { return p.raises_alert; }).map(function (p) { return ' · ALERT raised for ' + p.full_name; }).join(''));
        $('#cs-parts').innerHTML = ''; addPart(); ['#cs-category', '#cs-location', '#cs-summary'].forEach(function (s) { $(s).value = ''; }); loadCases(); loadAlerts();
      } else if (r.status === 409 && d.error === 'possible_duplicate') {
        var row = document.querySelectorAll('#cs-parts .cs-part')[d.index || 0]; if (row) row.dataset.confirm = '1';
        setResult('cs-result', 'bad', 'Participant ' + ((d.index || 0) + 1) + ': ' + d.message + ' Press "Open case" again to confirm they are a different person.');
      } else setResult('cs-result', 'bad', msg(d));
    });
  }
  function loadCases() {
    return api('GET', '/api/crime-cases?limit=30').then(function (r) {
      $('#cs-list').innerHTML = r.status !== 200 ? '<div class="kv">' + esc(r.data.message || 'You cannot view cases.') + '</div>' :
        table(['Case', 'Category', 'Status', 'Owner', 'Opened', 'People', ''], r.data.items.map(function (c) {
          return ['<b>' + esc(c.case_ref) + '</b>', esc(c.category), esc(c.status), esc(c.owner_code), esc(fmt(c.created_at)), esc(c.participants), btn('open-case', c.case_ref, 'Open')]; }), 'No cases visible to you.');
    });
  }
  function showCase(ref) {
    return api('GET', '/api/crime-cases/' + ref).then(function (r) {
      if (r.status !== 200) return;
      var c = r.data; openCase = c;
      $('#cs-detail-panel').classList.remove('hidden'); $('#cs-detail-title').textContent = c.case_ref + ' — ' + c.category;
      $('#cs-newstatus').value = c.status;
      $('#cs-detail').innerHTML = '<div class="kv">' + esc(c.owner_name) + ' · ' + esc(c.region || 'national') + ' · ' + esc(c.location || '') + '</div><p>' + esc(c.incident_summary || '') + '</p>' +
        table(['Person', 'Role', 'Alert', 'Origin'], c.participants.map(function (p) { return [esc(p.full_name) + ' <span class="kv">' + esc(p.person_ref) + '</span>', esc(p.role), esc(p.alert_status), esc(p.origin)]; }), 'No participants.') +
        table(['Evidence', 'Type', 'File', 'Caption'], c.evidence.map(function (e) { return [esc(e.evidence_ref), esc(e.file_type), '<a href="/api/uploads/' + esc(e.file_name) + '">file</a>', esc(e.caption || '')]; }), 'No evidence yet.');
      $('#cs-update').disabled = !c.can_update; $('#cs-addev').disabled = !c.can_update;
    });
  }
  function updateCase() {
    if (!openCase) return;
    return api('PATCH', '/api/crime-cases/' + openCase.case_ref, { changes: { status: $('#cs-newstatus').value } }).then(function (r) {
      setResult('cs-detail-result', r.status === 200 ? 'good' : 'bad', r.status === 200 ? 'Status saved.' : msg(r.data)); showCase(openCase.case_ref); loadCases(); });
  }
  function addEvidence() {
    if (!openCase) return;
    var f = $('#cs-evfile').files; if (!f || !f.length) return setResult('cs-detail-result', 'bad', 'Choose an evidence file first');
    return uploadInput('#cs-evfile').then(function (u) {
      return api('POST', '/api/crime-cases/' + openCase.case_ref + '/evidence', { file: u[0], file_type: $('#cs-evtype').value, caption: val('#cs-evcap') });
    }).then(function (r) { setResult('cs-detail-result', r.status === 201 ? 'good' : 'bad', r.status === 201 ? r.data.evidence.evidence_ref + ' attached.' : msg(r.data)); showCase(openCase.case_ref); });
  }
  function loadAlerts() {
    return api('GET', '/api/suspect-alerts').then(function (r) {
      $('#al-list').innerHTML = r.status !== 200 ? '<div class="kv">' + esc(r.data.message || 'You cannot view alerts.') + '</div>' :
        table(['Person', 'Role', 'Origin', 'Case', 'Reason', ''], r.data.items.map(function (a) {
          return [esc(a.full_name) + ' <span class="kv">' + esc(a.person_ref) + '</span>', esc(a.role), esc(a.origin), esc(a.case_ref || '—'), esc(a.notes || ''),
            a.can_lift ? '<input data-reason="' + esc(a.alert_ref) + '" placeholder="reason to lift" style="width:140px"> ' + btn('lift', a.alert_ref, 'Lift') : '']; }), 'No active alerts.');
    });
  }
  function saveAlert() {
    clearResult('al-result');
    var p = { first_name: val('#al-first'), second_name: val('#al-second'), third_name: val('#al-third'), date_of_birth: $('#al-dob').value, national_id: val('#al-nid') };
    return api('POST', '/api/suspect-alerts', { person: p, reason: val('#al-reason'), owner_unit: pick && pick.filing.alert[0] && pick.filing.alert[0].code, confirm_new: $('#al-save').dataset.confirm === '1' }).then(function (r) {
      var d = r.data;
      if (r.status === 201) { $('#al-save').dataset.confirm = ''; setResult('al-result', 'good', d.alert.full_name + ' listed (' + d.alert.alert_ref + ').'); loadAlerts(); }
      else if (r.status === 409 && d.error === 'possible_duplicate') { $('#al-save').dataset.confirm = '1'; setResult('al-result', 'bad', d.message + ' Press "List person" again to confirm a different person.'); }
      else setResult('al-result', 'bad', msg(d));
    });
  }

  // ------------------------------------------------------------------ HR
  function loadOfficers() {
    var q = val('#of-q');
    return api('GET', '/api/officers?limit=50' + (q ? '&q=' + encodeURIComponent(q) : '')).then(function (r) {
      if (r.status !== 200) { $('#of-list').innerHTML = '<div class="kv">' + esc(r.data.message || 'You cannot view officers.') + '</div>'; return; }
      $('#of-list').innerHTML = table(['Service ref', 'Name', 'Rank', 'Division', 'Posting', 'Duty', ''], r.data.items.map(function (o) {
        return ['<b>' + esc(o.service_ref) + '</b>', esc(o.full_name), esc(o.rank), esc(o.unit_role), esc(o.unit_name) + ' <span class="kv">' + esc(o.region || '') + '</span>', esc(o.duty_status), btn('open-officer', o.service_ref, 'History')]; }),
        'No officers visible to you.');
      fill('#cd-officer', (r.data.items || []).map(function (o) { return '<option value="' + esc(o.service_ref) + '">' + esc(o.full_name) + ' — ' + esc(o.rank) + ' (' + esc(o.service_ref) + ')</option>'; }).join(''), '— no officers —');
    });
  }
  function showOfficer(ref) {
    return api('GET', '/api/officers/' + ref).then(function (r) {
      if (r.status !== 200) return;
      $('#of-detail').innerHTML = '<b>' + esc(r.data.full_name) + '</b> · ' + esc(r.data.rank) + ' · ' + esc(r.data.duty_status) + '<ul>' +
        r.data.history.map(function (h) { return '<li>' + esc(fmt(h.created_at)) + ' — ' + esc(h.summary) + '</li>'; }).join('') + '</ul>';
    });
  }
  function saveOfficer() {
    var f = forms.o, v = f.values(); clearResult('of-result'); f.markInvalid([]);
    var problems = I.validateNew(v, { allowNoId: true });
    ['#of-unit', '#of-rank', '#of-role', '#of-enlist', '#of-gname', '#of-gaddr', '#of-gcontact', '#of-doc1t'].forEach(function (s) { if (!val(s)) problems.push({ message: ($(s).closest('.field').querySelector('label').textContent.replace(' *', '')) + ' is required' }); });
    if (!($('#of-photo').files || []).length) problems.push({ message: 'Officer picture is required' });
    if (!($('#of-doc1').files || []).length) problems.push({ message: 'Document 1 file is required' });
    if (problems.length) return setResult('of-result', 'bad', problems.map(function (p) { return p.message; }).join(' · '));
    return Promise.all([uploadInput('#of-photo'), uploadInput('#of-doc1')]).then(function (u) {
      return api('POST', '/api/officers', { unit: $('#of-unit').value, rank: $('#of-rank').value, unit_role: $('#of-role').value, date_of_enlistment: $('#of-enlist').value,
        person: I.personPayload(v).person, person_ref: f.person ? f.person.person_ref : undefined, confirm_new: f.confirmNew, photo: u[0][0], doc1_type: $('#of-doc1t').value, doc1_file: u[1][0],
        guarantor: { name: val('#of-gname'), address: val('#of-gaddr'), contact: val('#of-gcontact'), relationship: $('#of-grel').value } });
    }).then(function (r) {
      var d = r.data;
      if (r.status === 201) { setResult('of-result', 'good', d.officer.service_ref + ' registered: ' + d.officer.full_name + ' (' + d.officer.rank + ') at ' + d.officer.unit.name + '.'); loadOfficers(); }
      else if (r.status === 409 && d.error === 'possible_duplicate') { f.handleResult(d.search); setResult('of-result', 'bad', d.message); }
      else setResult('of-result', 'bad', msg(d));
    }).catch(function (e) { setResult('of-result', 'bad', (e && e.message) || String(e)); });
  }
  function onCdType() {
    var t = $('#cd-type').value, list = (voc && voc.conduct.classifications[t]) || [];
    fill('#cd-class', options(list, '— select —')); onCdClass();
  }
  function onCdClass() { $('#cd-rank-wrap').classList.toggle('hidden', !(voc && voc.conduct.rank_direction[$('#cd-class').value])); }
  function saveConduct() {
    clearResult('cd-result');
    return uploadInput('#cd-doc').then(function (docs) {
      return api('POST', '/api/conduct', { officer: $('#cd-officer').value, unit: $('#cd-unit').value, action_type: $('#cd-type').value, classification: $('#cd-class').value,
        proposed_rank: $('#cd-rank-wrap').classList.contains('hidden') ? undefined : $('#cd-rank').value, narrative: val('#cd-narr'), documents: docs });
    }).then(function (r) {
      setResult('cd-result', r.status === 201 ? 'good' : 'bad', r.status === 201 ? r.data.conduct.action_ref + ' submitted to HR for ' + r.data.conduct.officer_name + '.' : msg(r.data));
      if (r.status === 201) { $('#cd-narr').value = ''; loadConduct(); }
    }).catch(function (e) { setResult('cd-result', 'bad', (e && e.message) || String(e)); });
  }
  function loadConduct() {
    return api('GET', '/api/conduct?limit=50').then(function (r) {
      $('#cd-list').innerHTML = r.status !== 200 ? '<div class="kv">' + esc(r.data.message || 'You cannot view conduct files.') + '</div>' :
        table(['File', 'Officer', 'Action', 'Status', 'Filed by', 'Effect', ''], r.data.items.map(function (c) {
          var eff = [c.rank_applied ? 'rank → ' + c.proposed_rank : '', c.duty_applied ? 'duty → ' + c.duty_applied : ''].filter(Boolean).join(', ');
          var acts = c.can_review ? btn('cd-review', c.action_ref, 'Take up') + btn('cd-approve', c.action_ref, 'Approve', 'primary') + btn('cd-reject', c.action_ref, 'Reject') : '';
          return ['<b>' + esc(c.action_ref) + '</b>', esc(c.officer_name) + ' <span class="kv">' + esc(c.officer_rank) + '</span>', esc(c.classification) + ' <span class="kv">' + esc(c.action_type) + '</span>',
            esc(c.status), esc(c.submitted_by_name || ''), esc(eff), acts]; }), 'No conduct files visible to you.');
    });
  }
  function conductAct(act, ref) {
    return api('POST', '/api/conduct/' + ref + '/review', { decision: act, notes: val('#cd-notes') }).then(function (r) {
      setResult('cd-review-result', r.status === 200 ? 'good' : 'bad', r.status === 200 ? ref + ' → ' + r.data.status + (r.data.rank_applied ? ' · officer is now ' + r.data.officer.rank : '') + (r.data.duty_applied ? ' · duty status ' + r.data.duty_applied : '') : msg(r.data));
      loadConduct(); loadOfficers();
    });
  }

  // ------------------------------------------------------------------ ADMIN
  function loadAdmin() {
    return Promise.all([api('GET', '/api/admin/units'), api('GET', '/api/admin/assignments')]).then(function (rs) {
      $('#ad-units').innerHTML = rs[0].status !== 200 ? '<div class="kv">You cannot view units.</div>' : table(['Code', 'Name', 'Type', 'Parent', 'Region', 'Status'], rs[0].data.items.map(function (u) {
        return ['<b>' + esc(u.code) + '</b>', '<span style="padding-left:' + (u.depth * 12) + 'px">' + esc(u.name) + '</span>', esc(u.unit_type), esc(u.parent_code || '—'), esc(u.region_code || '—'), esc(u.status)]; }));
      var all = rs[0].status === 200 ? rs[0].data.items : [];
      var mg = all.filter(function (u) { return u.can_manage; });
      fill('#ad-parent', unitOptions(mg, '— select —')); fill('#as-unit', unitOptions(all.filter(function (u) { return u.can_assign; }), '— select —'));
      $('#ad-new-panel').classList.toggle('hidden', !mg.length);
      $('#as-list').innerHTML = rs[1].status !== 200 ? '' : table(['User', 'Role', 'Unit', 'Subtree', 'State', ''], rs[1].data.items.map(function (a) {
        return [esc(a.username), esc(a.role_name), esc(a.unit), a.include_descendants ? 'yes' : 'no', a.revoked_at ? 'revoked' : 'active', !a.revoked_at && a.can_revoke ? btn('revoke', a.id, 'Revoke') : '']; }), 'No assignments in your scope.');
    });
  }
  function saveUnit() {
    clearResult('ad-result'); var region = $('#ad-region').value;
    return api('POST', '/api/admin/units', { parent: $('#ad-parent').value, unit_type: $('#ad-type').value, code: val('#ad-code'), name: val('#ad-name'), attrs: region ? { region: region } : {} }).then(function (r) {
      setResult('ad-result', r.status === 201 ? 'good' : 'bad', r.status === 201 ? r.data.unit.code + ' created under ' + r.data.unit.parent_code + (r.data.unit.region ? ' (' + r.data.unit.region + ')' : '') + '.' : msg(r.data));
      if (r.status === 201) { loadSession(); }
    });
  }
  function saveGrant() {
    clearResult('as-result');
    return api('POST', '/api/admin/assignments', { username: val('#as-user'), role: $('#as-role').value, unit: $('#as-unit').value }).then(function (r) {
      setResult('as-result', r.status === 201 ? 'good' : 'bad', r.status === 201 ? 'Granted.' : msg(r.data)); loadAdmin(); });
  }

  // ------------------------------------------------------------------ wiring
  function showTab(name) {
    document.querySelectorAll('.tabs button').forEach(function (b) { b.setAttribute('aria-selected', String(b.dataset.tab === name)); });
    document.querySelectorAll('.tabpane').forEach(function (p) { p.classList.toggle('hidden', p.id !== 'tab-' + name); });
    try { history.replaceState(null, '', '#' + name); } catch (e) {}
  }
  function init() {
    personBlock('c', '#c-fields'); personBlock('o', '#o-fields');
    $('#cg-fields').innerHTML = '<div class="grid2">' + U.fieldsBlock('cg', ['first_name', 'second_name', 'third_name', 'fourth_name'], true) +
      U.fieldsBlock('cg', ['national_id', 'passport_id', 'phone', 'residence', 'occupation'], false) + '</div>' +
      '<div id="cg-matchlist" class="m-matchlist"></div><div id="cg-match" class="match-banner" role="status" aria-live="polite"></div>';
    forms.cg = new U.IdentityForm('cg', ['first_name', 'second_name', 'third_name', 'fourth_name', 'national_id', 'passport_id', 'phone', 'residence', 'occupation'], {});
    document.querySelectorAll('.tabs button').forEach(function (b) { b.addEventListener('click', function () { showTab(b.dataset.tab); }); });
    $('#user').addEventListener('change', function (e) {
      session.user = e.target.value; session.unit = ''; sessionStorage.setItem('sentinel.user', session.user); sessionStorage.removeItem('sentinel.unit');
      resetClearance(); loadSession();
    });
    $('#cl-save').addEventListener('click', saveClearance); $('#cl-new').addEventListener('click', resetClearance);
    $('#cs-addpart').addEventListener('click', addPart); $('#cs-save').addEventListener('click', saveCase);
    $('#cs-update').addEventListener('click', updateCase); $('#cs-addev').addEventListener('click', addEvidence);
    $('#al-save').addEventListener('click', saveAlert);
    $('#of-save').addEventListener('click', saveOfficer); $('#cd-save').addEventListener('click', saveConduct);
    $('#cd-type').addEventListener('change', onCdType); $('#cd-class').addEventListener('change', onCdClass);
    $('#of-q').addEventListener('input', function () { clearTimeout(init.t); init.t = setTimeout(loadOfficers, 250); });
    $('#ad-save').addEventListener('click', saveUnit); $('#as-save').addEventListener('click', saveGrant);
    document.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('button[data-act]'); if (!b) return;
      var a = b.dataset.act, id = b.dataset.id;
      if (a === 'approve' || a === 'reject' || a === 'print') clearanceAct(a, id);
      else if (a === 'open-case') showCase(id);
      else if (a === 'open-officer') showOfficer(id);
      else if (a === 'lift') { var inp = document.querySelector('[data-reason="' + id + '"]');
        api('POST', '/api/suspect-alerts/' + id + '/lift', { reason: inp ? inp.value : '' }).then(function (r) { setResult('al-result', r.status === 200 ? 'good' : 'bad', r.status === 200 ? id + ' lifted.' : msg(r.data)); loadAlerts(); }); }
      else if (a === 'cd-review') conductAct('review', id); else if (a === 'cd-approve') conductAct('approve', id); else if (a === 'cd-reject') conductAct('reject', id);
      else if (a === 'revoke') api('POST', '/api/admin/assignments/' + id + '/revoke', {}).then(function (r) { setResult('as-result', r.status === 200 ? 'good' : 'bad', r.status === 200 ? 'Revoked.' : msg(r.data)); loadAdmin(); });
    });
    addPart();
    var tab = (location.hash || '').replace('#', ''); if (['clearance', 'cid', 'hr', 'admin'].indexOf(tab) >= 0) showTab(tab);
    loadUsers().then(loadSession);
  }
  window.SentinelDirectorate = { init: init, forms: forms, showTab: showTab, loadSession: loadSession };
  document.addEventListener('DOMContentLoaded', init);
})();
