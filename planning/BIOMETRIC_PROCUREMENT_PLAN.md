# Biometric Procurement Action Plan

**Status:** draft for owner decision · **Prepared:** 7 November 2026
**Owner of this document:** project owner / CID command
**Covers decisions:** D-31 (scanner hardware), D-32 (bridge service ownership),
D-33 (matching engine and template format), D-35 (which fingers are captured),
and the acceptance evidence for D-34 (FAR/FRR operating point)

---

## 0. Why this document exists, and what it is not

This is one of the two action plans the owner asked to be prepared **in
parallel with Stage 0**, because both have lead times measured in weeks or
months and neither is under engineering control. Starting them late is the
single largest schedule risk to the fingerprint unit.

**This plan does not authorise any purchase, any vendor contact, or any
implementation.** It sets out what must be decided, in what order, what each
decision blocks, and what evidence is needed to close it. Nothing in it should
be read as a recommendation to buy a named product.

**Hard precondition, restated:** per the standing instruction, no work on a
genuine biometric matcher may begin until D-31, D-32, D-33 and D-34 are
resolved. Stage 0 deliberately did the opposite of implementing matching — it
**removed** the code that fabricated matches (WP-45g). The system today
performs **no biometric matching of any kind**, and that is the correct and
intended state until these decisions are made.

---

## 1. Current factual position

| Question | Position today | Evidence |
|---|---|---|
| Are fingerprint templates stored? | **No.** Only a browser `localStorage` key `sentinelBiometrics`, seeded from 9 hard-coded demo entries. | `index.html` biometric store |
| Is there a server-side biometric column or table? | **No.** | 21-table schema sweep; `persons` has no biometric field |
| Is there a matcher? | **No.** Identifier string comparison only. | `matchPersonByFingerprint()` |
| Was there a fallback that invented matches? | **Yes — removed in Stage 0 (WP-45g).** It rotated a cursor through the person registry and returned an arbitrary citizen as a confirmed match. | Before/after evidence in the Stage 0 report |
| Does scanner bridge code exist? | **No.** A protocol is *specified* in the SPA (localhost 8080/9001/11100, `/health`, `/scan/info`, `POST /scan`, WS `/biometrics`) but **no bridge implementation exists in this repository**. | SPA bridge section |
| What does `total_biometrics_logged` count? | Clearance applications — **not** biometrics. | Analytics query |

Everything in sections 2–6 therefore starts from zero, not from an existing
deployment.

---

## 2. Decisions to close, in dependency order

### D-35 — which fingers are captured *(close first)*

Decide before hardware, because it determines platen size, capture time,
storage and the capture UI.

| Option | Implication |
|---|---|
| Single thumb | Cheapest, fastest, lowest accuracy; weakest for 1:N identification |
| Two thumbs | Modest cost increase, materially better than one |
| Four-finger slap | Larger platen, higher unit cost; standard for civil identity |
| Ten-print | Highest cost and capture time; required if records must interoperate with a national or INTERPOL ten-print system |

**Required to close:** a written statement of the operational purpose — civil
clearance only, or criminal identification, or both — and whether records must
ever be exchanged with an external authority.

**Blocks:** D-31, D-33, WP-45a storage design, capture UI.

### D-31 — scanner hardware

**Required to close:** model, quantity, per-site allocation, budget line,
procurement route and delivery timeline.

Checklist to answer before any purchase commitment:

- [ ] Certification required? (e.g. FBI PIV/Appendix F, or an equivalent the owner names)
- [ ] Operating environment — checkpoint dust, heat, direct sunlight, intermittent power
- [ ] Interface and drivers — USB; Linux/Windows support matching the actual workstation estate
- [ ] SDK licence terms: per-device, per-seat, perpetual or subscription; redistribution rights
- [ ] Does the SDK permit template extraction **without** a cloud service? (A cloud dependency is disqualifying for police data unless legal clears it — see the legal plan, §D-05)
- [ ] Spares, warranty, mean time to repair, in-country support
- [ ] Unit count: how many capture points, at which sites, with what redundancy

**Lead time:** typically 4–16 weeks including tender, import and delivery.
**This is the critical path for the whole fingerprint unit.**

### D-32 — bridge service ownership

The browser cannot talk to a USB scanner. A local service must run on every
capture workstation. **This is an endpoint-management obligation, not only a
coding task.**

**Required to close, in writing:**

- [ ] Who **builds** it (in-house, vendor, contractor)
- [ ] Who **code-signs** it, and with whose certificate
- [ ] How it is **distributed** to every workstation, and how it is **updated**
- [ ] Who holds the signing key and who may authorise a release
- [ ] How it authenticates to the application so that a hostile local process cannot impersonate a scanner
- [ ] Support model and escalation path when a scanner fails mid-shift

**Risk if left open:** an unsigned localhost service listening on a fixed port
on a police workstation is itself an attack surface. It must be designed, not
improvised.

### D-33 — matching engine and template format

**Required to close:**

- [ ] Vendor SDK, or an open implementation (e.g. NIST NBIS), or a hybrid
- [ ] Template standard: ISO/IEC 19794-2, ANSI/INCITS 378, or proprietary
- [ ] Where extraction runs: on the bridge (raw image never leaves the workstation) or on the server (raw image crosses the network)
- [ ] Whether **raw images** are retained in addition to templates — this is a legal question as much as a technical one and is cross-referenced to D-04 in the legal plan
- [ ] Licence cost model at the planned number of capture points and records
- [ ] Exit path: can templates be exported and re-matched by a different engine? (vendor lock-in)

**Strong engineering preference, for the owner to accept or reject:** a
**standard template format** and **extraction on the bridge**. Standard formats
preserve the ability to change vendor; extracting at the edge means raw
fingerprint images never traverse the network, which materially reduces both
the breach impact and the DPIA burden. This is a recommendation only.

### D-34 — accuracy operating point (FAR/FRR)

Not a procurement decision, but it cannot be evidenced without the hardware and
engine chosen above, so it is tracked here.

- [ ] Target false accept rate and false reject rate, stated numerically
- [ ] **Who accepts the measured evidence** — a named person, not a role
- [ ] The test corpus used to measure it, and its provenance (**must not be real police records** — see the standing instruction and the legal plan)
- [ ] What the system does at the boundary: is there a "possible match — manual review" band, or a hard accept/reject?

A police identification system must not run on an unjustified threshold. Until
D-34 is closed with measured evidence, no match result may be presented to an
officer as authoritative.

---

## 3. Sequencing and realistic timeline

```
Week 0        D-35 fingers decided (owner, ~1 day of decision time)
Week 0–2      D-33 engine/format evaluation; D-32 ownership agreed in writing
Week 1        D-31 specification finalised; tender or quotation issued
Week 2–12     Procurement, import, delivery            <-- CRITICAL PATH
Week 2–8      WP-45a template storage built (needs only D-33's format)
Week 8–14     WP-45b bridge service (needs D-32 + at least one physical unit)
Week 12–20    WP-45c matcher integration (needs hardware in hand)
Week 18–24    D-34 FAR/FRR measurement and formal acceptance
```

**Earliest realistic date for a trustworthy biometric match: ~5–6 months from
the day D-35 and D-31 are decided**, and that assumes procurement does not
slip. The engineering effort alone for WP-45a–f is 56–110 days; it cannot start
in earnest without these decisions.

---

## 4. What can proceed now, with no procurement

These are genuinely unblocked and do not depend on any purchase:

| Work | Why it is unblocked |
|---|---|
| **WP-45g — remove fabricated matching** | **Delivered in Stage 0.** |
| Security Wave 1 (SR-01, SR-02, SR-03, SR-15) | **Delivered in Stage 0.** |
| Template storage *schema design* (not deployment) | Needs only the D-33 format decision |
| Capture-UI wireframes | Needs only D-35 |
| Legal/DPIA work | See the parallel legal plan — start now |

---

## 5. Risks

| # | Risk | Consequence | Mitigation |
|---|---|---|---|
| P-1 | Procurement slips past 16 weeks | The whole fingerprint unit slips with it | Decide D-35 and issue the D-31 specification **first**; treat it as the critical path |
| P-2 | A proprietary template format is chosen | Permanent vendor lock-in; re-enrolment of every subject to change vendor | Prefer ISO/IEC 19794-2 or ANSI-378; make export a contractual requirement |
| P-3 | Nobody owns the bridge service | Unsigned, unmaintained code on every police workstation | Close D-32 **in writing** before WP-45b starts |
| P-4 | Hardware arrives before the legal basis exists | Capability with no lawful authority to use it | Run the legal plan in parallel, not after |
| P-5 | An SDK requires a cloud service | Police biometric data leaves the jurisdiction | Make "local extraction only" a procurement requirement unless legal clears otherwise |
| P-6 | Accuracy is accepted informally | No defensible basis for an identification in court | Name the D-34 acceptor **before** measurement begins |

---

## 6. What the owner needs to provide

1. **D-35** — which fingers, and the operational purpose behind that choice.
2. **D-31** — budget envelope, number of capture points, procurement route.
3. **D-32** — the named party that will build, sign, distribute and update the bridge.
4. **D-33** — vendor-SDK vs open implementation, and accept/reject the standard-format recommendation.
5. **D-34** — the named individual who will accept the accuracy evidence.

Until these exist in writing, the correct engineering position is the one the
system is in today: **no biometric matching, and no claim of one.**
