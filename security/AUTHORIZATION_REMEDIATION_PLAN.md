> ## ✅ GATING DECISIONS RECORDED — 9 November 2026
>
> All eight owner decisions are approved (`DECISION_REGISTER.md` §1A). **D-3 = Option A** fixes
> SEC-0 at the three-state model, which unblocks **SEC-0 → SEC-2 → SEC-3 → SEC-4 → M-02-A →
> SEC-1 → SEC-5**. **D-5** makes **SS-1 mandatory**. **D-4b** re-scopes **A-13 to 4–6.25 d**.
>
> **The authoritative costings and sequencing are now
> `security/SECURITY_REMEDIATION_PROGRAMME.md` §3 and §4** (total **40–63.75 d**, derived from
> work items W-01…W-78). The package analysis and the 46 tests below remain valid and are
> unchanged; only the totals and the A-13/SS-1 scope moved.
>
> **SS-1 (§6) is no longer awaiting approval** — see the D-5 banner in
> `security/SS1_STATION_SAFEGUARD_OPTIONS.md`.
>
> **Implementation remains unauthorized.**

---

# Security Remediation Plan — Authorization (revised)

**Date:** 5 November 2026 (date conflict unresolved — `RELEASE_1_0_REFERENCE_DATA.md` §5)
**Commit:** `8ea2f9b` · **Status:** **PLAN — NOTHING IMPLEMENTED — AWAITING APPROVAL**
**Revision 3.** Supersedes revisions 1 and 2.
**What changed in revision 3** (your second review): S-16b is now **proven by execution on all four
linked registers** rather than inferred — see `S16_REGISTER_VERIFICATION.md`; suspect-alert ownership
has an architecture and a schema answer — see `SUSPECT_ALERT_OWNERSHIP.md`; the M-01 report-only
proposal is flagged prohibited; SS-1's three options are set out in full in
`SS1_STATION_SAFEGUARD_OPTIONS.md`; and a consolidated endpoint inventory is in
`ENDPOINT_AUTHORIZATION_INVENTORY.md`. **The dependency order changed as a result of the
measurements: SEC-1 is now the last package, not the first.** Totals moved 10–16 d → **11–17.5 d**.

**Revision 2 changes, retained:** S-16 promoted to its own critical package and
fully scoped; one consolidated authorization model (SEC-0); **report-only production phase removed**;
endpoint verification expanded to list / direct-ID / linked / read / write / update; shared identity
explicitly separated from protected unit records; SS-1 kept separate with G-b's operational impact
stated; estimates rebuilt with shared work counted once.

> No application code, schema, initialization or production configuration changed.
> `backend/server.py` is byte-identical to `e7263d7` (sha256 `a8211f4f…b3b9fc`).
> Suite: **28 PASS / 0 FAIL / 1 BLOCKED**.

---

## 1. The defect in one sentence

**Three different authorization dimensions — module, branch and checkpoint location — are each
resolved by a function that returns a falsy value for both "deliberately unrestricted" and "cannot
determine", and every call site reads that falsy value as "allow".**

S-14, S-16a, S-16b, H-2b and the checkpoint findings are **one defect class in several places**, which is why
§3 replaces them with a single model rather than patching ten call sites independently.

| Finding | Where | Severity | Precondition | Evidence |
|---|---|---|---|---|
| **S-16a** | `/api/persons/<id>` — no module, branch or location filter | **Critical** | **None** | **Executed — 4/4 registers** |
| **S-16b** | `/linked-records`, `/documents`, `/audit-history` — no branch filter | **High** | **None** | **Executed** (linked-records); documents/audit code-read |
| **S-14** | Branch scope, 12 enforcing call sites | **Critical** | A posting that does not resolve | Executed (P1–P5) |
| **S-15** | `/api/crimes` unit-type mismatch | **High** | None (fails closed when posting resolves) | **Executed — scenarios A–E** |
| **H-2b** | Checkpoint — branch never filtered, location fail-open | **High** | **None** | **Executed** (same-location/other-branch officer) |
| **S-04** | `suspect_alerts` — no branch column, no filter anywhere | **High** | **None** | **Executed** |
| **H-2b** | Checkpoint location scope | **High** | An empty `location_scope` |

---

## 2. S-16 — full scope (your point 1)

S-16 is **not** a checkpoint issue. It is a person-registry issue that happens to leak checkpoint
data along with everything else. It is now **package SEC-1**, sequenced first.

### 2.1 Every person endpoint and what it filters today

| # | Endpoint | Module | Branch | Checkpoint location | Verdict |
|---|---|---|---|---|---|
| **PE-1** | `GET /api/persons/<id>` | **✘ none** | **✘ none** | **✘ none** | **S-16a — Critical** |
| **PE-2** | `GET /api/persons/<id>/linked-records` | ✔ | **✘ none** | ✔ | **S-16b — branch missing** |
| **PE-3** | `GET /api/persons/<id>/documents` | ✔ | **✘ none** | ✔ | **S-16b** |
| **PE-4** | `GET /api/persons/<id>/audit-history` | ✔ | **✘ none** | ✔ | **S-16b** |
| **PE-5** | `GET /api/persons?q=` (search) | n/a — identity only | n/a | n/a | legitimate, see §2.3 |

**Verified:** `linked_person_records()`, `person_document_records()` and `person_audit_history()`
each begin `modules = user_module_set(user)`, gate each source with `if '<module>' in modules`, and
apply `checkpoint_scope_sql(checkpoint_scope(user), …)` to the checkpoint source. **None of the
three applies any branch filter** — they return `branch_id` and `branch_name` as display metadata
and never constrain on them.

So S-16 has two parts:

- **S-16a (Critical):** PE-1 applies **nothing**. Proven — a checkpoint officer refused the
  Fingerprint register with 401 received a clearance application from PE-1 with 200; a correctly
  posted Fingerprint officer whose direct fetch returned 403 received another branch's application
  from PE-1.
- **S-16b (High):** PE-2…PE-4 apply module and location but **not branch**. A correctly posted
  Fingerprint officer sees other branches' clearance records in all three.

### 2.2 Every linked unit register exposed through PE-1

| Array | Source table | Owning module | Branch column | Location column |
|---|---|---|---|---|
| `person['clearance']` | `clearance_applications` | `fingerprint` | `branch_id` | — |
| `person['airport']` | `airport_passengers` | `airport` | `branch_id` | — |
| `person['alerts']` | `suspect_alerts` | `cid` | **none** *(finding S-04)* | — |
| `person['checkpoints']` | `checkpoint_events` | `checkpoints` | `branch_id` | `location_code` |

`suspect_alerts` has no `branch_id` at all (S-04). Until S-04 is resolved it can be gated by module
only — and that gap must be **stated**, not papered over. Under the §3 model an attribute that
cannot be determined is **indeterminate → denied**, so alerts will be visible only to sessions
holding the `cid` module, and branch isolation for alerts arrives with S-04.

### 2.3 Shared identity versus protected unit records (your point 5)

**I am not proposing to block cross-module person identity access.** The `persons` table contains
**no unit data and no branch column** — it is pure identity. The boundary is therefore clean:

| Class | Fields | Rule |
|---|---|---|
| **Shared identity** — the `persons` row | `person_id`, `full_name`, the four name parts, `national_id`, `date_of_birth`, `phone`, `mother_name`, `place_of_birth`, `residence`, `occupation`, `passport_id`, `photo_path`, `created_at`, `updated_at` | **Remains available to any authenticated session, exactly as today.** No change |
| **Protected unit records** — the four attached arrays | `clearance`, `airport`, `alerts`, `checkpoints` | **Filtered by module + branch + location.** Omitted entirely when the caller has no right to the unit |

**Why identity must stay open to every authenticated role, including Checkpoint:** a checkpoint
officer does not hold the `people` module, yet `POST /api/checkpoint-events` calls
`ensure_person(...)` to create or merge the traveller's identity, and the checkpoint screen searches
the registry to do it. **Requiring the `people` module for identity would break checkpoint
operations.** The current behaviour is legitimate and is preserved.

**The fix returns the same person object with the unit arrays filtered — not a smaller person
object.** An empty `clearance: []` for a caller without the Fingerprint module is correct; a missing
`full_name` would be a regression, and **T-27 exists to catch exactly that.**

### 2.4 Behaviour after SEC-1

| Caller | Identity fields | `clearance` | `airport` | `alerts` | `checkpoints` |
|---|---|---|---|---|---|
| SystemAdmin | all | all | all | all | all |
| Chief Commander (read-only) | all | all | all | all | all |
| Fingerprint officer, branch A | all | **branch A only** | `[]` | `[]` | `[]` |
| CID officer, branch A | all | `[]` | `[]` | all *(S-04: no branch column)* | `[]` |
| Checkpoint officer, South | all | `[]` | `[]` | `[]` | **South only** |
| Officer with unresolved posting | all | **403** | **403** | **403** | **403** |

The last row is the §3 rule: an indeterminate authorization attribute denies the **request**, not
just the array — otherwise a misconfigured account would silently receive partial data and never
learn why.

---

## 3. SEC-0 — one consolidated authorization model (your point 2)

Built **once**, consumed by every package. This is why the estimates in §7 do not double-count.

### 3.1 Three states, applied to all three dimensions

```python
UNRESTRICTED  = 'unrestricted'   # explicitly privileged: SystemAdmin, records-admin,
                                 # Chief Commander, read-only oversight
GRANTED       = 'granted'        # resolved to a specific module / branch / location
INDETERMINATE = 'indeterminate'  # missing, empty, unknown, ambiguous, or below threshold
```

**There is no fourth state and no default branch.** Today's bug is that one `None` means both
`UNRESTRICTED` and `INDETERMINATE`.

```python
class AccessDecision(NamedTuple):
    state: str              # UNRESTRICTED | GRANTED | INDETERMINATE
    value: object | None    # branch id, location code, or None
    reason: str             # audit/diagnostic text, never shown as authorization


def authorize(c, user, *, module=None, unit_type=None, location=False) -> AccessDecision:
    """The single entry point for every authorization question.

    Evaluates, in order: explicit unrestricted privilege, module permission,
    branch scope, checkpoint location scope. Any dimension that cannot be
    determined returns INDETERMINATE. There is no path that returns
    UNRESTRICTED as a fallback.
    """
```

### 3.2 The one enforcement rule

```python
def enforce(decision, what):
    if decision.state == INDETERMINATE:
        raise AuthorizationError(
            f'Your access to {what} cannot be determined from your account '
            f'({decision.reason}). Ask an administrator to correct your '
            f'assignment.')          # 403
    return decision


def scope_clause(decision, column):
    """('', ()) when UNRESTRICTED; (' AND col=%s', (v,)) when GRANTED.
    INDETERMINATE never reaches here - enforce() raised."""
    if decision.state == UNRESTRICTED:
        return '', ()
    return f' AND {column}=%s', (decision.value,)
```

**No fallback to unrestricted access.** `scope_clause` has two branches because the third has
already raised. There is no `else: return '', ()`.

### 3.3 What each dimension resolves

| Dimension | UNRESTRICTED | GRANTED | INDETERMINATE |
|---|---|---|---|
| **Module** | admin / Chief | module in `user_module_set(user)` | module absent |
| **Branch** | admin / records-admin / Chief / read-only | posting resolves to exactly one branch of the unit type | empty, unknown, ambiguous, score < 45, **or no resolvable unit type** |
| **Checkpoint location** | admin / Chief | `location_scope` is a known `CHECKPOINT_LOCATIONS` value | **empty string**, unknown value, or role default `''` |

The checkpoint row is the H-2b fix: `ROLE_CHECKPOINT_OFFICER` maps to `''`, which is falsy, so
`if scope:` treats it as admin. Under this model `''` is **INDETERMINATE → 403**, which is what the
existing docstring already claims happens.

### 3.4 Replaced by SEC-0

| Existing function | Fate |
|---|---|
| `branch_scope_view()` / `user_branch_scope()` | wrap `authorize(...)`; keep the name for display callers |
| `require_record_branch_scope()` | reimplemented on `enforce()` — removes `if not scope: return` |
| `require_branch_write_scope()` | reimplemented on `enforce()` — removes `if not scope: return branch_row` |
| `checkpoint_scope()` | wrap `authorize(..., location=True)`; `''` becomes INDETERMINATE |
| `checkpoint_scope_sql()` | reimplemented on `scope_clause()`; exact match on `location_code` |
| `require_module()` | folded in as the module dimension |
| `posting_scope_status()` | **kept, display-only** — must report the state, must never raise |

---

## 4. Rollout — staging only, no exposed production phase (your point 3)

**You are right, and the previous plan was wrong.** It proposed a report-only phase in production.
Per **R-1** Sentinel has **never had an operational database** — there is no production to be
compatible with. A report-only production phase would have deliberately shipped known-exploitable
defects.

**Revised: authorization is enforced before production exists. Nothing is deployed with a known
open authorization path.**

| Phase | Where | Action | Exit criterion |
|---|---|---|---|
| **R-A** | Development | Implement SEC-0; unit-test the decision matrix in isolation | All three dimensions return the correct state for every input class |
| **R-B** | Development | Implement SEC-1…SEC-4 against SEC-0; enforcement **on from the first commit** | 46 tests (§5) pass; each seen to fail pre-fix |
| **R-C** | **Staging** | Load representative accounts — one per role, plus deliberately broken ones (empty posting, unknown branch, ambiguous name, empty `location_scope`) | Diagnostic report lists every INDETERMINATE account |
| **R-D** | **Staging** | Correct the invalid assignments (**PRE-4**); re-run | **Zero** INDETERMINATE results for intended-valid accounts; the deliberately broken ones still 403 |
| **R-E** | Staging | Full regression + the §5 suite | 34 suites green, no skips |
| **R-F** | Production | Initialize with authorization already enforced | — |

**R-C/R-D replace the report-only phase.** The diagnostic runs against staging, not against live
data with the guard disabled.

> **One other document proposes the pattern you rejected.**
> `MIGRATION_PROPOSAL_DOCUMENT_OWNERSHIP.md` §B1 (the M-01 document-ownership migration) specifies
> *"deploy enforcement in report-only mode: authorize, log what would have been denied, **serve the
> file anyway**"*. By the principle you set, that is also wrong and should become a staging
> exercise. **I have not edited it** — M-01 is a separate unapproved proposal with its own decision
> trail, and silently rewriting it would hide the change. **Flagging it for your direction.**

### 4.1 Staging diagnostic

A read-only script — **not** a server mode — that reports what enforcement *would* do:

```
account          role              module  branch           location     verdict
--------------   ---------------   ------  ---------------  -----------  -------------
fp.officer       FingerprintUnit   ok      Lasanod Branch   n/a          OK
cid.officer      CIDUnit           ok      INDETERMINATE    n/a          WOULD 403
cp.south         CheckpointSouth   ok      n/a              South        OK
cp.new           checkpoint_officer ok     n/a              '' EMPTY     WOULD 403
```

It never disables a guard and never runs in production.

---

## 5. Verification (your point 4)

### 5.1 Standards

- Every test asserts a **concrete value** — status code, record id, row count. No `assertTrue(resp)`.
- Every test is **run against unmodified code first and must fail there**.
- **No skips.** The `test_document_branch_authorization.py` pattern of 4 schema-gated skips is not
  acceptable here; these fixes are being implemented, so their tests must execute.
- **Paired assertions**: every "denied" test has an "allowed" twin in the same database and run.

### 5.2 Endpoint × access-mode matrix

`D` = unauthorized denied · `A` = authorized still works · `—` = route does not exist.

| # | Endpoint | List | Direct ID | Linked | Read | Write | Update |
|---|---|---|---|---|---|---|---|
| E-1 | `/api/clearance-applications` | D+A | D+A | — | D+A | D+A | — |
| E-2 | `/api/fingerprint/applications` | D+A | D+A | — | D+A | D+A | D+A |
| E-3 | `/api/airport-records` | D+A | — | — | D+A | D+A | — |
| E-4 | `/api/crime-cases` | D+A | D+A | — | D+A | D+A | — |
| E-5 | `/api/crimes` | D+A | — | — | D+A | D+A | — |
| E-6 | `/api/checkpoint-events` | D+A | — | — | D+A | D+A | — |
| E-7 | `/api/persons/<id>` **(PE-1)** | — | D+A | D+A | D+A | — | — |
| E-8 | `/api/persons/<id>/linked-records` | — | — | D+A | D+A | — | — |
| E-9 | `/api/persons/<id>/documents` | — | — | D+A | D+A | — | — |
| E-10 | `/api/persons/<id>/audit-history` | — | — | D+A | D+A | — | — |
| E-11 | `/api/persons?q=` | **A only** | — | — | A | — | — |
| E-12 | Per-record audit history | — | D+A | — | D+A | — | — |

E-11 is **A only** by design (§2.3): identity search stays open to every authenticated session.
A test asserts it **keeps working** for a checkpoint officer — the regression guard for point 5.

### 5.3 The 46 tests

**`test_authorization_model.py`** — SEC-0 in isolation (10)

| ID | Test | Asserts |
|---|---|---|
| T-01 | `test_admin_is_unrestricted` | `UNRESTRICTED` on all three dimensions |
| T-02 | `test_chief_is_unrestricted_read` | `UNRESTRICTED`; writes still blocked by `enforce_read_only` |
| T-03 | `test_resolved_posting_is_granted` | `GRANTED` + correct branch id |
| T-04 | `test_empty_posting_is_indeterminate` | `INDETERMINATE` |
| T-05 | `test_unknown_branch_is_indeterminate` | `INDETERMINATE` |
| T-06 | `test_ambiguous_posting_is_indeterminate` | two equal matches → `INDETERMINATE` |
| T-07 | `test_below_threshold_is_indeterminate` | score < 45 → `INDETERMINATE` |
| T-08 | `test_no_unit_type_is_indeterminate` | unresolvable unit → `INDETERMINATE` |
| T-09 | `test_empty_location_scope_is_indeterminate` | `''` → `INDETERMINATE` (H-2b) |
| T-10 | `test_no_input_yields_unrestricted_never` | **property test** — no input combination returns `UNRESTRICTED` unless explicitly privileged |

**`test_branch_scope_enforcement.py`** — S-14 (12)

| ID | Test | Asserts |
|---|---|---|
| T-11 | `test_resolved_officer_sees_own_branch` | 200; own ids only; count > 0 |
| T-12 | `test_resolved_officer_writes_own_branch` | 201; lands in own branch |
| T-13 | `test_unresolved_list_is_403` | **403** (pre-fix: 200 + 3 records) |
| T-14 | `test_unresolved_write_is_403` | **403** (pre-fix: 201 into branch 11) |
| T-15 | `test_unresolved_record_by_id_is_403` | **403** (pre-fix: 200) |
| T-16 | `test_cross_branch_list_excludes_foreign` | foreign absent, own present |
| T-17 | `test_cross_branch_record_by_id_is_403` | 403 |
| T-18 | `test_cross_branch_write_is_403` | 403; row count unchanged |
| T-19 | `test_admin_sees_all_branches` | ids from both branches |
| T-20 | `test_admin_not_locked_out` | **control** |
| T-21 | `test_fingerprint_spec_route_is_scoped` | E-2 list + update |
| T-22 | `test_airport_routes_are_scoped` | E-3 read + write |

**`test_crime_branch_consistency.py`** — S-15 (5)

| ID | Test | Asserts |
|---|---|---|
| T-23 | `test_crimes_list_uses_crime_branch` | posted CID officer sees own incidents — **count > 0** (pre-fix: 0) |
| T-24 | `test_crime_create_is_branch_scoped` | cross-branch filing → 403 |
| T-25 | `test_crime_create_adopts_own_branch` | omitted branch → own branch |
| T-26 | `test_removing_station_branches_does_not_widen_access` | **zero `police_station` rows → scoped or 403, never all rows** |
| T-27 | `test_crime_cases_and_crimes_agree` | both endpoints report the same branch id for one session |

**`test_checkpoint_scope_enforcement.py`** — Checkpoint (8)

| ID | Test | Asserts |
|---|---|---|
| T-28 | `test_officer_sees_own_location_only` | own location only |
| T-29 | `test_empty_location_scope_is_403` | **403** (pre-fix: all events) |
| T-30 | `test_cross_location_write_is_403` | 403 |
| T-31 | `test_unknown_location_is_rejected` | location `atlantis` → **400** |
| T-32 | `test_checkpoint_is_branch_scoped` | two branches, one location → isolated |
| T-33 | `test_substring_location_does_not_match` | `Southwest` ≠ `South` |
| T-34 | `test_admin_sees_all_locations` | **control** |
| T-35 | `test_checkpoint_officer_can_still_record` | **control** — normal intake unaffected |

**`test_person_detail_authorization.py`** — S-16 + alert ownership (11)

| ID | Test | Asserts |
|---|---|---|
| T-36 | `test_person_detail_filters_by_module` | `cp.south` → `clearance: []` (pre-fix: 1 record) |
| T-37 | `test_person_detail_filters_by_branch` | scoped FP officer → foreign application absent (pre-fix: present) |
| T-38 | `test_person_detail_filters_checkpoints_by_location` | own-location events only |
| T-39 | `test_person_detail_returns_identity_to_every_role` | **control, point 5** — `full_name`, `national_id`, `photo_path` present for a checkpoint officer |
| T-40 | `test_person_search_still_works_for_all_roles` | **control** — E-11 unaffected |
| T-41 | `test_linked_records_filters_by_branch` | S-16b |
| T-42 | `test_documents_filters_by_branch` | S-16b |
| T-43 | `test_audit_history_filters_by_branch` | S-16b |
| T-44 | `test_alert_content_is_branch_scoped` | **rewritten in rev 3.** Was "pin the S-04 gap"; now asserts a cross-branch CID officer is refused alert *content* (requires M-02 Phase A) |
| T-45 | `test_alert_flag_stays_national` | **control, safety-critical** — a checkpoint officer with **no** `cid` module still gets `Flagged match` for an out-of-branch suspect. Fails if the fix over-restricts |
| T-46 | `test_null_alert_branch_is_refused_not_all` | `branch_id IS NULL` ⇒ `INDETERMINATE` ⇒ refuse. Never "all branches" |

T-10, T-20, T-34, T-35, T-39, T-40, **T-45** are controls. **T-44 no longer pins a gap** — rev 2
accepted the alert register as unfixable; rev 3 fixes it via M-02 Phase A, so the test asserts the
corrected behaviour instead. See `SUSPECT_ALERT_OWNERSHIP.md`.

### 5.4 Suites

| File | Tests |
|---|---|
| `backend/test_authorization_model.py` | T-01…T-10 |
| `backend/test_branch_scope_enforcement.py` | T-11…T-22 |
| `backend/test_crime_branch_consistency.py` | T-23…T-27 |
| `backend/test_checkpoint_scope_enforcement.py` | T-28…T-35 |
| `backend/test_person_detail_authorization.py` | T-36…T-44 |

**Suites 29 → 34.** All match the runner glob.

---

## 6. SS-1 — station safeguards, separate package (your point 6)

**Unchanged in content, and still awaiting your approval.** Not merged into any SEC package and not
a dependency of any of them.

> **Full options analysis — including operational consequences, affected workflows and the
> recommendation — is in `SS1_STATION_SAFEGUARD_OPTIONS.md` (your review point 4).** The summary
> below is retained for continuity.

### 6.1 The four station-creation paths

| # | Path | Line | Produces |
|---|---|---|---|
| 1 | `register_station()` | 4915 | **Legitimate** — validated, phone required, `created_by` set, audited |
| 2 | `resolve_station_with_branch()` | 4700 | tier `'District HQ'`, no phone, `created_by NULL`, notes `'… (auto)'` |
| 3 | `resolve_station_with_branch()` | 4724 | as #2, legacy numeric id |
| 4 | `POST /api/branches` `unit_type='police_station'` | 9145 | as #2, `created_by` set, `except Exception: pass` |

| ID | Guard |
|---|---|
| **G-a** | Refuse a station with `contact_phone IS NULL` or `created_by IS NULL` at crime intake |
| **G-b** | `register_crime()` uses a new `resolve_station_readonly()` — **never creates** |
| **G-c** | Refuse `operational_status != 'Active'` |
| **G-d** | Confirm station codes before first use (PRE-5, procedural) |

### 6.2 G-b — operational impact, stated plainly

**Today:** posting an officer or filing a crime against a Police Stations branch (`BR-<id>`) *works*.
The system silently creates the backing station row and proceeds. The operator sees success.

**After G-b:** the same action **fails** with an error until a System Administrator registers the
station properly through *Register police station*.

| | Today | After G-b |
|---|---|---|
| File a crime against `BR-7` | Succeeds; station auto-created with invented `'District HQ'` tier, no phone | **Error** — "station is not registered" |
| Register an officer at `BR-7` | Succeeds; same | **Error** (same resolver) |
| Who must act | nobody | **System Administrator**, before the unit can proceed |
| Effect on existing records | none | none — nothing is deleted or altered |

**This is a real workflow change, not only a hardening measure.** It converts a silent success into
a blocking error, and it adds an administrative step on a path some operators may be using. The
security argument is that the "success" was fabricating an HQ-owned record and stamping its invented
code permanently into crime file numbers — but **that is a judgement about operations, and it is
yours.**

**Options:** **(i)** G-a + G-c now, G-b deferred — blocks *use* of fabricated stations without
changing the resolver; **(ii)** all four — fully closes the path; **(iii)** all four plus a clear
operator message naming the administrator action required. **I recommend (iii)**, but **nothing in
SS-1 proceeds without your explicit approval.**

**Effort: 1–2 days.** No schema change. Independently revertible.

---

## 7. Packages, dependencies and estimates (your point 7)

### 7.1 Dependency graph

```
SEC-0  unified authorization model  (built ONCE)
  ├── SEC-2  S-14  branch call sites ── SEC-3  S-15 crime consistency ──┐
  ├── SEC-4  H-2b  checkpoint ──────────────────────┬──────────────────┤
  │                                                 │                  │
  └── M-02 Phase A  suspect_alerts.branch_id ───────┴── SEC-1 ─────────┤
                                                   (S-16a/b + alerts)  │
                                                                       └── SEC-5 staging (R-C/R-D)
                                                                              └── A-18 (+ PRE-3)
SS-1   station safeguards — INDEPENDENT, awaiting approval
```

### 7.2 Estimates, shared work counted once

| Pkg | Content | Severity | **New work** | Depends on |
|---|---|---|---|---|
| **SEC-0** | Three-state model, `authorize()`, `enforce()`, `scope_clause()`, T-01…T-10 | — | **2–3 d** | — |
| **M-02-A** | `suspect_alerts.branch_id` column + backfill + record branch on write | **Critical** | **1–1.5 d** | SEC-0 |
| **SEC-1** | **S-16a + S-16b** — PE-1 filtering; branch filtering on PE-2…PE-4; alert read scoping; T-36…T-46 | **Critical** | **2–3 d** | SEC-0, **SEC-4**, **M-02-A** |
| **SEC-2** | **S-14** — 12 enforcing call sites on SEC-0; T-11…T-22 | **Critical** | **2–3 d** | SEC-0 |
| **SEC-3** | **S-15** — `/api/crimes` unit type, crime write guard; T-23…T-27 | High | **1–2 d** | SEC-0, SEC-2 |
| **SEC-4** | **Checkpoint** CP-2…CP-6 (CP-1 is now SEC-0); T-28…T-35 | High | **2–3 d** | SEC-0 |
| **SEC-5** | Staging diagnostic + assignment correction (R-C/R-D) | — | **1–2 d** | SEC-1…4 |
| | **Authorization total** | | **11–17.5 d** | |
| **SS-1** | Station safeguards G-a…G-d | High | **1–2 d** | *(independent — approval)* |
| **P0-WP-1** | N-7 / S-07 | High | 1.5 d | — |
| **P0-WP-2** | H-5 / S-02 session revocation | High | 1.5–2 d | — |
| **P0-WP-3** | Initialization, S-12/S-13, **A-18** | High | 2–3 d | SEC-2, SEC-3, PRE-3 |

**Double-counting avoided:** the three-state helper, the `INDETERMINATE` semantics and the
checkpoint `''` fix are **all in SEC-0 and costed once**. The first version costed S-14 at 3–5 d
*including* the helper and separately costed CP-1, which duplicated it. SEC-2 is now 2–3 d because
it is call-site work only, and SEC-4 dropped from 3–4 d to 2–3 d for the same reason.

**Revision 3 adds 1–1.5 d and nothing else.** That is M-02 Phase A — a schema change that did not
exist in the plan before, because until the four registers were actually measured the alert gap was
recorded as "cannot be fixed" rather than costed. SEC-1's own estimate is **unchanged at 2–3 d**:
the alert read-scoping is the same branch clause already being added to the other three arrays, so
it is **not re-counted**. Full shared-mechanism audit: `ENDPOINT_AUTHORIZATION_INVENTORY.md` §5.1.

### 7.3 Totals

| | Previous | **Revised** |
|---|---|---|
| Authorization (SEC-0…SEC-5 **+ M-02 Phase A**) | 10–16 d | **11–17.5 d** |
| P0-WP-1/2/3 | 7–9.5 d | 7–9.5 d |
| SS-1 *(separate, pending approval)* | 1–2 d | 1–2 d |
| **Before Release 1.0** | 17–25.5 d | **18–27 d + 1–2 d if SS-1 approved** |

The increase is **entirely** M-02 Phase A. It is the price of actually fixing the alert register
instead of documenting it as unfixable.

### 7.4 Release blockers

| ID | Severity | Blocks | Cleared by |
|---|---|---|---|
| **S-16a** | **Critical** | Release 1.0 | SEC-1 + T-36…T-40 |
| **S-16b** | High | Release 1.0 | SEC-1 + T-41…T-43 |
| **S-14** | **Critical** | Release 1.0 | SEC-2 + T-11…T-22 |
| **S-15** | High | Release 1.0 **and A-18** | SEC-3 + T-23…T-27 |
| **H-2b** | High | Release 1.0 | SEC-4 + T-28…T-35 |
| **S-04** | **High** *(raised)* | alert branch isolation, CID authorization completeness | **M-02 Phase A** + SEC-1 + T-44…T-46 |
| **S-03** | High | alert correction/withdrawal | **not in authorization scope** — needs M-02 lifecycle + D-23 |
| **PRE-3** | — | A-18 | CID deployment authority |

**A-18 remains on hold.**

---

## 8. Limits and disclosures

- **Nothing implemented.** All three probes deleted; `server.py` sha256 `a8211f4f…b3b9fc` unchanged;
  28 PASS / 0 FAIL / 1 BLOCKED.
- **The 46 tests are specified, not written.**
- **RESOLVED in rev 3 — all four registers measured.** Revision 2 disclosed that only the
  `clearance` array had been demonstrated and the other three were "structurally identical, not
  proven". They have now been measured individually through the real endpoint:
  `S16_REGISTER_VERIFICATION.md`. They are **not** identical — they fail in three different ways,
  and the differences changed the dependency order.
- **S-16b is now PROVEN**, on `clearance_applications` and `airport_passengers` — the two registers
  whose own endpoints *do* enforce branch, so the leak is unambiguous.
- **H-2b is now PROVEN**: a checkpoint officer at the matching location but a different branch reads
  the record from the **owning endpoint**. Previously a code-read inference.
- **RESOLVED 5 Nov 2026 — the last four code-read items were executed** (`OWNER_DECISION_SHEET_AUTHORIZATION.md`
  §6). `/documents` and `/audit-history` **leak cross-branch** (an Erigavo officer receives a
  Buuhoodle application's 4 documents and its clearance audit events in full); an unrecognised
  checkpoint location is **accepted and stored** as `'atlantis'`; and `South` **does** match
  `Southwest`. T-31, T-33, T-42, T-43 are evidence-backed, not speculative.
- **RESOLVED — S-15 has now been executed** (`S15_EXECUTION_VERIFICATION.md`, 5 Nov 2026,
  scenarios A–E). **Every finding in this package is now measured; none rests on code reading.**
  The probe also found **three new defects — S-17 (NULL branch accepted), S-18 (cross-branch write
  accepted), S-19 (file numbers encode the station region)** — and proved the A-18 blocker by
  moving posted officers from 0 rows to 8 (all) when the `police_station` branch rows were deleted
  in a disposable database. **SEC-3 is not safe to ship without SEC-2 and a write guard.**
- **Fixtures in the four-register probe were seeded with SQL**, not filed through the intake
  endpoints; only the authorization measurements were real HTTP. One record per register; no
  pagination or ordering coverage.
- **`suspect_alerts` branch-filtering now has an answer** — it requires a schema change (M-02 Phase
  A). Rev 2 recorded it as unfixable and pinned the gap; that was premature.
- **Your review named the airport register `airport_movements`; the table is `airport_passengers`.**
  Same register; recording it so the test plan and schema agree.
- **The previous revision proposed a report-only production phase.** That was wrong — it would have
  shipped known-exploitable defects into production. Removed and replaced by staging phases R-C/R-D.
- **SEC-5's duration depends on how many accounts need correcting**, which is an operational
  unknown, not an engineering estimate.
