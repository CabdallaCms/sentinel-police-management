# Owner Decision Sheet — Addendum

**Date:** 7 November 2026 · **Commit:** `05bac05` · **Status:** **AWAITING DECISIONS**
**Parent:** `OWNER_DECISION_SHEET.md` (unchanged) · `P0_TECHNICAL_CLARIFICATION.md` (unchanged)

> Answers to the four confirmations requested before the eight decisions are recorded.
> **One of them raises a ninth decision, A-16a — please record it alongside the other eight.**
> Nothing implemented. `backend/server.py` byte-identical to `e7263d7`
> (sha256 `a8211f4f…b3b9fc`).

**Note on paths:** these documents are in **`security/`**, not `planning/`. Full paths:
`security/OWNER_DECISION_SHEET.md`, `security/P0_TECHNICAL_CLARIFICATION.md`,
`security/OWNER_DECISION_SHEET_ADDENDUM.md`. I have not created duplicates under `planning/`,
which would split the record.

---

## C-1. The eight reference stations under A-18 — exact current values

Read from `backend/server.py:3287–3298`. These are what A-18 keeps or excludes.

| # | `station_id` | Name | Code | Region | District | Village | **Tier** | **Cells** |
|---|---|---|---|---|---|---|---|---|
| 1 | ST-001 | Ceerigaabo Central Station | SAN-C-01 | Sanaag | Ceerigaabo | Ceerigaabo | **Regional HQ** | **24** |
| 2 | ST-002 | Badhan Station | SAN-C-02 | Sanaag | Badhan | Badhan | **District HQ** | **12** |
| 3 | ST-003 | Caynabo Station | SOO-C-03 | Sool | Caynabo | Caynabo | **District HQ** | **10** |
| 4 | ST-004 | Las Anod Station | SOO-C-01 | Sool | Laascaanood | Laascaanood | **Regional HQ** | **20** |
| 5 | ST-005 | Burao Station | TOG-C-01 | East Togdheer | Burao | Burao | **Regional HQ** | **24** |
| 6 | ST-006 | Oodweyne Station | TOG-C-02 | East Togdheer | Oodweyne | Oodweyne | **District HQ** | **12** |
| 7 | ST-007 | Buuhoodle Station | ETG-C-03 | East Togdheer | Buuhoodle | **Widh Widh** | **Outpost** | **6** |
| 8 | ST-008 | Adhi Cadeeye Outpost | SOO-C-02 | Sool | Laascaanood | Adhi Cadeeye | **Checkpoint** | **4** |

**Total cell capacity: 112.** Tiers: 3 Regional HQ · 3 District HQ · 1 Outpost · 1 Checkpoint.

### The other reference data A-18 also covers

| Kind | Rows | Detail |
|---|---|---|
| `police_branches` | **15** | 3 branches × 5 unit types (`fingerprint`, `crime`, `checkpoint`, `airport`, `police_station`): **Buuhoodle Branch** (East Togdheer/Buuhoodle), **Lasanod Branch** (Sool/Laascaanood), **Erigavo Branch** (Sanaag/Ceerigaabo). Idempotent — `ON CONFLICT DO NOTHING` |
| `locations` | **3** | `South` → South Checkpoint · `East` → East Checkpoint · `West` → West Checkpoint, kind `Checkpoint` |

### Points to check before you answer A-18

1. **Code inconsistency, not a defect:** ST-007 Buuhoodle uses prefix **`ETG-`** while ST-005/ST-006
   in the same region use **`TOG-`**. Probably a typo in the original seed. Say which is correct and
   I will align it.
2. **ST-007 village is `Widh Widh`, not `Buuhoodle`** — the only station whose village differs from
   its district. Intentional?
3. **The three `locations` rows are load-bearing.** `South`/`East`/`West` are wired into
   `ROLE_LOCATION_SCOPE` and checkpoint scoping. **Excluding them would break checkpoint officer
   authorization until recreated** — so option (b) should still keep `locations` in practice; that
   is what option **(c)** exists for.
4. **I cannot verify operational accuracy.** Whether these eight stations exist, whether the tiers
   are right, and whether cell capacities are current are facts only you can confirm. If any is
   wrong, choose **(b)** or **(c)** and supply the real list.

---

## C-2. A-19 — precise production behaviour, including a configured override

Recommended option **(b)**: honour `SENTINEL_BOOTSTRAP_PASSWORD` in demonstration mode only.

### Complete truth table

| Mode | `SENTINEL_BOOTSTRAP_PASSWORD` | `users` empty? | Behaviour |
|---|---|---|---|
| **Production** (flag unset) | **unset** | yes | `admin` only; password = `Sx-` + 32 hex (**128-bit CSPRNG**), unique per install |
| **Production** | **set to any value** | yes | **IGNORED.** Warning to stderr. `admin` still gets a fresh random password. **Signing in with the configured value returns 401** |
| **Production** | set to empty string | yes | Treated as unset (empty is falsy) → random password, no warning |
| **Production** | any state | **no** | **No seeding occurs at all.** The variable has zero effect; no account is created or modified |
| **Demonstration** (`=1`) | unset | yes | 9 accounts, **9 distinct** random passwords |
| **Demonstration** (`=1`) | set to `X` | yes | 9 accounts, **all share `X`** — S-12 retained **deliberately**, because ~22 suites need a known password |

### What "ignored" means concretely

```
WARNING: SENTINEL_BOOTSTRAP_PASSWORD is set but is IGNORED in production
initialization. A unique random password will be generated. Set
SENTINEL_SEED_DEMO_DATA=1 for a demonstration database.
```

- Written to **stderr**, not stdout, so it is visible in service logs.
- The configured value is **never hashed, never stored, never accepted at login**.
- Because production creates exactly **one** account, a shared password is **structurally
  impossible** there — there is nothing to share it *with*. That is the substantive difference
  between option (b) and option (a), which only warns.

### One refinement I recommend

As specified, the warning lives inside `bootstrap_password_for()`, which only runs during seeding.
So an operator who sets the variable against an **already-initialized** database gets **no warning**
— correct (it has no effect) but silent. **I recommend hoisting the warning to startup** so the
variable is always reported when present. Minor, and included in A-16a below.

---

## C-3. Does production initialization fail safely when the mode is missing or invalid?

**Partly — and not well enough. I am revising my own specification.**

### As currently specified

```python
def demo_seeding_enabled():
    return str(os.environ.get(SEED_DEMO_ENV, '')).strip().lower() in ('1', 'true', 'yes', 'on')
```

| Input | Result | Safe? |
|---|---|---|
| **Missing** | production | ✅ safest mode |
| `0`, `false`, `no`, `off` | production | ✅ as intended |
| `1`, `TRUE`, ` Yes `, `on` | demonstration | ✅ (case/whitespace tolerant) |
| **Invalid** — `treu`, `demo`, `maybe`, `prod` | production | ⚠️ safe **but silent** |

**In the security direction it does fail safe**: every unrecognised value resolves to the most
restrictive mode. There is no input that silently *enables* demonstration seeding.

### Three weaknesses I should not gloss over

1. **It fails silently.** A developer who types `SENTINEL_SEED_DEMO_DATA=treu` gets a production
   database and confusing fixture failures. Safe, but a bad failure mode.
2. **No mode is ever stated.** Nothing in the logs says which mode ran. The only way to know is to
   query the tables afterwards — weak for a decision this consequential.
3. **The real gap — a mode flip does not clean an existing database.** All seeding is guarded by
   `if COUNT(*) == 0`. If a database is demo-seeded and the server is later restarted in production
   mode, **the nine personas and the un-clearable suspect alert simply persist**, and production
   mode does nothing because `users` is non-empty. The runbook's step-7 checks catch this *only if
   someone runs them.*

Weakness 3 is a plausible real-world path to exactly the outcome A-16 exists to prevent: someone
demos the system, then "switches it to production."

### Proposed amendment — **A-16a** (new decision)

**Question:** Should initialization **refuse to start** on an unrecognised mode value, announce its
mode on every startup, and refuse to run in production mode against a database containing
demonstration accounts?

**Options:** **(a)** all three guards · **(b)** announce only, never refuse · **(c)** leave as
specified (silent default to production).

**Recommended: (a).** Fail safe *and* loud. Refusing to start is the correct response to an
ambiguous instruction about whether a police database may contain fictional suspects.

```python
SEED_DEMO_ENV = 'SENTINEL_SEED_DEMO_DATA'
_DEMO_TRUE  = ('1', 'true', 'yes', 'on')
_DEMO_FALSE = ('', '0', 'false', 'no', 'off')
DEMO_PERSONAS = ('fp.officer', 'ap.officer', 'cid.officer', 'hr.officer',
                 'cp.south', 'cp.east', 'cp.west', 'chief')

def demo_seeding_enabled():
    raw = os.environ.get(SEED_DEMO_ENV, '')
    value = str(raw).strip().lower()
    if value in _DEMO_TRUE:
        return True
    if value in _DEMO_FALSE:
        return False
    raise SystemExit(
        'FATAL: %s=%r is not a recognised value.\n'
        '  demonstration : 1 | true | yes | on\n'
        '  production    : leave unset (or 0 | false | no | off)\n'
        'Refusing to start rather than guess the initialization mode.'
        % (SEED_DEMO_ENV, raw))

def announce_initialization_mode(c):
    demo = demo_seeding_enabled()
    sys.stderr.write('Sentinel initialization mode: %s\n'
                     % ('DEMONSTRATION' if demo else 'PRODUCTION'))
    if os.environ.get(BOOTSTRAP_PASSWORD_ENV) and not demo:
        sys.stderr.write('WARNING: %s is set but is IGNORED in production.\n'
                         % BOOTSTRAP_PASSWORD_ENV)
    if not demo:
        found = c.execute(
            'SELECT COUNT(*) FROM users WHERE username IN %s',
            (DEMO_PERSONAS,)).fetchone()[0]
        if found:
            raise SystemExit(
                'FATAL: PRODUCTION mode, but this database holds %d demonstration '
                'account(s). It was initialized with %s=1.\n'
                'A production system must not carry demonstration identities.\n'
                'Set %s=1 if this is a demonstration database, or provision a clean one.'
                % (found, SEED_DEMO_ENV, SEED_DEMO_ENV))
```

**Consequences**
- *Security:* Closes the demo→production mode-flip path, the most likely route to fictional
  suspects in an operational database.
- *Operational:* A typo now stops startup with a precise message instead of producing a silently
  wrong database. **A genuine demonstration database can no longer be started in production mode**
  — intended, but it must be in the runbook so it is not mistaken for a fault.
- *Legal:* Supports a positive assurance that no fictional person or suspect listing exists in the
  operational system.

**Reversible:** **Yes, fully** — validation and startup checks only, no persistent effect.

**Affects:** P0-WP-3 · findings S-13, S-12 · adds two tests (`test_invalid_mode_refuses_to_start`,
`test_production_refuses_contaminated_database`).

---

## C-4. Will the permanent suite include both tests?

**Yes — both ship as permanent suites with their work packages.** To be unambiguous: **neither is
in the suite today.** The harness that produced the verification was a throwaway and was deleted;
nothing is implemented. They land only if you approve A-10 and A-11.

| Test | Destination | Ships with |
|---|---|---|
| **Corrected N-7 negative control** — `test_close_with_another_open_action_does_not_reinstate`, including the **guard-the-guard** assertions (`assertEqual(create_status, 201)`, `assertTrue(second_action_id)`) that stop it going vacuous | **`backend/test_officer_discipline.py`** (new) | **P0-WP-1 / A-10**, acceptance criterion **AC-3** |
| **Two-token password-reset test** — `test_16_admin_reset_revokes_all_target_sessions`, asserting **both** of the victim's tokens return 401 | **`backend/test_password_security.py`** (extended) | **P0-WP-2 / A-11**, **AC-1** |
| `test_15` tightened — the `skipTest` escape removed, replaced with a hard 401 assertion | `backend/test_password_security.py` | **P0-WP-2 / A-11**, **AC-8** |

Both are collected automatically by `scripts/run-tests.sh` through the `backend/test_*.py` glob — no
runner change needed.

**The two-token design is not incidental.** A single-token test passes even against a fix that
deletes only the `sessions` rows and leaves the in-process `TOKENS` cache populated — which is
finding N-8. The second token is what makes the test able to fail for the right reason.

Alongside them ship the over-correction controls — administrator's own session survives, a third
party's session survives, a display-name-only PATCH does not revoke — plus
`test_terminated_officer_is_never_reactivated` and `test_close_requires_hr_permission`.

### Effect on the suite

| | Now | After P0 |
|---|---|---|
| Suites | 29 | **31** (+`test_officer_discipline.py`, +`test_production_init.py`) |
| PASS | 28 | **31** |
| BLOCKED | 1 (`test_server.py`, N-7) | **0** — A-10 unblocks it (verified) |

Each new test will be run against the **unfixed** code first and shown to fail. A regression test
never seen to fail proves nothing.

---

## Decisions now awaiting you

| # | Decision | Recommended |
|---|---|---|
| A-10 | Fix N-7 | (a) standalone, same week |
| A-11 | Revoke sessions on admin reset | (a) all sessions incl. cache |
| A-11a | Also revoke on deactivation | (a) — optional |
| A-16 | Flag demo seeding, default off | (a) |
| **A-16a** | **NEW — strict mode validation, startup announcement, contamination refusal** | **(a) all three guards** |
| A-17 | Production = admin only | (a) |
| A-18 | Keep reference stations/branches | (a) — your call; see C-1 notes 1–4 |
| A-19 | Bootstrap password variable | (b) + warning |
| A-13 | Interim alert withdrawal | (a) approve now |

**Nine decisions.** A-16a adds no measurable time to P0-WP-3 (it is ~30 lines inside the same work
package); the 7–9.5 day total is unchanged.

`PROJECT_STATUS.md` and `DECISION_REGISTER.md` remain **unmodified**, per your instruction.
