/* Sentinel — identity intake: pure decision logic (no DOM, no network).
 * Works in the browser (window.SentinelIdentity) and in Node (require) so it can be unit-tested.
 *
 * Ported from the legacy index.html: setMatch() -> bannerModel(), fillIdentity() -> formPlan(),
 * missingProfileFields() -> res.person.missing_fields.  The key change: what is LOCKED now comes
 * from the server's per-field state for THIS user (locked | fillable | editable) instead of the
 * legacy "any non-empty value is read-only" guess, so the UI can never disagree with the backend.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SentinelIdentity = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var FIELDS = ['first_name', 'second_name', 'third_name', 'fourth_name', 'date_of_birth', 'place_of_birth',
    'national_id', 'passport_id', 'mother_name', 'phone', 'residence', 'occupation'];
  var CORE_CLASSES = { core: 1, identifier: 1 };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function clean(v) { return String(v == null ? '' : v).replace(/\s+/g, ' ').trim(); }
  function same(field, a, b) {
    a = clean(a); b = clean(b);
    if (field === 'national_id' || field === 'passport_id') return a.toUpperCase() === b.toUpperCase();
    return a === b;
  }
  function labelOf(field) {
    return { first_name: 'First name', second_name: 'Second name', third_name: 'Third name', fourth_name: 'Fourth name',
      date_of_birth: 'Date of birth', place_of_birth: 'Place of birth', national_id: 'National ID',
      passport_id: 'Passport ID', mother_name: "Mother's name", phone: 'Phone', residence: 'Address',
      occupation: 'Occupation', photo_path: 'Photo', guardian: 'Guardian' }[field] || field;
  }

  /* What the notification banner should say for a search result. */
  function bannerModel(res, opts) {
    opts = opts || {};
    if (!res) return null;
    if (res.error) return { kind: 'warn', title: 'Lookup unavailable', lines: [res.message || res.error] };
    var p = res.person, lines = [], chips = [], extra = [];
    if (res.status === 'exists' && p) {
      lines.push(res.reason + ' (' + (res.tier_label || '') + ')');
      if (p.registered_at) lines.push('First registered at ' + p.registered_at.name + '.');
      lines.push('The existing master record was loaded. Locked identity fields cannot be changed here.');
      if (res.has_active_alert === true) chips.push({ kind: 'danger', text: 'Active alert — follow the alert procedure' });
      var miss = (p.missing_fields || []).map(function (m) { return m.label; });
      if (miss.length) extra.push({ kind: 'incomplete',
        text: 'Profile incomplete: ' + miss.join(', ') + ' — fill them in to enrich this record.' });
      (res.core_differences || []).forEach(function (d) {
        extra.push({ kind: 'diff', field: d.field,
          text: labelOf(d.field) + ' entered as "' + d.entered + '" but the registry has "' + d.stored + '". The registry value is kept.' });
      });
      (res.conflicts || []).forEach(function (c) { extra.push({ kind: 'conflict', text: c.message }); });
      return { kind: 'ok', icon: '✓', title: 'Person already exists in registry',
        headline: p.person_ref + ' · ' + p.full_name, lines: lines, chips: chips, extra: extra, person: p };
    }
    if (res.status === 'confirm' && p) {
      (res.conflicts || []).forEach(function (c) { extra.push({ kind: 'conflict', text: c.message }); });
      return { kind: 'warn', icon: '⚠', title: 'Possible duplicate — confirm before creating a new record',
        headline: p.person_ref + ' · ' + p.full_name,
        lines: [res.reason, 'This is a warning, not an automatic match. Pick the record below if it is the same person.'],
        chips: chips, extra: extra, person: p };
    }
    if (res.status === 'suggestions') {
      return { kind: 'info', icon: 'ℹ', title: 'Possible matches in the registry',
        lines: [res.reason], chips: chips, extra: extra };
    }
    if (res.status === 'new' && res.candidates && !res.candidates.length && res.reason && /^No existing/.test(res.reason)) {
      return { kind: 'info', icon: '＋', title: 'No existing record', lines: ['A new person record will be created on save.'], chips: chips, extra: extra };
    }
    return null;
  }

  /* Per-field UI plan from the server's field states. */
  function formPlan(person, opts) {
    opts = opts || {};
    var plan = {};
    FIELDS.forEach(function (f) {
      var st = person && person.field_states && person.field_states[f];
      var stored = person ? person[f] : null;
      var hasValue = clean(stored) !== '';
      var state = st ? st.state : 'fillable';
      plan[f] = {
        value: hasValue ? String(stored) : '',
        state: state,
        mutability: st ? st.mutability : null,
        readonly: state === 'locked',
        // locked-with-a-value is the interesting case: show the padlock and the reason
        padlock: state === 'locked' && hasValue,
        note: state === 'locked' && hasValue
          ? 'Locked after registration. Only the National Admin can correct this.'
          : (state === 'editable' && hasValue && st && CORE_CLASSES[st.mutability]
              ? 'National Admin: a change needs a reason and is audited.' : ''),
      };
    });
    return plan;
  }

  /* Changed fields the user is actually allowed to send (never locked ones). */
  function diffForPatch(person, values) {
    var changes = {}, coreChanged = [], blocked = [];
    FIELDS.forEach(function (f) {
      var entered = clean(values[f]);
      var stored = person ? person[f] : '';
      // A blank box means "not provided", never "erase" (same rule as the legacy enrich): the form
      // cannot wipe a stored value by accident.  Clearing is an explicit API call only.
      if (entered === '' || same(f, entered, stored)) return;
      var st = person && person.field_states && person.field_states[f];
      var hasValue = clean(stored) !== '';
      var allowed = st && (hasValue ? st.state === 'editable' : st.state !== 'locked');
      if (!allowed) { blocked.push(f); return; }
      changes[f] = entered;
      if (hasValue && st && CORE_CLASSES[st.mutability]) coreChanged.push(f);
    });
    return { changes: changes, coreChanged: coreChanged, blocked: blocked };
  }

  function personPayload(values, extra) {
    var out = {};
    FIELDS.forEach(function (f) { if (clean(values[f]) !== '') out[f] = clean(values[f]); });
    return Object.assign({ person: out }, extra || {});
  }

  /* Client-side pre-checks mirroring the server (the server stays the authority). */
  function validateNew(values, opts) {
    opts = opts || {};
    var problems = [];
    [['first_name', 'First name'], ['second_name', 'Second name'], ['third_name', 'Third name']].forEach(function (p) {
      if (!clean(values[p[0]])) problems.push({ field: p[0], message: p[1] + ' is required' });
    });
    if (opts.requireDob !== false && !clean(values.date_of_birth)) problems.push({ field: 'date_of_birth', message: 'Date of birth is required' });
    if (!opts.allowNoId && !clean(values.national_id) && !clean(values.passport_id))
      problems.push({ field: 'national_id', message: 'National ID or Passport ID is required' });
    return problems;
  }

  /* Human summary of a register/PATCH response. */
  function resultSummary(res) {
    var bits = [];
    if (res.created) bits.push('New person registered: ' + res.person.person_ref + '.');
    else if (res.exists) bits.push('Linked to the existing record ' + res.person.person_ref + ' — no duplicate was created.');
    else bits.push('Saved ' + res.person.person_ref + '.');
    if (res.filled && res.filled.length) bits.push('Added: ' + res.filled.map(labelOf).join(', ') + '.');
    if (res.updated && res.updated.length) bits.push('Updated: ' + res.updated.map(labelOf).join(', ') + '.');
    if (res.ignored && res.ignored.length)
      bits.push('Not changed (locked): ' + res.ignored.map(function (i) { return labelOf(i.field); }).join(', ') + '.');
    return bits.join(' ');
  }

  return { FIELDS: FIELDS, esc: esc, clean: clean, same: same, labelOf: labelOf, bannerModel: bannerModel,
    formPlan: formPlan, diffForPatch: diffForPatch, personPayload: personPayload, validateNew: validateNew,
    resultSummary: resultSummary };
});
