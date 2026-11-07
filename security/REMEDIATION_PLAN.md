# Remediation Plan — order, estimates and approvals

**Date:** 7 November 2026 · **Status:** **PROPOSAL — awaiting owner approval**
**Companion documents:** `SECURITY_ISSUE_REGISTER.md` · `MIGRATION_PROPOSAL_DOCUMENT_OWNERSHIP.md` ·
`DOCUMENT_AUTHORIZATION_TEST_DESIGN.md` · `CREDENTIAL_ROTATION_PROCEDURE.md` ·
`SUSPECT_ALERT_LIFECYCLE.md`

> **Nothing in this plan has been implemented.** No migration was run and no application code was
> changed. Work begins only on your approval.

---

## 1. Deviations and corrections — read this first

### 1.1 I corrected a wrong statement in the Stage 0 report

The Stage 0 report said `test_server.py` was blocked by finding **N-7**. **That was incomplete and
I should not have asserted it without running the suite to exhaustion.** N-7 is the *final* blocker,
but four other faults sat in front of it. The full chain is in §5.

### 1.2 I changed test files during an investigation-only task

I modified `backend/test_server.py` — five test-only corrections (§5). I judged this to be inside
"prepare tests" and "give a reproducible path to run it". **No application file was changed.**
If you consider this outside scope, revert with:
`git checkout 41b4843 -- backend/test_server.py`

### 1.3 I temporarily applied the N-7 fix, then reverted it

To give you a *verified* unblock path rather than an assertion, I applied the one-line N-7 fix,
ran the suite, then restored the file. **`backend/server.py` is byte-identical to the committed
version** — verified by `sha256sum -c` and `git diff --exit-code`. The result of that experiment is
in §5 and it is the reason I can state the unblock path as fact.

### 1.4 The implementation branch still cannot be created from this session

Standing environment restriction, re-disclosed: this session is bound to
`arena/6303ef2f-sentinel-police-management` and cannot create or push another branch. **Run this
yourself** before any Stage 1 work:

```sh
git branch stage-1-security e7263d7
```

### 1.5 One finding is based on reasoning, not a live run

The **S-05 analytics leak** role-by-role exposure table is derived from reading `ROLE_MODULES` and
the four bundle wrappers. The code path is certain; the exact field list each role sees is inferred.
A test matrix is specified to confirm it. I have flagged it rather than presenting it as measured.

---

## 2. Recommended order

The ordering principle: **stop ongoing harm to members of the public first**, then close
privilege escalation, then reduce exposure, then fix structural weaknesses.

### Priority 0 — do before anything else (days 1–3)

| # | Item | Why first | Days |
|---|---|---|---|
| P0.1 | **S-06** credential rotation assessment | If a pre-`e7263d7` database exists, `admin`/`ChangeMe123!` is live. Costs hours to check. | 0.5–1 |
| P0.2 | **S-07 / N-7** discipline placeholder fix | One line. A suspended officer **cannot be reinstated** today — an ongoing harm to a named person, and it unblocks the whole backend suite. | 0.5 + 1 test |
| P0.3 | **S-02 / H-5** revoke sessions on password reset | ~15 lines. Today a compromised account survives the reset meant to stop it. | 1–2 |

**P0 totals 3–4.5 days and removes two active harms.** I recommend approving P0 as one unit.

### Priority 1 — release-blocking (weeks 1–4)

| # | Item | Days |
|---|---|---|
| P1.1 | **S-03** interim suspect-alert withdrawal (§6 of the lifecycle doc) | 2–3 |
| P1.2 | **S-01** M-01 migration: schema + backfill + reconciliation | 5–8 |
| P1.3 | **S-01** enforcement + the prepared test matrix | 6–10 |
| P1.4 | **S-04** M-02: `branch_id` on alerts | 4–6 |
| P1.5 | **S-05** analytics RBAC gate + full role × bundle matrix | 2–4 |
| P1.6 | **S-08** session expiry and idle timeout | 2–3 |
| P1.7 | **S-09** authentication throttling and lockout | 2–3 |

**P1 totals 23–37 days.**

### Priority 2 — needed before any live deployment (weeks 4–10)

| # | Item | Days |
|---|---|---|
| P2.1 | **S-11** TLS termination and secure cookie flags | 2–4 |
| P2.2 | **S-10** tamper-evident audit log — **needs decision D-04** | 5–10 |
| P2.3 | Full suspect-alert lifecycle — **needs decision D-23** | 22–35 |
| P2.4 | `must_change_password` (M-03) | 2–3 |
| P2.5 | Document read auditing (who opened which file) | 3–5 |

**P2 totals 34–57 days**, and **two of these cannot start until you and your legal adviser answer
D-04 and D-23.** They are not engineering blockers; they are decision blockers.

### Summary

| Band | Days | Gate |
|---|---|---|
| P0 | 3–4.5 | Your approval only |
| P1 | 23–37 | Approval + schema sign-off |
| P2 | 34–57 | Approval + **D-04, D-23** |
| **Total** | **60–98.5** | |

For context: this is security remediation only. It sits inside — not on top of — the
**≈257–506 day** total in `planning/IMPLEMENTATION_ROADMAP.md`. It does not change the
**10-day verdict: NO**.

---

## 3. Exact owner approvals needed

Approve or reject each line. Nothing proceeds without the matching approval.

### Schema changes

| # | Approval | Document |
|---|---|---|
| A-1 | Create the additive `documents` table (M-01 Phase A) | Migration proposal |
| A-2 | Run the M-01 backfill on a restored copy, then on the live database | Migration proposal |
| A-3 | Adopt the four-value visibility class (`branch`/`station`/`national`/`self`) | Migration proposal |
| A-4 | Administrators and the Commander retain unrestricted document read | Migration proposal |
| A-5 | Unknown document → **404**, not 403 (no existence disclosure) | Migration proposal |
| A-6 | Length of the report-only soak before enforcement (recommended: 5 working days) | Migration proposal |
| A-7 | Add `branch_id` + lifecycle columns to `suspect_alerts` (M-02) | Lifecycle spec |
| A-8 | Create `suspect_alert_history` | Lifecycle spec |
| A-9 | Add `must_change_password` to `users` (M-03) | Rotation procedure |

### Code changes

| # | Approval |
|---|---|
| A-10 | Fix N-7 (`server.py:6828`) — one line |
| A-11 | Revoke sessions on administrator password reset (H-5) |
| A-12 | Gate the `'cid'` analytics bundle; remove `crimes` from both OR-lists (S-05) |
| A-13 | Interim administrator-only alert withdrawal, ahead of the full lifecycle |
| A-14 | Session expiry / idle timeout, and the timeout value |
| A-15 | Authentication throttling, and the lockout policy |

### Operational

| # | Approval |
|---|---|
| R-1 | Confirm whether any pre-`e7263d7` database exists |
| R-2 | Authorise the rotation maintenance window (all officers signed out) |
| R-3 | Approve the secure channel for delivering new passwords |
| R-4 | Rotate or deactivate each unused seeded account |

### Decisions that are not mine to make

| # | Decision | Blocks |
|---|---|---|
| D-04 | Audit retention and tamper-evidence | P2.2 |
| D-23 | Suspect listing authority, evidence threshold, maximum alert lifetime, clearing authority | P2.3 |
| D-05 | Data protection impact assessment | Deployment |

---

## 4. What I recommend

1. **Approve P0 now.** Three items, 3–4.5 days, and it ends two active harms — an officer who cannot
   be reinstated, and administrator password resets that do not actually lock an attacker out.
2. **Answer R-1 this week.** One query. If a pre-`e7263d7` database exists, everything else is
   secondary to rotating `admin`.
3. **Put D-23 in front of your legal adviser now.** It is the long pole: 22–35 days of work sits
   behind it, and the current behaviour — a suspect alert that can never be cleared — is the
   finding with the clearest consequence for an innocent person.
4. **Do not deploy.** S-11 (no TLS) alone makes a networked deployment unsafe; credentials and
   police records would cross the network in clear text.

---

## 5. Item 8 — why the remaining suite was blocked, and how to run it

### 5.1 Corrected diagnosis

`test_server.py` (3,200 lines, the largest backend suite) stops at the **first** failed assertion,
so each fault masks the next. Running it to exhaustion revealed **five** faults, not one.

| # | Line | Fault | Class | Status |
|---|---|---|---|---|
| 1 | 668, 1845 | PDF fixtures used `b'x'`, rejected by the Stage 0 magic-number check | **Test** | Fixed |
| 2 | 2626 | Called `sentinel_server.password_hash`; Stage 0 renamed it `hash_password` | **Test** | Fixed |
| 3 | 2698 | PNG fixture `b'\x89PNG x'` — the signature is 8 bytes | **Test** | Fixed |
| 4 | **1015** | **N-7: malformed SQL placeholder list, `server.py:6828` → HTTP 400** | **APPLICATION** | **BLOCKED — needs A-10** |
| 5 | 1072 | Expected 8 stations; `/api/stations` also mirrors 2 branches | **Test** | Fixed |
| 6 | 1245 | Reused the `chief` token after logout | **Test** | Fixed |

Faults 1, 2, 3 and 5 are consequences of Stage 0's own hardening and renaming — the harness was not
updated alongside. **That is my error from Stage 0, not a pre-existing defect.**

Fault 6 is more interesting. The test logged out, logged back in, then kept using the **old** token.
It passed historically because logout did not fully revoke a session — the exact N-8 defect Stage 0
fixed. **This test was passing for the wrong reason, and the N-8 fix correctly broke it.** It is
independent evidence that the N-8 fix works.

### 5.2 Verified reproducible path

Executed on 7 November 2026, with the five test-only fixes applied:

```sh
cd /path/to/sentinel-police-management
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
npm install

# 1. Confirm the single remaining blocker:
cd backend && SENTINEL_BOOTSTRAP_PASSWORD='ChangeMe123!' ../.venv/bin/python test_server.py
#    -> AssertionError (400, {'error': "unsupported format character ',' (0x2c) at index 94"})
#       at test_server.py:1015

# 2. Apply the N-7 fix (ONE line, server.py:6828) — REQUIRES APPROVAL A-10:
#      - placeholders = ','.join('%s' * len(DISCIPLINE_OPEN_STATUSES))
#      + placeholders = ','.join(['%s'] * len(DISCIPLINE_OPEN_STATUSES))

# 3. Re-run:
cd backend && SENTINEL_BOOTSTRAP_PASSWORD='ChangeMe123!' ../.venv/bin/python test_server.py
#    -> ALL BACKEND TESTS PASSED
```

**Step 3 was actually executed, not predicted.** The one-line fix was applied temporarily, the suite
ran to completion with `ALL BACKEND TESTS PASSED`, and `server.py` was then restored
(sha256 verified). The unblock path is therefore confirmed, and `test_server.py` is blocked by
**exactly one** application defect.

### 5.3 Current measured state

```
passed : 28        (27 Stage 0 baseline + test_document_branch_authorization.py)
failed : 0
blocked: 1         test_server.py — N-7, awaiting approval A-10
skipped: 0
```

Reproduce with `SENTINEL_TEST_LOGDIR=/tmp/logs scripts/run-tests.sh`.

**`test_server.py` is still reported BLOCKED, not PASS.** It does not pass on the committed tree,
and I will not record it as passing on the strength of an experiment I reverted.

---

## 6. Honest limitations

- **Every severity here is my engineering judgement**, not the output of a formal risk assessment
  against a policing standard. S-05 is rated Medium because it leaks operational metadata, not
  personal records — you may reasonably rate it higher.
- **No penetration test has been performed.** This triage is source analysis plus targeted executed
  tests. An adversarial assessment would likely find issues this did not.
- **The estimates are engineering days for one competent engineer**, excluding procurement, legal
  lead time, UAT and deployment. They carry the same uncertainty as every other estimate in this
  project: the ranges are wide because the requirements are still open.
- **S-05's per-role exposure table is inferred**, per §1.5.
- **Fixing everything here does not make the system fit for deployment.** It closes the known
  security findings. The biometric matcher (FPR-901), the legal basis (D-05, D-23) and the
  procurement path remain the dominant constraints on a real delivery date.
