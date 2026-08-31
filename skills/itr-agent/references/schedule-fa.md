# Schedule FA — foreign assets

**The highest-penalty block in the return, and the one most often left blank by
accident.** Read this whole file before filling it.

## Why it is different from everything else

Non-disclosure of a foreign asset is not an income-tax problem. It is a **Black
Money (Undisclosed Foreign Income and Assets) Act, 2015** problem, and the
penalty under s.43 is a **flat ₹10,00,000 per year** — unrelated to the asset's
value, unrelated to whether any tax was due, and applicable even if the asset
earned nothing and you sold nothing. A dormant $400 brokerage account attracts
the same penalty as a $4,000,000 one.

There is a small-account carve-out for bank accounts whose aggregate balance
stayed under ₹5,00,000 all year, but it does not extend to custodial accounts,
shares, or property. Do not rely on it without checking the current text.

## Two traps that catch almost everyone

**1. The period is the calendar year, not the financial year.** Schedule FA
reports **1 January 2025 – 31 December 2025**. Every other schedule in the
return reports 1 Apr 2025 – 31 Mar 2026. Pulling peak and closing balances off a
financial-year statement produces confidently wrong numbers.

**2. It survives having nothing to report.** Held the asset and did nothing all
year? Still disclosed. Closed it in March 2025? Still disclosed, because you
held it during the calendar year. Sold at a loss? Still disclosed. The
obligation is on *holding*, not on income.

## What triggers it

Anything held **outside India** at any point during the calendar year:

- A foreign bank account — including one left open from a stint abroad
- A brokerage or custodial account (Interactive Brokers, Schwab, Vested,
  IndMoney's US arm, and so on)
- **RSUs or ESOPs of a foreign parent**, vested or unvested, held abroad
- Foreign equity, debt, mutual funds, or ETFs held directly
- Immovable property, a life-insurance or annuity contract with cash value
- Signing authority over any foreign account, **even one you do not own**
- A beneficial interest in a foreign trust or entity

Crypto on an offshore exchange is contested ground. Treat it as reportable and
say why in your notes rather than deciding it away.

**Directly-held US stocks bought through an Indian broker's global arm still
count** — the custody is abroad. "I bought it on an Indian app" is not the test.

## Per asset, you will need

| Field | Note |
|---|---|
| Asset type | bank / custodial / equity & debt / property / insurance / other |
| Country and its ITD code | The portal uses its own numeric code list, not ISO |
| Institution name and full address | As on the statement |
| Account or reference number | Kept out of `return.json` — see below |
| Date opened / acquired | Not the date of the first trade |
| **Peak value** during the calendar year | The number people guess at. Don't. |
| **Closing value** as at 31 Dec 2025 | |
| Gross income credited (interest, dividend, sale proceeds) | |
| Where that income is offered in this return | Cross-referenced by the portal |

Values are converted at the **SBI TT buying rate** on the relevant date — the
rate for the last day of the month preceding the transaction for income, and the
prescribed date for balances. Get this from the bank's published card, not from
Google's mid-market rate; they differ by enough to matter.

## Peak value is not an estimate

For a bank account it is the highest closing balance on any day in the calendar
year. For a custodial account it is the highest total portfolio value. Most
brokers will export it; if yours will not, take month-end statements and use the
highest, and record that you did so in your extraction notes. **The engine will
not accept a closing value above the peak** — that combination is arithmetically
impossible and means one of the two was misread.

## Where the income also has to go

Schedule FA is a **disclosure** schedule. It does not tax anything. The income it
describes must *also* appear in the income schedules:

- Foreign dividends → `other_sources.dividends` (taxed at slab rates; the US
  withholds 25% at source)
- Foreign interest → `other_sources.deposit_interest`
- Sale of foreign shares → capital gains. **Foreign equity is not 111A/112A** —
  no STT was paid. It is `stcg_slab` if held ≤ 24 months, `ltcg_112` at 12.5% if
  held longer.

That last point is the most expensive misclassification in this file. Putting
foreign shares in the `ltcg_112a` bucket claims a 1,25,000 exemption you are not
entitled to.

## If foreign tax was withheld

You need **Form 67** for a foreign tax credit under s.90/91, and it must be filed
**before** the return. This engine does not compute FTC — the credit
interacts with treaty rates and per-country limitation in ways worth paying a CA
for. Everything else in the return can still be computed here; only the credit
is carved out.

## Privacy

Account numbers do not affect any computation. Keep `account_ref` as a stable
pseudonym (`BROKER-1`, `BANK-SG-1`) in `return.json` and the filing pack, and
type the real number straight into the portal yourself. The filing pack is the
file most likely to be shared with a CA or pasted into a chat.

## Sources

Black Money Act 2015 s.42–43 · ITD Schedule FA instructions for AY 2026-27 ·
CBDT's annual FA compliance advisory. Re-read the current year's instructions:
the field list changes more often than the rest of the form.
