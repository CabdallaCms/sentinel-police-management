# Legal and Data-Protection Action Plan

**Status:** draft for owner decision · **Prepared:** 7 November 2026
**Owner of this document:** project owner, with legal counsel / DPO
**Covers decisions:** D-04 (retention and tamper-evident audit), D-05 (DPIA,
lawful basis, subject rights), D-23 (suspect listing), D-24 (evidence chain of
custody), D-27 (authorised post-flag procedure)

---

## 0. Why this document exists, and what it is not

This is the second of the two action plans the owner asked to be prepared **in
parallel with Stage 0**. Legal lead time is estimated at **4–12 weeks** and is
entirely outside engineering control. Several of these decisions must be
settled **before** the corresponding code is designed, because retrofitting
them is far more expensive than designing for them — retention rules and audit
immutability in particular.

**This document is not legal advice.** It is an engineering statement of what
the system can and cannot currently do, what questions counsel must answer, and
what each answer will change in the software. Every item below needs a lawyer
or data-protection officer to close it.

---

## 1. The five legal decisions, and the exposure behind each

### D-04 — retention periods and tamper-evident audit · **Very high**

**What is needed:** a retention period for each of — clearance applications,
identity documents and uploaded scans, checkpoint events, crime cases,
**biometric templates and images**, and audit logs. Plus a ruling on whether
the audit trail must be tamper-evident, and to what standard.

**Current position:**

- **Nothing is ever deleted.** There is no retention mechanism anywhere in the system.
- The audit log is a plain table with **no integrity protection** (finding H-7): a database-level actor can edit or delete audit rows and leave no trace.
- Biometric retention is now in scope because decision D-18 was closed as **BOTH** (clearance *and* criminal identification).

**Why it must be decided early:** retention must be designed in. Adding it
later means writing a migration across every record type, and deciding
retrospectively what to do with data that should already have been destroyed.

**What changes in the code once decided:** a retention/disposal job, a
`retention_class` on each record type, and an append-only or hash-chained
audit store.

### D-05 — DPIA, lawful basis, consent, subject rights · **Very high**

**What is needed:** the lawful basis for processing, a completed DPIA covering
**biometric processing and minors' data**, a consent model where consent is the
basis, and a decision on subject rights (access, correction, erasure, objection).

**One question needs an explicit answer because the system currently assumes
the most permissive one:** *may every role search the entire central person
registry?* Today any authenticated officer can resolve any person in the
national registry. That is a design decision nobody has ratified.

**Current position:**

- No DPIA exists.
- No consent is recorded anywhere.
- No subject-rights mechanism exists (no export, no correction workflow, no erasure).
- Minors are processed today — the clearance flow has a guardian section — with no special handling.
- `resolve_person()` loads **the entire persons table into memory** and scores it; there is no scope limit on who may be searched.

**Why it must be decided early:** a DPIA covering biometrics cannot be produced
in days, and going live without one is a legal exposure, not a technical one.

### D-23 — suspect listing rules · **Very high**

**What is needed:** who may list a person as a suspect, on what evidence
threshold, for how long an alert may remain active, and whether a supervisor
must confirm an identity match before any action is taken.

**Current position — this is the most acute live defect in this group:**

- Suspect alerts are written with status `'Active alert'` and **that value is never changed by any code path**. There is no clear, no expiry, no review.
- **Consequence: a person cleared by CID keeps flagging at every checkpoint, indefinitely.** There is no mechanism to stop it.
- `suspect_alerts` has **no `branch_id`** (finding N-1), so alerts are not scoped to any branch.

**What changes in the code once decided:** an alert lifecycle (states, owner,
expiry, mandatory review), a clear/withdraw path with audit, and a branch
scope column — the latter is a schema change requiring separate approval.

### D-24 — evidence chain of custody, admissibility, disposal · **High**

**What is needed:** the chain-of-custody record required for evidence to be
admissible, integrity requirements, and disposal rules.

**Current position:**

- **No custody record.** Evidence is attached to a case with no record of who handled it, when, or why.
- **No integrity hash.** A stored evidence file can be replaced with no detection.
- Until Stage 0, evidence was **retrievable without any authentication** (finding C-1). **Stage 0 closed the anonymous-access hole (WP-08): a valid session is now required.** However, **any authenticated officer can still read any evidence file, including from another branch** — per-file authorisation needs a document-ownership schema change (finding N-6) and is not yet done.

**What changes in the code once decided:** a custody table, content hashing at
upload, per-file authorisation, and a disposal path.

### D-27 — the authorised post-flag procedure · **Very high**

**What is needed:** what an officer is authorised to do when a person is
flagged — detain, refuse passage, refer, release, or record a false match —
including **the legal basis and maximum duration of any detention**,
notification and custody-record obligations, referral routing and
acknowledgement SLA, and **who may clear a false match**.

**Current position:**

- The system can record **none** of these. There is no detention entity, no
  custody record, no referral routing, and no false-match record.
- With D-18 approving genuine matching, **a wrongful match at a checkpoint can
  lead to a wrongful detention with no record that it happened.**
- Stage 0 removed the worst contributor — the matcher no longer fabricates an
  identification (WP-45g) — but removing a fabricated match is not the same as
  authorising what happens after a real one.

**This decision gates the checkpoint unit entirely.** Building detention
recording before the legal basis is defined would be building the wrong thing.

---

## 2. What Stage 0 changed, and what it did not

Being precise, because these are legal-facing claims:

| Finding | Legal relevance | Status after Stage 0 |
|---|---|---|
| C-1 — uploads readable with no authentication | Evidence and identity documents were world-readable | **Closed.** 401 for anonymous callers, verified by executed test |
| C-2 — nine shared default credentials | Any party could obtain an admin session | **Closed.** No default password exists; verified by executed test |
| C-3 — unsalted SHA-256 passwords | Credential storage below any accepted standard | **Closed.** PBKDF2-HMAC-SHA256, 600,000 iterations, per-password salt |
| M-7 — unvalidated uploads | Arbitrary file types stored and served from the application origin | **Closed.** Allow-list, size cap and content/extension check |
| FPR-902 — fabricated biometric matches | **Wrongful-identification risk** | **Closed.** The fallback is gone; an unknown print now returns no match |
| H-2a — cross-branch document access | Evidence visible across branches | **OPEN.** Authentication now required, but authorisation is not per-file |
| H-7 — mutable audit log | Audit cannot be relied on as a record | **OPEN** — needs D-04 |
| N-1 — suspect alerts never cleared | Indefinite flagging of cleared persons | **OPEN** — needs D-23 |
| D-27 scope — no detention record | No record of a wrongful detention | **OPEN** — needs D-27 |

**No retention, consent, subject-rights or custody capability was added in
Stage 0, and none was in its authorised scope.**

---

## 3. Sequencing

```
Week 0–1    Brief counsel / DPO. Hand over this document and the security findings.
Week 0–1    Decide the registry-search question in D-05 (it is a policy call,
            not a drafting exercise, and it unblocks scoping work).
Week 1–4    D-23 and D-27 drafted — these gate the checkpoint unit and are the
            highest wrongful-detention exposure.
Week 2–8    D-04 retention schedule and audit-integrity standard.
Week 2–10   D-05 DPIA, including biometrics and minors.
Week 4–10   D-24 chain of custody.
Week 8–12   Sign-off and hand-back to engineering.
```

**D-23 and D-27 should be taken first.** They are the two with a live,
ongoing operational consequence: people are flagged indefinitely today, and
there is no authorised, recordable procedure for what happens when they are.

---

## 4. What engineering needs back, in writing

For each decision, a written answer that is specific enough to build from:

1. **D-04** — a table of record type → retention period → disposal method, and whether the audit log must be tamper-evident (and to what standard).
2. **D-05** — the lawful basis; a completed DPIA; whether consent is recorded and how; which roles may search the whole registry; the subject-rights processes the system must support.
3. **D-23** — who may list a suspect; the evidence threshold; maximum alert lifetime; whether supervisor confirmation is mandatory before action; who may clear an alert.
4. **D-24** — the custody fields required for admissibility; integrity requirements; disposal rules.
5. **D-27** — the authorised actions after a flag; the legal basis and maximum duration of detention; notification and custody obligations; referral routing and SLA; who may clear a false match.

---

## 5. Risks

| # | Risk | Consequence | Mitigation |
|---|---|---|---|
| L-1 | Legal work starts after engineering | Retention and audit retrofitted at high cost, or go-live without them | Start now, in parallel — this is why this document exists |
| L-2 | Go-live without a DPIA | Legal exposure for biometric and minors' data | Treat the DPIA as a release gate, not a document to follow up |
| L-3 | D-23 stays open | Cleared people continue to be flagged at checkpoints indefinitely | Prioritise D-23; it has a live operational consequence today |
| L-4 | D-27 stays open while matching is built | A wrongful match leads to a detention with no record | Do not build detention recording before the legal basis exists; do not deploy matching before D-27 |
| L-5 | Retention decided after data accumulates | Data that should have been destroyed already exists | Decide D-04 before the first production record is created |
| L-6 | Real police records used to test | Unlawful processing during development | **Standing instruction already in force: synthetic data only.** All Stage 0 tests use synthetic identities |

---

## 6. Standing constraints reaffirmed

- **No production deployment is authorised.** Nothing in this plan implies one.
- **No real police records may be used for testing.** Every fixture in the Stage 0 suites is synthetic.
- **Database structures must not change silently.** Several items above
  (`suspect_alerts.branch_id`, a custody table, retention columns, a document
  ownership link) are schema changes. Each is documented here and **none has
  been applied.** They require owner approval first.
