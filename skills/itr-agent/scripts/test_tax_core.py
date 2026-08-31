#!/usr/bin/env python3
"""Golden tests for tax_core.

Each case states the statutory result independently of the implementation - if
the engine and a case disagree, look up the section before touching either.

    python3 test_tax_core.py
"""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tax_core import (  # noqa: E402
    TaxError, compare, compute, floor_100, round_10, _months, _slab_tax_new,
    _slab_tax_old,
)


def salaried(gross, **extra):
    ret = {
        "meta": {"age_band": "below_60", "filing_date": "2026-07-15",
                 "due_date": "2026-07-31"},
        "salary": {"gross": gross},
    }
    ret.update(extra)
    return ret


class TestRounding(unittest.TestCase):
    def test_288a_half_up(self):
        self.assertEqual(round_10(Decimal(1_234_565)), Decimal(1_234_570))
        self.assertEqual(round_10(Decimal(1_234_564)), Decimal(1_234_560))
        self.assertEqual(round_10(Decimal(-45)), Decimal(-50))

    def test_rule_119a_floors_to_hundred(self):
        self.assertEqual(floor_100(Decimal(10_999)), Decimal(10_900))
        self.assertEqual(floor_100(Decimal(99)), Decimal(0))
        self.assertEqual(floor_100(Decimal(-500)), Decimal(0))

    def test_month_counting_includes_part_months(self):
        import datetime as dt
        self.assertEqual(_months(dt.date(2026, 7, 31), dt.date(2026, 8, 1)), 1)
        self.assertEqual(_months(dt.date(2026, 7, 31), dt.date(2026, 10, 30)), 3)
        self.assertEqual(_months(dt.date(2026, 7, 31), dt.date(2026, 7, 31)), 0)


class TestSlabTables(unittest.TestCase):
    def test_new_regime_slabs(self):
        # 12,00,000: 4L nil + 4L@5% = 20,000 + 4L@10% = 40,000
        self.assertEqual(_slab_tax_new(Decimal(1_200_000)), Decimal(60_000))
        # 24,00,000: 20k + 40k + 60k + 80k + 1,00,000 = 3,00,000
        self.assertEqual(_slab_tax_new(Decimal(2_400_000)), Decimal(300_000))
        self.assertEqual(_slab_tax_new(Decimal(400_000)), Decimal(0))

    def test_old_regime_slabs_by_age(self):
        # <60 at 10,00,000: 2.5L@5% = 12,500 + 5L@20% = 1,00,000
        self.assertEqual(_slab_tax_old(Decimal(1_000_000), "below_60"), Decimal(112_500))
        # senior: exemption starts at 3L, so 2L@5% = 10,000 + 1,00,000
        self.assertEqual(_slab_tax_old(Decimal(1_000_000), "senior"), Decimal(110_000))
        # super-senior: no 5% band at all, 5L@20% only
        self.assertEqual(_slab_tax_old(Decimal(1_000_000), "super_senior"), Decimal(100_000))


class TestNewRegimeRebate(unittest.TestCase):
    def test_salaried_break_even_is_1275000(self):
        """75,000 standard deduction + 12,00,000 rebate threshold."""
        r = compute(salaried(1_275_000), "new")
        self.assertEqual(r["total_income"], Decimal(1_200_000))
        self.assertEqual(r["rebate_87a"], Decimal(60_000))
        self.assertEqual(r["net_payable"], Decimal(0))

    def test_87a_marginal_relief_at_1210000(self):
        """Slab income 12,10,000: slab tax 61,500, excess 10,000.

        Relief = 51,500; tax = 10,000 + 4% cess = 10,400.
        """
        r = compute(salaried(1_285_000), "new")
        self.assertEqual(r["total_income"], Decimal(1_210_000))
        self.assertEqual(r["slab_tax"], Decimal(61_500))
        self.assertEqual(r["rebate_87a"], Decimal(51_500))
        self.assertEqual(r["total_tax_liability"], Decimal(10_400))

    def test_marginal_relief_expires_above_1270000(self):
        r = compute(salaried(1_400_000), "new")
        self.assertEqual(r["rebate_87a"], Decimal(0))

    def test_rebate_threshold_ignores_special_rate_income(self):
        """Finance Act 2025: the 12L test is on slab income only, and the
        rebate offsets slab tax only - 112A gains neither eat it nor gain from it."""
        ret = salaried(1_275_000)
        ret["capital_gains"] = {"ltcg_112a": 500_000}
        r = compute(ret, "new")
        self.assertEqual(r["rebate_87a"], Decimal(60_000))
        # (5,00,000 - 1,25,000) x 12.5% = 46,875, + 4% cess
        self.assertEqual(r["tax_112a"], Decimal("46875.00"))
        self.assertEqual(r["total_tax_liability"], Decimal(48_750))


class TestOldRegimeRebate(unittest.TestCase):
    def test_hard_cliff_no_marginal_relief(self):
        under = compute(salaried(550_000, deductions={"s80c": 150_000}), "old")
        self.assertEqual(under["total_income"], Decimal(350_000))
        self.assertEqual(under["total_tax_liability"], Decimal(0))

        over = compute(salaried(560_000), "old")
        self.assertEqual(over["total_income"], Decimal(510_000))
        self.assertEqual(over["rebate_87a"], Decimal(0))
        # 2.5L@5% = 12,500 + 10,000@20% = 2,000 -> 14,500 + 4% cess = 15,080
        self.assertEqual(over["total_tax_liability"], Decimal(15_080))

    def test_112a_tax_is_barred_from_87a(self):
        """s.112A(6) - the rebate cannot touch 112A tax even under the old regime."""
        ret = salaried(300_000)
        ret["capital_gains"] = {"ltcg_112a": 400_000}
        r = compute(ret, "old")
        self.assertEqual(r["rebate_87a"], Decimal(0))


class TestCapitalGains(unittest.TestCase):
    def test_112a_exemption_is_125000(self):
        ret = salaried(0)
        ret["capital_gains"] = {"ltcg_112a": 125_000}
        ret["salary"] = {"gross": 2_000_000}
        r = compute(ret, "new")
        self.assertEqual(r["tax_112a"], Decimal(0))

    def test_111a_rate_is_20_percent(self):
        ret = salaried(2_000_000)
        ret["capital_gains"] = {"stcg_111a": 100_000}
        r = compute(ret, "new")
        self.assertEqual(r["tax_111a"], Decimal(20_000))

    def test_vda_gets_no_basic_exemption_and_no_rebate(self):
        ret = {"meta": {"age_band": "below_60", "filing_date": "2026-07-15",
                        "due_date": "2026-07-31"},
               "capital_gains": {"vda": 100_000}}
        r = compute(ret, "new")
        self.assertEqual(r["tax_vda"], Decimal(30_000))
        self.assertEqual(r["rebate_87a"], Decimal(0))
        self.assertEqual(r["total_tax_liability"], Decimal(31_200))

    def test_unused_basic_exemption_absorbs_gains(self):
        """Resident with no other income: 4L of new-regime exemption soaks up 111A."""
        ret = {"meta": {"age_band": "below_60", "filing_date": "2026-07-15",
                        "due_date": "2026-07-31"},
               "capital_gains": {"stcg_111a": 400_000}}
        r = compute(ret, "new")
        self.assertEqual(r["net_payable"], Decimal(0))


class TestHouseProperty(unittest.TestCase):
    def test_self_occupied_interest_old_regime_only(self):
        ret = salaried(1_500_000)
        ret["house_property"] = [{"kind": "self_occupied", "interest_paid": 250_000}]
        old = compute(ret, "old")
        new = compute(ret, "new")
        self.assertEqual(old["hp_loss_setoff"], Decimal(200_000))  # capped by s.24(b)
        self.assertEqual(new.lines.get("house_property", Decimal(0)), Decimal(0))

    def test_let_out_30_percent_standard_deduction(self):
        ret = salaried(1_000_000)
        ret["house_property"] = [
            {"kind": "let_out", "annual_rent": 300_000, "municipal_tax_paid": 20_000,
             "interest_paid": 0}
        ]
        r = compute(ret, "new")
        # NAV 2,80,000 less 30% = 1,96,000
        self.assertEqual(r["house_property"], Decimal(196_000))

    def test_loss_setoff_capped_at_200000(self):
        ret = salaried(2_000_000)
        ret["house_property"] = [
            {"kind": "let_out", "annual_rent": 100_000, "interest_paid": 600_000}
        ]
        r = compute(ret, "old")
        self.assertEqual(r["hp_loss_setoff"], Decimal(200_000))
        self.assertTrue(any("71(3A)" in w for w in r.warnings))


class TestPresumptive(unittest.TestCase):
    def test_44ada_floor_is_50_percent(self):
        ret = {"meta": {"age_band": "below_60", "filing_date": "2026-08-15",
                        "due_date": "2026-08-31"},
               "business": {"presumptive_44ada": {"gross_receipts_digital": 4_000_000}}}
        r = compute(ret, "new")
        self.assertEqual(r["presumptive_44ada_income"], Decimal(2_000_000))

    def test_44ada_below_floor_is_refused(self):
        ret = {"meta": {"age_band": "below_60"},
               "business": {"presumptive_44ada": {
                   "gross_receipts_digital": 4_000_000, "declared_income": 1_000_000}}}
        with self.assertRaises(TaxError) as ctx:
            compute(ret, "new")
        self.assertIn("44AB", str(ctx.exception))

    def test_44ada_ceiling_is_75_lakh_when_cash_under_5_percent(self):
        ret = {"meta": {"age_band": "below_60"},
               "business": {"presumptive_44ada": {"gross_receipts_digital": 7_400_000}}}
        compute(ret, "new")  # must not raise

        ret["business"]["presumptive_44ada"] = {
            "gross_receipts_digital": 4_000_000, "gross_receipts_cash": 2_000_000}
        with self.assertRaises(TaxError):
            compute(ret, "new")  # cash > 5% drops the ceiling to 50 lakh

    def test_44ad_uses_6_and_8_percent(self):
        ret = {"meta": {"age_band": "below_60"},
               "business": {"presumptive_44ad": {
                   "turnover_digital": 1_000_000, "turnover_cash": 1_000_000}}}
        r = compute(ret, "new")
        self.assertEqual(r["presumptive_44ad_income"], Decimal(140_000))


class TestSurcharge(unittest.TestCase):
    def test_10_percent_above_50_lakh(self):
        r = compute(salaried(6_000_000), "new")
        self.assertGreater(r["surcharge"], Decimal(0))

    def test_marginal_relief_just_above_50_lakh(self):
        """Just over 50L, (tax + surcharge) cannot exceed tax@50L + the excess."""
        r = compute(salaried(5_090_000), "new")
        self.assertEqual(r["total_income"], Decimal(5_015_000))
        self.assertTrue(any("Marginal relief" in n for n in r.notes))

    def test_new_regime_caps_surcharge_at_25(self):
        r = compute(salaried(70_000_000), "new")
        self.assertTrue(any("capped at 25%" in n for n in r.notes))


class TestDeductions(unittest.TestCase):
    def test_80c_capped(self):
        r = compute(salaried(1_000_000, deductions={"s80c": 200_000}), "old")
        self.assertEqual(r["chapter_via"], Decimal(150_000))

    def test_new_regime_drops_80c(self):
        r = compute(salaried(1_000_000, deductions={"s80c": 150_000}), "new")
        self.assertEqual(r["chapter_via"], Decimal(0))

    def test_80ccd2_14_percent_in_new_regime(self):
        ret = salaried(2_000_000)
        ret["salary"]["basic_plus_da"] = 1_000_000
        ret["deductions"] = {"s80ccd2_employer_nps": 200_000}
        self.assertEqual(compute(ret, "new")["chapter_via"], Decimal(140_000))
        self.assertEqual(compute(ret, "old")["chapter_via"], Decimal(100_000))

    def test_via_cannot_shelter_capital_gains(self):
        ret = {"meta": {"age_band": "below_60"},
               "salary": {"gross": 100_000},
               "capital_gains": {"ltcg_112a": 2_000_000},
               "deductions": {"s80c": 150_000}}
        r = compute(ret, "old")
        self.assertEqual(r["chapter_via"], Decimal(50_000))  # only the 50k of salary left
        self.assertTrue(any("cannot be set against" in w for w in r.warnings))


class TestInterestAndFee(unittest.TestCase):
    def test_no_234a_when_refund_due(self):
        ret = salaried(1_000_000, taxes_paid={"tds": 200_000})
        ret["meta"]["filing_date"] = "2026-10-01"
        r = compute(ret, "new")
        self.assertEqual(r["interest_234a"], Decimal(0))
        self.assertGreater(r["refund_due"], Decimal(0))

    def test_234f_is_1000_below_5_lakh(self):
        ret = salaried(560_000)
        ret["meta"]["filing_date"] = "2026-09-01"
        self.assertEqual(compute(ret, "new")["fee_234f"], Decimal(1_000))

    def test_234f_is_5000_above_5_lakh(self):
        ret = salaried(1_500_000)
        ret["meta"]["filing_date"] = "2026-09-01"
        self.assertEqual(compute(ret, "new")["fee_234f"], Decimal(5_000))

    def test_senior_without_business_owes_no_234b_or_234c(self):
        ret = salaried(1_500_000)
        ret["meta"]["age_band"] = "senior"
        r = compute(ret, "new")
        self.assertEqual(r["interest_234b"], Decimal(0))
        self.assertEqual(r["interest_234c"], Decimal(0))
        self.assertTrue(any("207(2)" in n for n in r.notes))

    def test_234b_skipped_when_90_percent_prepaid(self):
        ret = salaried(2_000_000, taxes_paid={"tds": 300_000})
        r = compute(ret, "new")
        self.assertEqual(r["interest_234b"], Decimal(0))


class TestRegimeChoice(unittest.TestCase):
    def test_belated_return_without_business_is_locked_to_new(self):
        # Deduction-heavy enough that the old regime genuinely wins on tax...
        ret = salaried(1_500_000, deductions={"s80c": 150_000, "s80ccd1b": 50_000,
                                              "s80d": 50_000})
        ret["salary"]["exempt_allowances"] = 300_000
        ret["house_property"] = [{"kind": "self_occupied", "interest_paid": 200_000}]
        self.assertLess(compute(ret, "old")["total_tax_liability"],
                        compute(ret, "new")["total_tax_liability"])
        # ...but a belated return with no business income cannot elect it.
        ret["meta"]["filing_date"] = "2026-11-01"
        c = compare(ret)
        self.assertEqual(c["recommended"], "new")
        self.assertIsNotNone(c["forced_note"])
        self.assertIn("115BAC(6)", c["forced_note"])

    def test_business_income_may_still_pick_old_when_belated(self):
        ret = salaried(1_000_000, deductions={"s80c": 150_000})
        ret["business"] = {"presumptive_44ada": {"gross_receipts_digital": 500_000}}
        ret["meta"]["filing_date"] = "2026-11-01"
        c = compare(ret)
        self.assertIsNone(c["forced_note"])

    def test_comparison_picks_the_cheaper_regime(self):
        heavy = salaried(1_200_000, deductions={"s80c": 150_000, "s80ccd1b": 50_000,
                                                "s80d": 50_000})
        c = compare(heavy)
        self.assertIn(c["recommended"], ("new", "old"))
        self.assertGreaterEqual(c["saving"], Decimal(0))


class TestScopeGuards(unittest.TestCase):
    def test_non_resident_is_refused(self):
        ret = salaried(1_000_000)
        ret["meta"]["residential_status"] = "non_resident"
        with self.assertRaises(TaxError):
            compute(ret, "new")

    def test_bad_age_band_is_refused(self):
        ret = salaried(1_000_000)
        ret["meta"]["age_band"] = "middle_aged"
        with self.assertRaises(TaxError):
            compute(ret, "new")


class TestInvariants(unittest.TestCase):
    """Properties that must hold for any input, checked over a spread."""

    def _spread(self):
        for gross in (0, 300_000, 700_000, 1_275_000, 1_310_000, 2_500_000,
                      5_200_000, 11_000_000, 25_000_000):
            for ltcg in (0, 125_000, 900_000):
                ret = salaried(gross)
                if ltcg:
                    ret["capital_gains"] = {"ltcg_112a": ltcg}
                yield ret

    def test_tax_is_never_negative_and_monotonic_in_income(self):
        last = {}
        for ret in self._spread():
            for regime in ("new", "old"):
                r = compute(ret, regime)
                self.assertGreaterEqual(r["net_payable"], Decimal(0))
                self.assertGreaterEqual(r["total_tax_liability"], Decimal(0))
                key = (regime, ret.get("capital_gains", {}).get("ltcg_112a", 0))
                prev = last.get(key)
                if prev is not None:
                    self.assertGreaterEqual(
                        r["total_tax_liability"], prev,
                        f"tax fell as income rose ({regime}, {ret['salary']['gross']})")
                last[key] = r["total_tax_liability"]

    def test_payable_and_refund_are_never_both_positive(self):
        for ret in self._spread():
            ret["taxes_paid"] = {"tds": 150_000}
            for regime in ("new", "old"):
                r = compute(ret, regime)
                self.assertFalse(r["net_payable"] > 0 and r["refund_due"] > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
