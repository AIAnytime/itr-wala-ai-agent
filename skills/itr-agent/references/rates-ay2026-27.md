# Rate card — FY 2025-26 / AY 2026-27, resident individuals

**Read this to explain a number, never to produce one.** Every rule below is
implemented in `scripts/tax_core.py`. If this file and the engine disagree, the
engine is what the return is built on — open an issue rather than quietly
following the prose.

> **Verify the deadlines before you quote them.** Due dates move by CBDT order
> under s.119 more often than any other figure here. Check
> incometax.gov.in → *Latest Updates* at the start of every session. The dates
> below are the statutory positions, not a promise about this season.

## Due dates

| Filing | Deadline |
|---|---|
| ITR-1 / ITR-2 | 31 Jul 2026 |
| ITR-3 / ITR-4, no s.44AB audit | 31 Aug 2026 |
| Audit cases (s.44AB) | 31 Oct 2026 |
| Transfer pricing (s.92E) | 30 Nov 2026 |
| Belated return, s.139(4) | 31 Dec 2026 |
| Revised return, s.139(5) | 31 Mar 2027 |

The determinant for the non-audit split is **audit liability under s.44AB**, not
income type. A freelancer declaring the full 50% under s.44ADA is not liable to
audit and gets the later date.

**Regime lock on belated returns (s.115BAC(6)).** Once the s.139(1) date passes,
a taxpayer with no business income can no longer elect the old regime — the
portal enforces new-regime-only. The engine detects this, warns, and overrides
its own recommendation even when the old regime computes cheaper.

## New regime (s.115BAC — the default)

| Slab | Rate |
|---|---|
| 0 – 4,00,000 | nil |
| 4,00,001 – 8,00,000 | 5% |
| 8,00,001 – 12,00,000 | 10% |
| 12,00,001 – 16,00,000 | 15% |
| 16,00,001 – 20,00,000 | 20% |
| 20,00,001 – 24,00,000 | 25% |
| above 24,00,000 | 30% |

- Standard deduction on salary/pension: **75,000**.
- **s.87A rebate: up to 60,000.** Finance Act 2025 narrowed it twice over — the
  12,00,000 threshold is tested on **slab-rate income only**, and the rebate
  offsets **slab-rate tax only**. Capital gains therefore neither consume the
  rebate nor benefit from it. Salaried break-even: **12,75,000 gross → nil tax**.
- **Marginal relief** just above the threshold caps total tax at the income above
  12,00,000. At slab income 12,10,000: slab tax 61,500, excess 10,000, relief
  51,500, tax 10,000 + 4% cess = **10,400**. Relief tapers to nothing a little
  above 12,70,000.
- Surviving deduction: **employer NPS, s.80CCD(2), at 14% of Basic+DA** — both
  government and private employers, FY 2025-26.
- Gone: 80C, 80D, 80TTA/TTB, HRA, LTA, s.24(b) on a self-occupied house, and
  house-property loss set-off against other heads.
- **Retirement exemptions survive**: gratuity 10(10), commuted pension 10(10A),
  leave encashment 10(10AA), retrenchment 10(10B), VRS 10(10C). s.115BAC
  withdraws 10(5)/10(13A)/most of 10(14)/10(17)/10(32) — not these. In the schema
  that is `salary.exempt_retirement` (both regimes) versus
  `salary.exempt_allowances` (old regime only).

## Old regime (opt-in)

| Slab | under 60 | 60–79 | 80+ |
|---|---|---|---|
| Nil up to | 2,50,000 | 3,00,000 | 5,00,000 |
| 5% | 2.5L–5L | 3L–5L | — |
| 20% | 5L–10L | 5L–10L | 5L–10L |
| 30% | above 10L | above 10L | above 10L |

- Standard deduction **50,000**; professional tax deductible, capped at 5,000.
- **s.87A: 12,500 if total income ≤ 5,00,000 — a cliff, with no marginal
  relief.** 5,00,010 loses the whole rebate. The test is on the s.288A-rounded
  figure, so 5,00,004 still qualifies.
- The rebate cannot touch **112A** tax (statutory bar, s.112A(6)). The engine
  also withholds it from VDA and winnings tax: there is no statutory bar there,
  but no ruling supports the claim and the utility rejects it, so the engine
  takes the safe posture and says so.
- 87A **against 111A/112 tax is claimable** in the old regime — the Finance Act
  2025 denial amended only the new-regime proviso, and Bombay HC plus ITAT
  rulings back it. But CPC disputes it in processing and CBDT Circular 13/2025
  sides with the department. The engine claims it **and warns you to confirm the
  portal accepts the figure before submitting.**
- Chapter VI-A ceilings the engine enforces: 80C 1,50,000 · 80CCD(1B) 50,000 ·
  80TTA 10,000 (under 60) / 80TTB 50,000 (seniors, savings **and** deposits) ·
  s.24(b) self-occupied 2,00,000 · house-property loss vs other heads 2,00,000
  (s.71(3A)) · 80CCD(2) at **10%** of Basic+DA for private employers.
- **s.24(b) caveat:** the 2,00,000 cap presumes a post-1-Apr-1999 loan for
  purchase or construction completed within five years. Repair or renovation
  loans are capped at **30,000**. The engine applies 2,00,000 and warns —
  confirm the loan's purpose.

## Both regimes

- **Family pension, s.57(iia):** one-third of the pension, capped at 25,000 (new)
  / 15,000 (old).
- **Relief u/s 89(1):** transcribe the figure from your Form 10E into
  `relief_89`. The engine nets it after cess, which also shrinks the 234A/B base.
  **Form 10E must be e-filed before the return** or CPC disallows the relief.
- **Set-off order (s.71):** house-property loss absorbs the other slab heads
  first, then capital gains highest-rate bucket first, against the **full 112A
  gain before its 1,25,000 exemption** — the exemption is a tax-stage threshold,
  not an income exclusion. Never against VDA (s.115BBH(2)) or winnings
  (s.58(4)). Anything unabsorbed carries forward via Schedule CFL, which this
  tool does not track — the engine warns.

## Special rates

| Section | Income | Rate |
|---|---|---|
| s.111A | STCG on STT-paid equity / equity MF (held ≤ 12m) | **20%** |
| s.112A | LTCG on the same, held > 12m | **12.5% above 1,25,000** |
| s.112 | Other LTCG (property, unlisted, gold) | **12.5%, no indexation** |
| s.115BBH | VDA / crypto | **30% flat** |
| s.115BB / s.115BBJ | Lottery, game shows, online games | **30% flat** |

- The 1,25,000 exemption **aggregates across every broker** for the year. Enter
  raw totals; the engine applies the exemption once.
- 31-Jan-2018 grandfathering still applies to 112A cost of acquisition.
- **s.112 trap:** for land or buildings acquired on or before 22-Jul-2024, the
  tax on that asset is capped at 20% of the *indexed* gain (2nd proviso to
  s.112(1)(a)) — a cap on tax, not a different gain. Always feed the
  **unindexed** gain, since that is what enters total income. The engine cannot
  apply the cap and warns; if 20% × indexed gain is lower, that asset needs the
  offline utility or a CA.
- Debt and "specified" mutual-fund units bought on or after 1 Apr 2023 (s.50AA)
  are always short-term at slab rate → the `stcg_slab` bucket.
- A resident may absorb **unused basic exemption** against 111A/112A/112 gains,
  never against VDA or winnings. No single absorption order is always cheapest
  once 87A is in play, so the engine tries every order and keeps the lowest
  lawful tax.
- Chapter VI-A deductions cannot be set against special-rate income at all.

## Surcharge and cess

The 10% and 15% tiers test **total income**. The 25% and 37% tiers test total
income **excluding dividends and 111A/112/112A gains**.

| Test | Surcharge |
|---|---|
| Total income > 50,00,000 | 10% |
| Total income > 1,00,00,000 | 15% |
| Excluding dividends/CG > 2,00,00,000 | 25% |
| Excluding dividends/CG > 5,00,00,000 | 37% — **old regime only; the new regime caps at 25%** |

- **First Schedule clause (e):** if total income crosses 2 crore *only* because
  of dividend or capital-gain income, surcharge is a flat **15% on the entire
  tax** — never 25% on the salary side.
- A **15% ceiling** applies to the surcharge attributable to dividends and
  111A/112/112A tax regardless of total income.
- **Marginal relief** at each threshold: the extra (tax + surcharge) over the tax
  at the threshold cannot exceed the income above it.
- **Health and education cess: 4%** on (tax + surcharge), after rebate, always.

## Interest and fee

- **s.234A** — late filing: 1% simple per month or part on the unpaid balance
  from the day after the due date. A self-assessment payment stops the clock on
  what it discharges, at its own date. Nil if a refund is due.
- **s.234B** — advance-tax default: applies only if assessed tax (liability less
  TDS/TCS) is ≥ 10,000 *and* advance tax paid was under 90% of it. 1% per month
  from 1 Apr 2026.
- **s.234C** — deferment: cumulative 15% / 45% / 75% / 100% by 15 Jun, 15 Sep,
  15 Dec, 15 Mar. Shortfall charged 1% × 3 months for the first three, × 1 month
  for March. Safe harbour: no Q1/Q2 interest if 12% / 36% was paid. Presumptive
  filers under 44AD/44ADA owe **one 100% installment by 15 Mar**.
- **s.207(2):** a resident aged 60+ with no business or professional income owes
  no advance tax at all, so no 234B or 234C. Applied automatically from
  `age_band`.
- **Rule 119A:** the base for 234A/B/C is rounded **down** to a multiple of 100
  before the 1% is applied.
- **s.234F late fee:** 5,000, or **1,000 if total income ≤ 5,00,000**.

## Rounding

s.288A rounds total income to the nearest 10; s.288B rounds tax payable or
refund to the nearest 10. Both half-up. Allow ±10 against the portal at any
intermediate line — a larger gap is a real disagreement, not rounding.

## Sources

incometaxindia.gov.in (Act text and rate tables) · cleartax.in · taxguru.in ·
tax2win.in · CBDT Circular 13/2025. Where practitioner sources conflict with the
bare Act, this file says so rather than picking a side silently.
