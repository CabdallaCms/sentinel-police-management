# D-23 Legal Action Brief — Suspect Listing and Alert Lifecycle

**Date:** 7 November 2026 · **Status:** **BRIEF FOR LEGAL COUNSEL — decision required**
**Audience:** the owner, the legal adviser, and the CID / command stakeholder who owns the policy
**Companion:** `security/SUSPECT_ALERT_LIFECYCLE.md` (the engineering specification this unblocks)
**Related:** `planning/LEGAL_ACTION_PLAN.md` · decisions **D-04**, **D-05**, **D-24**, **D-27**

> This is a brief for a legal decision, not legal advice. I am an engineer describing what the
> system does and what it cannot do. The questions in §4 need a lawyer's answer.

---

## 1. Why this is urgent

**D-23 is the longest pole in the security remediation plan: 22–35 engineering days sit behind it**,
and none of that work can responsibly start until the questions in §4 are answered. Building a
suspect-alert lifecycle against guessed rules would have to be rebuilt.

But the schedule is the smaller reason. The larger one:

> **A suspect alert in Sentinel today is permanent and cannot be withdrawn by any user.**

This is not a design choice. It is a defect. And it has a direct effect on members of the public.

---

## 2. What the system does today — verified, not assumed

Established by direct code reading of `backend/server.py` (10,275 lines):

| Fact | Evidence |
|---|---|
| An alert is created with `alert_status = 'Active alert'` | `server.py:9497` (API), `:3356` (seed) |
| **No code path anywhere changes `alert_status`** | The only `UPDATE suspect_alerts` in the entire codebase sets `origin`, at `:3232` |
| No alert is ever deleted | No `DELETE FROM suspect_alerts` exists |
| Only one status value is ever used | Every read filters `alert_status = 'Active alert'`; no other literal appears |
| Alerts carry **no branch** | `suspect_alerts` DDL (`:299`) has no `branch_id` — any CID officer in any branch sees every alert |
| Alerts carry no lifecycle fields | No `cleared_at`, `cleared_by`, `closed_at`, `reopened_at`, no reason field |
| There is no listing authority check beyond role | Any CID officer may list any person |
| There is no evidence threshold | `notes` is free text and optional |
| There is no expiry | Nothing ages an alert out |
| There is no review queue | No officer is ever prompted to revisit a listing |

### The practical consequence

A person listed as a suspect is flagged at **every** checkpoint screening, **indefinitely**:

- If CID investigates and clears them — the alert still fires.
- If the case is closed — the alert still fires.
- If the listing was a **mistake** or a **mistaken identity** — the alert still fires.
- If the person is later convicted and has served a sentence — the alert still fires.

**The only way to stop it is for someone with database access to edit the table by hand.** That
action would be unlogged, unauthorised by any procedure, and performed by whoever happens to hold
the credentials.

A further compounding fact: the **audit log is mutable** (finding S-10 / H-7, decision D-04). Even
the record of who listed a person, and when, can be altered without trace.

### Scale, in context

The demonstration seed creates one such alert against a fictional person on first run (finding
S-13). In an operating deployment the count grows and nothing ever removes an entry. **The suspect
register is append-only by accident, not by policy.**

---

## 3. What legal counsel needs to weigh

I am flagging these as areas of exposure for counsel to assess. I am not asserting the legal
position.

1. **Lawful basis for listing.** On whose authority is a person added to a police watch list, and
   what evidential standard applies? Today: any CID officer, no stated threshold, no supervisor.
2. **Proportionality and duration.** An indefinite listing with no review is likely to be hard to
   defend. Most comparable regimes impose a maximum period and a periodic review.
3. **Right of rectification.** A person wrongly listed has no route to correction, because the
   police themselves have none.
4. **Accountability of the record.** With a mutable audit log, the organisation cannot reliably
   evidence who listed a person or when — in a complaint, an appeal, or a court.
5. **Consequence at the checkpoint.** A flag triggers a stop. Repeated stops of an innocent person
   are a foreseeable, recurring harm, not a one-off error.
6. **Cross-branch visibility.** With no `branch_id`, an alert raised in one branch is actionable by
   every branch — widening the effect of any single officer's decision.
7. **Data protection.** Overlaps with **D-05** (DPIA). A suspect listing is a high-risk processing
   activity under most data-protection frameworks.

---

## 4. Decisions required

Engineering cannot proceed on items D-23.1 to D-23.6. They are policy and law, not design.

| # | Question | Why engineering is blocked |
|---|---|---|
| **D-23.1** | **Who may list a suspect?** Any CID officer, or only a supervisor? | Determines the permission model. **There is no supervisor role in the system today** — `ROLE_CID` is flat. Adding one costs **+4–8 days** and touches every module |
| **D-23.2** | **What evidential threshold justifies a listing?** | Determines whether a mandatory structured justification field is required at creation, and what it must contain |
| **D-23.3** | **What is the maximum lifetime of an alert?** | Sets `expires_at`. **Without a number, the column cannot be populated and the expiry job cannot be written.** I will not invent a duration |
| **D-23.4** | **Must a supervisor confirm an identity match before action is taken at a checkpoint?** | Determines whether the checkpoint flow needs a confirmation step before a stop escalates |
| **D-23.5** | **Who may clear, withdraw and reopen an alert?** | Determines the transition permission matrix |
| **D-23.6** | **Are the six proposed states correct?** `Active`, `Suspended`, `Cleared`, `Withdrawn`, `Expired`, `Closed` | Determines the state machine. In particular: is **`Cleared`** ("no longer of interest") properly distinct from **`Withdrawn`** ("should never have been listed")? I believe it is, and that the distinction matters to the person and to any later complaint — but it is a policy judgement |
| **D-23.7** | **Does a person have a right to be told they were listed, or de-listed?** | Determines whether a notification obligation exists. Ties to **D-05** |

### Recommended defaults, if counsel has no contrary view

Offered so the decision has a starting point, not as a recommendation to skip the legal review:

| # | Suggested default | Reasoning |
|---|---|---|
| D-23.1 | CID officer may list; **supervisor confirmation within 72 hours** or the alert auto-suspends | Keeps operational speed, adds accountability |
| D-23.2 | Mandatory free-text justification, minimum length, linked to a case where one exists | Minimum defensible record |
| D-23.3 | **90 days**, renewable once by a supervisor with a reason | A number counsel can move; it makes the system buildable |
| D-23.4 | Yes for any action beyond recording the screening | A flag should not by itself authorise detention |
| D-23.5 | Supervisor clears, withdraws and reopens; officer may suspend | Separates listing from de-listing authority |
| D-23.6 | Adopt the six states | |
| D-23.7 | Defer to counsel — no engineering default offered | Genuinely a legal question |

---

## 5. The interim decision you can take now

Full lifecycle implementation is **22–35 days** and waits on the answers above. **One narrow
mitigation does not:**

> An administrator-only endpoint that sets an alert to `Withdrawn`, with a mandatory reason and an
> audit entry. No schema change — `alert_status` is already free text.

**Effect:** gives the police a way to **stop flagging an innocent person today**.
**Cost:** 2–3 engineering days (approval **A-13**).
**Does it pre-empt D-23?** No. It adds one terminal state and an administrator-only route. Whatever
lifecycle counsel approves later supersedes it.

**I recommend approving this independently of D-23**, because the alternative — the current
position — is that the organisation has no lawful mechanism to correct its own error.

---

## 6. What happens after the decision

| Phase | Work | Days | Gate |
|---|---|---|---|
| Interim | Administrator withdrawal (§5) | 2–3 | **A-13 only** |
| M-02 | `branch_id` + lifecycle columns + `suspect_alert_history` | 4–6 | A-7, A-8 |
| Lifecycle | Transition rules, permissions, audit history | 6–10 | **D-23.1, .5, .6** |
| Review | Expiry job and review queue | 3–5 | **D-23.3** |
| UI | Alert history, transition controls, review queue | 5–8 | |
| Tests | All states, permissions, branch scope | 4–6 | |
| *(conditional)* | CID supervisor role | +4–8 | **D-23.1, .5** |
| | **Total** | **22–35** *(+4–8)* | |

### Backfill note for counsel

When `branch_id` is added, alerts created with **no case** (`origin = 'Direct Intelligence
Listing'`) **cannot have a branch derived** — there is nothing to derive it from. Those rows will be
listed for manual classification rather than defaulted. The number is not knowable today because no
operational database exists (**R-1**), but the procedure must exist before the first one does.

---

## 7. Recommended next steps

1. **Send §2, §3 and §4 to the legal adviser this week.** §2 is the factual position and is
   verified; §3 and §4 are what they need to rule on.
2. **Approve A-13** (interim withdrawal) without waiting for counsel.
3. **Have the CID/command stakeholder answer D-23.1, D-23.5 and D-23.6 in parallel** — they are
   operational policy and need not wait for a legal opinion.
4. **Treat D-23.3 as the critical answer.** Everything about expiry and review is blocked on a
   single number.

**Cost of delay:** each week without D-23 defers 22–35 days of work that is release-blocking, and
extends the period in which a wrongly listed person has no remedy.
