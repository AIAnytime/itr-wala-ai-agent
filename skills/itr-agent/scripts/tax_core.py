#!/usr/bin/env python3
"""tax_core - deterministic Indian income-tax computation for FY 2025-26 (AY 2026-27).

Resident individuals. Both regimes. No network, no dependencies, no LLM.

The agent that drives the e-filing portal never does arithmetic; it calls this
module and quotes the result. Every rate encoded here is cited in
references/rates-ay2026-27.md.

Usage:
    python3 tax_core.py return.json              # human-readable comparison
    python3 tax_core.py return.json --json       # machine-readable
    python3 tax_core.py return.json --regime new
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

AY = "2026-27"
FY_START = _dt.date(2025, 4, 1)
FY_END = _dt.date(2026, 3, 31)
DEFAULT_DUE_DATE = _dt.date(2026, 7, 31)

# --------------------------------------------------------------------------
# money
# --------------------------------------------------------------------------
# Every figure is a Decimal of whole rupees. Paise never enter the return, and
# float arithmetic on 7-figure sums is how you end up 1 rupee off the portal.

Money = Decimal
ZERO = Decimal(0)


def rupees(x: Any) -> Money:
    """Coerce anything the schema allows into a whole-rupee Decimal."""
    if x is None or x == "":
        return ZERO
    if isinstance(x, Decimal):
        d = x
    elif isinstance(x, bool):
        raise TypeError("booleans are not amounts")
    else:
        d = Decimal(str(x))
    return d.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def round_10(x: Money) -> Money:
    """s.288A / s.288B - round to the nearest multiple of ten, half up."""
    return (x / 10).quantize(Decimal(1), rounding=ROUND_HALF_UP) * 10


def floor_100(x: Money) -> Money:
    """Rule 119A - the base for 234A/B/C interest drops to a multiple of 100."""
    if x <= 0:
        return ZERO
    return (x // 100) * 100


def pct(base: Money, rate: str) -> Money:
    return (base * Decimal(rate) / 100).quantize(Decimal("0.01"))


# --------------------------------------------------------------------------
# rate card - FY 2025-26
# --------------------------------------------------------------------------

# (upper bound or None for open-ended, rate %)
SLABS_NEW = [
    (Decimal(400_000), "0"),
    (Decimal(800_000), "5"),
    (Decimal(1_200_000), "10"),
    (Decimal(1_600_000), "15"),
    (Decimal(2_000_000), "20"),
    (Decimal(2_400_000), "25"),
    (None, "30"),
]

BASIC_EXEMPTION_OLD = {
    "below_60": Decimal(250_000),
    "senior": Decimal(300_000),
    "super_senior": Decimal(500_000),
}

STD_DEDUCTION = {"new": Decimal(75_000), "old": Decimal(50_000)}
PROF_TAX_CAP = Decimal(5_000)

# s.87A
REBATE_NEW_CAP = Decimal(60_000)
REBATE_NEW_THRESHOLD = Decimal(1_200_000)
REBATE_OLD_CAP = Decimal(12_500)
REBATE_OLD_THRESHOLD = Decimal(500_000)

CESS_RATE = "4"

# Chapter VI-A ceilings
CAP_80C = Decimal(150_000)
CAP_80CCD1B = Decimal(50_000)
CAP_80TTA = Decimal(10_000)
CAP_80TTB = Decimal(50_000)
CAP_24B_SELF_OCCUPIED = Decimal(200_000)
CAP_HP_LOSS_SETOFF = Decimal(200_000)  # s.71(3A)
CAP_FAMILY_PENSION = {"new": Decimal(25_000), "old": Decimal(15_000)}

# special rates
RATE_111A = "20"          # STCG on STT-paid equity, post 23-Jul-2024
RATE_112A = "12.5"        # LTCG on the same, above the exemption
EXEMPT_112A = Decimal(125_000)
RATE_112 = "12.5"         # other LTCG, no indexation
RATE_VDA = "30"           # s.115BBH
RATE_WINNINGS = "30"      # s.115BB / s.115BBJ

# presumptive
RATE_44AD_DIGITAL = Decimal("0.06")
RATE_44AD_CASH = Decimal("0.08")
RATE_44ADA = Decimal("0.50")

# surcharge: (threshold, rate, tested-on-exclusive-figure?)
SURCHARGE_TIERS = [
    (Decimal(5_000_000), "10", False),
    (Decimal(10_000_000), "15", False),
    (Decimal(20_000_000), "25", True),
    (Decimal(50_000_000), "37", True),
]
SURCHARGE_CAP_NEW = Decimal(25)      # new regime never exceeds 25%
SURCHARGE_CAP_SPECIAL = Decimal(15)  # ceiling on tax from dividends + 111A/112/112A

# advance tax installments: (due date, cumulative %, safe-harbour %)
INSTALMENTS = [
    (_dt.date(2025, 6, 15), Decimal("0.15"), Decimal("0.12")),
    (_dt.date(2025, 9, 15), Decimal("0.45"), Decimal("0.36")),
    (_dt.date(2025, 12, 15), Decimal("0.75"), None),
    (_dt.date(2026, 3, 15), Decimal("1.00"), None),
]


class TaxError(Exception):
    """Input the engine refuses to compute on."""


# --------------------------------------------------------------------------
# parsed return
# --------------------------------------------------------------------------


@dataclass
class Payment:
    date: _dt.date
    amount: Money


@dataclass
class Buckets:
    """Income split by how it is taxed, not by which head it came from.

    `slab` is everything that faces the slab table. The rest each carry their
    own statutory rate and are kept apart all the way to the tax stage, because
    Chapter VI-A cannot touch them and 87A treats them differently per regime.
    """

    slab: Money = ZERO
    stcg_111a: Money = ZERO
    ltcg_112a: Money = ZERO
    ltcg_112: Money = ZERO
    vda: Money = ZERO
    winnings: Money = ZERO

    def total(self) -> Money:
        return (
            self.slab + self.stcg_111a + self.ltcg_112a
            + self.ltcg_112 + self.vda + self.winnings
        )

    def special_total(self) -> Money:
        return self.total() - self.slab


@dataclass
class Result:
    regime: str
    lines: dict[str, Money] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __getitem__(self, k: str) -> Money:
        return self.lines[k]


# --------------------------------------------------------------------------
# head-wise income
# --------------------------------------------------------------------------


def _salary(ret: dict, regime: str, out: Result) -> Money:
    s = ret.get("salary") or {}
    gross = rupees(s.get("gross"))
    if gross == 0:
        return ZERO

    # Retirement exemptions - 10(10), 10(10A), 10(10AA), 10(10B), 10(10C) -
    # survive s.115BAC. HRA/LTA and most 10(14) allowances do not.
    exempt = rupees(s.get("exempt_retirement"))
    hra_lta = rupees(s.get("exempt_allowances"))
    if regime == "old":
        exempt += hra_lta
    elif hra_lta > 0:
        out.warnings.append(
            f"New regime: HRA/LTA exemption of {hra_lta:,} dropped (s.115BAC withdraws 10(5)/10(13A))."
        )

    net = gross - exempt
    std = min(STD_DEDUCTION[regime], max(net, ZERO))
    net -= std
    out.lines["salary_standard_deduction"] = std

    if regime == "old":
        pt = min(rupees(s.get("professional_tax")), PROF_TAX_CAP)
        net -= pt
        out.lines["professional_tax"] = pt
    elif rupees(s.get("professional_tax")) > 0:
        out.warnings.append("New regime: professional tax is not deductible; ignored.")

    return max(net, ZERO)


def _house_property(ret: dict, regime: str, out: Result) -> Money:
    total = ZERO
    for i, hp in enumerate(ret.get("house_property") or []):
        kind = hp.get("kind", "self_occupied")
        interest = rupees(hp.get("interest_paid"))

        if kind == "self_occupied":
            if regime == "new":
                if interest > 0:
                    out.warnings.append(
                        f"New regime: s.24(b) interest of {interest:,} on the self-occupied "
                        f"property is not deductible."
                    )
                continue
            allowed = min(interest, CAP_24B_SELF_OCCUPIED)
            if interest > CAP_24B_SELF_OCCUPIED:
                out.warnings.append(
                    f"s.24(b) capped at {CAP_24B_SELF_OCCUPIED:,} for the self-occupied property."
                )
            out.warnings.append(
                "The 2,00,000 self-occupied cap assumes a post-1-Apr-1999 purchase/construction "
                "loan completed within 5 years. Repair/renovation loans are capped at 30,000 - "
                "confirm the loan purpose."
            )
            total += -allowed
            continue

        # let out / deemed let out
        rent = rupees(hp.get("annual_rent"))
        municipal = rupees(hp.get("municipal_tax_paid"))
        nav = max(rent - municipal, ZERO)
        std30 = (nav * Decimal("0.30")).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        total += nav - std30 - interest
        out.lines[f"hp{i}_nav"] = nav

    return total


def _business(ret: dict, out: Result) -> Money:
    """Presumptive income under s.44AD / s.44ADA, plus any regular-books profit.

    The engine will not manufacture a presumptive figure below the statutory
    minimum: declaring less is legal but drags in books of account and a s.44AB
    audit, which is out of scope here.
    """
    b = ret.get("business") or {}
    total = ZERO

    ada = b.get("presumptive_44ada")
    if ada:
        digital = rupees(ada.get("gross_receipts_digital"))
        cash = rupees(ada.get("gross_receipts_cash"))
        receipts = digital + cash
        cap = Decimal(7_500_000) if cash <= receipts * Decimal("0.05") else Decimal(5_000_000)
        if receipts > cap:
            raise TaxError(
                f"s.44ADA gross receipts {receipts:,} exceed the {cap:,} ceiling. "
                "Presumptive taxation does not apply - this needs regular books and a CA."
            )
        floor = (receipts * RATE_44ADA).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        declared = rupees(ada.get("declared_income")) or floor
        if declared < floor:
            raise TaxError(
                f"s.44ADA declared income {declared:,} is below 50% of receipts ({floor:,}). "
                "That triggers books of account and a s.44AB audit - out of scope."
            )
        out.lines["presumptive_44ada_receipts"] = receipts
        out.lines["presumptive_44ada_income"] = declared
        total += declared

    ad = b.get("presumptive_44ad")
    if ad:
        digital = rupees(ad.get("turnover_digital"))
        cash = rupees(ad.get("turnover_cash"))
        turnover = digital + cash
        cap = Decimal(30_000_000) if cash <= turnover * Decimal("0.05") else Decimal(20_000_000)
        if turnover > cap:
            raise TaxError(
                f"s.44AD turnover {turnover:,} exceeds the {cap:,} ceiling."
            )
        floor = (
            digital * RATE_44AD_DIGITAL + cash * RATE_44AD_CASH
        ).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        declared = rupees(ad.get("declared_income")) or floor
        if declared < floor:
            raise TaxError(
                f"s.44AD declared income {declared:,} is below the presumptive minimum "
                f"({floor:,} = 6% digital + 8% cash)."
            )
        out.lines["presumptive_44ad_turnover"] = turnover
        out.lines["presumptive_44ad_income"] = declared
        total += declared

    regular = rupees(b.get("regular_books_profit"))
    if regular:
        out.lines["business_regular_profit"] = regular
        total += regular

    return total


def _other_sources(ret: dict, regime: str, out: Result) -> tuple[Money, Money]:
    """Returns (slab-rate other income, winnings taxed at 30%)."""
    o = ret.get("other_sources") or {}
    slab = (
        rupees(o.get("savings_interest"))
        + rupees(o.get("deposit_interest"))
        + rupees(o.get("dividends"))
        + rupees(o.get("other"))
    )

    fp = rupees(o.get("family_pension"))
    if fp:
        allowed = min(
            (fp / 3).quantize(Decimal(1), rounding=ROUND_HALF_UP),
            CAP_FAMILY_PENSION[regime],
        )
        out.lines["family_pension_deduction_57iia"] = allowed
        out.notes.append(f"s.57(iia): {allowed:,} deducted from family pension of {fp:,}.")
        slab += fp - allowed

    return slab, rupees(o.get("winnings"))


# --------------------------------------------------------------------------
# Chapter VI-A
# --------------------------------------------------------------------------


def _chapter_via(ret: dict, regime: str, slab_income: Money, out: Result) -> Money:
    d = ret.get("deductions") or {}
    salary = ret.get("salary") or {}
    basic_da = rupees(salary.get("basic_plus_da"))
    employer_nps = rupees(d.get("s80ccd2_employer_nps"))

    if regime == "new":
        # Only employer NPS survives - at 14% of Basic+DA for FY 2025-26, for
        # both government and private employers.
        allowed = min(employer_nps, (basic_da * Decimal("0.14")).quantize(Decimal(1)))
        if employer_nps > allowed:
            out.warnings.append(
                f"s.80CCD(2) capped at 14% of Basic+DA = {allowed:,} (claimed {employer_nps:,})."
            )
        dropped = sum(
            (rupees(v) for k, v in d.items() if k != "s80ccd2_employer_nps"), ZERO
        )
        if dropped > 0:
            out.warnings.append(
                f"New regime: {dropped:,} of Chapter VI-A deductions (80C/80D/80TTA/...) dropped."
            )
        out.lines["chapter_via"] = allowed
        return min(allowed, max(slab_income, ZERO))

    age = ret.get("meta", {}).get("age_band", "below_60")
    senior = age in ("senior", "super_senior")

    total = ZERO
    caps = {
        "s80c": CAP_80C,
        "s80ccd1b": CAP_80CCD1B,
    }
    for key, cap in caps.items():
        claimed = rupees(d.get(key))
        allowed = min(claimed, cap)
        if claimed > cap:
            out.warnings.append(f"{key.upper()} capped at {cap:,} (claimed {claimed:,}).")
        total += allowed

    nps_cap = (basic_da * Decimal("0.10")).quantize(Decimal(1))
    allowed_nps = min(employer_nps, nps_cap)
    if employer_nps > allowed_nps:
        out.warnings.append(
            f"s.80CCD(2) capped at 10% of Basic+DA = {allowed_nps:,} under the old regime "
            f"(private employer)."
        )
    total += allowed_nps

    o = ret.get("other_sources") or {}
    if senior:
        interest = rupees(o.get("savings_interest")) + rupees(o.get("deposit_interest"))
        allowed = min(interest, CAP_80TTB)
        if allowed:
            out.notes.append(f"s.80TTB (senior): {allowed:,} on savings + deposit interest.")
        total += allowed
    else:
        allowed = min(rupees(o.get("savings_interest")), CAP_80TTA)
        if allowed:
            out.notes.append(f"s.80TTA: {allowed:,} on savings-bank interest.")
        total += allowed

    # Uncapped-here items the user must have proofs for; the checker warns.
    for key in ("s80d", "s80g", "s80e", "s80u", "s80dd", "s80ddb", "s80eeb", "other"):
        total += rupees(d.get(key))

    # Chapter VI-A can never exceed slab-rate income; it cannot touch special rates.
    allowed_total = min(total, max(slab_income, ZERO))
    if total > allowed_total:
        out.warnings.append(
            f"Chapter VI-A restricted to slab-rate income: {allowed_total:,} of {total:,} usable "
            "(deductions cannot be set against capital gains, VDA or winnings)."
        )
    out.lines["chapter_via"] = allowed_total
    return allowed_total


# --------------------------------------------------------------------------
# set-off
# --------------------------------------------------------------------------


def _apply_hp_loss(hp_income: Money, b: Buckets, out: Result) -> None:
    """s.71 - house-property loss against other heads, capped at 2,00,000."""
    if hp_income >= 0:
        b.slab += hp_income
        return

    loss = -hp_income
    usable = min(loss, CAP_HP_LOSS_SETOFF)
    if loss > CAP_HP_LOSS_SETOFF:
        out.warnings.append(
            f"s.71(3A): house-property loss set-off capped at {CAP_HP_LOSS_SETOFF:,}; "
            f"{loss - CAP_HP_LOSS_SETOFF:,} carries forward (Schedule CFL - not tracked here)."
        )

    against_slab = min(usable, b.slab)
    b.slab -= against_slab
    remaining = usable - against_slab

    # Then capital gains, highest rate first. Never VDA (s.115BBH(2)) and never
    # winnings (s.58(4)). Against the full 112A gain, before its exemption -
    # the 1.25L is a tax-stage threshold, not an income exclusion.
    for name in ("stcg_111a", "ltcg_112a", "ltcg_112"):
        if remaining <= 0:
            break
        avail = getattr(b, name)
        used = min(remaining, avail)
        setattr(b, name, avail - used)
        remaining -= used

    if remaining > 0:
        out.warnings.append(
            f"{remaining:,} of house-property loss is unabsorbed and carries forward."
        )
    out.lines["hp_loss_setoff"] = usable - remaining


# --------------------------------------------------------------------------
# tax on the slab table
# --------------------------------------------------------------------------


def _slab_tax_new(income: Money) -> Money:
    tax = ZERO
    lower = ZERO
    for upper, rate in SLABS_NEW:
        if upper is None:
            tax += pct(max(income - lower, ZERO), rate)
            break
        band = min(income, upper) - lower
        if band > 0:
            tax += pct(band, rate)
        lower = upper
        if income <= upper:
            break
    return tax


def _slab_tax_old(income: Money, age_band: str) -> Money:
    exempt = BASIC_EXEMPTION_OLD.get(age_band, BASIC_EXEMPTION_OLD["below_60"])
    tax = ZERO
    # 5% band runs from the basic exemption to 5L; super-seniors have none.
    if income > exempt:
        tax += pct(min(income, Decimal(500_000)) - exempt, "5")
    if income > Decimal(500_000):
        tax += pct(min(income, Decimal(1_000_000)) - Decimal(500_000), "20")
    if income > Decimal(1_000_000):
        tax += pct(income - Decimal(1_000_000), "30")
    return max(tax, ZERO)


def _absorb_basic_exemption(b: Buckets, regime: str, age_band: str, out: Result) -> Buckets:
    """A resident may set unused basic exemption against special-rate gains.

    Never against VDA (s.115BBH) or winnings. Order matters, and no single order
    is always cheapest once 87A is in play, so callers try each; this helper is
    given an explicit order.
    """
    exempt = (
        Decimal(400_000) if regime == "new"
        else BASIC_EXEMPTION_OLD.get(age_band, BASIC_EXEMPTION_OLD["below_60"])
    )
    unused = max(exempt - b.slab, ZERO)
    if unused <= 0:
        return b
    out.notes.append(f"Unused basic exemption of {unused:,} absorbed against special-rate gains.")
    return b


def _tax_special(b: Buckets, absorb_order: list[str], regime: str, age_band: str
                 ) -> tuple[Money, Money, dict[str, Money]]:
    """Tax on the special-rate buckets after absorbing unused basic exemption.

    Returns (rebate-eligible tax, rebate-barred tax, per-bucket detail).
    Rebate-barred = 112A (s.112A(6)) plus VDA and winnings, where the portal
    denies 87A and the engine takes the safe posture.
    """
    exempt = (
        Decimal(400_000) if regime == "new"
        else BASIC_EXEMPTION_OLD.get(age_band, BASIC_EXEMPTION_OLD["below_60"])
    )
    unused = max(exempt - b.slab, ZERO)

    amounts = {
        "stcg_111a": b.stcg_111a,
        "ltcg_112a": b.ltcg_112a,
        "ltcg_112": b.ltcg_112,
    }
    for name in absorb_order:
        if unused <= 0:
            break
        used = min(unused, amounts[name])
        amounts[name] -= used
        unused -= used

    detail: dict[str, Money] = {}
    detail["tax_111a"] = pct(amounts["stcg_111a"], RATE_111A)
    taxable_112a = max(amounts["ltcg_112a"] - EXEMPT_112A, ZERO)
    detail["tax_112a"] = pct(taxable_112a, RATE_112A)
    detail["tax_112"] = pct(amounts["ltcg_112"], RATE_112)
    detail["tax_vda"] = pct(b.vda, RATE_VDA)
    detail["tax_winnings"] = pct(b.winnings, RATE_WINNINGS)
    detail["taxable_112a_after_exemption"] = taxable_112a

    if regime == "new":
        # Finance Act 2025 bars 87A against all special-rate income in the new regime.
        eligible = ZERO
        barred = (
            detail["tax_111a"] + detail["tax_112a"] + detail["tax_112"]
            + detail["tax_vda"] + detail["tax_winnings"]
        )
    else:
        eligible = detail["tax_111a"] + detail["tax_112"]
        barred = detail["tax_112a"] + detail["tax_vda"] + detail["tax_winnings"]

    return eligible, barred, detail


# --------------------------------------------------------------------------
# rebate, surcharge, cess
# --------------------------------------------------------------------------


def _rebate(regime: str, slab_income: Money, total_income: Money,
            slab_tax: Money, special_eligible: Money, out: Result) -> Money:
    if regime == "new":
        # Threshold tested on slab-rate income only, and the rebate offsets
        # slab-rate tax only (Finance Act 2025).
        if slab_income > REBATE_NEW_THRESHOLD:
            # Marginal relief: total tax cannot exceed the income above 12L.
            excess = slab_income - REBATE_NEW_THRESHOLD
            if slab_tax > excess:
                relief = slab_tax - excess
                out.notes.append(
                    f"s.87A marginal relief: slab tax {slab_tax:,} reduced by {relief:,} "
                    f"to the {excess:,} of income above 12,00,000."
                )
                return relief
            return ZERO
        return min(REBATE_NEW_CAP, slab_tax)

    # Old regime: hard cliff on total income, no marginal relief.
    if total_income > REBATE_OLD_THRESHOLD:
        return ZERO
    eligible = slab_tax + special_eligible
    rebate = min(REBATE_OLD_CAP, eligible)
    if special_eligible > 0 and rebate > slab_tax:
        out.warnings.append(
            "s.87A is being claimed against s.111A/112 tax. Courts allow it but CBDT "
            "Circular 13/2025 and CPC processing dispute it - confirm the portal accepts "
            "this figure before you submit."
        )
    return rebate


def _surcharge(regime: str, b: Buckets, total_income: Money, tax_after_rebate: Money,
               special_detail: dict[str, Money], slab_tax: Money, out: Result) -> Money:
    if tax_after_rebate <= 0:
        return ZERO

    # The 25%/37% tiers are tested on income excluding dividends and 111A/112/112A.
    dividends = special_detail.get("_dividends", ZERO)
    exclusive = total_income - dividends - b.stcg_111a - b.ltcg_112a - b.ltcg_112

    rate = ZERO
    threshold = ZERO
    for limit, r, on_exclusive in SURCHARGE_TIERS:
        tested = exclusive if on_exclusive else total_income
        if tested > limit:
            rate = Decimal(r)
            threshold = limit
    if rate == 0:
        return ZERO

    if regime == "new" and rate > SURCHARGE_CAP_NEW:
        out.notes.append("New regime: surcharge capped at 25% (37% tier does not apply).")
        rate = SURCHARGE_CAP_NEW

    # First Schedule clause (e): if total income crosses 2 crore only because of
    # dividends/CG, surcharge is a flat 15% on the whole tax - never 25%.
    if total_income > Decimal(20_000_000) and exclusive <= Decimal(20_000_000):
        out.notes.append(
            "Surcharge held at 15% (First Schedule clause (e)): total income crosses "
            "2 crore only on dividend/capital-gain income."
        )
        rate = Decimal(15)
        threshold = Decimal(10_000_000)

    surcharge = (tax_after_rebate * rate / 100).quantize(Decimal("0.01"))

    # 15% ceiling on the surcharge attributable to dividends and 111A/112/112A.
    if rate > SURCHARGE_CAP_SPECIAL:
        sheltered_tax = (
            special_detail.get("tax_111a", ZERO)
            + special_detail.get("tax_112a", ZERO)
            + special_detail.get("tax_112", ZERO)
        )
        if sheltered_tax > 0:
            other_tax = max(tax_after_rebate - sheltered_tax, ZERO)
            capped = (
                other_tax * rate / 100 + sheltered_tax * SURCHARGE_CAP_SPECIAL / 100
            ).quantize(Decimal("0.01"))
            if capped < surcharge:
                out.notes.append(
                    f"Surcharge on dividend/capital-gain tax held at the statutory 15% "
                    f"ceiling: {surcharge:,.0f} reduced to {capped:,.0f}."
                )
                surcharge = capped

    # Marginal relief: (tax + surcharge) may not exceed the tax at the threshold
    # plus every rupee of income above it.
    tested = exclusive if rate >= 25 else total_income
    over = tested - threshold
    if over > 0:
        tax_at_threshold = tax_after_rebate * threshold / tested if tested else ZERO
        ceiling = tax_at_threshold + over
        if tax_after_rebate + surcharge > ceiling:
            relieved = max(ceiling - tax_after_rebate, ZERO).quantize(Decimal("0.01"))
            if relieved < surcharge:
                out.notes.append(
                    f"Marginal relief on surcharge: {surcharge:,.0f} reduced to {relieved:,.0f}."
                )
                surcharge = relieved

    return surcharge


# --------------------------------------------------------------------------
# interest and fee
# --------------------------------------------------------------------------


def _months(start: _dt.date, end: _dt.date) -> int:
    """Whole months and any part of a month, the way s.234 counts them."""
    if end <= start:
        return 0
    n = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day > start.day:
        n += 1
    return max(n, 1)


def _parse_payments(items: Any) -> list[Payment]:
    out = []
    for p in items or []:
        out.append(Payment(_dt.date.fromisoformat(p["date"]), rupees(p["amount"])))
    return sorted(out, key=lambda x: x.date)


def _interest_234a(balance: Money, due: _dt.date, filing: _dt.date,
                   self_assessment: list[Payment], out: Result) -> Money:
    """1% per month on the unpaid balance past the due date.

    Payments stop the clock on the portion they discharge, at their own date.
    """
    if balance <= 0 or filing <= due:
        return ZERO

    interest = ZERO
    outstanding = balance
    cursor = due
    for p in self_assessment:
        if p.date <= due or outstanding <= 0:
            continue
        stop = min(p.date, filing)
        interest += floor_100(outstanding) * Decimal("0.01") * _months(cursor, stop)
        outstanding = max(outstanding - p.amount, ZERO)
        cursor = stop
    if outstanding > 0:
        interest += floor_100(outstanding) * Decimal("0.01") * _months(cursor, filing)
    if interest > 0:
        out.notes.append(f"s.234A: return filed after {due.isoformat()}.")
    return interest.quantize(Decimal("0.01"))


def _interest_234b(assessed: Money, prepaid: Money, advance: Money,
                   filing: _dt.date, self_assessment: list[Payment], out: Result) -> Money:
    shortfall_base = assessed - prepaid
    if shortfall_base < Decimal(10_000):
        return ZERO
    if advance >= shortfall_base * Decimal("0.90"):
        return ZERO

    start = _dt.date(2026, 4, 1)
    interest = ZERO
    outstanding = shortfall_base - advance
    cursor = start
    for p in self_assessment:
        if p.date <= start or outstanding <= 0:
            continue
        stop = min(p.date, filing)
        interest += floor_100(outstanding) * Decimal("0.01") * _months(cursor, stop)
        outstanding = max(outstanding - p.amount, ZERO)
        cursor = stop
    if outstanding > 0:
        interest += floor_100(outstanding) * Decimal("0.01") * _months(cursor, max(filing, start))
    if interest > 0:
        out.notes.append("s.234B: advance tax paid was under 90% of the assessed liability.")
    return interest.quantize(Decimal("0.01"))


def _interest_234c(assessed_advance: Money, advance: list[Payment],
                   presumptive: bool, out: Result) -> Money:
    if assessed_advance <= 0:
        return ZERO

    if presumptive:
        paid_by_mar15 = sum(
            (p.amount for p in advance if p.date <= _dt.date(2026, 3, 15)), ZERO
        )
        short = max(assessed_advance - paid_by_mar15, ZERO)
        if short <= 0:
            return ZERO
        out.notes.append("s.234C: presumptive taxpayers owe one 100% installment by 15 Mar.")
        return (floor_100(short) * Decimal("0.01")).quantize(Decimal("0.01"))

    interest = ZERO
    for i, (due, cum, safe) in enumerate(INSTALMENTS):
        paid = sum((p.amount for p in advance if p.date <= due), ZERO)
        required = (assessed_advance * cum).quantize(Decimal(1))
        if safe is not None and paid >= (assessed_advance * safe).quantize(Decimal(1)):
            continue
        short = max(required - paid, ZERO)
        if short <= 0:
            continue
        months = 1 if i == 3 else 3
        interest += floor_100(short) * Decimal("0.01") * months
    if interest > 0:
        out.notes.append(
            "s.234C: advance-tax installments were short. The engine assumes no "
            "unforeseeable-gain carve-out unless quarterly capital-gain data is supplied."
        )
    return interest.quantize(Decimal("0.01"))


def _fee_234f(total_income: Money, due: _dt.date, filing: _dt.date, out: Result) -> Money:
    if filing <= due:
        return ZERO
    fee = Decimal(1_000) if total_income <= Decimal(500_000) else Decimal(5_000)
    out.notes.append(f"s.234F late-filing fee: {fee:,}.")
    return fee


# --------------------------------------------------------------------------
# the computation
# --------------------------------------------------------------------------


def compute(ret: dict, regime: str) -> Result:
    if regime not in ("new", "old"):
        raise TaxError(f"unknown regime {regime!r}")

    meta = ret.get("meta") or {}
    age_band = meta.get("age_band", "below_60")
    if age_band not in BASIC_EXEMPTION_OLD:
        raise TaxError(f"age_band must be one of {sorted(BASIC_EXEMPTION_OLD)}")
    if meta.get("residential_status", "resident") != "resident":
        raise TaxError(
            "This engine covers resident individuals only. Non-resident and RNOR "
            "returns need a CA."
        )

    out = Result(regime=regime)

    # --- heads
    salary = _salary(ret, regime, out)
    hp = _house_property(ret, regime, out)
    business = _business(ret, out)
    other_slab, winnings = _other_sources(ret, regime, out)

    cg = ret.get("capital_gains") or {}
    b = Buckets(
        slab=salary + business + other_slab + rupees(cg.get("stcg_slab")),
        stcg_111a=rupees(cg.get("stcg_111a")),
        ltcg_112a=rupees(cg.get("ltcg_112a")),
        ltcg_112=rupees(cg.get("ltcg_112")),
        vda=rupees(cg.get("vda")),
        winnings=winnings,
    )
    out.lines["salary_net"] = salary
    out.lines["house_property"] = hp
    out.lines["business"] = business
    out.lines["other_sources"] = other_slab

    if b.ltcg_112 > 0:
        out.warnings.append(
            "s.112: feed the UNINDEXED gain. For land/building acquired on or before "
            "22-Jul-2024 the tax is capped at 20% of the indexed gain (2nd proviso to "
            "s.112(1)(a)) - the engine cannot apply that cap. If 20% x indexed gain is "
            "lower, that asset needs the offline utility or a CA."
        )
    if b.vda > 0:
        out.notes.append(
            "s.115BBH: crypto/VDA at a flat 30%, cost of acquisition only, no set-off, "
            "no carry-forward, no basic-exemption absorption, no 87A."
        )

    _apply_hp_loss(hp, b, out)

    gross_total = b.total()
    out.lines["gross_total_income"] = gross_total

    via = _chapter_via(ret, regime, b.slab, out)
    b.slab = max(b.slab - via, ZERO)

    total_income = round_10(b.total())
    out.lines["total_income"] = total_income
    out.lines["slab_income"] = b.slab
    out.lines["special_income"] = b.special_total()

    # --- tax. No fixed absorption order is always cheapest once 87A is in
    #     play, so try every order and keep the lowest lawful tax.
    dividends = rupees((ret.get("other_sources") or {}).get("dividends"))
    best = None
    orders = [
        ["stcg_111a", "ltcg_112a", "ltcg_112"],
        ["stcg_111a", "ltcg_112", "ltcg_112a"],
        ["ltcg_112a", "stcg_111a", "ltcg_112"],
        ["ltcg_112", "stcg_111a", "ltcg_112a"],
        ["ltcg_112a", "ltcg_112", "stcg_111a"],
        ["ltcg_112", "ltcg_112a", "stcg_111a"],
    ]
    for order in orders:
        probe = Result(regime=regime)
        slab_tax = (
            _slab_tax_new(b.slab) if regime == "new"
            else _slab_tax_old(b.slab, age_band)
        )
        elig, barred, detail = _tax_special(b, order, regime, age_band)
        rebate = _rebate(regime, b.slab, total_income, slab_tax, elig, probe)
        after = max(slab_tax + elig + barred - rebate, ZERO)
        if best is None or after < best[0]:
            best = (after, order, slab_tax, elig, barred, detail, rebate, probe)

    after_rebate, order, slab_tax, elig, barred, detail, rebate, probe = best
    out.notes.extend(probe.notes)
    out.warnings.extend(probe.warnings)
    if b.special_total() > 0:
        _absorb_basic_exemption(b, regime, age_band, out)

    out.lines["slab_tax"] = slab_tax
    out.lines["special_rate_tax"] = elig + barred
    for k, v in detail.items():
        if not k.startswith("_"):
            out.lines[k] = v
    out.lines["rebate_87a"] = rebate
    out.lines["tax_after_rebate"] = after_rebate

    detail["_dividends"] = dividends
    surcharge = _surcharge(regime, b, total_income, after_rebate, detail, slab_tax, out)
    out.lines["surcharge"] = surcharge

    cess = pct(after_rebate + surcharge, CESS_RATE)
    out.lines["cess"] = cess

    relief89 = rupees(ret.get("relief_89"))
    if relief89:
        out.warnings.append(
            "Relief u/s 89(1) claimed: Form 10E must be e-filed BEFORE the return or "
            "CPC will disallow it."
        )
    liability = max(after_rebate + surcharge + cess - relief89, ZERO)
    out.lines["relief_89"] = relief89
    out.lines["total_tax_liability"] = liability

    # --- credits
    tp = ret.get("taxes_paid") or {}
    tds = rupees(tp.get("tds")) + rupees(tp.get("tcs"))
    advance_list = _parse_payments(tp.get("advance_tax"))
    sa_list = _parse_payments(tp.get("self_assessment_tax"))
    advance = sum((p.amount for p in advance_list), ZERO)
    sa = sum((p.amount for p in sa_list), ZERO)
    out.lines["tds_tcs"] = tds
    out.lines["advance_tax"] = advance
    out.lines["self_assessment_tax"] = sa

    # --- interest and fee
    due = (
        _dt.date.fromisoformat(meta["due_date"]) if meta.get("due_date")
        else DEFAULT_DUE_DATE
    )
    filing = (
        _dt.date.fromisoformat(meta["filing_date"]) if meta.get("filing_date")
        else _dt.date.today()
    )

    balance_before_interest = max(liability - tds - advance - sa, ZERO)
    i234a = _interest_234a(balance_before_interest, due, filing, sa_list, out)

    has_business = bool(ret.get("business"))
    senior_no_business = age_band in ("senior", "super_senior") and not has_business
    if senior_no_business:
        i234b = i234c = ZERO
        out.notes.append(
            "s.207(2): a resident 60+ with no business income owes no advance tax, "
            "so no 234B/234C."
        )
    else:
        i234b = _interest_234b(liability, tds + advance, advance, filing, sa_list, out)
        presumptive = bool(
            (ret.get("business") or {}).get("presumptive_44ad")
            or (ret.get("business") or {}).get("presumptive_44ada")
        )
        i234c = _interest_234c(max(liability - tds, ZERO), advance_list, presumptive, out)

    fee = _fee_234f(total_income, due, filing, out)

    out.lines["interest_234a"] = i234a
    out.lines["interest_234b"] = i234b
    out.lines["interest_234c"] = i234c
    out.lines["fee_234f"] = fee

    net = liability + i234a + i234b + i234c + fee - tds - advance - sa
    net = round_10(net)
    out.lines["net_payable"] = max(net, ZERO)
    out.lines["refund_due"] = max(-net, ZERO)

    if filing > due:
        out.warnings.append(
            f"Filed after the due date ({due.isoformat()}). Under s.115BAC(6) a taxpayer "
            "with no business income cannot opt into the OLD regime in a belated return - "
            "the portal enforces new-regime-only."
        )

    return out


def compare(ret: dict) -> dict[str, Any]:
    """Both regimes, plus a recommendation that respects the belated-return lock."""
    results = {r: compute(ret, r) for r in ("new", "old")}
    meta = ret.get("meta") or {}
    due = (
        _dt.date.fromisoformat(meta["due_date"]) if meta.get("due_date")
        else DEFAULT_DUE_DATE
    )
    filing = (
        _dt.date.fromisoformat(meta["filing_date"]) if meta.get("filing_date")
        else _dt.date.today()
    )
    has_business = bool(ret.get("business"))

    def cost(r: Result) -> Money:
        return r["net_payable"] - r["refund_due"]

    cheaper = min(results.values(), key=cost)
    recommended = cheaper.regime
    forced = None
    if filing > due and not has_business and recommended == "old":
        recommended = "new"
        forced = (
            "The old regime computes cheaper, but the return is belated and there is no "
            "business income - s.115BAC(6) locks you into the new regime. The portal will "
            "not accept the old-regime figure."
        )

    saving = abs(cost(results["new"]) - cost(results["old"]))
    return {
        "assessment_year": AY,
        "results": results,
        "recommended": recommended,
        "saving": saving,
        "forced_note": forced,
    }


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

ROWS = [
    ("salary_net", "Salary (net of exemptions & standard deduction)"),
    ("house_property", "Income from house property"),
    ("business", "Profits and gains of business/profession"),
    ("other_sources", "Income from other sources"),
    ("special_income", "Capital gains / special-rate income"),
    ("gross_total_income", "Gross total income"),
    ("chapter_via", "Less: Chapter VI-A deductions"),
    ("total_income", "TOTAL INCOME (s.288A)"),
    (None, None),
    ("slab_tax", "Tax at slab rates"),
    ("tax_111a", "  Tax on STCG s.111A @ 20%"),
    ("tax_112a", "  Tax on LTCG s.112A @ 12.5%"),
    ("tax_112", "  Tax on LTCG s.112 @ 12.5%"),
    ("tax_vda", "  Tax on VDA s.115BBH @ 30%"),
    ("tax_winnings", "  Tax on winnings @ 30%"),
    ("rebate_87a", "Less: rebate u/s 87A"),
    ("surcharge", "Add: surcharge"),
    ("cess", "Add: health & education cess @ 4%"),
    ("relief_89", "Less: relief u/s 89(1)"),
    ("total_tax_liability", "TOTAL TAX LIABILITY"),
    (None, None),
    ("tds_tcs", "Less: TDS / TCS"),
    ("advance_tax", "Less: advance tax"),
    ("self_assessment_tax", "Less: self-assessment tax"),
    ("interest_234a", "Add: interest u/s 234A"),
    ("interest_234b", "Add: interest u/s 234B"),
    ("interest_234c", "Add: interest u/s 234C"),
    ("fee_234f", "Add: fee u/s 234F"),
]


def _fmt(x: Money) -> str:
    return f"{x:,.0f}"


def render(cmp: dict) -> str:
    new, old = cmp["results"]["new"], cmp["results"]["old"]
    L: list[str] = []
    L.append(f"Income tax computation - AY {cmp['assessment_year']} (FY 2025-26)")
    L.append("=" * 74)
    L.append(f"{'':<46}{'NEW':>13}{'OLD':>15}")
    L.append("-" * 74)
    for key, label in ROWS:
        if key is None:
            L.append("")
            continue
        a, b = new.lines.get(key, ZERO), old.lines.get(key, ZERO)
        if a == 0 and b == 0:
            continue
        L.append(f"{label:<46}{_fmt(a):>13}{_fmt(b):>15}")
    L.append("-" * 74)
    for key, label in (("net_payable", "NET TAX PAYABLE"), ("refund_due", "REFUND DUE")):
        a, b = new.lines[key], old.lines[key]
        if a or b:
            L.append(f"{label:<46}{_fmt(a):>13}{_fmt(b):>15}")
    L.append("=" * 74)

    L.append("")
    L.append(f"RECOMMENDED REGIME: {cmp['recommended'].upper()}   (difference: {_fmt(cmp['saving'])})")
    if cmp["forced_note"]:
        L.append(f"  ! {cmp['forced_note']}")
    if cmp["recommended"] == "old":
        L.append("  ! The old regime needs documentary proof for every deduction claimed.")
        L.append("  ! With business income, opting for the old regime requires Form 10-IEA")
        L.append("    filed BEFORE this return.")

    for name, res in (("NEW", new), ("OLD", old)):
        if res.notes or res.warnings:
            L.append("")
            L.append(f"{name} regime - notes")
            for n in res.notes:
                L.append(f"  . {n}")
            for w in res.warnings:
                L.append(f"  ! {w}")

    L.append("")
    L.append("Figures are rounded per s.288A/288B; allow +/- 10 against the portal.")
    return "\n".join(L)


def to_dict(cmp: dict) -> dict:
    return {
        "assessment_year": cmp["assessment_year"],
        "recommended_regime": cmp["recommended"],
        "saving": float(cmp["saving"]),
        "forced_note": cmp["forced_note"],
        "regimes": {
            name: {
                "lines": {k: float(v) for k, v in res.lines.items()},
                "notes": res.notes,
                "warnings": res.warnings,
            }
            for name, res in cmp["results"].items()
        },
    }


def _track(workspace, stage, status, detail=None, **meta):
    """Optional status-page update. Imported lazily so the engine stays a
    self-contained module with no reason to reach for anything else."""
    if not workspace:
        return
    try:
        from progress import record
        record(workspace, stage, status, detail, **meta)
    except Exception:  # noqa: BLE001 - the dashboard never blocks a computation
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("return_json", help="path to return.json")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--regime", choices=("new", "old"), help="compute one regime only")
    ap.add_argument("--progress", metavar="WORKSPACE",
                    help="also update the status page in this workspace")
    args = ap.parse_args(argv)

    with open(args.return_json, encoding="utf-8") as fh:
        ret = json.load(fh)

    try:
        if args.regime:
            res = compute(ret, args.regime)
            if args.json:
                print(json.dumps(
                    {"lines": {k: float(v) for k, v in res.lines.items()},
                     "notes": res.notes, "warnings": res.warnings},
                    indent=2,
                ))
            else:
                for k, v in res.lines.items():
                    print(f"{k:<40}{_fmt(v):>15}")
            return 0
        cmp = compare(ret)
    except TaxError as exc:
        print(f"tax_core: {exc}", file=sys.stderr)
        _track(args.progress, "compute", "blocked", str(exc))
        return 2

    chosen = cmp["results"][cmp["recommended"]]
    _track(args.progress, "compute", "done",
           f"{cmp['recommended'].capitalize()} regime is cheaper by "
           f"{cmp['saving']:,.0f}",
           regime=cmp["recommended"],
           refund=float(chosen["refund_due"]) or None,
           payable=float(chosen["net_payable"]) or None)

    print(json.dumps(to_dict(cmp), indent=2) if args.json else render(cmp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
