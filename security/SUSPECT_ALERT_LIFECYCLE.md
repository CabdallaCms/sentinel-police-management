# Suspect Alert Lifecycle — specification

**Date:** 7 November 2026 · **Status:** **SPECIFICATION — NOT IMPLEMENTED**
**Addresses:** S-03 (alerts can never be cleared), S-04 (alerts carry no branch)
**Depends on legal decision:** **D-23** (who may list a suspect, evidence threshold, maximum alert
lifetime, whether supervisor confirmation is required) — see `planning/LEGAL_ACTION_PLAN.md`

> No code was written and no migration was executed. This is a specification for owner and legal
> review.

---

## 1. Current behaviour — measured, not assumed

| Fact | Evidence |
|---|---|
| `alert_status` is set to `'Active alert'` at INSERT and **nowhere else** | Only `INSERT` sites are `server.py:3356` (seed) and `server.py:9497` (API) |
| **No code path ever UPDATEs `alert_status`** | The sole `UPDATE suspect_alerts` in the codebase is `SET origin='Case Link'` at line 3232 |
| Only one status value is ever used | Every read filters `alert_status='Active alert'`; no other literal exists |
| There is no DELETE path | No `DELETE FROM suspect_alerts` anywhere |
| Alerts have no branch | `suspect_alerts` DDL (line 299): `alert_id, person_id, case_id, role, alert_status, origin, notes, created_by, created_at` — no `branch_id` |
| Duplicate protection exists | INSERT refuses a second active alert for the same person+case (409) |

**Consequence, stated plainly: a suspect alert is permanent.** Once a person is listed, every
checkpoint that screens them flags them, forever. If CID clears the person, the alert still fires.
If the case is closed, the alert still fires. If the listing was a mistake, there is no way to
withdraw it through the application. The only remedy today is a manual database edit.

This is the clearest example in the system of a defect with a direct human consequence: an innocent
person repeatedly stopped at checkpoints with no mechanism for the police to stop it.

---

## 2. Proposed lifecycle

### 2.1 States

| State | Meaning | Person flagged at checkpoints? |
|---|---|---|
| `Active` | A current, valid alert | **Yes** |
| `Suspended` | Temporarily paused pending review (e.g. identity disputed) | No |
| `Cleared` | The person is no longer of interest. The listing was valid but is now resolved. | No |
| `Withdrawn` | The listing should not have been made (error, wrong identity, insufficient basis) | No |
| `Expired` | The maximum lifetime set by D-23 elapsed without review | No |
| `Closed` | The underlying case concluded; retained for the record | No |

`Cleared` and `Withdrawn` are deliberately distinct. "We investigated and you are no longer of
interest" is not the same statement as "we should never have listed you", and the difference matters
to the person and to any later complaint or legal challenge.

### 2.2 Permitted transitions

```
                    ┌──────────────────────────────────────┐
                    ▼                                      │
   (create) ──► Active ──► Suspended ──────────────────────┘   (resume)
                  │ │
                  │ ├──► Cleared   ──┐
                  │ ├──► Withdrawn ──┤
                  │ ├──► Expired   ──┼──► (reopen, with reason) ──► Active
                  │ └──► Closed    ──┘
                  │
                  └──► (automatic) Expired at max lifetime
```

Rules:

- **Every transition requires a reason.** Free text, mandatory, minimum length enforced.
- **Reopening is always possible** but is a first-class, audited event — never a silent re-INSERT.
  Today a "reopen" would be a new alert row with no link to the original, destroying the history.
- **`Withdrawn` is terminal-by-default.** Reopening a withdrawn alert should require a supervisor,
  because withdrawal means the listing was wrong.
- **No transition ever deletes a row.** The alert is the audit record.

### 2.3 Permissions — **provisional, pending D-23**

| Action | Proposed authority | Notes |
|---|---|---|
| Create `Active` | CID officer | Already the case today |
| `Active → Suspended` | CID officer, or the checkpoint supervisor who disputes the identity | |
| `Active → Cleared` | **CID supervisor** | The listing authority should close it |
| `Active → Withdrawn` | **CID supervisor** | Admission of error — needs seniority |
| `→ Expired` | System (automatic) | |
| `Closed` | CID officer, on case conclusion | Should ideally be automatic when the case closes |
| Reopen | CID supervisor | |
| Reopen a `Withdrawn` alert | CID supervisor + recorded justification | |

**There is no supervisor role in the system today.** `ROLE_CID` is a single flat role. Introducing a
CID supervisor is a role-model change with wide consequences, and it is **a D-23 decision, not an
engineering one.** If legal determines that supervisor confirmation is required, that role must be
added first.

**Until D-23 is answered, these permissions are a proposal and must not be built.**

### 2.4 Audit

Every transition writes an `audit_events` row: actor, alert id, person, from-state, to-state,
reason, timestamp. The alert's own history must be retrievable and displayable — an officer at a
checkpoint seeing a flag should be able to see when it was raised and by whom.

**Caveat:** the audit log is currently mutable (S-10 / H-7). An alert history built on it inherits
that weakness. Decision **D-04** governs whether the audit store must be tamper-evident.

---

## 3. Proposed migration M-02 (additive)

```sql
-- M-02 — additive. PROPOSAL, NOT APPLIED.

-- 1. Branch scope for alerts (finding S-04 / N-1).
ALTER TABLE suspect_alerts
  ADD COLUMN IF NOT EXISTS branch_id INTEGER REFERENCES police_branches(id) ON DELETE SET NULL;

-- 2. Lifecycle columns. Defaults preserve every existing row's meaning.
ALTER TABLE suspect_alerts ADD COLUMN IF NOT EXISTS status_reason   TEXT;
ALTER TABLE suspect_alerts ADD COLUMN IF NOT EXISTS status_changed_at TEXT;
ALTER TABLE suspect_alerts ADD COLUMN IF NOT EXISTS status_changed_by INTEGER REFERENCES users(id);
ALTER TABLE suspect_alerts ADD COLUMN IF NOT EXISTS expires_at      TEXT;
ALTER TABLE suspect_alerts ADD COLUMN IF NOT EXISTS reopened_from   INTEGER REFERENCES suspect_alerts(id);

-- 3. Full transition history — one row per transition, never updated.
CREATE TABLE IF NOT EXISTS suspect_alert_history(
  id          SERIAL PRIMARY KEY,
  alert_id    TEXT NOT NULL REFERENCES suspect_alerts(alert_id) ON DELETE CASCADE,
  from_status TEXT,
  to_status   TEXT NOT NULL,
  reason      TEXT NOT NULL,
  actor_id    INTEGER REFERENCES users(id),
  created_at  TEXT DEFAULT (to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_suspect_alert_history_alert
  ON suspect_alert_history(alert_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_suspect_alerts_status ON suspect_alerts(alert_status);
CREATE INDEX IF NOT EXISTS idx_suspect_alerts_branch ON suspect_alerts(branch_id);
```

### Handling the existing status vocabulary

Existing rows hold the literal `'Active alert'`. Every read filters on that exact string. Changing
it to `'Active'` would silently break every dashboard count and every checkpoint flag.

**Recommended approach — do not rename in place:**

1. Keep `'Active alert'` as the stored value for the Active state. Introduce the new terminal states
   alongside it.
2. Define the canonical set in one constant, as the codebase already does elsewhere:
   `ALERT_STATUSES = ('Active alert', 'Suspended', 'Cleared', 'Withdrawn', 'Expired', 'Closed')`.
3. Change every read from `alert_status = 'Active alert'` to `alert_status = ALERT_ACTIVE`, so the
   literal appears **once**.
4. Only then, if the owner wants the cleaner vocabulary, rename in a separate migration with a
   single `UPDATE`.

This sequencing is what keeps the change additive and reviewable. A rename bundled into the same
step is how a dashboard silently starts reporting zero.

### Backfill

| Column | Backfill |
|---|---|
| `branch_id` | From `crime_cases.branch_id` via `case_id` where present. **Rows with no case cannot be resolved** — they must be listed for manual classification, not defaulted. |
| `status_changed_at` | `created_at` |
| `status_changed_by` | `created_by` |
| `expires_at` | **NULL until D-23 sets a maximum lifetime.** Do not invent one. |
| `suspect_alert_history` | One synthetic `→ Active alert` row per existing alert, reason `'migrated: original listing'` |

The unresolvable `branch_id` rows are a real and expected outcome: alerts can be created with no
case (`origin = 'Direct Intelligence Listing'`). They must be surfaced, not guessed.

---

## 4. API surface (specification)

| Endpoint | Purpose |
|---|---|
| `POST /api/suspect-alerts` | Create — exists today |
| `GET /api/suspect-alerts/<alert_id>` | Read one, including full history — **does not exist today** |
| `PATCH /api/suspect-alerts/<alert_id>` | Transition: `{status, reason}` — **does not exist today** |
| `POST /api/suspect-alerts/<alert_id>/reopen` | Reopen with justification; links `reopened_from` |
| `GET /api/suspect-alerts?status=&branch=&person=` | Filtered list for review workflows |

A **review queue** is also required: alerts approaching `expires_at`, and alerts active beyond a
threshold with no activity. Without it, "maximum lifetime" is a column nobody looks at.

---

## 5. What must be decided before any of this is built

| # | Question | Owner |
|---|---|---|
| D-23.1 | Who may list a suspect? | Legal + command |
| D-23.2 | What evidence threshold justifies a listing? | Legal |
| D-23.3 | **Maximum alert lifetime** — this sets `expires_at` | Legal |
| D-23.4 | Must a supervisor confirm an identity match before action? | Legal + command |
| D-23.5 | Who may clear, withdraw and reopen? Does a CID supervisor role need to exist? | Command |
| D-23.6 | Are the six proposed states right, and is `Cleared` vs `Withdrawn` the right distinction? | Legal + command |
| D-23.7 | What is the person's right to be told they were listed, or de-listed? | Legal (ties to D-05) |

**Nothing in §2–§4 should be implemented until D-23.1 through D-23.6 are answered.** Building a
lifecycle against guessed rules would have to be rebuilt.

---

## 6. Interim mitigation — available now, no migration

If the owner wants the acute risk reduced **before** D-23 concludes, there is a narrow option:

> Add an administrator-only endpoint that sets `alert_status` to `'Withdrawn'` with a mandatory
> reason and an audit row. No new columns; `alert_status` is already free TEXT.

This gives the police a way to stop flagging an innocent person **today**, without pre-empting the
lifecycle design. It is roughly **2–3 engineering days**.

**It requires owner approval** — it is a code change and it introduces a status value, which is a
small but real change to the data vocabulary. I am recommending it be considered, not doing it.

---

## 7. Estimates

| Item | Days |
|---|---|
| Interim withdraw-only mitigation (§6) | 2–3 |
| M-02 migration + backfill + reconciliation of unresolvable rows | 4–6 |
| Lifecycle API + transition rules + audit history | 6–10 |
| Review queue and expiry job | 3–5 |
| UI: alert history, transition controls, review queue | 5–8 |
| Tests across all states, permissions and branch scope | 4–6 |
| **Total (excluding the interim mitigation)** | **22–35** |

Add a CID supervisor role, if D-23.5 requires one: **+4–8 days**, and it touches the role model
used by every module.
