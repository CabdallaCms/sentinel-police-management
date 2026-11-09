# Owner Decision Package — REVISION 2

**Document date:** 9 November 2026 · **Status: ALL EIGHT DECISIONS RECORDED.**
**Nothing implemented.**
**Companion:** `security/SECURITY_REMEDIATION_PROGRAMME.md` (the work these decisions gate).

> **How this document is built.** Every decision below is reproduced with its **exact original
> wording**, quoted verbatim from the document where it was first recorded, with the source file
> named. Where I have a recommendation it is labelled as a recommendation and placed **after** the
> options, never inside them. **No decision has been selected, altered or narrowed on your behalf.**
> Two *classifications* have changed since revision 1 of the review package — D-4b and S-05/S-20 —
> and both are flagged explicitly where they appear.
>
> **Revision 2 adds your answers and changes nothing else.** Every option, consequence and
> recommendation from revision 1 is preserved exactly as it was put to you, so that the record
> shows what was offered as well as what was chosen. Your answers appear in **§0** and again as an
> **OUTCOME** box at the end of each decision's section. Where your answer differs from the
> engineering recommendation it is marked **OVERRIDDEN**, never quietly absorbed.

---

## 0. Decisions as recorded — 9 November 2026

**Recorded exactly as you gave them.**

| # | Decision | **Your answer** | vs. recommendation |
|---|---|---|---|
| 1 | **D-3** | **Option A — strict branch access for detailed suspect-alert information** | Matches |
| 2 | **D-1a** | **Explicitly stored branch ownership for every suspect alert** | Matches |
| 3 | **D-1b** | **Do not disclose the owning branch in national warnings** | **OVERRIDDEN** (I recommended disclosure) |
| 4 | **D-2** | **Authorized checkpoint officers receive a minimal national warning and escalation instruction** | Matches, and narrows it |
| 5 | **D-4** | **Phase A ownership-only migration. Alert lifecycle management remains separate** | Matches |
| 6 | **D-4b** | **Crime Unit officers may create suspect records and alerts. Only the authorized Crime Unit supervisor may withdraw national alerts. SystemAdmin must not receive this authority automatically** | **Approved with a changed authority model** |
| 7 | **D-5** | **Crime Unit officers select existing registered police stations. They cannot create stations** | Approved — mandates guard **G-b** |
| 8 | **D-7** | **Fail-closed migration with a manual review worklist for unresolved ownership** | Matches |

### 0.1 What these answers changed

| | Effect |
|---|---|
| **Implementation planning is unblocked** | D-3 was the only decision blocking everything. SEC-0 is fixed at three states; SEC-2, SEC-3, SEC-4, M-02-A, SEC-1, SEC-5, SEC-7 and SS-1 all follow |
| **A-13 grew** | 2–3 d → **4–6.25 d**. Supervisor authority is not administrator authority, and the grant must be stored — **a migration A-13 did not previously need** |
| **SS-1 became mandatory** | Previously optional at 1–2 d; now **1–1.5 d** in the programme |
| **The total moved** | **37–59 d → 40–63.75 d.** `37+2+1 = 40`; `59+3.25+1.5 = 63.75`. Full working in `SECURITY_REMEDIATION_PROGRAMME.md` §3.3 |
| **Three new decisions appeared** | **D-1c** (escalation route, created by D-1b), **D-4c** (alert editing — recorded unresolved at your instruction), **D-5a** (residual station guards) |
| **A-13 is still not buildable** | **D-23.6** has not fixed the terminal state vocabulary, and **D-21** has not defined who the Crime Unit supervisor is. **No role or permission has been invented to work around this** |

---

## 1. Which decisions block what

> **RESOLVED 9 November 2026.** Everything in §1.1 and §1.2 is now answered. The map is retained
> unchanged because it records *why* each decision mattered and which packages each one released.
> The live gate is now `SECURITY_REMEDIATION_PROGRAMME.md` §7.

### 1.1 Blocks **all** implementation — ✅ **ANSWERED (D-3 = Option A)**

| Decision | Why nothing can start |
|---|---|
| **D-3** | It changes the **type signature of SEC-0**, the first package, on which every later package depends. Option **A** needs three states (`UNRESTRICTED` / `GRANTED` / `INDETERMINATE`). Option **B** needs a fourth concept — a role-based unrestricted grant for a role that does not exist yet. Option **C** needs a fifth state, `EXISTENCE_ONLY`, plus an audited request action. **SEC-0 cannot be written, let alone tested, until you choose.** |

### 1.2 Blocks only specific packages — ✅ **ALL ANSWERED**

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

### 2.5 ✅ OUTCOME — recorded 9 November 2026

> **Your answer: Option A — strict branch access for detailed suspect-alert information.**

**Matches the recommendation.** Consequences now fixed:

- **SEC-0 is settled at three states** — `UNRESTRICTED` / `GRANTED` / `INDETERMINATE`. No
  `EXISTENCE_ONLY`, no national CID read role, no role-keyed unrestricted grant.
- **Cost 0 d.** Option A falls out of the model that had to be built anyway. Had you chosen B the
  total would have risen 0.5 d plus a role-model change; C, 1–1.5 d.
- **The one decision blocking all implementation is now closed.** SEC-0 can be written, and with
  it SEC-2, SEC-3, SEC-4, SEC-1.
- A CID officer reading an out-of-branch alert gets **403**. If operational feedback later shows
  this is too rigid, **C remains the upgrade path — not B**, for the reasons in §2.4.

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

#### ✅ OUTCOME — recorded 9 November 2026

> **Your answer: explicitly stored branch ownership for every suspect alert.**

**Matches.** R1–R5 stand in full: owner written at `INSERT`, **stored and never derived**,
`branch_id IS NULL` ⇒ `INDETERMINATE` ⇒ content refused, creation refused when the creator's branch
is unresolved, and ownership unchanged by case reassignment. **M-02-A is unblocked at 1–1.5 d.**
An officer transfer will not silently re-own their alert history.

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

#### ⚠️ OUTCOME — recorded 9 November 2026 · **RECOMMENDATION OVERRIDDEN**

> **Your answer: do not disclose the owning branch in national warnings.**

**This overrides the engineering recommendation, and is recorded as an override rather than
absorbed.** It is a legitimate answer: the reasoning against disclosure is set out in the "No"
column above — with nine CID branches, naming the listing unit can itself reveal what a person is
suspected of, especially to someone stopped repeatedly.

**What follows from it:**

- The alert payload and the checkpoint response **must not contain the owning branch name**. The
  M-02-A and SEC-1 work is specified accordingly.
- **The sequencing constraint falls away.** The hint was the only reason the payload had to wait
  for SEC-4; there is now no routing hint to leak.
- **A gap is created, and it is not an engineering question.** D-2 requires an *escalation
  instruction*, and the system currently writes `action_taken = 'Supervisor contacted'`. With the
  branch withheld, **nothing in the record tells the screening officer which supervisor to
  contact.** The instruction can no longer be derived from the alert.
- **This is raised as new decision D-1c** (`DECISION_REGISTER.md` §1A.1): a fixed national CID
  contact point, a per-checkpoint standing instruction, a reference number to quote, or no routing
  at all. **I have not chosen one, and no routing hint will be added on the assumption that D-1c
  will permit one.** M-02-A proceeds; only the escalation wording waits.

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

#### ✅ OUTCOME — recorded 9 November 2026

> **Your answer: authorized checkpoint officers receive a minimal national warning and escalation
> instruction.**

**Matches, and narrows it usefully.** The flag stays national — a person listed in Buuhoodle is
still flagged in Erigavo. Two details in your wording are now binding:

- **"Authorized"** — the warning is delivered to *authorized checkpoint officers*, not to any
  caller who reaches the endpoint. The authorization check belongs at
  `POST /api/checkpoint-events` and is in SEC-4's scope.
- **"Minimal … and escalation instruction"** — confirms the boundary in §3.2: a boolean plus an
  instruction, with no reason, no case, no narrative. Combined with **D-1b**, also no branch name,
  which is precisely what **D-1c** must now resolve.

**T-45 remains mandatory** — a checkpoint officer with no `cid` module must still receive
`Flagged match` for an out-of-branch suspect. If it ever fails, the fix over-restricted and is a
safety regression. **0 d.**

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

#### ✅ OUTCOME — recorded 9 November 2026

> **Your answer: Phase A ownership-only migration. Alert lifecycle management remains separate.**

**Matches, and states the boundary more clearly than the original option did.** Phase A is
additive ownership only — column, index, backfill worklist, write-time ownership, R4 refusal. The
six-state lifecycle, status transitions, expiry and history stay out of Release 1.0 and remain
with **D-23**. **1–1.5 d. M-02-A unblocked; SEC-1 and A-18 released behind it.**

**One boundary note.** "Lifecycle management remains separate" is not the same as "no withdrawal":
**A-13 is a single terminal action, not lifecycle management**, and you approved it separately
under D-4b. The two decisions are consistent — A-13 adds one transition, not a state machine.

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

#### ✅ OUTCOME — recorded 9 November 2026 · **APPROVED WITH A CHANGED AUTHORITY MODEL**

> **Your answer: Crime Unit officers may create suspect records and alerts. Only the authorized
> Crime Unit supervisor may withdraw national alerts. SystemAdmin must not receive this authority
> automatically.**

**This is an approval, and it rejects the authority model A-13 was originally specified with.**
You did not merely approve A-13 — you answered §4.3's question in the direction §4.3 argued for,
and in doing so settled the *withdraw* half of **D-23.5**.

**Three consequences, all of which increase scope:**

| | Revision 1 (as offered) | **As decided** |
|---|---|---|
| Who withdraws | The administrator | **Only the authorized Crime Unit supervisor** |
| SystemAdmin | Implicitly the holder | **Excluded unless separately and deliberately granted** |
| Schema | *"No schema change beyond M-02 Phase A"* | **A migration is required** to store the grant |

**A-13 moves from 2–3 d to 4–6.25 d.** Working: the original 2.0–3.0 plus 2.0–3.25 for the
authority model (grant storage, audited grant/revoke path, branch isolation of the withdrawal, and
the negative tests that prove SystemAdmin is refused). Itemised as W-70…W-74 in
`SECURITY_REMEDIATION_PROGRAMME.md` §3.1.

**No role or permission has been invented to satisfy this.** You instructed that explicitly, and it
matters, because **the system has no Crime Unit supervisor**:

- `ROLE_CID` (`:1338`) is flat — no supervisor, no rank, no appointment, no command hierarchy.
- **`ROLE_CHIEF` (`:1374`) has not been pressed into service.** It is a reporting role and was
  never defined as a CID command post; treating it as the supervisor would be inventing an
  authority, which is the exact failure D-4b guards against.
- **"Any `ROLE_CID` user" is not the supervisor either** — that would hand the power to every
  investigator.

**So the authority is modelled as a new, explicitly granted permission, `alerts:withdraw`,
stored per user** (control **C-1**), granted and revoked through an audited administrative path
that is **separate from using it** (E-38 vs E-37). When **D-21** defines the CID role structure,
the grant moves to the role **without a second migration**. That is the entire reason for choosing
a permission over a role test, and it is why the **+4–8 d supervisor rank is excluded** from the
estimate rather than hidden inside it.

**Branch isolation, per your instruction and consistent with D-3 = Option A.** The permission is
**not national**. A holder may withdraw **only alerts owned by their own CID branch**, resolved
through SEC-0's `authorize()` like every other alert operation. An alert whose owner is unresolved
is `INDETERMINATE` and the withdrawal is **refused** — it never falls back to permitting. A
cross-branch attempt is a **403**, not a silent no-op.

**Withdrawal is not amendment.** The route sets a terminal status and a reason and **must reject
any attempt to change another field** (T-81). **D-4c — whether an officer may edit an existing
alert — is recorded UNRESOLVED at your instruction**, and no edit capability is designed, costed
or implied anywhere in the programme.

**Creation authority is confirmed and costs nothing.** Crime Unit officers may create suspect
records and alerts; that is current behaviour, now constrained by **R4** (creation refused when
the creator's branch is unresolved).

**Controls C-1…C-9 (§4.5) stand, with C-1 strengthened**: authorization is by the named permission
**and** branch scope, and **never** by `role == 'SystemAdmin'`. **T-78 — a SystemAdmin holding
every module but no explicit grant is refused — is the direct test of this decision and may never
be skipped or weakened.**

> **⛔ A-13 STILL CANNOT BE BUILT.** Two gates remain, neither of them engineering's:
> **D-23.6** must fix the terminal state vocabulary, because A-13 writes one permanent terminal
> value and changing it later mislabels every record it wrote; and **D-21** must define the CID
> role structure before the supervisor can be identified from the data model rather than by
> explicit per-user grant. **D-23.5 is now partially answered** — withdraw is settled, *clear* and
> *reopen* are not.

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

#### ✅ OUTCOME — recorded 9 November 2026

> **Your answer: Crime Unit officers select existing registered police stations. They cannot
> create stations.**

**Approved. This mandates guard G-b unambiguously** — `register_crime()` (`:5294`) and
`register_officer()` (`:4828`) must stop fabricating stations, and both paths must resolve an
existing registered station or refuse. **The measured blast radius is closed on both paths**, which
was the decisive objection to option (i).

**SS-1 moves from optional into the mandatory programme at 1–1.5 d**, and S-19 rides inside it.
`BR-7`-style fabricated codes can no longer reach a permanent `CRM-<year>-<code>-NNNN` file number
(`new_crime_file_number` `:4734`). Tests **T-82…T-85**, including the positive control that a
correctly registered station still files normally.

**One point your wording does not settle, raised rather than assumed — new decision D-5a.**
Your answer maps cleanly onto **G-b**, and is consistent with published options **(ii)** and
**(iii)**, which differ only in whether the refusal message names the administrator remedy. It does
not state whether the other two guards are also in scope:

| Guard | In scope? |
|---|---|
| **G-b** — never create a station at crime or officer registration | ✅ **Yes, explicitly decided** |
| **G-a** — refuse a station with `contact_phone IS NULL` or `created_by IS NULL` | ❓ **Not stated** |
| **G-c** — refuse a station whose `operational_status != 'Active'` | ❓ **Not stated.** Note this closes a *separate* hole: decommissioned stations currently still accept filings |
| **Operator message naming the administrator remedy** | ❓ **Not stated.** This is the only difference between options (ii) and (iii) |

**I have not assumed option (iii) on your behalf.** The approved G-b core is costed at 1–1.5 d; the
residual is **+0.25–0.5 d** and waits on D-5a. (1.0–1.5 plus 0.25–0.5 reaches the 1–2 d band
originally published for option (iii), so nothing has been quietly dropped.)

**PRE-5 remains mandatory regardless** — a wrong station code cannot be corrected once stamped
into a file number.

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

#### ✅ OUTCOME — recorded 9 November 2026

> **Your answer: fail-closed migration with a manual review worklist for unresolved ownership.**

**Matches, and names the two clauses that matter most.** Unresolved rows fail **closed**
(`branch_id IS NULL` ⇒ `INDETERMINATE` ⇒ content refused, **never** "all branches") and go to a
**manual review worklist** — never defaulted to a branch, because a wrong owner grants access
where no owner merely withholds it.

The rest of the procedure is approved with it: **the flag is unaffected** (an unowned alert still
flags nationally, so no safety function is lost while ownership is being classified),
**staging first**, and the **two-lever rollback** in strict order — revert code first, and never
`DROP COLUMN` while enforcement is live.

**Scope note, restated because it widened again with D-4b.** This procedure now governs **four**
migrations: **M-02-A**, **M-01**, **SEC-7's `last_seen_at`**, and **A-13's permission grant
storage** — the last of which did not exist when the procedure was put to you. It is costed once,
as a decision, and never charged per migration.

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

#### ⚠️ OUTCOME — **PARTIALLY ANSWERED** by D-4b, 9 November 2026

> **D-4b settles one of the three verbs: "Only the authorized Crime Unit supervisor may withdraw
> national alerts."**

| Verb | Status |
|---|---|
| **Withdraw** | ✅ **Answered** — the authorized Crime Unit supervisor, branch-scoped, by explicit grant |
| **Clear** | ⛔ **Still open** |
| **Reopen** | ⛔ **Still open** |
| **Suspend** | ⛔ **Still open** (the brief's default gave this to the officer) |

Your answer corresponds to option **(c)** in substance — supervisor-level de-listing authority,
separated from the listing officer — **but without creating a supervisor rank**, which option (c)
assumed and priced at +4–8 d. The structural recommendation was taken: **it is a permission, not a
role**, so when **D-21** defines the CID role structure the grant moves across with no second
migration.

**Clear, reopen and suspend remain with the 1.1 lifecycle** and do not block Release 1.0.

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

#### ⛔ OUTCOME — **STILL OPEN. This is now the single decision blocking A-13.**

The eight approvals did not reach D-23.6, and **A-13 cannot be built without it.** A-13 writes
exactly **one** permanent terminal value into records that may later be produced to a court or
challenged by the person listed. If the vocabulary changes afterwards, every record A-13 wrote is
mislabelled and correcting them requires **a second migration over live alert data**.

**This is the cheapest decision on the list and it has the largest scheduling effect** — it needs
a vocabulary, not analysis. Answering it releases a 4–6.25 d package; leaving it open means
Release 1.0 ships with alerts that still cannot be corrected, which is blocker **B-6**.

---

## 7. Summary — what was decided, and what is still outstanding

### 7.1 Closed, 9 November 2026

| # | Decision | **Your answer** | Effect |
|---|---|---|---|
| **D-3** | Cross-branch CID access | **Option A — strict branch** | SEC-0 fixed at three states. **0 d.** Unblocked everything |
| **D-7** | Migration safety | **Fail-closed + manual worklist** | Governs four migrations. **0 d** |
| **D-1a** | Alert ownership | **Explicitly stored per alert** | M-02-A unblocked. **1–1.5 d** |
| **D-4** | Phase A | **Ownership-only; lifecycle separate** | SEC-1 and A-18 released behind it |
| **D-2** | Alert flag | **Minimal national warning + escalation, to authorized officers** | Flag stays national. T-45 mandatory. **0 d** |
| **D-1b** | Branch name in warnings | **Do not disclose** | **Override recorded.** Creates **D-1c** |
| **D-4b** | Withdrawal authority | **Crime Unit supervisor only; SystemAdmin not automatic** | **A-13: 2–3 d → 4–6.25 d**, plus a grant migration |
| **D-5** | Station safeguards | **Select existing stations; cannot create** | **SS-1 now mandatory, 1–1.5 d.** Creates **D-5a** |

**Corrected total: 40 – 63.75 days** (from 37–59). `37+2+1 = 40`; `59+3.25+1.5 = 63.75`.

### 7.2 Still requiring your decision

| Priority | # | Question | Blocks |
|---|---|---|---|
| **1** | **D-23.6** | Are the six alert states correct; is `Cleared` distinct from `Withdrawn`? | **A-13 (4–6.25 d).** The only decision now blocking a costed package |
| **2** | **D-21** | CID role structure — who *is* the authorized Crime Unit supervisor? | A-13's grant stays explicit and per-user until answered |
| **3** | **D-1c** | What escalation route does the national warning carry, given D-1b? | Alert payload wording in M-02-A / SEC-1 |
| **4** | **PRE-3** | Confirm the CID branch list *(a confirmation, not a decision)* | **A-18**, therefore P0-WP-3 |
| **5** | **SEC-6** | Schedule S-05/S-20, **or** sign a risk acceptance | Nothing technically — but deferring without the signature is not an available option |
| **6** | **M-01 §7 Phase B1** | Approve a revised document-migration rollout | S-01's production rollout. **Still PROHIBITED** |
| **7** | **D-5a** | Are guards G-a and G-c, and the operator remedy message, in SS-1 scope? | +0.25–0.5 d inside SS-1 only |
| **8** | **D-4c** | May an officer edit an existing alert? | **Recorded UNRESOLVED at your instruction.** Nothing is designed or costed |
| **9** | **D-23.5 residual** | Who may **clear** and **reopen**? | 1.1 lifecycle only |
| **10** | **D-04 / A-6** | Legal retention and tamper-evident audit | **S-10** (+5–10 d) |
| **11** | **D-23.1, .2, .3, .4, .7** · **A-1…A-5** | Remaining legal and police authority | 1.1 lifecycle; A-1 underpins D-2 |

**D-6 is CLOSED**, answered by the S-15 execution. **PRE-1…PRE-5** are confirmations owed by HQ and
HR, not decisions.

---

**Nothing has been implemented.** The eight decisions are recorded exactly as you gave them, with
one override and one scope change marked as such. **Implementation begins only on your explicit
approval.**
