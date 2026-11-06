# Fingerprint Unit — Requirements (Release 1.0)

**Phase 3 deliverable A · Requirements and architecture only. No application code was changed.**
Branch `arena/6303ef2f-sentinel-police-management` · assessed against commit `a1c2478` · 2026-11-06

> **Owner decision D-18 — APPROVED and now binding:** Release 1.0 Fingerprint Unit includes **both**
> the clearance/identity-review workflow **and genuine biometric capture and matching.**
> This document is written to that scope.

---

## 0. Statement of fact before any requirement

**There is no genuine biometric functionality in the system today.** This is stated plainly because
the user interface strongly implies otherwise.

| What the UI suggests | What the code actually does | Evidence |
|---|---|---|
| Fingerprints are enrolled and stored | Nothing biometric is stored server-side. There is **no template column, no biometric table, nothing in the DDL** | `backend/server.py` schema; no `template`/`minutiae`/`biometric` column exists |
| A captured print is matched against the registry | A **string** is compared against other strings — person id, a `BIO-…` label, a filename, national ID, passport — with `includes()` substring tests | `index.html:4526-4575` `matchPersonByFingerprint()` |
| Captured biometrics persist | They are written to **browser `localStorage`** under `sentinelBiometrics`, seeded with nine hard-coded demo entries | `index.html:2698-2726` |
| "Biometrics logged" is a biometric count | It is `COUNT(clearance_applications)` | `cid_fingerprint_analytics()` `:6071` |
| A live scan identifies the right person | **If no string matches, the code returns an arbitrary person from the registry by rotating a cursor** (`window._bioScanCursor`) | `index.html:4573-4578` |

**That last row is the most serious functional defect found in the entire assessment.** A "live scanner
fallback" that cycles through the person list and returns whoever is next is not a weak match — it is
a **fabricated identification**, and the UI presents the result as *"⚡ Biometric Fingerprint Match
Found — Linked to Central Person Record #…"*. Requirement **FPR-902** removes it.

**What genuinely does exist and is worth keeping** is described in §2. It is more than nothing: the
hardware bridge *protocol* is specified, and the server-side identity-resolution engine is real.

---

## 1. Terminology (used consistently in this document)

| Term | Meaning here |
|---|---|
| **Capture / acquisition** | Obtaining a fingerprint **image** from a sensor, with a quality score |
| **Template** | A vendor or standard-format encoding of minutiae derived from the image (ISO/IEC 19794-2, ANSI-378, or a vendor-proprietary format) |
| **Enrolment** | Storing a subject's templates against a person record so they can later be matched |
| **Verification (1:1)** | "Is this person who they claim to be?" — compare a probe against **one** enrolled identity |
| **Identification (1:N)** | "Who is this?" — compare a probe against **all** enrolled identities |
| **Threshold** | The comparison score at or above which the system declares a candidate match |
| **FAR / FRR** | False Accept Rate / False Reject Rate — the two error rates a threshold trades off |
| **Failed capture (FTA)** | The sensor could not produce an image of usable quality |
| **Failure to enrol (FTE)** | No usable template could be produced for a subject at all |
| **Latent** | A print lifted from a scene rather than captured live. **Out of Release 1.0 scope** — see D-30 |

---

## 2. What can be retained, what must be redesigned, what needs external software or hardware

### 2.1 RETAIN — genuinely useful, keep with modification

| # | Asset | Why it is worth keeping |
|---|---|---|
| R-1 | **The hardware bridge client protocol** (`SentinelBiometricHardware`, `index.html:4773-5350`) | It is a real, vendor-agnostic, documented contract: probes `localhost`/`127.0.0.1` on ports 8080/9001/11100, tries WebSocket `/biometrics` then HTTP `POST /scan`, accepts `{ok, template, format, quality, vendor, image}` or a plain signature string, with timeouts and health probing. **This is a sound design.** It needs a server-side counterpart and a real bridge implementation, not a rewrite. |
| R-2 | **The server-side identity-resolution engine** (`resolve_person()` `:5484`, `upsert_person()` `:5593`, `ensure_person()` `:5609`) | A real 4-tier matcher: Tier 1 exact national ID/passport, Tier 2 exact 4-part name + DOB, Tier 3 fuzzy 3-part name + mother's name (flagged "officer confirmation required"), Tier 4 scored partial name. It returns candidates and an `auto_merge` flag. **Biometric matching should become Tier 0 above this, not replace it.** |
| R-3 | **The clearance application workflow** — create, attach documents, signed-scan upload, approve, certificate number, printable `application.html` / `certificate.html` | Working, and the A4 print contract is the **one** feature in the system with an executed passing test (`backend/test_print_fit.py`) |
| R-4 | **The 12-hour review gate** (`review_gate_decision()` `:946` plus an independent inline guard `:9057`) | Genuine defence-in-depth, deliberately duplicated, and covered by `test_review_gate.py` (37 references — **not yet executed**). Keep the mechanism; fix the bypasses (§7). |
| R-5 | **The branch model and the fail-closed record check** `require_record_branch_scope()` `:2790` | Correct pattern — *"unknown must never mean everything"*. Extend it to the routes that lack it. |
| R-6 | **Enrolment-status vocabulary** (`captured` / `pending` / `none`) and the capture UI affordances | The officer-facing model is reasonable; only its storage location is wrong. |

### 2.2 REDESIGN — exists, but cannot be kept as built

| # | Asset | Required change |
|---|---|---|
| X-1 | `biometricStore` in `localStorage` (`index.html:2698`) | **Delete.** Replace with server-side enrolment storage. Browser-local biometric data is unauditable, unscoped, per-device and trivially editable by the officer. |
| X-2 | `matchPersonByFingerprint()` string matching (`index.html:4526`) | **Delete the biometric pretence.** Its *non-biometric* tiers (national ID, passport, name) duplicate the server engine (R-2) and should call it instead. |
| X-3 | The rotating-cursor "fallback match" (`index.html:4573`) | **Delete unconditionally.** No fallback may ever invent an identity. |
| X-4 | `total_biometrics_logged` / `identity_match_rate` metrics (`:6071`) | **Redefine** against real enrolment and matching data, and **scope them by branch** (currently the builder takes no `user`). |
| X-5 | Client-side hashing of the template into a `BIO-…` signature (`index.html:4780`) | The hash may remain as a **display label and deduplication aid**, but it must never be the matching key. Matching happens on templates, server-side. |
| X-6 | Clearance status model — only `Pending Review` and `Approved` are reachable | **Redesign** with the full lifecycle, including rejection (§6, D-19). |
| X-7 | `FP-` / `CL-` identifiers = last 8 digits of epoch ms | **Redesign** as year-scoped database sequences (collision and guessability). |

### 2.3 EXTERNAL — must be procured, licensed or built outside this repository

| # | Component | Note |
|---|---|---|
| E-1 | **Fingerprint scanner hardware** | Model, count and per-site allocation are **not decided** — raises **D-31**. The bridge design already names SecuGen in an example, but nothing is selected. |
| E-2 | **Vendor capture SDK / driver** | Required to produce images and quality scores on the capture workstation. Licensing cost and platform support are procurement questions. |
| E-3 | **The local bridge service itself** | The browser calls `http://127.0.0.1:<port>/scan` and `ws://localhost:<port>/biometrics`. **No code for this service exists in this repository.** It must be built or supplied, then installed on every capture workstation — which makes it a **deployment and endpoint-management problem**, not only a coding task. Raises **D-32**. |
| E-4 | **Matching engine (template extraction + comparison)** | Either a vendor SDK (server-side) or an open implementation (e.g. NIST NBIS/MINDTCT+BOZORTH3). A 1:N search against a growing gallery is a specialised component with real performance characteristics. **Do not assume it can be written inline.** Raises **D-33**. |
| E-5 | **Template format decision** | ISO/IEC 19794-2 or ANSI-378 (portable, vendor-neutral) versus a proprietary format (often more accurate with its own matcher, but locks the project in). Raises **D-33**. |
| E-6 | **Accuracy acceptance evidence** | A declared operating threshold needs measured FAR/FRR on a representative test set. Raises **D-34**. |

> **Consequence for planning:** of the six external items, **four (E-1…E-4) are on the critical path**
> and none is a code change inside this repository. The biometric half of this unit cannot be
> scheduled as ordinary application development.

---

## 3. Actors and permissions

| Actor | Role in code | Fingerprint capability (proposed) |
|---|---|---|
| **Fingerprint officer** | `FingerprintUnit` (`ROLE_MODULES` `:1871` → `{dashboard, people, fingerprint}`) | Register applicants · capture biometrics · run 1:1 verification · run 1:N identification · submit applications · attach documents |
| **Fingerprint supervisor** | **Does not exist** — must be created | Everything above, **plus** adjudicate candidate lists, approve, reject, override a failed capture, authorise an exception |
| **System administrator** | `SystemAdmin` | User and branch administration. **Must not** silently bypass the review gate (§7) |
| **Commander** | `chief_commander` | Read-only across all branches (`enforce_read_only()`), including biometric **metadata** but **not** template or image bytes (**FPR-703**) |
| Any other role | — | **No access.** The `fingerprint` module gate at `:8101` / `:8874` already enforces this |

**FPR-001 — Separation of duties.** The officer who submits a clearance application **must not** be
able to approve it. *Pending owner confirmation of **D-12**; the requirement is written for the
"separation required" answer and must be revisited if the owner decides otherwise.*

**FPR-002 — A Fingerprint supervisor role is created**, holding approval, rejection and override
authority. Capture and submission alone do not confer approval authority.

---

## 4. Workflow 1 — Applicant registration and identity resolution

**Actors:** Fingerprint officer · **Precondition:** officer authenticated, posting resolves to a branch

| ID | Requirement |
|---|---|
| FPR-101 | The officer enters applicant identity data: four name parts, date of birth, place of birth, mother's name, national ID and/or passport, phone, residence, occupation, photograph. |
| FPR-102 | On entry, the system calls the existing resolution engine (`/api/persons/resolve`) and presents the tier, reason and candidate list **before** a new person record is created. |
| FPR-103 | **Tier 1** (exact national ID/passport) and **Tier 2** (exact 4-part name + DOB) link automatically and enrich empty fields only — never overwriting stored values. *(Behaviour exists: `upsert_person()` `:5593`, `enrich_person()` `:5565`.)* |
| FPR-104 | **Tier 3** (fuzzy) and **Tier 4** (partial) **must require explicit officer confirmation** and record who confirmed, when, and which candidate was chosen. *(The engine already flags "officer confirmation required"; the confirmation is not currently recorded.)* |
| FPR-105 | Creating a person without a national ID **or** passport is refused unless an explicitly audited exception is recorded with a reason. *(`create_person()` `:5546` enforces the rule; `allow_no_id=True` currently bypasses it silently in the checkpoint path.)* |
| FPR-106 | **Once biometrics exist, biometric identification runs as Tier 0 — above all name/ID tiers** — because a template match is stronger evidence than a name match. |
| FPR-107 | Identity resolution must be **branch-scoped on write** and must record a cross-branch link attempt rather than silently widening. |
| **Audit** | `CREATE person` / `UPSERT person` / `ENRICH person`, each with tier, reason and the confirming officer |
| **Acceptance** | Two applicants sharing a name but differing in DOB resolve to **two** records · an applicant re-presenting with the same national ID resolves to **one** record and does not duplicate · a Tier 3 match cannot be accepted without a recorded confirmation |

---

## 5. Workflow 2 — Biometric capture, enrolment and matching

### 5.1 Image acquisition

| ID | Requirement |
|---|---|
| FPR-201 | Capture is performed by a local bridge service on the workstation, reached over `localhost` only, using the existing probe/scan contract (R-1). |
| FPR-202 | The bridge returns, per finger: the **image**, a **quality score**, the **sensor/vendor identity** and the **capture timestamp**. The score must come from the SDK, not be fabricated client-side. |
| FPR-203 | **Which fingers are captured is an owner decision — D-35.** Options: single thumb · two thumbs · four-finger slaps · full ten-print. This materially affects accuracy, capture time, hardware choice and storage. **The system must support whichever set is chosen, per finger position (ISO finger-position codes).** |
| FPR-204 | A capture below the configured quality floor is **rejected with a re-capture prompt**, never silently accepted. |
| FPR-205 | After a configurable number of failed attempts the officer may record a **Failure to Acquire (FTA)** with a reason (injury, worn ridges, amputation, non-cooperation) and proceed down the manual-review path (§6.3). |
| FPR-206 | Raw images are transmitted to the server over the authenticated API only. **They are never written to browser storage.** |

### 5.2 Template generation and enrolment

| ID | Requirement |
|---|---|
| FPR-211 | Templates are generated by the chosen matcher (E-4) in the chosen format (E-5), **server-side or on the bridge — D-33 decides which.** |
| FPR-212 | Enrolment stores, per person per finger position: template, format, format version, quality, capture timestamp, capturing officer, device identity, and the branch of capture. |
| FPR-213 | **Re-enrolment never overwrites.** A new capture creates a new version; previous versions are retained and marked superseded, so a past match decision can be reconstructed. |
| FPR-214 | Whether the **source image** is retained in addition to the template is **owner decision D-36** (it increases evidentiary value and re-processing ability, and increases risk and storage). |
| FPR-215 | Enrolment writes an audit event carrying person, finger positions, quality scores, device and officer — **never the template bytes**. |

### 5.3 Verification (1:1)

| ID | Requirement |
|---|---|
| FPR-221 | Given a claimed identity and a fresh probe, the system returns **match / no-match** plus the comparison score and the threshold applied. |
| FPR-222 | Used when an applicant presents a prior record or a certificate and claims to be that person. |
| FPR-223 | The result, score, threshold and decision are recorded against the application. |
| **Acceptance** | Verifying a person against their own enrolment succeeds; verifying against a different enrolment fails; both outcomes are audited with the score |

### 5.4 Identification (1:N)

| ID | Requirement |
|---|---|
| FPR-231 | Given a probe, the system searches the enrolled gallery and returns a **ranked candidate list** with scores — **not** a single asserted identity. |
| FPR-232 | **Above the auto-accept threshold:** a single candidate may be proposed as a match, still shown to the officer with its score. |
| FPR-233 | **Between the review and auto-accept thresholds:** the candidate list is presented for **mandatory human adjudication**. The system must not decide. |
| FPR-234 | **Below the review threshold:** the result is **"no match"**. The system **must never** return a nearest-neighbour as a match, and **must never** rotate through the registry (**FPR-902**). |
| FPR-235 | 1:N search must be **branch-scoped by default**, with cross-branch search as an explicit, audited, permissioned action — a national search is an investigative act, not a default. **Confirm with D-37.** |
| FPR-236 | Every search records: who searched, when, the probe reference, the candidate list returned, the thresholds in force, and the officer's decision. |
| FPR-237 | 1:N response time and gallery size assumptions must be stated and tested. Current code loads **all** persons into memory for name resolution (`SELECT * FROM persons`, `:5490`) — that pattern **must not** be extended to biometric search. Depends on **D-07** (expected scale). |
| **Acceptance** | A probe from an enrolled person returns that person as rank 1 · a probe from a non-enrolled person returns an empty or sub-threshold list and is reported as "no match" · no code path returns a candidate chosen by position, rotation or default |

### 5.5 Thresholds and human review

| ID | Requirement |
|---|---|
| FPR-241 | The system holds **two configurable thresholds**: `review_threshold` and `auto_accept_threshold`. |
| FPR-242 | Threshold values are **configuration, not code**, and every change is audited with who changed it, when, from what, to what, and why. |
| FPR-243 | The operating point must be justified by **measured FAR/FRR** on a representative set before go-live (**D-34**). An unjustified threshold is not acceptable for a police identification system. |
| FPR-244 | Every automated decision displays its score and the threshold applied. No silent matching. |
| FPR-245 | A supervisor may **override** any automated outcome, in either direction, with a mandatory reason. The override is the record of decision; the automated result is retained beside it. |

### 5.6 False matches and failed captures

| ID | Requirement |
|---|---|
| FPR-251 | An officer or supervisor can mark a proposed match as a **false match**, with a reason. |
| FPR-252 | A confirmed false match is **recorded against the match event** and is reportable (feeds report R-19, §9 of the report catalogue). It must not merely disappear from the screen. |
| FPR-253 | Repeated false matches against the same enrolment raise an enrolment-quality flag for supervisor attention. |
| FPR-254 | A **Failure to Acquire** or **Failure to Enrol** is a first-class recorded outcome with a reason code, not an absence of data. |
| FPR-255 | An applicant who cannot be enrolled biometrically must still be able to progress through a **documented manual-review exception path** (§6.3) — biometric failure must never become a denial of service to a citizen. |

---

## 6. Workflow 3 — Clearance decision and certificate

### 6.1 Status model *(replaces the current two reachable statuses)*

```
Draft ─► Submitted ─► Under Review ─┬─► Approved ─► Certificate Issued ─► [Expired]
                           │        │
                           │        ├─► Rejected (reason code)
                           │        └─► Returned for Correction ─► Submitted
                           └─► On Hold (awaiting biometric / document / external check)
```

| ID | Requirement |
|---|---|
| FPR-301 | **One** status vocabulary, enforced server-side by a transition table. Free-text status is refused. |
| FPR-302 | Every transition records actor, timestamp, prior status, new status and reason where required. |
| FPR-303 | **A rejection path exists** — currently there is none anywhere in the system. Requires reason codes and an applicant-notification rule (**D-19**). |
| FPR-304 | **Returned for Correction** allows resubmission without losing history. |
| FPR-305 | Certificate validity: `certificate.html` states six months, but **nothing records an expiry**. Expiry must be stored and reportable. |
| FPR-306 | The 12-hour review window is retained (R-4). Its **bypasses are restricted** — see §7. |
| FPR-307 | Approval requires: identity resolved, biometric enrolment present **or** an audited FTE exception, required documents attached, and the review window satisfied or an audited exception recorded. |

### 6.2 Certificate handling

| ID | Requirement |
|---|---|
| FPR-311 | Certificate numbers are issued from a **year-scoped sequence** with a uniqueness constraint (replacing the millisecond-suffix scheme). |
| FPR-312 | The A4 print contract is preserved and `backend/test_print_fit.py` must continue to pass — it is the project's only executed passing test. |
| FPR-313 | The signed-scan upload keeps its allow-list and 20 MB cap (`:9009`) and gains the **branch check it currently lacks**. |
| FPR-314 | Certificate retrieval requires authentication and branch scope (see security requirement SR-01). |
| FPR-315 | Third-party verification of a printed certificate is **decision D-10** and is **not** in Release 1.0 unless the owner says otherwise. |

### 6.3 Manual review and exception handling

| ID | Requirement |
|---|---|
| FPR-321 | Exceptions are explicit, typed and audited: `FTA` · `FTE` · `identity ambiguous` · `biometric unavailable (device/outage)` · `legal exemption`. |
| FPR-322 | Each exception records the authorising **supervisor**, the reason and any compensating check performed. |
| FPR-323 | An application approved under exception is **marked as such on the record** and is reportable. |
| FPR-324 | The `Citizenship` purpose currently skips the review window by a property the submitter supplies. Until **D-06** is answered this remains a **release blocker**; if the exemption is lawful it must become an **explicit, audited, supervisor-authorised exception** rather than an implicit consequence of a form field. |

---

## 7. Review-gate and approval integrity

| ID | Requirement |
|---|---|
| FPR-401 | The dual 12-hour gate (`review_gate_decision()` + the inline guard) is retained as defence-in-depth. |
| FPR-402 | `is_admin_user()` must **not** silently bypass the gate. If an administrative override is required it becomes a named, reasoned, audited override (FPR-245), not a role side effect. |
| FPR-403 | `citizenship_wait_exempt()` must **not** be a submitter-selectable bypass (FPR-324 / D-06). |
| FPR-404 | `/approve` and `/signed-document` must enforce **branch scope** — neither does today (`:8997`, `:9032`). |
| FPR-405 | Approval requires a role holding approval authority (FPR-002) and an approver different from the submitter (FPR-001, D-12). |
| FPR-406 | Every bypass or override is recorded as a **structured, queryable field**, not only inside an audit detail string as at `:9071`. |
| **Acceptance** | A branch-A officer cannot approve a branch-B application · a submitter cannot approve their own application · an administrator approving inside the window produces a distinct, queryable override record · `test_review_gate.py` is **executed** and passes |

---

## 8. Biometric data protection, retention and access

> Biometric data is the most sensitive category this system will hold. It is **irrevocable**: a
> compromised password can be changed, a compromised fingerprint cannot.

| ID | Requirement |
|---|---|
| FPR-701 | Templates and images are **encrypted at rest**, with a documented key-management and key-rotation procedure. |
| FPR-702 | Biometric data is **never** written to browser storage, never served from a static path, and never included in a general-purpose API response. |
| FPR-703 | **No role receives bulk export of templates or images** — including `SystemAdmin` and `chief_commander`. Administration of the system is not authority over its biometric contents. |
| FPR-704 | Every read of a template or image is **individually audited** (who, when, which subject, why). Biometric access is a logged event, not an incidental one. |
| FPR-705 | Access is branch-scoped by default; cross-branch biometric access is an explicit, permissioned, audited action (FPR-235 / D-37). |
| FPR-706 | **Retention periods are legally determined and are not set by this document — D-04.** The system must support a defined retention period with automated expiry and audited deletion. |
| FPR-707 | **Lawful basis, consent and subject rights are not resolved — D-05.** A DPIA covering biometric processing is required before go-live. |
| FPR-708 | Deletion of a biometric record is possible, audited, and leaves a tombstone proving what was deleted and by whose authority — without retaining the biometric itself. |
| FPR-709 | Backups containing biometric data inherit the same encryption, access and retention rules, and the restore procedure must be rehearsed (ties to M-12). |
| FPR-710 | Transport of biometric data requires TLS. Until **H-8** is closed, **no biometric data may be captured in any environment reachable beyond a single trusted host.** |

---

## 9. Device integration and fallback

| ID | Requirement |
|---|---|
| FPR-801 | The bridge is reachable on loopback only. The browser must never be instructed to call a non-local address for capture. |
| FPR-802 | The bridge contract (R-1) is **formalised and versioned**, with the server rejecting an unknown or unsupported bridge version. |
| FPR-803 | The bridge must identify the device (vendor, model, serial) so a capture can be attributed to hardware. |
| FPR-804 | Workstations must be able to install and update the bridge in a controlled way — this is an **endpoint-management requirement**, not only software (**D-32**). |
| FPR-805 | **Absence of a scanner degrades gracefully to the documented manual path (§6.3) — it never fabricates a result.** The current code already keeps every bridge failure non-blocking (`showNoScannerFallback`, `index.html:5773`); that behaviour is correct and is retained. |
| FPR-806 | Bridge health is visible to the officer before capture is attempted. |
| FPR-807 | Bridge failures are recorded with their error code (`BRIDGE_EMPTY`, `BRIDGE_FAILED`, `UNSUPPORTED`) so device reliability is reportable. |

---

## 10. Requirements that delete existing behaviour

| ID | Requirement | Reason |
|---|---|---|
| **FPR-901** | Remove `biometricStore` and all `localStorage` biometric persistence, including the nine hard-coded demo entries | Unauditable, per-device, officer-editable, and it makes demo data indistinguishable from real data |
| **FPR-902** | **Remove the rotating-cursor fallback match** (`index.html:4573-4578`) | It fabricates identifications and presents them as biometric matches. **This must be removed even if biometric matching is deferred.** |
| **FPR-903** | Remove string-based "biometric" matching; route non-biometric matching to the server engine (R-2) | Two divergent matchers, one of them fictional |
| **FPR-904** | Redefine `total_biometrics_logged` and `identity_match_rate` | They currently measure applications, not biometrics |
| **FPR-905** | If D-18 had been answered "clearance only", FPR-901 and FPR-902 would still apply | Misleading capability is a defect in its own right |

---

## 11. Acceptance criteria for the unit *(a UI is not completion)*

| # | Criterion | How it is proven |
|---|---|---|
| AC-1 | A person can be enrolled, and their enrolment is visible **after clearing browser storage and on a different workstation** | Server-side enrolment test |
| AC-2 | 1:1 verification returns match for self, no-match for another | Automated test with fixture templates |
| AC-3 | 1:N returns the enrolled person at rank 1 for their own probe | Automated test against a gallery |
| AC-4 | 1:N returns **no match** for a non-enrolled probe — never a nearest neighbour | Automated **negative** test |
| AC-5 | No code path returns a candidate by rotation, position or default | Code assertion test + removal of FPR-902 |
| AC-6 | Scores between thresholds always require human adjudication | Automated test |
| AC-7 | Threshold changes are audited | Automated test |
| AC-8 | FTA/FTE produce recorded outcomes and a usable manual path | Automated test |
| AC-9 | Branch-A officer cannot read, verify against, or search branch-B enrolments without an audited cross-branch action | Automated negative test |
| AC-10 | No endpoint returns template bytes to a general-purpose client | Automated test |
| AC-11 | Every template/image read is audited | Automated test |
| AC-12 | Submitter cannot approve own application; cross-branch approval refused | Automated negative tests |
| AC-13 | Rejection with reason code works, and the applicant-notification rule is implemented as decided | Automated test |
| AC-14 | Certificate numbers are unique under 100 concurrent approvals | Concurrency test |
| AC-15 | `test_print_fit.py` and `test_review_gate.py` **execute** and pass | CI run |
| AC-16 | Measured FAR/FRR at the configured operating point is documented and accepted | Accuracy report (D-34) |

---

## 12. New decisions raised by this document

| ID | Decision | Blocking? |
|---|---|---|
| **D-30** | Are **latent prints** (lifted from scenes, for Crime Unit use) in scope? This document assumes **no** for Release 1.0. | Scope — answer early |
| **D-31** | Scanner hardware: model, quantity, per-site allocation, procurement timeline and budget | **Blocks the biometric critical path** |
| **D-32** | Who builds, signs, distributes and updates the **local bridge service** on every capture workstation? | **Blocks capture** |
| **D-33** | Matching engine: vendor SDK or open implementation (e.g. NBIS); where extraction and matching run (bridge vs server) | **Blocks matching** |
| **D-34** | Required accuracy operating point, and who accepts the measured FAR/FRR evidence | **Blocks go-live** |
| **D-35** | Which fingers are captured — thumb / two thumbs / four-finger slaps / ten-print | **Blocks capture UI, storage and accuracy planning** |
| **D-36** | Are source **images** retained in addition to templates? | Blocks storage and retention design |
| **D-37** | Is 1:N search branch-scoped by default, with cross-branch as a permissioned audited action? | Blocks the authorization model |
| *(carried)* | **D-04** retention · **D-05** DPIA and lawful basis · **D-06** Citizenship exemption · **D-12** separation of duties · **D-19** rejection path · **D-07** scale · **D-10** certificate verification | Several are release blockers |

---

## 13. Honest summary for the owner

- The **clearance workflow** is largely built and can be completed with ordinary development work.
- The **biometric half approved under D-18 is new construction**, and four of its prerequisites
  (**hardware, SDK, bridge service, matching engine**) are **outside this repository** and outside
  this team's unilateral control.
- Three things should be removed regardless of any other decision: browser-stored biometrics, string
  "matching", and above all the **rotating-cursor fallback that invents identifications**.
- **No biometric capability in this document can be scheduled until D-31, D-32, D-33 and D-35 are
  answered.** The roadmap treats them as a procurement track running in parallel with software work.
