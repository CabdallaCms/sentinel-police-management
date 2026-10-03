/* Sentinel — Operations UI: checkpoint stops, airport passenger log, station crime incidents.
 * Reuses the registry pieces from identity-intake.js (IdentityForm: live search, "already exists" banner,
 * field locks, guardian recognition), so a traveler / passenger / guardian typed here is resolved against
 * the Central Person Registry exactly as on the intake screen.  No framework, no build step.
 */
(function () {
  'use strict';
  var U = window.SentinelUI, I = window.SentinelIdentity;
  var api = U.api, session = U.session, setResult = U.setResult, clearResult = U.clearResult, esc = I.esc;
  var $ = function (s) { return document.querySelector(s); };
  var forms = {}, units = { checkpoint: [], airport: [], station: [] }, vocab = null, uploaded = {};

  var PERSON_FIELDS = ['first_name', 'second_name', 'third_name', 'fourth_name', 'date_of_birth', 'place_of_birth', 'national_id', 'passport_id'];
  var ID_ROW = ['first_name', 'second_name', 'third_name', 'fourth_name', 'date_of_birth', 'place_of_birth', 'national_id', 'passport_id'];

  // ------------------------------------------------------------------ helpers
  function options(list, placeholder) {
    return (placeholder == null ? '' : '<option value="">' + esc(placeholder) + '</option>') +
      (list || []).map(function (x) { return '<option>' + esc(x) + '</option>'; }).join('');
  }
  function val(id) { return I.clean(($(id) || {}).value); }
  function fmtTime(t) { return t ? String(t).replace('T', ' ').slice(0, 16) : ''; }

  function markFields(fields, map) {
    document.querySelectorAll('.field.invalid').forEach(function (n) { n.classList.remove('invalid'); });
    (fields || []).forEach(function (f) {
      var sel = map[f] || ('#' + f);
      var el = $(sel); if (!el) return;
      var wrap = el.closest ? el.closest('.field') : null; if (wrap) wrap.classList.add('invalid');
    });
  }

  function failMessage(d) {
    if (d.problems && d.problems.length) return d.problems.map(function (p) { return p.message; }).join(' · ');
    return d.message || 'Request failed';
  }

  // ------------------------------------------------------------------ uploads (photos / documents / evidence)
  function readBytes(file) {
    if (file.arrayBuffer) return file.arrayBuffer().then(function (b) { return new Uint8Array(b); });
    return new Promise(function (resolve, reject) {
      var r = new FileReader(); r.onload = function () { resolve(new Uint8Array(r.result)); }; r.onerror = reject; r.readAsArrayBuffer(file);
    });
  }
  function uploadOne(file) {
    var key = [file.name, file.size, file.lastModified].join('|');
    if (uploaded[key]) return Promise.resolve(uploaded[key]);       // a retry after a warning does not upload twice
    return readBytes(file).then(function (bytes) {
      var h = { 'X-Filename': encodeURIComponent(file.name || 'file'), 'Content-Type': 'application/octet-stream' };
      if (session.user) h['X-Dev-User'] = session.user;
      return fetch('/api/uploads', { method: 'POST', headers: h, body: bytes });
    }).then(function (r) {
      return r.json().then(function (d) {
        if (r.status !== 201) throw { message: (file.name || 'File') + ': ' + (d.message || 'upload failed'), field: true };
        uploaded[key] = d.name; return d.name;
      });
    });
  }
  function uploadInput(sel) {
    var files = Array.prototype.slice.call(($(sel) && $(sel).files) || []);
    return files.reduce(function (p, f) { return p.then(function (acc) { return uploadOne(f).then(function (n) { acc.push(n); return acc; }); }); }, Promise.resolve([]));
  }

  // ------------------------------------------------------------------ session + units
  function loadUsers() {
    return fetch('/api/dev/users').then(function (r) { return r.ok ? r.json() : { users: [] }; }).then(function (d) {
      var sel = $('#user');
      if (!d.users.length) { sel.innerHTML = '<option value="">(sign-in not configured)</option>'; return; }
      sel.innerHTML = '<option value="">— choose a user —</option>' + d.users.map(function (u) {
        return '<option value="' + esc(u.username) + '">' + esc(u.display_name) + ' — ' + esc(u.roles || 'no role') + '</option>'; }).join('');
      sel.value = session.user;
    });
  }

  function fillUnitSelect(sel, list, note) {
    var el = $(sel), mine = list.filter(function (u) { return u.can_create; }), prev = el.value;
    el.innerHTML = mine.map(function (u) {
      return '<option value="' + esc(u.code) + '">' + esc(u.name) + ' — ' + esc(u.district || u.region || '') + ' (' + esc(u.code) + ')</option>'; }).join('');
    if (!mine.length) el.innerHTML = '<option value="">— none assigned to your account —</option>';
    el.disabled = !mine.length;
    var want = mine.some(function (u) { return u.code === prev; }) ? prev : (mine.some(function (u) { return u.code === session.unit; }) ? session.unit : (mine[0] && mine[0].code));
    if (want) el.value = want;
    return mine.length;
  }

  function loadSession() {
    units = { checkpoint: [], airport: [], station: [] }; vocab = null;
    if (!session.user) { $('#who').textContent = ''; applyAbilities(); return Promise.resolve(); }
    return Promise.all([api('GET', '/api/me'), api('GET', '/api/operations/units'), api('GET', '/api/operations/vocabularies')]).then(function (rs) {
      if (rs[0].status !== 200) { $('#who').textContent = rs[0].data.message || 'Sign-in failed'; applyAbilities(); return; }
      $('#who').textContent = rs[0].data.user.display_name;
      units = rs[1].data; vocab = rs[2].data;
      applyAbilities(); loadAllLists();
    });
  }

  function applyAbilities() {
    var n = {
      cp: fillUnitSelect('#cp-unit', units.checkpoint), ap: fillUnitSelect('#ap-unit', units.airport), st: fillUnitSelect('#st-unit', units.station)
    };
    ['cp', 'ap', 'st'].forEach(function (k) { $('#' + k + '-save').disabled = !n[k]; });
    var v = vocab && vocab.incident;
    if (v) {
      $('#st-category').innerHTML = options(v.categories, '— select —');
      $('#st-severity').innerHTML = options(v.severities, '— not set —');
      $('#st-party').innerHTML = options(v.reporting_parties, '— not set —');
      $('#st-status').innerHTML = options(v.statuses, null);
      $('#st-vgender').innerHTML = options(v.victim_genders, '— not set —');
      ['#st-e1type', '#st-e2type'].forEach(function (s) { $(s).innerHTML = options(v.evidence_types, '— type —'); });
    }
    var rule = (vocab && vocab.checkpoint && vocab.checkpoint.guardian) || 'all';
    $('#g-policy').textContent = rule === 'all' ? 'required for every traveler' : rule === 'minors' ? 'required for under-18s' : 'optional';
    var w = vocab && vocab.airport;
    if (w && w.past != null) {
      var d = new Date(), iso = function (x) { return x.toISOString().slice(0, 10); };
      $('#ap-date').min = iso(new Date(d.getTime() - w.past * 864e5)); $('#ap-date').max = iso(new Date(d.getTime() + w.future * 864e5));
    }
  }

  // ------------------------------------------------------------------ recent lists
  function table(heads, rows) {
    if (!rows.length) return '<div class="kv">Nothing recorded yet.</div>';
    return '<table class="res"><thead><tr>' + heads.map(function (h) { return '<th>' + h + '</th>'; }).join('') + '</tr></thead><tbody>' +
      rows.map(function (r) { return '<tr>' + r.map(function (c) { return '<td>' + c + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table>';
  }
  function loadList(kind) {
    var cfg = {
      cp: ['/api/checkpoint-events?limit=15', '#cp-list', ['When', 'Checkpoint', 'Traveler', 'Result', 'Purpose', 'Guardian'], function (i) {
        return [esc(fmtTime(i.created_at)), esc(i.unit_name), esc(i.full_name) + ' <span class="kv">' + esc(i.person_ref) + '</span>',
          i.screening_result === 'Flagged match' ? '<span class="badge flag">FLAGGED</span> ' + esc(i.action_taken) : '<span class="badge ok">Cleared</span>',
          esc(i.purpose_of_visit || ''), esc((i.details && i.details.guardian && i.details.guardian.full_name) || '—')]; }],
      ap: ['/api/airport-records?limit=15', '#ap-list', ['Date', 'Airport', 'Passenger', 'Movement', 'Flight', 'Route'], function (i) {
        return [esc(i.travel_date), esc(i.unit_name), esc(i.full_name) + ' <span class="kv">' + esc(i.person_ref) + '</span>',
          esc(i.movement), esc(i.flight_number), esc(i.route || '')]; }],
      st: ['/api/crimes?limit=15', '#st-list', ['Filed', 'Station', 'File number', 'Category', 'Severity', 'Status', 'Location'], function (i) {
        return [esc(fmtTime(i.incident_at)), esc(i.unit_name), '<b>' + esc(i.file_number) + '</b>', esc(i.category), esc(i.severity || '—'),
          esc(i.case_status), esc(i.location_of_occurrence || '')]; }]
    }[kind];
    return api('GET', cfg[0]).then(function (r) {
      $(cfg[1]).innerHTML = r.status === 200 ? table(cfg[2], r.data.items.map(cfg[3])) : '<div class="kv">' + esc(r.data.message || 'You cannot view these records.') + '</div>';
    });
  }
  function loadAllLists() { return Promise.all([loadList('cp'), loadList('ap'), loadList('st')]); }

  // ------------------------------------------------------------------ CHECKPOINT
  var CP_FIELD_MAP = { purpose_of_visit: '#cp-purpose', current_address: '#t-residence', traveler_photo: '#cp-photo', traveler_docs: '#cp-docs',
    guardian: '#g-first_name', guardian_relationship: '#g-relationship', guardian_phone: '#g-phone', guardian_address: '#g-residence',
    guardian_occupation: '#g-occupation', guardian_docs: '#cp-gdocs', date_of_birth: '#t-date_of_birth', unit: '#cp-unit' };

  function saveCheckpoint() {
    var t = forms.t, g = forms.g, v = t.values(), gv = g.values(), res = '#cp-result';
    clearResult('cp-result'); markFields([], {}); t.markInvalid([]); g.markInvalid([]);
    var problems = I.validateNew(v, { allowNoId: true });
    if (!val('#cp-purpose')) problems.push({ field: 'purpose_of_visit', message: 'Purpose of visit is required' });
    if (!I.clean(v.residence)) problems.push({ field: 'current_address', message: 'Traveler current address is required' });
    if (!($('#cp-photo').files || []).length) problems.push({ field: 'traveler_photo', message: 'Traveler photo is required' });
    if (!($('#cp-docs').files || []).length) problems.push({ field: 'traveler_docs', message: 'At least one traveler document is required' });
    if (problems.length) {
      markFields(problems.map(function (p) { return p.field; }), CP_FIELD_MAP);
      return setResult('cp-result', 'bad', problems.map(function (p) { return p.message; }).join(' · '));
    }
    var btn = $('#cp-save'); btn.disabled = true;
    return Promise.all([uploadInput('#cp-photo'), uploadInput('#cp-docs'), uploadInput('#cp-gdocs')]).then(function (u) {
      var guardian = I.personPayload(gv).person, hasGuardian = Object.keys(guardian).length > 0;
      return api('POST', '/api/checkpoint-events', {
        unit: $('#cp-unit').value, traveler: I.personPayload(v).person,
        link_person_ref: t.person ? t.person.person_ref : undefined, confirm_new: t.confirmNew,
        purpose_of_visit: val('#cp-purpose'), current_address: v.residence, permanent_address: val('#cp-permaddr'), notes: val('#cp-notes'),
        traveler_photo: u[0][0], traveler_docs: u[1], guardian: hasGuardian ? guardian : undefined,
        guardian_relationship: $('#g-relationship').value, guardian_person_ref: g.person ? g.person.person_ref : undefined,
        guardian_confirm_new: g.confirmNew, guardian_docs: u[2] });
    }).then(function (r) {
      var d = r.data;
      if (r.status === 201) {
        var ev = d.event;
        t.select(d.person, { status: 'exists', reason: d.identity.created ? 'Registered just now.' : d.identity.match.reason, tier_label: '', person: d.person,
          core_differences: (d.identity.ignored || []).map(function (i) { return { field: i.field, stored: i.stored, entered: i.entered }; }) });
        setResult('cp-result', ev.alerted ? 'flag' : 'good',
          (ev.alerted ? '⚠ FLAGGED MATCH — ' + ev.action_taken + '. Hold the traveler and contact your supervisor. ' : 'No active alert — cleared. ') +
          ev.event_ref + ' recorded at ' + ev.unit.name + '. ' + I.resultSummary(Object.assign({ person: d.person }, d.identity)) +
          (d.guardian ? ' Guardian: ' + d.guardian.full_name + (d.guardian.created ? ' (new record)' : ' (already in the registry)') + '.' : ''));
        loadList('cp');
      } else if (r.status === 409 && d.error === 'possible_duplicate') {
        (d.scope === 'guardian' ? g : t).handleResult(d.search);
        setResult('cp-result', 'bad', (d.scope === 'guardian' ? 'Guardian: ' : 'Traveler: ') + d.message);
      } else if (r.status === 422) {
        markFields(d.fields, CP_FIELD_MAP); setResult('cp-result', 'bad', failMessage(d));
      } else setResult('cp-result', 'bad', d.message || 'Request failed');
    }).catch(function (e) { setResult('cp-result', 'bad', (e && e.message) || String(e)); })
      .then(function () { btn.disabled = !$('#cp-unit').value; });
  }

  function resetCheckpoint() {
    forms.t.clear(); forms.g.clear(); uploaded = {};
    ['#cp-purpose', '#cp-permaddr', '#cp-notes', '#cp-photo', '#cp-docs', '#cp-gdocs'].forEach(function (s) { try { $(s).value = ''; } catch (e) {} });
    $('#g-relationship').value = ''; clearResult('cp-result'); markFields([], {});
  }

  // ------------------------------------------------------------------ AIRPORT
  var AP_FIELD_MAP = { movement: '#ap-movement', flight_number: '#ap-flight', travel_date: '#ap-date', origin_city: '#ap-origin',
    destination_city: '#ap-dest', unit: '#ap-unit', national_id: '#a-national_id', date_of_birth: '#a-date_of_birth' };

  function syncMovement() {
    var dep = $('#ap-movement').value === 'Departure';
    $('#ap-origin-wrap').querySelector('label').textContent = 'Origin city' + (dep ? '' : ' *');
    $('#ap-dest-wrap').querySelector('label').textContent = 'Destination city' + (dep ? ' *' : '');
  }

  function saveAirport() {
    var a = forms.a, v = a.values();
    clearResult('ap-result'); markFields([], {}); a.markInvalid([]);
    var problems = I.validateNew(v, {});
    if (!val('#ap-flight')) problems.push({ field: 'flight_number', message: 'Flight number is required' });
    if (!$('#ap-date').value) problems.push({ field: 'travel_date', message: 'Travel date is required' });
    var dep = $('#ap-movement').value === 'Departure';
    if (!dep && !val('#ap-origin')) problems.push({ field: 'origin_city', message: 'Origin city is required for an arrival' });
    if (dep && !val('#ap-dest')) problems.push({ field: 'destination_city', message: 'Destination city is required for a departure' });
    if (problems.length) {
      a.markInvalid(problems.filter(function (p) { return PERSON_FIELDS.indexOf(p.field) >= 0; }));
      markFields(problems.map(function (p) { return p.field; }).filter(function (f) { return PERSON_FIELDS.indexOf(f) < 0; }), AP_FIELD_MAP);
      return setResult('ap-result', 'bad', problems.map(function (p) { return p.message; }).join(' · '));
    }
    var btn = $('#ap-save'); btn.disabled = true;
    return api('POST', '/api/airport-records', {
      unit: $('#ap-unit').value, passenger: I.personPayload(v).person, link_person_ref: a.person ? a.person.person_ref : undefined,
      confirm_new: a.confirmNew, movement: $('#ap-movement').value, travel_date: $('#ap-date').value, flight_number: val('#ap-flight'),
      airline: val('#ap-airline'), origin_city: val('#ap-origin'), destination_city: val('#ap-dest'), notes: val('#ap-notes') }).then(function (r) {
      var d = r.data;
      if (r.status === 201) {
        a.select(d.person, { status: 'exists', reason: d.identity.created ? 'Registered just now.' : d.identity.match.reason, tier_label: '', person: d.person,
          core_differences: (d.identity.ignored || []).map(function (i) { return { field: i.field, stored: i.stored, entered: i.entered }; }) });
        setResult('ap-result', 'good', d.record.record_ref + ' — ' + d.record.movement + ' ' + d.record.flight_number + ' at ' + d.record.unit.name + '. ' +
          I.resultSummary(Object.assign({ person: d.person }, d.identity)) + (d.has_active_alert ? ' ⚠ This person has an active alert — inform your supervisor.' : ''));
        loadList('ap');
      } else if (r.status === 409 && d.error === 'possible_duplicate') {
        a.handleResult(d.search); setResult('ap-result', 'bad', d.message);
      } else if (r.status === 409) setResult('ap-result', 'bad', d.message);
      else if (r.status === 422) { markFields(d.fields, AP_FIELD_MAP); a.markInvalid((d.fields || []).filter(function (f) { return PERSON_FIELDS.indexOf(f) >= 0; })); setResult('ap-result', 'bad', failMessage(d)); }
      else setResult('ap-result', 'bad', d.message || 'Request failed');
    }).catch(function (e) { setResult('ap-result', 'bad', String(e)); }).then(function () { btn.disabled = !$('#ap-unit').value; });
  }

  function resetAirport() {
    forms.a.clear(); ['#ap-flight', '#ap-airline', '#ap-origin', '#ap-dest', '#ap-notes'].forEach(function (s) { $(s).value = ''; });
    $('#ap-movement').value = 'Arrival'; $('#ap-date').value = new Date().toISOString().slice(0, 10); syncMovement();
    clearResult('ap-result'); markFields([], {});
  }

  // ------------------------------------------------------------------ STATION
  var ST_FIELD_MAP = { category: '#st-category', severity: '#st-severity', incident_at: '#st-when', location_of_occurrence: '#st-location',
    description: '#st-desc', reporting_party_type: '#st-party', victim_gender: '#st-vgender', victim_age: '#st-vage', officer_ref: '#st-officer',
    evidence1_type: '#st-e1type', evidence2_type: '#st-e2type', victim_person_ref: '#st-vnid', unit: '#st-unit' };
  var victimTimer = null, victimLink = null;

  function checkVictim() {
    var id = val('#st-vnid'), note = $('#st-vlink'); victimLink = null;
    if ($('#st-anon').checked || id.length < 4) { note.textContent = ''; return; }
    api('GET', '/api/persons/search?q=' + encodeURIComponent(id) + '&limit=3').then(function (r) {
      if (id !== val('#st-vnid')) return;                                    // stale
      var d = r.data;
      if (r.status === 200 && d.exists && d.person) {
        victimLink = d.person;
        note.textContent = '✓ Already in the registry: ' + d.person.full_name + ' (' + d.person.person_ref + ') — this incident will be linked to them.';
      } else note.textContent = 'Not in the registry — details stay with this incident only; no person record is created.';
    });
  }

  function saveIncident() {
    clearResult('st-result'); markFields([], {});
    var problems = [];
    [['#st-category', 'category', 'Crime category is required'], ['#st-when', 'incident_at', 'Incident date/time is required'],
     ['#st-location', 'location_of_occurrence', 'Location of occurrence is required'], ['#st-desc', 'description', 'Incident description is required']]
      .forEach(function (c) { if (!val(c[0])) problems.push({ field: c[1], message: c[2] }); });
    if (problems.length) { markFields(problems.map(function (p) { return p.field; }), ST_FIELD_MAP); return setResult('st-result', 'bad', problems.map(function (p) { return p.message; }).join(' · ')); }
    var btn = $('#st-save'); btn.disabled = true;
    return Promise.all([uploadInput('#st-e1file'), uploadInput('#st-e2file')]).then(function (u) {
      var anon = $('#st-anon').checked;
      return api('POST', '/api/crimes', {
        unit: $('#st-unit').value, officer_ref: val('#st-officer'), category: $('#st-category').value, severity: $('#st-severity').value,
        incident_at: $('#st-when').value, location_of_occurrence: val('#st-location'), description: val('#st-desc'),
        reporting_party_type: $('#st-party').value, case_status: $('#st-status').value, statement: val('#st-statement'),
        victim_anonymous: anon, victim_full_name: anon ? '' : val('#st-vname'), victim_national_id: anon ? '' : val('#st-vnid'),
        victim_contact: anon ? '' : val('#st-vcontact'), victim_gender: anon ? '' : $('#st-vgender').value,
        victim_age: anon ? '' : val('#st-vage'), victim_address: anon ? '' : val('#st-vaddr'),
        victim_person_ref: !anon && victimLink ? victimLink.person_ref : undefined,
        evidence1_type: $('#st-e1type').value, evidence1_file: u[0][0], evidence2_type: $('#st-e2type').value, evidence2_file: u[1][0] });
    }).then(function (r) {
      var d = r.data;
      if (r.status === 201) {
        var i = d.incident;
        setResult('st-result', 'good', 'Incident filed: ' + i.file_number + ' at ' + i.unit.name + ' (' + i.category + ').' +
          (i.victim_person_ref ? ' Victim linked to registry record ' + i.victim_person_ref + '.' : '') + (i.victim_anonymous ? ' Victim kept anonymous.' : ''));
        loadList('st');
      } else if (r.status === 422) { markFields(d.fields, ST_FIELD_MAP); setResult('st-result', 'bad', failMessage(d)); }
      else setResult('st-result', 'bad', d.message || 'Request failed');
    }).catch(function (e) { setResult('st-result', 'bad', (e && e.message) || String(e)); }).then(function () { btn.disabled = !$('#st-unit').value; });
  }

  function resetIncident() {
    ['#st-officer', '#st-when', '#st-location', '#st-desc', '#st-vname', '#st-vnid', '#st-vcontact', '#st-vage', '#st-vaddr', '#st-statement', '#st-e1file', '#st-e2file']
      .forEach(function (s) { try { $(s).value = ''; } catch (e) {} });
    ['#st-category', '#st-severity', '#st-party', '#st-vgender', '#st-e1type', '#st-e2type'].forEach(function (s) { $(s).selectedIndex = 0; });
    $('#st-anon').checked = false; onAnon(); $('#st-vlink').textContent = ''; victimLink = null; uploaded = {};
    clearResult('st-result'); markFields([], {});
  }
  function onAnon() { $('#st-victim').classList.toggle('hidden', $('#st-anon').checked); if ($('#st-anon').checked) { $('#st-vlink').textContent = ''; victimLink = null; } }

  // ------------------------------------------------------------------ tabs + init
  function showTab(name) {
    document.querySelectorAll('.tabs button').forEach(function (b) { b.setAttribute('aria-selected', String(b.dataset.tab === name)); });
    [['checkpoint', 'cp'], ['airport', 'ap'], ['station', 'st']].forEach(function (p) {
      $('#tab-' + p[0]).classList.toggle('hidden', p[0] !== name); $('#' + p[1] + '-recent').classList.toggle('hidden', p[0] !== name);
    });
    try { history.replaceState(null, '', '#' + name); } catch (e) {}
    var unit = $({ checkpoint: '#cp-unit', airport: '#ap-unit', station: '#st-unit' }[name]).value;
    if (unit) { session.unit = unit; sessionStorage.setItem('sentinel.unit', unit); }
  }

  function init() {
    var lbl = { residence: 'Current address' }, glbl = { residence: 'Permanent address', phone: 'Contact number' };
    $('#t-fields').innerHTML = '<div class="grid2">' + U.fieldsBlock('t', ID_ROW, true) + '</div>' +
      '<div id="t-matchlist" class="m-matchlist"></div><div id="t-match" class="match-banner" role="status" aria-live="polite"></div>' +
      '<div class="grid2" style="margin-top:12px">' + U.fieldsBlock('t', ['mother_name', 'residence', 'phone', 'occupation'], true, lbl) + '</div>';
    $('#g-fields').innerHTML = '<div class="grid2">' + U.fieldsBlock('g', ['first_name', 'second_name', 'third_name', 'fourth_name'], true) +
      U.fieldsBlock('g', ['national_id', 'passport_id', 'phone', 'residence', 'occupation'], false, glbl) + '</div>' +
      '<div id="g-matchlist" class="m-matchlist"></div><div id="g-match" class="match-banner" role="status" aria-live="polite"></div>';
    $('#a-fields').innerHTML = '<div class="grid2">' + U.fieldsBlock('a', ID_ROW, true) + '</div>' +
      '<div id="a-matchlist" class="m-matchlist"></div><div id="a-match" class="match-banner" role="status" aria-live="polite"></div>';

    forms.t = new U.IdentityForm('t', ID_ROW.concat(['mother_name', 'residence', 'phone', 'occupation']), {});
    forms.g = new U.IdentityForm('g', ['first_name', 'second_name', 'third_name', 'fourth_name', 'national_id', 'passport_id', 'phone', 'residence', 'occupation'], {});
    forms.a = new U.IdentityForm('a', ID_ROW, {});

    document.querySelectorAll('.tabs button').forEach(function (b) { b.addEventListener('click', function () { showTab(b.dataset.tab); }); });
    $('#user').addEventListener('change', function (e) {
      session.user = e.target.value; session.unit = ''; sessionStorage.setItem('sentinel.user', session.user); sessionStorage.removeItem('sentinel.unit');
      resetCheckpoint(); resetAirport(); resetIncident(); loadSession();
    });
    ['#cp-unit', '#ap-unit', '#st-unit'].forEach(function (s) { $(s).addEventListener('change', function (e) { session.unit = e.target.value; sessionStorage.setItem('sentinel.unit', session.unit); }); });
    $('#cp-save').addEventListener('click', saveCheckpoint); $('#cp-new').addEventListener('click', resetCheckpoint);
    $('#ap-save').addEventListener('click', saveAirport); $('#ap-new').addEventListener('click', resetAirport);
    $('#st-save').addEventListener('click', saveIncident); $('#st-new').addEventListener('click', resetIncident);
    $('#ap-movement').addEventListener('change', syncMovement);
    $('#st-anon').addEventListener('change', onAnon);
    $('#st-vnid').addEventListener('input', function () { clearTimeout(victimTimer); victimTimer = setTimeout(checkVictim, 300); });
    $('#ap-date').value = new Date().toISOString().slice(0, 10); syncMovement();
    var tab = (location.hash || '').replace('#', ''); if (['checkpoint', 'airport', 'station'].indexOf(tab) >= 0) showTab(tab);
    loadUsers().then(loadSession);
  }

  window.SentinelOps = { init: init, forms: forms, showTab: showTab, loadSession: loadSession, reset: { cp: resetCheckpoint, ap: resetAirport, st: resetIncident } };
  document.addEventListener('DOMContentLoaded', init);
})();
