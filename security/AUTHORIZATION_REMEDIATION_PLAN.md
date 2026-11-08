# Security Remediation Plan — Authorization (revised)

**Date:** 5 November 2026 (date conflict unresolved — `RELEASE_1_0_REFERENCE_DATA.md` §5)
**Commit:** `8ea2f9b` · **Status:** **PLAN — NOTHING IMPLEMENTED — AWAITING APPROVAL**
**Revision 2.** Supersedes the first version. Changes: S-16 promoted to its own critical package and
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

| Finding | Where | Severity | Precondition to exploit |
|---|---|---|---|
| **S-16a** | `/api/persons/<id>` — no module, branch or location filter | **Critical** | **None** |
| **S-16b** | `/linked-records`, `/documents`, `/audit-history` — no branch filter | **High** | **None** |
| **S-14** | Branch scope, 12 enforcing call sites | **Critical** | A posting that does not resolve |
| **S-15** | `/api/crimes` unit-type mismatch | **High** | None (currently fails closed) |
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
| **R-B** | Development | Implement SEC-1…SEC-4 against SEC-0; enforcement **on from the first commit** | 44 tests (§5) pass; each seen to fail pre-fix |
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

### 5.3 The 44 tests

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

**`test_person_detail_authorization.py`** — S-16 (9)

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
| T-44 | `test_alerts_gated_by_module_only_is_documented` | asserts `cid`-module gating **and** that alerts are *not* branch-filtered, pinning the S-04 gap so it cannot be silently forgotten |

T-10, T-20, T-34, T-35, T-39, T-40 are controls. T-44 deliberately pins a **known remaining gap**
rather than asserting a fiction.

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
  ├── SEC-1  S-16   person endpoints        ──┐
  ├── SEC-2  S-14   branch call sites       ──┤
  │     └── SEC-3   S-15  crime consistency  │
  └── SEC-4  H-2b   checkpoint              ──┤
                                              └── SEC-5  staging diagnostics (R-C/R-D)
                                                     └── A-18  (also needs PRE-3)
SS-1   station safeguards — INDEPENDENT, awaiting approval
```

### 7.2 Estimates, shared work counted once

| Pkg | Content | Severity | **New work** | Depends on |
|---|---|---|---|---|
| **SEC-0** | Three-state model, `authorize()`, `enforce()`, `scope_clause()`, T-01…T-10 | — | **2–3 d** | — |
| **SEC-1** | **S-16a + S-16b** — PE-1 filtering; branch filtering on PE-2…PE-4; T-36…T-44 | **Critical** | **2–3 d** | SEC-0 |
| **SEC-2** | **S-14** — 12 enforcing call sites on SEC-0; T-11…T-22 | **Critical** | **2–3 d** | SEC-0 |
| **SEC-3** | **S-15** — `/api/crimes` unit type, crime write guard; T-23…T-27 | High | **1–2 d** | SEC-0, SEC-2 |
| **SEC-4** | **Checkpoint** CP-2…CP-6 (CP-1 is now SEC-0); T-28…T-35 | High | **2–3 d** | SEC-0 |
| **SEC-5** | Staging diagnostic + assignment correction (R-C/R-D) | — | **1–2 d** | SEC-1…4 |
| | **Authorization total** | | **10–16 d** | |
| **SS-1** | Station safeguards G-a…G-d | High | **1–2 d** | *(independent — approval)* |
| **P0-WP-1** | N-7 / S-07 | High | 1.5 d | — |
| **P0-WP-2** | H-5 / S-02 session revocation | High | 1.5–2 d | — |
| **P0-WP-3** | Initialization, S-12/S-13, **A-18** | High | 2–3 d | SEC-2, SEC-3, PRE-3 |

**Double-counting avoided:** the three-state helper, the `INDETERMINATE` semantics and the
checkpoint `''` fix are **all in SEC-0 and costed once**. The first version costed S-14 at 3–5 d
*including* the helper and separately costed CP-1, which duplicated it. SEC-2 is now 2–3 d because
it is call-site work only, and SEC-4 dropped from 3–4 d to 2–3 d for the same reason.

### 7.3 Totals

| | Previous | **Revised** |
|---|---|---|
| Authorization (SEC-0…SEC-5) | 10–16 d | **10–16 d** |
| P0-WP-1/2/3 | 7–9.5 d | 7–9.5 d |
| SS-1 *(separate, pending approval)* | 1–2 d | 1–2 d |
| **Before Release 1.0** | 17–25.5 d | **17–25.5 d + 1–2 d if SS-1 approved** |

Unchanged in total, but now with the model built once and SEC-5 (staging) explicitly funded instead
of an unfunded report-only production phase.

### 7.4 Release blockers

| ID | Severity | Blocks | Cleared by |
|---|---|---|---|
| **S-16a** | **Critical** | Release 1.0 | SEC-1 + T-36…T-40 |
| **S-16b** | High | Release 1.0 | SEC-1 + T-41…T-43 |
| **S-14** | **Critical** | Release 1.0 | SEC-2 + T-11…T-22 |
| **S-15** | High | Release 1.0 **and A-18** | SEC-3 + T-23…T-27 |
| **H-2b** | High | Release 1.0 | SEC-4 + T-28…T-35 |
| **S-04** | Medium | alert branch isolation | pinned by T-44; needs the S-04 schema change |
| **PRE-3** | — | A-18 | CID deployment authority |

**A-18 remains on hold.**

---

## 8. Limits and disclosures

- **Nothing implemented.** Both probes deleted; `server.py` unchanged; 28 PASS / 0 FAIL / 1 BLOCKED.
- **The 44 tests are specified, not written.**
- **S-16's `airport`, `alerts` and `checkpoints` arrays were not separately measured** — only
  `clearance` was demonstrated (probes Q2, Q4). The other three are the same unfiltered
  `WHERE person_id=%s` in the same handler. Stated as structurally identical, **not** as proven.
- **S-16b was established by reading `linked_person_records()`, `person_document_records()` and
  `person_audit_history()`**, confirming each applies module and checkpoint filters and **no branch
  filter**. Not probed. T-41…T-43 must fail pre-fix.
- **Checkpoint findings (c) unknown-location and (d) substring matching are from code reading**, not
  from a probe. T-31 and T-33 must fail pre-fix.
- **`suspect_alerts` cannot be branch-filtered** — the column does not exist (S-04). T-44 pins the
  gap deliberately.
- **The previous revision proposed a report-only production phase.** That was wrong — it would have
  shipped known-exploitable defects into production. Removed and replaced by staging phases R-C/R-D.
- **SEC-5's duration depends on how many accounts need correcting**, which is an operational
  unknown, not an engineering estimate.
