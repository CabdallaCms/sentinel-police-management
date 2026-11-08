# Owner Decision Sheet — authorization remediation

**Date:** 5 November 2026 · **Status:** for decision · **Nothing implemented**
**Detail documents:** `AUTHORIZATION_REMEDIATION_PLAN.md` (rev 3) ·
`S16_REGISTER_VERIFICATION.md` · `SUSPECT_ALERT_OWNERSHIP.md` ·
`ENDPOINT_AUTHORIZATION_INVENTORY.md` · `SS1_STATION_SAFEGUARD_OPTIONS.md`

**State:** `server.py` sha256 `a8211f4f…b3b9fc` unmodified · suite 28 PASS / 0 FAIL / 1 BLOCKED ·
`origin/main` `a1c2478` · PR #23 untouched · **A-18 on hold**.

---

## 1. Suspect-alert ownership

### 1.1 Proposed structure (M-02 Phase A — additive only)

```sql
ALTER TABLE suspect_alerts
  ADD COLUMN IF NOT EXISTS branch_id INTEGER
      REFERENCES police_branches(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_suspect_alerts_branch ON suspect_alerts(branch_id);
```

No column is dropped, renamed or retyped. No existing row is deleted.

### 1.2 Ownership rules

| Rule | Statement |
|---|---|
| **R1** | An alert is owned by the **CID branch of the officer who created it**, written at `INSERT`. |
| **R2** | Ownership is **stored, never derived**. Not from `case_id` (nullable by design — standalone intelligence listings), not from the creator's current `users.branch` (mutable; an officer transfer would silently re-own their history). |
| **R3** | `branch_id IS NULL` ⇒ `INDETERMINATE` ⇒ **content refused**. Never "all branches". |
| **R4** | If the creator's own branch is unresolved, **creation is refused**. An alert cannot be created without an owner. |
| **R5** | Ownership does not change when the linked case is reassigned, closed or deleted. |

### 1.3 What a national checkpoint warning reveals

| Revealed to any screening officer, nationally | Restricted to the owning CID branch |
|---|---|
| **That** the person has an active Suspect alert | `alert_id` |
| `screening_result = 'Flagged match'` | `role` (Suspect / Witness / Person of interest) |
| `action_taken = 'Supervisor contacted'` | `origin` (Case Link / Direct Intelligence Listing) |
| *(optional — see D-1b)* the owning branch **name**, so the officer knows whom to call | `notes` — the free-text reason the person was listed |
| | `case_id`, case category, case status |
| | listing officer, creation time, full alert history |

**The warning is a boolean plus a routing hint. It carries no reason, no case and no narrative.**
This is already how the system behaves: `POST /api/checkpoint-events` runs
`SELECT 1 … LIMIT 1` and the checkpoint officer never holds the `cid` module.

---

## 2. National flag — operational consequences

### 2.1 What national visibility means in practice

A person listed in Buuhoodle is flagged when screened in Erigavo. **Branch-scoping the flag would
mean a suspect stops being flagged the moment they leave the listing region — i.e. precisely when
they are travelling.** That is why I am recommending *against* restricting it.

### 2.2 The costs, stated plainly

| Risk | Consequence today | Consequence after the fix |
|---|---|---|
| **False positive — wrong identity match** | The system matches on `national_id` / `passport_id` / four-part name. A shared or mistyped ID flags the wrong person at every checkpoint in the country. | **Unchanged.** This fix does not improve identity matching. |
| **Incorrect alert (listed in error)** | Flags nationally, permanently. | **Unchanged until M-02 lifecycle.** |
| **Withdrawal** | **Impossible. No endpoint exists.** `alert_status` is written once at `INSERT`. | **Still impossible after Phase A** — Phase A adds ownership, not lifecycle. |
| **Correction** | Impossible — no update path. | Still impossible until M-02 lifecycle. |
| **Over-restriction** | — | Guarded by test **T-45**: a checkpoint officer with no `cid` module must still receive `Flagged match` for an out-of-branch suspect. |

> **The most serious issue on this page is not an authorization defect.** A person wrongly listed
> is flagged at every checkpoint in the country, indefinitely, and **no one — not even an
> administrator — can clear it.** That is **S-03**. Scoping the *content* does not reduce that harm
> at all, because the harm is carried by the flag.

### 2.3 Decisions that are not mine to make

| # | Decision | Authority |
|---|---|---|
| **A-1** | Whether alert existence is visible nationally | **Police authority** — operational safety |
| **A-2** | Maximum alert lifetime before mandatory review (D-23.3 proposes 90 days, renewable) | **Legal** |
| **A-3** | Who may withdraw an alert, and whether withdrawal requires a supervisor rank that **does not exist** in the role model today | **Legal + police authority** |
| **A-4** | Whether a person may be told they are, or were, listed | **Legal** |
| **A-5** | Whether a disputed identity suspends the flag pending verification | **Police authority** |
| **A-6** | Whether the audit trail must be tamper-evident if alerts are used in proceedings (S-10 / D-04) | **Legal** |

**None of these is blocked by the authorization work, and the authorization work is not blocked by
them.** A-2…A-6 belong to the M-02 lifecycle and D-23.

---

## 3. Cross-branch CID access — A, B, C

**No option is assumed approved.** All three are live.

| | **A — Strict branch** | **B — National CID read role** | **C — Flag + request** |
|---|---|---|---|
| **Definition** | A CID officer reads alert content only for their own branch. Out-of-branch ⇒ `403`. | A new named role reads alert content in **every** branch. Ordinary CID officers remain branch-scoped. | Out-of-branch CID officers see that an alert **exists** and its **owning branch**, not its content, plus an audited "request access" action. |
| **Affected roles** | `ROLE_CID` only | `ROLE_CID` + a **new** role (role-model change) | `ROLE_CID` only |
| **Permitted operations** | Own branch: read/create/update. Other: none. | Holder: read **all** branches (read-only). Others as A. | Own branch: as A. Other: existence + branch name + request. |
| **Security consequence** | Smallest surface. Fail-closed by construction. | **Recreates today's exposure for whoever holds the role.** Its safety depends entirely on holder discipline — a process control, not a technical one. | Small surface; the request trail is itself useful evidence. |
| **Operational consequence** | A national investigation needs out-of-band phone calls. Rigid; may drive workarounds. | Investigations work smoothly. | Officer discovers the right branch instantly and asks. |
| **Cost** | **0 d** (falls out of SEC-0) | +0.5 d + role-model change | +1–1.5 d |

**Recommendation: A for Release 1.0, C as a 1.1 follow-up.**
A costs nothing and is the only option that is fail-closed by construction. C is the better
long-term design but should not delay a security fix. **B is the one I would advise against as a
default**: it rebuilds the current cross-branch exposure under a nicer name, and there is no
supervisor/seniority model in the system today to constrain who holds it.

**If operational feedback shows A is too rigid, C is the upgrade path — not B.**

---

## 4. M-02 Phase A — exact boundary

| **Phase A INCLUDES** | **Phase A EXCLUDES** |
|---|---|
| `branch_id` column + index (§1.1) | The six-state lifecycle (`Active`/`Suspended`/`Cleared`/`Withdrawn`/`Expired`/`Closed`) |
| Backfill of existing rows (§7) | Any state-transition endpoint |
| Writing `branch_id` on alert creation | **Withdraw** and **update** endpoints |
| Refusing creation when the creator's branch is unresolved (R4) | Automatic expiry / retention (**D-23.3**) |
| Branch-scoped **reads** of alert content | `status_reason`, `expires_at`, `reopened_from`, append-only history |
| Tests T-44, T-45, T-46 | A CID supervisor role |
| **1–1.5 d** | *(blocked on D-23 — legal)* |

### 4.1 Required for a safe Release 1.0

| Capability | Required? | Why |
|---|---|---|
| Alert content branch-scoped | **Yes** | Proven live cross-branch read (S-04) |
| Alert flag stays national | **Yes** | Removing it is a safety regression |
| Creation refused when owner unresolved | **Yes** | Otherwise NULL owners accumulate |
| Withdraw / correct an alert | **Not for 1.0** *(see below)* | Needs D-23 |
| Retention / expiry | **No** | Needs D-23 |

> **One caveat, recorded as a risk rather than a recommendation.** Shipping 1.0 with alerts that
> cannot be withdrawn means an erroneous national flag is permanent. The interim mitigation
> already on the books is **A-13 — an admin-only Withdraw, 2–3 d** — which needs no lifecycle and
> no new role. **I am not asking you to approve it here, but I would be wrong not to put it in
> front of you**, because the authorization fix makes alerts *more* correct without making them
> *correctable*.

---

## 5. SS-1 — all four options

Only **two** workflows call the fabricating resolver (measured — these are the only callers):
**crime incident registration** (`register_crime`, `:5294`) and **officer registration**
(`register_officer`, `:4828`).

| | **(i) G-a + G-c** | **(ii) all four guards** | **(iii) all four + operator message** | **(iv) G-c only — accept the risk** |
|---|---|---|---|---|
| **Crime registration vs `BR-7`** | **Blocked** (no phone / no `created_by`) | **Blocked** — *"station does not exist"* | **Blocked**, with the remedy named | **Still succeeds**; station fabricated |
| **Officer registration vs `BR-7`** | **Still succeeds — station still fabricated** | **Blocked** | **Blocked**, remedy named | **Still succeeds** |
| **Fabrication stopped?** | **No** — rows keep accumulating | Yes | Yes | No |
| **Decommissioned stations refused** | Yes | Yes | Yes | Yes |
| **Operator experience** | Crime desk blocked with a cause they cannot act on | Blocked; error names a code, not a remedy | Blocked; error names the administrator action | No change |
| **Effort** | 0.5–1 d | 1–2 d | 1–2 d | 0.25 d |

### 5.1 Why (iii)

1. **(i) is the worst of both.** It blocks the crime desk while leaving officer registration
   fabricating stations — half the measured blast radius untouched, and the junk rows keep coming.
2. **(ii) and (iii) cost the same.** The difference is one sentence of error text. The entire
   operational objection to G-b is "operators will be blocked and won't know why" — refusing to
   spend that sentence is indefensible.
3. **The integrity stake is permanent.** `register_crime()` stamps the station code into
   `CRM-<year>-<code>-NNNN`. A fabricated station puts an invented code into an **official file
   number that can never be corrected**.
4. **(iv) is coherent and I have kept it on the sheet.** If you judge the workflow disruption
   unacceptable for 1.0, (iv) is more honest than (i) pretending to be a fix — but it must then be
   recorded as **accepted risk with your signature**, not left open as though scheduled.

---

## 6. Remaining endpoint verification — executed

All four previously code-read items have now been run. **Measured results below; the
code-reading conclusion each one tested is noted beside it.** Every prediction was confirmed —
but they are now evidence, not inference.

### 6.1 MEASURED — `/documents` and `/audit-history`

Clearance application owned by **Buuhoodle** fingerprint; documents filed through the real intake:

```
user          /documents                      /audit-history
pb.fp.buu     200  4 items, 4 from clearance  200  2 events, 1 clearance   <- owning branch
pb.fp.eri     200  4 items, 4 from clearance  200  2 events, 1 clearance   <- OTHER BRANCH: LEAK
pb.cp.south   200  0 items, 0 from clearance  200  1 events, 0 clearance   <- module gate works
admin         200  4 items, 4 from clearance  200  2 events, 1 clearance
```

**S-16b confirmed on both endpoints.** An Erigavo fingerprint officer receives a Buuhoodle
application's **documents and audit events in full** — byte-identical to the owning officer. The
module gate is enforced (`pb.cp.south` gets nothing); **only branch is missing.** T-42 and T-43 are
no longer speculative.

### 6.2 MEASURED — unknown checkpoint location

```
POST /api/checkpoint-events  location="Atlantis Border Post"   -> HTTP 201 ACCEPTED
stored: location='atlantis'  location_code='atlantis'  checkpoint_location='atlantis Checkpoint'
CHECKPOINT_LOCATIONS = ('South','East','West')   valid? False
```

**Confirmed.** An unrecognised location is **not rejected**. It is lowercased to its first token
and **permanently stored** as though it were a checkpoint code. The register now contains a
location that does not exist, and any officer later scoped to `'atlantis'` would inherit it.

### 6.3 MEASURED — substring matching

Event seeded at location `Southwest`; officer scoped `South`:

```
user (scope)             /api/checkpoint-events      linked-records
pb.cp.south (South)      200 SEES Southwest          200 SEES      <-- SUBSTRING LEAK
pb.cp.swest (Southwest)  200 SEES Southwest          200 SEES
```

**Confirmed.** `checkpoint_scope_sql` ends with `ILIKE '%south%'`, so **`South` matches
`Southwest`** on both the register and the person endpoint. A South-scoped officer reads another
checkpoint's traffic.

### 6.4 Evidence status — complete inventory

| Item | Status |
|---|---|
| S-16a, all four registers | **MEASURED** |
| S-16b `/linked-records` | **MEASURED** |
| S-16b `/documents`, `/audit-history` | **MEASURED** (§6.1) |
| H-2b checkpoint branch | **MEASURED** |
| Checkpoint unknown location | **MEASURED** (§6.2) |
| Checkpoint substring | **MEASURED** (§6.3) |
| S-14 branch fail-open | **MEASURED** (P1–P5) |
| S-04 alert cross-branch read | **MEASURED** |
| **S-15** `/api/crimes` unit-type mismatch | **CODE-READ + schema only — the single remaining unmeasured finding** |

> **One finding is still inference: S-15.** It is derived from the branch-id disjunction
> (`/api/crimes` scopes on `police_station` ids 5/10/15; `register_crime` stores `crime` ids
> 2/7/12) and from the absence of any write-scope call. I have not executed it. It currently fails
> *closed*, which is why it has been lower priority — but **it is the last claim in this package
> resting on code reading**, and I will probe it before implementation unless you want it sooner.

---

## 7. Migration safety

### 7.1 How existing alerts get ownership

| Source | Rule | Result |
|---|---|---|
| Alert **with** a case whose `crime_cases.branch_id` is set | `branch_id := crime_cases.branch_id` | Resolved automatically |
| Alert **with** a case whose `branch_id` is NULL | cannot resolve | **NULL — worklist** |
| Alert with **no case** (standalone listing) | cannot resolve | **NULL — worklist** |

**Per R-1 there is no production database.** The only alerts that exist are demo seed rows. **The
backfill worklist is expected to be empty or near-empty, and this is the cheapest moment this
change will ever be made.** The procedure below exists because that will not be true later.

### 7.2 NULL and ambiguous ownership

1. **Fail closed.** `branch_id IS NULL` ⇒ `INDETERMINATE` ⇒ content refused (**T-46**). Never
   "all branches" — that is the S-14 mistake this whole package exists to remove.
2. **The flag is unaffected.** An unowned alert **still flags nationally at checkpoints**, because
   the flag is not branch-scoped. **No safety function is lost while ownership is being
   classified** — only CID content visibility is withheld.
3. **Worklist, not a default.** Unresolved rows are listed for manual classification by a CID
   administrator. **Never defaulted to a branch**; a wrong owner is worse than no owner, because it
   grants access rather than withholding it.
4. **Staging first.** Classification is completed and verified in staging (phases R-C/R-D) before
   enforcement reaches production — consistent with your ruling that there is no report-only
   production phase.

### 7.3 Rollback

Two **independent** levers, in strict order:

| Lever | Action | Effect | Data loss |
|---|---|---|---|
| **1. Code** | Revert the SEC-1 enforcement commit | Alert reads return to current (unscoped) behaviour; column stays, keeps being populated | **None** |
| **2. Schema** | `ALTER TABLE suspect_alerts DROP COLUMN branch_id;` | Returns the table to its present shape | **Ownership assignments are lost** |

**Rules:** lever 1 may be used alone, at any time, with no data loss — it is the real rollback.
Lever 2 **must never be used while enforcement is live** (every alert would become
`INDETERMINATE` and all content would vanish from CID screens). Always revert code first, then
schema, and only if the column itself is being abandoned.

**Phase A is additive**, so lever 2 is a true inverse: no column is dropped, renamed or retyped on
the way in, and nothing outside `suspect_alerts` is touched.

---

## 8. Decisions requested

| # | Decision | Options | My recommendation |
|---|---|---|---|
| **D-1a** | Alert ownership = creating CID branch, stored explicitly (R1–R5) | approve / reject | **Approve** |
| **D-1b** | Does the national warning also reveal the **owning branch name** (routing hint)? | yes / no | **Yes** — low sensitivity, high operational value |
| **D-2** | Alert **flag** stays national | keep national / branch-scope it | **Keep national** — scoping it is a safety regression |
| **D-3** | Cross-branch CID access | **A** / **B** / **C** | **A** for 1.0, **C** for 1.1. Advise against B |
| **D-4** | M-02 **Phase A** approved as a Release 1.0 dependency (§4) | approve / defer | **Approve** — 1–1.5 d |
| **D-4b** | **A-13** interim admin-only Withdraw (2–3 d) | approve / defer / reject | *Your call* — flagged because 1.0 otherwise ships permanent, uncorrectable flags |
| **D-5** | SS-1 | **(i)** / **(ii)** / **(iii)** / **(iv)** | **(iii)** |
| **D-6** | Probe **S-15** before implementation (the last code-read finding) | yes / proceed without | **Yes** |
| **D-7** | Migration safety procedure §7 (worklist, fail-closed NULL, two-lever rollback) | approve / amend | **Approve** |

**Totals if D-1a, D-2, D-3=A, D-4, D-5=(iii), D-7 are approved:**
authorization **11–17.5 d** · P0 **7–9.5 d** · SS-1 **1–2 d** ⇒ **19–29 d before Release 1.0**.
Add **2–3 d** if D-4b (A-13) is approved.

**A-18 remains on hold.** Nothing will be implemented, no schema changed, nothing merged or
deployed until you record these decisions.
