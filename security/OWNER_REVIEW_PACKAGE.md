# Consolidated Owner-Review Package — investigation closed, implementation unauthorized

**Date:** 5 November 2026 · **Commit:** see §6 · **Status:** for owner decision
**Investigation phase: CLOSED.** Every finding below is execution-tested unless explicitly marked.
**Nothing is implemented. No schema, migration, initialization or production configuration changed.**

| Document | Purpose |
|---|---|
| **THIS DOCUMENT** | The consolidated package: findings, decisions, dependencies, blockers, gates |
| `SECURITY_ISSUE_REGISTER.md` | Canonical per-finding register (S-01…S-19) |
| `AUTHORIZATION_REMEDIATION_PLAN.md` (rev 3) | Full remediation design |
| `S15_EXECUTION_VERIFICATION.md` · `S16_REGISTER_VERIFICATION.md` | Execution evidence |
| `OWNER_DECISION_SHEET_AUTHORIZATION.md` (`e8f6a44`) | Source of the nine decisions |
| `SUSPECT_ALERT_OWNERSHIP.md` · `SS1_STATION_SAFEGUARD_OPTIONS.md` · `ENDPOINT_AUTHORIZATION_INVENTORY.md` | Supporting analysis |

---

# 1. Reconciled findings inventory

## 1.1 Authorization defect class — all execution-tested

| ID | Severity | Defect | Affected endpoints | Affected roles | Evidence | Release impact |
|---|---|---|---|---|---|---|
| **S-14** | **Critical** | Branch scope **fails open**: `branch_scope_view()` returns `None` for both "unrestricted" and "cannot resolve"; every call site reads falsy as *allow* | `/api/clearance-applications` (list, id, POST), `/api/airport-records`, `/api/crime-cases`, `/api/crimes` | **Any** scoped unit officer whose `users.branch` does not resolve — Fingerprint, Airport, CID, Checkpoint | `BRANCH_SCOPE_FAIL_OPEN.md` P1–P5; re-confirmed `S15_EXECUTION_VERIFICATION.md` §3 | **BLOCKS 1.0** |
| **S-15** | **High** | `/api/crimes` scopes on `police_station` branch ids while `register_crime()` stores a `crime` branch id — disjoint sets | `GET /api/crimes` | CID / `crimes` module holders | `S15_EXECUTION_VERIFICATION.md` §2, §3, §7 | **BLOCKS 1.0** + **gates A-18** |
| **S-16a** | **Critical** | `GET /api/persons/<id>` attaches four unit registers with **no module, branch or location filter**. **No precondition** | `GET /api/persons/<id>` | **Every authenticated role** | `S16_REGISTER_VERIFICATION.md` §2–§5 (4/4 registers, 27 leak combinations) | **BLOCKS 1.0** |
| **S-16b** | **High** | `/linked-records`, `/documents`, `/audit-history` apply module + checkpoint-location filters but **never branch** | `/api/persons/<id>/linked-records`, `/documents`, `/audit-history` | Fingerprint, Airport, CID, Checkpoint | `S16_REGISTER_VERIFICATION.md` §2–§3; `OWNER_DECISION_SHEET_AUTHORIZATION.md` §6.1 | **BLOCKS 1.0** |
| **H-2b** | **High** | Checkpoint scope: **(a)** no branch filter anywhere, **(b)** unrecognised locations accepted and stored, **(c)** `South` matches `Southwest` by substring | `GET`/`POST /api/checkpoint-events`; location half of the person endpoints | Checkpoint officers (all locations) | `S16_REGISTER_VERIFICATION.md` §5; `OWNER_DECISION_SHEET_AUTHORIZATION.md` §6.2, §6.3 | **BLOCKS 1.0** |
| **S-04** | **High** *(raised from Medium)* | `suspect_alerts` has **no branch column and no branch filter anywhere** — not even on its own endpoint | `GET`/`POST /api/suspect-alerts`; `alerts[]` on the person endpoints | CID officers, all branches | `S16_REGISTER_VERIFICATION.md` §4 | **BLOCKS 1.0** — needs schema change |
| **S-17** | **High** | `crime_incidents.branch_id` **accepts NULL** from the API (`resolve_branch` called without `required=True`). The record is then invisible to every scoped officer and visible to every unscoped one, permanently | `POST /api/crimes` | CID / `crimes` module holders | `S15_EXECUTION_VERIFICATION.md` §4, §5 | **BLOCKS 1.0** |
| **S-18** | **High** | Cross-branch **and** cross-region crime filing accepted from a scoped account. `register_crime()` has **no `require_branch_write_scope()` call at all** | `POST /api/crimes` | CID / `crimes` module holders | `S15_EXECUTION_VERIFICATION.md` §4 | **BLOCKS 1.0** |
| **S-19** | **Medium** | Crime file numbers encode the **station region**, not the filing branch — `CRM-2026-SAN-C-01-0006` minted by a Buuhoodle-posted officer | `POST /api/crimes` → `new_crime_file_number()` | CID / `crimes` | `S15_EXECUTION_VERIFICATION.md` §4, §5 | **Not blocking** — record-integrity; overlaps SS-1 |

### 1.1.1 The four newly execution-tested items, itemised

| Item | Previously | Measured result | Evidence |
|---|---|---|---|
| `/api/persons/<id>/documents` | code-read | An **Erigavo** fingerprint officer receives a **Buuhoodle** application's **4 documents** — identical to the owning officer. A checkpoint officer correctly receives **0** | Decision sheet §6.1 |
| `/api/persons/<id>/audit-history` | code-read | Same officer receives the **clearance audit events** in full; checkpoint officer receives **0** | Decision sheet §6.1 |
| Checkpoint unknown location | code-read | `POST` with `"Atlantis Border Post"` → **HTTP 201**, stored permanently as `location_code='atlantis'` — not a valid checkpoint | Decision sheet §6.2 |
| Checkpoint substring | code-read | Officer scoped `South` **reads a `Southwest` event** on both the register and the person endpoint | Decision sheet §6.3 |

**In all four the module gate held and only the intended dimension failed** — which is why the
remediation is one model, not four patches.

## 1.2 Carried findings — not re-investigated this round, still open

| ID | Severity | Defect | Release impact |
|---|---|---|---|
| **S-01** | High | Cross-branch document access — any authenticated officer can read any uploaded file | **BLOCKS** — needs migration **M-01** |
| **S-02** | High | Admin password reset does not revoke the target's sessions (H-5) | **BLOCKS** — P0-WP-2 |
| **S-03** | High | **Suspect alerts can never be cleared.** No update or withdraw endpoint exists | **BLOCKS** — needs M-02 lifecycle + **D-23** |
| **S-05** | Medium | Analytics RBAC leak — `crimes` acts as a skeleton key | Should fix; **not itself a gate** |
| **S-06** | — | Reduced by **R-1** (no operational database ever existed). Residual is S-12/S-13 | Reduced |
| **S-07** | High *(operational)* | N-7 — closing a disciplinary action is impossible; a suspended officer can never return to Active duty | **BLOCKS** — P0-WP-1 |
| **S-08** | High | No session expiry (H-3) | **BLOCKS** — needs A-14 |
| **S-09** | High | No authentication throttling or auth audit (H-4) | **BLOCKS** — needs A-15 |
| **S-10** | High | Mutable audit log (H-7) | **BLOCKS** — needs **D-04** |
| **S-11** | High | No TLS (H-8) | **BLOCKS** — deployment decision |
| **S-12** | High | One environment variable gives all nine seeded accounts the same password | **BLOCKS first production install** |
| **S-13** | High | First run seeds demonstration data (3 fictional persons, 2 cases, 1 application, 1 checkpoint event) into any empty database | **BLOCKS first production install** |

**Totals: 19 security findings + H-2b. 17 are release-blocking. 9 are execution-tested this round.**

---

# 2. The nine owner decisions

Reproduced from `OWNER_DECISION_SHEET_AUTHORIZATION.md` (`e8f6a44`) with consequences stated in
full. **No decision is taken on your behalf.**

> **D-6 has been answered by execution since that sheet was written.** It is retained below for
> completeness and marked **CLOSED**. **Eight decisions remain open.**

---

### D-1a — Alert ownership model

**Question:** Is an alert owned by the **CID branch of the officer who created it**, stored
explicitly on the row (rules R1–R5), rather than derived?

| Option | Consequence |
|---|---|
| **Approve** | `suspect_alerts.branch_id` written at INSERT. Ownership stable across case reassignment, case deletion and officer transfer |
| **Reject** | Either no ownership (status quo — proven cross-branch read) or ownership derived from `crime_cases.branch_id`, which **fails for standalone alerts** (`case_id` is nullable *by design*) and is unstable (`ON DELETE SET NULL`) |

* **Technical:** additive column + index. Derivation alternatives were tested against the schema and rejected (§2.2 of `SUSPECT_ALERT_OWNERSHIP.md`).
* **Security:** without it, S-04 cannot be closed — there is nothing to filter on.
* **Operational/legal:** none directly; makes "which unit listed this person" answerable, which matters to any later complaint.
* **Dependencies:** enables M-02 Phase A and the alert half of SEC-1.
* **Blocks 1.0:** **Yes** — S-04 is release-blocking.
* **Recommendation:** **Approve.**

---

### D-1b — Does the national warning reveal the owning branch name?

**Question:** When a checkpoint officer gets `Flagged match`, do they also see **which branch**
listed the person?

| Option | Consequence |
|---|---|
| **Yes** | Officer knows whom to contact. Reveals one additional fact: that *some* unit in a named branch has an interest |
| **No** | Officer sees only "flagged — contact supervisor" and must escalate blindly |

* **Technical:** one extra field on the screening response.
* **Security:** marginal. Discloses the listing branch, not the reason, case or narrative.
* **Operational:** materially faster escalation; without it `action_taken='Supervisor contacted'` has no routing target.
* **Dependencies:** D-1a.
* **Blocks 1.0:** No — either answer ships.
* **Recommendation:** **Yes.**

---

### D-2 — Does the alert flag stay national?

**Question:** Does *alert existence* remain visible to every screening officer nationally, with
only the *content* branch-scoped?

| Option | Consequence |
|---|---|
| **Keep national** | A suspect listed in Buuhoodle is flagged when screened in Erigavo. Matches existing behaviour (`server.py:9597`), which checkpoint intake already depends on |
| **Branch-scope the flag** | A suspect stops being flagged the moment they leave the listing region — i.e. **precisely when they are travelling** |

* **Technical:** keeping it national is the status quo; scoping it would require changing the checkpoint intake path.
* **Security:** national visibility reveals one boolean to officers performing a lawful screening. Scoping it does **not** reduce the harm of a wrong alert, because the harm rides on the flag.
* **Operational/legal:** **this is a safety judgement, not a technical one.** Reserved to **police authority** (A-1 in the decision sheet).
* **Dependencies:** guarded by test **T-45** so the fix cannot over-restrict.
* **Blocks 1.0:** **Yes** — SEC-1 cannot be specified without the answer.
* **Recommendation:** **Keep national.** Scoping it is a safety regression.

---

### D-3 — Cross-branch CID access

**Question:** What happens when a CID officer needs an alert owned by another branch?

| | **A — Strict branch** | **B — National CID read role** | **C — Flag + request** |
|---|---|---|---|
| **Definition** | Out-of-branch ⇒ `403`. Content never leaves the owning branch | A new named role reads alert **content in every branch**, read-only. Ordinary CID stays scoped | Out-of-branch officer sees that an alert **exists** and its **owning branch**, not its content, plus an audited "request access" action |
| **Affected roles** | `ROLE_CID` | `ROLE_CID` + a **new role** (role-model change) | `ROLE_CID` |
| **Permitted ops** | Own branch: read/create/update. Other: none | Holder: read all branches. Others as A | Own branch as A; other: existence + branch name + request |
| **Security** | Smallest surface; fail-closed by construction | **Recreates today's exposure for whoever holds the role.** Safety depends entirely on holder discipline — a process control, not a technical one | Small surface; the request trail is itself evidence |
| **Operational** | National investigations need out-of-band calls. Rigid; may drive workarounds | Investigations flow smoothly | Officer finds the right branch instantly and asks |
| **Cost** | **0 d** | +0.5 d + role-model change | +1–1.5 d |

* **Dependencies:** D-1a. B additionally requires a role-model change and an owner ruling on who holds it.
* **Blocks 1.0:** **Yes** — determines SEC-1's refusal behaviour.
* **Recommendation:** **A for 1.0, C as a 1.1 follow-up.** **I advise against B as a default** — it rebuilds the current cross-branch exposure under a nicer name, and there is no seniority model to constrain the holder list. **A is not assumed approved.**

---

### D-4 — M-02 Phase A as a Release 1.0 dependency

**Question:** Approve the additive `suspect_alerts.branch_id` migration (ownership only) as a 1.0
dependency?

| Option | Consequence |
|---|---|
| **Approve** | 1–1.5 d. S-04 becomes closable. Backfill is near-free now (**R-1**: no production database) |
| **Defer** | S-04 stays open and **release-blocking**; the cost rises permanently once real alerts exist |

* **Phase A includes:** the column + index, backfill, writing `branch_id` on creation, refusing creation when the creator's branch is unresolved, branch-scoped **reads**, tests T-44/T-45/T-46.
* **Phase A excludes:** the six-state lifecycle, any transition endpoint, **withdraw and update**, automatic expiry/retention, `status_reason`/`expires_at`/`reopened_from`, a CID supervisor role.
* **Technical:** additive, nullable, reversible (§3.5).
* **Security:** NULL must mean `INDETERMINATE` (refuse), never "all".
* **Operational/legal:** none in Phase A; the excluded items need **D-23**.
* **Dependencies:** D-1a, D-2, D-3; feeds SEC-1.
* **Blocks 1.0:** **Yes.**
* **Recommendation:** **Approve.**

---

### D-4b — A-13 interim admin-only Withdraw

**Question:** Approve an interim administrator-only alert withdrawal (2–3 d), ahead of the full
lifecycle?

| Option | Consequence |
|---|---|
| **Approve** | An erroneous national flag can be removed by an administrator. No new role, no lifecycle |
| **Defer / reject** | **1.0 ships alerts that are correctly scoped but permanently uncorrectable.** A wrongly listed person is flagged at every checkpoint in the country, indefinitely, and nobody — including an administrator — can clear it |

* **Technical:** one new endpoint + audit; no schema change beyond Phase A.
* **Security:** adds a privileged write path that must itself be audited and branch-aware.
* **Operational/legal:** **who may withdraw, and whether withdrawal requires a rank that does not exist in the role model, is reserved to legal + police authority** (A-3). A-2 (retention) and A-4 (notifying the person) are also legal.
* **Dependencies:** D-4.
* **Blocks 1.0:** **No** — but S-03 remains open and release-blocking either way.
* **Recommendation:** **Your call.** I have flagged it because the authorization fix makes alerts *more correct* without making them *correctable*.

---

### D-5 — SS-1 station safeguards

**Question:** Which station-creation safeguards are approved? Only **two** workflows call the
fabricating resolver: **crime incident registration** (`:5294`) and **officer registration**
(`:4828`).

| | **(i) G-a + G-c** | **(ii) all four guards** | **(iii) all four + operator message** | **(iv) G-c only — accept the risk** |
|---|---|---|---|---|
| **Crime registration vs `BR-7`** | **Blocked** (no phone / no `created_by`) | **Blocked** — *"station does not exist"* | **Blocked**, remedy named | **Still succeeds**; station fabricated |
| **Officer registration vs `BR-7`** | **Still succeeds — station still fabricated** | **Blocked** | **Blocked**, remedy named | **Still succeeds** |
| **Fabrication stopped?** | **No** | Yes | Yes | No |
| **Decommissioned stations refused** | Yes | Yes | Yes | Yes |
| **Operator experience** | Crime desk blocked with a cause they cannot act on | Blocked; error names a code, not a remedy | Blocked; error names the administrator action | No change |
| **Effort** | 0.5–1 d | 1–2 d | 1–2 d | 0.25 d |

* **Technical:** no schema change; no existing record altered; independently revertible.
* **Security:** `register_crime()` stamps the station code permanently into `CRM-<year>-<code>-NNNN`. A fabricated station puts an invented code into an **official file number that can never be corrected**. This is also the mechanism behind **S-19**.
* **Operational:** (ii)/(iii) convert a currently-working action into a blocking error requiring a System Administrator. **That is a real workflow change and the judgement is yours.**
* **Dependencies:** none — independent of SEC-0…SEC-5 in both directions.
* **Blocks 1.0:** **No** — optional package.
* **Recommendation:** **(iii).** (i) leaves half the measured blast radius untouched; (ii) and (iii) cost the same and differ by one sentence of error text. If you judge the disruption unacceptable, **(iv) is more honest than (i)** but must be recorded as **accepted risk with your signature**.

---

### D-6 — Probe S-15 before implementation — **CLOSED**

**Question:** Probe S-15 before implementation?
**Outcome:** **Executed** (`0dc584f`). Scenarios A–E complete. S-15 confirmed; **S-17, S-18 and
S-19 discovered**; the A-18 blocker proven (posted officers went from **0 rows to 8**). **Every
finding in the authorization package is now execution-tested; none rests on code reading.**
**No decision required.**

---

### D-7 — Migration safety procedure

**Question:** Approve the backfill, NULL handling and rollback procedure?

| Option | Consequence |
|---|---|
| **Approve** | Backfill from `crime_cases.branch_id` where resolvable; unresolved rows go to a **worklist**, never defaulted; NULL fails closed; two-lever rollback |
| **Amend** | Specify the change |

* **Technical:** see §3.5 for the full rollback matrix.
* **Security:** **a wrong owner is worse than no owner** — it grants access rather than withholding it. Hence worklist, not defaults.
* **Operational:** **the flag keeps working while classification is pending**, so no safety function is lost. Classification completes in **staging** before enforcement reaches production.
* **Dependencies:** D-4.
* **Blocks 1.0:** **Yes** — M-02 Phase A cannot proceed without an agreed procedure.
* **Recommendation:** **Approve.**

---

### 2.1 Decision summary

| # | Open? | Blocks 1.0 | My recommendation |
|---|---|---|---|
| D-1a | **Open** | Yes | Approve |
| D-1b | **Open** | No | Yes |
| D-2 | **Open** | Yes | Keep national |
| D-3 | **Open** | Yes | A now, C at 1.1; advise against B |
| D-4 | **Open** | Yes | Approve |
| D-4b | **Open** | No | Your call |
| D-5 | **Open** | No | (iii) |
| D-6 | **CLOSED** | — | answered by execution |
| D-7 | **Open** | Yes | Approve |

---

# 3. Implementation dependency sequence

## 3.1 The sequence

```
SEC-0  consolidated authorization model  (built ONCE)
  │
  ├── SEC-2  S-14   branch call sites
  │     │
  │     └── SEC-3  S-15 + S-17 + S-18   read fix AND crime write guard — ONE package
  │
  ├── SEC-4  H-2b   checkpoint: branch filter, location validation, exact matching
  │
  └── M-02 Phase A  suspect_alerts.branch_id
          │
          └── SEC-1  S-16a + S-16b + alert reads   (LAST — needs SEC-4 and M-02-A)
                  │
                  └── SEC-5  staging diagnostics (R-C/R-D)
                          │
                          └── A-18  (additionally gated by PRE-3)

SS-1  station safeguards — INDEPENDENT, optional, no dependency either way
```

## 3.2 Why SEC-0 → SEC-2 → SEC-3 + write guard must ship together

**Measured, not argued:**

1. **SEC-3 alone leaves unresolved postings unrestricted.** In scenario B, `s15.unres` and
   `s15.empty` returned `branch_scope=None` and **1 of 1 rows — indistinguishable from the
   administrator**. Correcting which `unit_type` feeds the filter does not touch
   `branch_scope_view()`. **Without SEC-2, a typo in a posting still grants national visibility.**
2. **SEC-2 alone cannot fix `/api/crimes`.** Even with a correct three-state resolver, the endpoint
   would resolve a *`police_station`* branch id and compare it to a stored *`crime`* branch id.
   Scenario A measured this: both correctly posted officers saw **0 of 1**, including their own
   branch's record. **S-14 and S-15 are two different bugs on the same line.**
3. **The read fix without the write guard makes things worse.** Scenario C: a Buuhoodle-scoped
   officer filed under Erigavo branch 12 and got **201**. Once reads are correctly scoped, that
   officer would **lose sight of the record they just created** — a functional regression layered
   on a security hole.
4. **SEC-0 supplies the only thing that distinguishes the two meanings of `None`.** Without the
   three-state model, every fix re-creates the fail-open in a new place.

**Therefore SEC-0, SEC-2 and SEC-3-with-write-guard are one release unit.** Shipping any subset
leaves a measured hole.

## 3.3 How S-17, S-18 and S-19 are resolved

| Finding | Resolution | Package | Extra cost |
|---|---|---|---|
| **S-17** NULL branch accepted | `register_crime()` calls `resolve_branch(..., 'crime', required=True)`; `scope_clause()` treats NULL ownership as `INDETERMINATE` (refuse), never "all". Existing NULL rows go to the §3.5 worklist | **SEC-3** | none |
| **S-18** cross-branch/region write | `register_crime()` calls `require_branch_write_scope(c, user, branch, 'crime')` — the same guard airport (`:9215`) and checkpoint (`:9511`) already use. A scoped officer is **pinned** to their own branch; omission adopts it; mismatch ⇒ **403** | **SEC-3** | none |
| **S-19** station-derived file numbers | **Not a code fix on its own.** Two parts: (a) **SS-1 option (ii)/(iii)** stops fabricated stations entering the numbering at all; (b) whether the file number should encode the **branch** instead of the station is a **records-policy decision for you**, not an engineering one | **SS-1** + owner view | SS-1 only |

**None of the three changes the estimates.** All sit inside SEC-3's existing 1–2 d, except S-19's
policy half.

## 3.4 How station removal is prevented from widening access

**The measured failure (scenario D):** deleting the three `police_station` branch rows moved both
posted officers from **0 rows → 8 (all)**, because `user_branch_scope(user,'police_station')`
stopped resolving and the `WHERE` clause vanished.

Three independent defences, in order:

| # | Defence | Effect |
|---|---|---|
| **1** | **SEC-3 removes the dependency entirely.** `/api/crimes` resolves a **`crime`** branch, so `police_station` rows are irrelevant to crime visibility | The scenario-D trigger ceases to exist |
| **2** | **SEC-0 makes unresolvable ⇒ `INDETERMINATE` ⇒ refuse.** Even if some future endpoint loses its branch rows, the result is **403, never "all"** | Fail-closed by construction |
| **3** | **Ordering gate.** A-18 runs only after SEC-2, SEC-3 and SEC-5, and additionally after **PRE-3** | Removal cannot happen before the defences exist |

**Test T-26 pins this permanently:** with **zero** station branch rows a scoped officer must receive
a scoped result or `403` — **never the full register**. It must be seen to fail against the
pre-fix build.

> **Register correction:** `SECURITY_ISSUE_REGISTER.md` §6 previously read *"SEC-1 → SEC-2 → SEC-3
> → A-18"*. That ordering is stale — SEC-1 moved last in revision 3. Corrected to
> **SEC-0 → SEC-2 → SEC-3 → A-18** in this package and in the register.

## 3.5 How existing station records remain protected

| Guarantee | Mechanism |
|---|---|
| **No station row is deleted, renamed or retyped** by any SEC package | SEC-0…SEC-5 are read-path and write-guard changes only |
| **A-18 does not touch `police_stations`** | A-18 is `police_branches` only; the station list, tiers and cell capacities were **withdrawn** from your approval in `4cc3067` and remain **HQ responsibility, outside CID scope** |
| **No DELETE path exists for stations in the application** | Confirmed by code search — there is no station delete route |
| **Scenario D's deletions were disposable** | Executed inside a temporary pgserver cluster, destroyed at exit. **No real station record was modified at any point** |
| **SS-1 alters nothing already stored** | It changes only what happens on the *next* intake |
| **Three FKs stay intact** | `officers.station_id` (NOT NULL), `crime_incidents.station_id` (NOT NULL), `officer_conduct_actions.station_id` (nullable) |

## 3.6 How branch ownership is validated on reads and writes

**One model, both directions — this is the core of SEC-0.**

| Direction | Mechanism | Behaviour |
|---|---|---|
| **Read** | `scope_clause(decision, column)` | `UNRESTRICTED` ⇒ `('', ())` no clause · `GRANTED` ⇒ `(' AND col=%s', (v,))` · `INDETERMINATE` ⇒ **never reaches SQL** — `enforce()` has already raised. **Two branches, no `else: return '',()`** |
| **Write** | `require_branch_write_scope(c, user, branch_row, unit_type)` | Scoped officer **pinned** to their own branch; omitted branch **adopts** it; mismatch ⇒ **403**. Applied to `register_crime()` for the first time (S-18) |
| **Both** | `authorize(c, user, *, module, unit_type, location)` returns `AccessDecision(state, value, reason)` | `UNRESTRICTED` is reachable **only** by an explicit privilege grant. **Test T-10** is a property test asserting no input combination yields `UNRESTRICTED` otherwise |
| **Record ownership** | Written at INSERT, never derived | Crime: `required=True` (S-17). Alerts: creator's CID branch (D-1a) |

**The invariant:** a record's owning branch is written once at creation and compared on every read.
"Cannot determine" is a distinct third state that always refuses.

---

# 4. Remaining Release 1.0 blockers — complete

## 4.1 Security

| ID | Blocker | Package | Days |
|---|---|---|---|
| S-16a, S-16b | Person-endpoint leaks | SEC-1 | *(in SEC band)* |
| S-14 | Branch fail-open | SEC-2 | |
| S-15, S-17, S-18 | Crime read + write | SEC-3 | |
| H-2b | Checkpoint scope | SEC-4 | |
| S-04 | Alert ownership | M-02-A + SEC-1 | |
| | **SEC band total (SEC-0…SEC-5 + M-02-A)** | | **11–17.5** |
| S-07 | N-7 discipline closure | P0-WP-1 | 1.5 |
| S-02 | Session revocation on reset | P0-WP-2 | 1.5–2 |
| S-01 | Cross-branch documents | **M-01** (unapproved) | *in P1* |
| S-03 | Alerts cannot be cleared | M-02 lifecycle (**D-23**) | *in P1/P2* |
| S-08 | No session expiry | A-14 | *in P1* |
| S-09 | No auth throttling / audit | A-15 | *in P1* |
| S-10 | Mutable audit log | **D-04** | *in P2* |
| S-11 | No TLS | deployment decision | *in P2* |
| S-05 | Analytics leak | A-12 | not a gate |
| **S-19** | Station-derived file numbers | SS-1 + owner view | not a gate |

## 4.2 Operational

| Gate | Requirement | Authority |
|---|---|---|
| **PRE-1** | Register ≥ 1 real police station (name, tier, region, district, **contact phone**) | **HQ / System Administrator** |
| **PRE-2** | Register ≥ 1 officer per crime-desk station (multipart, photo + primary document) | **HR Directorate** |
| **PRE-4** | Correct every invalid `users.branch` assignment so postings resolve | Administrators, in **staging** (SEC-5) |
| **PRE-5** | Confirm station codes with HQ **before first use** — they are permanent in file numbers | **HQ** |
| **SS-1** | Station-safeguard option (D-5) | Owner |

## 4.3 Migration

| ID | Migration | Status |
|---|---|---|
| **M-02 Phase A** | `suspect_alerts.branch_id` — additive | **Awaiting D-4** |
| **M-01** | `documents` table + per-file ownership (S-01) | **Unapproved.** §7 Phase B1 (report-only / serve-anyway) **PROHIBITED for production** by your ruling |
| **M-02 lifecycle** | Six states, transitions, history | **Blocked on D-23** |

## 4.4 Production initialization

| ID | Item | Status |
|---|---|---|
| **A-16 / A-16a** | Demo seeding behind `SENTINEL_SEED_DEMO_DATA`, default **off**; strict-mode validation + contamination refusal | Approved in principle, **not implemented** |
| **A-17** | Production init creates **only** the administrator account | Same |
| **A-19** | Retain `SENTINEL_BOOTSTRAP_PASSWORD` with a warning | Same |
| **A-18** | **9 branch rows** (fingerprint / crime / checkpoint × 3 locations) | **ON HOLD** — gated by SEC-2, SEC-3 and **PRE-3** |
| **PRE-3** | Confirm the three CID branch names and placements, or replace them with the real list | **CID deployment authority.** `DEFAULT_POLICE_BRANCHES` has **no provenance and is NOT approved production data** |
| **S-12 / S-13** | Shared bootstrap password; demo data in any empty database | **BLOCKS first production install** — P0-WP-3 |

## 4.5 Legal / policy

| ID | Question | Authority |
|---|---|---|
| **D-23** (D-23.1–23.7) | Suspect-alert legal framework; **D-23.3 — 90-day renewable lifetime — critical** | **Legal** |
| **A-2** | Maximum alert lifetime before mandatory review | Legal |
| **A-3** | Who may withdraw; whether a supervisor rank (which does not exist today) is required | Legal + police authority |
| **A-4** | Whether a person may be told they are, or were, listed | Legal |
| **A-1** | Whether alert existence is visible nationally (**= D-2**) | **Police authority** |
| **A-5** | Whether a disputed identity suspends the flag pending verification | Police authority |
| **A-6 / D-04** | Whether the audit store must be tamper-evident if alerts are used in proceedings | Legal |
| **Date conflict** | Six documents read 5 Nov 2026, thirteen read 7 Nov; the sandbox clock reads 8 Nov. **Not silently reconciled** — needs your ruling | Owner |

---

# 5. Implementation and testing gates

> **Scope note.** "Automated" and "manual" below are **implementation-side verification performed
> by me before handing a package over**. They are **not** your acceptance testing — that is §5.8,
> and it happens on your environment, after handover, against your own criteria.

### 5.1 SEC-0 — consolidated authorization model · 2–3 d

| | |
|---|---|
| **Files** | `backend/server.py` (new helpers; `branch_scope_view`, `user_branch_scope`, `require_record_branch_scope`, `require_branch_write_scope`, `checkpoint_scope`, `checkpoint_scope_sql`, `require_module` wrapped/replaced) |
| **Tables** | **None** |
| **Migration** | **None** |
| **Automated** | `test_authorization_model.py` T-01…T-10, incl. **T-10 property test** (no input yields `UNRESTRICTED` without an explicit grant) |
| **Manual** | Confirm `posting_scope_status()` stays display-only and can never raise |
| **Rollback** | Single code revert; no data touched |
| **Acceptance** | Three states exist and are distinct; `scope_clause()` has exactly two branches and **no** `else: return '',()`; T-01…T-10 green; each seen to fail pre-fix |

### 5.2 SEC-2 — S-14 branch call sites · 2–3 d

| | |
|---|---|
| **Files** | `backend/server.py` — 12 enforcing call sites |
| **Tables** | None · **Migration** None |
| **Automated** | `test_branch_scope_enforcement.py` T-11…T-22 (list, direct-ID, write; deny **and** allow) |
| **Manual** | Re-run the P1–P5 scenarios from `BRANCH_SCOPE_FAIL_OPEN.md`; all must now refuse |
| **Rollback** | Code revert |
| **Acceptance** | `probe.unresolved` receives **403**, not data; T-20 confirms a correctly posted officer is unaffected |

### 5.3 SEC-3 — S-15 + S-17 + S-18, read fix **and** crime write guard · 1–2 d

| | |
|---|---|
| **Files** | `backend/server.py` — `/api/crimes` (`:8837`), `register_crime()` (`:5288`) |
| **Tables** | `crime_incidents` (**read/write only — no DDL**) |
| **Migration** | **None.** Existing NULL-branch rows go to the §3.5 worklist — a data task, not a migration |
| **Automated** | `test_crime_branch_consistency.py` T-23…T-27, incl. **T-26** (zero station branch rows ⇒ scoped or 403, **never all**) + new cases for S-17 (NULL refused) and S-18 (cross-branch 403, own-branch 201) |
| **Manual** | Re-run S-15 scenarios A–D; A must flip to "officer sees own branch", B to refusal, C to 403, D to no widening |
| **Rollback** | Code revert. **Note:** reverting restores the measured exposure |
| **Acceptance** | Posted officer sees exactly their own branch's incidents; unresolved ⇒ 403; cross-branch write ⇒ 403; omitted branch ⇒ pinned, never NULL; station-row removal does not widen |

### 5.4 SEC-4 — checkpoint (H-2b) · 2–3 d

| | |
|---|---|
| **Files** | `backend/server.py` — `checkpoint_scope()` (`:2965`), `checkpoint_scope_sql()` (`:6275`), `GET`/`POST /api/checkpoint-events` |
| **Tables** | `checkpoint_events` (read/write only) |
| **Migration** | **None.** Any stored invalid `location_code` (e.g. `'atlantis'`) needs a **data review**, listed not auto-corrected |
| **Automated** | `test_checkpoint_scope_enforcement.py` T-28…T-35 — T-29 (`''` ⇒ 403), T-31 (unknown location ⇒ **400**, not stored), T-33 (`Southwest` ≠ `South`), T-34/T-35 controls |
| **Manual** | Confirm the `ILIKE '%scope%'` fallback is gone and that a legitimate `'South Checkpoint'` label still matches |
| **Rollback** | Code revert |
| **Acceptance** | Branch **and** location both enforced; unrecognised location rejected at intake; exact matching; a correctly scoped officer still reads and still writes |

### 5.5 M-02 Phase A — alert ownership · 1–1.5 d

| | |
|---|---|
| **Files** | `backend/server.py` — `POST /api/suspect-alerts`; migration script |
| **Tables** | **`suspect_alerts` — ADD COLUMN `branch_id` + index** |
| **Migration** | **Yes — the only schema change in this package.** Additive, nullable, no column dropped/renamed/retyped |
| **Automated** | T-44 (content branch-scoped), **T-45** (flag stays national for a checkpoint officer with no `cid` module), T-46 (NULL ⇒ refuse, never all) |
| **Manual** | Run the backfill against a staging copy; confirm the worklist is produced and nothing is defaulted |
| **Rollback** | **Two levers, strictly ordered.** 1) revert the code — reads return to current behaviour, no data loss, **this is the real rollback**. 2) `DROP COLUMN branch_id` — **only after** lever 1, loses ownership assignments. Never use lever 2 while enforcement is live |
| **Acceptance** | Every new alert carries an owner; creation refused when the creator's branch is unresolved; NULL refuses; **the national flag still fires** |

### 5.6 SEC-1 — person endpoints + alert reads · 2–3 d · **LAST**

| | |
|---|---|
| **Files** | `backend/server.py` — `GET /api/persons/<id>` (`:8449–8461`), `linked_person_records()` (`:5883`), `person_document_records()` (`:5962`), `person_audit_history()` (`:4451`) |
| **Tables** | None · **Migration** None (consumes M-02-A) |
| **Depends on** | **SEC-4** (shared location fix) and **M-02 Phase A** (alert ownership) |
| **Automated** | `test_person_detail_authorization.py` T-36…T-46 |
| **Manual** | Re-run the four-register matrix from `S16_REGISTER_VERIFICATION.md`; all 27 leak combinations must close |
| **Rollback** | Code revert |
| **Acceptance** | **T-39 is the gate** — the fix returns the **same person object with filtered arrays**, never a smaller object. Identity stays readable by every authenticated session; all four arrays filtered by module, branch and location |

### 5.7 SEC-5 — staging verification · 1–2 d · and SS-1 · 1–2 d *(optional)*

| | **SEC-5** | **SS-1** |
|---|---|---|
| **Files** | read-only diagnostic script | `register_crime()`, `register_officer()`, `resolve_station_with_branch()`, `POST /api/branches` |
| **Tables** | none (read-only) | none |
| **Migration** | none | none |
| **Automated** | full regression; 46 tests green | guard tests per chosen option |
| **Manual** | load representative **and deliberately broken** accounts; correct assignments (PRE-4); re-run until only the deliberately broken ones are refused | confirm both affected workflows fail with the intended message |
| **Rollback** | n/a — diagnostic only, never a server mode, never runs in production | code revert; independently revertible |
| **Acceptance** | zero `INDETERMINATE` for intended-valid accounts; **enforcement never disabled at any point** | no new fabricated station rows; existing rows untouched |

### 5.8 Your local acceptance testing — separate from the above

Performed by **you**, on **your** environment, **after** handover. Suggested scope, not a
substitute for your own criteria:

1. Log in as one officer per unit and confirm each sees **their own branch's records and no others**.
2. Deliberately mistype one officer's posting and confirm they are **refused**, not given everything.
3. File a crime from a scoped account against another branch and confirm **403**.
4. Screen a person at a checkpoint who is flagged in a **different** branch and confirm the **flag still fires**.
5. Confirm the administrator still sees everything and ordinary officers do not.
6. Confirm no officer has **lost** access they legitimately need — the over-restriction check.

**I will not mark any package complete on the basis of my own testing alone.**

---

# 6. Repository safety verification

| Requirement | Status |
|---|---|
| No implementation | ✔ |
| No schema changes | ✔ |
| No production configuration changes | ✔ |
| No merge to `main` | ✔ **`origin/main` = `a1c2478`**, unchanged since the session began |
| All evidence and decision history preserved | ✔ nothing deleted or rewritten; M-01's original text retained with a prohibition banner |
| `backend/server.py` | ✔ sha256 `a8211f4f2222e46f14047f5e4ff3135dd43472f0f8c98578d06293708bb3b9fc` |
| Temporary probes | ✔ all deleted (`zz_person_leak_probe`, `zz_branch_scope_probe`, `zz_s16b_registers_probe`, `zz_point6_probe`, `zz_s15_probe`) |
| `PROJECT_STATUS.md`, `DECISION_REGISTER.md` | ✔ unchanged — awaiting your recorded decisions |
| PR #23 | ✔ OPEN + draft, untouched |
| Working tree / commit | ✔ see the executive summary |

---

# 7. What remains

**Before implementation can start:** eight owner decisions (D-1a, D-1b, D-2, D-3, D-4, D-4b, D-5,
D-7). D-2 and parts of D-4b additionally need **police authority / legal** input.

**Before Release 1.0:**

| Band | Content | Days |
|---|---|---|
| **SEC** (SEC-0…SEC-5 + M-02-A) | The authorization defect class | **11–17.5** |
| **P0** | S-07, S-02, S-12/S-13, production initialization | **7–9.5** |
| **SS-1** *(optional, D-5)* | Station safeguards | 1–2 |
| **A-13** *(optional, D-4b)* | Interim withdraw | 2–3 |
| | **Engineering subtotal** | **18–27 d** *(19–29 with SS-1, 21–32 with both)* |
| **P1** | S-01, S-03, S-04 lifecycle, S-05, S-08, S-09 | 23–37 |
| **P2** | S-10 (D-04), S-11, full M-02 lifecycle (D-23) | 34–57 |

**Not expressible in days:** PRE-1, PRE-2, PRE-3, PRE-5 (HQ / HR / CID deployment authority),
**D-23** (legal), the **date conflict** ruling, and your acceptance testing.

**Nothing proceeds without your explicit approval.**
