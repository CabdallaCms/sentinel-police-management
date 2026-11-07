# Owner Decision Sheet

**Date:** 7 November 2026 · **Revised:** 8 November 2026 · **Status:** **AWAITING DECISIONS — nothing implemented**
**Detail:** `P0_TECHNICAL_CLARIFICATION.md` (exact diffs and tests) · `P0_WORK_PACKAGES.md` (full packages)
**Addendum:** `OWNER_DECISION_SHEET_ADDENDUM.md` (adds A-16a) · `REFERENCE_DATA_SCOPE_ANALYSIS.md` (**A-18 revised**)

> **8 Nov 2026 — A-18 revised, §6.** The earlier A-18 asked you to approve eight police stations
> with their tiers and cell capacities. **Station management is HQ's responsibility, not a CID
> Release 1.0 decision, and that request is withdrawn.** A-18 now asks only which reference data
> production initialization creates for CID. **No station data is deleted or modified.**
> Scope of this release: Fingerprint, Crime, Checkpoint (1.0) and Airport (Phase 2 / 1.1).

> `backend/server.py` is **byte-identical** to commit `e7263d7` —
> sha256 `a8211f4f…b3b9fc`, verified after the testing described below.

---

## Verification status of these decisions

**A-10 and A-11 are no longer proposals on paper.** I applied both fixes to a scratch copy, ran a
purpose-built harness, and reverted. **14 of 14 checks passed.** The same harness run against
today's unmodified code failed exactly the 4 checks the two defects predict.

| | Unfixed code | With A-10 + A-11 |
|---|---|---|
| Close a disciplinary action | **400** (N-7) | 200 |
| Officer with another open action | *unreachable* | **stays `Suspended`** |
| Victim's 2 tokens after admin reset | **200, 200** (alive) | **401, 401** |
| Administrator's own session | 200 | 200 |
| Unrelated officer's session | 200 | 200 |

**A-16…A-19 and A-13 are not yet verified by execution** — they describe code that does not exist
yet. They are specified, not proven.

**One correction, disclosed.** My first run of the reinstatement negative control *failed*, and it
would have been easy to report that as "the fix is unsafe". It was my fixture: I used an action type
`'Reprimand'` that the API rejects, so the "second open action" never existed and the control was
vacuous. Corrected to `'Misconduct'`, plus an added assertion that the fixture really exists before
the control is trusted. **The guard is sound; my test was not.**

---

## 1. A-10 — Fix N-7

**Question:** Do you authorise changing one line in `backend/server.py:6828` so that closing a
disciplinary action succeeds and a suspended officer can be returned to Active duty?

**Options**
- **(a)** Approve as a standalone same-week HR maintenance task.
- **(b)** Approve, but bundle into a larger HR work package later.
- **(c)** Reject / defer.

**Recommended: (a).** One line, no schema change, no new dependency. The pattern
`','.join('%s' * n)` appears **nowhere else** in the codebase (verified by grep across `server.py`
and `vehicles.py`), so the blast radius is a single statement. It also unblocks `test_server.py`,
the last blocked suite — verified: with the fix the suite reports `ALL BACKEND TESTS PASSED`.

**Consequences**
- *Security:* Neutral. The broken statement never executed, so no bad data was written.
- *Operational:* **Removes an active harm.** Today a suspended officer cannot be reinstated through
  the application at all; the only workaround is a hand-edit of the database, which is unlogged.
- *Legal:* An unresolvable suspension affects a named person's employment and pay. The longer it
  stands, the weaker the organisation's position in any employment dispute.

**Reversible:** **Yes, fully.** `git revert` restores the current behaviour. No data migration, no
persistent change.

**Affects:** P0-WP-1 · finding S-07 / N-7 · unblocks `test_server.py`.

---

## 2. A-11 — Revoke sessions on administrator password reset

**Question:** Do you authorise `PATCH /api/admin/users/<id>` to revoke **all** of the target user's
sessions — including the in-process token cache — whenever the password is changed?

**Options**
- **(a)** Revoke all of the target's sessions on password change.
- **(b)** Revoke only the database rows (not the in-memory cache).
- **(c)** Reject / defer.

**Recommended: (a).** **(b) is not a real option** — it is precisely finding N-8, which Stage 0
already fixed for the self-service path. `require_auth()` consults the in-process `TOKENS` dict
*before* the `sessions` table, so deleting rows alone leaves every other browser authenticated until
the server restarts. The existing helper `revoke_user_sessions()` (`server.py:4224`) already does
both correctly; this reuses it rather than inventing a new primitive.

Verified with two concurrent victim sessions: both returned **401** after the reset, while the
administrator's own session and an unrelated officer's session both stayed **200**.

**Consequences**
- *Security:* **Closes the gap directly.** Today an administrator resetting a compromised account's
  password does **not** sign the attacker out — the token is independent of the password. Combined
  with S-08 (no session expiry), that session never dies.
- *Operational:* The target officer must sign in again. That is the intended effect of a reset.
- *Legal:* Being unable to evict a known intruder is difficult to defend after an incident,
  particularly as `/uploads/` reads are not audited (so you could not prove what was accessed).

**Reversible:** **Yes**, with one caveat: a revert does not restore sessions already revoked.
Affected officers sign in again. No data loss.

**Affects:** P0-WP-2 · finding S-02 / H-5 · tightens `test_password_security.py::test_15`.

---

## 3. A-11a — Also revoke when an account is deactivated

**Question:** Should the same revocation also fire when an administrator sets `active = 0`?

**Options**
- **(a)** Yes — revoke on both password change and deactivation.
- **(b)** No — password change only.

**Recommended: (a), but it is genuinely optional.** Deactivation *already* takes effect immediately,
because `require_auth()` filters on `active = 1` on every request — so this is defence in depth, not
a gap being closed. Its real value is the **audit record**: an explicit `REVOKE_SESSIONS` entry
stating when and why the sessions ended, rather than leaving it implicit.

**If you prefer the smallest possible change, choose (b)** and the security fix is unaffected.

**Consequences**
- *Security:* Marginal improvement; removes reliance on one filter being correct everywhere.
- *Operational:* None beyond (a) — a deactivated officer cannot work anyway.
- *Legal:* A clearer audit trail for dismissals and suspensions.

**Reversible:** **Yes, fully.**

**Affects:** P0-WP-2 (optional half).

---

## 4. A-16 — Gate demonstration seeding behind a flag, default OFF

**Question:** Do you authorise introducing `SENTINEL_SEED_DEMO_DATA` so that demonstration accounts
and demonstration records are created **only** when it is explicitly set, with the default being a
clean database?

**Options**
- **(a)** Add the flag, default **off** (production-safe by default).
- **(b)** Add the flag, default **on** (preserves today's behaviour unless disabled).
- **(c)** Remove demonstration seeding entirely.
- **(d)** Reject — keep as is.

**Recommended: (a).** The difference between (a) and (b) is what happens when an operator does
nothing. Today that produces nine fictional officer accounts, three fictional citizens **with
national ID numbers**, and **one active suspect alert that cannot be cleared** (because of S-03).
Safe-by-default is the only responsible choice for a police system. (c) is wrong because the
demonstration dataset is genuinely useful and ~22 test suites depend on it.

**Consequences**
- *Security:* Removes nine known-username accounts from any production install.
- *Operational:* Developers and testers must set one environment variable. The test runner sets it
  automatically, so no suite changes.
- *Legal:* **Fictional persons carrying national ID numbers and a suspect listing should not exist
  in an operational police database.** They are indistinguishable from real records in schema and in
  every report and analytics count.

**Reversible:** **Yes.** The change is additive and flag-gated; reverting restores demo-by-default.
A database already created cleanly is unaffected — it simply has fewer rows.

**Affects:** P0-WP-3 · findings S-13, S-06 (residual).

---

## 5. A-17 — Production initialization creates only the administrator

**Question:** In production mode, should first run create **exactly one** account (`admin`) rather
than all nine role personas?

**Options**
- **(a)** One `admin` account only.
- **(b)** One account per role, with generated passwords.
- **(c)** No accounts; require a separate CLI bootstrap command.

**Recommended: (a).** Every real officer must be created through `POST /api/admin/users` with their
own identity and badge number anyway. Pre-creating eight role-shaped accounts (option b) just
creates eight credentials nobody owns, nobody rotates, and nobody notices being used — the same
class of problem as the original shared default. (c) is cleaner in principle but adds a new
entry point and more to get wrong; it can be revisited later.

**Consequences**
- *Security:* Minimises the initial credential surface to one account.
- *Operational:* The administrator must create real officer accounts before anyone can work. This is
  correct, but it **must be in the go-live checklist** or the system looks broken on day one.
- *Legal:* Every account maps to an accountable individual — a precondition for the audit trail
  meaning anything.

**Reversible:** **Yes** for the code. **Not retroactive:** a database already initialized in
production mode will not grow the other eight accounts if you revert; they would be created
manually.

**Affects:** P0-WP-3 · finding S-13 · `PRODUCTION_INITIALIZATION.md`.

---

## 6. A-18 — Reference data created by production initialization *(REVISED 8 Nov 2026)*

> **REVISED after the owner's scope correction.** The previous version asked you to approve eight
> police stations with their tiers and cell capacities. **That request has been withdrawn.** Station
> management is an HQ responsibility and was never a CID Release 1.0 decision — it reached this
> sheet through a scope error on my part, explained in `REFERENCE_DATA_SCOPE_ANALYSIS.md` §1.
> **No station list, tier or capacity requires your approval.**

**Question:** For production initialization, should the system create **only `police_branches`** —
the reference data the CID authorization model and all four CID units require — and create **no
stations and no checkpoint-location rows**, leaving station provisioning to HQ?

**Options**
- **(a)** `police_branches` only (15 rows). No stations, no `locations` rows. HQ provisions stations.
- **(b)** `police_branches` plus one placeholder station, so the Crime Unit works out of the box.
- **(c)** Status quo — seed branches, locations and all eight stations.

**Recommended: (a).** Verified dependency position:

| Reference data | Required by CID? | Verdict |
|---|---|---|
| `police_branches` | **Yes — all four units.** Every CID table carries `branch_id REFERENCES police_branches(id)`, and branch-scope authorization resolves postings against it | **Create** |
| `locations` (3 rows) | **No. The table is never read** — no `SELECT`, no `/api/locations` endpoint. Checkpoint scoping uses the `CHECKPOINT_LOCATIONS` constant (`server.py:1649`) | **Do not create** |
| `police_stations` (8 rows) | Only the **Crime Unit**, and only that **≥1 row exists** — not which ones. `crime_incidents.station_id` is `NOT NULL` | **HQ provisions — out of CID scope** |

**(b) recreates finding S-13 in another table** — a fictional station in an operational police
database, appearing in every station report and capacity figure, with incidents filed against a
station that does not exist. **(c)** is what produced the scope error.

**Nothing is deleted.** The `police_stations` table, the `locations` table and every existing row
stay exactly as they are — three foreign keys point at `police_stations`, two of them `NOT NULL`.
This decision changes only what a *new production database* creates.

**Consequences**
- *Security:* No fictional operational records; consistent with A-16 and A-17.
- *Operational:* **The Crime Unit cannot record incidents until HQ provisions stations and HR
  registers officers** (dependencies HQ-1/2/3). A sequencing constraint for the go-live checklist,
  not a defect. Fingerprint and Checkpoint are unaffected.
- *Legal:* Avoids fabricated station and detention-capacity records in an operational police system.

**Reversible:** **Yes** for the code. No rows are deleted under any option, so there is nothing to
restore.

**Affects:** P0-WP-3 · acceptance criterion **AC-8 rewritten** (production: `police_branches` = 15,
`police_stations` = 0, `locations` = 0; demonstration mode unchanged) · no change to the 7–9.5 day
P0 estimate.

**Out of CID scope, documented not decided:** HQ-1…HQ-6 in `REFERENCE_DATA_SCOPE_ANALYSIS.md` §3 —
including that `crime_incidents` hard-requires both a station **and** a registered officer, and
that station tier, cell capacity, commander and operational status have no CID function at all.

---

## 7. A-19 — Retain `SENTINEL_BOOTSTRAP_PASSWORD` with a warning

**Question:** Finding S-12: this one variable gives **all nine** seeded accounts the **same**
password, silently. Retain it with a warning, restrict it, or remove it?

**Options**
- **(a)** Retain; emit a loud warning outside demonstration mode.
- **(b)** Retain for demonstration mode only; **ignore it** in production mode.
- **(c)** Remove entirely.

**Recommended: (b), with (a)'s warning as well.** (c) is not viable: ~22 existing suites depend on a
known password supplied this way, and removing it would require rewriting all of them — a large
change with real risk of weakening coverage. (a) alone still permits the unsafe outcome and relies
on an operator reading stderr. **(b) makes the unsafe case structurally impossible in production**
— only one account exists there, so there is nothing to share a password *with* — while keeping the
test path working unchanged.

**Consequences**
- *Security:* Closes the shared-credential path for production while preserving test ergonomics.
- *Operational:* No change for developers. Production operators get a warning if the variable is
  present, and it is ignored.
- *Legal:* Removes a plausible route back to a shared administrative credential.

**Reversible:** **Yes, fully.** Configuration-only behaviour, no persistent effect.

**Affects:** P0-WP-3 · finding S-12 · `test_password_security.py`.

---

## 8. A-13 — Interim suspect-alert withdrawal

**Question:** Do you authorise a narrow, administrator-only ability to withdraw a suspect alert —
with a mandatory reason and an audit entry — **before** the full lifecycle design is settled by
D-23?

**Options**
- **(a)** Approve now, ahead of D-23.
- **(b)** Wait for D-23 and build the full lifecycle once.
- **(c)** Reject.

**Recommended: (a).** This is the single finding with the clearest effect on a member of the public.
**No code path in 10,275 lines ever changes `alert_status`** — the only `UPDATE suspect_alerts`
statement sets `origin`. A person listed in error is flagged at **every** checkpoint, **forever**,
and the police have no lawful mechanism to stop it. The only current remedy is an unlogged manual
database edit.

**It does not pre-empt D-23.** It adds one terminal state and one administrator-only route to an
`alert_status` column that is already free text — **no schema change**. Whatever lifecycle counsel
approves later supersedes it. Cost: 2–3 days against 22–35 for the full lifecycle.

**Consequences**
- *Security:* Introduces a privileged destructive-ish action — hence administrator-only, mandatory
  reason, audited. **Caveat: the audit log is mutable (S-10 / H-7),** so that record is not
  tamper-evident until D-04 is resolved.
- *Operational:* Gives CID and command a real remedy for a mistaken listing.
- *Legal:* **Strongly favourable.** Currently the organisation cannot correct its own error — hard
  to defend in a complaint or challenge. This creates the correction route and the record of who
  exercised it.

**Reversible:** **Code: yes.** **Data: partly** — alerts withdrawn while it is live keep the
`'Withdrawn'` status after a revert, and no code would then read it. They would need manual
reconciliation (a short, enumerable list).

**Affects:** Findings S-03, S-04 · `SUSPECT_ALERT_LIFECYCLE.md` §6 · `D23_LEGAL_ACTION_BRIEF.md` §5.

---

## 9. Decision summary

| # | Decision | Recommended | Reversible | Days |
|---|---|---|---|---|
| **A-10** | Fix N-7 | **(a)** standalone, same week | Yes | 1.5 |
| **A-11** | Revoke sessions on admin reset | **(a)** all sessions, incl. cache | Yes¹ | 1.5–2 |
| **A-11a** | Also revoke on deactivation | **(a)** — optional | Yes | — |
| **A-16** | Flag demo seeding, default off | **(a)** | Yes | } |
| **A-17** | Production = admin only | **(a)** | Yes² | } 2–3 |
| **A-18** | **Branches only; HQ provisions stations** *(revised)* | **(a)** | Yes | } |
| **A-19** | Bootstrap password variable | **(b)** + warning | Yes | } |
| **A-13** | Interim alert withdrawal | **(a)** approve now | Code yes, data partly | 2–3 |
| | | | **Total** | **7–9.5** |

¹ revoked sessions are not restored · ² code reversible, rows already created are not

### Also needed

- **Commit structure:** I recommend **three separate commits on one branch**, one per work package,
  each independently revertible. Confirm or override.
- **Branch:** still yours to create — this session is bound to
  `arena/6303ef2f-sentinel-police-management` and cannot create or push another:

```sh
git branch stage-1-security e7263d7
```

### Not in scope of this sheet

**S-01** (cross-branch documents), **S-05** (analytics RBAC), **S-08/09/10/11** (expiry, throttling,
mutable audit, TLS) remain open and are **not** covered by any decision above. **P0 does not make
the system deployable** — S-11 alone means credentials would cross the network in clear text.

**Per your instruction, `PROJECT_STATUS.md` and `DECISION_REGISTER.md` have NOT been updated. They
will be updated only once you record these decisions.**
