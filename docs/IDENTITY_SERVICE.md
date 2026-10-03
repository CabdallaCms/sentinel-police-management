# Central Person Registry — Smart Search & Field Immutability

Port of the legacy identity engine onto the Migration 001 architecture.
Schema: `migrations/002_person_identity.sql` · Service: `app/identity/` · API: `app/server.py` · UI: `web/`

---

## 1. What the legacy system did (and where)

| Concern | Legacy location | Behaviour |
|---|---|---|
| Tier 1 – exact ID | `backend/server.py:2737` `find_by_id` | `LOWER(TRIM(national_id))` then passport equality. |
| Tier 2 – exact name + DoB | `server.py:2812` `resolve_person` | All **four** name parts joined and compared to the stored `full_name`, plus equal DoB. Case/space-insensitive. |
| Tier 3 – "fuzzy" | `server.py:2812` | **Not fuzzy:** ≥3 entered parts found *anywhere* in the stored name as exact tokens **and** an exactly equal mother's name. Warning only. |
| Tier 4 – partial / dropdown | `server.py:2758` `person_suggestions` | Score: ID exact +60 / prefix +25, +10 per name part, +8 if in order, +12 DoB, +8 mother; ≥18 listed, ≥30 "strong". |
| Cost | `server.py:2813` | `SELECT * FROM persons` into Python for **every** keystroke-driven resolve — O(table). |
| Enrichment | `server.py:2894` `enrich_person` | Fills **empty** fields only; never overwrites. |
| Duplicate-safe create | `server.py:2921` `upsert_person` | Tier 1/2 → merge+enrich; else create. No lock → two units registering at once could both create. |
| **Immutability** | `index.html:1844` `setLocked`, `:1853` `fillIdentity` | **UI only**: any non-empty auto-filled input becomes `readOnly`. |
| **The gap** | `server.py:5869` `PUT /api/persons/<id>` | Overwrote **any** field (names, DoB, IDs) for anyone with the `people` module. A hand-made request bypassed every lock. |
| Auto-select alert | `index.html:2013` `wireIdentity` → `:1894` `setMatch` | 220 ms debounce, stale-response guard; tier ≤2 → green banner + auto-fill + lock; tier 3 → amber warning + list; tier 4 → blue info + list. |
| Incomplete-profile nudge | `index.html:1885-1894` | "Some details (…) are incomplete — fill them in to enrich this central record." |

## 2. What was ported unchanged

Tier meanings and labels, the scoring weights and thresholds (`matching.py` constants), the debounce / stale-response / "don't clobber what the officer typed" behaviour, the banner colours and markup, the "click a match to auto-fill / create as new Central Person" list, fill-only enrichment, and the incomplete-profile prompt.

## 3. What was modernised (deliberate deviations)

| Change | Why |
|---|---|
| **Real fuzzy matching** (Damerau-Levenshtein, tokens ≥ 0.80 similar, one-to-one assignment; short tokens must match exactly) | Legacy "fuzzy" tolerated reordering but not a single typo. `Cabdi`≈`Cabdii`, `Axmed`≈`Ahmed`. |
| Tier 3 also fires on **fuzzy name + same DoB** | Legacy needed the mother's name, which is often unknown at a checkpoint. |
| Tier 2 needs ≥3 parts (not exactly 4), token-normalised | Third-name-only registrations still dedupe. |
| **Indexed candidate search** — trigger-maintained `name_keys` (3-char prefix keys, GIN) + ID prefix indexes; scoring in Python on ≤200 candidates | No table scan, **no extensions** (`pg_trgm` is unavailable in the embedded build and the blueprint is extension-free). |
| Normalisation is done by the **database** (`norm_text`, `norm_ident`) and Python consumes it | One definition: query and stored values can never normalise differently. IDs are unique after normalisation (`so-123` = `SO123`). |
| **Conflicts reported**: ID → person A but name+DoB → person B; ID match whose typed name/DoB disagree with the record | Legacy silently picked one / silently overwrote the display. |
| **Concurrency-safe register**: advisory lock + unique-violation retry | Four simultaneous intakes of one person ⇒ exactly one record (tested). |
| **Lock state comes from the server per user** (`locked/fillable/editable`) | Legacy locked "whatever is non-empty" for everyone, incl. the admin who is allowed to fix it. |
| **Immutability enforced in the database** | See §4. The legacy `PUT` hole is closed. |

## 4. Field immutability

Rules live in the **data table `person_field_policy`** and are enforced by the `persons_guard` trigger. The API reads the same table (`person_field_states()`), so UI, API and database cannot disagree.

| Class | Fields | Blank → fill | Non-blank → change |
|---|---|---|---|
| **core** | first, second, third, fourth name · date of birth · place of birth | any role with `person:create` (once) | `person:edit_core` **at the root unit** + a reason |
| **identifier** | national ID · passport ID | same | same |
| **protected** | mother's name | same | `person:update` (Fingerprint directorate; National Admin) |
| **dynamic** | phone · address (`residence`) · occupation · photo | same | any role with `person:update_dynamic` (every role that can create persons) |

* **National Admin** = `system_admin` assigned at the **root (HQ)** unit. The same role assigned to a district does *not* qualify — `national_only` makes the trigger check `authz_can(user, 'person:edit_core', <root>)`. Only `system_admin` holds `person:edit_core` (asserted by a test). The read-only Chief Commander holds no write permission.
* Every core/identifier **correction requires a reason** (DB-enforced) and is written to the append-only `person_field_audit` (`kind='change'`, old/new value, user, unit, reason). Fills are audited too (`kind='fill'`).
* `full_name`, `name_tokens`, `name_keys` are derived — `full_name` cannot be edited around the locked parts. `id`, `person_ref`, `created_*` are immutable even for the admin. Persons cannot be deleted.
* **Fail-closed**: a write with no authenticated user (`app.user_id` unset) is rejected. Bulk imports must opt in with `SELECT set_config('sentinel.maintenance','on',true)`.
* **Two write paths, deliberately different:**
  * `PATCH /api/persons/{ref}` is **strict**: if any field is locked for the caller → `403 field_locked` listing every offender, **nothing is written** (atomic). Unchanged values are ignored, so a UI may post the whole form.
  * `POST /api/persons` (intake) is **lenient on existing people**: it links, fills blanks, refreshes dynamic fields and *reports* (`ignored[]`) anything that disagrees with a locked value — it never applies it and never creates a duplicate.
* **Guardians** (`person_guardians`): a guardian is a person (same matching, same locks); the link is append-only. A minor with no guardian shows `guardian` in `missing_fields`, so a later visit at a *different unit* is prompted to add one, and the guardian's own blank details are enriched.

## 5. Smart-search API

`POST /api/persons/search {query:{…}}` or `GET /api/persons/search?q=…` (the single box understands Person ID, National ID/passport, and names).

```jsonc
{
  "status": "exists | confirm | suggestions | new",
  "exists": true,            // high-confidence master profile already exists (Tier 1/2)
  "auto_select": true,       // UI: load the record + show the "already exists" banner
  "tier": 1, "tier_label": "…", "reason": "Exact National ID / Passport match",
  "person": { "person_ref": "P-2026-000001", "full_name": "…", "registered_at": {"code":"DIR-FP",…},
              "missing_fields": [{"field":"residence","label":"Address"}],
              "guardians": [], "field_states": {"first_name":{"state":"locked","mutability":"core"}, …} },
  "candidates": [ … ranked, each with tier/score/reasons/field_states … ],
  "conflicts": [{"code":"name_dob_other_person","message":"…","person_refs":["P-…"]}],
  "core_differences": [{"field":"date_of_birth","stored":"1990-05-17","entered":"1991-05-17"}],
  "has_active_alert": false  // yes/no only; null if the caller may not check alerts. Never the case.
}
```

`POST /api/persons` → `201` created · `200` linked to existing · `409 possible_duplicate` (body carries the search result; resend with `link_person_ref` or `confirm_new:true`) · `422` field errors · `403`. A read-only or non-registering user gets `403` *before* any confirmation prompt.

## 6. Running it

```bash
pip install -r app/requirements.txt
# apply migrations/001_*.sql and 002_*.sql (one transaction each, e.g. psql -1 -f …)
SENTINEL_DATABASE_URL=postgresql://… SENTINEL_DEV_AUTH=1 python -m app.server --port 8080

# or, for a self-contained DEV demo (embedded PostgreSQL + fictional people, no setup):
python -m app.dev --port 8080
```

**Authentication is a placeholder.** The unified auth stack is blueprint open item O9 and is not built. With `SENTINEL_DEV_AUTH=1` the caller is whoever the `X-Dev-User` header names; **without it every API call is `401`** (fail closed). Replace `app.server.authenticate()` with the real session check — nothing else depends on how the user was identified. Do not enable dev auth outside development.

Tests (each builds a scratch PostgreSQL from `migrations/`):

```bash
python -m unittest discover -s tests -t .          # 84 Python tests (matching, DB guard, service, HTTP)
python docs/blueprint/test_blueprint.py            # 24 blueprint tests (still green with 002 applied)
node tests/test_identity_core.mjs                  # 16 pure-UI-logic tests
(cd tests/ui && npm install) && python -m tests.run_ui_flow   # 15 UI steps: real page + real API + real DB (jsdom)
```

## 7. Open items / honest limits

| # | Item | Note |
|---|---|---|
| I1 | **Core fields can be filled once when blank** by any registering role (then lock). | Matches the legacy "only non-empty locks". If you want core fields to be mandatory-at-registration with *no* later fill, set `fill_perm` to `person:edit_core` for those rows — a one-row data change. |
| I2 | **Fourth name is treated as core**; PoB is optional at registration (locks once set). | You listed first/second/third + DoB + PoB; the legacy UI is 4-part, so the fourth is locked with them. |
| I3 | **Spelling variants** (Maxamed/Mohamed/Muhammad, Cabdi/Abdi, Xasan/Hassan) are not matched — edit distance only. | Needs a curated variants table; recommended next. Misspelling the first 3 letters of every name part also escapes candidate generation. |
| I4 | **Year-only / unknown-day dates of birth** are not supported (`date`). | Common in practice; needs `dob_precision`. Tier 2 needs an exact date. |
| I5 | **Person merge** (`person:merge` exists, no function yet). | The no-delete trigger already points to it. |
| I6 | ~~Photo upload was a path column only.~~ **Done in Phase 2:** `POST /api/uploads` with magic-byte checks and access that follows record access. | See [`OPERATIONS.md`](OPERATIONS.md) §2, §4. |
| I7 | ~~Unit events not ported.~~ **Done in Phase 2:** checkpoint stops, airport logs and station incidents now go through `registry.register()` (victims link only, never auto-create). | See [`OPERATIONS.md`](OPERATIONS.md). Clearance events remain with the national Fingerprint directorate (later phase). |
| I8 | **UI verified with jsdom, not a real browser** (the browser download is blocked in this environment). | Layout/visual polish is unchecked. |
| I9 | Dev-auth placeholder (see §6). | Blocker for production, by design. |
