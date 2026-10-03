/* Sentinel — Central Person Registry UI: search box, intake form, "already exists" banner,
 * field locks and guardian enrichment.  Ported from the legacy index.html (wireIdentity /
 * setMatch / renderMatchList / fillIdentity), now driven by the unified API.
 * Depends on identity-core.js (window.SentinelIdentity).  No framework, no build step.
 */
(function () {
  'use strict';
  var I = window.SentinelIdentity;
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var esc = I.esc;

  // ---------------------------------------------------------------- session + api
  var session = { user: sessionStorage.getItem('sentinel.user') || '', unit: sessionStorage.getItem('sentinel.unit') || '', me: null };

  function api(method, path, body) {
    var headers = { 'Content-Type': 'application/json' };
    if (session.user) headers['X-Dev-User'] = session.user;
    if (session.unit) headers['X-Unit'] = session.unit;
    return fetch(path, { method: method, headers: headers, body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }); });
  }

  // ---------------------------------------------------------------- identity form (person + guardian)
  var LABELS = { first_name: 'First name', second_name: 'Second name', third_name: 'Third name', fourth_name: 'Fourth name',
    date_of_birth: 'Date of birth', place_of_birth: 'Place of birth', national_id: 'National ID', passport_id: 'Passport ID',
    mother_name: "Mother's name", phone: 'Phone', residence: 'Address (residence)', occupation: 'Occupation' };
  var PLACEHOLDER = { first_name: 'e.g. Ayaan', second_name: 'e.g. Cabdi', third_name: 'e.g. Xasan', fourth_name: 'e.g. Axmed',
    national_id: 'National ID number', passport_id: 'Passport number', mother_name: "Mother's full name",
    phone: '+252 …', residence: 'Street, district, town', place_of_birth: 'City / town', occupation: 'Occupation' };
  var REQUIRED = { first_name: 1, second_name: 1, third_name: 1 };

  function fieldHTML(prefix, f, required, label) {
    var type = f === 'date_of_birth' ? 'date' : 'text';
    return '<div class="field" id="' + prefix + '-' + f + '-wrap"><label for="' + prefix + '-' + f + '">' + esc(label || LABELS[f]) +
      (required ? ' *' : '') + '</label><input id="' + prefix + '-' + f + '" type="' + type + '" autocomplete="off" placeholder="' +
      esc(PLACEHOLDER[f] || '') + '"><div class="hint-note" id="' + prefix + '-' + f + '-note"></div></div>';
  }

  /** One identity form: wires live matching, banner, match list and lock rendering. */
  function IdentityForm(prefix, fields, opts) {
    this.prefix = prefix; this.fields = fields; this.opts = opts || {};
    this.person = null;           // the selected existing master record (null = registering a new one)
    this.confirmNew = false;      // officer chose "it's a different person"
    this.seq = 0; this.timer = null; this.lastSnapshot = '';
    this.el = function (f) { return document.getElementById(prefix + '-' + f); };
    var self = this;
    fields.forEach(function (f) {
      var el = self.el(f);
      if (el) el.addEventListener('input', function () { self.onInput(f); });
    });
  }
  var P = IdentityForm.prototype;

  P.values = function () {
    var v = {}, self = this;
    this.fields.forEach(function (f) { var el = self.el(f); v[f] = el ? el.value : ''; });
    return v;
  };
  P.matchKey = function () {      // the fields that identify a person (what the legacy engine matched on)
    var v = this.values(), keys = ['first_name', 'second_name', 'third_name', 'fourth_name', 'date_of_birth', 'national_id', 'passport_id', 'mother_name'];
    return JSON.stringify(keys.map(function (k) { return I.clean(v[k]); }));
  };
  P.onInput = function () {
    var self = this;
    if (this.person) return;                       // a record is selected: edits are updates, not a new search
    // NB: an officer's "it is a different person" decision is kept while they keep typing; it only
    // silences the SOFT prompts (similar name).  A hard match (same ID / name+DoB) still auto-selects.
    clearTimeout(this.timer);
    this.timer = setTimeout(function () { self.run(); }, 220);
  };

  P.run = function () {
    var self = this, my = ++this.seq, snap = this.matchKey(), v = this.values();
    var has = this.fields.some(function (f) { return I.clean(v[f]) !== '' && !{ phone: 1, residence: 1, occupation: 1, place_of_birth: 1 }[f]; });
    if (!has) { this.showMatches(null); this.showBanner(null); return Promise.resolve(); }
    return api('POST', '/api/persons/search', { query: I.personPayload(v).person }).then(function (r) {
      if (my !== self.seq) return;                                   // a newer search is running: drop this one
      if (self.matchKey() !== snap) return;                          // officer kept typing while we waited
      if (r.status !== 200) { self.showBanner(I.bannerModel({ error: r.data.error, message: r.data.message })); return; }
      self.handleResult(r.data);
    }).catch(function (e) { if (my === self.seq) self.showBanner(I.bannerModel({ error: 'network', message: String(e) })); });
  };

  P.handleResult = function (res) {
    if (res.status === 'exists' && res.auto_select) {            // Tier 1/2: auto-select + "already exists" banner
      this.select(res.person, res);
    } else if (this.confirmNew && (res.status === 'confirm' || res.status === 'suggestions')) {
      return;                                                    // already decided: new person, no re-prompt
    } else if (res.status === 'confirm' || res.status === 'suggestions') {
      this.showBanner(I.bannerModel(res));
      this.showMatches(res.candidates, res);
    } else {
      this.showMatches(null);
      this.showBanner(I.bannerModel(res));
    }
  };

  /** Select an existing master record: fill the form and lock what the server says is locked. */
  P.select = function (person, res) {
    this.person = person; this.confirmNew = false;
    var typed = this.values();
    res = res || { status: 'exists', reason: 'Selected from the matching list', tier_label: '', person: person };
    if (!res.core_differences) {                                  // computed locally when picked from the list
      res.core_differences = I.FIELDS.filter(function (f) {
        var st = person.field_states && person.field_states[f];
        return st && st.state === 'locked' && I.clean(typed[f]) && I.clean(person[f]) && !I.same(f, typed[f], person[f]);
      }).map(function (f) { return { field: f, stored: person[f], entered: typed[f] }; });
    }
    this.render(person, typed);
    this.showMatches(null);
    this.showBanner(I.bannerModel(Object.assign({ status: 'exists' }, res, { person: person })));
    if (this.opts.onSelect) this.opts.onSelect(person);
  };

  P.render = function (person, typed) {
    var plan = I.formPlan(person), self = this;
    this.fields.forEach(function (f) {
      var el = self.el(f), wrap = document.getElementById(self.prefix + '-' + f + '-wrap'),
        note = document.getElementById(self.prefix + '-' + f + '-note');
      if (!el || !plan[f]) return;
      var p = plan[f], t = typed && typed[f] ? String(typed[f]) : '';
      if (p.readonly) el.value = p.value;                         // locked: the registry value always wins
      else if (!(t && !I.same(f, t, p.value))) el.value = p.value || t;   // editable: keep what the officer typed if it differs
      el.readOnly = p.readonly;
      el.classList.toggle('locked', p.readonly);
      el.setAttribute('aria-readonly', p.readonly ? 'true' : 'false');
      el.title = p.padlock ? p.note : '';
      if (wrap) { wrap.classList.toggle('is-locked', p.padlock); wrap.classList.toggle('has-note', !!p.note); }
      if (note) note.textContent = p.note;
    });
  };

  /** Back to a blank, fully editable form. */
  P.clear = function () {
    var self = this;
    this.person = null; this.confirmNew = false; this.seq++;
    this.fields.forEach(function (f) {
      var el = self.el(f), wrap = document.getElementById(self.prefix + '-' + f + '-wrap');
      if (!el) return;
      el.value = ''; el.readOnly = false; el.classList.remove('locked'); el.title = '';
      if (wrap) wrap.classList.remove('is-locked', 'has-note', 'invalid');
    });
    this.showMatches(null); this.showBanner(null);
    if (this.opts.onClear) this.opts.onClear();
  };

  /** "It is a different person": unlock for a NEW record, remembering the officer's decision. */
  P.createAsNew = function () {
    this.confirmNew = true; this.person = null; this.seq++;
    var typed = this.values();
    this.clearLocksKeepValues(typed);
    this.showMatches(null);
    this.showBanner({ kind: 'info', icon: '＋', title: 'Creating a new person', lines: ['You confirmed this is a different person. A new record will be created on save.'] });
  };
  P.clearLocksKeepValues = function (typed) {
    var self = this;
    this.fields.forEach(function (f) {
      var el = self.el(f), wrap = document.getElementById(self.prefix + '-' + f + '-wrap');
      if (!el) return;
      el.value = typed[f] || ''; el.readOnly = false; el.classList.remove('locked'); el.title = '';
      if (wrap) wrap.classList.remove('is-locked', 'has-note');
    });
  };

  P.markInvalid = function (list) {
    var self = this;
    this.fields.forEach(function (f) { var w = document.getElementById(self.prefix + '-' + f + '-wrap'); if (w) w.classList.remove('invalid'); });
    (list || []).forEach(function (p) {
      var w = document.getElementById(self.prefix + '-' + (p.field || p) + '-wrap'); if (w) w.classList.add('invalid');
    });
  };

  // ---- banner + match list (ported markup) ----
  P.showBanner = function (m) {
    var box = document.getElementById(this.prefix + '-match');
    if (!box) return;
    if (!m) { box.className = 'match-banner'; box.innerHTML = ''; return; }
    var html = '<div class="m-bannerrow"><span class="m-icon" aria-hidden="true">' + esc(m.icon || '') + '</span><div>' +
      '<b>' + (m.kind === 'ok' ? '✓ ' : '') + esc(m.title) + (m.headline ? ' — ' + esc(m.headline) : '') + '</b>' +
      (m.lines || []).map(function (l) { return '<small>' + esc(l) + '</small>'; }).join('') +
      (m.chips || []).map(function (c) { return '<span class="m-chip ' + esc(c.kind) + '">' + esc(c.text) + '</span>'; }).join('') +
      (m.extra || []).map(function (x) { return '<span class="m-note ' + esc(x.kind) + '">' + esc(x.text) + '</span>'; }).join('') +
      '</div></div>';
    box.className = 'match-banner show ' + (m.kind || 'info');
    box.innerHTML = html;
  };

  P.showMatches = function (items, res) {
    var box = document.getElementById(this.prefix + '-matchlist'), self = this;
    if (!box) return;
    this.items = items || [];
    if (!items || !items.length) { box.className = 'm-matchlist'; box.innerHTML = ''; return; }
    box.className = 'm-matchlist show';
    box.innerHTML = '<div class="m-label">Matching people in the registry — pick one to link</div>' +
      items.map(function (p, i) {
        var initials = (p.full_name || '?').split(' ').slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase();
        return '<button type="button" class="m-item" data-i="' + i + '"><span class="mini">' + esc(initials) + '</span>' +
          '<span class="m-body"><b>' + esc(p.full_name) + '</b><small>' + esc(p.national_id || p.passport_id || 'No ID') +
          ' · DOB ' + esc(p.date_of_birth || '—') + (p.registered_at ? ' · ' + esc(p.registered_at.name) : '') + '</small></span>' +
          '<span class="m-tier">Tier ' + esc(p.tier) + '</span><span class="m-id">' + esc(p.person_ref) + '</span></button>';
      }).join('') + '<button type="button" class="m-item m-new" data-new="1">＋ It is a different person — create a new record</button>';
    box.onclick = function (e) {
      var b = e.target.closest('.m-item'); if (!b) return;
      if (b.dataset.new) self.createAsNew(); else self.select(self.items[Number(b.dataset.i)]);
    };
  };

  // ---------------------------------------------------------------- page wiring
  var main, guardian, found = null;

  function fieldsBlock(prefix, list, required, labels) {
    return list.map(function (f) { return fieldHTML(prefix, f, required && REQUIRED[f], labels && labels[f]); }).join('');
  }

  function setResult(id, cls, text) {
    var r = document.getElementById(id);
    r.className = 'result show ' + cls; r.textContent = text;
  }
  function clearResult(id) { var r = document.getElementById(id); r.className = 'result'; r.textContent = ''; }

  function buildForms() {
    $('#p-fields').innerHTML = '<div class="grid2">' +
      fieldsBlock('p', ['first_name', 'second_name', 'third_name', 'fourth_name', 'date_of_birth', 'place_of_birth', 'national_id', 'passport_id'], true) +
      '</div><div id="p-matchlist" class="m-matchlist"></div><div id="p-match" class="match-banner" role="status" aria-live="polite"></div>' +
      '<div class="grid2" style="margin-top:12px">' + fieldsBlock('p', ['mother_name', 'residence', 'phone', 'occupation'], true) + '</div>';
    $('#g-fields').innerHTML = '<div class="grid2">' +
      fieldsBlock('g', ['first_name', 'second_name', 'third_name', 'fourth_name'], true) +
      '<div class="field"><label for="g-relationship">Relationship</label><select id="g-relationship"><option value="">— select —</option>' +
      '<option>Parent</option><option>Spouse</option><option>Legal Guardian</option><option>Sibling</option><option>Relative</option><option>Employer</option><option>Other</option></select></div>' +
      fieldsBlock('g', ['national_id', 'passport_id', 'phone', 'residence', 'occupation'], false) +
      '</div><div id="g-matchlist" class="m-matchlist"></div><div id="g-match" class="match-banner" role="status" aria-live="polite"></div>';

    main = new IdentityForm('p', ['first_name', 'second_name', 'third_name', 'fourth_name', 'date_of_birth', 'place_of_birth',
      'national_id', 'passport_id', 'mother_name', 'residence', 'phone', 'occupation'], {
      onSelect: function (p) { onPersonSelected(p); }, onClear: function () { onPersonCleared(); } });
    guardian = new IdentityForm('g', ['first_name', 'second_name', 'third_name', 'fourth_name', 'national_id', 'passport_id',
      'phone', 'residence', 'occupation'], {});
  }

  function onPersonSelected(p) {
    $('#save-btn').textContent = 'Save updates to ' + p.person_ref;
    $('#clear-btn').classList.remove('hidden');
    $('#noid-line').classList.add('hidden');
    $('#guardian-panel').classList.remove('hidden');
    var minor = p.age != null && p.age < 18;
    var needs = (p.missing_fields || []).some(function (m) { return m.field === 'guardian'; });
    $('#g-hint').innerHTML = minor
      ? '<b>' + esc(p.full_name) + '</b> is ' + esc(p.age) + ' years old' + (needs ? ' and has <b>no guardian on record</b> — add the guardian now.' : '. Guardians on record are listed below; you can add another.')
      : 'Add a guardian or next of kin for <b>' + esc(p.full_name) + '</b> (optional).';
    $('#g-list').innerHTML = (p.guardians || []).map(function (g) {
      return '<li><b>' + esc(g.full_name) + '</b> · ' + esc(g.relationship || 'relationship not recorded') + ' · ' + esc(g.guardian_ref) +
        (g.phone ? ' · ' + esc(g.phone) : '') + (g.occupation ? ' · ' + esc(g.occupation) : '') + '</li>';
    }).join('') || '<li class="sub">No guardian recorded yet.</li>';
    $('#p-title').textContent = p.person_ref + ' · ' + p.full_name;
    guardian.clear();
  }
  function onPersonCleared() {
    $('#save-btn').textContent = 'Register person';
    $('#clear-btn').classList.add('hidden');
    $('#noid-line').classList.remove('hidden');
    $('#guardian-panel').classList.add('hidden');
    $('#reason-row').classList.add('hidden');
    $('#p-title').textContent = 'Person intake';
    clearResult('p-result');
  }

  function save() {
    clearResult('p-result'); main.markInvalid([]);
    var v = main.values();
    if (main.person) return savePatch(v);
    var allowNoId = $('#noid').checked;
    var problems = I.validateNew(v, { allowNoId: allowNoId });
    if (problems.length) { main.markInvalid(problems); return setResult('p-result', 'bad', problems.map(function (p) { return p.message; }).join(' · ')); }
    return api('POST', '/api/persons', I.personPayload(v, { allow_no_id: allowNoId, confirm_new: main.confirmNew })).then(function (r) {
      var d = r.data;
      if (r.status === 200 || r.status === 201) {
        main.select(d.person, { status: 'exists', reason: d.created ? 'Registered just now.' : d.match.reason, tier_label: '',
          person: d.person, core_differences: (d.ignored || []).map(function (i) { return { field: i.field, stored: i.stored, entered: i.entered }; }) });
        setResult('p-result', 'good', I.resultSummary(d));
      } else if (r.status === 409 && d.error === 'possible_duplicate') {
        main.handleResult(d.search);
        setResult('p-result', 'bad', d.message);
      } else if (r.status === 422) {
        main.markInvalid((d.fields || []).map(function (f) { return f.field ? f : { field: f }; }));
        setResult('p-result', 'bad', ((d.fields || []).map(function (f) { return f.message; }).filter(Boolean).join(' · ')) || d.message);
      } else setResult('p-result', 'bad', d.message || 'Request failed');
    });
  }

  function savePatch(v) {
    var diff = I.diffForPatch(main.person, v);
    if (!Object.keys(diff.changes).length) return setResult('p-result', 'good', 'Nothing to update — the form matches the registry.');
    var reason = $('#reason').value.trim();
    if (diff.coreChanged.length) {
      $('#reason-row').classList.remove('hidden');
      if (!reason) { $('#reason').focus(); return setResult('p-result', 'bad', 'Enter the reason for correcting ' + diff.coreChanged.map(I.labelOf).join(', ') + '.'); }
    }
    return api('PATCH', '/api/persons/' + main.person.person_ref, { changes: diff.changes, reason: reason || undefined }).then(function (r) {
      var d = r.data;
      if (r.status === 200) {
        main.select(d.person, { status: 'exists', reason: 'Profile updated.', tier_label: '', person: d.person, core_differences: [] });
        $('#reason').value = ''; $('#reason-row').classList.add('hidden');
        setResult('p-result', 'good', I.resultSummary({ person: d.person, filled: d.filled, updated: d.updated }));
      } else if (r.status === 403 && d.error === 'field_locked') {
        setResult('p-result', 'bad', (d.fields || []).map(function (f) { return f.reason || f.field; }).join(' '));
      } else setResult('p-result', 'bad', d.message || 'Request failed');
    });
  }

  function saveGuardian() {
    clearResult('g-result'); guardian.markInvalid([]);
    var v = guardian.values();
    var picked = guardian.person;
    var problems = picked ? [] : I.validateNew(v, { requireDob: false, allowNoId: true });
    if (problems.length) { guardian.markInvalid(problems); return setResult('g-result', 'bad', problems.map(function (p) { return p.message; }).join(' · ')); }
    var body = { guardian: I.personPayload(v).person, relationship: $('#g-relationship').value || undefined,
      guardian_person_ref: picked ? picked.person_ref : undefined, confirm_new: guardian.confirmNew };
    return api('POST', '/api/persons/' + main.person.person_ref + '/guardians', body).then(function (r) {
      var d = r.data;
      if (r.status === 200 || r.status === 201) {
        main.person = d.person; onPersonSelected(d.person); main.render(d.person, main.values());
        setResult('g-result', 'good', (d.link_created ? 'Guardian added: ' : 'Guardian already linked: ') + d.guardian.full_name + ' (' + d.guardian.person_ref + ').' +
          (d.guardian_filled && d.guardian_filled.length ? ' Added: ' + d.guardian_filled.map(I.labelOf).join(', ') + '.' : ''));
      } else if (r.status === 409 && d.error === 'possible_duplicate') {
        guardian.handleResult(d.search); setResult('g-result', 'bad', d.message);
      } else if (r.status === 422) {
        guardian.markInvalid((d.fields || []).map(function (f) { return f.field ? f : { field: f }; }));
        setResult('g-result', 'bad', d.message);
      } else setResult('g-result', 'bad', d.message || 'Request failed');
    });
  }

  // ---------------------------------------------------------------- central search box
  var qTimer = null, qSeq = 0;
  function runSearchBox() {
    var q = $('#q').value.trim(), my = ++qSeq;
    var out = $('#q-out');
    if (!q) { out.innerHTML = ''; return; }
    api('GET', '/api/persons/search?q=' + encodeURIComponent(q) + '&limit=10').then(function (r) {
      if (my !== qSeq) return;
      if (r.status !== 200) { out.innerHTML = '<div class="result show bad">' + esc(r.data.message || 'Search failed') + '</div>'; return; }
      var rows = r.data.candidates;
      if (!rows.length) { out.innerHTML = '<div class="hint" style="margin-top:12px">No one in the registry matches “' + esc(q) + '”.</div>'; found = null; return; }
      found = rows;
      out.innerHTML = '<table class="res"><thead><tr><th>Person</th><th>ID / Passport</th><th>Date of birth</th><th>Registered at</th><th>Match</th></tr></thead><tbody>' +
        rows.map(function (p, i) {
          return '<tr class="pick" tabindex="0" data-i="' + i + '"><td><b>' + esc(p.full_name) + '</b><br><small>' + esc(p.person_ref) + '</small></td><td>' +
            esc(p.national_id || p.passport_id || '—') + '</td><td>' + esc(p.date_of_birth || '—') + '</td><td>' +
            esc(p.registered_at ? p.registered_at.name : '—') + '</td><td><span class="badge ok">Tier ' + esc(p.tier) + '</span></td></tr>';
        }).join('') + '</tbody></table>' + (r.data.has_active_alert === true ? '<div class="m-chip danger">Active alert on the top match</div>' : '');
    });
  }
  function openFromSearch(i) {
    var p = found && found[i]; if (!p) return;
    main.clear();
    main.select(p, { status: 'exists', reason: 'Opened from Central Person Search', tier_label: '', person: p, core_differences: [] });
    $('#intake-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ---------------------------------------------------------------- session bar
  function loadMe() {
    session.me = null;
    if (!session.user) return Promise.resolve();
    return api('GET', '/api/me').then(function (r) {
      if (r.status !== 200) { $('#who').textContent = r.data.message || 'Sign-in failed'; return; }
      session.me = r.data;
      var a = r.data.abilities;
      $('#who').textContent = r.data.user.display_name + (a.is_national_admin ? ' · National Admin' : '') +
        (!a.can_register ? ' · read-only' : '');
      var sel = $('#unit');
      sel.innerHTML = '<option value="">— no unit —</option>' + r.data.units.map(function (u) {
        return '<option value="' + esc(u.code) + '">' + esc(u.name) + ' (' + esc(u.code) + ')</option>'; }).join('');
      var pref = r.data.units.find(function (u) { return u.code === session.unit; }) || r.data.units.filter(function (u) { return /airport|checkpoint|directorate/.test(u.unit_type); })[0];
      session.unit = pref ? pref.code : ''; sel.value = session.unit; sessionStorage.setItem('sentinel.unit', session.unit);
      $('#save-btn').disabled = !a.can_register && !a.can_update_dynamic;
    });
  }
  function loadUsers() {
    return fetch('/api/dev/users').then(function (r) { return r.ok ? r.json() : { users: [] }; }).then(function (d) {
      var sel = $('#user');
      if (!d.users.length) { sel.innerHTML = '<option value="">(sign-in not configured)</option>'; return; }
      sel.innerHTML = '<option value="">— choose a user —</option>' + d.users.map(function (u) {
        return '<option value="' + esc(u.username) + '">' + esc(u.display_name) + ' — ' + esc(u.roles || 'no role') + '</option>'; }).join('');
      sel.value = session.user;
    });
  }

  function init() {
    if (!document.getElementById('p-fields')) return;      // other pages (operations.html) reuse the pieces below
    buildForms();
    loadUsers().then(loadMe);
    $('#user').addEventListener('change', function (e) {
      session.user = e.target.value; session.unit = ''; sessionStorage.setItem('sentinel.user', session.user); sessionStorage.removeItem('sentinel.unit');
      main.clear(); guardian.clear(); $('#q-out').innerHTML = ''; loadMe();
    });
    $('#unit').addEventListener('change', function (e) { session.unit = e.target.value; sessionStorage.setItem('sentinel.unit', session.unit); });
    $('#q').addEventListener('input', function () { clearTimeout(qTimer); qTimer = setTimeout(runSearchBox, 250); });
    $('#q-out').addEventListener('click', function (e) { var tr = e.target.closest('tr.pick'); if (tr) openFromSearch(Number(tr.dataset.i)); });
    $('#q-out').addEventListener('keydown', function (e) { if (e.key === 'Enter') { var tr = e.target.closest('tr.pick'); if (tr) openFromSearch(Number(tr.dataset.i)); } });
    $('#save-btn').addEventListener('click', save);
    $('#clear-btn').addEventListener('click', function () { main.clear(); });
    $('#new-btn').addEventListener('click', function () { main.clear(); });
    $('#g-save-btn').addEventListener('click', saveGuardian);
  }

  window.SentinelUI = { init: init, main: function () { return main; }, guardian: function () { return guardian; }, session: session,
    // shared with web/operations.js
    IdentityForm: IdentityForm, api: api, fieldsBlock: fieldsBlock, setResult: setResult, clearResult: clearResult };
  document.addEventListener('DOMContentLoaded', init);
})();
