# Consolidated Owner-Review Package — REVISION 3

**Document date:** 9 November 2026 · **Revision 3** · supersedes revision 2
(content `cc33f1a`, metadata `80573d1`) and revision 1 (`c5bfb61`)
**Content commit:** recorded in §7.1 · **Status:** for owner decision.
**Investigation closed. Implementation unauthorized.**

> **SUPERSEDED FOR PLANNING, 9 November 2026.** The authoritative remediation plan, work-item
> estimate and implementation sequence are now **`security/SECURITY_REMEDIATION_PROGRAMME.md`**,
> and the authoritative owner-decision text is **`security/OWNER_DECISION_PACKAGE_R1.md`**.
> **Revision 3 remains the evidence and review record** — the finding-by-finding evidence
> classification (§5), the date reconciliation (§7.2) and the correction history of revisions 1–3
> exist nowhere else. The totals agree (14–21 before staging, +23–38 before production, 37–59
> total); where presentation differs, **the programme document is authoritative** because it
> derives them from individual work items W-01…W-69 rather than from package bands.

> **Revision 3 corrects six issues you raised against revision 2 and adds execution evidence for
> four findings that were previously unverified.** The two headline changes:
>
> 1. **Your arithmetic was right and mine was wrong.** The `+23–37` figure was not a sum of the
>    tasks listed beside it — it was a band total copied from a different grouping that
>    double-counted two items and omitted two others. **Full reconciliation in §1.2.**
> 2. **S-05 was executed and is worse than recorded.** A CID officer with no HR module reads the
>    full officer register, including dates of birth, mothers' names, personal telephone numbers
>    and the **names, home addresses and telephone numbers of officers' civilian guarantors**.
>    S-05 is re-rated **Medium → High** and moved into the mandatory pre-production band, and the
>    officer-register half is recorded as the new finding **S-20**.

---

## 0. What changed in revision 3

| # | Your finding | Resolution |
|---|---|---|
| **A** | The additional production tasks total 21–34, not 23–37 | **§1.2** — reconciled line by line. **No task was omitted; the total was wrong.** Corrected band **21–34**, corrected overall **35–55**, and **37–59** once S-05/S-20 move in |
| **B** | The eight decisions were not self-contained | **§6** — every option, consequence, cost and recommendation reproduced in full. No cross-reference to an earlier revision |
| **C** | D-1b and A-13 authority unreconciled | **§2.7** (A-13: technical SystemAdmin vs police authority, and what approval is required) and **§6.2** (D-1b: exactly what the warning reveals) |
| **D** | S-05 not reassessed | **Executed.** `S08_S09_EXECUTION_VERIFICATION.md` §2; summarised in §1.3 and §5. Re-rated and re-banded |
| **E** | Decision dependencies and evidence classification | **§6.1** (two dependency tiers), **§6.10** (why D-23 is needed before implementation), **§5** (S-06 reclassified, counts reconciled), **§7.1** (commit ledger with the exact metadata hash) |
| **F** | S-08 / S-09 not executed; S-11 undocumented | **Executed** against a disposable PostgreSQL cluster — `S08_S09_EXECUTION_VERIFICATION.md` §3–§4. S-11 staging HTTPS acceptance test **TLS-1…TLS-10** specified in that document §5.2 |

---

# 1. Authoritative Release 1.0 blocker classification

**Rule applied:** a finding is placed in the earliest category its risk requires. **Nothing has
been moved to a later category to shorten the schedule.** Where a cheaper partial measure exists,
it is named explicitly rather than used to silently reclassify the finding.

## 1.1 The table

| ID | Finding | **Before implementation** | **Before staging** | **Before production 1.0** | **Permitted after 1.0** | Days |
|---|---|:--:|:--:|:--:|:--:|---|
| **Decisions D-1a…D-7** | Eight open owner decisions | **✔** | | | | — |
| **PRE-3** | Confirmed CID branch list | **✔** *(for A-18 scope)* | | | | — |
| **D-23.5 / .6** | Withdrawal authority + state vocabulary | **✔** *(for A-13 only — §6.10)* | | | | — |
| **SEC-0** | Consolidated authorization model | | **✔** | | | 2–3 |
| **SEC-2** | S-14 branch fail-open | | **✔** | | | 2–3 |
| **SEC-3** | S-15 + S-17 + S-18 + write guard | | **✔** | | | 1–2 |
| **SEC-4** | H-2b checkpoint | | **✔** | | | 2–3 |
| **M-02-A** | S-04 alert ownership | | **✔** | | | 1–1.5 |
| **SEC-1** | S-16a + S-16b + alert reads | | **✔** | | | 2–3 |
| **SEC-5** | Staging verification + PRE-4 | | **✔** | | | 1–2 |
| **P0-WP-1** | S-07 discipline closure (N-7) | | **✔** | | | 1.5 |
| **P0-WP-2** | **S-02** admin-reset session revocation | | **✔** | | | 1.5–2 |
| **P0-WP-3** | S-12, S-13, production init (A-16/16a/17/19) | | | **✔** | | 2–3 |
| **PRE-1 / PRE-2** | ≥1 real station; ≥1 officer | | | **✔** | | — |
| **PRE-5** | Station codes confirmed by HQ | | | **✔** | | — |
| **A-18** | 9 branch rows | | | **✔** | | *(in WP-3)* |
| **S-01** | Cross-branch document access (M-01) | | | **✔** | | **11–18** |
| **S-03** | Alerts cannot be corrected — **minimum A-13** | | | **✔** | | **2–3** |
| **S-08** | No session expiry — **execution-proven** | | | **✔** | | **2–3** |
| **S-09** | No auth throttling / no auth audit — **execution-proven** | | | **✔** | | **2–3** |
| **S-11** | No TLS; cookie lacks `Secure` — **partly measured** | | | **✔** | | **2–4** |
| **S-05 + S-20** | Analytics RBAC leak **+ officer-register PII leak** — **execution-proven** | | | **✔ — moved in revision 3** | | **2–4** |
| **S-10** | Mutable audit log | | | **conditional — §1.3** | conditional | 5–10 |
| **S-19** | Station-derived file numbers | | | | **✔** *(policy)* | *(SS-1)* |
| **SS-1** | Station safeguards (D-5) | | | | **✔** *(optional, owner)* | 1–2 |
| **M-02 lifecycle** | Full six-state alert lifecycle | | | | **✔** *(D-23)* | 22–35 |
| **S-06** | Reduced by owner ruling R-1 | — | — | — | — | — |

## 1.2 Corrected totals — with the arithmetic shown

### Where `23–37` came from (reconciled, as you asked)

**No task was omitted. The figure was a band total lifted from a different grouping.** It is the
**P1 band** of `REMEDIATION_PLAN.md` lines 70–78, reproduced verbatim:

| P1 line | Item | Days |
|---|---|---|
| P1.1 | S-03 interim withdrawal | 2–3 |
| P1.2 | S-01 M-01 migration | 5–8 |
| P1.3 | S-01 enforcement + test matrix | 6–10 |
| **P1.4** | **S-04 M-02 `branch_id`** | **4–6** |
| **P1.5** | **S-05 analytics RBAC** | **2–4** |
| P1.6 | S-08 session expiry | 2–3 |
| P1.7 | S-09 throttling and lockout | 2–3 |
| | **P1 total** | **23–37** |

Revision 2 pasted that total next to a **different** list of six items. The two disagree because:

| Discrepancy | Effect on the figure |
|---|---|
| **P1.4 (S-04, 4–6 d) is already counted elsewhere.** Revision 2 moved Phase A (1–1.5 d) into the *staging* band as **M-02-A** and folded the remainder into the deferred lifecycle | **Double-counted: −4 to −6** |
| **P1.5 (S-05, 2–4 d) was listed separately** by revision 2 as "optional / owner-elective" | **Double-counted: −2 to −4** |
| **S-11 (2–4 d)** lives in the P2 band, so the P1 total never contained it — yet revision 2 listed it | **Omitted: +2 to +4** |
| **P0-WP-3 (2–3 d)** is a P0 item, not P1 — also listed by revision 2 | **Omitted: +2 to +3** |

`23–37 − (4–6) − (2–4) + (2–4) + (2–3) = 21–34.` **Your number is correct.**

This is the precise failure my own standing rule was written to prevent — *estimates must not
double-count a shared underlying fix*. I applied the rule to the items and then broke it in the
total.

### The corrected calculation

**Mandatory before staging**

```
SEC-0    2–3        SEC-4     2–3        SEC-5     1–2
SEC-2    2–3        M-02-A    1–1.5      P0-WP-1   1.5
SEC-3    1–2        SEC-1     2–3        P0-WP-2   1.5–2
                                        ─────────────────
                                 minimum  2+2+1+2+1+2+1+1.5+1.5 = 14
                                 maximum  3+3+2+3+1.5+3+2+1.5+2 = 21
```

**Additionally mandatory before production Release 1.0**

```
P0-WP-3        2–3
S-01          11–18
S-03 (A-13)    2–3
S-08           2–3
S-09           2–3
S-11           2–4
S-05 + S-20    2–4     <- moved into this band in revision 3 (§1.3)
──────────────────────
 minimum  2+11+2+2+2+2+2 = 23
 maximum  3+18+3+3+3+4+4 = 38
```

| Band | Days |
|---|---|
| Mandatory before staging | **14–21** |
| Additionally mandatory before production | **+23–38** |
| **Total mandatory before production Release 1.0** | **37–59** |
| *Same total if you sign an explicit risk acceptance for S-05/S-20* | *35–55* |
| Optional / owner-elective — SS-1 | +1–2 |
| Conditional — S-10 tamper-evident audit (D-04, legal) | +5–10 |
| Deferrable to 1.1 — full M-02 lifecycle (D-23) | 22–35 |

> **A coincidence worth flagging so you do not mistake it for agreement.** Revision 2's wrong
> total was 37–58; revision 3's correct total is **37–59**. The numbers nearly match **for
> entirely different reasons** — revision 2 double-counted S-04 and S-05 while omitting S-11 and
> P0-WP-3; revision 3 counts each item once and adds S-05/S-20 on measured evidence. The
> agreement is arithmetic accident, not confirmation.

## 1.3 Treatment of the findings you named

**S-11 — TLS. Mandatory before production. 2–4 days. One correction to revision 2.**
Every credential, session token, person record and uploaded document currently crosses the network
in plaintext. Fixing authorization while leaving transport open means an attacker reads the data
without needing authorization at all. Revision 2 called this *"not an application task"* —
**that was wrong.** Measured: the session cookie is issued `HttpOnly; SameSite=Lax` but **without
`Secure`** (`server.py:8970`), so after TLS is terminated the cookie would *still* be sent over
plain HTTP. One application change is required alongside the infrastructure work. The estimate is
unchanged; its composition is corrected. Staging acceptance test **TLS-1…TLS-10** is specified in
`S08_S09_EXECUTION_VERIFICATION.md` §5.2, together with the infrastructure controls you must own.

**S-01 — Cross-branch document access. Mandatory before production. 11–18 days.**
The same defect class as S-16b, one layer down: any authenticated officer can read any uploaded
file, including another branch's. `test_upload_access_control.py::test_07` **returns 200 today**.
It needs migration M-01 and is the single largest remaining item — the main reason the honest
total is in the thirties, not the twenties.

**S-08 — Session expiry. Mandatory before production. 2–3 days. Now execution-proven.**
A session whose `created_at` was set to **678 days old** returned **200** from `/api/me` — and
still returned 200 **after the server was restarted**, proving the token is re-validated from
storage and accepted, not merely cached. The same aged token read `/api/persons`,
`/api/clearance-applications`, `/api/dashboard` and `/api/fingerprint/applications`. Five
simultaneous sessions for one account all worked; logging one out left the other four alive; no
endpoint can even enumerate them. **Note for scheduling:** an *idle* timeout needs a new
`last_seen_at` column, so S-08 carries a small additive migration and falls under D-7. An
*absolute* timeout alone needs no DDL.

**S-09 — Authentication throttling and audit. Mandatory before production. 2–3 days. Now
execution-proven.** Thirty consecutive wrong passwords: **all 401, no 429, no lockout**, a flat
212 ms each from first to last — that is the PBKDF2 cost, which is *work*, not a *defence*. The
decisive measurement is the next one: **the correct password immediately afterwards returned 200**,
so no protection threshold exists at any value. A one-guess spray across all nine accounts hit no
global or per-source limit. And `audit_events` went **4 → 4** across fifty failed logins and
several successful ones: **authentication is not audited at all**, successful or failed. For a
police system that is an accountability failure as much as a security one.

**S-03 — Suspect-alert correction. Mandatory before production, at the A-13 minimum. 2–3 days.**
Full treatment in §2. The authorization work makes alerts *correctly scoped* but leaves them
*permanently uncorrectable*. Shipping a national flag that nobody — including an administrator —
can remove is the highest human-harm item in this package.

**S-05 + S-20 — Analytics RBAC and officer-register PII. Moved to mandatory before production.
2–4 days for both.** Measured: `ROLE_CID` holds `{dashboard, people, cid, crimes}` and **no
`officers` module**, yet `GET /api/officers` returns **200** with the full register — `date_of_birth`,
`mother_name`, `place_of_birth`, `contact_number`, and `guarantor_name`, `guarantor_address`,
`guarantor_contact`. The guarantor is a **third-party civilian** who never dealt with the CID unit.
The same role reads the station and vehicle analytics bundles, and `/api/analytics?module=all`
silently assembles whatever a caller can reach. Root cause is one line — the `crimes` bypass at
`server.py:8396–8397` — and `/api/officers` has no internal gate of its own.
**Your instruction was explicit: sensitive police information reachable outside authorized roles
may not be classified as safe to defer without explicit risk acceptance.** So it is now in the
mandatory band. **This is a classification change, flagged — not a decision taken for you.** You
may still elect deferral, but then it must be recorded as a signed accepted risk, and the total
falls from 37–59 to 35–55.
*Negative controls that passed, so you can see the measurement is not uniformly red:* HR
analytics, discipline, promotions and conduct are correctly refused to CID/FP/AP/CP;
`/api/admin/*` is refused to everyone but `admin`, including `chief`; the global executive bundle
is correctly restricted to `analytics:global`.

**S-10 — Mutable audit log. Conditional, and the condition is legal, not technical.**
If alerts, clearances or conduct files are ever used in a proceeding, the audit store must be
tamper-evident and S-10 becomes mandatory before production. If not, it may follow 1.0.
**Decision D-04 / A-6 — legal, not mine.** Left conditional rather than chosen. It is also the one
finding I deliberately did **not** probe: see §5.3.

---

# 2. S-03 and D-4b resolved

## 2.1 What S-03 means after M-02 Phase A

**Unchanged. Phase A adds ownership, not lifecycle.**

| Capability | Before Phase A | **After Phase A** |
|---|---|---|
| Alert records which branch owns it | ✘ | **✔** |
| Alert content branch-scoped on read | ✘ | **✔** (with SEC-1) |
| Creation refused when owner unresolved | ✘ | **✔** |
| National screening flag | ✔ | ✔ (unchanged, by design) |
| **Mark an alert cleared** | ✘ | **✘ — still impossible** |
| **Withdraw an alert listed in error** | ✘ | **✘ — still impossible** |
| **Correct an alert's details** | ✘ | **✘ — still impossible** |

`alert_status` is written once, at `INSERT` (`server.py:9497`), always `'Active alert'`. The only
`UPDATE suspect_alerts` in the codebase is a one-time `origin` backfill (`:3232`). There is no
PATCH, no PUT, no DELETE and no withdraw route. **After Phase A, a wrongly listed person is still
flagged at every checkpoint in the country, indefinitely, and nobody can clear it.**

## 2.2 What A-13 actually fixes

A-13 is an **interim, administrator-only withdrawal**: one endpoint that sets a terminal status,
requires a mandatory reason, writes an audit event, and stops the national flag firing.

| A-13 **does** provide | A-13 **does not** provide |
|---|---|
| A way to stop a wrong alert flagging | The six-state lifecycle (`Suspended`, `Cleared`, `Expired`, `Closed`, reopen) |
| A mandatory, audited reason | The distinction between *"cleared — no longer of interest"* and *"withdrawn — should never have been listed"* |
| An actor on record | Automatic expiry / retention (D-23.3's 90-day renewable lifetime) |
| Branch-aware authorization (inherits SEC-0) | A CID supervisor role — **none exists in the role model** |
| | Reopening with history (`reopened_from`) |

**Effort: 2–3 days. No schema change beyond M-02 Phase A.**

## 2.3 What remains unresolved if A-13 is rejected

1. **No correction path of any kind exists.** Not for administrators, not for the listing officer,
   not for the owning branch.
2. **A false-positive identity match is permanent.** Matching is on `national_id` / `passport_id` /
   four-part name; a shared or mistyped ID flags the wrong person nationally, forever.
3. **The only workaround is direct database editing** — which you have explicitly ruled out as a
   permanent solution, and which leaves no audit trail.
4. **Legal exposure grows with every alert created**, and D-23.3's retention requirement becomes
   unimplementable: an alert cannot expire if nothing can change its status.
5. **S-03 stays open and release-blocking regardless** — rejecting A-13 does not close it, it only
   removes the interim mitigation.

## 2.4 Is there a safe alternative?

| Alternative | Verdict |
|---|---|
| **Direct database edit when an error is reported** | **Not safe, and you have already ruled it out.** No audit, no authorization, no reason recorded |
| **Delete the alert row** | **Not safe.** The alert *is* the audit record; deleting it destroys the evidence that an error occurred |
| **Suppress the flag in the UI only** | **Not safe.** `POST /api/checkpoint-events` reads the table directly (`:9597`); the flag would still fire server-side |
| **Add `expires_at` and let alerts lapse** | Partial, and **more** work than A-13 (needs a scheduler). Does nothing for an error discovered today |
| **Ship 1.0 with alert creation disabled** | Coherent but removes a core CID capability; effectively descoping the Crime Unit |
| **A-13 as specified** | **The minimum safe option.** Smallest surface, fully audited, no new role, no schema change |

## 2.5 Minimum correction capability required for Release 1.0

> **One authenticated, authorized, audited action that stops a wrong alert from flagging, with a
> mandatory reason and an actor on record.**

That is precisely A-13. Anything less is either unaudited (direct DB edit), destructive (delete), or
ineffective (UI-only).

## 2.6 Legal/police authority versus engineering

| Question | Who decides |
|---|---|
| Whether a correction capability must exist before production | **Owner** (D-4b) |
| **Who** may withdraw — administrator, listing officer, or a supervisor rank that does not exist today | **Legal + police authority** (A-3, D-23.5) |
| Whether withdrawal requires a second approver | **Legal + police authority** |
| Maximum alert lifetime before mandatory review (D-23.3: 90 days renewable) | **Legal** (A-2) |
| Whether the listed person may be told | **Legal** (A-4, D-23.7) |
| Whether a disputed identity suspends the flag | **Police authority** (A-5) |
| Whether the audit store must be tamper-evident for evidential use | **Legal** (A-6 / D-04) |
| How the endpoint is built, authorized and audited | **Engineering** |
| Whether `Cleared` and `Withdrawn` are distinct states | **Legal shapes it; engineering implements it** (D-23.6) |

## 2.7 A-13 authority — a technical SystemAdmin is **not** a police authority

**This section exists because revision 2 glossed over it.** It said A-13 "uses the existing
administrator role, so it does not pre-empt A-3". That is true about *implementation effort* and
misleading about *authority*.

### What the SystemAdmin role actually is

`ROLE_ADMIN = 'SystemAdmin'` (`server.py:1335`) holds every module. In the data model a user has
`role`, `branch`, `location_scope` and `badge_number` — and **nothing else**. There is no rank
field, no appointment, no warrant number, no command hierarchy, and `ROLE_CID` is flat (confirmed
in D-23.1: *"there is no supervisor role in the system today"*).

| | **Technical SystemAdmin** | **Operationally authorized police officer** |
|---|---|---|
| What it is | The account that operates the deployment: creates users, edits stations, runs initialization | A post holding a police-authority mandate over a person's status in a criminal intelligence register |
| Where its authority comes from | **The software.** Possession of the credential | **Police regulation and law.** An appointment that can be audited, challenged and withdrawn |
| Who may hold it | Anyone the deployment gives it to — **including an IT contractor who is not a sworn officer** | Only a person holding the appointment |
| Accountable to | The system owner | The police service, the courts, and the listed person |
| Can the system tell them apart? | **No.** There is no attribute that records whether the holder is sworn, ranked or appointed | — |

**Therefore A-13 as specified grants the power to clear a national suspect flag to a technical
account, not to a police authority.** I will not present that as adequate. It is acceptable only
as an *interim*, and only if you accept — in writing — that the SystemAdmin credential is held by,
or operated strictly on the written instruction of, a person who holds the operational authority.

### What approval is required before an administrator may withdraw an alert

| # | Required before A-13 is **built** | Authority | Why |
|---|---|---|---|
| 1 | **D-23.5** — who may clear, withdraw and reopen | Legal + police | The direct authority question. Until it is answered, any withdrawal is performed under an authority the police service has never defined |
| 2 | **D-23.6** — are the six states correct; is `Cleared` distinct from `Withdrawn` | Legal + police | A-13 writes **one** terminal value. If the vocabulary changes later, every record A-13 wrote is mislabelled — and the difference between *"no longer of interest"* and *"should never have been listed"* matters to the person and to any later complaint |
| 3 | **A-3** — whether withdrawal requires a supervisor rank | Legal + police | That rank does not exist; creating it is +4–8 days and touches every module |
| 4 | **D-23.1** — who may list | Police | Bounds who may de-list; de-listing authority cannot be looser than listing authority |
| 5 | **A written standing instruction** — *outside the software* | Police authority | Must name the **post** (not the person) holding withdrawal authority, the record required (reason, authorising officer, timestamp), and what happens to withdrawn alerts. Software cannot supply this |

**Not required before A-13:** D-23.2 (evidential threshold), D-23.3 (90-day expiry), D-23.4
(checkpoint confirmation step) and D-23.7 (notification). Those shape the 1.1 lifecycle.

### Engineering proposal, offered — not decided

Build A-13 so the authority is a **named permission** (e.g. `alerts:withdraw`) rather than
hard-wired to `role == 'SystemAdmin'`. Grant it to the SystemAdmin account for 1.0; move it to a
proper supervisor role in 1.1 **without a second migration and without re-authorizing every call
site**. The system already has a permission layer — `PERM_ANALYTICS_GLOBAL` works exactly this way.
**This costs nothing extra inside the 2–3 days** and avoids baking the mismatch into the schema.
It is a proposal; accepting or rejecting it is yours.

---

# 3. Authoritative A-18 dependency sequence

## 3.1 The single authoritative statement

> **A-18 prerequisites — complete list, no other section may contradict this:**
>
> **SEC-0 · SEC-2 · SEC-3 · SEC-4 · M-02 Phase A · SEC-1 · SEC-5 · PRE-3**
>
> In plain terms: **the entire SEC band must be complete, and PRE-3 must be confirmed.**

| Prerequisite | Why A-18 cannot precede it |
|---|---|
| **SEC-0** | Supplies the three-state model. Without it every scope check can still fail open |
| **SEC-2** | S-14: unresolved postings read everything. Initializing production with that live is indefensible |
| **SEC-3** | **Measured:** A-18 creates no `police_station` branch rows, so `/api/crimes` scope becomes unresolvable and posted officers go from **0 rows to 8 (all)** — scenario D |
| **SEC-4** | Checkpoint branch/location scope; A-18 creates the checkpoint branches A-18 itself provisions |
| **M-02-A** | Alert ownership must exist before alerts are created in a real database |
| **SEC-1** | S-16a leaks every unit register through `GET /api/persons/<id>` with **no precondition** |
| **SEC-5** | Staging verification + PRE-4 assignment correction must complete **before** production exists |
| **PRE-3** | `DEFAULT_POLICE_BRANCHES` has **no provenance and is not approved production data** |

## 3.2 Reconciliation of the superseded statements

| Section | Revision 1 said | Now |
|---|---|---|
| **§3.1 graph** | A-18 after SEC-5, gated by PRE-3 | **Correct** — full chain stated explicitly above |
| **§3.4** | "after SEC-2, SEC-3 and SEC-5, and additionally PRE-3" | **Superseded** — omitted SEC-0, SEC-4, M-02-A, SEC-1 |
| **§4.4** | "gated by SEC-2, SEC-3 and PRE-3" | **Superseded** — omitted SEC-5 and the rest |

All sections defer to §3.1.

## 3.3 Full implementation sequence

```
DECISIONS (D-1a, D-1b, D-2, D-3, D-4, D-4b, D-5, D-7)   <- see §6.1 for which block what
      │
SEC-0  consolidated authorization model
      ├── SEC-2  S-14 branch call sites
      │      └── SEC-3  S-15 + S-17 + S-18 + crime write guard   [ONE package]
      ├── SEC-4  H-2b checkpoint
      └── M-02 Phase A  suspect_alerts.branch_id
                 └── SEC-1  S-16a + S-16b + alert reads   [LAST: needs SEC-4 + M-02-A]
                        └── SEC-5  staging verification + PRE-4
                               └── A-18  production branch rows   [+ PRE-3]
                                      └── P0-WP-3  production initialization
                                             └── PRE-1, PRE-2, PRE-5  (HQ / HR)
                                                    └── PRODUCTION RELEASE 1.0
                                                           ^
          also mandatory before this point, independent tracks:
          S-01 (M-01, 11-18d) · S-03 (A-13, 2-3d, + D-23.5/.6) · S-08 (2-3d)
          S-09 (2-3d) · S-11 (TLS, 2-4d) · S-05+S-20 (2-4d)

P0-WP-1 (S-07) and P0-WP-2 (S-02)  — independent, before staging
SS-1 — independent, optional, owner-elective
```

## 3.4 Station removal, and protection of existing station records

Three defences: SEC-3 removes the dependency; SEC-0 makes unresolvable ⇒ refuse; the ordering gate
above. Pinned permanently by **T-26**. Six guarantees protect existing station records: no SEC
package issues station DDL; A-18 touches `police_branches` only; no station DELETE route exists in
the application; scenario D's deletions were inside a disposable cluster destroyed at exit; SS-1
changes only future intake; the three station foreign keys stay intact.

---

# 4. Test identifiers and counts reconciled

## 4.1 T-44 / T-45 / T-46 — shared tests, **not** duplicated identifiers

There are **46 distinct test identifiers, T-01…T-46, each defined once.** The overlap in revision 1
was in *package assignment*, not numbering.

| Test | Asserts | Authored in | **Green after** | Pre-fix expectation |
|---|---|---|---|---|
| **T-44** | Cross-branch CID officer refused alert **content** | M-02 Phase A | **SEC-1** | RED until SEC-1 |
| **T-45** | Checkpoint officer with **no** `cid` module still gets `Flagged match` for an out-of-branch suspect | M-02 Phase A | **Already green — control** | **GREEN before, during and after.** Fails ⇒ the fix over-restricted |
| **T-46a** | Creation refused when the creator's branch is unresolved | M-02 Phase A | **M-02 Phase A** | RED until Phase A |
| **T-46b** | `branch_id IS NULL` ⇒ refuse on read, never "all branches" | M-02 Phase A | **SEC-1** | RED until SEC-1 |

**T-46 has two halves** because the write side lands in Phase A and the read side in SEC-1. They are
sub-parts of one identifier — **T-46 may not be reported green until both land.** All three live in
one file, `backend/test_person_detail_authorization.py`, costed once inside SEC-1's 2–3 days.

## 4.2 The 46 acceptance tests versus the 28-pass / 1-blocked suite

**These measure different things and must never be added together.**

| | **Existing suite** | **The 46 acceptance tests** |
|---|---|---|
| What is counted | **Suite files** | **Individual test cases** |
| Current figure | **29 files: 28 PASS · 0 FAIL · 1 BLOCKED** | **0 executed** |
| Status | Written, running, green today | **Specified only — not written, never run** |
| Covers the authorization fixes? | **No. None of them.** | Yes — that is their purpose |
| After delivery | 34 files | 46 cases across 5 new files |

* **The blocked file** is `backend/test_server.py`, blocked by **N-7 / S-07**. It is *not* passing.
* **No test in the existing suite verifies any authorization fix**, because no fix exists.
* **None of the 46 has been executed.** Where this package says a test "must fail pre-fix", that is
  a **requirement on the implementer**, not a measurement.

## 4.3 Coverage the 46 do **not** include — stated so the count is not mistaken for completeness

The 46 identifiers cover the SEC band, M-02 Phase A and the P0 work packages. They do **not** cover
the carried findings now in the mandatory band:

| Finding | Test status |
|---|---|
| **S-01** | A full matrix already exists in `backend/test_document_branch_authorization.py` — **prepared, dual-mode, currently skipping** until migration M-01 creates the `documents` table. It is written but not numbered in the 46 |
| **S-05 / S-20** | **No tests designed.** Must assert the measured matrix in reverse: `cid.officer` → `/api/officers`, `/api/stations*`, `/api/vehicles*`, `?module=all` all refused, **and** the five negative controls in `S08_S09_EXECUTION_VERIFICATION.md` §2.4 still pass |
| **S-08** | **No tests designed.** Must cover absolute expiry, idle expiry, post-restart rejection, concurrent-session cap/enumeration, and admin-reset revocation |
| **S-09** | **No tests designed.** Must cover lockout threshold, reset-after-success, spray across accounts, and the presence of an audit row per attempt |
| **S-11** | **TLS-1…TLS-10 specified** in `S08_S09_EXECUTION_VERIFICATION.md` §5.2 — a staging acceptance test, not a unit test |

**Designing those tests is part of each package's estimate and is already inside the day ranges in
§1.1.** I am not adding identifiers now, because numbering tests I have not designed is exactly the
kind of predicted-as-actual reporting you told me to stop doing.

---

# 5. Evidence traceability

**Classification:** **[E1]** execution-tested in the latest investigation · **[E2]** execution-tested
in an earlier investigation (reference given) · **[C]** code-reviewed only · **[N]** not yet verified
in this engagement · **[O]** resolved by owner ruling — *not an engineering evidence class*.

## 5.1 Per-finding classification

| ID | Severity | Class | Evidence |
|---|---|:--:|---|
| **S-15** | High | **[E1]** | `S15_EXECUTION_VERIFICATION.md` §2–§3, §6–§7 — scenarios A–E, commit `0dc584f` |
| **S-17** | High | **[E1]** | ibid. §4 — `POST` with no `branch_id` → 201, stored NULL |
| **S-18** | High | **[E1]** | ibid. §4 — Buuhoodle-scoped officer → Erigavo branch 12 → 201 |
| **S-19** | Medium | **[E1]** | ibid. §4 — `CRM-2026-SAN-C-01-0006` minted by a Buuhoodle officer |
| **S-05** | **High** *(was Medium)* | **[E1]** *(was [C])* | `S08_S09_EXECUTION_VERIFICATION.md` §2 — 20-endpoint × 7-role matrix; station and vehicle bundles reachable by `cid.officer`; `?module=cid` ungated |
| **S-20** | **High** | **[E1]** | ibid. §2.2 — `cid.officer` → `GET /api/officers` **200**, full register incl. guarantor name/address/phone |
| **S-08** | High | **[E1]** *(was [N])* | ibid. §3 — 678-day-old session valid across a server restart; 5 concurrent sessions; aged token reads four protected endpoints |
| **S-09** | High | **[E1]** *(was [N])* | ibid. §4 — 30 failures then success = no threshold; spray unimpeded; `audit_events` 4 → 4 |
| **S-02** | High | **[E1]** *(was [E2])* | ibid. §3.5 — admin `PATCH …{password}` → victim's old token still **200**, 3 session rows survive |
| **S-11** | High | **[E1-partial]** *(was [N])* | ibid. §5.1 — cookie lacks `Secure`, served plaintext. **TLS termination itself remains [N]** until TLS-1…TLS-10 run in staging |
| **S-16a** | Critical | **[E2]** | `S16_REGISTER_VERIFICATION.md` §2–§5 — 4/4 registers, 27 leak combinations |
| **S-16b** (`/linked-records`) | High | **[E2]** | ibid. §2–§3 |
| **S-16b** (`/documents`, `/audit-history`) | High | **[E2]** | `OWNER_DECISION_SHEET_AUTHORIZATION.md` §6.1 — 4 documents + clearance events to an out-of-branch officer |
| **S-14** | Critical | **[E2]** | `BRANCH_SCOPE_FAIL_OPEN.md` P1–P5; re-confirmed `S15_EXECUTION_VERIFICATION.md` §3 |
| **H-2b** (no branch filter) | High | **[E2]** | `S16_REGISTER_VERIFICATION.md` §5 |
| **H-2b** (unknown location) | High | **[E2]** | Decision sheet §6.2 — `"Atlantis Border Post"` → 201, stored `'atlantis'` |
| **H-2b** (substring) | High | **[E2]** | Decision sheet §6.3 — `South` scope reads a `Southwest` event |
| **S-04** | High | **[E2]** | `S16_REGISTER_VERIFICATION.md` §4 — Erigavo CID reads a Buuhoodle alert, 200 |
| **S-01** | High | **[E2]** | `test_upload_access_control.py::test_07` **returns 200** |
| **S-07 / N-7** | High *(op.)* | **[E2]** | P0 probe (`05bac05`): pre-fix 8 pass/4 fail → post-fix 14/0; the standing blocked suite |
| **S-12** | High | **[E2]** | `test_password_security.py::test_05`; `server.py:3489` |
| **S-13** | High | **[E2]** | P0 probe: first production run → branches 9, stations/locations/officers 0, users 1 |
| **S-03** | High | **[C]** | Code search: the only `UPDATE suspect_alerts` is the `origin` backfill (`:3232`). **No endpoint exists to test** — absence of a route cannot be probed, only demonstrated by exhaustive search |
| **S-10** | High | **[N]** | **Deliberately not probed — see §5.3** |
| **S-06** | — | **[O]** | **Reclassified in revision 3.** Resolved by owner ruling **R-1**, which is a *factual determination by you* ("no operational database has ever existed"), **not execution evidence**. Its live residual is S-12 + S-13, both **[E2]** above |

## 5.2 Reconciled counts

| Class | Count | Members |
|---|---|---|
| **[E1]** | **9** | S-15, S-17, S-18, S-19, S-05, S-20, S-08, S-09, S-02 |
| **[E1-partial]** | **1** | S-11 |
| **[E2]** | **12** | S-16a, S-16b ×2, S-14, H-2b ×3, S-04, S-01, S-07/N-7, S-12, S-13 |
| **[C]** | **1** | S-03 |
| **[N]** | **1** | S-10 |
| **[O]** | **1** | S-06 |
| **Total rows** | **25** | |

> **Two counting errors in revision 2, both corrected.** It stated *"[E1] 4 · [E2] 13 · [C] 2 ·
> [N] 4"* = 23 against a table of **24** rows: S-02 was listed in the table but the [E2] tally said
> 13 when fourteen rows carried the marker, and S-06 was counted as [E2] when owner ruling is not
> execution evidence. The counts above were produced by counting the table, not by recalling it.

## 5.3 Why S-10 was not probed

Demonstrating S-10 is trivial: `UPDATE audit_events …` succeeds because nothing prevents it. But
that proves a property of **PostgreSQL table permissions**, not of the application, and the open
question in S-10 is **whether the audit store must be tamper-evident** — decision **D-04 / A-6
(legal)**. A probe would generate evidence that does not move the decision. It stays **[N]**, with
the reason recorded rather than disguised as thoroughness.

---

# 6. The eight open decisions — complete, self-contained

**Nothing in this section refers you to another document or an earlier revision.** Every option,
consequence, cost and recommendation is reproduced here in full. **No decision has been altered or
taken on your behalf.** Two *classifications* have changed, both flagged: **D-4b** (now blocks 1.0)
and **S-05/S-20** (now mandatory before production).

## 6.1 Which decisions block what — the two tiers you asked for

### Tier 1 — blocks **all** implementation

| Decision | Why nothing can start |
|---|---|
| **D-3** (cross-branch CID access, A/B/C) | It changes the **type signature of SEC-0**, the first package, on which every later package depends. Option **A** needs the three states `UNRESTRICTED` / `GRANTED` / `INDETERMINATE`. Option **B** needs a fourth concept — a role-based unrestricted grant for a role that does not exist yet. Option **C** needs a fifth state, `EXISTENCE_ONLY`, plus an audited request action. SEC-0 cannot be written, let alone tested, until you choose |

### Tier 2 — blocks only particular packages

| Decision | Blocks | Does **not** block |
|---|---|---|
| **D-7** (migration safety) | Every package carrying DDL: **M-02-A**, **S-01/M-01**, and **S-08** if an idle timeout is chosen | SEC-0, SEC-2, SEC-3, SEC-4 (code-only), S-09, S-05/S-20, S-11 |
| **D-1a** (ownership stored, R1–R5) | **M-02-A**, then **SEC-1**, then **A-18** | SEC-0, SEC-2, SEC-3, SEC-4, and all P0 work |
| **D-4** (Phase A as a 1.0 dependency) | **M-02-A** → **SEC-1** → **A-18** | SEC-0, SEC-2, SEC-3, SEC-4, P0 |
| **D-2** (flag stays national) | **M-02-A** and **SEC-1** behaviour; the T-45 control | Everything else |
| **D-1b** (reveal owning branch) | Only the **alert response payload** in M-02-A/SEC-1. Smallest blast radius of the eight | Everything else |
| **D-4b** (A-13) | **A-13 only** — but A-13 is itself release-blocking | Every other package |
| **D-5** (SS-1) | **SS-1 only** — optional | Every other package |
| **D-23.5 / D-23.6** *(legal, not one of the eight)* | **A-13's authority model and terminal state value** — see §6.10 | Everything else |
| **D-04 / A-6** *(legal, not one of the eight)* | **S-10 only** | Everything else |

**Everything is additionally blocked by the standing authorization gate**: implementation has not
been approved at all. That is a process state, not a numbered decision.

## 6.2 D-1a — alert ownership = the creating CID branch, stored explicitly

**Options: approve / reject.** **Blocks:** M-02-A → SEC-1 → A-18. **Cost:** inside M-02-A's 1–1.5 d.

The proposed schema is additive only — no column dropped, renamed or retyped, no row deleted:

```sql
ALTER TABLE suspect_alerts
  ADD COLUMN IF NOT EXISTS branch_id INTEGER
      REFERENCES police_branches(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_suspect_alerts_branch ON suspect_alerts(branch_id);
```

| Rule | Statement |
|---|---|
| **R1** | An alert is owned by the **CID branch of the officer who created it**, written at `INSERT` |
| **R2** | Ownership is **stored, never derived** — not from `case_id` (nullable by design: standalone intelligence listings), and not from the creator's current `users.branch` (mutable: an officer transfer would silently re-own their entire history) |
| **R3** | `branch_id IS NULL` ⇒ `INDETERMINATE` ⇒ **content refused.** Never "all branches" |
| **R4** | If the creator's own branch is unresolved, **creation is refused.** An alert cannot exist without an owner |
| **R5** | Ownership does not change when the linked case is reassigned, closed or deleted |

**If you reject it,** ownership must be derived at read time from `crime_cases.branch_id` — which
is NULL for every standalone intelligence listing, so those alerts become permanently
`INDETERMINATE` and invisible to the unit that created them; and an officer transfer silently
re-owns their alert history, which is an audit defect as much as a security one.

**Recommendation: approve.** R2 is the substantive choice and the reason is transfer-safety, not
convenience.

## 6.3 D-1b — does the national warning also reveal the **owning branch name**?

**Options: yes / no.** **Blocks:** the alert response payload only. **Cost:** ≈0 — the value is
already in scope at the point the response is built.

### What the national warning reveals **today** (measured from the code path)

`POST /api/checkpoint-events` runs exactly this (`server.py:9597`):

```sql
SELECT 1 FROM suspect_alerts
 WHERE person_id=%s AND role='Suspect' AND alert_status='Active alert' LIMIT 1
```

and sets `screening_result = 'Flagged match'` (else `'No active alert'`) and
`action_taken = 'Supervisor contacted'` (else `'Cleared'`).

| Revealed nationally, to any screening officer | Restricted to the owning CID branch |
|---|---|
| **That** the person has an active Suspect alert | `alert_id` |
| `screening_result = 'Flagged match'` | `role` (Suspect / Witness / Person of interest) |
| `action_taken = 'Supervisor contacted'` | `origin` (Case Link / Direct Intelligence Listing) |
| *(under D-1b)* the owning branch **name** | `notes` — the free-text reason the person was listed |
| | `case_id`, case category, case status |
| | listing officer, creation time, full alert history |

**The warning is a boolean plus a fixed action string.** It carries no reason, no case and no
narrative. The checkpoint officer never holds the `cid` module.

### Why the branch name **should** be visible

The screening officer is told `action_taken = 'Supervisor contacted'` and is given **no way to
know which supervisor**. Today that means phoning around while a flagged person waits. The branch
name is a routing hint that makes the instruction executable. It also creates an accountable
point of contact if the person disputes the listing, which is the practical precondition for
D-23.7 (notification) ever working.

### Why it **should not**

The branch name is itself information about an investigation: it tells the screening officer
*where* the person is of interest. With eight stations and nine CID branches, "Buuhoodle CID
listed this person" can be enough to infer the subject matter — especially for someone stopped
repeatedly. And the value does not stay at the checkpoint: it is written into `checkpoint_events`,
a register whose scoping is **weaker than the alert's** until SEC-4 closes H-2b. So the routing
hint would propagate further than the alert content it is meant to substitute for.

**Engineering constraint, not a decision:** if you answer yes, it must not ship **before SEC-4**,
or the hint leaks wider than the data it replaces.

**Recommendation: yes — low sensitivity relative to `notes` or `case_id`, high operational value —
but sequenced after SEC-4.** **Whose decision:** police authority (who may know which unit is
investigating whom), informed by legal via D-23.7.

## 6.4 D-2 — does the alert **flag** stay national?

**Options: keep national / branch-scope it.** **Blocks:** M-02-A and SEC-1 behaviour, and the T-45
control. **Cost:** 0 either way.

A person listed in Buuhoodle is currently flagged when screened in Erigavo. **Branch-scoping the
flag would mean a suspect stops being flagged the moment they leave the listing region — precisely
when they are travelling.**

| Risk | Today | After the authorization fix |
|---|---|---|
| **False positive — wrong identity match** | Matching is on `national_id` / `passport_id` / four-part name. A shared or mistyped ID flags the wrong person at every checkpoint in the country | **Unchanged.** This fix does not improve identity matching |
| **Incorrect alert (listed in error)** | Flags nationally, permanently | **Unchanged until A-13 or the M-02 lifecycle** |
| **Withdrawal** | **Impossible — no endpoint exists** | **Still impossible after Phase A** |
| **Over-restriction** | — | Guarded by **T-45**: a checkpoint officer with no `cid` module must still receive `Flagged match` for an out-of-branch suspect |

**Recommendation: keep national.** Scoping it is a safety regression, and it would not reduce the
real harm — which is carried by the flag, not by the content.
**Whose decision: police authority (A-1), not engineering.** I can tell you what each option costs
and breaks; I cannot tell you whether a suspect should stop being flagged at a regional border.

## 6.5 D-3 — cross-branch CID access: **A**, **B** or **C**

**Options: A / B / C — all three live, none assumed approved.** **Blocks: ALL implementation
(Tier 1).**

| | **A — Strict branch** | **B — National CID read role** | **C — Flag + request** |
|---|---|---|---|
| **Definition** | A CID officer reads alert content only for their own branch. Out-of-branch ⇒ `403` | A new named role reads alert content in **every** branch. Ordinary CID officers stay branch-scoped | Out-of-branch CID officers see that an alert **exists** and its **owning branch**, not its content, plus an audited "request access" action |
| **Affected roles** | `ROLE_CID` only | `ROLE_CID` + a **new** role (role-model change) | `ROLE_CID` only |
| **Permitted operations** | Own branch: read/create/update. Other: none | Holder: read **all** branches (read-only). Others as A | Own branch: as A. Other: existence + branch name + request |
| **Security consequence** | Smallest surface. **Fail-closed by construction** | **Recreates today's exposure for whoever holds the role.** Its safety depends entirely on holder discipline — a process control, not a technical one | Small surface; the request trail is itself useful evidence |
| **Operational consequence** | A national investigation needs out-of-band phone calls. Rigid; may drive workarounds | Investigations work smoothly | The officer discovers the right branch instantly and asks |
| **Cost** | **0 d** — falls out of SEC-0 | +0.5 d **plus a role-model change** | +1–1.5 d |

**Recommendation: A for Release 1.0, C as a 1.1 follow-up. Advise against B.** A costs nothing and
is the only option fail-closed by construction. C is the better long-term design but should not
delay a security fix. **B rebuilds the current cross-branch exposure under a nicer name, and there
is no supervisor or seniority model in the system today to constrain who holds it.** If
operational feedback shows A is too rigid, **C is the upgrade path — not B.**

## 6.6 D-4 — M-02 Phase A approved as a Release 1.0 dependency

**Options: approve / defer.** **Blocks:** M-02-A → SEC-1 → A-18. **Cost: 1–1.5 d.**

| **Phase A INCLUDES** | **Phase A EXCLUDES** |
|---|---|
| `branch_id` column + index | The six-state lifecycle (`Active`/`Suspended`/`Cleared`/`Withdrawn`/`Expired`/`Closed`) |
| Backfill of existing rows | Any state-transition endpoint |
| Writing `branch_id` on alert creation | **Withdraw** and **update** endpoints |
| Refusing creation when the creator's branch is unresolved (R4) | Automatic expiry / retention (D-23.3) |
| Branch-scoped **reads** of alert content | `status_reason`, `expires_at`, `reopened_from`, append-only history |
| Tests T-44, T-45, T-46 | A CID supervisor role |

| Capability | Required for a safe 1.0? | Why |
|---|---|---|
| Alert content branch-scoped | **Yes** | Proven live cross-branch read (S-04) |
| Alert flag stays national | **Yes** | Removing it is a safety regression |
| Creation refused when owner unresolved | **Yes** | Otherwise NULL owners accumulate |
| Withdraw / correct an alert | **Separate — D-4b** | Needs D-23.5/.6 |
| Retention / expiry | **No** | Needs D-23.3 |

**If you defer it,** SEC-1 cannot complete (alert reads stay unscoped, so S-04 stays open) and
A-18 stays blocked — which blocks production initialization entirely.

**Recommendation: approve.**

## 6.7 D-4b — A-13, the interim administrator-only withdrawal

**Options: approve / defer / reject.** **Blocks: A-13 only — but A-13 is release-blocking.**
**Cost: 2–3 d.** Full analysis in §2; authority analysis in §2.7.

| | |
|---|---|
| **Approve** | 1.0 ships with one authenticated, audited way to stop a wrong alert flagging. +2–3 d. Requires **D-23.5 and D-23.6** answered first (§6.10), and a written standing instruction naming the authorising post |
| **Defer** | 1.0 ships with alerts that **cannot be corrected by anyone**. A false-positive identity match is permanent and national. The only workaround is direct database editing, which you have prohibited. **This must be recorded as an accepted risk with your signature, not left open as though scheduled** |
| **Reject** | As "defer", permanently, and D-23.3's retention requirement becomes unimplementable — an alert cannot expire if nothing can change its status |

> **Reclassification, flagged.** Revision 1 marked D-4b *"does not block 1.0"*. §1 and §2 establish
> that **some** correction capability is mandatory before production and A-13 is the minimum such
> capability, so **D-4b now blocks Release 1.0.** The *classification* changed; **the decision
> remains yours**, and rejecting A-13 with a recorded risk acceptance is a legitimate answer.

**Recommendation: approve** — with the permission-based authority model proposed in §2.7, so the
power can move to a proper supervisor role in 1.1 without a second migration.

## 6.8 D-5 — SS-1 station safeguards

**Options: (i) / (ii) / (iii) / (iv).** **Blocks: SS-1 only — optional, not release-blocking.**

Only **two** workflows call the fabricating resolver — measured, these are the only callers:
crime incident registration (`register_crime`, `:5294`) and officer registration
(`register_officer`, `:4828`).

| | **(i) G-a + G-c** | **(ii) all four guards** | **(iii) all four + operator message** | **(iv) G-c only — accept the risk** |
|---|---|---|---|---|
| **Crime registration vs `BR-7`** | **Blocked** (no phone / no `created_by`) | **Blocked** — *"station does not exist"* | **Blocked**, with the remedy named | **Still succeeds**; station fabricated |
| **Officer registration vs `BR-7`** | **Still succeeds — station still fabricated** | **Blocked** | **Blocked**, remedy named | **Still succeeds** |
| **Fabrication stopped?** | **No** — rows keep accumulating | Yes | Yes | No |
| **Decommissioned stations refused** | Yes | Yes | Yes | Yes |
| **Operator experience** | Crime desk blocked with a cause they cannot act on | Blocked; the error names a code, not a remedy | Blocked; the error names the administrator action required | No change |
| **Effort** | 0.5–1 d | 1–2 d | 1–2 d | 0.25 d |

**Why (iii):** (i) is the worst of both — it blocks the crime desk while leaving officer
registration fabricating stations, so half the measured blast radius is untouched and the junk
rows keep coming. (ii) and (iii) **cost the same**; the difference is one sentence of error text,
and the entire operational objection to blocking is "operators will be blocked and won't know
why" — refusing to spend that sentence is indefensible. The integrity stake is permanent:
`register_crime()` stamps the station code into `CRM-<year>-<code>-NNNN`, so a fabricated station
puts an invented code into an **official file number that can never be corrected**.
**(iv) is coherent and I have kept it on the sheet** — if you judge the workflow disruption
unacceptable for 1.0, (iv) is more honest than (i) pretending to be a fix — but it must then be
recorded as **accepted risk with your signature**.

**Recommendation: (iii).**

## 6.9 D-7 — migration safety procedure

**Options: approve / amend.** **Blocks: every package carrying DDL** — M-02-A, S-01/M-01, and S-08
if an idle timeout is chosen. **Cost:** procedural, no separate day cost.

**How existing alerts get ownership**

| Source | Rule | Result |
|---|---|---|
| Alert **with** a case whose `crime_cases.branch_id` is set | `branch_id := crime_cases.branch_id` | Resolved automatically |
| Alert **with** a case whose `branch_id` is NULL | cannot resolve | **NULL — worklist** |
| Alert with **no case** (standalone listing) | cannot resolve | **NULL — worklist** |

Per your ruling R-1 there is no production database, so the only alerts that exist are demo seed
rows. **The backfill worklist is expected to be empty or near-empty, and this is the cheapest
moment this change will ever be made.** The procedure exists because that will not be true later.

**NULL and ambiguous ownership**

1. **Fail closed.** `branch_id IS NULL` ⇒ `INDETERMINATE` ⇒ content refused (**T-46**). Never "all
   branches" — that is the S-14 mistake this whole package exists to remove.
2. **The flag is unaffected.** An unowned alert **still flags nationally at checkpoints**. No
   safety function is lost while ownership is being classified; only CID content visibility is
   withheld.
3. **Worklist, not a default.** Unresolved rows are listed for manual classification. **Never
   defaulted to a branch** — a wrong owner is worse than no owner, because it *grants* access
   rather than withholding it.
4. **Staging first.** Classification is completed and verified in staging before enforcement
   reaches production, consistent with your ruling that there is **no report-only production
   phase**.

**Rollback — two independent levers, in strict order**

| Lever | Action | Effect | Data loss |
|---|---|---|---|
| **1. Code** | Revert the SEC-1 enforcement commit | Alert reads return to current behaviour; the column stays and keeps being populated | **None** |
| **2. Schema** | `ALTER TABLE suspect_alerts DROP COLUMN branch_id;` | Returns the table to its present shape | **Ownership assignments are lost** |

Lever 1 may be used alone, at any time, with no data loss — **it is the real rollback.** Lever 2
**must never be used while enforcement is live** (every alert would become `INDETERMINATE` and all
content would vanish from CID screens). Always revert code first, then schema, and only if the
column is being abandoned. Phase A is additive, so lever 2 is a true inverse.

**Recommendation: approve.**

## 6.10 Why **D-23** is required before implementation even though the lifecycle is deferred to 1.1

You asked this directly, and it is a fair challenge: if the six-state lifecycle is 1.1 work, why
should a legal decision gate 1.0?

**It does not gate 1.0 as a whole. It gates A-13 specifically, and only two of its seven parts.**

| Sub-decision | Needed before implementation? | Why |
|---|---|---|
| **D-23.5** — who may clear, withdraw and reopen | **YES — before A-13 is built** | A-13 *is* a withdrawal action. Building it answers D-23.5 by default, in code, without the police service having decided. Every withdrawal performed under it would be performed under an authority nobody defined |
| **D-23.6** — are the six states correct; is `Cleared` distinct from `Withdrawn` | **YES — before A-13 is built** | A-13 writes exactly **one** terminal value. If the vocabulary later differs, every record A-13 wrote is mislabelled — and "no longer of interest" versus "should never have been listed" is precisely the distinction that matters to the listed person and to any later complaint. Re-labelling them afterwards means a second migration over live alert records |
| **D-23.1** — who may list a suspect | **Only if a supervisor rank is assumed** | There is no supervisor role today. If A-13 is built against a rank that does not exist, it cannot ship; +4–8 d to create one, touching every module |
| **D-23.2** — evidential threshold | No — 1.1 | Shapes a mandatory justification field at *creation*, not withdrawal |
| **D-23.3** — maximum alert lifetime (90 days proposed) | No — 1.1 | Sets `expires_at` and the expiry job. **But note the dependency runs the other way:** without A-13 or the lifecycle, nothing can change a status, so D-23.3 is *unimplementable* no matter what number you choose |
| **D-23.4** — supervisor confirmation before action at a checkpoint | No — 1.1 | Changes the checkpoint flow, not the alert record |
| **D-23.7** — right to be told | No — 1.1 | A notification obligation; ties to D-05 |

**In one sentence: deferring the lifecycle is fine; deferring the two questions that fix A-13's
authority and its terminal state vocabulary is not, because A-13 writes permanent records against
both.**

This is why **D-23.5/.6** appear in the *before implementation* column of §1.1 — scoped to A-13
alone, not to the release.

## 6.11 Summary — status of each decision

| # | Decision | Options | Blocks | My recommendation |
|---|---|---|---|---|
| **D-1a** | Alert ownership = creating CID branch, stored (R1–R5) | approve / reject | M-02-A → SEC-1 → A-18 | **Approve** |
| **D-1b** | National warning reveals the owning branch name | yes / no | Alert payload only | **Yes**, sequenced after SEC-4 |
| **D-2** | Alert **flag** stays national | keep national / branch-scope | M-02-A, SEC-1, T-45 | **Keep national** *(police authority)* |
| **D-3** | Cross-branch CID access | **A** / **B** / **C** | **ALL implementation** | **A** for 1.0, **C** for 1.1. Advise against **B** |
| **D-4** | M-02 Phase A as a 1.0 dependency | approve / defer | M-02-A → SEC-1 → A-18 | **Approve** — 1–1.5 d |
| **D-4b** | A-13 interim admin-only withdrawal | approve / defer / reject | A-13 **(release-blocking)** | **Approve**, with §2.7's permission model |
| **D-5** | SS-1 station safeguards | **(i)/(ii)/(iii)/(iv)** | SS-1 only *(optional)* | **(iii)** |
| **D-7** | Migration safety procedure | approve / amend | All DDL packages | **Approve** |

**D-6 is CLOSED** — answered by the S-15 execution (`0dc584f`).
**Not among the eight, but outstanding and consequential:** **D-23.5 / D-23.6** (legal + police —
gate A-13), **D-23.1** (police), **D-04 / A-6** (legal — gates S-10), **A-1…A-5** (police/legal).

---

# 7. Metadata, repository safety and changed files

## 7.1 Commit ledger

| Revision | Role | Commit |
|---|---|---|
| Revision 1 | content | `c5bfb61` |
| Revision 2 | content | `cc33f1a` |
| **Revision 2** | **metadata** | **`80573d1`** — recorded here, as you required |
| **Revision 3** | **content** | **`b81ceb7`** (full: `b81ceb78657582edfe057f89a609770ee6b1808c`) — carries all three changed files |
| Revision 3 | metadata | the commit that writes the revision 3 content hash into this table; its own hash is reported in the delivery message and recorded in the next revision |

> **Why one hash per revision is always recorded one step late.** A commit's hash is a digest of
> its own content, so a commit cannot contain its own hash — writing the value changes the value.
> The content commit is therefore made first and its hash recorded in a small follow-up commit.
> The content commit is never `--amend`ed, because amending would produce a new hash and
> invalidate the value printed above. Revision 2's metadata hash was missing from revision 2 for
> exactly this reason; **it is `80573d1` and it is now recorded.**

| Item | Value |
|---|---|
| Branch | `arena/6303ef2f-sentinel-police-management` |
| `origin/main` | **`a1c2478` — unchanged** |
| `backend/server.py` | sha256 `a8211f4f2222e46f14047f5e4ff3135dd43472f0f8c98578d06293708bb3b9fc` — unchanged |
| Working tree | clean at commit time |
| Test suite | 29 files — **28 PASS · 0 FAIL · 1 BLOCKED** (N-7), unchanged |

## 7.2 Date discrepancy — explained, not silently reconciled

| Source | Value |
|---|---|
| Session-supplied local date (earlier turns) | **5 November 2026** |
| Sandbox clock (`date -u`), earlier turns | 7–8 November 2026 |
| Sandbox clock (`date -u`), this turn | **9 November 2026** |
| **Your statement** | **9 November 2026** |

**Resolution: the sandbox clock was correct and the session-supplied date was stale.** Earlier in
this engagement I back-dated four documents from 7 November to 5 November on the strength of the
stale value. **That was my error.** Those documents have **not** been re-dated again — you
instructed that historical dates be preserved — so they still read 5 November and this note is the
record of why. Only this consolidated document carries the 9 November date. A one-line erratum for
`RELEASE_1_0_REFERENCE_DATA.md` §5 is **recommended but not applied**, because applying it would
edit a historical document.

## 7.3 Compliance with your restrictions

| Restriction | Status |
|---|---|
| Investigation and documentation only | ✔ nothing implemented |
| No application implementation | ✔ `server.py` sha256 unchanged before and after the probe |
| No migrations or schema changes | ✔ the probe issued no DDL |
| No production configuration changes | ✔ |
| No merge to `main` | ✔ `origin/main` = `a1c2478` |
| Disposable test data only | ✔ temporary PostgreSQL cluster, destroyed at exit; two synthetic officer rows inside it; **no existing database opened** |
| Existing evidence and decision history preserved | ✔ nothing deleted, back-dated or rewritten |
| Owner decisions unchanged | ✔ — two *classification* changes (D-4b, S-05/S-20), both flagged; no decision taken |
| `PROJECT_STATUS.md`, `DECISION_REGISTER.md` | ✔ **not modified** |
| Temporary probes removed | ✔ `backend/zz_sec_probe.py` deleted; working tree clean |
| Final commit and working tree verified | ✔ §7.1 |

## 7.4 Documentation files changed in revision 3

**Exactly three. No application file, no test file, no configuration file.**

| File | Change |
|---|---|
| `security/OWNER_REVIEW_PACKAGE.md` | Rewritten as revision 3 — §1.2 arithmetic reconciliation, §2.7 A-13 authority, §4.3 test-coverage gaps, §5 reclassified and recounted, §6 fully self-contained decisions, §7.1 commit ledger |
| `security/S08_S09_EXECUTION_VERIFICATION.md` | **NEW** — execution evidence for S-05, S-08, S-09, S-02 and the S-11 cookie finding; the TLS-1…TLS-10 staging acceptance test; disclosed limitations |
| `security/SECURITY_ISSUE_REGISTER.md` | Evidence classes updated to match §5; S-05 re-rated Medium → High; **S-20 added**; S-06 reclassified **[O]** |

## 7.5 Deviations and errors disclosed in this revision

1. **The `23–37` figure was a mis-cited band total**, not a sum — it double-counted S-04 and S-05
   and omitted S-11 and P0-WP-3. It broke my own rule against double-counting a shared fix.
2. **Revision 2's evidence counts were wrong twice** — the [E2] tally said 13 against fourteen
   marked rows, and S-06 was counted as execution evidence when it rests on an owner ruling.
3. **Revision 2 called S-11 "not an application task."** Measured: the session cookie lacks
   `Secure`, so one application change is required.
4. **Revision 2 left S-05 at Medium and deferred it** on a code-read basis. Execution shows
   officer and guarantor personal data reachable by a role with no HR module.
5. **Revision 2's §7.1 named a metadata commit without a value.** It is `80573d1`, recorded in
   §7.1 above.
6. **Two officer rows were SQL-seeded** for the S-05 measurement, and the 678-day session age was
   produced by updating `created_at` rather than waiting. Both are disclosed in
   `S08_S09_EXECUTION_VERIFICATION.md` §5.5; every access measurement was real HTTP.
7. **S-10 was not probed** — deliberately, with the reason recorded in §5.3.

---

**Nothing in this package has been implemented. Eight decisions remain open, plus the legal
questions in §6.11. I am waiting for your approval before any implementation begins.**
