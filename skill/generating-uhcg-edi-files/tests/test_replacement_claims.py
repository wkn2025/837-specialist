"""Void-and-replace: a claim declared as the replacement of a prior claim.

UHCG carries the link in Loop 2300, not in CLM05-3 - the professional
companion guide pins the frequency code flat ("UHCG will pass a value of 1
here"), and both guides give REF*9F the job instead:

    UHCG_837P_Companion_Guide_FULL.csv, loop 2300
        REF01 = 9F  ... "UHCG will use this field to identify voided and
                         replacement claims"
        REF02       ... "Original UHAP Claim ID, When REF01 = 9F", AN 1-50
    UHCG_837I_Companion_Guide_FULL.csv, loop 2300
        REF01 = 9F  ... "9F=To identify voided and replacement claims"
        REF02       ... "Original UHAP Claim ID, When REF01 = 9F"
    UHCG_Special_Instructions_NTE_Guide.md
        "UHCG passes Special Instructions for 'Void and Replace Scenario' at
         the Claim level", NTE01 = ADD in Loop 2300, NTE02 <= 80 characters,
        example NTE*ADD*Rplcmnt fr Voided Clm 12345678~

The professional seed carries two real ones - blocks 7 and 8 - and they show
two things the guides also say. The REF run comes out in guide order
(9F, F8, 9A, then the NTE); and the CCN in REF*F8 is the ORIGINAL claim's,
not a new one - UHCG assigns a CCN once per claim ("11 digit # assigned to
claim by UHCG") and keeps it however many times the claim is reworked, so a
replacement inherits it from the run that issued the original.

This is the second override that changes a block's segment count, so it moves
SE01 and every positional index money_edits addresses, exactly as a line
splice does.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import generate as G
import masterfile as M
import overrides
import seeds
import validate
import x12_parse as X

from test_generate import fake_alloc, fake_alloc_p

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
I = seeds.get("I")
P = seeds.get("P")

# The seed's own replacement blocks (7 and 8) carry REF*9A / REF*9F / REF*F8
# / NTE*ADD. Both companion guides list loop 2300's REFs as 9F, F8, 9A
# (837P rows 591/596/602, 837I rows 693/701/709) and every EDI2 file in the
# repo emits F8 before 9A, so a generated replacement follows the guides -
# the seed's 9A-before-F8 is the outlier, not the rule.
NTE_PREFIX = "NTE*ADD*Rplcmnt fr Voided Clm "


def _build(doc, claims=1, profile=P):
    ov = None if doc is None else overrides.parse(doc, profile, claims)
    segs = seeds.load_seed(profile, REPO)
    alloc = fake_alloc(claims) if profile is I else fake_alloc_p(claims)
    return G.build(segs, profile, alloc, claims, ov)


def _seed_block(profile, i):
    return seeds.blocks(seeds.load_seed(profile, REPO))[i]


def _parse_error(case, doc, profile=P, claims=1):
    with case.assertRaises(overrides.OverrideError) as cm:
        overrides.parse(doc, profile, claims)
    return str(cm.exception)


class TestTheDocument(unittest.TestCase):
    def test_a_replaces_declaration_is_carried_on_the_claim(self):
        ov = overrides.parse({"claims": [{"n": 1, "replaces": "15641267"}]},
                             P, 1)
        self.assertEqual(ov.claim(1)["replaces"], "15641267")

    def test_a_claim_without_one_carries_none(self):
        ov = overrides.parse({"claims": [{"n": 1, "principalDiagnosis": "R42"}]},
                            P, 1)
        self.assertIsNone(ov.claim(1)["replaces"])

    def test_an_empty_replaced_id_is_refused(self):
        self.assertIn("replaces",
                      _parse_error(self, {"claims": [{"n": 1,
                                                      "replaces": "  "}]}))

    def test_a_non_string_replaced_id_is_refused(self):
        self.assertIn("replaces",
                      _parse_error(self, {"claims": [{"n": 1,
                                                      "replaces": 15641267}]}))

    def test_a_separator_in_the_replaced_id_is_refused(self):
        # REF02 is one element; a value carrying * or ~ would forge structure.
        self.assertIn("separator",
                      _parse_error(self, {"claims": [{"n": 1,
                                                      "replaces": "156*4126"}]}))

    def test_a_replaced_id_over_fifty_characters_is_refused(self):
        # REF02 is AN 1-50 in both companion guides.
        msg = _parse_error(self, {"claims": [{"n": 1, "replaces": "9" * 51}]})
        self.assertIn("1-50", msg)

    def test_fifty_characters_is_accepted(self):
        ov = overrides.parse({"claims": [{"n": 1, "replaces": "9" * 50}]}, P, 1)
        self.assertEqual(ov.claim(1)["replaces"], "9" * 50)


class TestTheSplice(unittest.TestCase):
    def test_the_ref_run_comes_out_in_guide_order(self):
        out = _build({"claims": [{"n": 1, "replaces": "15641267"}]})
        block = seeds.blocks(out)[0]
        i9f = next(j for j, s in enumerate(block) if s.startswith("REF*9F*"))
        self.assertEqual(block[i9f], "REF*9F*15641267")
        self.assertTrue(block[i9f + 1].startswith("REF*F8*"))
        self.assertTrue(block[i9f + 2].startswith("REF*9A*"))
        self.assertEqual(block[i9f + 3], NTE_PREFIX + "15641267")

    def test_the_seeds_own_9a_before_f8_order_is_not_kept(self):
        # The seed puts 9A first; the guides put F8 first. A replacement
        # follows the guides, so the pair comes out swapped.
        seed = _seed_block(P, 0)
        si9a = next(j for j, s in enumerate(seed) if s.startswith("REF*9A*"))
        self.assertTrue(seed[si9a + 1].startswith("REF*F8*"))
        block = seeds.blocks(
            _build({"claims": [{"n": 1, "replaces": "15641267"}]}))[0]
        i8 = next(j for j, s in enumerate(block) if s.startswith("REF*F8*"))
        i9a = next(j for j, s in enumerate(block) if s.startswith("REF*9A*"))
        self.assertLess(i8, i9a)

    def test_an_undeclared_claim_keeps_the_seeds_order(self):
        block = seeds.blocks(_build(None))[0]
        i9a = next(j for j, s in enumerate(block) if s.startswith("REF*9A*"))
        self.assertTrue(block[i9a + 1].startswith("REF*F8*"))

    def test_the_block_grows_by_exactly_two_segments(self):
        seed = _seed_block(P, 0)
        out = _build({"claims": [{"n": 1, "replaces": "15641267"}]})
        self.assertEqual(len(seeds.blocks(out)[0]), len(seed) + 2)

    def test_se01_counts_the_grown_block(self):
        out = _build({"claims": [{"n": 1, "replaces": "15641267"}]})
        block = seeds.blocks(out)[0]
        self.assertEqual(X.elems(block[-1])[1], str(len(block)))

    def test_an_undeclared_claim_is_untouched(self):
        out = _build({"claims": [{"n": 1, "replaces": "15641267"}]}, claims=2)
        second = seeds.blocks(out)[1]
        self.assertEqual([s for s in second if s.startswith("REF*9F")], [])
        self.assertEqual([s for s in second if s.startswith("NTE*ADD")], [])

    def test_it_works_on_the_institutional_seed_too(self):
        out = _build({"claims": [{"n": 1, "replaces": "E2E26081112125701"}]},
                     profile=I)
        block = seeds.blocks(out)[0]
        i9f = next(j for j, s in enumerate(block) if s.startswith("REF*9F*"))
        self.assertEqual(block[i9f], "REF*9F*E2E26081112125701")
        self.assertTrue(block[i9f + 1].startswith("REF*F8*"))
        self.assertTrue(block[i9f + 2].startswith("REF*9A*"))
        self.assertEqual(block[i9f + 3], NTE_PREFIX + "E2E26081112125701")

    def test_it_composes_with_a_line_splice(self):
        # Both overrides move SE01 and the positional money indices; a claim
        # declaring each must still reconcile.
        out = _build({"claims": [{"n": 1, "replaces": "15641267",
                                  "lines": [{"date": "20260130",
                                             "billed": "100.00",
                                             "savings": "10.00"},
                                            {"date": "20260130",
                                             "billed": "50.00",
                                             "savings": "5.00"}]}]})
        block = seeds.blocks(out)[0]
        self.assertIn("REF*9F*15641267", block)
        self.assertEqual(len([s for s in block if s.startswith("LX*")]), 2)
        clm = next(s for s in block if s.startswith("CLM*"))
        self.assertEqual(X.elems(clm)[2], "150.00")
        ok, detail = validate.MONEY_RULES[P.money_rule][0](seeds.blocks(out), P)
        self.assertTrue(ok, detail)


class TestTheRefusals(unittest.TestCase):
    def test_a_block_that_is_already_a_replacement_is_refused(self):
        # Professional seed blocks 7 and 8 carry their own REF*9F. Loop 2300
        # allows one, so a second declaration cannot be honoured.
        with self.assertRaises(G.BuildError) as cm:
            _build({"claims": [{"n": 7, "replaces": "15641267"}]}, claims=7)
        self.assertIn("9F", str(cm.exception))

    def test_replacing_a_claim_in_the_same_file_is_refused(self):
        # A file that replaces a claim it is itself allocating is incoherent.
        alloc = fake_alloc_p(1)
        with self.assertRaises(G.BuildError) as cm:
            G.build(seeds.load_seed(P, REPO), P, alloc, 1,
                    overrides.parse({"claims": [{"n": 1,
                                                 "replaces": alloc.ref_9a[0]}]},
                                    P, 1))
        self.assertIn("itself", str(cm.exception))


class TestTheValidator(unittest.TestCase):
    """Check 9 and check 10 must both see the declared block, not the seed."""

    def _expected(self, doc, claims=1, profile=P):
        man = {"overrides": doc}
        return validate.declared_blocks(
            profile, man, seeds.blocks(seeds.load_seed(profile, REPO)), claims)

    def test_the_declared_block_carries_the_two_segments(self):
        doc = {"claims": [{"n": 1, "replaces": "15641267"}]}
        block = self._expected(doc)[0]
        self.assertIn("REF*9F*15641267", block)
        self.assertIn(NTE_PREFIX + "15641267", block)

    def test_the_declared_block_length_matches_what_is_built(self):
        doc = {"claims": [{"n": 1, "replaces": "15641267"}]}
        built = seeds.blocks(_build(doc))[0]
        self.assertEqual(len(self._expected(doc)[0]), len(built))

    def test_an_undeclared_replacement_is_not_excused(self):
        # No declaration: the expected block is the untouched seed, so a file
        # carrying REF*9F would differ from it.
        block = self._expected({"claims": [{"n": 1}]})[0]
        self.assertEqual([s for s in block if s.startswith("REF*9F")], [])


class TestTheInheritedCcn(unittest.TestCase):
    """A replacement takes the CCN its original already carries.

    UHCG assigns the Claim Control Number once per claim (loop 2300 REF*F8,
    "11 digit # assigned to claim by UHCG") and does not reissue it on a
    rework, so the allocator's fresh value is overwritten before the file is
    built.
    """

    def _mf(self, runs):
        return {"version": 1, "runs": runs}

    def test_the_allocated_ccn_is_replaced_by_the_originals(self):
        mf = self._mf([{"type": "P", "output": "EDI1/Batch X/a.x12",
                        "ref_9a": ["15641267", "15641268"],
                        "ref_f8": ["99012156010", "99012156011"]}])
        alloc = fake_alloc_p(2)
        ov = overrides.parse({"claims": [{"n": 2, "replaces": "15641268"}]},
                             P, 2)
        before = list(alloc.ref_f8)
        got = G.inherit_replacement_ccns(mf, alloc, ov, 2)
        self.assertEqual(got, {2: "99012156011"})
        self.assertEqual(alloc.ref_f8[0], before[0])
        self.assertEqual(alloc.ref_f8[1], "99012156011")

    def test_the_built_file_carries_the_inherited_ccn(self):
        mf = self._mf([{"type": "P", "output": "EDI1/Batch X/a.x12",
                        "ref_9a": ["15641267"], "ref_f8": ["99012156010"]}])
        alloc = fake_alloc_p(1)
        ov = overrides.parse({"claims": [{"n": 1, "replaces": "15641267"}]},
                             P, 1)
        G.inherit_replacement_ccns(mf, alloc, ov, 1)
        block = seeds.blocks(G.build(seeds.load_seed(P, REPO), P, alloc, 1,
                                     ov))[0]
        self.assertIn("REF*F8*99012156010", block)
        self.assertIn("REF*9F*15641267", block)

    def test_an_undeclared_claim_keeps_its_allocated_ccn(self):
        mf = self._mf([{"type": "P", "output": "EDI1/Batch X/a.x12",
                        "ref_9a": ["15641267"], "ref_f8": ["99012156010"]}])
        alloc = fake_alloc_p(1)
        before = list(alloc.ref_f8)
        self.assertEqual(G.inherit_replacement_ccns(mf, alloc, None, 1), {})
        self.assertEqual(alloc.ref_f8, before)

    def test_an_original_no_run_issued_is_refused(self):
        mf = self._mf([{"type": "P", "output": "EDI1/Batch X/a.x12",
                        "ref_9a": ["15641267"], "ref_f8": ["99012156010"]}])
        ov = overrides.parse({"claims": [{"n": 1, "replaces": "15999999"}]},
                             P, 1)
        with self.assertRaises(G.BuildError) as ctx:
            G.inherit_replacement_ccns(mf, fake_alloc_p(1), ov, 1)
        self.assertIn("no recorded run ever issued", str(ctx.exception))

    def test_two_runs_disagreeing_on_the_ccn_are_refused(self):
        mf = self._mf([{"type": "P", "output": "a.x12",
                        "ref_9a": ["15641267"], "ref_f8": ["99012156010"]},
                       {"type": "P", "output": "b.x12",
                        "ref_9a": ["15641267"], "ref_f8": ["99012156099"]}])
        ov = overrides.parse({"claims": [{"n": 1, "replaces": "15641267"}]},
                             P, 1)
        with self.assertRaises(G.BuildError) as ctx:
            G.inherit_replacement_ccns(mf, fake_alloc_p(1), ov, 1)
        self.assertIn("different", str(ctx.exception))

    def test_the_bootstrap_run_is_not_a_source_of_ccns(self):
        # Its lists are an inventory of what was on disk, so index i of
        # ref_9a has nothing to do with index i of ref_f8.
        mf = self._mf([{"type": "imported", "ref_9a": ["15641267"],
                        "ref_f8": ["99012156010"]}])
        self.assertEqual(M.ccn_for_uhap(mf, "15641267"), [])

    def test_a_run_with_no_ccn_beside_the_uhap_is_refused(self):
        mf = self._mf([{"type": "P", "output": "a.x12",
                        "ref_9a": ["15641267", "15641268"],
                        "ref_f8": ["99012156010"]}])
        with self.assertRaises(M.MasterfileError):
            M.ccn_for_uhap(mf, "15641268")


if __name__ == "__main__":
    unittest.main()
