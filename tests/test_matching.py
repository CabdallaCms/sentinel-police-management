"""Pure unit tests for the matching engine (no database)."""
import unittest
from datetime import date

from app.identity import matching as m


def cand(id, name, dob=None, mother=None, nid=None, pid=None):
    return {'id': id, 'name_tokens': name.lower().split(), 'date_of_birth': dob, 'mother_norm': mother,
            'nid_norm': nid, 'pid_norm': pid}


class TestSimilarity(unittest.TestCase):
    def test_typos_and_transpositions_match_but_strangers_do_not(self):
        self.assertGreaterEqual(m.similarity('cabdi', 'cabdii'), m.TOKEN_MATCH_MIN)    # doubled letter
        self.assertGreaterEqual(m.similarity('axmed', 'ahmed'), m.TOKEN_MATCH_MIN)     # substitution
        self.assertGreaterEqual(m.similarity('xasan', 'xsaan'), m.TOKEN_MATCH_MIN - 0.01)  # transposition
        self.assertLess(m.similarity('cabdi', 'warsame'), 0.5)
        self.assertEqual(m.similarity('ali', 'ali'), 1.0)
        self.assertEqual(m.similarity('ali', 'ayo'), 0.0)         # very short tokens must be exact

    def test_assignment_is_one_to_one(self):
        # one stored 'cabdi' cannot satisfy two query tokens
        matched, _, _ = m.match_tokens(['cabdi', 'cabdi'], ['cabdi', 'xasan'])
        self.assertEqual(matched, 1)


class TestTiers(unittest.TestCase):
    D = date(1990, 5, 17)
    STORED = cand(1, 'ayaan cabdi xasan axmed', D, 'hodan', 'SO1001', None)

    def q(self, name='', dob=None, nid=None, pid=None, mother=None):
        return m.Query(tokens=name.lower().split(), dob=dob, national_id=nid, passport_id=pid, mother=mother)

    def test_tier1_exact_id(self):
        d = m.decide(self.q('someone else entirely', nid='SO1001'), [self.STORED])
        self.assertEqual((d.status, d.tier, d.exists), ('exists', 1, True))

    def test_tier2_same_name_and_dob(self):
        d = m.decide(self.q('Ayaan Cabdi Xasan Axmed'.lower(), dob=self.D), [self.STORED])
        self.assertEqual((d.status, d.tier), ('exists', 2))

    def test_tier2_needs_the_dob(self):
        d = m.decide(self.q('ayaan cabdi xasan axmed'), [self.STORED])
        self.assertNotEqual(d.status, 'exists')

    def test_tier3_typo_name_with_same_mother(self):
        d = m.decide(self.q('ayaan cabdii xasan ahmed', mother='hodan'), [self.STORED])
        self.assertEqual((d.status, d.tier), ('confirm', 3))
        self.assertFalse(d.exists)        # a warning, never an automatic link

    def test_tier3_typo_name_with_same_dob_and_no_mother(self):
        d = m.decide(self.q('ayaan cabdii xasan ahmed', dob=self.D), [self.STORED])
        self.assertEqual((d.status, d.tier), ('confirm', 3))

    def test_similar_name_alone_is_only_a_suggestion(self):
        d = m.decide(self.q('ayaan cabdi xasan'), [self.STORED])
        self.assertEqual((d.status, d.tier), ('suggestions', 4))

    def test_different_mother_and_dob_blocks_tier3(self):
        d = m.decide(self.q('ayaan cabdii xasan ahmed', dob=date(2001, 1, 1), mother='faadumo'), [self.STORED])
        self.assertEqual(d.status, 'suggestions')

    def test_unrelated_is_new(self):
        d = m.decide(self.q('zeynab warsame', dob=self.D), [self.STORED])
        self.assertEqual((d.status, d.tier), ('new', 0))

    def test_id_pointing_at_one_person_and_name_dob_at_another_is_a_conflict(self):
        other = cand(2, 'nuur faarax cali yuusuf', date(1985, 1, 1), None, 'SO2002')
        d = m.decide(self.q('nuur faarax cali yuusuf', dob=date(1985, 1, 1), nid='SO1001'), [self.STORED, other])
        self.assertEqual((d.status, d.primary.person_id), ('exists', 1))
        self.assertEqual([c['code'] for c in d.conflicts], ['name_dob_other_person'])

    def test_two_records_sharing_name_and_dob_require_confirmation(self):
        twin = cand(3, 'ayaan cabdi xasan axmed', self.D)
        d = m.decide(self.q('ayaan cabdi xasan axmed', dob=self.D), [self.STORED, twin])
        self.assertEqual(d.status, 'confirm')
        self.assertEqual(d.conflicts[0]['code'], 'duplicate_records')

    def test_id_prefix_is_a_suggestion_not_a_match(self):
        d = m.decide(self.q(nid='SO10'), [self.STORED])
        self.assertEqual((d.status, d.tier), ('suggestions', 4))


if __name__ == '__main__':
    unittest.main()
