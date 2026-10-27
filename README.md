# Sentinel Police Management

A working browser-based prototype for a central police management platform. It is designed around a single Central Person Registry with separate unit records.

## Included units

- Central Person Registry
- Fingerprint Unit and clearance applications
- Clearance approval and certificate number generation
- CID criminal cases
- Suspect list
- South, West and East Checkpoints
- Hargeisa Local Airport passenger register
- Central Police Search (officers / stations / cars by Region → District → Village)
- Police Stations / Officers / Cars registration (regional modules)
- Officer Conduct, Promotions & Disciplinary Management (Police Officer Registration Office / HR Directorate)
- Dashboard and cross-unit activity feed
- Clean operational registers — full-width tables with slide-over drawers for new entries (no inline forms, no per-page analytics)
- Departmental analytics exclusive to the Chief Commander's Global Executive Dashboard (HQ / Command)

## Central-person linking model

Every person receives one central `Person ID` (`P-0001`, etc.). Unit registers store their own records and reference this ID:

- Airport: movement type, travel date, flight number, airline/carrier, origin city, destination city and travel notes
- Fingerprint: clearance purpose, guardian, relationship, legal document references and review status
- CID: case participants and case references
- Checkpoint: screening events and actions taken

### Smart identity resolution (single unified form)

There is **one unified person entry form** used everywhere (Central Persons, Add Suspect, Airport, Fingerprint, Checkpoint and CID participants). It captures the **4-part full name (first, second, third, fourth), date of birth, National ID / Passport, mother's name and address** — there is no manual "existing person vs new person" toggle.

As the officer types, the form performs **real-time background matching** against the Central Person Registry — case-insensitive and whitespace-trimmed:

- **Exact match** (National ID/passport, or 4-part name + DOB) → success banner **"Matched Central Record: [ID] - [Name]"** and the existing data auto-populates.
- **Partial/full name match (2, 3 or 4 name components)** and partial ID/passport matches → a **live dropdown** lists the matching Central Persons (Full Name, NID/Passport, DOB). **Clicking a match instantly auto-fills all existing central data** (name, mother's name, DOB, National ID, Passport, address, phone, photo) and shows the green **"Matched Central Record: [ID] - [Name]"** banner.
- **Fuzzy 3-part name + mother's name** → amber warning prompt listing candidate records; the officer confirms before linking (Tier 3 is never an automatic merge).
- **No match** → the form shows a notice and submission **auto-creates the Central Person first**, then attaches the unit/suspect record.

The same interactive matching engine (Tier 1 exact ID/passport auto-merge, Tier 2 exact 4-part name + DOB high-confidence link, Tier 3 fuzzy warning, Tier 4 partial-name dropdown) is applied across **Checkpoints, Airport Control, Fingerprint Unit and CID**.

### Central Person enrichment on submission

When a unit record (Airport, Checkpoint, Fingerprint or CID/suspect) links to an **existing Central Person ID**, the backend checks the incoming submission for any values that are still **null/empty** in the person's profile (e.g. Mother's name, Phone, Occupation, Address, Passport ID, photo). It **automatically enriches** the central `persons` record with those non-empty new values **without overwriting existing non-null data** — so an officer can complete a partially-filled profile (e.g. the blank "Mother's name" in the Airport form) and the central record is updated on save.

The same fill-only enrichment applies to the identity-merge path (`/api/persons/upsert` and the unit routes' auto-resolve): matched records never get overwritten, only missing fields are filled.

**Locked auto-filled fields (partial-profile completion):** when a Central Person is matched and auto-filled, only the fields with **actual non-empty text** are set to read-only (greyed out). Any field that came back **blank/`null`** (e.g. Mother's name, Occupation, Contact Number, Address) is left **fully editable and active**, so the officer can complete the missing profile data — and the value is enriched into the central record on save. Officer-entered input into those blanks is never clobbered by the live re-match.

When a matched profile is incomplete, an **info tag** appears under the match banner: *"ℹ️ Matched Profile: P-XXXX. Some details (e.g. Mother's Name) are incomplete — fill them in to enrich this central record."*

### No popups — pages and centered modals

The interface uses **no native browser dialogs**. All create/edit actions happen in **dedicated full-page workspaces** (e.g. the CID case workspace) or **centered modal dialogs** (new person, new case, checkpoint stop, identity review) that open dead-center over a blurred dark backdrop with a fixed header, an internally scrolling body and a sticky footer.

### In-modal errors and the global toast

- Form submission errors, validation warnings and backend API errors are **never** shown as floating toasts. Inside a modal they render as an **inline red alert banner** directly under the modal title (icon + action instructions); the modal body scrolls to and focuses the first invalid field (opening its wizard step if needed). Only failed fields get red borders; valid siblings and optional empty fields remain neutral. Attachment minimums use a single group indicator rather than flagging every optional slot. On the inline page forms they render in the form's own notice area (red variant) — and any other page-level failure shows a transient top-of-page alert.
- The **bottom-right global toast** is reserved exclusively for **success/system notifications** (e.g. "Record saved successfully"). It is redesigned with a check icon, drop shadow, proper padding, crisp typography and an auto-dismiss animation after 4 seconds.

### Fingerprint application, review and certificate

- The expanded clearance application captures applicant data (full name, mother's name, DOB/POB, residence, occupation, passport, National ID, photo, gender, email, clearance reason) plus **4 applicant file slots (≥2 required)** and guardian data (name, relationship, ID, occupation, address, contact) with **3 guardian file slots (≥2 required)**.
- The **clearance reason** dropdown offers exactly five mandatory reasons — **Education, Travel, Employment, Citizenship, Licence**. The API rejects any other value with HTTP 400.
- **`application.html`** — the printable Day-1 application form (A4, Somali, from the official source blueprint): **"CODSIGA SHAHAADADA DAMBI-LA'AANTA"** with the Northeastern Police Force / CID masthead (`PCC-2026-DIGITAL-01`), the police emblem **only as the centred low-opacity watermark** (top 52% / left 50%, opacity 0.08, z-index 2 behind the content), passport photo box, and QAYBTA 01–03 mapping every registration field (identity, purpose, guardian/guarantor) with Somali declarations and signature lines in QAYBTA 04. The Django-style blueprint is bound client-side: all `{{ application.* }}` slots carry ids filled by the preserved fetch/auth/12-hour-lock script.
- **`certificate.html`** — the official Day-2 **Certificate of Good Conduct (Police Clearance Certificate)** from the official source blueprint: cream sheet, bilingual letterhead (English left, police crest centred, Arabic right), the emblem **also as the centred watermark**, "TO WHOM IT MAY CONCERN" certification, a 65% details table beside the photo box, the **NO ADVERSE CRIMINAL RECORD FOUND** search result, purpose/six-month validity lines, the Chief of Fingerprint Unit signature block and the blue absolute footer bar. Locked until an officer approves, then unlocked for printing.
- **A4 print contract (both documents).** Blueprint `@page` rules (`application`: `size:A4; margin:0` with `.page{padding:6mm 8mm 4mm 8mm}` on paper; `certificate`: `size: A4 portrait; margin: 0`), plus `print-color-adjust: exact` and all web chrome (toolbar, buttons, badges, banners, toasts) hidden when printing. The application sheet drops `min-height` on paper (the single-sheet guarantee — a 297mm-tall box with zero `@page` margin spills a blank second page on engine rounding). The certificate fills the sheet (11pt/1.52 body, centered 11.5pt signature block pushed toward the footer bar) and QAYBTA 01 is a strict side-by-side executive grid (tinted 25% label cells, uppercase titles, equal-width entries). `backend/test_print_fit.py` — runnable as `python -m unittest backend.test_print_fit` or `python3 backend/test_print_fit.py` — pins the rules, the emblem placement (opacity band 0.08–0.12), blueprint wording verbatim (Somali + Arabic), every DOM binding/endpoint/lock hook, the transparent RGBA seal asset, and worst-case single-page height budgets (application 244.1mm ≤ 265mm envelope; certificate 281.1mm inside the 270–284mm filled-page envelope vs 297mm usable).
- **Mandatory 12-hour review period.** Except for **Citizenship**, a clearance application can only be approved once `created_at + 12 hours` has elapsed. **Citizenship** is exempt from this wait: an authorized Fingerprint Officer can approve it immediately and then print the certificate. Approval, authentication and role checks are still required; the exemption is based on the stored purpose, not approval-request data. A **Fingerprint Officer** attempting an earlier approval gets HTTP 400 `Application is under mandatory 12-hour review period.`; a **System Administrator** bypasses the wait and can approve immediately. The lock is enforced in **three** places:
  - the backend gate on `POST /api/fingerprint/applications/{id}/approve`;
  - the **Fingerprint register table** in `index.html`, where the Approve button is disabled and replaced by a `🔒 Review Lock (12h Required) - X hours remaining` badge the moment the application is created (admins see an enabled `Approve` action);
  - `application.html`, which reads `created_at` and the signed-in role and blocks the approve call client-side before any request is sent.
- Role names are alias-tolerant: an officer stored as `fingerprint_officer` (or an account named `admin`) resolves to the canonical `FingerprintUnit` / `SystemAdmin` role for modules, RBAC gates, visibility flags and the review window.

### CID case workspace and optional case linking

Each case opens in a full-page workspace with three tabs: **1) Case Details & Incident Summary**, **2) Participants & Suspect List Linkage** (suspect/victim/witness/complainant, with suspects creating checkpoint/airport alerts), and **3) Evidence & Media Storage** (file uploads with captions).

The **Add Suspect** modal makes the **linked case strictly optional**: a suspect can be listed with a case, or without one, in which case the origin is recorded as **"Direct Intelligence Listing"** or **"Manual Entry"**. The suspect endpoints (`POST /api/suspect-alerts`) accept an optional `case_id` and store the origin server-side.

### Role-Based Access Control & location-isolated checkpoints

Officers sign in with one of nine roles. The sidebar, top-bar user pill, and every API call are scoped to the role:

- **System Admin** — full access to every module, every departmental analytics bundle and the User Management page.
- **Fingerprint Unit** — the biometrics register plus Central Person Search only. Like the Airport
  and CID units it is **not** a party to Central Police Search (`policesearch` is stripped from the
  role's module set on the server and again in the sidebar), so a Fingerprint officer never sees the
  cross-registry officers / stations / vehicles lookup.
- **Airport Control** — the Airport module plus Central Person Search only. **Central Police
  Search is not part of this unit** (`policesearch` is stripped from the role's module set on the
  server and again in the sidebar), so an Airport officer never sees the cross-registry police
  search — only their own unit scope and the person register.
- **CID Criminal Unit** — the CID / suspect-alert and Crime registers plus Central Person Search,
  and the `crime` section of the CID analytics bundle — again **without Central Police Search**.
- **HR Directorate** (`hr_officer`) — the **Police Officers** register in full (roster, green-badge promotions, red-badge discipline and their analytics bundle) plus read access to **Police Stations** for postings and the two central search registries. No admin, CID, checkpoint, airport or fleet-write rights.
- **Chief Commander of Police Office (HQ / Command)** (`chief_commander`) — the **global read-only command role** (shown in the UI as *Commander / High Command*). It holds the `readonly:global` permission plus `analytics:global`, `cid:view`, `personnel:view` and `transport:view`, so it monitors every department, register, log and search across the whole country and uses the two HQ pages: the **Global Executive Dashboard** (KPI grid — Total Officers · CID Clearance Rate · Active Checkpoint Hits · Fleet Readiness — department cards, charts and the regional stations table) and **Stations Oversight & Regional Data**. Backed by `GET /api/analytics/global` (also `GET /api/analytics?module=global`). It **cannot write anything**: every `POST`, `PATCH` and `DELETE` on any route is refused with **`403 Forbidden`** by a single firewall in front of the API (see *Global read-only command role* below), and the UI renders every module in strict view-only mode — no *Register*, *Add*, *Edit*, *Approve* or *Open case* control is shown. Signing in as `chief_commander` lands directly on the Global Executive Dashboard.
- **Checkpoint South / East / West** — only the Checkpoint module, **scoped to their assigned location**; `GET /api/checkpoint-events` returns a `scope` and `visible_locations` payload so the frontend can render the active filter, and `POST /api/checkpoint-events` rejects events at any other location.

The top bar shows the active officer and location, e.g. **Officer H. Xasan · South Checkpoint**, and the sidebar hides modules the user cannot use. Server-side enforcement mirrors the UI: a non-admin token cannot reach `/api/admin/*` or the executive analytics aggregation, a Fingerprint officer cannot list Airport or Crime records, an Airport or CID officer cannot open Central Police Search, and each departmental analytics bundle only ever returns the sections its caller's modules allow.

### Global read-only command role (Commander / High Command)

`chief_commander` is the only **read-only** role in the system, and the rule is enforced twice so the
UI and the API can never disagree:

- **Backend firewall.** `enforce_read_only()` runs inside `do_POST`, `do_PUT`, `do_PATCH` and
  `do_DELETE` immediately after authentication and *before* any route-specific handling, so a
  command token is refused with **`403 Forbidden`** (`{"error": …, "code": "read_only_role",
  "read_only": true, "path": …}`) on every mutation in the API — persons, airport records,
  clearance/fingerprint applications, crime cases and evidence, suspect alerts, checkpoint events,
  stations, officers, vehicles, crime files, conduct submissions and HR reviews, promotions,
  disciplinary actions and user management. Because the check sits in front of the router it also
  covers paths that do not exist (a Commander never distinguishes 403 from 404) and the verb the API
  does not serve (`PUT` → 403 instead of 405). `GET` / `HEAD` / `OPTIONS` are untouched, and
  `POST /api/login` / `POST /api/logout` stay available so the officer can still sign in and out.
  The role no longer holds `stations:manage`, so the station-management bypass is closed as well.
- **Frontend view-only mode.** The Commander session applies `body.readonly-mode`, which hides
  every control marked `data-write` / `.write-action` (Register Officer, Add, Edit, Approve
  Clearance, Open Case, the register's *Print* link, …), drops the dashboard's
  quick-registration panel for a lock notice, swaps every action cell for a *View only* marker, and
  shows a **View-only** badge + banner in the top bar. On top of the CSS marker there is a
  **DOM hardener**: `hardenReadOnlyDom()` hides *any* element whose handler is a mutation entry
  point (even one that lost its `data-write` marker), restores the controls when a write-capable
  officer signs in on the same tab, and a `MutationObserver` re-runs it after every repaint — so
  every department page is clean, including rows painted dynamically. Every write entry point
  (`openEntryModal`, the person/case/checkpoint/user drawers, approval and review handlers) refuses
  to run, and the `api()` transport refuses any non-`GET` call locally with a `403` before it leaves
  the browser — the same status the server returns. The printable review page
  (`application.html`) carries the same rule: a read-only session gets no *Approve Application*
  button, a view-only note instead, and `approve()` never issues the request.
- **Confirming which build is live (and never running a cached one).** `index.html` stamps
  `<meta name="sentinel-ui-build" content="sentinel-checkpoint-audit-6-9a4c7f31">` and shows *UI build …*
  in the sidebar footer (`window.SENTINEL_UI_BUILD`). The stamp ends with the short commit the page
  was published from, which is also the `?v=` parameter on every static reference in the app
  (`certificate.html?v=9a4c7f31&id=…`, `images/police_logo.png?v=9a4c7f31`) — bump `ASSET_VERSION`
  *and* `UI_BUILD` in `backend/server.py` together with the `?v=` parameters in `index.html`,
  `application.html` and `certificate.html` (the station action suite asserts all of them agree).
  Served documents answer `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` +
  `Expires: 0` + `Pragma: no-cache`, so a normal reload always fetches the current page, and
  `?v=`-stamped assets are the only ones allowed to be cached (`immutable`). `GET /api/health`
  reports `ui_build` (read from the `index.html` on disk, not a constant) and `asset_version`:
  if the sidebar footer and `ui_build` differ, the tab is stale — hard-refresh it.
- **Where the page comes from (local runs).** `python backend/server.py` serves the `index.html`
  found in the **current working directory** first, then the repository root that holds
  `backend/server.py`, then `SENTINEL_UI_DIR` when set (explicit override, packaged deployments).
  The file is re-read on every request, so editing it is live on the next reload — no template
  cache, no restart. `python backend/server.py --ui-check` answers *what would `GET /` serve?*
  without starting the server or touching the database (exit `1` if it would refuse), and
  `/api/health` reports `ui_source`, `ui_cwd` and `ui_git` (branch + commit of the checkout the
  template came from). **The station View/Edit work lives on the branch
  `arena/70d3d88b-sentinel-police-management`, not on `main`** — a checkout of `main` is
  `sentinel-rbac-readonly-3` without the Actions column, and the server now refuses to start on it
  instead of silently serving it.
- **A stale page cannot be served.** `/api/health` also publishes `ui_path`, `ui_sha256`,
  `ui_actions_published` and `ui_ok`/`ui_problems` for the template the process is actually serving,
  and `bash scripts/verify-live-ui.sh <url>` compares them with a checkout (stamp, sha256, Actions
  column, View/Edit entry points, cache headers) — a fresh browser showing an old build is a *server*
  problem, and that script names it. Startup refuses to bind the port at all when the `index.html` it
  would serve is not this build (old stamp, or missing the Actions / View / Edit markers), a
  running server answers `503` (`X-Sentinel-UI-Stale: 1`) rather than emit it after the checkout
  changes underneath it, and
  `SENTINEL_UI_DIR` lets a packaged deployment point at a different template directory — whatever
  directory wins is the one verified, logged and reported. Meanwhile the
  backend prints its RBAC guarantees at start-up
  (*Central Police Search is NOT granted to AirportControl, CIDUnit* / *global read-only roles
  chief_commander — DELETE, PATCH, POST, PUT … answer 403 Forbidden*). If a browser still shows the
  old menu or action buttons, it is a stale tab: hard-refresh it (the server sends
  `Cache-Control: no-store`).

**Session persistence (refresh-safe sign-in).** On sign-in the auth token and user object are stored in browser storage (`localStorage.setItem('sentinel_token', token)` and `localStorage.setItem('sentinel_user', JSON.stringify(user))`, plus the legacy `sentinelSession` object used by the printable pages). On every page load `initApp()` re-hydrates `currentUser` and `authToken` **before** the initial API sync (`syncServer` / `fetchCheckpoints`), and every request automatically carries `Authorization: Bearer ${token}`. A refresh therefore never signs the officer out: only an explicit HTTP **401** from the dedicated auth check (`GET /api/me`) clears the session — non-fatal startup errors (server still booting, transient 5xx, a 404) keep the officer signed in and retry in the background.

**Role normalization and the unit denylist.** The module a session receives is
resolved through the alias tables *and* a family fallback, so the label spellings an operator may
have typed into `users.role` — `Airport Control Officer`, `Airport Control Unit`, `CID Criminal
Unit`, `Criminal Unit`, `Crime Unit`, `Chief Commander of Police Office`, … — resolve to their real
role instead of falling through. That fall-through was the source of a real defect: an unrecognised
role used to inherit the review-lock default module set (the Fingerprint set, which *includes*
Central Police Search). Now:

- `ROLE_MODULES[FingerprintUnit] = {dashboard, people, fingerprint}`,
  `ROLE_MODULES[AirportControl] = {dashboard, people, airport}` and `ROLE_MODULES[CIDUnit] =
  {dashboard, people, cid, crimes}` — and the hard denylist (`UNIT_MODULE_DENY` +
  `denied_modules_for_role()` / `strip_denied_modules()`) is re-applied to **every** module list the
  server emits or checks (login, `/api/me`, dashboard, `require_module`, `user_module_set`), so no
  spelling, cached payload or future edit can leak `policesearch` into a unit session. The police
  search surface itself (`/api/vehicles`, `/api/vehicles/analytics`) answers **401** for all three
  units.
- An **unrecognised** role is fail-closed: it resolves to dashboard only, never to another unit's
  modules.
- The server runs `rbac_self_test()` at start-up and **refuses to boot** if the denylist or the
  read-only command role is not in force in that process (`RBAC self-test: PASS — module denylist in
  force for AirportControl, CIDUnit, read-only roles: chief_commander`).

**One Checkpoint Officer role.** There is a single assignable role, **`checkpoint_officer`**; *which* checkpoint an officer commands is data (`users.location_scope` + the composed `users.branch` label), assigned through the Region → District → Checkpoint cascade. The historical spellings (`CheckpointSouth` / `CheckpointEast` / `CheckpointWest`, `checkpoint_south`, `cp_south`, `cp.east`, `Checkpoint Officer (West)`, …) are still **accepted and normalised** to the unified role so an older client or an un-migrated row keeps working, and `migrate()` rewrites every stored compound role in place while preserving its scope. The compound roles are no longer in `ALL_ROLES`, so they can never be assigned again. `GET /api/dashboard` and `GET /api/checkpoint-events` return HTTP 200 for all of these roles — never 404/401 for a valid checkpoint officer — and the checkpoint query matches the location case-insensitively (`LOWER(location_code) = 'south' OR LOWER(checkpoint_location) LIKE '%south%'` and equivalent columns).

**Checkpoint table freshness.** `submitCheckpoint()` prepends the new stop into `db.checkpoints` immediately so the table and the location badge update instantly (`South Checkpoint 0 → 1`), and `syncServer()` never overwrites `db.checkpoints` with `[]` from a transient/failed response — only a successful response with rows replaces the local cache.

### Hierarchical sidebar navigation

The sidebar is organised the way the service actually works: **four collapsible operational
categories**, each holding departmental accordions (or, in Command Center, the dashboard plus
its accordions). Both levels remember their open/closed state (`localStorage.sentinelNavSections`
and `sentinelNavGroups`), navigating into a page auto-expands the category + accordion that own
it, and the narrow mobile rail keeps the same hierarchy.

| Category | Accordion | Items (`data-page` · module) |
|----------|-----------|------------------------------|
| **COMMAND CENTER** | *(plain entry)* | **Dashboard** (`dashboard`) |
| | **Search & Intelligence** | *Central Person Search* (`people`), *Central Police Search* (`policesearch` — one cascading Region → District → Village/Town filter across the officers, stations and cars registers plus free-text search; not granted to the Airport Control or CID Criminal Unit roles) |
| | **HQ Command** | *Global Executive Dashboard* (`executive`), *Stations Oversight & Regional Data* (`oversight`) |
| **OPERATIONAL UNITS** | *(category utility)* | **Unit Directory** — one searchable directory for every unit the session may read (not a page; see below) |
| | **Fingerprint Units** | *Fingerprint Unit* (`fingerprint`) + its dynamic Region → District → branch tree |
| | **Crime Units** | *Crime Unit* (`cid`) |
| | **Airport Control** | *Airport Unit* (`airport`) |
| | **Checkpoint Units** | *Checkpoint Unit* (`checkpoints`) + its dynamic Region → District → checkpoint tree (see below) |
| | **Stations & Registers** | *Police Stations* (`stations`) + its dynamic Region → District → station tree, *Register Crime* (`crimes`) |
| **AGENCY & PERSONNEL** | **Police Personnel** | *Registration Office* (`officers`), *Conduct & Discipline* (`conduct`) |
| | **Transport / Fleet** | *Vehicle Registry* (`cars`), *Vehicle Status & Tracking* (`vehiclestatus`, module `cars`) |
| **ADMINISTRATION** | **System Administration** | *User Management* (`admin`, System Admin only), *Branch Management* (`branches`, module `admin`) |

The regrouping is labelling only for the existing pages — every page id, `data-page`/`data-modules`
value and RBAC gate is unchanged, and the case workspace still highlights its parent Crime Unit
entry. The standalone **Analytics** entry is gone: the only full analytics surface is the Chief
Commander's **Global Executive Dashboard** (see **Departmental analytics (executive dashboard
only)** below); each operational page keeps only a compact overview strip of live counters on top
of its register.

Visibility is driven by the `modules` array from `GET /api/me` in `applyNavForRole()`: each button
is gated on its own module, the Administration category on the `is_admin` flag, and a whole
category (or accordion) disappears when every entry inside it is hidden for the signed-in role —
e.g. a Checkpoint officer sees only *Command Center → Search & Intelligence* plus *Operational
Units → Checkpoint Units*, and never an empty heading.

#### Dynamic unit trees (Region → District → unit) + the Unit Directory

Operational postings are unbounded data — an administrator can register any number of branches and
checkpoints — so the rail never renders a flat list of raw names. Every operational unit accordion
(*Fingerprint Units* · *Crime Units* · *Airport Control* · *Checkpoint Units*) — and the
*Police Stations* register — paints the **same live three-level tree**:

```
Fingerprint Units
  Sanaag                    3
    Ceerigaabo              1
      Erigavo
    Badhan                  1
      Badhan
Checkpoint Units
  Sool                      2
    Laascaanood             1
      Lasanod Central
    Xudun                   1
      Yagoori
```

- **Live sources** — `unitNavCatalog(type)` merges the branch catalogue (`/api/branches`, via
  `branchCatalog`) with the **live register** (`db.checkpoints` / `db.fingerprint` /
  `db.airport` / `db.cases`) and, for checkpoints, the canonical `South` / `East` / `West` codes
  from `/api/me`. A legacy row whose posting is not (yet) a registered branch still appears,
  located through its `Name · District · Region` label.
- **Immediate updates** — `renderUnitNavTrees()` runs on every nav paint, every `renderAll()`,
  every server sync, after a branch is saved in **Branch Management** and after a checkpoint stop
  is recorded, so a **new branch or checkpoint is in the sidebar before the next click** (no
  reload). The canonical `South` / `East` / `West` areas (which have no gazetteer district of
  their own) are grouped under *Checkpoint areas*, and a row that cannot be placed at all is shown
  under *Unassigned region* / *Unassigned district* instead of being dropped.
- **Short labels** — `shortUnitLabel()` decides what the rail shows: the administrative suffix
  (*Branch* / *Checkpoint* / *Police Station* / *Outpost* …) is dropped and the remainder is
  ellipsised to a fixed width (`NAV_UNIT_SHORT_MAX`), so `Buuhoodle Border Crossing Checkpoint`
  reads `Buuhoodle Border C…` at 210 px. Every nav label is one non-wrapping line and the **full
  name always survives in the tooltip** and in the Unit Directory.
- **Persisted state** — region (`type|region`) and district (`type|region|district`) open/closed
  state lives in `localStorage.sentinelNavRegions`; the region/district owning the active unit is
  auto-revealed (never collapsed) by `markUnitNavCurrent()`.
- **Clicking a unit** — `openUnitNavUnit()` opens that unit's register filtered to the posting
  (the page's own search box for fingerprint / airport / crime; the location chips for a canonical
  checkpoint). A station-scoped checkpoint officer keeps their RBAC posting — a click can never
  widen the register beyond the unit they are assigned to (a toast explains it).

**Unit Directory** is a **category-level utility** at the top of *Operational Units* (it is
deliberately **not** nested inside the Checkpoint Units accordion any more). It opens the read-only
`#unitDir` modal, which lists every unit of the categories the session may read with
**unit type / Region / District / free-text** filters, and an *All unit types* view. Clicking a row
opens that unit exactly like the tree does. It stays available to a read-only Commander session
(a read surface — no write control is rendered inside it).

#### Robust posting resolution + auto-locked branch selectors

A posting is **free text**: `users.branch` stores a readable label and
`users.location_scope` stores the checkpoint area, and neither is a foreign key. Before a branch
can be locked (or a register scoped) the posting is therefore **canonicalised** — in exactly one
place per tier, `canonical_posting_key()` / `resolve_posting_branch()` in `backend/server.py` and
their JS twins in `index.html`:

| Stored posting | Resolves to |
|----------------|-------------|
| `Lasanod Branch` | `Lasanod Branch` |
| `  LASANOD branch ` | `Lasanod Branch` (case, padding, punctuation ignored) |
| `Lasanod` | `Lasanod Branch` (administrative suffix dropped) |
| `Lasanod Branch · Laascaanood · Sool` | `Lasanod Branch` (composed label split) |
| `Fingerprint Unit · Sool` | the Sool branch (legacy **unit-level** posting + region) |
| `Fingerprint Unit` (three branches, no region) | **nothing** — ambiguous, so the officer keeps the free choice |
| `South Checkpoint` (checkpoint officer) | the branch posted to that area, else nothing |

Rules: the catalogue is first restricted to the officer's own department (the same branch name
exists once per department), then scored per candidate — exact canonical name **100** / one name
contained in the other **70–80** / district hint **62** / region hint **52** / legacy unit-level
posting **40–46**. The highest score wins **only if it is unique** and at least
`POSTING_MATCH_MIN`; a tie is never broken by guessing.

`GET /api/login` and `GET /api/me` return the resolved posting (`branch_scope`) and its status
(`branch_scope_status: {resolved, branch, posting, unit_type, override}`), so the browser and the
API always agree. `refreshBranchSelect()` ends with `applyBranchLock()`:

- **Posted officer** — the resolved branch is **pre-selected and disabled**, with a clean
  `🔒 Locked to assigned branch · <branch> · <district> · <region>` chip (no yellow warning banner).
- **System Administrator / multi-branch Commander** — `is_admin`, `can_manage_records`, the
  `SystemAdmin`/HQ roles or the payload's `override` flag keep the selector open, and the
  checkpoint location selector stays editable too.
- **Unresolvable posting** — the field stays editable (a fabricated `branch_id` could never be
  saved) and a muted `ⓘ` note explains that an administrator has to assign a branch, after which
  the field locks itself.

#### Strict branch scoping (reads and writes)

The API scopes with the **same** resolver (`branch_scope_view()`), so what the UI pins is what the
server enforces. A standard officer whose posting resolves to a branch is *scoped*; a
System Administrator, the Commander and any unresolvable posting stay unrestricted (never silently
narrowed):

- **Registers** — `GET /api/clearance-applications`, `/api/airport-records`, `/api/crime-cases` and
  `/api/crimes` add `WHERE branch_id = <own branch>`; the checkpoint event filter keeps its
  existing location scope. Each payload echoes `branch_scope`.
- **Single records** — a clearance application, its printable page, a CID case and
  `/api/audit/entity/<entity>/<id>` answer **403 `branch_scope_forbidden`** when the record belongs
  to another branch (a guessed identifier can never widen the scope; a record with no branch is
  out of scope for a scoped officer).
- **Writes** — a scoped officer filing under another branch is refused with the same 403 and the
  message names their posting; a legacy client that omits `branch_id` is pinned to the officer's
  own branch instead of storing an unscoped record.
- **Untouched** — authentication, session cookies, module gates, the read-only firewall, the
  12-hour fingerprint review lock and the existing database schema are unchanged.

#### Contextual module headers

Each operational page's overview banner and the dashboard heading now name the officer's posting
instead of a generic unit title:

| Session | Banner |
|---------|--------|
| Fingerprint officer posted to `Lasanod Branch` | `Fingerprint Unit — Lasanod Branch Operations` (detail line `Laascaanood · Sool`) |
| Checkpoint officer at `Lasanod Central Checkpoint` | `Checkpoint Unit — Lasanod Central Checkpoint Operations` |
| System Administrator | `Fingerprint Unit — all branches` · dashboard `Cross-unit Operations` |
| Commander | `Fingerprint Unit — cross-region command` |
| Unresolved posting | `Fingerprint Unit — <posting> Operations` (the posting is named) |

`paintModuleHeaders()` repaints on every navigation, save and session change from the same
resolver the lock uses, and `GET /api/dashboard` adds `branch_scope` / `branch_context`.

#### Branch-scoped navigation tree

The sidebar follows the same resolved posting, so a branch-scoped officer cannot browse into a
register the API would refuse anyway:

- **One choke point** — `unitNavCatalog(type)` filters its rows through `navUnitScope(type)` /
  `unitInNavScope(unit, scope)` before anything renders, so the Region → District → unit trees,
  the Unit Directory rows and the `#navUnitCount` badge can never disagree.
- **Scoped view** — a posted officer sees only their own region → district → branch in *every*
  tree (Fingerprint, Crime, Checkpoint, Airport, Stations). Rows are matched on region + district
  and then on `branch_id`, falling back to the canonical branch name for legacy rows that carry no
  `branch_id`; a row that cannot be placed is dropped rather than shown in an *Unassigned* group.
- **Full national tree** — a System Administrator, the Commander (`can_manage_records`) and any
  unresolvable posting keep every region, district and unit, exactly as before.

#### Unit Directory (command authority only)

The category-level *Unit Directory* lists every national branch, so it is reserved for the
cross-branch command: `System Administrator`, the `can_manage_records` role, the Commander
(`branch_scope_status.override`) and HQ. For a branch-scoped officer the launcher is hidden, the
count badge is blank and `openUnitDirectory()` refuses with the *Unit Directory is restricted*
toast — defence in depth, not just a hidden button. The officer's own registers stay reachable
through their scoped tree, so nothing they are entitled to disappears.

### Regional location schema (Sool · Sanaag · East Togdheer)

Registration modules share one location hierarchy — **Region → District → Village/Town** — defined once in the `LOCATIONS` constant in `index.html`. It is the single source of truth for every location control, so extending the gazetteer there is all that is needed to make a new district selectable everywhere.

The three levels are entered as **Dropdown (Region) → Dropdown (District) → Text Input (Village/Town)**:

- **Region** — a dropdown restricted to exactly three options: **Sool**, **Sanaag**, **East Togdheer**.
- **District** — a dropdown restricted to the official districts belonging to the selected Region, per the standard administrative gazetteers (Wikipedia "Sool" / "States and regions of Somalia" / EUAA COI 2025): Sool → *Laascaanood, Caynabo, Xudun, Taleex*; Sanaag → *Ceerigaabo, Ceel Afweyn, Garadag, Badhan, Dhahar*; East Togdheer → *Burao, Oodweyne, Buuhoodle*.
- **Village/Town** — a **free-text input** (no fixed list). The registering officer types the exact settlement name at entry time, e.g. Region `East Togdheer` → District `Buuhoodle` → Village `Widh Widh`, or Region `Sool` → District `Laascaanood` → Village `Adhi Cadeeye`.

- **Reusable component** — `locationDropdowns(prefix, opts)` renders and wires the control (`{prefix}-region` select, `{prefix}-district` select, `{prefix}-village` text input) into a `.loc-grid` container: choosing a Region populates its official Districts (and clears the typed Village/Town); choosing a District clears the typed Village/Town. `opts.withAll` adds "All …" placeholders (used by the Central Police Search filter) and `opts.disabled` renders the whole block locked (for fixed-location contexts). `readLocation(prefix)` / `setLocation(prefix, loc)` read and write the three levels; `requireLocation(prefix)` enforces all three (village must be non-empty text).
- **Station anchor model** — Police **Station Registration** captures *Station Name, Code, Region, District, Village/Town* (`requireLocation()` enforces all three levels) and now persists server-side via `POST /api/stations`. **Police Car** registration links a record to an assigned station; picking a station **pre-fills** the Region/District/Village fields with the station's location as editable defaults (`wireStationLocationDefaults()` → `paintLocationDefaults()`). **Police Officer** registration instead uses the station as a plain foreign-key dropdown (Section 1) and captures the officer's own **Regional & Origin Data** in a separate section (see *Officer Registration* below).
- **Storage** — **Stations**, **Officers**, **Crime incidents** and **Vehicles** persist in PostgreSQL (`police_stations`, `officers`, `crime_incidents`, `vehicles`) and sync from `GET /api/stations`, `/api/officers`, `/api/crimes` and `/api/vehicles` in `syncServer()` (localStorage remains an offline fallback). Central Police Search filters officers, stations and vehicles through the same cascading location filter — for officers it matches stored **origin** (`officerLocation()`). The `policesearch` / `stations` / `officers` / `cars` / `crimes` module keys are part of `ROLE_MODULES`; `policesearch` is granted to the System Admin, the Fingerprint Unit, the HR Directorate and the Chief Commander, and is explicitly **not** part of `AirportControl` or `CIDUnit` (the frontend mirrors the same denylist in `sanitizeModules()`, so a cached session cannot resurrect the entry). Registration modules are admin-only except crime intake for CID. `/api/me` drives nav visibility and the `go()` RBAC redirect.

### Police Officers — HR Directorate register (System Admin + `hr_officer`)

The **Police Officers** page carries three tabs, all of them available to **both** the System
Admin and the **HR Directorate** role (`hr_officer`). The registration entry forms live in
centered entry modals behind each tab's primary action button (＋ Register Officer · ＋ Nominate
for Promotion · ＋ Record Disciplinary Action); the tabs themselves hold the full-width tables
(each with its own search box over both the queue and the history):

| Tab | Colour | Contents |
|-----|--------|----------|
| **Officer Registration** | — | the *Central Officer Search* register table; the five-step registration wizard opens in a centered modal (`POST /api/officers`) |
| **Promotions & Commendations** | green `#2e7d32` | the **awaiting commander verification** queue (FIFO, oldest nomination first) with **Verify** / **Reject** actions, the verified/rejected history with the verifying commander, and the nomination form in a centered modal (`POST /api/officers/promotions`) |
| **Disciplinary & Misconduct** | red `#c62828` | the **open actions** queue with **Confirm** / **Close** actions, the confirmed/closed history, and the action form in a centered modal (`POST /api/officers/discipline` — misconduct, suspension, demotion, warning, investigation) |

The two badge tabs are operational views over exactly the rows the register queues count, and
the tab labels carry live counters (`hrPromoBadge` / `hrDiscBadge`). Confirming an action applies
its side effect to the officer record — a confirmed **Suspension** sets duty status to *Suspended*
(leaving the active force), a confirmed **Demotion** rewrites the rank, and **closing** the last
open action returns a suspended officer to *Active* — so the roster KPIs, rank distribution and
badge counts all move on the next refresh.

The **Police Officers** register itself is a five-step wizard (multi-tab `offStep(n)` flow) backed by `POST /api/officers` (multipart) with a mirrored client-side validator (`validateOfficerForm()`). Sections and rules:

1. **Official & System identifiers** — auto-generated *Service ID* (`POL-YYYY-XXXX`, from `new_service_id()`), *Rank* (`OFFICER_RANKS`), *Unit / Division* (`OFFICER_UNITS`), *Assigned Station* (foreign key to `police_stations`, required), *Date of Enlistment* (required) and *Duty Status* (`OFFICER_DUTY_STATUSES`, default **Active**).
2. **Personal identification** — *Full Name*, *Mother's Name*, *DOB*, *Place of Birth*, *Contact Number* (all required), plus *Height*, *Weight*, *Blood Group* (`OFFICER_BLOOD_GROUPS`) and the mandatory *Officer Picture* (JPEG/PNG, ≤ 5 MB).
3. **Regional & Origin data** — *State / Region of Origin* (`OFFICER_ORIGIN_REGIONS`: Sool, Sanaag, East Togdheer + other Somali regions), cascading *District of Origin* (`ORIGIN_REGIONS` gazetteer), and free-text *Town / Village*.
4. **Guarantor / Emergency contact** — *Name*, *Permanent Address*, *Contact* (required), *Occupation*, *Relationship* (`GUARANTOR_RELATIONSHIPS`) and an optional *Guarantor Picture*.
5. **Verification & supporting documents** — **Document Slot 1** (mandatory: type from `OFFICER_DOC_TYPES_PRIMARY` + PDF/JPG/PNG file) and **Document Slot 2** (optional: type from `OFFICER_DOC_TYPES_SECONDARY` + file; type and file must be provided together).

Server-side validation (`register_officer()`) enforces every mandatory field, the fixed dropdown option lists, the station foreign key, the upload extension/size policy (5 MB), and the coherent Slot 2 pairing — identical rules to the client, so a request that passes the form cannot be rejected by the API (and vice-versa). Uploads are persisted under `backend/uploads/` via `save_upload_validated()`.

### Operational page layout — unit overview strip + search boxes + centered entry modals

The operational unit pages (Fingerprint · Airport · Stations · Officers · Crimes · Cars) are
laid out as a clean workspace:

- **Compact unit overview strip.** Every operational page opens with a slim KPI strip
  (`renderUnitStats()`) of live counters computed from the same local register cache the table
  below renders, so the numbers always agree with the visible rows — unit stats at a glance
  without returning to the dashboard. E.g. Fingerprint → Applications · Pending review ·
  Approved · Rejected; Airport → Movements · Arrivals · Departures · Today · Suspect-linked;
  Checkpoints → Screenings · Flagged hits · Cleared · Distinct travelers (scoped to the active
  location filter, like the table); HR → Officers registered · Active force · Suspended ·
  Promotions awaiting · Open disciplinary. Charts, ratios and roll-ups stay exclusive to the
  Global Executive Dashboard.
- **Search box on every table.** Each register table's header toolbar carries a responsive
  search/filter input for instant, case-insensitive record filtering — Fingerprint
  (`fpSearch`), Airport (`airSearch`), CID cases (`caseSearch`) and suspects (`suspectSearch`),
  Checkpoints (`cpSearch`), Crime intake (`crmSearch`), both HR pane pairs (`prmSearch` /
  `dscSearch`, each covering its queue + history), plus the pre-existing Central Station /
  Officer / Vehicle / person searches.
- **No inline forms.** The permanent registration form boxes are gone from the page; nothing
  form-shaped is visible on the main view.
- **Primary action buttons + centered modals.** Each unit page carries one clean primary action
  button (e.g. **＋ Register Airport Passenger**, **＋ New Clearance Application**, **＋
  Register Officer**). Clicking it opens a **centered popup modal** (`.cmodal` +
  `openEntryModal()` / `closeEntryModal()`) over a dark blurred backdrop with a smooth
  fade/scale-in animation, containing the full entry form, its identity matching, document
  slots and validation — the form markup stays in the document (hidden until opened), so every
  field id and wiring behaves exactly as before. Escape or clicking the backdrop closes it with
  a matching scale-out. The Station modal is gated to SystemAdmin / `stations:manage`
  (`.admin-write`).
- **Full-width tables.** With the form out of the way, every register table spans 100% of the
  page — no horizontal scrolling on a clean workspace.
- **No per-page analytics.** The per-unit analytics strips were removed from the operational
  pages entirely (the compact overview strip above is plain counters only — no charts, no
  ratios, no extra API calls).
- The **Operations dashboard** quick-registration buttons navigate to the unit page *and* open
  its entry modal in one click (`quickAction()`).

### Departmental analytics (executive dashboard only)

Analytics is no longer rendered on the operational registers — the **only analytics surface is
the Chief Commander's Global Executive Dashboard** (HQ / Command: KPI tiles, department
overviews, region charts and the regional stations table, backed by
`GET /api/analytics/global`), with the **Stations Oversight** page providing the regional
roll-up for the same role. (The compact unit overview strip on the operational pages is not an
analytics bundle — just plain counters computed from the local register cache, no charts, no
ratios, no extra API calls.) The per-register analytics endpoints remain available server-side
for the executive/admin surfaces and programmatic consumers (every number is still computed
server-side — `kpis` summary cards, `charts` zero-padded `[{label,count}]` series and `lists`
badge rows):

| Bundle | Endpoint | Contents |
| --- | --- | --- |
| CID → **Fingerprint Unit** | `GET /api/cid/analytics` → `fingerprint` | Total biometrics logged, identity match rate, suspect hits + hit rate, pending/approved clearances, status & clearance-reason charts |
| CID → **Crime Department** | `GET /api/cid/analytics` → `crime` | Case volume by location, time-of-day buckets (06-12 / 12-18 / 18-24 / 00-06), crime categories, open vs. closed ratio + closure rate, active suspects |
| CID → **Checkpoint Unit** | `GET /api/cid/analytics` → `checkpoint` | Traveler screening volume, distinct travelers, flagged suspect hits **per checkpoint** (South / East / West), flag rate, screening-result ratio |
| CID → **Airport Unit** | `GET /api/cid/analytics` → `airport` | Inbound/outbound movement counts and shares, top routes, **active suspect movement alerts** list |
| **Police Officers** (HR Directorate) | `GET /api/officers/analytics` | Roster metrics (active force, rank distribution, duty status, officers per region, average service years), **Promotion list (green badge)**, **Disciplinary list (red badge)** |
| **Police Cars** | `GET /api/vehicles/analytics` | Fleet operational status + serviceable ratio, security alert breakdown, fleet by region, flagged-vehicle list |
| **Police Stations** | `GET /api/stations/analytics` | Operational capacity by tier, cell capacity, **deployment matrix** across Sool, Sanaag and East Togdheer, unstaffed-station list |

`GET /api/analytics?module=cid|officers|vehicles|stations|all` is the unified alias for the same
builders (`hr` / `cars` / `station` are accepted aliases; an unknown module returns **400**, never a
silent empty payload). `module=all` returns every bundle the caller is entitled to see and silently
omits the rest.

**RBAC.** The CID bundle is shared by the four directorate units and is *sectioned* by module: a
Fingerprint officer receives only `sections: ["fingerprint"]`, a Checkpoint officer only
`sections: ["checkpoint"]` — and that section is filtered to their own `location_scope`
(a South officer never sees East/West counts). `officers` requires the `officers` module — held by
**both** the System Admin and the **HR Directorate** (`hr_officer`), which therefore see an
identical bundle — `vehicles` any of `cars` / `policesearch` / `checkpoints` / `crimes`, `stations`
any of `stations` / `crimes`; everything else answers **401**. The legacy executive aggregation
(`GET /api/admin/analytics`, admin only) is unchanged and still powers the printable summary.

**HR Directorate records.** The promotion / disciplinary widgets are backed by two new tables
(`officer_promotions`, `officer_discipline`) with their own routes:
`POST /api/officers/promotions` (`PRM-YYYY-XXXX`, validates the proposed rank against
`OFFICER_RANKS` and refuses a same-rank nomination),
`PATCH /api/officers/promotions/{nomination_id}` (commander verification:
`Verified` / `Rejected` / `Awaiting Verification`, stamps `verified_by` + `verified_at`),
`POST /api/officers/discipline` (`DSC-YYYY-XXXX`; a `Demotion` must name a *junior* `to_rank`),
`PATCH /api/officers/discipline/{action_id}` (status / severity / suspension window / demotion
target — confirming a Suspension sets the officer's duty status to *Suspended*, confirming a
Demotion rewrites their rank, and closing the last open action returns them to *Active*),
plus `GET /api/officers/promotions` and `GET /api/officers/discipline` for headless reads.
All of them are gated on the `officers` module, so the System Admin and the HR Directorate share
the exact same rights here. Station and vehicle **writes** stay SystemAdmin-only
(`POST /api/stations`, `POST /api/vehicles`, `POST /api/vehicles/{id}/status`): the HR Directorate
reads the station register for postings and the vehicle register through Central Police Search,
and the station create form is hidden for them (`.admin-write`).
The **green badge** counts only nominations that are `Awaiting Verification` **and** belong to an
officer whose `duty_status` is `Active`; the **red badge** counts actions still open
(`Pending` / `In Review` / `Appealed`).

### Admin User Management (admin only)

The **User Management** page (admin only) lets a System Admin create, edit, activate and deactivate officers and assign their role and location scope. The backend supports `GET /api/admin/users`, `POST /api/admin/users`, `PATCH /api/admin/users/{id}` and `GET /api/admin/users/{id}` for headless provisioning.

A standalone migration script applies the RBAC schema to an existing database without re-creating it:

```bash
python3 backend/migrate_rbac.py
```

## Architecture

The system now has two parts:

- **Frontend** — `index.html`, a single-page browser application.
- **Central backend** — `backend/server.py`, a Python standard-library HTTP API backed by PostgreSQL via psycopg2. It serves the frontend and a JSON REST API from the same origin, and enforces the central-person rule on the server.

Airport, Fingerprint, CID and Checkpoint unit records are all written to the central database; checkpoint screening results (Flagged match / No active alert) are computed server-side from active suspect alerts, and the action follows automatically (Supervisor contacted / Cleared).

The frontend automatically uses the central backend when it is loaded through `backend/server.py`. If it is opened as a static file with no server, it falls back to browser local-storage demo mode (a "Local demo mode" notice appears in the browser console).

## Run locally (full stack)

Python 3 is enough — no packages to install:

```bash
python3 backend/server.py
```

Windows:

```bash
py backend/server.py
```

Then open `http://localhost:8001` (the backend serves the UI and the API together). The port can be changed with the `PORT` environment variable, and the PostgreSQL engine settings (database, user, password, host, port) with the `SENTINEL_DB_*` variables in the root `.env` — see `backend/README.md`.

### Demo accounts (development only)

Nine demo users are seeded automatically on first run — one per role — all with
password `ChangeMe123!`. This makes it easy to exercise the role-based access
control and location-isolated checkpoints:

| Username     | Role                | Scope / Module             |
|--------------|---------------------|----------------------------|
| `admin`      | System Administrator| All modules + analytics + user management |
| `fp.officer` | Fingerprint Unit    | Fingerprint register · Central Person Search (no police search) |
| `ap.officer` | Airport Control     | Airport only               |
| `cid.officer`| CID Criminal Unit   | CID / suspect alerts only  |
| `hr.officer` | HR Directorate      | Police Officers (roster + promotions + discipline) · Police Stations (read) · central search |
| `cp.south`   | Checkpoint South    | Checkpoint · South only    |
| `cp.east`    | Checkpoint East     | Checkpoint · East only     |
| `cp.west`    | Checkpoint West     | Checkpoint · West only     |
| `chief`      | Chief Commander (HQ / Command) — *Commander / High Command* | Global Executive Dashboard · Stations Oversight · **read-only** visibility across every department, register, log and search — every write answers `403 Forbidden` |

These accounts are created automatically on first run and must be removed or
changed before any real deployment. To add a real admin, sign in as `admin`
and use the **User Management** page in the UI, or `POST /api/admin/users`.

See [`backend/README.md`](backend/README.md) for the full API reference,
including the RBAC enforcement rules.

### Frontend-only demo

To view just the interface with local-storage data (no server):

```bash
python3 -m http.server 8000 --bind 0.0.0.0
```

Open `http://localhost:8000`.

## Testing

Officer profile, badge-attribution and role-driven location suite (boots the real server
against a throwaway PostgreSQL cluster; needs `psycopg2-binary` + `pgserver`):

```bash
python3 backend/test_officer_profile_locations.py
```

Covers the cascading **Region → District → (Checkpoint | Station / Branch / Unit)** assignment for
both drawer flows, the badge number every user payload now carries (`FP-102` →
`Badge #FP-102`, `#Not recorded` only when a row genuinely has none), `GET /api/admin/audit`
attribution, the self-service profile endpoints (`PATCH /api/me`, `POST /api/me/avatar`,
`POST /api/me/password`) and the Commander's unchanged `403 read_only_role` firewall.

The original standard-library `backend/test_server.py` predates the PostgreSQL-only backend and is
kept for reference only; it cannot boot against the current storage layer. Use the suites in
[TESTING.md](TESTING.md) instead.

Read-only / unit-module regression suite (boots the real server against PostgreSQL; skipped when no
database is configured):

```bash
python3 backend/test_read_only_rbac.py
```

Pins the two RBAC changes end to end: the Airport Control and CID Criminal Unit module sets
(`ap.officer` → `{dashboard, people, airport}`, `cid.officer` → `{dashboard, people, cid, crimes}` —
never `policesearch`), the Commander's global read set (21 dashboards/registers/logs/searches return
`200`), the global write firewall (**25** refused calls across every route and all four verbs
`POST` / `PUT` / `PATCH` / `DELETE` return `403` with `code: read_only_role` — including stations,
which the role used to manage, and unknown paths, which are refused before routing), the empty
`quick_actions` payload, and that every `Commander` / `HighCommand` / `high_command` / `command_hq` /
`hq_command` / `police_hq` / `chief.commander` spelling resolves to the same read-only role while
SystemAdmin and the unit officers keep writing (a SystemAdmin `PUT` still gets the ordinary `405`).

The suite also drives a **role-spelling matrix** directly against the server module: 32 spellings of
the three restricted units (Fingerprint, Airport Control, CID Criminal Unit) must resolve to their
own family and never `policesearch`, 12 other role spellings must keep it, unknown roles must be
dashboard-only, and `rbac_self_test()` must be clean.

The frontend half of the same contract is pinned in `backend/test_frontend_session.mjs` (the
sidebar-removal code path, no *Print* link for a read-only session, `hardenReadOnlyDom()`
returning the number of controls it changed, the entry points and the local `api()` firewall) and in
`backend/test_print_fit.py` (the `application.html` read-only contract: marked control, view-only
note, fail-closed session seed, `/api/me` flags, `applyReadOnlyUi()`, and `approve()` refusing
locally). Sidebar removal/restore and the per-page control sweep are exercised behaviourally against
the running server (jsdom), including a denied module coming back for an allowed role in the same
tab.

It also runs a dedicated **departmental analytics suite** (`departmental_analytics_suite()`), which
boots a *second, isolated* server against a fresh database holding a fully deterministic fixture and
asserts the **exact arithmetic** of every department endpoint:

- `GET /api/cid/analytics` — biometrics logged / unique persons / repeat captures and the derived
  identity-match and suspect-hit rates; case volume by location, the four 24-hour buckets
  (recomputed independently from the raw `created_at` stamps), category counts and open-vs-closed
  ratios; screenings, flagged hits and flag rate **per checkpoint** plus the scoped read for
  `cp.south` / `cp.east` / `cp.west`; inbound/outbound counts, shares and suspect-movement alerts.
- `GET /api/officers/analytics` — active force, rank/duty/region distributions, average service
  years, the green promotion badge (a retired officer's nomination must *not* count) and the red
  disciplinary badge (misconduct / pending suspensions / demotions), including commander
  verification moving a nomination off the badge.
- `GET /api/vehicles/analytics` — In Service vs. Maintenance / Out of Service / Decommissioned,
  serviceable ratio, alert breakdown, clean civilian registrations and the flagged-vehicle list
  (re-asserted after flipping a vehicle to *Wanted in Crime*).
- `GET /api/stations/analytics` — capacity by tier, cell capacity totals/averages and the
  deployment matrix (stations, officers, *active* officers and vehicles per region and per station).
- `GET /api/analytics?module=…` — byte-identical payloads to the direct routes, the `hr` / `cars`
  aliases, `module=all`, a `400` for an unknown module, and the per-module RBAC matrix
  (including that `module=all` silently omits bundles the caller may not see).

Review-gate regression suite (PostgreSQL; uses the configured test database or a temporary `pgserver` cluster, and performs timestamp backdating through the application's connection adapter):

```bash
python3 backend/test_review_gate.py
```

Pins the three mandated approval rules over HTTP: the **12-hour rule** (a Fingerprint Officer — canonical or `fingerprint_officer` alias, on both `/api/fingerprint/applications/<id>/approve` and the legacy `/api/clearance-applications/<id>/approve` route — gets `400 review_period_active` with the exact spec message on a fresh application; 11.9 h stays locked, 12.1 h releases and issues the certificate), the **admin bypass** (`admin` / `SystemAdmin` approve instantly with `review_period_bypassed: true` and `can_approve: true` even while the row is inside the window), and the fail-closed guarantees (missing `created_at` locks officers but never admins, foreign roles hit the module gate with 401, unknown ids 404, re-approval is idempotent, and the gate still enforces after a server restart on persistent sessions).

Approve/Print button journey (Node ≥ 18; drives the real `index.html`, `application.html` and `certificate.html` scripts against the real backend in VM sandboxes):

```bash
node backend/test_approval_flow.mjs
```

Reproduces the "the approve/print button does not work for either users or administrators" report end to end: `syncServer()` merges the server register into `db.fingerprint` (the stray `cd is not defined` line used to abort it before any row was painted), `checkBackendBuild()` resolves instead of rejecting with `seen is not defined`, the officer's fresh-application control renders disabled ("🔒 Review Locked (12h)" + remaining-hours badge) and `approveFP()` refuses without touching the network, the same handler approves successfully once the submission is backdated past +12 h, the admin register row renders an enabled "✓ Approve" action immediately and the click executes (201 → certificate), the stale-backend banner is created/removed correctly, the printable page's Approve button retains its admin-bypass behavior, even when the 12-hour gate is active, and `certificate.html` releases its Print button only after an approval.

Frontend session smoke test (Node ≥ 18; executes the real inline script against the real backend in a VM sandbox):

```bash
node backend/test_frontend_session.mjs
```

Verifies the checkpoint-officer refresh journey: sign in as `cp.south`, token/user persisted to `sentinel_token` / `sentinel_user`, page refresh re-hydrates the session before the API sync (no auto-signout, no 401/404), the checkpoint count survives the refresh, an empty server sync never wipes local rows, a bogus token signs out only via an explicit `/api/me` 401, and a server-down load keeps the officer signed in.

Registered Stations row actions — View / Edit permission suite (PostgreSQL; uses the configured test
database or a temporary `pgserver` cluster):

```bash
python3 backend/test_station_actions.py
```

Pins the Actions column contract end to end: `GET /api/stations/<id>` returns the full record
(registry fields, officer / vehicle deployment counters, mirrored Police Stations branch lineage and
the per-session `can_edit` flag) to every session that may open the register (SystemAdmin, HR
Directorate, read-only Commander) and 401 to a session without the `stations` module; `PATCH` and
`PUT /api/stations[/<id>]` are served for the SystemAdmin / Admin role and answer **403 Forbidden**
(`code: admin_only`) for the HR Directorate, a checkpoint officer **and** the Commander (the last of
which is refused even earlier by the read-only firewall with `code: read_only_role`); a refused write
never alters the row; the edit validation mirrors station registration (district must belong to the
region, status from the fixed list, name required, mirrored `BR-<id>` entries refused with an
explanation); the update is audited (`UPDATE police_station`, changed fields in `details`), stamps
`updated_at` / `updated_by`, and `PUT /api/persons` keeps its ordinary `405`.

The frontend half is pinned in `backend/test_station_frontend.mjs` (jsdom):

```bash
node backend/test_station_frontend.mjs
```

The same journey is driven against a live server and database in
`backend/test_station_integration.mjs` (`PYTHON="$PWD/.venv/bin/python" node backend/test_station_integration.mjs`):
the real page script signs in as each role, syncs the register from the API, opens the View drawer on
the server payload, saves an Edit through `PATCH /api/stations/<id>` and reads the change back, while
the HR Directorate and Commander attempts are refused with `403` (`admin_only` / `read_only_role`) and
never touch the row.

It renders the Registered Stations table for an administrator (View + Edit on every persisted row),
for the HR Directorate, a unit officer and the read-only Commander (View only — the Edit modal
refuses to open and the DOM sweep removes a painted Edit control), asserts a mirrored `BR-<id>`
branch entry stays view-only, drives the View drawer (code, name, Region → District → Village,
operational status, officer / vehicle counts, commander, mirrored branch lineage from the
authoritative `GET /api/stations/<id>` payload with a local-row fallback), and drives the Edit modal
(prefill, PATCH `/api/stations/<id>`, register re-render, validation before any request, and an
offline save reported as an unsynced draft).

Conduct & disciplinary UI journey test (Node ≥ 18):

```bash
node backend/test_conduct_frontend.mjs
```

Drives the Officers Registration Office flow through the real inline script: sign in as `hr.officer`, open the HR Action Modal, search the target officer by Service ID (`POL-YYYY-XXXX`), file a Rank Advancement with the mandatory narrative, watch the green/red split-view badges update, execute the rank change from the HR Approval Desk with one click (the officers register refreshes to the new rank), reject a Rank Demotion without touching the rank, view the immutable service history, and confirm `/api/conduct` stays denied to non-HR roles.

Print-template contract tests (standard library only):

```bash
python3 backend/test_print_fit.py
```

Pins the official-template rules for `application.html` / `certificate.html`: the exact `@page { size: A4 portrait; margin: 8mm }` + `print-color-adjust: exact` print block, all web chrome hidden when printing, the emblem placement (application: watermark only; certificate: masthead + watermark), every dynamic DOM binding (4-part legal name, DOB, National ID/Passport, phone, address, gender, occupation, purpose chips, guardian/guarantor, 35×45 mm photo box, serial/QR placeholders), the preserved endpoints/auth checks/12-hour review-lock logic, and a conservative worst-case height budget proving each document fits one A4 page.

## Demo workflow

1. Open **Airport** and type `Ayaan / Cabdi / Xasan / Axmed`, DOB `1997-04-18` and `10012345` — the unified identity form matches central person `P-0001` in real time and auto-fills the existing data.
2. Open **Fingerprint Unit** and type the same identity; an exact match auto-fills the applicant fields.
3. Complete clearance reason, guardian details, and attach **at least 2 applicant and 2 guardian documents** (plus an optional photo), then save.
4. In the Fingerprint register click **Print** to open `application.html` — print the Day-1 summary and use **Approve Application**. Sign in as `fp.officer` and the button is disabled with a "review lock" note until the mandatory 12-hour period has elapsed; sign in as `admin` and the same application can be approved instantly.
   **Citizenship exception:** no 12-hour delay applies; approve and print immediately. All other reasons keep the existing waiting period.
5. After approval, click **Certificate** to open `certificate.html` — the Day-2 clearance certificate is now unlocked and printable.
6. Open **CID Criminal Unit → Add suspect** and type a new identity. See the real-time match banner; submit **without a linked case** and the suspect is recorded with origin **Direct Intelligence Listing**. The **Suspect reason / alert details** field is **mandatory when no Crime Case is linked**; when a case IS linked it can be left empty and automatically defaults to `Linked to CID case {code} — {category}`. Submitting with an exact match reuses the existing central record.
7. Open a case workspace: edit the incident summary (tab 1), link participants (tab 2 — choosing *Suspect* raises a checkpoint/airport alert; the case is optional, and a participant note is required when no case is linked), and upload evidence (tab 3).
8. Open **Checkpoints → Record stop** for a listed suspect and see the automatic "Flagged match" screening. The stop is saved to the central database and the screening result is computed server-side against active suspect alerts. The checkpoint modal is a **full traveler + guardian screening layout**: traveler (4-part name, DOB, place of birth, current/permanent address, purpose of visit, real-time photo, optional National ID/Passport, **≥1 of 2 document slots**), guardian (name, relationship, contact, permanent address, occupation, optional IDs, **≥1 of 2 document slots**). Smart identity resolution auto-fills **both** traveler and guardian, and all uploaded files are stored in `backend/uploads/` and referenced from the stored event.
9. Sign in as `hr.officer` (Officer Registration Office) and open **Police Registrations & Management → Conduct & Discipline**. Click **＋ New conduct action**, search an officer by Service ID, pick the green *Promotion / Commendation* type with *Rank Advancement*, choose a higher rank, write the detailed justification (station report number / case reference) and submit — the file enters the queue as `ACT-YYYY-XXXX · Submitted to HR` in the **Promotions & Commendations** tab. Switch to the **HR Approval Desk**, pick the reviewing HR officer and click **✓ Approve** — the officer's rank in the register updates automatically and the immutable service-history entry appears in the file view. File a red *Disciplinary / Penalty* action (e.g. *Rank Demotion*) to see the **Disciplinary & Misconduct** tab, and reject it to leave the rank untouched.

Uploaded files are stored in `backend/uploads/` (git-ignored) and served from `/uploads/`.

## Important implementation note — development only, not for operational police data

This is now a **connected development system**: the browser UI talks to a central
backend API, and server data is stored in a live PostgreSQL database
(`sentinel_police`, configured through the root `.env` / `SENTINEL_DB_*` variables)
instead of only browser local storage. **It is still not ready for real police
data.** It currently uses:

- **psycopg2 + PostgreSQL** — a real engine, but with development-grade
  connection defaults and no TLS/credential-management hardening yet
- **Development authentication** — a single hard-coded demo login (`admin` / `ChangeMe123!`), in-memory session tokens, and unsalted SHA-256 password hashing
- **No HTTPS** — traffic is plain HTTP
- **Role- and location-based permissions partially implemented** — the server now enforces role-based access control for the operational modules (System Admin / Fingerprint Unit / Airport Control / CID / Checkpoint South·East·West) and location isolation for Checkpoint users, and the departmental analytics endpoints (`/api/cid/analytics`, `/api/officers/analytics`, `/api/vehicles/analytics`, `/api/stations/analytics`) still surface summary metrics, crime distribution, checkpoint volumes, fleet status, roster/HR badges and the station deployment matrix for the executive dashboard and programmatic consumers (the legacy executive aggregation remains available to admins at `/api/admin/analytics`). The hard-coded demo logins and the unsigned `ChangeMe123!` default password are still in use.
- **No production deployment** configuration
- **No evidence file security** or chain-of-custody storage
- **No backup service** or disaster-recovery process

Before operational use, the hardening work **must** include, at minimum:

- **PostgreSQL** (or another managed production RDBMS) with migrations and least-privilege database users
- **Secure password storage** (salted, slow hashes such as Argon2/bcrypt) and real account provisioning
- **Role- and branch-based permissions** enforced on the server, with per-unit access control
- **HTTPS / TLS** for all traffic, plus secure cookies/headers and secrets management
- **Immutable, tamper-evident audit logging** (append-only, with integrity protection)
- **Evidence file storage with chain of custody** (encrypted at rest, access-logged, retention-enforced)
- **Automated backups and tested disaster recovery**
- **Production-grade authentication** (identity provider / SSO or properly managed auth, MFA, lockout)
- Server-side validation and duplicate matching across the full data model
- Certificate QR verification
- Network/offline synchronization policy
- Legal rules for suspect alerts, clearance decisions and data retention
- Supervisor confirmation for possible suspect matches

The local-storage fallback in the frontend is for demo convenience only and is
not appropriate for live police operations or multiple computers.

The current data model is intentionally compatible with a relational implementation using tables such as `persons`, `unit_records`, `airport_passengers`, `clearance_applications`, `crime_cases`, `case_participants`, `suspect_alerts`, `checkpoint_events`, `locations`, `users`, and `audit_events`.


## Form and identity-profile improvements (testing branch)

- Submit validation is shared by inline forms, entry modals and modal-footer
  save buttons. It combines HTML validity with conditional identity, document,
  officer, vehicle and other registration requirements; scroll/focus follows DOM
  order, including hidden officer wizard steps. Errors clear as fields become
  valid or conditional requirements no longer apply.
- Successful registration closes its entry modal. Successful case-workspace
  saves return to the CID register. Branch Management hides the saved form and
  offers **Add another branch**. API/validation failures leave entries open.
- **Identity profile → Linked Unit Records** fetches
  `GET /api/persons/{person_id}/linked-records`: source record/table, recording
  branch, branch region, uploader/account branch, UTC timestamp and recorded
  location context. Results respect the caller's unit and checkpoint scope.
- **Proximity is not fabricated.** There are no live person or branch coordinates
  in this data model. Nearby/current branch is explicitly **Not determined**;
  dated unit locations and recorded residence are context, not live tracking.
  Uploader branch reflects the user's **current account details**, not a
  historical upload-branch snapshot. Missing legacy branch data is labelled.

See [TESTING.md](TESTING.md) for the focused automated tests and officer UAT checklist.

## Registered Stations — View / Edit row actions (testing branch)

The **Police Stations → Registered stations** table now carries an **Actions** column:

- **View** opens a read-only station record drawer with the full metadata: station
  code and id, station name, **Region → District → Village**, operational status,
  station tier, contact phone, cell capacity, commander / deputy, notes, the
  **officer** and **vehicle** deployment counters (counted from the `officers` /
  `vehicles` registers) and the **mirrored branch lineage** (a Police Stations
  branch entry, `BR-<id>`, resolves to its mirrored registry row). It is available
  to every session that may open the register — SystemAdmin, the HR Directorate
  and the read-only Commander — and is served by `GET /api/stations/<id>`.
- **Edit** opens the administration modal (name, Region → District → Village,
  operational status, plus tier / phone / cell capacity / notes) and saves through
  `PATCH /api/stations/<id>` (`PUT /api/stations[/<id>]` is accepted too). The
  station id and code are immutable, the update stamps `updated_at` /
  `updated_by` and is written to `audit_events` (`UPDATE police_station`).

**Role rules — Edit is a SystemAdministrator / Admin capability.** The Edit action
is rendered only for `body.is-admin` and `can_edit_records` (the flag the API
returns in the session payload and the visibility block); the server enforces the
same rule independently — `require_records_admin()` answers **403 Forbidden**
(`code: admin_only`) for every non-admin role on `PUT` / `PATCH /api/stations`,
while the read-only Commander is refused even earlier with
`code: read_only_role`. A standard officer (including the HR Directorate, which
may read the register for postings) keeps View only, and a `BR-<id>` synthetic
mirror is view-only even for an administrator — it is edited in Branch Management.
`can_edit_records` / `can_edit_stations` are the reusable capability flags the same
administration rule exposes to every management table, so admins keep full edit
access wherever an inline Edit action exists.

## Clearance purpose, document viewer, certificate print lock & field-level RBAC (testing branch)

**Clearance purpose is visible everywhere a clearance record is read.**
`GET /api/fingerprint/applications` keeps returning the stored `purpose`
(Education / Travel / Employment / Citizenship / Licence) and the frontend renders
it as a colour-coded chip instead of hiding it in the detail JSON:

- the **Fingerprint register** gained a `Purpose` column (`purposeBadge()`), so the
  queue can be scanned without opening a record;
- the **review modal** (`openClearanceReview`) shows the purpose chip in its header
  and in the summary grid next to the applicant tile;
- the printable **`application.html`** and **`certificate.html`** pages show the same
  chip in their toolbars and inside the printed purpose line.

**Photographs and documents open in a fullscreen viewer.**
Every applicant/person photograph and every image document card in the person
detail modal is rendered as an `<img>` (extension-aware `documentExtension()`), not
as a generic file icon, and carries `data-image-zoom`. Clicking one opens
`#imageLightbox`: wheel or `+` / `−` zoom (25 %–400 %), drag to pan, `0` / *Reset*
to fit, *Open in new tab*, and `Esc` / backdrop click to close. Non-image documents
keep their file icon and open link.

**Certificate printing is locked until the signed paper application is scanned.**
`certificate_print_state()` is the single source of truth and is published as
`certificate_print` on the clearance list and detail payloads:

```json
{"unlocked": false, "locked": true, "requires_signed_scan": true,
 "signed_scan_present": false, "admin_bypass": false,
 "read_only_bypass": false, "reason": "Scan the signed ...", "editable_by": [...]}
```

Unlocked = **SystemAdmin / Admin** (bypass), **Commander / High Command**
(view-only, prints what an officer issued) or **`signed_scan_present`** for
everyone else. The register row, the review modal, `application.html` and
`certificate.html` all gate on that verdict — the deep link is refused too, so a
bookmarked `certificate.html?id=…` cannot print an unlocked certificate for a
regular officer. Uploading the signed scan (`POST
/api/fingerprint/applications/<id>/signed-document`) unlocks it immediately.

**Field-level editing in Person Details.** Regular users may edit only **contact
phone**, **residence address** and **occupation**; full legal names, mother's name,
DOB/POB, National ID, passport ID, gender, email and every other biographic/legal
field stay read-only. SystemAdministrators / Admins edit every field. The rule is
enforced in **both** places: the UI disables the inputs and sends only the permitted
keys, and `PATCH /api/persons/<id>` refuses a protected change with **403** `code:
field_edit_forbidden` (plus `restricted_fields`, `editable_fields`,
`admin_bypass: false`) — atomically, so a bundle containing one identity change
persists nothing. An unchanged identity echo is allowed, and creating a new person
(`POST /api/persons`, `/upsert`) is unchanged.

**The person profile answers "why is this person being cleared?".** The detail
head card carries a purpose chip for the **newest** clearance application of the
viewed person (`personClearanceSummary()`), labelled `Clearance` with the same
Education / Travel / Employment / Citizenship / Licence tones used everywhere else.
When the person has more than one application the chip adds `+N earlier` and its
tooltip names the application behind it. A person with no application keeps the
header clean — no placeholder chip is invented.

**One edit action, no indicator badges.** The person profile footer offers a single
**✏ Edit Details** action that opens the role-aware inline editor (`Cancel` /
`Save details`); the previous `Edit profile` + `Edit / append details` pair is
gone, and the register's **+ New / update person** flow still covers creating a
new identity or merging through the live match. Inside the editor, fields the role
may not change are ordinary disabled inputs (`.pv-locked`, `aria-readonly=true`,
hover hint) — the old per-field `🔒 Admin only` / `Derived` tags were removed and
the restriction is explained once in the role note under the grid.

See [TESTING.md](TESTING.md) for the suites and the officer UAT checklist.

## Register row numbering — reverse sequence `#` (testing branch)

Every primary register now opens with a compact **`#`** column. Because the
registers render newest-first, the number counts **down** the visible rows:

| Position | Example (6 records) |
|----------|--------------------|
| first row (newest record) | `6` |
| second row | `5` |
| … | … |
| last row (oldest record) | `1` |

The number is derived from the **filtered** result set on every paint
(`reverseSequence(index,total)` → `total − index`), so typing in the table search
box, switching a checkpoint location chip, or registering a new record
immediately renumbers the table — no refresh, cache or extra state.

```js
list.map((row, index) => `<tr>${sequenceCell(index, list.length)} … </tr>`)
```

- **Where** — Fingerprint register, Central Person Registry, Airport register,
  CID cases, CID suspects, Checkpoint screening, Registered Stations, Police
  Officers, Vehicles, Crime intake and all three Central Police Search tabs.
- **Layout** — a fixed 46 px (38 px on small screens) right-aligned column with
  tabular figures; the header and body counts stay in step, the empty-state
  `colspan` was widened with the table and **Actions stays the last column**, so
  nothing else moved and `.table-wrap` still scrolls horizontally on narrow
  screens.
- **Markup** — `<th class="seq" scope="col">#</th>` and
  `<td class="seq" data-seq="6">6</td>` (the `data-seq` attribute is what the UI
  suite asserts against). Highlighted biometric-match rows tint the number too.

## Officer badges, audit attribution, profile modal & role-driven site assignment (testing branch)

### Role-driven cascading location pickers (User Management → New / Edit Officer)

The New Officer drawer and the Edit Officer modal now share one **Region → District → site**
cascade. The third selector changes shape with the role family:

| Role family | Region | District | Third selector | Hidden field |
|---|---|---|---|---|
| Checkpoint (`checkpoint_officer`; legacy `CheckpointSouth/East/West`, `cp_south`, … normalise to it) | required | required | **Checkpoint** — only the *active* checkpoints of that district | Station / Branch / Unit |
| Station / Unit (Fingerprint, Airport, CID, HR, Police Station / Branch units) | required | required | **Station / Branch / Unit** — the stations and branches registered in that district | Checkpoint |

- Changing **Region** re-populates (and clears) **District**; changing **District** re-populates
  (and clears) the checkpoint / unit list. No stale option from another district can be submitted.
- The catalogues are the live registries the app already loads — `police_stations`
  (`station_tier = 'Checkpoint'` rows are the checkpoints, every other tier plus every
  `police_branches` row is a station/branch/unit) and `police_branches`, filtered by
  region + district and, for checkpoints, `operational_status = 'Active'`.
- The composed posting is stored in the existing `users.branch` column
  (`Name · District · Region`) and a Checkpoint role also stores the checkpoint as its
  `location_scope`, so downstream scope filters are unchanged. A legacy free-text branch (an old
  client or a demo account) still works exactly as before.

### Badge numbers and audit attribution

- Every account carries a `badge_number` (`FP-102`, `AP-201`, `CP-501`, `ADM-101`, `CMD-901`, …).
  It is returned by `/api/login`, `/api/me`, `GET /api/admin/users` and
  `GET /api/admin/users/{id}` together with a printable `badge_label` (**`Badge #FP-102`**).
- Migration backfills a deterministic badge for every existing row, so a legacy account is never
  left blank; `#Not recorded` is reserved for a genuinely empty value and is never invented.
- **User Management → Audit trail** (`GET /api/admin/audit`) lists the append-only `audit_events`
  with the acting officer, role and badge chip. Badge attribution therefore reads
  *Badge #FP-102* (or *#Not recorded* when a row truly has none) instead of always falling back.
- `PATCH /api/admin/users/{id}` audits *which fields changed*, and every JSON response is sent with
  `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` so a reload never replays a stale
  roster or audit page.

### Officer Profile (clickable header identity block)

Clicking the officer's name / avatar in the top-right header opens **Officer Profile**
(`#officerIdentity` → `#officerProfileModal`):

- **Display name** — 2–80 characters, saved with `PATCH /api/me`; the header, sidebar footer and
  user table update immediately.
- **Avatar** — pick one of the built-in colour presets (initials avatar) or upload a
  JPG / PNG / WebP / GIF up to 5 MB (`POST /api/me/avatar`).
- **Password** — current password + new password twice (`POST /api/me/password`); the current
  password is re-checked, every *other* browser session for the account is signed out, and the
  session that made the change stays signed in.
- The global read-only Commander may open the profile but keeps the existing zero-write contract:
  the three endpoints answer `403 read_only_role` exactly like every other mutation.

### Instant dashboard refresh

Clearance approvals, signed-scan uploads, checkpoint screenings, officer / station / branch /
vehicle registrations and unit updates now call `refreshLiveMetrics()` right after the successful
write: the executive KPIs and the activity feed repaint from `/api/dashboard` — no reload, no cache
clear, no manual sync.

## One Checkpoint Officer role & per-record audit history (testing branch)

### A single, scalable checkpoint role

`CheckpointSouth` / `CheckpointEast` / `CheckpointWest` are gone as roles. Every checkpoint
officer now holds the one **`checkpoint_officer`** role, and *which* checkpoint they command is
**data**:

| Stored field | Example | Meaning |
|---|---|---|
| `users.role` | `checkpoint_officer` | the same role for every checkpoint officer |
| `users.location_scope` | `South` / `Adhi Cadeeye Outpost` | the checkpoint (or district post) the officer is scoped to |
| `users.branch` | `Adhi Cadeeye Outpost · Laascaanood · Sool` | the readable posting label |

- **Assigning** — User Management → New / Edit Officer → role **Checkpoint Officer** switches the
  third selector to **Checkpoint** (Region → District → the *active* checkpoints of that district)
  and hides Station / Branch. Any other role does the reverse. Changing the region resets the
  district, changing the district resets the posting, and the selection is stored exactly as above.
- **Scaling** — adding a checkpoint is a data entry in the station/branch registry; it appears in
  the cascade immediately and needs no new role, no code change and no migration.
- **Compatibility (zero breaking changes)** — every historical spelling still normalises to the
  unified role and keeps its area (`cp_south` → `checkpoint_officer` + `South`), `migrate()` rewrites
  stored compound rows in place (`unify_checkpoint_roles()`), keeps an explicit
  `location_scope`, and is idempotent. The compound roles were removed from `ALL_ROLES` only, so
  they can never be assigned again — the API, sessions, RBAC gates, module sets and permissions are
  unchanged.

### Audit history on the record itself

Every primary record view now carries an **Audit history** tab (Person Details, Police Registration)
or section (**Police Stations → View**):

- The full chronological log, newest first: identity creation, enrichment/updates, approval,
  signed-scan upload, checkpoint screening, station registration / edit, account changes.
- Each event shows the readable action (*Created*, *Updated*, *Uploaded*, *Approved*), the acting
  officer, the role and the **badge chip** (`Badge #FP-102`, or `#Not recorded` when a row really
  has none), the record the event belongs to, the details and the UTC timestamp.
- `GET /api/persons/{person_id}/audit-history` gathers the identity’s events plus every linked unit
  record the caller may read (clearance applications **and** their signed scans, airport movements,
  checkpoint screenings inside the officer’s scope, CID suspect listings).
- `GET /api/audit/entity/{entity}/{id}` serves any other record: `person`, `officer`,
  `police_station`, `clearance_application`, `checkpoint_event`, `suspect_alert`, `vehicle`,
  `conduct_action`, `user`, … Each entity kind declares the module that governs it, so a record’s
  history can never show more than the register the viewer could already open
  (`403 audit_scope_forbidden` otherwise, `404` for an unknown entity kind).
- Both surfaces read the **same append-only `audit_events` rows** as the administrative register in
  User Management, so the record history is always a subset of the admin trail — never a second log
  that can drift.
