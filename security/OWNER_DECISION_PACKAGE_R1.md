# Owner Decision Package — REVISION 1

**Document date:** 9 November 2026 · **Status:** awaiting owner decisions. **Nothing implemented.**
**Companion:** `security/SECURITY_REMEDIATION_PROGRAMME.md` (the work these decisions gate).

> **How this document is built.** Every decision below is reproduced with its **exact original
> wording**, quoted verbatim from the document where it was first recorded, with the source file
> named. Where I have a recommendation it is labelled as a recommendation and placed **after** the
> options, never inside them. **No decision has been selected, altered or narrowed on your behalf.**
> Two *classifications* have changed since revision 1 of the review package — D-4b and S-05/S-20 —
> and both are flagged explicitly where they appear.

---

## 1. Which decisions block what

### 1.1 Blocks **all** implementation

| Decision | Why nothing can start |
|---|---|
| **D-3** | It changes the **type signature of SEC-0**, the first package, on which every later package depends. Option **A** needs three states (`UNRESTRICTED` / `GRANTED` / `INDETERMINATE`). Option **B** needs a fourth concept — a role-based unrestricted grant for a role that does not exist yet. Option **C** needs a fifth state, `EXISTENCE_ONLY`, plus an audited request action. **SEC-0 cannot be written, let alone tested, until you choose.** |

### 1.2 Blocks only specific packages

| Decision | Blocks | Does **not** block |
|---|---|---|
| **D-7** | Every package carrying DDL: **M-02-A**, **S-01/M-01**, **SEC-7** (`last_seen_at`), **SEC-8** if counters are stored | SEC-0, SEC-2, SEC-3, SEC-4, SEC-6, SEC-9, P0-WP-1, P0-WP-2 |
| **D-1a** | **M-02-A** → **SEC-1** → **A-18** | SEC-0, SEC-2, SEC-3, SEC-4, SEC-6…SEC-9, all P0 work |
| **D-4** | **M-02-A** → **SEC-1** → **A-18** | As above |
| **D-2** | **M-02-A** and **SEC-1** behaviour; the **T-45** control | Everything else |
| **D-1b** | The alert **response payload** only, inside M-02-A/SEC-1. Smallest blast radius of the eight | Everything else |
| **D-4b** | **A-13 only** — but A-13 is itself release-blocking | Every other package |
| **D-5** | **SS-1 only** — optional, not release-blocking | Every other package |
| **D-23.5**, **D-23.6** *(legal/police, not among the eight)* | **A-13's authority model and its terminal state value** | Everything else |
| **D-04 / A-6** *(legal, not among the eight)* | **S-10 only** | Everything else |
| **PRE-3** *(not a decision — a confirmation)* | **A-18**, and therefore P0-WP-3 | Everything else |

### 1.3 Decision order I recommend you work in

1. **D-3** — unblocks everything.
2. **D-7**, **D-1a**, **D-4** — unblock the migration-bearing packages.
3. **D-2**, **D-1b** — behaviour and payload, needed before SEC-1 completes.
4. **D-23.5**, **D-23.6** — with your legal adviser; needed before A-13 is **built**.
5. **D-4b** — once 4 is answered, because its authority model depends on it.
6. **D-5** — optional, can follow.

---

## 2. D-3 — cross-branch CID access · **blocks all implementation**

### 2.1 Original wording, verbatim

From `security/OWNER_DECISION_SHEET_AUTHORIZATION.md` §8:

> | **D-3** | Cross-branch CID access | **A** / **B** / **C** | **A** for 1.0, **C** for 1.1. Advise against B |

From §3 of the same document: *"**No option is assumed approved.** All three are live."*

### 2.2 All available options

| | **A — Strict branch** | **B — National CID read role** | **C — Flag + request** |
|---|---|---|---|
| **Definition** | A CID officer reads alert content only for their own branch. Out-of-branch ⇒ `403` | A new named role reads alert content in **every** branch. Ordinary CID officers remain branch-scoped | Out-of-branch CID officers see that an alert **exists** and its **owning branch**, not its content, plus an audited "request access" action |
| **Affected roles** | `ROLE_CID` only | `ROLE_CID` + a **new** role (role-model change) | `ROLE_CID` only |
| **Permitted operations** | Own branch: read/create/update. Other: none | Holder: read **all** branches (read-only). Others as A | Own branch: as A. Other: existence + branch name + request |
| **Security consequence** | Smallest surface. **Fail-closed by construction** | **Recreates today's exposure for whoever holds the role.** Its safety depends entirely on holder discipline — a process control, not a technical one | Small surface; the request trail is itself useful evidence |
| **Operational consequence** | A national investigation needs out-of-band phone calls. Rigid; may drive workarounds | Investigations work smoothly | The officer discovers the right branch instantly and asks |
| **Cost** | **0 d** — falls out of SEC-0 | +0.5 d **plus a role-model change** | +1–1.5 d |

### 2.3 Technical consequence of each option for SEC-0

| Option | What SEC-0 must become |
|---|---|
| **A** | Three states. The model already designed. No extra work |
| **B** | Three states **plus** a role-keyed unrestricted grant, and a new role in `ROLE_MODULES`. The grant must be explicit and enumerable, or it reintroduces exactly the S-14 ambiguity the programme exists to remove |
| **C** | A **fourth** decision state, `EXISTENCE_ONLY`, that returns a boolean and a branch name but no content — plus an audited request action and somewhere to store requests. Every consumer of `authorize()` must handle the new state |

**This is why D-3 blocks everything:** each option produces a different `authorize()` return type,
and SEC-2, SEC-3, SEC-4, SEC-1 and A-13 are all written against it.

### 2.4 Recommendation *(mine, not a selection)*

**A for Release 1.0, C as a 1.1 follow-up. Advise against B.** A costs nothing and is the only
option that is fail-closed by construction. C is the better long-term design but should not delay a
security fix. **B rebuilds the current cross-branch exposure under a nicer name, and there is no
supervisor or seniority model in the system today to constrain who holds it.** If operational
feedback shows A is too rigid, **C is the upgrade path — not B.**

---

## 3. D-1a, D-1b and D-2 — alert ownership, disclosure and the national flag

### 3.1 D-1a — ownership = the creating CID branch, stored explicitly

**Original wording, verbatim** (`OWNER_DECISION_SHEET_AUTHORIZATION.md` §8):

> | **D-1a** | Alert ownership = creating CID branch, stored explicitly (R1–R5) | approve / reject | **Approve** |

**The rules R1–R5 being approved or rejected, verbatim from §1.2 of that document:**

> | **R1** | An alert is owned by the **CID branch of the officer who created it**, written at `INSERT`. |
> | **R2** | Ownership is **stored, never derived**. Not from `case_id` (nullable by design — standalone intelligence listings), not from the creator's current `users.branch` (mutable; an officer transfer would silently re-own their history). |
> | **R3** | `branch_id IS NULL` ⇒ `INDETERMINATE` ⇒ **content refused**. Never "all branches". |
> | **R4** | If the creator's own branch is unresolved, **creation is refused**. An alert cannot be created without an owner. |
> | **R5** | Ownership does not change when the linked case is reassigned, closed or deleted. |

**Options: approve / reject.** **Blocks:** M-02-A → SEC-1 → A-18.

| Option | Technical consequence | Operational consequence |
|---|---|---|
| **Approve** | One additive column + index. Ownership is a fact recorded at creation time and is stable | An officer transfer does not move their alert history. Standalone intelligence listings can be owned |
| **Reject** | Ownership must be **derived at read time** from `crime_cases.branch_id` | `case_id` is nullable by design, so **every standalone intelligence listing becomes permanently `INDETERMINATE`** — invisible even to the unit that created it. And because `users.branch` is mutable, an officer transfer would **silently re-own their entire alert history**, which is an audit defect as much as a security one |

**Recommendation:** approve. R2 is the substantive choice and the reason is transfer-safety.

### 3.2 D-1b — does the national warning also reveal the owning branch name?

**Original wording, verbatim** (`OWNER_DECISION_SHEET_AUTHORIZATION.md` §8):

> | **D-1b** | Does the national warning also reveal the **owning branch name** (routing hint)? | yes / no | **Yes** — low sensitivity, high operational value |

**What the warning reveals today** — this is the code path, not an opinion.
`POST /api/checkpoint-events` runs exactly (`server.py:9597`):

```sql
SELECT 1 FROM suspect_alerts
 WHERE person_id=%s AND role='Suspect' AND alert_status='Active alert' LIMIT 1
```

and sets `screening_result = 'Flagged match'` (else `'No active alert'`) and
`action_taken = 'Supervisor contacted'` (else `'Cleared'`).

**The disclosure boundary, verbatim from §1.3 of the decision sheet:**

> | Revealed to any screening officer, nationally | Restricted to the owning CID branch |
> | **That** the person has an active Suspect alert | `alert_id` |
> | `screening_result = 'Flagged match'` | `role` (Suspect / Witness / Person of interest) |
> | `action_taken = 'Supervisor contacted'` | `origin` (Case Link / Direct Intelligence Listing) |
> | *(optional — see D-1b)* the owning branch **name**, so the officer knows whom to call | `notes` — the free-text reason the person was listed |
> | | `case_id`, case category, case status |
> | | listing officer, creation time, full alert history |
>
> **The warning is a boolean plus a routing hint. It carries no reason, no case and no narrative.**

**Options: yes / no.**

| Option | Consequence |
|---|---|
| **Yes** | The screening officer is told `action_taken = 'Supervisor contacted'` and is currently given **no way to know which supervisor** — in practice, phoning around while a flagged person waits. The branch name makes the instruction executable, and creates an accountable point of contact if the person disputes the listing, which is the practical precondition for D-23.7 ever working |
| **No** | The branch name is itself information about an investigation: it tells the screening officer **where** the person is of interest. With eight stations and nine CID branches, *"Buuhoodle CID listed this person"* can be enough to infer the subject matter, especially for someone stopped repeatedly. The value is also **written into `checkpoint_events`**, a register whose scoping is weaker than the alert's until SEC-4 lands — so the hint would propagate further than the content it substitutes for |

**Engineering constraint, not a decision:** if you answer **yes**, it must **not ship before SEC-4**,
or the routing hint leaks wider than the data it replaces.

**Whose decision:** police authority — who may know which unit is investigating whom — informed by
legal via D-23.7. **Recommendation:** yes, sequenced after SEC-4.

### 3.3 D-2 — does the alert flag stay national?

**Original wording, verbatim** (`OWNER_DECISION_SHEET_AUTHORIZATION.md` §8):

> | **D-2** | Alert **flag** stays national | keep national / branch-scope it | **Keep national** — scoping it is a safety regression |

**The consequences table, verbatim from §2.2 of that document:**

> | **False positive — wrong identity match** | The system matches on `national_id` / `passport_id` / four-part name. A shared or mistyped ID flags the wrong person at every checkpoint in the country. | **Unchanged.** This fix does not improve identity matching. |
> | **Incorrect alert (listed in error)** | Flags nationally, permanently. | **Unchanged until M-02 lifecycle.** |
> | **Withdrawal** | **Impossible. No endpoint exists.** `alert_status` is written once at `INSERT`. | **Still impossible after Phase A** — Phase A adds ownership, not lifecycle. |
> | **Over-restriction** | — | Guarded by test **T-45**: a checkpoint officer with no `cid` module must still receive `Flagged match` for an out-of-branch suspect. |

**Options: keep national / branch-scope it.** **Cost: 0 either way.**

| Option | Consequence |
|---|---|
| **Keep national** | A person listed in Buuhoodle is still flagged when screened in Erigavo. The known harms — false identity matches and erroneous listings — are **unchanged by this choice**; they are addressed by A-13 and the lifecycle, not here |
| **Branch-scope it** | **A suspect stops being flagged the moment they leave the listing region — precisely when they are travelling.** This is a safety regression and it does not reduce the harm, because the harm is carried by the flag's *existence*, not by its reach |

**Whose decision: police authority (A-1), not engineering.** I can tell you what each option costs
and breaks; I cannot tell you whether a suspect should stop being flagged at a regional border.
**Recommendation:** keep national, with **T-45** as the permanent guard against over-restriction.

---

## 4. D-4 and D-4b — Phase A, and the authority to withdraw a national alert

### 4.1 D-4 — M-02 Phase A as a Release 1.0 dependency

**Original wording, verbatim** (`OWNER_DECISION_SHEET_AUTHORIZATION.md` §8):

> | **D-4** | M-02 **Phase A** approved as a Release 1.0 dependency (§4) | approve / defer | **Approve** — 1–1.5 d |

**The exact boundary being approved, verbatim from §4:**

> | **Phase A INCLUDES** | **Phase A EXCLUDES** |
> | `branch_id` column + index (§1.1) | The six-state lifecycle (`Active`/`Suspended`/`Cleared`/`Withdrawn`/`Expired`/`Closed`) |
> | Backfill of existing rows (§7) | Any state-transition endpoint |
> | Writing `branch_id` on alert creation | **Withdraw** and **update** endpoints |
> | Refusing creation when the creator's branch is unresolved (R4) | Automatic expiry / retention (**D-23.3**) |
> | Branch-scoped **reads** of alert content | `status_reason`, `expires_at`, `reopened_from`, append-only history |
> | Tests T-44, T-45, T-46 | A CID supervisor role |
> | **1–1.5 d** | *(blocked on D-23 — legal)* |

**Options: approve / defer.**

| Option | Consequence |
|---|---|
| **Approve** | 1–1.5 d. Alert content becomes branch-scoped; SEC-1 can complete; A-18 is unblocked |
| **Defer** | **SEC-1 cannot complete** — alert reads stay unscoped, so S-04 stays open with a measured live cross-branch read. **A-18 stays blocked**, which blocks production initialization entirely. In practice, deferring D-4 defers Release 1.0 |

**Recommendation:** approve.

### 4.2 D-4b — A-13, interim administrator-only withdrawal · **classification changed, flagged**

**Original wording, verbatim** (`OWNER_DECISION_SHEET_AUTHORIZATION.md` §8):

> | **D-4b** | **A-13** interim admin-only Withdraw (2–3 d) | approve / defer / reject | *Your call* — flagged because 1.0 otherwise ships permanent, uncorrectable flags |

**The caveat as originally recorded, verbatim from §4.1:**

> **One caveat, recorded as a risk rather than a recommendation.** Shipping 1.0 with alerts that
> cannot be withdrawn means an erroneous national flag is permanent. The interim mitigation
> already on the books is **A-13 — an admin-only Withdraw, 2–3 d** — which needs no lifecycle and
> no new role. **I am not asking you to approve it here, but I would be wrong not to put it in
> front of you**, because the authorization fix makes alerts *more* correct without making them
> *correctable*.

> **CLASSIFICATION CHANGE, FLAGGED.** Revision 1 of the review package marked D-4b *"does not block
> 1.0"*. On analysis, some correction capability is **mandatory** before production and A-13 is the
> minimum such capability, so **D-4b now blocks Release 1.0.** The *classification* changed; **the
> decision remains yours**, and rejecting A-13 with a recorded risk acceptance is a legitimate
> answer.

**Options: approve / defer / reject.**

| Option | Consequence |
|---|---|
| **Approve** | +2–3 d. 1.0 ships with one authenticated, authorized, audited action that can stop a wrong alert flagging, with a mandatory reason and an actor on record. **Requires D-23.5 and D-23.6 answered first** (§6) and a written standing instruction (§4.4) |
| **Defer** | 1.0 ships with alerts **nobody can correct — not even an administrator.** A false-positive identity match is permanent and national. The only workaround is direct database editing, which you have prohibited. **Must be recorded as an accepted risk with your signature, not left open as though scheduled** |
| **Reject** | As "defer", permanently. In addition, **D-23.3's retention requirement becomes unimplementable** — an alert cannot expire if nothing can change its status |

### 4.3 **A technical SystemAdmin is not a police authority**

You instructed that this must not be assumed. It is not, and here is the basis.

`ROLE_ADMIN = 'SystemAdmin'` (`server.py:1335`) holds every module. In the data model a user has
`role`, `branch`, `location_scope` and `badge_number` — **and nothing else**. There is no rank
field, no appointment, no warrant number and no command hierarchy; `ROLE_CID` is flat, as D-23.1
records: *"There is no supervisor role in the system today."*

| | **Technical SystemAdmin** | **Operationally authorized police officer** |
|---|---|---|
| What it is | The account that operates the deployment: creates users, edits stations, runs initialization | A post holding a police-authority mandate over a person's status in a criminal intelligence register |
| Where authority comes from | **The software.** Possession of the credential | **Police regulation and law.** An appointment that can be audited, challenged and withdrawn |
| Who may hold it | Anyone the deployment gives it to — **including an IT contractor who is not a sworn officer** | Only the holder of the appointment |
| Accountable to | The system owner | The police service, the courts, and the listed person |
| **Can the system distinguish them?** | **No.** No attribute records whether the holder is sworn, ranked or appointed | — |

**Consequence, stated plainly: A-13 as originally specified would grant the power to clear a
national suspect flag to a technical account.** That is acceptable only as an interim, and only if
you accept in writing that the SystemAdmin credential is held by — or operated strictly on the
written instruction of — a person who holds the operational authority.

### 4.4 Required police/legal authority before an administrator may withdraw an alert

| # | Required before A-13 is **built** | Authority | Why |
|---|---|---|---|
| 1 | **D-23.5** — who may clear, withdraw and reopen | Legal + police | The direct authority question. Until answered, every withdrawal is performed under an authority the police service has never defined |
| 2 | **D-23.6** — are the six states correct; is `Cleared` distinct from `Withdrawn` | Legal + police | A-13 writes **one** terminal value. If the vocabulary changes later, every record A-13 wrote is mislabelled, and correcting them needs a second migration over live alert data |
| 3 | **A-3** — whether withdrawal requires a supervisor rank | Legal + police | That rank does not exist. Creating it is **+4–8 d** and touches every module |
| 4 | **D-23.1** — who may list a suspect | Police | De-listing authority cannot be looser than listing authority |
| 5 | **A written standing instruction**, outside the software | Police authority | Must name the **post** (not the person) holding withdrawal authority, the record required (reason, authorising officer, timestamp), and what happens to withdrawn alerts. **Software cannot supply this** |

### 4.5 Controls that must be built to prevent unauthorized withdrawal

These are engineering commitments, offered for your approval as part of A-13:

| # | Control | Purpose |
|---|---|---|
| **C-1** | Authorization by a **named permission** (`alerts:withdraw`), never `role == 'SystemAdmin'` | The authority can move to a proper supervisor role in 1.1 **without a second migration** and without re-authorizing every call site. The system already works this way for `analytics:global` |
| **C-2** | The permission is **explicitly granted and enumerable** — never implied by holding every module | Prevents the S-14 failure mode (a capability acquired by accident rather than by grant) |
| **C-3** | **Mandatory structured reason**, minimum length, rejected if absent | A withdrawal with no reason is indistinguishable from a mistake or a cover-up |
| **C-4** | **Audit row naming actor, permission used, reason and timestamp**, written in the same transaction | Accountability survives the action |
| **C-5** | The alert row is **never deleted** — only its status changes | The alert *is* the evidence that an error occurred |
| **C-6** | Withdrawal is **branch-scoped** like every other alert operation, except for an explicit unrestricted grant | A branch cannot withdraw another branch's alert by default |
| **C-7** | **Verified through the real endpoint:** after withdrawal, `POST /api/checkpoint-events` returns `No active alert` | The checkpoint handler reads `suspect_alerts` directly (`:9597`); a UI-only suppression would not be caught by anything else |
| **C-8** | A **periodic report of withdrawals** — who withdrew what, when and why — available to the owner | Makes misuse visible rather than merely recorded |
| **C-9** | Withdrawals are **counted and alarmed** if they exceed a threshold | A compromised admin credential withdrawing alerts in bulk should be noticed |

**Recommendation:** approve D-4b **with controls C-1…C-9**, and answer D-23.5/D-23.6 first. If you
defer or reject, record it as a signed accepted risk — it is a legitimate answer, but not a silent
one.

---

## 5. D-5 and D-7 — station safeguards and migration safety

### 5.1 D-5 — SS-1 station safeguards

**Original wording, verbatim** (`OWNER_DECISION_SHEET_AUTHORIZATION.md` §8):

> | **D-5** | SS-1 | **(i)** / **(ii)** / **(iii)** / **(iv)** | **(iii)** |

**The four guards being chosen between, verbatim from `SS1_STATION_SAFEGUARD_OPTIONS.md`:**

> | **G-a** | Refuse to use a station with `contact_phone IS NULL` **or** `created_by IS NULL` at crime intake | Blocks *use* of fabricated rows. Does not stop them being created |
> | **G-b** | `register_crime()` / `register_officer()` call a new `resolve_station_readonly()` that **never creates** | Stops the fabrication at source |
> | **G-c** | Refuse a station whose `operational_status != 'Active'` | Closes a second, unrelated hole: decommissioned stations currently still accept filings |
> | **G-d** | Confirm station codes with HQ before first use (**PRE-5**) | Procedural, not code |

**All four options, verbatim from the decision sheet §5:**

| | **(i) G-a + G-c** | **(ii) all four guards** | **(iii) all four + operator message** | **(iv) G-c only — accept the risk** |
|---|---|---|---|---|
| **Crime registration vs `BR-7`** | **Blocked** (no phone / no `created_by`) | **Blocked** — *"station does not exist"* | **Blocked**, with the remedy named | **Still succeeds**; station fabricated |
| **Officer registration vs `BR-7`** | **Still succeeds — station still fabricated** | **Blocked** | **Blocked**, remedy named | **Still succeeds** |
| **Fabrication stopped?** | **No** — rows keep accumulating | Yes | Yes | No |
| **Decommissioned stations refused** | Yes | Yes | Yes | Yes |
| **Operator experience** | Crime desk blocked with a cause they cannot act on | Blocked; error names a code, not a remedy | Blocked; error names the administrator action | No change |
| **Effort** | 0.5–1 d | 1–2 d | 1–2 d | 0.25 d |

**Blocks: SS-1 only. Not release-blocking.**

**Why (iii), verbatim from §5.1 of the decision sheet:**

> 1. **(i) is the worst of both.** It blocks the crime desk while leaving officer registration
>    fabricating stations — half the measured blast radius untouched, and the junk rows keep coming.
> 2. **(ii) and (iii) cost the same.** The difference is one sentence of error text. The entire
>    operational objection to G-b is "operators will be blocked and won't know why" — refusing to
>    spend that sentence is indefensible.
> 3. **The integrity stake is permanent.** `register_crime()` stamps the station code into
>    `CRM-<year>-<code>-NNNN`. A fabricated station puts an invented code into an **official file
>    number that can never be corrected**.
> 4. **(iv) is coherent and I have kept it on the sheet.** If you judge the workflow disruption
>    unacceptable for 1.0, (iv) is more honest than (i) pretending to be a fix — but it must then be
>    recorded as **accepted risk with your signature**, not left open as though scheduled.

**Related but separate: S-19** — file numbers encode the station *region*, not the filing branch
(`CRM-2026-SAN-C-01-0006` was minted by a Buuhoodle officer). It overlaps SS-1 and is not separately
costed. **PRE-5 remains mandatory regardless of D-5**, because a wrong code cannot be corrected once
stamped into a file number.

### 5.2 D-7 — migration safety procedure

**Original wording, verbatim** (`OWNER_DECISION_SHEET_AUTHORIZATION.md` §8):

> | **D-7** | Migration safety procedure §7 (worklist, fail-closed NULL, two-lever rollback) | approve / amend | **Approve** |

**The procedure being approved, verbatim from §7.2 and §7.3:**

> 1. **Fail closed.** `branch_id IS NULL` ⇒ `INDETERMINATE` ⇒ content refused (**T-46**). Never
>    "all branches" — that is the S-14 mistake this whole package exists to remove.
> 2. **The flag is unaffected.** An unowned alert **still flags nationally at checkpoints**, because
>    the flag is not branch-scoped. **No safety function is lost while ownership is being
>    classified** — only CID content visibility is withheld.
> 3. **Worklist, not a default.** Unresolved rows are listed for manual classification by a CID
>    administrator. **Never defaulted to a branch**; a wrong owner is worse than no owner, because it
>    grants access rather than withholding it.
> 4. **Staging first.** Classification is completed and verified in staging (phases R-C/R-D) before
>    enforcement reaches production — consistent with your ruling that there is no report-only
>    production phase.

> | **1. Code** | Revert the SEC-1 enforcement commit | Alert reads return to current (unscoped) behaviour; column stays, keeps being populated | **None** |
> | **2. Schema** | `ALTER TABLE suspect_alerts DROP COLUMN branch_id;` | Returns the table to its present shape | **Ownership assignments are lost** |
>
> **Rules:** lever 1 may be used alone, at any time, with no data loss — it is the real rollback.
> Lever 2 **must never be used while enforcement is live** (every alert would become
> `INDETERMINATE` and all content would vanish from CID screens). Always revert code first, then
> schema, and only if the column itself is being abandoned.

**Options: approve / amend.** **Blocks:** M-02-A, S-01/M-01, SEC-7, and SEC-8 if it stores counters.

| Option | Consequence |
|---|---|
| **Approve** | One procedure governs every migration in the programme. No per-migration negotiation |
| **Amend** | Tell me which clause to change. **Note:** the procedure now governs **four** migrations, not one — M-02-A, M-01, SEC-7's `last_seen_at`, and possibly SEC-8's counters. An amendment applies to all four |

**Recommendation:** approve, noting the widened scope.

---

## 6. D-23.5 and D-23.6 — the legal decisions that gate A-13

> **Why these appear in a Release 1.0 package at all.** The full six-state lifecycle is deferred to
> 1.1. These two sub-decisions are **not** deferred, because **A-13 writes permanent records against
> both** — an authority it does not have, and a terminal state value that may be wrong.

### 6.1 D-23.5 — who may clear, withdraw and reopen an alert?

**Original wording, verbatim** (`planning/D23_LEGAL_ACTION_BRIEF.md`):

> | **D-23.5** | **Who may clear, withdraw and reopen an alert?** | Determines the transition permission matrix |

**The engineering default offered in that brief, verbatim:**

> | D-23.5 | Supervisor clears, withdraws and reopens; officer may suspend | Separates listing from de-listing authority |

**Options available to you:**

| Option | Technical consequence | Operational consequence |
|---|---|---|
| **(a) Administrator only** *(A-13 as originally specified)* | Cheapest. Uses the existing admin account | **Grants the power to a technical account that may not be a sworn officer** (§4.3). Acceptable only as an interim with a written instruction |
| **(b) The listing officer may withdraw their own** | Small change; ownership is already recorded by M-02-A | Fast correction of one's own error — but no separation of duties, so the same person lists and de-lists |
| **(c) Supervisor withdraws; officer may suspend** *(the brief's default)* | **Requires a supervisor rank that does not exist. +4–8 d, touches every module** | Proper separation of listing from de-listing authority |
| **(d) Two-person rule** | Most work: a request/approve flow and somewhere to store pending requests | Strongest accountability; slowest correction, which matters when a wrongly flagged person is being stopped repeatedly |

**Engineering note:** control **C-1** in §4.5 — a named `alerts:withdraw` permission — lets you
start at **(a)** and move to **(b)**, **(c)** or **(d)** later **without a second migration**. That
is the main reason I recommend it.

**This is a legal and police-authority decision. I have no recommendation on who should hold the
power.** My only recommendation is structural: make it a permission, not a role.

### 6.2 D-23.6 — are the six proposed states correct?

**Original wording, verbatim** (`planning/D23_LEGAL_ACTION_BRIEF.md`):

> | **D-23.6** | **Are the six proposed states correct?** `Active`, `Suspended`, `Cleared`, `Withdrawn`, `Expired`, `Closed` | Determines the state machine. In particular: is **`Cleared`** ("no longer of interest") properly distinct from **`Withdrawn`** ("should never have been listed")? I believe it is, and that the distinction matters to the person and to any later complaint — but it is a policy judgement |

**The engineering default offered in that brief, verbatim:**

> | D-23.6 | Adopt the six states | |

**Options available to you:**

| Option | Technical consequence | Operational consequence |
|---|---|---|
| **(a) Adopt all six** | A-13 writes `Withdrawn`; the 1.1 lifecycle adds the rest with no re-labelling | The record distinguishes *"we were wrong to list you"* from *"you are no longer of interest"* |
| **(b) Collapse `Cleared` and `Withdrawn` into one terminal state** | Simplest; A-13 writes one value | **The record can no longer tell a person, or a court, whether they were wrongly listed or merely no longer of interest.** That distinction is the substance of most complaints |
| **(c) A different vocabulary of your choosing** | A-13 writes whatever you specify | Fine — **but it must be specified before A-13 is built**, because changing it afterwards means a second migration over live alert records |

**Why this blocks A-13 specifically:** A-13 writes exactly **one** terminal value into permanent
records. If that value is later judged wrong, every record it wrote is mislabelled and must be
migrated.

**This is a policy judgement. The brief's author believes `Cleared` and `Withdrawn` are properly
distinct, and so do I — but neither of us decides it.**

---

## 7. Summary — the decisions, in the order I recommend taking them

| Order | # | Decision | Options | Blocks | My recommendation |
|---|---|---|---|---|---|
| 1 | **D-3** | Cross-branch CID access | **A / B / C** | **ALL implementation** | **A** for 1.0, **C** for 1.1; advise against **B** |
| 2 | **D-7** | Migration safety procedure | approve / amend | M-02-A, M-01, SEC-7, SEC-8 | **Approve**, noting it now governs four migrations |
| 3 | **D-1a** | Ownership = creating branch, stored (R1–R5) | approve / reject | M-02-A → SEC-1 → A-18 | **Approve** |
| 4 | **D-4** | Phase A as a 1.0 dependency | approve / defer | M-02-A → SEC-1 → A-18 | **Approve** — 1–1.5 d |
| 5 | **D-2** | Alert flag stays national | keep / branch-scope | M-02-A, SEC-1, T-45 | **Keep national** *(police authority — A-1)* |
| 6 | **D-1b** | Warning reveals the owning branch name | yes / no | Alert payload only | **Yes**, sequenced after SEC-4 |
| 7 | **D-23.5** | Who may clear, withdraw, reopen | (a)/(b)/(c)/(d) | **A-13** | *No recommendation — legal/police.* Structurally: make it a permission |
| 8 | **D-23.6** | Are the six states correct | (a)/(b)/(c) | **A-13** | *Policy judgement.* I agree the distinction matters |
| 9 | **D-4b** | A-13 interim withdrawal | approve / defer / reject | **A-13 (release-blocking)** | **Approve with controls C-1…C-9** |
| 10 | **D-5** | SS-1 station safeguards | (i)/(ii)/(iii)/(iv) | SS-1 only *(optional)* | **(iii)** |

**Also outstanding, not in this package:** **D-04 / A-6** (legal — gates S-10), **D-23.1, .2, .3,
.4, .7** (1.1 lifecycle), **A-1…A-5** (police/legal), and **PRE-1…PRE-5** (confirmations owed by HQ
and HR, not decisions). **D-6 is CLOSED**, answered by the S-15 execution.

**One further choice created by this revision, which is not a numbered decision:** S-05 and S-20
were moved into the mandatory pre-production band on measured evidence. **Either schedule SEC-6
(2–4 d) before production, or record a signed risk acceptance.** Deferring without the signature is
the one option not available, under your own standing instruction.

---

**Nothing has been implemented. No decision has been taken on your behalf. Implementation begins
only on your explicit approval.**
