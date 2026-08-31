# Presumptive taxation for freelancers — s.44ADA

For independent professionals: software and IT consultants, designers, doctors,
lawyers, architects, accountants, technical writers, interior decorators.

## The deal

Declare **50% of gross receipts** as income and you are done — no books of
account, no expense records, no audit, no depreciation schedule. The other 50% is
deemed to be your costs, whether you actually spent it or not.

**Ceiling:** ₹75,00,000 of gross receipts, provided **cash receipts stay at or
under 5%** of the total. Above 5% cash, the ceiling drops to ₹50,00,000. This is
why `return.json` splits `gross_receipts_digital` from `gross_receipts_cash` —
it is not bookkeeping detail, it moves your ceiling by 25 lakh.

## Declaring less than 50%

Legal, but it costs you the whole benefit: you must maintain books under s.44AA
**and** get a tax audit under s.44AB. `tax_core.py` refuses to compute a
sub-50% figure rather than produce a number that quietly implies an audit
obligation you may not know you have. If your actual margin really is under 50%,
that is a genuine reason to hire a CA — not a reason to override the engine.

## Receipts, not invoices

Gross receipts are what **actually landed in the year**, on a cash basis. An
invoice raised in March 2026 and paid in April 2026 belongs to next year's
return. This is the most common reconciliation gap against Form 26AS, because
your client deducted TDS when they *paid*, and their timing may not match your
invoice register.

Receipts are gross of TDS. If a client paid ₹90,000 after deducting ₹10,000, your
receipt is **₹1,00,000** — and the ₹10,000 is a tax credit you claim separately.
Netting it off understates income and overstates nothing.

Include: professional fees, retainers, consulting income, foreign remittances for
services (converted at the rate on the receipt date). Exclude: reimbursements
billed at cost, GST collected, capital receipts, interest income (that is
`other_sources`).

## Advance tax — one installment

Presumptive filers escape the four-installment schedule and owe **100% by
15 March 2026** instead. Miss that and s.234C bites for one month; miss it badly
and s.234B runs from 1 April. The engine models both.

## What you still have to fill in

Presumptive does not mean the return is empty:

- **Nature of business code** — mandatory in Schedule BP. `16019` (other
  professional services) and `14005` (software development) cover most technical
  freelancers. Pick from the portal's list; the engine warns if it is missing.
- **Part A-BS, "no account case"** — sundry debtors, sundry creditors,
  stock-in-trade and cash balance as at 31 Mar 2026. Mandatory even under
  presumptive. Most freelancers have debtors (invoices raised but unpaid) and
  near-zero of the rest, but the fields must be filled, not skipped.

## Which form

**ITR-4** if presumptive is your only complication and total income is under
50 lakh. **ITR-3** the moment you have foreign assets, capital losses to carry
forward, more than one house property, or income above 50 lakh.

Moving to ITR-3 **does not cost you the 50% presumption** — s.44ADA is declared
in ITR-3's Schedule BP exactly as it would be in ITR-4. Only the form changes.
People give up presumptive taxation over this misunderstanding every year.

## Regime choice, once

With business income, electing the old regime requires **Form 10-IEA filed before
the return**, and the switch is effectively **once in a lifetime** — not the
annual toggle a salaried filer gets. Opt out of the new regime, come back, and
you cannot leave again. Run the engine on both regimes and treat the decision as
structural, not tactical.

## The 44ADA / 44AD confusion

s.44ADA is for **professions** at 50%. s.44AD is for **businesses** at 6% of
digital turnover and 8% of cash turnover, with a ₹3,00,00,000 ceiling. A
freelance developer selling their own time is 44ADA. The same person reselling
hardware is 44AD. If you genuinely do both, declare both — the validator warns so
you confirm it was deliberate.
