# Consolidated Owner-Review Package — REVISION 2

**Document date:** 9 November 2026 · **Revision 2** · supersedes revision 1 (commit `c5bfb61`)
**Content commit:** recorded in §7.1
**Status:** for owner decision. **Investigation closed. Implementation unauthorized.**

> **Revision 2 corrects five inconsistencies you identified in revision 1.** The most important
> is §1: revision 1 labelled S-01, S-03, S-08, S-09 and S-11 as release blockers in one section
> and placed them outside the headline schedule in another. **They are blockers. The schedule was
> wrong, not the classification.** The honest figure before production Release 1.0 is
> **37–58 days**, not 18–27.

---

## 0. What changed in revision 2

| # | Your finding | Resolution |
|---|---|---|
| 1 | Blocker classification contradicted the schedule | **§1** — one authoritative four-category table. **No blocker downgraded.** Headline total corrected **18–27 → 37–58 d** |
| 2 | S-03 / D-4b unclear | **§2** — what S-03 means after Phase A, what A-13 fixes, what is left if rejected, alternatives, and the minimum capability for 1.0 |
| 3 | A-18 prerequisites inconsistent across §3.1/§3.4/§4.4 | **§3** — one authoritative sequence; every section now states the same prerequisites |
| 4 | T-44/T-45/T-46 overlap; 46 vs 28/1 confusion | **§4** — shared tests, not duplicated identifiers; the two counts measure different things |
| 5 | Evidence not traceable per finding | **§5** — four-level classification on every finding |
| 6 | Header date wrong | **§7.2** — corrected to 9 November; historical dates preserved; discrepancy explained |

---

# 1. Authoritative Release 1.0 blocker classification

**Rule applied:** a finding is placed in the earliest category its risk requires. **Nothing has
been moved to a later category to shorten the schedule.** Where a cheaper partial measure exists,
it is named explicitly rather than used to silently reclassify the finding.

## 1.1 The table

| ID | Finding | **Mandatory before implementation** | **Mandatory before staging** | **Mandatory before production 1.0** | **Permitted after 1.0** | Days |
|---|---|:--:|:--:|:--:|:--:|---|
| **Decisions D-1a…D-7** | Eight open owner decisions | **✔** | | | | — |
| **PRE-3** | Confirmed CID branch list | **✔** *(for A-18 scope)* | | | | — |
| **D-23** | Alert legal framework | **✔** *(for lifecycle only)* | | | | — |
| **SEC-0** | Consolidated authorization model | | **✔** | | | 2–3 |
| **SEC-2** | S-14 branch fail-open | | **✔** | | | 2–3 |
| **SEC-3** | S-15 + S-17 + S-18 + write guard | | **✔** | | | 1–2 |
| **SEC-4** | H-2b checkpoint | | **✔** | | | 2–3 |
| **M-02-A** | S-04 alert ownership | | **✔** | | | 1–1.5 |
| **SEC-1** | S-16a + S-16b + alert reads | | **✔** | | | 2–3 |
| **SEC-5** | Staging verification + PRE-4 | | **✔** | | | 1–2 |
| **P0-WP-1** | S-07 discipline closure (N-7) | | **✔** | | | 1.5 |
| **P0-WP-2** | S-02 session revocation | | **✔** | | | 1.5–2 |
| **P0-WP-3** | S-12, S-13, production init (A-16/16a/17/19) | | | **✔** | | 2–3 |
| **PRE-1 / PRE-2** | ≥1 real station; ≥1 officer | | | **✔** | | — |
| **PRE-5** | Station codes confirmed by HQ | | | **✔** | | — |
| **A-18** | 9 branch rows | | | **✔** | | *(in WP-3)* |
| **S-01** | Cross-branch document access (M-01) | | | **✔** | | **11–18** |
| **S-03** | Alerts cannot be corrected — **minimum A-13** | | | **✔** | | **2–3** |
| **S-08** | No session expiry | | | **✔** | | **2–3** |
| **S-09** | No auth throttling / auth audit | | | **✔** | | **2–3** |
| **S-11** | No TLS | | | **✔** *(infrastructure)* | | **2–4** |
| **S-10** | Mutable audit log | | | **conditional — see §1.3** | conditional | 5–10 |
| **S-05** | Analytics RBAC leak | | | | **✔** *(recommended earlier)* | 2–4 |
| **S-19** | Station-derived file numbers | | | | **✔** *(policy)* | *(SS-1)* |
| **SS-1** | Station safeguards (D-5) | | | | **✔** *(optional, owner)* | 1–2 |
| **M-02 lifecycle** | Full six-state alert lifecycle | | | | **✔** *(D-23)* | 22–35 |
| **S-06** | Reduced by R-1 | — | — | — | — | — |

## 1.2 Corrected totals

| Band | Content | Days |
|---|---|---|
| Before staging | SEC-0…SEC-5 + M-02-A + P0-WP-1 + P0-WP-2 | **14–21** |
| Before production 1.0 | + P0-WP-3, S-01, S-03 (A-13), S-08, S-09, S-11 | **+23–37** |
| **Mandatory before production Release 1.0** | | **37–58 d** |
| Optional / owner-elective | SS-1 (1–2), S-05 (2–4) | +3–6 |
| Conditional | S-10 tamper-evident audit (D-04) | +5–10 |
| Deferrable to 1.1 | Full M-02 lifecycle (D-23) | 22–35 |

> **Why revision 1 said 18–27.** That figure covered only the SEC band plus P0 — the work arising
> from *this* investigation. It silently excluded the carried findings even though §1.2 of the same
> document correctly called them release-blocking. **The two statements could not both be true.**
> The classification was right; the headline was wrong. **37–58 days is the honest figure.**

## 1.3 Treatment of the five findings you named

**S-11 — TLS. Mandatory before production. Not negotiable, and not an application task.**
Every credential, session token, person record and uploaded document currently crosses the network
in plaintext. Fixing the authorization model while leaving the transport open means an attacker
reads the data without needing authorization at all. It is 2–4 days of *infrastructure* work
(termination, secure cookie flags, HSTS) and does not compete with engineering capacity. **It
cannot be deferred past production on the grounds that it is "a deployment concern".**

**S-01 — Cross-branch document access. Mandatory before production. 11–18 days.**
This is the **same defect class as S-16b**, one layer down: any authenticated officer can read any
uploaded file, including another branch's. Fixing branch scope on the *registers* while leaving the
*documents* open means the data the registers protect is still reachable. `test_upload_access_control.py::test_07`
**returns 200 today** — execution-tested. It needs migration **M-01**, which is the single largest
remaining item. **It is the main reason the honest total is 37–58 rather than 18–27.**

**S-08 — Session expiry. Mandatory before production. 2–3 days.**
Tokens never expire. A token captured once works indefinitely, which defeats P0-WP-2 (revoking
sessions on password reset) — you can revoke a session you know about, but a stolen token you
don't know about never lapses. Cheap, self-contained, and it closes the gap P0-WP-2 half-opens.

**S-09 — Authentication throttling and auth audit. Mandatory before production. 2–3 days.**
No rate limiting and no record of failed logins. PBKDF2 at 600k iterations (delivered in Stage 0)
raises the cost per guess but does not stop an unlimited online attack, and with no auth audit a
sustained attempt leaves no trace. For a police system this is also an accountability gap, not only
a security one.

**S-03 — Suspect-alert correction. Mandatory before production, at the A-13 minimum. 2–3 days.**
Full treatment in **§2**. In short: the authorization work makes alerts *correctly scoped* but
leaves them *permanently uncorrectable*. Shipping a national flag that nobody — including an
administrator — can remove is the single highest human-harm item in this package. The **full**
lifecycle (22–35 d, D-23) may wait; **some** correction path may not.

**S-10 — Mutable audit log. Conditional, and the condition is legal, not technical.**
If alerts, clearances or conduct files are ever used in a proceeding, the audit store must be
tamper-evident, and S-10 becomes mandatory before production. If they are not, it may follow 1.0.
**Decision D-04 / A-6 — legal, not mine.** I have left it as *conditional* rather than choosing.

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
| **Who** may withdraw — administrator, listing officer, or a supervisor rank that does not exist today | **Legal + police authority** (A-3) |
| Whether withdrawal requires a second approver | **Legal + police authority** |
| Maximum alert lifetime before mandatory review (D-23.3: 90 days renewable) | **Legal** (A-2) |
| Whether the listed person may be told | **Legal** (A-4) |
| Whether a disputed identity suspends the flag | **Police authority** (A-5) |
| Whether the audit store must be tamper-evident for evidential use | **Legal** (A-6 / D-04) |
| How the endpoint is built, authorized and audited | **Engineering** |
| Whether `Cleared` and `Withdrawn` are distinct states | **Legal shapes it; engineering implements it** |

**A-13 is deliberately scoped so it needs only the owner decision.** It uses the existing
administrator role, so it does not pre-empt A-3. If legal later rules that a supervisor must
withdraw, A-13's endpoint is re-authorized — not rebuilt.

---

# 3. Authoritative A-18 dependency sequence

## 3.1 The single authoritative statement

> **A-18 prerequisites — complete list, no other section may contradict this:**
>
> **SEC-0 · SEC-2 · SEC-3 · SEC-4 · M-02 Phase A · SEC-1 · SEC-5 · PRE-3**
>
> In plain terms: **the entire SEC band must be complete, and PRE-3 must be confirmed.**

### Why every SEC package, not just SEC-2 and SEC-3

A-18 is **production initialization** — the moment real branch rows are created in a real database.
Revision 1 listed only the packages that cause the *measured* widening (SEC-2, SEC-3) and was
inconsistent about SEC-1 and SEC-5. Corrected reasoning:

| Prerequisite | Why A-18 cannot precede it |
|---|---|
| **SEC-0** | Supplies the three-state model. Without it every scope check can still fail open |
| **SEC-2** | S-14: unresolved postings read everything. Initializing production with that live is indefensible |
| **SEC-3** | **Measured:** A-18 creates no `police_station` branch rows, so `/api/crimes` scope becomes unresolvable and posted officers go from **0 rows to 8 (all)** — scenario D |
| **SEC-4** | Checkpoint branch/location scope; A-18 creates the checkpoint branches A-18 itself provisions |
| **M-02-A** | Alert ownership must exist before alerts are created in a real database |
| **SEC-1** | S-16a leaks every unit register through `GET /api/persons/<id>` with **no precondition**. Initializing production while that is open ships a known-exploitable path |
| **SEC-5** | Staging verification + PRE-4 assignment correction must complete **before** production exists |
| **PRE-3** | `DEFAULT_POLICE_BRANCHES` has **no provenance and is not approved production data**. A-18 must use the authoritative list |

## 3.2 Reconciliation of the three sections

| Section | Revision 1 said | Revision 2 says |
|---|---|---|
| **§3.1 graph** | A-18 after SEC-5, gated by PRE-3 | **Correct** — now states the full chain explicitly |
| **§3.4** | "after SEC-2, SEC-3 and SEC-5, and additionally PRE-3" | **Superseded** — omitted SEC-0, SEC-4, M-02-A and SEC-1 |
| **§4.4** | "gated by SEC-2, SEC-3 and PRE-3" | **Superseded** — omitted SEC-5 and the rest |

All three now defer to §3.1 above.

## 3.3 Full implementation sequence

```
DECISIONS (D-1a, D-1b, D-2, D-3, D-4, D-4b, D-5, D-7)   <- blocks everything
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
          S-01 (M-01, 11-18d) · S-03 (A-13, 2-3d) · S-08 (2-3d) · S-09 (2-3d) · S-11 (TLS, 2-4d)

P0-WP-1 (S-07) and P0-WP-2 (S-02)  — independent, before staging
SS-1 — independent, optional, owner-elective
```

## 3.4 Station removal, and protection of existing station records

**Unchanged from revision 1 and still accurate** — three defences (SEC-3 removes the dependency;
SEC-0 makes unresolvable ⇒ refuse; the ordering gate above), pinned permanently by **T-26**. Six
guarantees protect existing station records: no SEC package issues station DDL; A-18 is
`police_branches` only; no station DELETE route exists in the application; scenario D's deletions
were inside a disposable cluster destroyed at exit; SS-1 changes only future intake; the three
station FKs stay intact.

---

# 4. Test identifiers and counts reconciled

## 4.1 T-44 / T-45 / T-46 — shared tests, **not** duplicated identifiers

There are **46 distinct test identifiers, T-01…T-46, each defined once.** The overlap in revision 1
was in *package assignment*, not numbering: I listed these three under both M-02 Phase A (§5.5) and
SEC-1 (§5.6, "T-36…T-46"). That was ambiguous. Authoritative assignment:

| Test | Asserts | Authored in | **Green after** | Pre-fix expectation |
|---|---|---|---|---|
| **T-44** | Cross-branch CID officer refused alert **content** | M-02 Phase A | **SEC-1** | RED until SEC-1 |
| **T-45** | Checkpoint officer with **no** `cid` module still gets `Flagged match` for an out-of-branch suspect | M-02 Phase A | **Already green — control** | **GREEN before, during and after.** Fails ⇒ the fix over-restricted |
| **T-46a** | Creation refused when the creator's branch is unresolved | M-02 Phase A | **M-02 Phase A** | RED until Phase A |
| **T-46b** | `branch_id IS NULL` ⇒ refuse on read, never "all branches" | M-02 Phase A | **SEC-1** | RED until SEC-1 |

**T-46 has two halves** because the write side lands in Phase A and the read side in SEC-1. They are
sub-parts of one identifier, not new identifiers — **T-46 may not be reported green until both land.**

All three live in **one file**, `backend/test_person_detail_authorization.py`, which is delivered
with M-02 Phase A and completed by SEC-1. **No test is counted twice in the estimates**; the file is
costed once, inside SEC-1's 2–3 days.

## 4.2 The 46 acceptance tests versus the 28-pass / 1-blocked suite

**These measure different things and must never be added together.**

| | **Existing suite** | **The 46 acceptance tests** |
|---|---|---|
| What is counted | **Suite files** | **Individual test cases** |
| Current figure | **29 files: 28 PASS · 0 FAIL · 1 BLOCKED** | **0 executed** |
| Status | Written, running, green today | **Specified only — not written, never run** |
| Covers the authorization fixes? | **No. None of them.** | Yes — that is their entire purpose |
| After delivery | 34 files | 46 cases, distributed across 5 new files |

* **The blocked file** is `backend/test_server.py`, blocked by **N-7 / S-07**. It is *not* passing
  and is not counted as passing.
* **No test in the existing suite verifies any authorization fix**, because no fix exists. A green
  suite today says nothing about S-14, S-15, S-16, S-04, S-17 or S-18.
* **None of the 46 has been executed.** Where this package says a test "must fail pre-fix", that is
  a **requirement on the implementer**, not a measurement. The findings themselves were proven by
  **throwaway probes**, which were deleted — the probes are not part of the suite and were never
  counted in it.

---

# 5. Evidence traceability

**Classification:** **[E1]** execution-tested in the latest investigation · **[E2]** execution-tested
in an earlier investigation (reference given) · **[C]** code-reviewed only · **[N]** not yet verified
in this engagement.

| ID | Severity | Class | Evidence |
|---|---|:--:|---|
| **S-15** | High | **[E1]** | `S15_EXECUTION_VERIFICATION.md` §2–§3, §6–§7 — scenarios A–E, commit `0dc584f` |
| **S-17** | High | **[E1]** | ibid. §4 — `POST` with no `branch_id` → 201, stored NULL |
| **S-18** | High | **[E1]** | ibid. §4 — Buuhoodle-scoped officer → Erigavo branch 12 → 201 |
| **S-19** | Medium | **[E1]** | ibid. §4 — `CRM-2026-SAN-C-01-0006` minted by a Buuhoodle officer |
| **S-16a** | Critical | **[E2]** | `S16_REGISTER_VERIFICATION.md` §2–§5 — 4/4 registers, 27 leak combinations |
| **S-16b** (`/linked-records`) | High | **[E2]** | ibid. §2–§3 |
| **S-16b** (`/documents`, `/audit-history`) | High | **[E2]** | `OWNER_DECISION_SHEET_AUTHORIZATION.md` §6.1 — 4 documents + clearance events to an out-of-branch officer |
| **S-14** | Critical | **[E2]** | `BRANCH_SCOPE_FAIL_OPEN.md` P1–P5; re-confirmed `S15_EXECUTION_VERIFICATION.md` §3 |
| **H-2b** (no branch filter) | High | **[E2]** | `S16_REGISTER_VERIFICATION.md` §5 — same-location/other-branch officer reads the record |
| **H-2b** (unknown location) | High | **[E2]** | Decision sheet §6.2 — `"Atlantis Border Post"` → 201, stored `'atlantis'` |
| **H-2b** (substring) | High | **[E2]** | Decision sheet §6.3 — `South` scope reads a `Southwest` event |
| **S-04** | High | **[E2]** | `S16_REGISTER_VERIFICATION.md` §4 — Erigavo CID reads a Buuhoodle alert, 200 |
| **S-01** | High | **[E2]** | `test_upload_access_control.py::test_07` **returns 200** |
| **S-02** | High | **[E2]** | `test_password_security.py::test_15` passes, proving the session stays live |
| **S-07 / N-7** | High *(op.)* | **[E2]** | P0 probe (`05bac05`): pre-fix 8 pass/4 fail → post-fix 14/0. Also the standing blocked suite |
| **S-12** | High | **[E2]** | `test_password_security.py::test_05`; `server.py:3489` |
| **S-13** | High | **[E2]** | P0 probe: first production run → branches 9, stations/locations/officers 0, users 1 |
| **S-03** | High | **[C]** | Code search: the only `UPDATE suspect_alerts` is the `origin` backfill (`:3232`). **No endpoint exists to test** — absence of a route cannot be probed, only demonstrated by exhaustive search |
| **S-05** | Medium | **[C]** | Root cause isolated (`crimes` as skeleton key, `:8396`). **Not probed** |
| **S-08** | High | **[N]** | Carried from the Phase 2 static register. **Not verified this engagement** |
| **S-09** | High | **[N]** | Carried. **Not verified this engagement** |
| **S-10** | High | **[N]** | Carried. **Not verified this engagement** |
| **S-11** | High | **[N]** | Carried; deployment-level. **Not verified this engagement** |
| **S-06** | — | **[E2]** | Resolved by owner ruling **R-1** |

**Counts: [E1] 4 · [E2] 13 · [C] 2 · [N] 4.**

> **Correction to revision 1.** It said *"Every finding below is execution-tested unless explicitly
> marked"* and §2 of the S-15 report said *"every finding in the authorization package is now
> execution-tested"*. **The second statement is true and the first is not.** The *authorization*
> findings are all execution-tested. **S-08, S-09, S-10 and S-11 are not, and S-03 and S-05 are
> code-reviewed only.** Revision 1 overstated the evidence base for the carried findings.
>
> **S-08/S-09/S-10/S-11 are not in doubt** — they are absence-of-control findings carried from a
> static review — but **they have not been probed in this engagement and must not be presented as
> though they had.** If you want them execution-tested before they are scheduled, that is a
> separate, small investigation (≈0.5–1 d) and I recommend it for S-08 and S-09, where the exact
> current behaviour affects the fix.

---

# 6. The eight open decisions

**Unchanged from revision 1 §2 — reproduced there in full with options, consequences,
dependencies and release impact. No decision has been altered or taken on your behalf.**

| # | Decision | Blocks 1.0 | My recommendation |
|---|---|---|---|
| **D-1a** | Alert ownership = creating CID branch, stored explicitly (R1–R5) | Yes | Approve |
| **D-1b** | National warning also reveals the owning branch name | No | Yes |
| **D-2** | Alert flag stays national | Yes | Keep national *(police authority input)* |
| **D-3** | Cross-branch CID access — **A / B / C** | Yes | A for 1.0, C for 1.1; advise against B |
| **D-4** | M-02 Phase A as a 1.0 dependency | Yes | Approve |
| **D-4b** | A-13 interim admin-only withdraw | **Yes — reclassified in revision 2** | **Approve** — see §2.5 |
| **D-5** | SS-1 — **(i) / (ii) / (iii) / (iv)** | No | (iii) |
| **D-7** | Migration safety procedure | Yes | Approve |

**D-6 is CLOSED** — answered by the S-15 execution (`0dc584f`).

> **One reclassification, flagged explicitly.** Revision 1 marked **D-4b** as *"does not block
> 1.0"*. §1 and §2 of this revision establish that **some** correction capability is mandatory
> before production, and A-13 is the minimum such capability. **D-4b now blocks Release 1.0.**
> This is a change to the *classification*, not to the decision — **the decision remains yours**,
> and you may still reject A-13 and accept the risk, provided that is recorded as an explicit
> accepted risk.

---

# 7. Metadata, repository safety and changed files

## 7.1 Commit and working tree

| Item | Value |
|---|---|
| Branch | `arena/6303ef2f-sentinel-police-management` |
| Revision 1 commit | `c5bfb61` |
| **Revision 2 content commit** | _recorded in the follow-up metadata commit — see below_ |
| `origin/main` | **`a1c2478` — unchanged** |
| `backend/server.py` | sha256 `a8211f4f2222e46f14047f5e4ff3135dd43472f0f8c98578d06293708bb3b9fc` |
| Working tree | clean at commit time |
| Test suite | 29 files — **28 PASS · 0 FAIL · 1 BLOCKED** (N-7), unchanged |

## 7.2 Date discrepancy — explained, not silently reconciled

| Source | Value |
|---|---|
| Session-supplied local date (earlier turns) | **5 November 2026** |
| Sandbox clock (`date -u`), earlier turns | 7–8 November 2026 |
| Sandbox clock (`date -u`), now | **9 November 2026, 15:57 UTC** |
| **Your statement** | **9 November 2026** |

**Conclusion: the sandbox clock was correct and the session-supplied date was stale.** In earlier
turns I changed four documents from 7 November to **5 November** on the strength of the supplied
date. **That was a mistake**, and it is why the corpus now carries two date families.

**Action taken — deliberately minimal:**

* **This document only** is dated **9 November 2026**.
* **All historical dates in evidence and decision documents are preserved unchanged**, including
  the six documents reading "5 November" and the thirteen reading "7 November". Rewriting them
  would destroy the record of when each finding was actually established.
* **No document has been back-dated or forward-dated.**

**Recommended ruling (not applied):** treat **"7 November 2026"** as the correct creation date for
the documents that carry it, and record a one-line erratum in `RELEASE_1_0_REFERENCE_DATA.md` §5
noting that the six "5 November" documents were mis-dated from a stale session clock. **I have not
done this** — it changes historical metadata and is your call.

## 7.3 Compliance

| Restriction | Status |
|---|---|
| No application code altered | ✔ `server.py` sha unchanged |
| No migrations, schema or production configuration changes | ✔ |
| No merge to `main` | ✔ `origin/main` = `a1c2478` |
| Original evidence and decision history preserved | ✔ nothing deleted, back-dated or rewritten |
| Owner decisions unchanged | ✔ — one *classification* change (D-4b), flagged in §6, decision untouched |
| `PROJECT_STATUS.md`, `DECISION_REGISTER.md` | ✔ **not modified** |
| Temporary probes | ✔ all five deleted |

## 7.4 Documentation files changed in revision 2

| File | Change |
|---|---|
| `security/OWNER_REVIEW_PACKAGE.md` | **Rewritten as revision 2** — §1 authoritative blocker table and corrected totals, §2 S-03/D-4b, §3 A-18 sequence, §4 test reconciliation, §5 evidence classification, §7 metadata |
| `security/SECURITY_ISSUE_REGISTER.md` | Evidence-class markers **[E1]/[E2]/[C]/[N]** added to the affected rows; no finding text altered |

**No other file was modified.** In particular: no application code, no test file, no
`PROJECT_STATUS.md`, no `DECISION_REGISTER.md`, and no evidence document.
