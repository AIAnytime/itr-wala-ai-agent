#!/usr/bin/env python3
"""check_return - validate return.json before it reaches the tax engine.

Two jobs:

1. **Schema.** Unknown keys are errors, not warnings. A typo like "s80CC" would
   silently drop a deduction and cost real money, so the whitelist is closed.
2. **Cross-check.** Figures transcribed from documents are compared against the
   totals printed on those documents (`source_totals`). A mismatch is an ERROR
   that blocks computation - not an advisory - because it means the extraction
   is wrong somewhere and the engine would compute a confident wrong answer.

Exit 0 = safe to compute. Exit 1 = errors. Warnings never block, but the agent
must read every one of them aloud to the user.

    python3 check_return.py return.json
    python3 check_return.py return.json --json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

# Field name -> allowed child keys. None means "any scalar amount".
SCHEMA: dict[str, Any] = {
    "meta": {
        "assessment_year", "age_band", "residential_status",
        "filing_date", "due_date", "itr_form", "taxpayer_label",
    },
    "salary": {
        "gross", "exempt_allowances", "exempt_retirement",
        "professional_tax", "basic_plus_da", "employer",
    },
    "house_property": {
        "kind", "annual_rent", "municipal_tax_paid", "interest_paid", "label",
    },
    "business": {
        "presumptive_44ada", "presumptive_44ad", "regular_books_profit",
        "nature_of_business_code",
    },
    "capital_gains": {
        "stcg_111a", "stcg_slab", "ltcg_112a", "ltcg_112", "vda",
    },
    "other_sources": {
        "savings_interest", "deposit_interest", "dividends",
        "family_pension", "winnings", "other",
    },
    "deductions": {
        "s80c", "s80ccd1b", "s80ccd2_employer_nps", "s80d", "s80g", "s80e",
        "s80u", "s80dd", "s80ddb", "s80eeb", "other",
    },
    "taxes_paid": {"tds", "tcs", "advance_tax", "self_assessment_tax"},
    "foreign_assets": {
        "country", "country_code", "asset_type", "institution",
        "account_ref", "opened_on", "peak_value", "closing_value",
        "income_accrued", "income_offered_in_schedule",
    },
    "source_totals": {
        "form16_gross_salary", "form16_tds", "form26as_tds",
        "ais_interest", "ais_dividends", "broker_ltcg_112a", "broker_stcg_111a",
    },
    "relief_89": None,
    "notes": None,
}

# Fields that hold text or dates rather than rupees. Everything else inside a
# known block is swept as an amount, so a negative or a boolean cannot slip
# through just because no hand-written rule happened to look at it.
NON_AMOUNT = {
    "assessment_year", "age_band", "residential_status", "filing_date",
    "due_date", "itr_form", "taxpayer_label", "employer", "kind", "label",
    "nature_of_business_code", "country", "country_code", "asset_type",
    "institution", "account_ref", "opened_on", "income_offered_in_schedule",
    "advance_tax", "self_assessment_tax", "presumptive_44ada",
    "presumptive_44ad", "notes",
}

AGE_BANDS = {"below_60", "senior", "super_senior"}
HP_KINDS = {"self_occupied", "let_out", "deemed_let_out"}
ASSET_TYPES = {
    "bank_account", "custodial_account", "equity_debt_interest",
    "immovable_property", "insurance_contract", "other",
}
# Tolerance against document totals. Ten rupees is s.288B rounding; more than
# that is a transcription error, not rounding.
TOLERANCE = Decimal(10)

PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def _amount(value: Any, path: str, rep: Report) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, bool):
        rep.err(f"{path}: expected an amount, got a boolean")
        return Decimal(0)
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        rep.err(f"{path}: {value!r} is not a number")
        return Decimal(0)
    if d < 0 and not path.startswith("house_property"):
        rep.err(f"{path}: negative amount {d} - income and deductions are entered positive")
    if d != d.to_integral_value() and abs(d % 1) > 0:
        rep.warn(f"{path}: {d} has paise; the return is filed in whole rupees")
    return d


def _date(value: Any, path: str, rep: Report) -> _dt.date | None:
    if value is None:
        return None
    try:
        return _dt.date.fromisoformat(str(value))
    except ValueError:
        rep.err(f"{path}: {value!r} is not an ISO date (YYYY-MM-DD)")
        return None


# --------------------------------------------------------------------------
# structure
# --------------------------------------------------------------------------


def check_schema(ret: dict, rep: Report) -> None:
    for key in ret:
        if key not in SCHEMA:
            near = [k for k in SCHEMA if k.lower().startswith(key.lower()[:4])]
            hint = f" - did you mean {near[0]!r}?" if near else ""
            rep.err(f"unknown top-level key {key!r}{hint}")

    for key, allowed in SCHEMA.items():
        if key not in ret or allowed is None:
            continue
        value = ret[key]
        blocks = value if isinstance(value, list) else [value]
        for i, block in enumerate(blocks):
            if not isinstance(block, dict):
                rep.err(f"{key}: expected an object, got {type(block).__name__}")
                continue
            label = f"{key}[{i}]" if isinstance(value, list) else key
            for child in block:
                if child not in allowed:
                    near = [k for k in allowed if k.lower().startswith(child.lower()[:4])]
                    hint = f" - did you mean {near[0]!r}?" if near else ""
                    rep.err(f"{label}.{child}: not a recognised field{hint}")


def check_amounts(ret: dict, rep: Report) -> None:
    """Sweep every rupee field in every known block through _amount."""
    for key, allowed in SCHEMA.items():
        if key not in ret:
            continue
        value = ret[key]
        if allowed is None:
            if key == "relief_89":
                _amount(value, key, rep)
            continue
        blocks = value if isinstance(value, list) else [value]
        for i, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            label = f"{key}[{i}]" if isinstance(value, list) else key
            for child, v in block.items():
                if child in NON_AMOUNT:
                    # Nested presumptive blocks are amount-bearing themselves.
                    if isinstance(v, dict):
                        for gk, gv in v.items():
                            _amount(gv, f"{label}.{child}.{gk}", rep)
                    continue
                _amount(v, f"{label}.{child}", rep)


def check_meta(ret: dict, rep: Report) -> None:
    meta = ret.get("meta") or {}
    if not meta:
        rep.err("meta: missing. age_band, filing_date and due_date are required.")
        return

    ay = meta.get("assessment_year")
    if ay and str(ay) != "2026-27":
        rep.err(
            f"meta.assessment_year is {ay!r}. This engine is pinned to AY 2026-27; "
            "the rates for any other year are different. Stop and use a CA."
        )

    age = meta.get("age_band")
    if age not in AGE_BANDS:
        rep.err(f"meta.age_band must be one of {sorted(AGE_BANDS)}, got {age!r}")

    status = meta.get("residential_status", "resident")
    if status != "resident":
        rep.err(
            f"meta.residential_status is {status!r}. Non-resident and RNOR returns "
            "are out of scope."
        )

    due = _date(meta.get("due_date"), "meta.due_date", rep)
    filing = _date(meta.get("filing_date"), "meta.filing_date", rep)
    if due and filing and filing > due:
        rep.warn(
            f"Filing on {filing} is after the {due} due date: expect s.234A interest and "
            "the s.234F fee, and note the s.115BAC(6) regime lock."
        )
    if due and due not in (_dt.date(2026, 7, 31), _dt.date(2026, 8, 31),
                           _dt.date(2026, 10, 31), _dt.date(2026, 11, 30)):
        rep.warn(
            f"meta.due_date {due} is not a standard AY 2026-27 deadline "
            "(31 Jul / 31 Aug / 31 Oct / 30 Nov 2026). Confirm it matches your ITR form."
        )

    form = meta.get("itr_form")
    if form and form not in ("ITR-1", "ITR-2", "ITR-3", "ITR-4"):
        rep.err(f"meta.itr_form {form!r} is not one of ITR-1/2/3/4")


def check_privacy(ret: dict, rep: Report) -> None:
    """PAN and Aadhaar are not needed to compute anything. If they turn up in
    the JSON, someone pasted a document wholesale."""
    blob = json.dumps(ret)
    if PAN_RE.search(blob):
        rep.err(
            "A PAN appears in return.json. No computation needs it - remove it. "
            "This file is the one most likely to be pasted into a chat or committed."
        )
    if AADHAAR_RE.search(blob):
        rep.warn(
            "Something matching an Aadhaar number appears in return.json. If it is one, "
            "remove it; nothing here needs it."
        )


def check_shape(ret: dict, rep: Report) -> None:
    for i, hp in enumerate(ret.get("house_property") or []):
        kind = hp.get("kind")
        if kind not in HP_KINDS:
            rep.err(f"house_property[{i}].kind must be one of {sorted(HP_KINDS)}")
        if kind == "self_occupied" and _amount(hp.get("annual_rent"), "x", Report()) > 0:
            rep.err(f"house_property[{i}]: a self-occupied property cannot have rent")
        interest = _amount(hp.get("interest_paid"), f"house_property[{i}].interest_paid", rep)
        if kind == "self_occupied" and interest > 200_000:
            rep.warn(
                f"house_property[{i}]: s.24(b) interest of {interest:,} exceeds the "
                "2,00,000 self-occupied cap; the excess is not deductible."
            )

    b = ret.get("business") or {}
    if b.get("presumptive_44ada") and b.get("presumptive_44ad"):
        rep.warn(
            "Both s.44ADA and s.44AD are declared. That is legal but unusual - confirm "
            "you have both a profession and a separate business."
        )
    if b and not b.get("nature_of_business_code"):
        rep.warn(
            "business.nature_of_business_code is missing. The portal makes it mandatory "
            "in Schedule BP (e.g. 16019 other professional services, 14005 software)."
        )

    for i, fa in enumerate(ret.get("foreign_assets") or []):
        if fa.get("asset_type") not in ASSET_TYPES:
            rep.err(f"foreign_assets[{i}].asset_type must be one of {sorted(ASSET_TYPES)}")
        for req in ("country", "peak_value", "closing_value"):
            if fa.get(req) in (None, ""):
                rep.err(f"foreign_assets[{i}].{req} is required for Schedule FA")
        opened = _date(fa.get("opened_on"), f"foreign_assets[{i}].opened_on", rep)
        if opened and opened > _dt.date(2025, 12, 31):
            rep.warn(
                f"foreign_assets[{i}] was opened after 31-Dec-2025, outside the Schedule FA "
                "reporting period (1 Jan - 31 Dec 2025). It belongs in next year's return."
            )
        peak = _amount(fa.get("peak_value"), f"foreign_assets[{i}].peak_value", rep)
        closing = _amount(fa.get("closing_value"), f"foreign_assets[{i}].closing_value", rep)
        if closing > peak:
            rep.err(
                f"foreign_assets[{i}]: closing value {closing:,} exceeds the peak "
                f"{peak:,} - one of the two is wrong."
            )

    for key in ("advance_tax", "self_assessment_tax"):
        for i, p in enumerate(((ret.get("taxes_paid") or {}).get(key)) or []):
            if not isinstance(p, dict) or "date" not in p or "amount" not in p:
                rep.err(f"taxes_paid.{key}[{i}]: needs both 'date' and 'amount'")
                continue
            d = _date(p["date"], f"taxes_paid.{key}[{i}].date", rep)
            _amount(p["amount"], f"taxes_paid.{key}[{i}].amount", rep)
            if d and key == "advance_tax" and not (_dt.date(2025, 4, 1) <= d <= _dt.date(2026, 3, 31)):
                rep.err(
                    f"taxes_paid.advance_tax[{i}].date {d} falls outside FY 2025-26. "
                    "A payment after 31-Mar-2026 is self-assessment tax, not advance tax."
                )


# --------------------------------------------------------------------------
# cross-checks against the documents
# --------------------------------------------------------------------------


def check_sources(ret: dict, rep: Report) -> None:
    st = ret.get("source_totals") or {}
    if not st:
        rep.warn(
            "source_totals is empty, so nothing was cross-checked against your documents. "
            "Fill in the Form 16 / 26AS / AIS totals as printed - this is the only "
            "mechanical guard against a transcription slip."
        )
        return

    def cmp(label: str, claimed: Decimal, printed_key: str) -> None:
        if printed_key not in st:
            return
        printed = _amount(st[printed_key], f"source_totals.{printed_key}", rep)
        delta = claimed - printed
        if abs(delta) > TOLERANCE:
            rep.err(
                f"{label}: return.json says {claimed:,} but {printed_key} says "
                f"{printed:,} (off by {delta:,}). Find the difference before computing."
            )

    salary = ret.get("salary") or {}
    cmp("salary.gross", _amount(salary.get("gross"), "salary.gross", rep),
        "form16_gross_salary")

    tp = ret.get("taxes_paid") or {}
    tds = _amount(tp.get("tds"), "taxes_paid.tds", rep)
    if "form26as_tds" in st and "form16_tds" in st:
        f16 = _amount(st["form16_tds"], "source_totals.form16_tds", rep)
        f26 = _amount(st["form26as_tds"], "source_totals.form26as_tds", rep)
        if f26 > f16 + TOLERANCE:
            rep.warn(
                f"26AS shows {f26 - f16:,} more TDS than Form 16. A bank or another "
                "deductor probably withheld tax too - claim it, and declare the income "
                "that produced it."
            )
    cmp("taxes_paid.tds", tds, "form26as_tds")

    o = ret.get("other_sources") or {}
    interest = (_amount(o.get("savings_interest"), "other_sources.savings_interest", rep)
                + _amount(o.get("deposit_interest"), "other_sources.deposit_interest", rep))
    cmp("interest income", interest, "ais_interest")
    cmp("other_sources.dividends",
        _amount(o.get("dividends"), "other_sources.dividends", rep), "ais_dividends")

    cg = ret.get("capital_gains") or {}
    cmp("capital_gains.ltcg_112a",
        _amount(cg.get("ltcg_112a"), "capital_gains.ltcg_112a", rep), "broker_ltcg_112a")
    cmp("capital_gains.stcg_111a",
        _amount(cg.get("stcg_111a"), "capital_gains.stcg_111a", rep), "broker_stcg_111a")


def check_plausibility(ret: dict, rep: Report) -> None:
    """Things that are legal but are usually a sign something was missed."""
    o = ret.get("other_sources") or {}
    interest = (_amount(o.get("savings_interest"), "x", Report())
                + _amount(o.get("deposit_interest"), "x", Report()))
    if interest == 0:
        rep.warn(
            "No interest income at all. Almost every filer has some savings-bank "
            "interest, and it is in your AIS whether you declare it or not. Check."
        )

    d = ret.get("deductions") or {}
    if _amount(d.get("s80d"), "x", Report()) == 0:
        rep.warn(
            "No s.80D claimed. If you pay any health-insurance premium (including for "
            "parents), it is deductible under the old regime - worth checking before "
            "you settle on a regime."
        )

    cg = ret.get("capital_gains") or {}
    if _amount(cg.get("ltcg_112"), "x", Report()) > 0:
        rep.warn(
            "s.112 LTCG present: feed the UNINDEXED gain. For land or buildings bought "
            "on or before 22-Jul-2024 the tax is capped at 20% of the indexed gain and "
            "the engine cannot apply that cap - if it bites, you need a CA."
        )

    if ret.get("foreign_assets"):
        rep.warn(
            "Schedule FA is in play. Non-disclosure carries a flat 10,00,000 penalty "
            "under the Black Money Act regardless of the asset's value, and the "
            "reporting period is the CALENDAR year 1 Jan - 31 Dec 2025, not the FY. "
            "Foreign assets also rule out ITR-1 and ITR-4."
        )

    b = ret.get("business") or {}
    if b and (ret.get("meta") or {}).get("itr_form") in ("ITR-1", "ITR-2"):
        rep.err(
            f"Business income cannot be filed on {ret['meta']['itr_form']}. "
            "Use ITR-4 (presumptive only) or ITR-3."
        )
    if ret.get("foreign_assets") and (ret.get("meta") or {}).get("itr_form") in ("ITR-1", "ITR-4"):
        rep.err(
            f"Foreign assets require Schedule FA, which {ret['meta']['itr_form']} does "
            "not carry. Use ITR-2 (no business income) or ITR-3."
        )


def validate(ret: dict) -> Report:
    rep = Report()
    if not isinstance(ret, dict):
        rep.err("return.json must contain a JSON object")
        return rep
    check_schema(ret, rep)
    check_amounts(ret, rep)
    check_meta(ret, rep)
    check_privacy(ret, rep)
    check_shape(ret, rep)
    check_sources(ret, rep)
    check_plausibility(ret, rep)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("return_json")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--progress", metavar="WORKSPACE",
                    help="also update the status page in this workspace")
    args = ap.parse_args(argv)

    # Progress reporting is a convenience layered on top; it is imported here so
    # the validator itself stays importable with nothing else present.
    def track(stage, status, detail=None):
        if not args.progress:
            return
        try:
            from progress import record
            record(args.progress, stage, status, detail)
        except Exception:  # noqa: BLE001 - never let the dashboard block a check
            pass

    track("validate", "active")

    try:
        with open(args.return_json, encoding="utf-8") as fh:
            ret = json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"check_return: {args.return_json} is not valid JSON - {exc}", file=sys.stderr)
        return 1

    rep = validate(ret)

    if rep.ok:
        track("validate", "done",
              f"{len(rep.warnings)} thing(s) to look at" if rep.warnings
              else "Everything matches your documents")
    else:
        track("validate", "blocked", rep.errors[0])

    if args.json:
        print(json.dumps({"ok": rep.ok, "errors": rep.errors,
                          "warnings": rep.warnings}, indent=2))
        return 0 if rep.ok else 1

    for e in rep.errors:
        print(f"ERROR  {e}")
    for w in rep.warnings:
        print(f"WARN   {w}")
    if rep.ok:
        print(f"\nOK - {len(rep.warnings)} warning(s). Read every one to the user "
              "before computing.")
        return 0
    print(f"\nBLOCKED - {len(rep.errors)} error(s). The engine will not run until "
          "these are resolved.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
