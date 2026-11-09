# Owner Decision Sheet — D-21: the authorized Crime Unit supervisor

**Document date:** 9 November 2026 · **Status:** awaiting owner decision. **Nothing implemented.**
**Raised by:** D-4b (*"Only the authorized Crime Unit supervisor may withdraw national alerts"*).
**Companions:** `DECISION_REGISTER.md` §1A · `security/SECURITY_REMEDIATION_PROGRAMME.md` §2.6.

> **Scope note.** D-21 as originally raised is broader than alert withdrawal — it covers case
> assignment and the whole CID capability matrix. This sheet answers **the part D-4b made urgent**:
> *how the system represents the authorized Crime Unit supervisor*. The wider question is presented
> in full in §2 and costed in §7 as Option 4, because you may wish to settle it in one decision.
>
> **I have not invented any institutional position.** No rank, post, title or appointment is
> proposed anywhere in this document. Every option below is a way for the *software* to recognise
> a person **you** designate. Who that person is remains a police-authority decision that software
> cannot make. **`ROLE_CHIEF` is not treated as the Crime Unit supervisor** — §3.2 sets out the
> code-level evidence for why it cannot be.

---

## 1. The exact question and its original wording

### 1.1 D-21 as recorded in the authoritative register

`DECISION_REGISTER.md` §3.2, verbatim:

> | **D-21** | CID role structure — investigator / supervisor / unit chief; who assigns cases; case-level permissions | Add a **CID supervisor** role plus a minimal assignment model (assignee, assigned-by, assigned-at, history). Adopt the capability matrix in `architecture/SYSTEM_ARCHITECTURE.md` §3.2 | Assignment (CRR-3xx), report R-17, the whole permission matrix |

### 1.2 D-21 as first raised, Phase 2

`assessment/DECISION_REGISTER_RECOMMENDATIONS.md`, verbatim:

> | **D-21** | **CID role structure** — investigator / supervisor / unit chief; who assigns cases | **Phase 2** | new | **Release blocker (Crime)** |

and the evidence recorded beside it, verbatim:

> | **D-21** | There is **one** CID role. No investigator, supervisor or unit chief. Case assignment does not exist in any form (`grep assigned_to|investigator|assignee|officer_in_charge` → **0** hits). | Case assignment; investigation workflow; per-officer reporting (R-17); case-level permissions |

and the Phase 2 recommendation, verbatim, **including its own stated cost**:

> | **D-21** | **Add a supervisor role and a minimal assignment model** (assignee, assigned-by, assigned-at, history). | Expands the RBAC matrix, which is already the most intricate part of the system (`rbac_self_test()` exists for a reason). Every new role multiplies the authorization test surface. |

### 1.3 The requirements-level form

`assessment/CRIME_UNIT_REQUIREMENTS.proposed.md`, verbatim:

> | **D-21** | CID role structure: investigator / supervisor / unit chief; who assigns cases; whether case-level permissions are required. |

> | OP-06 | `[NEEDS OWNER APPROVAL]` The CID role structure and whether case-level permissions are required. | **D-21** |

### 1.4 The question this sheet must answer now

**How does the system identify the one person — or the few people — you authorize to withdraw a
national suspect alert, given that no supervisor exists in the data model today?**

---

## 2. The current CID role structure, and exactly what it cannot do

Everything in this section was read from `backend/server.py` at
sha256 `a8211f4f2222e46f14047f5e4ff3135dd43472f0f8c98578d06293708bb3b9fc` and the line numbers
re-verified for this document.

### 2.1 There is one CID role

| Fact | Evidence |
|---|---|
| `ROLE_CID = 'CIDUnit'` — a **single, flat** role | `:1338` |
| Its entire capability set is **one view permission** | `ROLE_PERMISSIONS[ROLE_CID] = {PERM_CID_VIEW}` (`:2070`) |
| No investigator / supervisor / unit chief distinction exists | Phase 2: `grep assigned_to\|investigator\|assignee\|officer_in_charge` → **0 hits** |
| No case assignment exists in any form | as above |

### 2.2 What a `users` row actually contains

Base table (`:222`) — **verified, not recalled**:

```
users(id, username, display_name, role, branch, password_hash, active)
```

plus columns added through the codebase's additive-migration mechanism `ADDED_COLUMNS` (`:458`):
`location_scope` (`:460`), `badge_number` (`:466`), `avatar_path`, `avatar_preset`.

**There is no rank, no appointment, no warrant number, no commission date, no command
relationship and no supervisor pointer.** A user is a username, a role, a branch, an optional
location scope and a badge string. **Nothing in the row can express "this officer holds an
authority over that officer."**

### 2.3 There *is* a real permission system — and it is role-derived

This matters, because it is the mechanism every option below either uses or changes.

| Component | Line | What it does |
|---|---|---|
| `PERM_ANALYTICS_GLOBAL = 'analytics:global'` and five siblings | `:1388–1395` | Capability strings. The in-code comment is explicit: *"Modules gate which PAGES a role can open; permissions gate cross-cutting CAPABILITIES … `has_permission()` is the single lookup"*  (`:1384–1387`) |
| `ROLE_PERMISSIONS` | `:2065` | A Python `dict` mapping **role → set of permissions** |
| `user_permissions(user)` | `:2081` | Returns the union of three role lookups — raw role, normalized role, canonical unit role |
| `has_permission(user, permission)` | `:2092` | **The single check.** One line |
| `require_permission(user, permission)` | `:2096` | The enforcing wrapper |
| Session payload exposes `'permissions'` | `:2884` | The frontend already receives a permission list |

**The decisive property: `user_permissions()` reads the user's *role* and nothing else.** There is
**no per-user permission storage anywhere in the system.** A capability today is held by a *role*,
never by a *person*.

### 2.4 The five limitations that make D-21 unavoidable

1. **No authority can be held by a person.** Only by a role. Designating one officer is currently
   impossible without creating a role that one officer holds — which is a role in name and a
   person in substance.
2. **No hierarchy exists.** Nothing expresses seniority, command or supervision.
3. **Roles are coarse.** Granting a capability to `CIDUnit` grants it to **every** CID officer in
   **every** branch.
4. **Every new role multiplies the authorization test surface** — Phase 2's warning, and
   `rbac_self_test()` (`:2010`) exists precisely because this matrix is the most intricate part of
   the system. A role is not a cheap primitive here.
5. **`users.branch` is a scope, not an authority.** It says where an officer works, never what
   they may decide.

### 2.5 The proposed capability matrix already on file — *proposed, not approved*

`architecture/SYSTEM_ARCHITECTURE.md` §3.2 is headed, verbatim:

> ### 3.2 Target permission matrix *(proposed — requires sign-off, D-21)*

It already contains a **CID supervisor** column, and already assigns it **A** (approve/authorise)
for: *Crime case — assign*, *Crime case — close / reopen*, *Incident ↔ case linking*,
*Evidence — withdraw*, and **Suspect alert — clear / expire**. It also gives **A** on
*Suspect alert — clear / expire* to a **Checkpoint supervisor**.

**This matrix is a proposal awaiting your sign-off and has not been treated as decided
anywhere.** It is reproduced here because adopting it *is* Option 4, and because it shows the
alert-withdrawal authority was already anticipated to sit with a CID supervisor — a convergence
worth knowing, not an argument that the question is settled.

---

## 3. Options for representing the authorized Crime Unit supervisor

### 3.1 The four realistic options

| | **Option 1 — per-user permission grant** | **Option 2 — a new `CIDSupervisor` role** | **Option 3 — a boolean column on `users`** | **Option 4 — the full D-21 structure** |
|---|---|---|---|---|
| **What it is** | `alerts:withdraw` granted to **named individuals**, stored in the database, on top of their existing `CIDUnit` role | A new role sitting beside `CIDUnit`; designated officers are moved into it | `ALTER TABLE users ADD COLUMN alerts_withdraw INTEGER`, set per user | Investigator / supervisor / unit chief, the §3.2 capability matrix, and the assignment model |
| **Who holds the authority** | The individuals you name | Everyone in the role | The individuals you name | Everyone at supervisor level |
| **New role created?** | **No** | Yes — one | **No** | Yes — two or three |
| **Granularity** | Per person, per capability | Per role | Per person, one capability only | Per role, full matrix |
| **Migration** | New table `user_permissions` *(additive)* | `users.role` values change for designated officers *(data migration on live accounts)* | One additive nullable column, using the existing `ADDED_COLUMNS` pattern (`:458`) | Role data migration **plus** assignment tables |
| **Code reach** | **One function** — `user_permissions()` (`:2081`) | `ROLE_CID`-adjacent constants, `ROLE_MODULES` (`:1865`), `ROLE_LABELS` (`:1816`), `ROLE_LOCATION_SCOPE` (`:1908`), `ROLE_PERMISSIONS` (`:2065`), alias tables, `rbac_self_test()` (`:2010`), frontend role lists | `user_permissions()` **plus a special case per column** | All of Option 2, plus assignment endpoints and the full matrix |
| **Reversible?** | **Yes** — revoke a row | Partially — officers must be moved back | Yes — set the column to 0 | Hard |
| **Cost** | **+0 d** *(already priced inside A-13)* | **+0.5 – 1.25 d** over Option 1 | **−0.5 – −1.0 d** under Option 1 | **8 – 15 d**, not decomposed — see §7.4 |

### 3.2 Three things that are **not** options, and why

You instructed that no institutional position be invented and that `ROLE_CHIEF` not be assumed to
be the Crime Unit supervisor. These are the candidates a reader might reach for, with the
code-level reason each one fails.

| Rejected | Why it fails |
|---|---|
| **`ROLE_CHIEF` (`chief_commander`, `:1374`)** | **It is architecturally read-only.** Its permission set is `COMMANDER_PERMISSIONS` (`:1401`), whose in-code comment reads, verbatim: *"The command role's authority: every read capability, zero write capability. `stations:manage` is deliberately ABSENT."* It also carries the marker `PERM_READ_ONLY_GLOBAL` (`:1395`), described in code as *"the holder may READ everything but may never MUTATE anything."* **Giving it a withdrawal authority would contradict the role's own stated invariant and break the read-only tests that enforce it.** Separately — and decisively — nothing in the codebase or the requirements establishes that `chief_commander` is a *Crime Unit* post at all |
| **`ROLE_ADMIN` (`SystemAdmin`, `:1335`)** | **Excluded by your own D-4b decision**, and on the merits set out in `OWNER_DECISION_PACKAGE_R1.md` §4.3: it is a technical deployment account that may be held by an IT contractor, and nothing in the data model records whether its holder is a sworn officer |
| **"Any `CIDUnit` user"** | Grants the authority to **every investigator in every branch** — the opposite of a supervisor control, and a direct contradiction of D-4b's word *"only"* |

**A fourth non-option, recorded because it is tempting and wrong:** inferring authority from
`users.badge_number` prefixes or display-name conventions. A naming convention is not an
authority model, cannot be audited, and would fail silently the first time someone is renamed.

---

## 4. Can a designated user's explicit `alerts:withdraw` work **without** a new supervisor role?

**Yes. Verified against the code, and this is the finding that makes Option 1 viable.**

### 4.1 Why it works cleanly

The permission layer has **exactly one derivation point and one check**:

```
user_permissions(user)        :2081   ← the ONLY place permissions are derived
    └── has_permission()      :2092   ← the ONLY check
            └── require_permission()  :2096
```

Extending `user_permissions()` to union a database-backed grant on top of the role-derived set is
**a change to one function**. Every existing consumer — including the session payload at `:2884`,
which already ships a `permissions` list to the frontend — picks it up with no further change.
No new enforcement path is introduced, which means no new way to get enforcement wrong.

### 4.2 It satisfies D-4b as written

**`ROLE_ADMIN` would not receive the new permission automatically.** This is a matter of fact, not
hope: `ROLE_PERMISSIONS[ROLE_ADMIN] = set(CHIEF_PERMISSIONS)` (`:2066`), and `CHIEF_PERMISSIONS`
(`:1396`) is a **fixed frozenset of five named permissions**. A newly defined
`PERM_ALERTS_WITHDRAW` is not a member, so SystemAdmin does not get it by default.

> **⚠️ A trap that must be closed, disclosed here because it would silently break D-4b.**
> The comment above `ROLE_PERMISSIONS` (`:2060`) reads *"SystemAdmin keeps every permission (it
> already sees everything)"*. **The code does not do that** — it assigns a fixed set. The comment
> and the code disagree. If someone later "corrects" the code to match the comment — for example
> by making SystemAdmin's set computed rather than fixed — **SystemAdmin would silently acquire
> `alerts:withdraw` and your D-4b decision would be violated with no error anywhere.**
> **Mitigation, mandatory:** test **T-78** (a SystemAdmin with every module but no explicit grant
> is refused) becomes a permanent regression guard, and the misleading comment is corrected in the
> same change. Neither is optional.

### 4.3 What it does not solve

Option 1 records **that you authorized a person**. It does not record **why** they are authorized,
because the system still has no concept of rank or appointment. The written standing instruction
required by `OWNER_DECISION_PACKAGE_R1.md` §4.4 — naming the **post**, not the person — remains
necessary. **Software cannot supply it.**

---

## 5. Who may grant and revoke the permission, with audit controls

> **Granting the authority and holding it are different acts, and must stay separate.** D-4b
> excludes SystemAdmin from *holding* the withdrawal authority. It does not say who performs the
> *administrative act* of recording your designation. These are my proposals for your approval —
> **not decisions I have taken.**

### 5.1 Proposed grant model

| Question | Proposal |
|---|---|
| Who performs the grant? | **SystemAdmin**, through a dedicated audited endpoint (**E-38**, separate from the withdraw route **E-37**) — because user administration is already the administrator's function |
| On whose authority? | **Yours, in writing** — the standing instruction naming the post. The administrator executes a designation; they do not originate it |
| Who may revoke? | SystemAdmin, by the same audited path. **Revocation must never be harder than granting** |
| Does the grant expire? | **Open question for you** — see §5.3 |

### 5.2 Audit controls, proposed

| # | Control | Why |
|---|---|---|
| **G-1** | **An administrator may not grant `alerts:withdraw` to their own account.** Self-grant refused, server-side, and audited as an attempt | Without this, the exclusion of SystemAdmin in D-4b is cosmetic: an admin simply grants themselves the permission |
| **G-2** | Every grant and revocation writes an audit row: **actor, subject, permission, reason, timestamp** | A designation is an authority change and must be reconstructable |
| **G-3** | The **reason is mandatory** and must reference the written standing instruction | Ties the technical act to the police authority behind it |
| **G-4** | Grants are **enumerable** — "who currently holds `alerts:withdraw`" is a question with a cheap, exact answer | You cannot supervise an authority you cannot list |
| **G-5** | A **periodic report of holders and of every withdrawal** goes to you | Makes misuse visible, not merely recorded |
| **G-6** | Grant, revocation and use are **three distinct audit actions** | *Granted the power*, *lost the power* and *used the power* must never be conflated |
| **G-7** | Revocation takes effect immediately for existing sessions | Otherwise a revoked holder keeps the authority until logout — and note **S-08**: sessions currently never expire |
| **G-8** | **Optional, for your decision:** a two-person rule on granting | Strongest control; slows legitimate designation |

**G-7 has a dependency worth stating plainly.** Immediate revocation needs session invalidation.
The helper exists — `revoke_user_sessions()` (`:4224`) — and **P0-WP-2** is already wiring it into
the administrator path for **S-02**. Sequencing A-13's grant work after P0-WP-2 means G-7 costs
almost nothing. **Without P0-WP-2, revocation is not immediate**, because a session is valid until
its token is used — and today sessions never expire at all (**S-08**).

### 5.3 One question only you can answer

**Should a grant of `alerts:withdraw` expire automatically** — for example at a fixed interval,
requiring renewal — **or persist until explicitly revoked?** Expiry is a strong control against
authority accumulating silently in accounts nobody reviews. It also means an unrenewed grant
leaves nobody able to correct a wrongful alert. **I have no recommendation; it is a police
operational judgement.** Cost is the same either way (±0.25 d).

---

## 6. How the permission stays restricted to the holder's own branch

**The permission is a capability. It is not, and must never become, a scope.** These are two
different questions and the system must ask both:

```
  1. May this user withdraw alerts at all?     → has_permission(user,'alerts:withdraw')   :2092
  2. May this user withdraw THIS alert?        → SEC-0 authorize() on the alert's branch_id
```

**Both must pass. Either one failing is a 403.**

| Rule | Detail |
|---|---|
| **R-W1** | The permission grants **no scope whatsoever**. `user_permissions()` (`:2081`) is branch-blind by design and must stay that way — the branch test is a **separate, explicit step** in the withdraw handler, never folded into the permission lookup |
| **R-W2** | Scope is resolved by **SEC-0's `authorize()`** against the alert's stored `branch_id` (added by **M-02-A** under D-1a), compared with the holder's `users.branch`. This is the same path every other alert operation uses — **no second authorization mechanism is created** |
| **R-W3** | **Consistent with D-3 Option A** — strict branch. An out-of-branch withdrawal is **403**, not a silent no-op, and not a partial success |
| **R-W4** | **`branch_id IS NULL` ⇒ `INDETERMINATE` ⇒ refuse.** It never falls back to permitting. This is D-7's fail-closed rule applied to a write |
| **R-W5** | **There is no national withdrawal authority in Release 1.0.** If one is ever needed it must be a *separate, separately granted* permission with its own decision — never an exception inside this one |
| **R-W6** | Branch isolation is proven by **T-79** (cross-branch holder refused) and **T-80** (unresolved owner refused), over real HTTP, with a **positive control** that the holder's own-branch withdrawal still succeeds |

**Why R-W1 is stated so firmly.** The system's existing fail-open defect (**S-14**,
`branch_scope_view()` `:2661` returning `None` for both "privileged" and "unresolvable") happened
precisely because a capability question and a scope question were answered by one value. **That
mistake must not be repeated in the authority that corrects wrongful alerts.**

---

## 7. Security consequences, migration requirements and cost, per option

### 7.1 Option 1 — per-user permission grant · **+0 d beyond A-13's current estimate**

| | |
|---|---|
| **Security** | **Least privilege by construction.** Exactly the named individuals hold it, in exactly one branch each. Revocable in one row. Grant metadata (who, when, why) is recordable. **Risk:** the authority is invisible in the role list, so §5.2's G-4 enumeration and G-5 reporting are **required**, not optional |
| **Migration** | One additive table `user_permissions(user_id, permission, granted_by, granted_at, reason)`. No existing column altered, no row rewritten. Governed by **D-7** |
| **Code** | `user_permissions()` (`:2081`) — one function. Plus the grant/revoke endpoint E-38 and the self-grant refusal |
| **Cost** | **Already inside A-13's 4–6.25 d** as items **W-70…W-74**. Choosing Option 1 **adds nothing** to the published total |
| **Test surface** | Small: T-78…T-81 plus a positive control |

### 7.2 Option 2 — new `CIDSupervisor` role · **+0.5 – 1.25 d**

| | |
|---|---|
| **Security** | The authority is **visible in the role list**, which is good for review. **But it is role-wide:** every holder of the role gets it, and there is no way to say "this supervisor may withdraw, that one may not." If the role later acquires other capabilities, withdrawal travels with them silently |
| **Migration** | **`users.role` changes on live accounts** — a data migration on authentication-bearing rows, the riskiest kind here. A wrong value is a login or authorization failure for a real officer |
| **Code** | Wider than it looks: `ROLE_MODULES` (`:1865`), `ROLE_LABELS` (`:1816`), `ROLE_LOCATION_SCOPE` (`:1908`), `ROLE_PERMISSIONS` (`:2065`), the alias tables, `rbac_self_test()` (`:2010`), and the frontend role lists |
| **Cost** | **+0.5 – 1.25 d** over Option 1. **Assumption:** the role carries *only* `alerts:withdraw` beyond `CIDUnit`'s existing set. Any further capability re-opens the §3.2 matrix and is Option 4 |
| **Test surface** | **Materially larger** — Phase 2's warning that *"every new role multiplies the authorization test surface"* is the recorded engineering position, and `rbac_self_test()` exists because of it |

### 7.3 Option 3 — boolean column on `users` · **−0.5 – −1.0 d**

| | |
|---|---|
| **Security** | Works, and is the cheapest. **But it bypasses the permission abstraction**, so `has_permission()` stops being "the single lookup" that the code comment at `:1384–1387` promises. The second capability you ever need per-person requires a second column and a second special case — and that is how permission systems rot |
| **Migration** | Smallest possible: one additive nullable column via the existing `ADDED_COLUMNS` mechanism (`:458`), the pattern already used for `location_scope` and `badge_number` |
| **Code** | `user_permissions()` plus a per-column special case |
| **Cost** | **−0.5 – −1.0 d** relative to Option 1 |
| **Caveat** | **No grant metadata** unless you add `granted_by`, `granted_at` and `reason` columns too — at which point you have built Option 1 badly. **Controls G-2, G-3 and G-4 are not satisfiable by this option as stated** |

### 7.4 Option 4 — the full D-21 structure · **8 – 15 d, not decomposed**

| | |
|---|---|
| **Security** | The **correct long-term answer**. Authority becomes structural, reviewable and consistent across every module instead of a list of exceptions |
| **Migration** | Role data migration on live accounts **plus** new assignment tables |
| **Scope** | Investigator / supervisor / unit chief, the §3.2 capability matrix replacing `PERM_CID_VIEW` for every CID role, and the assignment model (assignee, assigned-by, assigned-at, history) |
| **Also delivers** | Case assignment (**CRR-3xx**), report **R-17**, and **A-3** |
| **Cost** | **8 – 15 d. ⚠️ Stated as an order-of-magnitude band, NOT a decomposed estimate.** Every other figure in this programme is summed from itemised work; this one is not. **Assumptions:** it subsumes A-3 (recorded at +4–8 d, touching every module) and adds the assignment model and matrix rollout. **It must not be treated as equally reliable, and it must be decomposed before it is scheduled** |
| **Schedule effect** | **Would move Release 1.0 by roughly two to three weeks.** That is the real decision here |

### 7.5 Option 5 — Option 1 now, Option 4 at Release 1.1 · **+0 d now, +0.25 – 0.5 d later**

Because the authority is a **named permission** from the outset, moving it into a role later is a
one-line addition to `ROLE_PERMISSIONS` (`:2065`) plus revoking the individual grants. **No second
migration over alert data, and no re-authorization of any call site.** This is the whole reason
control **C-1** specified a permission rather than a role test.

### 7.6 Side-by-side

| | Opt 1 — grant | Opt 2 — role | Opt 3 — column | Opt 4 — full | Opt 5 — 1 then 4 |
|---|---|---|---|---|---|
| Cost vs. current plan | **+0** | +0.5 – 1.25 | −0.5 – −1.0 | **+8 – 15** | **+0** now |
| Per-person control | ✅ | ❌ role-wide | ✅ | ❌ role-wide | ✅ → structural |
| Grant metadata (G-2, G-3) | ✅ | ⚠️ role change only | ❌ | ✅ | ✅ |
| Enumerable (G-4) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Migrates live `users.role` | ❌ | ⚠️ **yes** | ❌ | ⚠️ **yes** | ❌ now |
| Keeps `has_permission()` single | ✅ | ✅ | ❌ | ✅ | ✅ |
| Test-surface growth | small | **large** | small | **large** | small now |
| Delays Release 1.0 | **No** | marginally | ❌ **yes, ~2–3 weeks** | — | **No** |
| Reversible | ✅ one row | partial | ✅ | hard | ✅ |

---

## 8. Recommendation

### **Option 5 — adopt Option 1 now, and settle the full D-21 structure for Release 1.1.**

**Why.**

1. **It costs nothing against the published plan.** A-13's 4–6.25 d already prices exactly this
   work (W-70…W-74). The programme total stays as reported.
2. **It is the only option that is per-person.** D-4b says *"only the authorized Crime Unit
   supervisor"*. Options 2 and 4 grant to a role; if that role ever has two holders and you
   intended one, the software cannot express your decision. Option 1 can.
3. **It does not touch live authentication data.** Options 2 and 4 migrate `users.role` on real
   accounts; a mistake there locks out a serving officer. Option 1 adds rows to a new table and
   changes nothing that exists.
4. **It keeps the permission abstraction intact**, which Option 3 does not. `has_permission()`
   remains the single lookup the code promises at `:1386`.
5. **It does not delay the security remediation.** Option 4 would add roughly two to three weeks
   before a wrongly listed person can be cleared — while **B-6** remains open and alerts stay
   permanent.
6. **It is reversible and upgradeable.** Revocation is one row; promotion to a proper role later
   is one line in `ROLE_PERMISSIONS` with **no second migration**.

**What I am explicitly not recommending.** I am not recommending that D-21's substantive question
be dropped. **Option 4 is the correct long-term answer** and the register is right to call it a
release blocker for the Crime Unit's functional scope — it is the only option that makes authority
structural rather than a list of exceptions. **My recommendation is about sequencing, not merit:**
take the authority you need for A-13 now, in a form that converts into the proper structure
without rework, and decide the structure when it is not sitting on the critical path of a
safety fix.

### Conditions I would attach

| # | Condition |
|---|---|
| **1** | Controls **G-1…G-7** are built with the grant, not after it. **G-1 (no self-grant) is the one that makes D-4b real** |
| **2** | **T-78 is a permanent regression guard**, and the misleading `:2060` comment is corrected in the same change (§4.2) |
| **3** | Branch isolation follows **R-W1…R-W6** — capability and scope are asked separately, and `INDETERMINATE` refuses |
| **4** | A **written standing instruction naming the post** exists before the first grant. The software records your designation; it cannot create the authority |
| **5** | **A-13 sequences after P0-WP-2**, so revocation is immediate (G-7) |
| **6** | D-21's full structure is **scheduled for 1.1, not quietly dropped** — and **decomposed before it is scheduled**, since §7.4 is a band and not an estimate |

---

## 9. What is being asked of you

| # | Question | Options |
|---|---|---|
| **1** | **How is the authorized Crime Unit supervisor represented?** | **Option 1** / Option 2 / Option 3 / Option 4 / **Option 5** *(recommended)* |
| **2** | **Who performs the grant, and on whose written authority?** | §5.1 proposes SystemAdmin executing a written designation from you |
| **3** | **Do you require a two-person rule on granting (G-8)?** | yes / no |
| **4** | **Does a grant expire and need renewal, or persist until revoked?** | §5.3 — *no recommendation offered; operational judgement* |
| **5** | **Is the full D-21 structure scheduled for 1.1?** | yes / defer again |

**Who decides.** Questions 1 and 5 are engineering-shaped and yours to approve. **Questions 2, 3
and 4 are police-authority matters**, and this sheet deliberately offers no recommendation on
question 4.

---

**No institutional position has been invented. `ROLE_CHIEF` has not been treated as the Crime Unit
supervisor. Nothing has been implemented, and no option has been selected on your behalf.**
