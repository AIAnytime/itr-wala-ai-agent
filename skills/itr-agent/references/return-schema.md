# `return.json` — the schema

One file holds the whole return. `scripts/check_return.py` validates it and
**rejects unknown keys**: a typo like `s80CC` would otherwise be silently
ignored and quietly cost you the deduction.

Amounts are plain numbers in **whole rupees** — no commas, no `₹`, no strings.
Dates are ISO `YYYY-MM-DD`.

## Minimum viable file

```json
{
  "meta": {
    "assessment_year": "2026-27",
    "age_band": "below_60",
    "residential_status": "resident",
    "filing_date": "2026-07-25",
    "due_date": "2026-07-31"
  },
  "salary": { "gross": 1450000 },
  "taxes_paid": { "tds": 96000 }
}
```

## Blocks

### `meta` — required

| Key | Values |
|---|---|
| `assessment_year` | `"2026-27"` only. Any other year and the validator stops you. |
| `age_band` | `below_60` · `senior` (60–79) · `super_senior` (80+) |
| `residential_status` | `resident` only. NRI and RNOR are out of scope. |
| `filing_date` | The day you will actually submit — it drives 234A/B/C. |
| `due_date` | Your form's deadline (see `form-picker.md`). |
| `itr_form` | `ITR-1`/`2`/`3`/`4`. Optional, but set it — the validator cross-checks it against your income. |
| `taxpayer_label` | A nickname. **Never a PAN** — the validator errors on one. |

### `salary`

| Key | Meaning |
|---|---|
| `gross` | 17(1) + 17(2) + 17(3), as printed on Form 16 Part B |
| `exempt_allowances` | HRA, LTA, and most 10(14) allowances — **old regime only** |
| `exempt_retirement` | Gratuity, commuted pension, leave encashment, VRS — **both regimes** |
| `professional_tax` | s.16(iii), old regime only, capped at 5,000 |
| `basic_plus_da` | Needed only to cap 80CCD(2) |

Keeping the two exemption fields apart is the point: lumping retirement
exemptions into `exempt_allowances` would silently tax them under the new
regime.

### `house_property` — a list

```json
[{ "kind": "self_occupied", "interest_paid": 240000 },
 { "kind": "let_out", "annual_rent": 360000,
   "municipal_tax_paid": 12000, "interest_paid": 180000 }]
```

`kind` is `self_occupied`, `let_out` or `deemed_let_out`. The engine applies the
30% standard deduction on let-out NAV, the 2,00,000 s.24(b) cap on
self-occupied, and the s.71(3A) set-off limit.

### `business`

```json
{ "nature_of_business_code": "16019",
  "presumptive_44ada": { "gross_receipts_digital": 3800000,
                         "gross_receipts_cash": 0,
                         "declared_income": 1900000 } }
```

Omit `declared_income` and the engine uses the statutory minimum. Set it *below*
that minimum and the engine refuses to compute — declaring less is legal but
pulls in books of account and a s.44AB audit, which is out of scope. See
`presumptive-44ada.md`. `presumptive_44ad` takes `turnover_digital` /
`turnover_cash` instead. `regular_books_profit` is a plain figure for anyone not
using presumptive taxation.

### `capital_gains`

| Key | Bucket |
|---|---|
| `stcg_111a` | STT-paid equity/equity MF held ≤ 12 months → 20% |
| `stcg_slab` | Debt MF post-Apr-2023 (s.50AA), unlisted short-term → slab rate |
| `ltcg_112a` | STT-paid equity/equity MF held > 12 months → 12.5% above 1,25,000 |
| `ltcg_112` | Property, gold, unlisted → 12.5%, **enter the unindexed gain** |
| `vda` | Crypto → 30% flat |

Enter **raw totals across all brokers**. The 1,25,000 exemption is applied once,
by the engine — subtracting it yourself double-counts it.

### `other_sources`

`savings_interest` · `deposit_interest` · `dividends` · `family_pension` ·
`winnings` (30% flat) · `other`.

Savings and deposit interest are separate because 80TTA covers only savings
while 80TTB covers both.

### `deductions`

`s80c` · `s80ccd1b` · `s80ccd2_employer_nps` · `s80d` · `s80g` · `s80e` ·
`s80u` · `s80dd` · `s80ddb` · `s80eeb` · `other`.

Enter the amount you have **proof for**, not the amount you are entitled to. The
engine caps what it can and drops what the new regime disallows.

### `foreign_assets` — a list

Each entry needs `asset_type` (`bank_account` · `custodial_account` ·
`equity_debt_interest` · `immovable_property` · `insurance_contract` · `other`),
`country`, `country_code`, `institution`, `account_ref`, `opened_on`,
`peak_value`, `closing_value`, `income_accrued`, and
`income_offered_in_schedule`.

**The reporting period is the calendar year 1 Jan – 31 Dec 2025**, not the
financial year. See `schedule-fa.md` — this is the highest-penalty block in the
file.

### `taxes_paid`

```json
{ "tds": 96000, "tcs": 0,
  "advance_tax":         [{ "date": "2025-12-14", "amount": 40000 }],
  "self_assessment_tax": [{ "date": "2026-07-24", "amount": 15000 }] }
```

Dates matter: they stop the 234A/234B clock at the point of payment. An advance
tax entry dated after 31 Mar 2026 is a validation error — that is
self-assessment tax.

### `source_totals` — the safety net

```json
{ "form16_gross_salary": 1450000, "form16_tds": 90000,
  "form26as_tds": 96000, "ais_interest": 31200,
  "ais_dividends": 4100, "broker_ltcg_112a": 88000 }
```

Copy these **exactly as printed** on the documents. The validator compares them
against what you transcribed and **blocks computation on a mismatch above ±10**.
This is the only mechanical guard against a transposed digit, and skipping it
only warns — which is worse, because the engine will then compute a confident
wrong answer.

### `relief_89` and `notes`

`relief_89` is a top-level number, transcribed from your Form 10E — which must
be e-filed **before** the return. `notes` is free text for your own reminders.

## What never goes in this file

PAN, Aadhaar, bank account numbers, portal passwords. None of them are needed to
compute anything, and this is the file most likely to be pasted into a chat or
committed by accident. The validator errors on a PAN pattern and warns on an
Aadhaar-shaped number.
