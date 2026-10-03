"""Identity matching engine — pure functions, no database access.

Ported from the legacy `resolve_person()` / `person_suggestions()` in backend/server.py and
modernised.  Everything here works on ALREADY-NORMALISED values (the database functions
`norm_text` / `norm_ident` are the single source of truth for normalisation; the registry
passes their output in), so this module is deterministic and unit-testable on its own.

Tiers (same meaning as legacy; thresholds are explicit and tunable here):

  Tier 1  exact National ID or Passport                     -> the person EXISTS  (auto link)
  Tier 2  same name (>=3 parts, same order) + same DoB      -> the person EXISTS  (auto link)
  Tier 3  fuzzy name (>=3 parts) + (same mother OR same DoB)-> POSSIBLE duplicate (officer confirms)
  Tier 4  partial name (>=2 parts, all found)               -> suggestion list only

What changed vs. legacy
  * Fuzzy: tokens match by edit-distance similarity (typos / transpositions), not only exactly.
  * Tier 2 is no longer limited to exactly four parts, and ignores token case/punctuation.
  * Tier 3 also fires on fuzzy-name + same DoB (the legacy needed the mother's name).
  * Conflicts are reported: an ID that points at person A while the name+DoB points at B, and
    an ID match whose stored name/DoB disagree with what was entered.
  * Candidate generation is bounded by the caller (GIN-indexed prefix keys), not a table scan.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

# ---- tunables -------------------------------------------------------------------------
TOKEN_MATCH_MIN = 0.80      # similarity at/above which two name tokens count as "the same"
MOTHER_MATCH_MIN = 0.90     # mother's name is compared as a whole string
SUGGEST_MIN_SCORE = 18      # legacy: score >= 18 appears in the suggestion list
STRONG_MIN_SCORE = 30       # legacy: score >= 30 is "strong"
ID_PREFIX_MIN = 2           # live typing: a National ID prefix of >= 2 chars scores a little
W_ID_EXACT, W_ID_PREFIX = 60, 25
W_TOKEN, W_ORDER, W_DOB, W_MOTHER = 10, 8, 12, 8

TIER_LABELS = {
    1: 'Tier 1 · Exact National ID / Passport match',
    2: 'Tier 2 · Same name and date of birth',
    3: 'Tier 3 · Possible duplicate — similar name with matching mother or date of birth',
    4: 'Tier 4 · Partial name match — select a record to link',
    0: 'No match',
}


# ---- string similarity ----------------------------------------------------------------
def edit_distance(a: str, b: str) -> int:
    """Damerau-Levenshtein (optimal string alignment): insert/delete/substitute/transpose."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if not la or not lb:
        return max(la, lb)
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[lb]


def similarity(a: str, b: str) -> float:
    """1.0 identical .. 0.0 unrelated.  Very short tokens must match exactly (no 'Ali'~'Ayo')."""
    if a == b:
        return 1.0
    longest = max(len(a), len(b))
    if longest == 0:
        return 1.0
    if min(len(a), len(b)) <= 3:
        return 0.0
    return max(0.0, 1.0 - edit_distance(a, b) / longest)


def match_tokens(query: Sequence[str], stored: Sequence[str],
                 threshold: float = TOKEN_MATCH_MIN) -> Tuple[int, float, bool]:
    """Greedy one-to-one assignment of query tokens to stored tokens.

    Returns (matched_count, summed_similarity, ordered) where `ordered` means the matched
    stored tokens appear in the same order as the query tokens (legacy "prefix, in order").
    """
    pairs = []
    for qi, q in enumerate(query):
        for si, s in enumerate(stored):
            sim = similarity(q, s)
            if sim >= threshold:
                pairs.append((sim, qi, si))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_q, used_s, chosen = set(), set(), []
    for sim, qi, si in pairs:
        if qi in used_q or si in used_s:
            continue
        used_q.add(qi)
        used_s.add(si)
        chosen.append((qi, si, sim))
    chosen.sort()
    ordered = all(chosen[i][1] < chosen[i + 1][1] for i in range(len(chosen) - 1))
    return len(chosen), sum(c[2] for c in chosen), ordered


# ---- query / candidate model ----------------------------------------------------------
@dataclass
class Query:
    """Normalised search input.  Empty/None means "not supplied"."""
    tokens: List[str] = field(default_factory=list)      # norm_text() tokens, entered order
    dob: Optional[date] = None
    national_id: Optional[str] = None                    # norm_ident()
    passport_id: Optional[str] = None                    # norm_ident()
    mother: Optional[str] = None                         # norm_text()

    @property
    def has_anything(self) -> bool:
        return bool(self.tokens or self.dob or self.national_id or self.passport_id or self.mother)


@dataclass
class Evaluation:
    person_id: int
    tier: int = 0
    score: int = 0
    id_exact: bool = False
    name_exact: bool = False        # identical token sequence
    name_matched: int = 0           # query tokens found (fuzzily) in the stored name
    name_all: bool = False          # every query token was found
    name_ordered: bool = False
    dob_match: bool = False
    mother_match: bool = False
    reasons: List[str] = field(default_factory=list)


def evaluate(q: Query, cand: Dict) -> Evaluation:
    """Score one stored person (a row dict with the normalised columns) against the query."""
    ev = Evaluation(person_id=cand['id'])
    stored_tokens = list(cand.get('name_tokens') or [])
    stored_nid = cand.get('nid_norm')
    stored_pid = cand.get('pid_norm')
    score = 0

    # -- identifiers (Tier 1) --
    for qv, sv in ((q.national_id, stored_nid), (q.passport_id, stored_pid)):
        if qv and sv:
            if qv == sv:
                ev.id_exact = True
                score += W_ID_EXACT
            elif len(qv) >= ID_PREFIX_MIN and sv.startswith(qv):
                score += W_ID_PREFIX

    # -- date of birth / mother --
    ev.dob_match = bool(q.dob and cand.get('date_of_birth') and q.dob == cand['date_of_birth'])
    if q.mother and cand.get('mother_norm'):
        ev.mother_match = (q.mother == cand['mother_norm']
                           or similarity(q.mother, cand['mother_norm']) >= MOTHER_MATCH_MIN)

    # -- name --
    if q.tokens and stored_tokens:
        matched, sim_sum, ordered = match_tokens(q.tokens, stored_tokens)
        ev.name_matched = matched
        ev.name_all = matched == len(q.tokens)
        ev.name_ordered = ordered
        ev.name_exact = list(q.tokens) == stored_tokens
        if len(q.tokens) >= 2 and ev.name_all:
            score += round(W_TOKEN * sim_sum)
            if ordered and matched == len(q.tokens):
                score += W_ORDER
            if ev.dob_match:
                score += W_DOB
            if ev.mother_match:
                score += W_MOTHER
    ev.score = score

    # -- tier --
    if ev.id_exact:
        ev.tier = 1
        ev.reasons.append('Exact National ID / Passport match')
    elif len(q.tokens) >= 3 and ev.name_exact and ev.dob_match:
        ev.tier = 2
        ev.reasons.append('Same name and date of birth')
    elif len(q.tokens) >= 3 and ev.name_matched >= 3 and (ev.mother_match or ev.dob_match):
        ev.tier = 3
        basis = "mother's name" if ev.mother_match else 'date of birth'
        if ev.mother_match and ev.dob_match:
            basis = "mother's name and date of birth"
        ev.reasons.append(f'Similar name ({ev.name_matched} of {len(q.tokens)} parts) and the same {basis}')
    elif len(q.tokens) >= 2 and ev.name_all and ev.score >= SUGGEST_MIN_SCORE:
        ev.tier = 4
        ev.reasons.append(f'Partial name match ({ev.name_matched}-part)')
    elif ev.score >= SUGGEST_MIN_SCORE:
        ev.tier = 4
        ev.reasons.append('Partial identifier match')
    return ev


# ---- decision across candidates -------------------------------------------------------
@dataclass
class Decision:
    status: str                                  # exists | confirm | suggestions | new
    tier: int
    primary: Optional[Evaluation]
    ranked: List[Evaluation]
    reason: str
    conflicts: List[Dict] = field(default_factory=list)

    @property
    def exists(self) -> bool:
        return self.status == 'exists'


def decide(q: Query, candidates: Sequence[Dict]) -> Decision:
    evals = [evaluate(q, c) for c in candidates]
    ranked = sorted((e for e in evals if e.tier > 0),
                    key=lambda e: (e.tier, -e.score, e.person_id))
    if not ranked:
        return Decision('new', 0, None, [], 'No existing record found — a new person record will be created.')

    conflicts: List[Dict] = []
    tier1 = [e for e in ranked if e.tier == 1]
    tier2 = [e for e in ranked if e.tier == 2]

    if tier1:
        primary = tier1[0]
        if len({e.person_id for e in tier1}) > 1:
            conflicts.append({'code': 'id_conflict', 'person_ids': [e.person_id for e in tier1],
                              'message': 'The National ID and the Passport belong to DIFFERENT existing people.'})
        other = [e for e in tier2 if e.person_id != primary.person_id]
        if other:
            conflicts.append({'code': 'name_dob_other_person', 'person_ids': [e.person_id for e in other],
                              'message': 'Another record has the same name and date of birth as the one entered.'})
        return Decision('exists', 1, primary, ranked, primary.reasons[0], conflicts)

    if tier2:
        primary = tier2[0]
        if len({e.person_id for e in tier2}) > 1:
            conflicts.append({'code': 'duplicate_records', 'person_ids': [e.person_id for e in tier2],
                              'message': 'Several records share this name and date of birth.'})
            return Decision('confirm', 2, primary, ranked,
                            'Several existing records have this name and date of birth — confirm which one.', conflicts)
        return Decision('exists', 2, primary, ranked, primary.reasons[0], conflicts)

    best = ranked[0]
    if best.tier == 3:
        n = len([e for e in ranked if e.tier == 3])
        return Decision('confirm', 3, best, ranked,
                        f'{best.reasons[0]} — {n} possible match(es); officer confirmation required.', conflicts)
    strong = [e for e in ranked if e.score >= STRONG_MIN_SCORE]
    return Decision('suggestions', 4, strong[0] if len(strong) == 1 else None, ranked,
                    'Possible matches found — select a record from the list to link.', conflicts)


def core_differences(q_raw: Dict[str, str], person: Dict, fields: Sequence[str]) -> List[Dict]:
    """Which locked fields the officer typed differently from the stored record.

    `q_raw` and `person` hold display values; comparison is whitespace/case-insensitive so
    only genuine disagreements are reported.
    """
    def key(v):
        return ' '.join(str(v).split()).casefold() if v not in (None, '') else ''
    out = []
    for f in fields:
        entered, stored = q_raw.get(f), person.get(f)
        if hasattr(stored, 'isoformat'):
            stored = stored.isoformat()
        if key(entered) and key(stored) and key(entered) != key(stored):
            out.append({'field': f, 'stored': stored, 'entered': entered})
    return out
