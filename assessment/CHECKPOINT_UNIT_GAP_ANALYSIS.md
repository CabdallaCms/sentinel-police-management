# Checkpoint Unit — Gap Analysis

**Deliverable 4 of 8 · Phase 2 · Assessment only.**
Branch `arena/6303ef2f-sentinel-police-management` · commit `a1c2478` · 2026-11-06
Evidence classes: **[STATIC]** · **[RUNTIME-2026-11-06]** · **[RUNTIME-HISTORICAL]** (PR #23 @ `381545c`) · **[NOT VERIFIED]**

---

## 1. The headline question: is the Checkpoint Unit "already implemented"?

**Partly — and the part that is missing is the part that makes it safe.**

| Aspect | Verdict |
|---|---|
| Screening **capture** (traveller identity, guardian, documents, live photo, purpose, addresses) | Built, thorough, and stricter than the other units' intake forms **[STATIC]** |
| Automatic **suspect flagging** against CID alerts | Built **[STATIC]** |
| **Location isolation** — the control that stops one checkpoint reading another's travellers | **Fails open for the canonical role** **[STATIC]**, reproduced historically as M-2 **[RUNTIME-HISTORICAL]** |
| **Branch isolation on reads** | Not applied — reads filter by location string, never by `branch_id` **[STATIC]** |
| **What happens after a flag** (detention, escalation, handover, outcome) | Does not exist **[STATIC]** |
| **Verification** | Zero suites executed at this commit **[RUNTIME-2026-11-06]** |

So: the unit can *record* a stop very well. It cannot yet be trusted to *contain* that record, and it cannot record the operational response to a hit.

---

## 2. What exists and works (by code reading)

| # | Capability | Location | Class |
|---|---|---|---|
| CP-01 | Screening event capture, multipart or JSON | `server.py:9212-9218` | Implemented but not verified |
| CP-02 | Traveller validation: 4-part name, DOB, purpose of visit, current address | `:9220-9228` | Implemented but not verified |
| CP-03 | Mandatory **live traveller photo** and ≥1 traveller document | `:9229-9231` | Implemented but not verified |
| CP-04 | Guardian block required in full: 4-part name, relationship, phone, permanent address, occupation, ≥1 document | `:9232-9246` | Implemented but not verified |
| CP-05 | Traveller identity auto-create / fill-only enrichment, IDs optional (`allow_no_id=True`) | `:9248-9253` | Implemented but not verified |
| CP-06 | Guardian identity resolution — explicit `guardian_person_id`, else match by NID/passport/name | `:9256-9266` | Implemented but not verified |
| CP-07 | **Automatic suspect flagging**: active `Suspect` alert → `Flagged match` + `Supervisor contacted`; otherwise `No active alert` + `Cleared` | `:9304-9307` | Implemented but not verified |
| CP-08 | Location normalised to a canonical code and written consistently to three columns | `:9267-9290`, `:9318` | Implemented but not verified |
| CP-09 | Branch-scoped **write** | `require_branch_write_scope(...,'checkpoint')` `:9219` | Implemented but not verified |
| CP-10 | Location-scoped **write** refusal | `:9300-9303` | Implemented but not verified (fails open — see G-01) |
| CP-11 | Location-scoped read with a tolerant 6-way SQL match | `:8460-8474` | Implemented but not verified (fails open — see G-01) |
| CP-12 | Response carries `scope` and `visible_locations` for the UI | `:8490-8492` | Implemented but not verified |
| CP-13 | Unified `checkpoint_officer` role; legacy compound roles normalise to it and are migrated in place | `ROLE_LABELS:1816`; `unify_checkpoint_roles()` | Implemented but not verified |
| CP-14 | Per-record audit history, branch-scoped | `AUDIT_ENTITY_*:2757-2772`; `:4281` | Implemented but not verified |
| CP-15 | Location-scoped checkpoint analytics | `cid_checkpoint_analytics(c, user)` `:6176-6183` | Implemented but not verified |
| CP-16 | Vehicle plate / VIN lookup from the checkpoint page | `lookupCheckpointPlate`; `/api/vehicles` break-out `:8118-8123` | Implemented but not verified |
| CP-17 | Audit row on every screening event | `:9341-9342` | Implemented but not verified |

---

## 3. Gaps **inside** Release 1.0 scope

### 3.1 Security gaps (blocking)

| # | Gap | Evidence | Class | Priority |
|---|---|---|---|---|
| **G-01** | **Location scope fails open for the canonical `checkpoint_officer` role.** `ROLE_LOCATION_SCOPE[ROLE_CHECKPOINT_OFFICER] = ''` (`:1922`), and `checkpoint_scope()` returns `ROLE_LOCATION_SCOPE[r] or ''` (`:2990`) — an **empty string**. Both call sites branch on `if scope:` (`:8460`, `:9301`), so an empty scope means **no filter**. A checkpoint officer whose `location_scope` is blank therefore **reads every checkpoint's travellers and can file a stop at any checkpoint**. The in-code comment at `:1919-1921` asserts the opposite intent ("its default scope is empty so the SQL filter never leaks other locations"), so this is an implementation/intent mismatch, not a design choice. Note the perverse consequence: the **legacy** roles (`CheckpointSouth/East/West`) are **safer** than the modern one, because their scope is derived from the role name. | `:1922`, `:2983-2990`, `:8460`, `:9301` | **[STATIC]** confirmed; **[RUNTIME-HISTORICAL]** M-2 | **P0** |
| **G-02** | **Posting scope fails open too.** `branch_scope_view()` returns `None` (unrestricted) when an officer's posting does not resolve to a registered branch (`:2683-2684`). This governs the branch-scoped **write** check at `:9219`, so an unresolvable posting removes the branch constraint as well. | `:2661-2694` | **[STATIC]** confirmed; **[RUNTIME-HISTORICAL]** H-2b | **P0** |
| **G-03** | **Traveller photographs and identity documents are retrievable without authentication.** Checkpoint uploads go to the same `/uploads/` directory served by `serve_static()` before auth. | `:7914`, `:9247`, `:9254-9255` | **[STATIC]** confirmed; **[RUNTIME-HISTORICAL]** C-1 | **P0** |
| **G-04** | **Reads are not branch-scoped at all.** `GET /api/checkpoint-events` filters only on location strings; `checkpoint_events.branch_id` exists and is written, but is never used as a read filter. Two checkpoints named "South" in different branches would see each other's rows. | `:8433-8480` vs DDL `:319` | **[STATIC]** | **P1** |
| **G-05** | **Traveller and guardian uploads are unvalidated** — no extension, MIME or size check (`save_upload()`), unlike the Fingerprint signed-scan route. | `:3939-3946` vs `:9009-9018` | **[STATIC]** | **P1** |
| **G-06** | **Event identifier collision risk** — `'CP-' + last 8 digits of epoch ms`. | `:9319` | **[STATIC]** | **P2** |
| **G-07** | **`location_scope` is not mandatory when creating a checkpoint officer.** Combined with G-01, an administrator can create an unscoped checkpoint officer by omitting one field. | user-create path `:9105+`; no required-scope validation found | **[STATIC]** | **P1** |

### 3.2 Functional gaps (in scope)

| # | Gap | Evidence | Class |
|---|---|---|---|
| **G-08** | **The officer cannot record what actually happened.** `screening_result` and `action_taken` are computed by the server from the alert check alone (two possible values each). The officer cannot record a detention, a refusal, a referral, a false match, a vehicle seizure or any other real outcome. | `:9305-9306` | **Not implemented** |
| **G-09** | **No post-flag workflow.** A `Flagged match` writes `'Supervisor contacted'` as a *string*; nothing notifies a supervisor, creates a task, opens a CID referral or records the response. | `:9306` | **Not implemented** |
| **G-10** | **No event amendment or correction.** There is no `PATCH /api/checkpoint-events/<id>`; a mistaken screening is permanent. | do_PATCH route list `:9491-9650` | **Not implemented** |
| **G-11** | **No single-event read route.** Only the register listing exists, so there is no per-record authorization point. | GET route list | **Not implemented** |
| **G-12** | **No vehicle linkage on the event.** The plate lookup is a read-only UI convenience; `checkpoint_events` has no vehicle column, so "which vehicle was stopped" is not recorded. | DDL `:316-336`; `lookupCheckpointPlate` | **Not implemented** |
| **G-13** | **The checkpoint catalogue is hard-coded to three areas.** `CHECKPOINT_LOCATIONS = ('South','East','West')` while Branch Management and officer postings already support named district checkpoints (e.g. "Adhi Cadeeye Outpost", referenced in `checkpoint_scope`'s own docstring). Named checkpoints fall into the analytics "Other" bucket. | `:1649`; `:6196-6215` | **Partially implemented**, needs **D-20** |
| **G-14** | **Three columns encode one location fact** (`location`, `location_code`, `checkpoint_location`), which is why the read filter needs a six-way `OR` with `ILIKE` fallbacks. This makes the scope control hard to reason about and hard to test — a normalisation debt sitting directly under a security control. | DDL `:320`; `:8460-8474` | **Partially implemented** |
| **G-15** | **No structured search or filtering** — one client-side free-text box; the endpoint reads no query parameters; no pagination. | `index.html` `#checkpoints`; `:8433` | **Not implemented** |
| **G-16** | **No designed offline operation.** Checkpoints are the most likely place to lose connectivity, and the only fallback is the generic browser `localStorage` demo store, which is a data-integrity hazard, not a sync model. | `index.html:2641-2648` | **Blocked** on **D-11** |
| **G-17** | **Documents stored as JSON blobs** (`traveler_docs`, `guardian_docs`) — no per-document authorization, retention or integrity hash. | DDL `:519`, `:528` | **Partially implemented** |

---

## 4. Roles and permissions **[STATIC]**

| Role | Modules | Location scope | Note |
|---|---|---|---|
| `checkpoint_officer` (canonical) | `{dashboard, checkpoints}` | `users.location_scope`, **empty by default** | **Unscoped when blank — G-01** |
| `CheckpointSouth` / `East` / `West` (legacy) | `{dashboard, checkpoints}` | derived from the role name | Safer than the canonical role |
| `SystemAdmin` | all | `None` = all locations | Intended |
| `chief_commander` | read-only all | `None` = all locations | Intended; writes `403` |
| Every other role | — | — | `403` from the module gate |

**Gaps:** no supervisor or checkpoint-commander role, so G-09's "supervisor contacted" has no one to contact inside the system; and no per-checkpoint permission beyond the single `location_scope` string.

---

## 5. Main workflows **[STATIC]**

**Implemented:** open scoped page → fill traveller + guardian form (strict validation) → live photo + documents → identity resolved/created/enriched → server checks `suspect_alerts` → result and action computed → event stored with normalised location → audit row → optional plate lookup.

**Not implemented:** anything after the flag. No detention record, no escalation, no CID referral, no outcome capture, no correction, no handover, no supervisor acknowledgement.

---

## 6. Database model **[STATIC]**

```
persons ──1──< checkpoint_events (event_id 'CP-########')
   │              person_id          → persons.id         NOT NULL
   │              guardian_person_id → persons.id         nullable
   │              branch_id          → police_branches.id (unit_type='checkpoint')  ← written, never read as a filter
   │              location / location_code / checkpoint_location   ← 3 columns, 1 fact
   │              screening_result   'Flagged match' | 'No active alert'   ← server-computed only
   │              action_taken       'Supervisor contacted' | 'Cleared'    ← server-computed only
   │              purpose_of_visit · current_address · permanent_address
   │              traveler_photo · traveler_docs (JSON TEXT) · guardian_docs (JSON TEXT)
   │              guardian_name/relationship/phone/address/occupation/national_id/passport_id
   │              created_by → users.id
suspect_alerts ───┘ read at screening time (role='Suspect' AND alert_status='Active alert')
```

**Relationship risk:** the Checkpoint Unit's core value depends entirely on `suspect_alerts`, which (per the Crime Unit analysis) has **no `branch_id`** and **no lifecycle** — an alert, once created, stays `'Active alert'` forever. A person cleared by CID will keep flagging at every checkpoint indefinitely. **[STATIC]**

---

## 7. API and frontend **[STATIC]**

| Method | Path | Module gate | Scope applied |
|---|---|---|---|
| GET | `/api/checkpoint-events` | `checkpoints` `:8103` | location only, **fails open** |
| POST | `/api/checkpoint-events` | `checkpoints` `:8876` | branch (`:9219`) **+** location (`:9301`), both **fail open** |
| GET | `/api/vehicles` | break-out permits `checkpoints` `:8120` | none |
| GET | `/api/cid/analytics` → checkpoint section | `checkpoints` | location, same fail-open |
| GET | `/api/audit/entity/checkpoint_event/<id>` | `checkpoints` | branch-scoped `:4281` |

**Frontend (`index.html`, page `#checkpoints`):** `renderCheckpointPage`, `renderCheckpointTable`, `renderCheckpointNav`, `fetchCheckpoints`, `openCheckpointDrawer`, `openCheckpointUnit`, `submitCheckpoint`, `travelerFormHTML`, `validateTraveler`, `checkpointScopeFor`, `checkpointUnitCatalog`, `paintCheckpointScopeHint`, `paintCheckpointChips`, `userCheckpointOptions`, `isCheckpointRole`, `isCheckpointPosting`, `lookupCheckpointPlate`, `checkpointLabelText`.

---

## 8. Tests and their results

| Suite | Checkpoint relevance | Result at `a1c2478` |
|---|---|---|
| `test_checkpoint_roles_audit.py` | 76 references — unified role, legacy migration idempotency, per-record audit history | **NOT RUN** (needs `pgserver`) |
| `test_sidebar_navigation.mjs` | 86 references — navigation scoping (**client-side only**) | **NOT RUN** |
| `test_frontend_session.mjs` | 57 references | **NOT RUN** |
| `test_officer_profile_locations.py` | 34 references — Region→District→Checkpoint pickers | **NOT RUN** |
| `test_branch_management_ui.mjs` / `test_branch_management_crud.py` | 29 / 26 references | **NOT RUN** |

**Critical coverage gap [STATIC]:** no suite asserts that a `checkpoint_officer` with a **blank `location_scope`** is denied. The behaviour that G-01 describes is therefore not merely untested — the test suite is silent precisely where the control fails. Additionally, the navigation suites assert what the **UI hides**, which cannot prove what the **server refuses**.

**Required negative tests that do not exist:**
1. `checkpoint_officer`, `location_scope=''` → `GET /api/checkpoint-events` must **not** return another location's rows.
2. Same officer → `POST` to another location must return 403.
3. Officer with an unresolvable posting must be **denied**, not unscoped.
4. Anonymous `GET /uploads/<traveller photo>` must return 401/403.
5. Cross-branch read of a checkpoint event must be refused even when the location label matches.

---

## 9. Integration dependencies

| Dependency | Direction | Risk |
|---|---|---|
| **`suspect_alerts` (Crime Unit)** | Checkpoint ← Crime | **Hard dependency.** The flag is the unit's purpose. Inherits the Crime Unit's missing alert lifecycle (G-09 cannot be completed without SM-07). |
| Central Person Registry | Checkpoint → shared | Auto-create with `allow_no_id=True` — the loosest identity path in the system |
| `police_branches` + scoping helpers | Checkpoint → shared | Fixing G-02 is a shared change affecting all units |
| `users.location_scope` | Checkpoint → shared | Fixing G-01/G-07 touches user management |
| `audit_events` | Checkpoint → shared | — |
| Uploads directory | Checkpoint → shared | Fixing G-03 is the same shared fix as FG-01 |
| `vehicles` | Checkpoint → Transport | Read-only lookup today; G-12 would make it a real link |

---

## 10. Classification roll-up

| Class | Count | Items |
|---|---|---|
| **Implemented and verified** | 0 | — (no checkpoint suite was executable at this commit) |
| **Implemented but not verified** | 8 | CP-01…CP-09, CP-12…CP-17 (grouped areas) |
| **Partially implemented** | 3 | G-13, G-14, G-17 |
| **Not implemented** | 5 | G-08 (officer-recorded outcome) · G-09 (post-flag workflow) · G-10 + G-11 (event amendment and single-event read — one missing per-record route surface) · G-12 (vehicle linkage) · G-15 (structured search and filtering) |
| **Blocked** | 1 | G-16 (**D-11**) |

---

## 11. Recommended close-out order for this unit

> Order only. **No work is authorised until the owner approves.**

1. **G-01** make `checkpoint_scope()` fail **closed**: a checkpoint officer with no resolvable location is denied, not widened. Ship with the five negative tests in §8.
2. **G-02** make `branch_scope_view()` fail closed (shared with all units).
3. **G-03** authenticated document retrieval (shared fix).
4. **G-07** require `location_scope` when creating or editing a checkpoint officer.
5. **G-04** add branch-based read filtering alongside location filtering.
6. **G-05** validate traveller and guardian uploads.
7. **D-20 decision** → **G-13** configurable checkpoint catalogue.
8. **G-08 / G-09** officer-recorded outcome and post-flag workflow — **requires the Crime Unit's SM-07 alert lifecycle first**.
9. **G-10 / G-11** amendment route and single-event read.
10. **G-14** collapse the three location columns (schema change; schedule after versioned migrations exist).
11. **D-11 decision** → **G-16** offline model, if genuinely required.

---

## 12. New decisions raised by this unit

| ID | Decision |
|---|---|
| **D-20** | Is the checkpoint catalogue fixed at South / East / West, or must named district checkpoints be first-class (affects `CHECKPOINT_LOCATIONS`, analytics bucketing, scope matching and the branch model)? |
| **D-27** | What outcomes must an officer be able to record at a checkpoint (detain, refuse entry, refer to CID, release, false match, seize vehicle…), and what is the authorised post-flag procedure the system must support? |
| **D-28** | Must a checkpoint stop record the **vehicle** involved, linking to the vehicle registry? |
