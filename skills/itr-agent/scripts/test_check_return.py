#!/usr/bin/env python3
"""Tests for check_return - the gate in front of the tax engine.

The point of most of these is that a *silent* failure is the dangerous one. A
mistyped key that gets ignored costs money; a mistyped key that errors costs a
minute.

    python3 test_check_return.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from check_return import validate  # noqa: E402


def base(**over):
    ret = {
        "meta": {"assessment_year": "2026-27", "age_band": "below_60",
                 "residential_status": "resident", "filing_date": "2026-07-20",
                 "due_date": "2026-07-31"},
        "salary": {"gross": 1_200_000},
        "other_sources": {"savings_interest": 8_000},
        "deductions": {"s80d": 25_000},
        "taxes_paid": {"tds": 90_000},
    }
    ret.update(over)
    return ret


def errs(ret):
    return validate(ret).errors


def warns(ret):
    return validate(ret).warnings


class TestSchemaIsClosed(unittest.TestCase):
    def test_clean_input_passes(self):
        self.assertEqual(errs(base()), [])

    def test_unknown_top_level_key_is_an_error(self):
        e = errs(base(salery={"gross": 1}))
        self.assertTrue(any("salery" in x for x in e))

    def test_typo_in_a_deduction_is_an_error_not_a_shrug(self):
        """The whole reason the whitelist is closed: 's80CC' must not vanish."""
        e = errs(base(deductions={"s80CC": 150_000}))
        self.assertTrue(any("s80CC" in x for x in e))

    def test_near_miss_gets_a_suggestion(self):
        e = errs(base(deductions={"s80cc": 150_000}))
        self.assertTrue(any("did you mean" in x for x in e), e)

    def test_negative_amounts_are_rejected(self):
        e = errs(base(salary={"gross": -100}))
        self.assertTrue(any("negative" in x for x in e))

    def test_boolean_is_not_an_amount(self):
        e = errs(base(salary={"gross": True}))
        self.assertTrue(any("boolean" in x for x in e))


class TestMeta(unittest.TestCase):
    def test_wrong_assessment_year_is_refused(self):
        r = base()
        r["meta"]["assessment_year"] = "2025-26"
        self.assertTrue(any("pinned to AY 2026-27" in x for x in errs(r)))

    def test_non_resident_is_refused(self):
        r = base()
        r["meta"]["residential_status"] = "nri"
        self.assertTrue(any("out of scope" in x for x in errs(r)))

    def test_bad_age_band_is_refused(self):
        r = base()
        r["meta"]["age_band"] = "60"
        self.assertTrue(errs(r))

    def test_late_filing_is_warned_not_blocked(self):
        r = base()
        r["meta"]["filing_date"] = "2026-09-10"
        self.assertEqual(errs(r), [])
        self.assertTrue(any("234A" in x for x in warns(r)))

    def test_non_standard_due_date_is_flagged(self):
        r = base()
        r["meta"]["due_date"] = "2026-09-15"
        self.assertTrue(any("standard AY 2026-27 deadline" in x for x in warns(r)))


class TestPrivacy(unittest.TestCase):
    def test_pan_in_the_file_is_an_error(self):
        r = base()
        r["meta"]["taxpayer_label"] = "ABCDE1234F"
        self.assertTrue(any("PAN" in x for x in errs(r)))

    def test_aadhaar_shape_is_warned(self):
        r = base()
        r["notes"] = "aadhaar 1234 5678 9012"
        self.assertTrue(any("Aadhaar" in x for x in warns(r)))


class TestCrossChecks(unittest.TestCase):
    def test_salary_mismatch_against_form16_blocks(self):
        r = base(source_totals={"form16_gross_salary": 1_250_000})
        self.assertTrue(any("form16_gross_salary" in x for x in errs(r)))

    def test_within_rounding_tolerance_passes(self):
        r = base(source_totals={"form16_gross_salary": 1_200_006})
        self.assertEqual(errs(r), [])

    def test_tds_mismatch_against_26as_blocks(self):
        r = base(source_totals={"form26as_tds": 105_000})
        self.assertTrue(any("form26as_tds" in x for x in errs(r)))

    def test_26as_above_form16_suggests_a_second_deductor(self):
        r = base(taxes_paid={"tds": 105_000},
                 source_totals={"form16_tds": 90_000, "form26as_tds": 105_000})
        self.assertEqual(errs(r), [])
        self.assertTrue(any("another\ndeductor" in x or "another deductor" in x
                            or "bank or another" in x for x in warns(r)))

    def test_missing_source_totals_warns_loudly(self):
        self.assertTrue(any("nothing was cross-checked" in x for x in warns(base())))


class TestHouseProperty(unittest.TestCase):
    def test_self_occupied_cannot_have_rent(self):
        r = base(house_property=[{"kind": "self_occupied", "annual_rent": 100_000}])
        self.assertTrue(any("cannot have rent" in x for x in errs(r)))

    def test_bad_kind_is_rejected(self):
        r = base(house_property=[{"kind": "rented_out"}])
        self.assertTrue(errs(r))

    def test_interest_over_the_cap_warns(self):
        r = base(house_property=[{"kind": "self_occupied", "interest_paid": 300_000}])
        self.assertTrue(any("2,00,000" in x for x in warns(r)))


class TestForeignAssets(unittest.TestCase):
    def _fa(self, **over):
        a = {"asset_type": "bank_account", "country": "Singapore",
             "opened_on": "2021-01-05", "peak_value": 500_000,
             "closing_value": 400_000}
        a.update(over)
        return base(foreign_assets=[a])

    def test_valid_entry_passes(self):
        self.assertEqual(errs(self._fa()), [])

    def test_missing_peak_value_blocks(self):
        r = self._fa()
        del r["foreign_assets"][0]["peak_value"]
        self.assertTrue(any("peak_value" in x for x in errs(r)))

    def test_closing_above_peak_is_impossible(self):
        r = self._fa(peak_value=100, closing_value=200)
        self.assertTrue(any("exceeds the peak" in x for x in errs(r)))

    def test_account_opened_after_the_window_is_flagged(self):
        r = self._fa(opened_on="2026-02-01")
        self.assertTrue(any("outside the Schedule FA" in x for x in warns(r)))

    def test_black_money_act_warning_always_fires(self):
        self.assertTrue(any("Black Money Act" in x for x in warns(self._fa())))

    def test_foreign_assets_rule_out_itr1_and_itr4(self):
        r = self._fa()
        r["meta"]["itr_form"] = "ITR-4"
        self.assertTrue(any("Schedule FA" in x for x in errs(r)))
        r["meta"]["itr_form"] = "ITR-3"
        self.assertEqual(errs(r), [])


class TestBusiness(unittest.TestCase):
    def test_business_income_cannot_go_on_itr1(self):
        r = base(business={"presumptive_44ada": {"gross_receipts_digital": 100_000}})
        r["meta"]["itr_form"] = "ITR-1"
        self.assertTrue(any("cannot be filed on ITR-1" in x for x in errs(r)))

    def test_missing_nature_of_business_code_warns(self):
        r = base(business={"presumptive_44ada": {"gross_receipts_digital": 100_000}})
        self.assertTrue(any("nature_of_business_code" in x for x in warns(r)))


class TestTaxPayments(unittest.TestCase):
    def test_advance_tax_outside_the_fy_is_an_error(self):
        r = base(taxes_paid={"tds": 0,
                             "advance_tax": [{"date": "2026-06-01", "amount": 50_000}]})
        self.assertTrue(any("outside FY 2025-26" in x for x in errs(r)))

    def test_payment_needs_both_date_and_amount(self):
        r = base(taxes_paid={"tds": 0, "advance_tax": [{"amount": 50_000}]})
        self.assertTrue(any("needs both" in x for x in errs(r)))


class TestPlausibility(unittest.TestCase):
    def test_zero_interest_is_questioned(self):
        r = base(other_sources={})
        self.assertTrue(any("interest income at all" in x for x in warns(r)))

    def test_no_80d_is_questioned(self):
        r = base(deductions={})
        self.assertTrue(any("80D" in x for x in warns(r)))

    def test_s112_gain_gets_the_indexation_cap_warning(self):
        r = base(capital_gains={"ltcg_112": 1_000_000})
        self.assertTrue(any("UNINDEXED" in x for x in warns(r)))


class TestShippedExample(unittest.TestCase):
    def test_example_return_validates(self):
        path = HERE.parent / "assets" / "example-return.json"
        rep = validate(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(rep.errors, [], "the shipped example must validate cleanly")


if __name__ == "__main__":
    unittest.main(verbosity=2)
