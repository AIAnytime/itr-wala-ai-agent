# Capital gains — getting the bucket right

Misclassification, not arithmetic, is what goes wrong here. The engine applies
whatever rate the bucket implies, so the bucket *is* the answer.

## The buckets

| `return.json` key | What belongs there | Rate |
|---|---|---|
| `stcg_111a` | STT-paid listed equity and equity MF, held **≤ 12 months** | 20% |
| `ltcg_112a` | The same, held **> 12 months** | 12.5% above 1,25,000 |
| `stcg_slab` | Debt/specified MF bought on or after 1 Apr 2023 (s.50AA); unlisted and property held short-term; **foreign shares ≤ 24 months** | slab |
| `ltcg_112` | Property, gold, unlisted shares, **foreign shares > 24 months** | 12.5%, unindexed |
| `vda` | Crypto and other VDAs | 30% flat |

## Holding periods

- Listed equity, equity MF, listed bonds: **12 months**.
- Everything else — property, gold, unlisted shares, foreign shares: **24
  months**.
- Debt and specified MF units bought on or after 1 Apr 2023: **always
  short-term**, whatever the holding period (s.50AA).

## Three misclassifications that cost real money

**Foreign shares are not 112A.** No STT was paid on a Nasdaq trade, so it cannot
be 111A or 112A. Under 24 months it is `stcg_slab`; over, it is `ltcg_112` at
12.5%. Putting it in `ltcg_112a` claims a 1,25,000 exemption you do not have.
This is the most common error in a return with an overseas brokerage account.

**Post-Apr-2023 debt funds are never long-term.** s.50AA removed the option.
They go in `stcg_slab` regardless of how long you held them.

**Crypto is not a capital gain in the normal sense.** s.115BBH: 30% flat, cost of
acquisition only — no expenses, no set-off against anything, no carry-forward, no
basic-exemption absorption, no 87A. A loss on one coin cannot offset a gain on
another.

## The 1,25,000 exemption

One allowance for the financial year, **aggregated across every broker and every
scrip**. Enter raw totals in `return.json`; the engine subtracts it once.

It is a **tax-stage threshold, not an income exclusion**. The full gain enters
total income — which is why it counts toward the 50 lakh surcharge test and why
house-property loss sets off against the full gain, not the post-exemption
figure.

## Grandfathering, 31 Jan 2018

For equity bought before 1 Feb 2018, the cost of acquisition is the **higher of**
actual cost and the fair market value on 31 Jan 2018 — but that FMV substitute is
capped at the sale price, so grandfathering can reduce a gain to nil but never
creates a loss.

Broker Tax P&L statements apply this already. Use their figure. Recomputing it
from raw trades is how you introduce an error the department will not have.

## Schedule 112A is scrip-wise

The portal wants each holding separately: ISIN, name, quantity, sale
consideration, cost of acquisition, and the 31-Jan-2018 FMV where applicable.
The engine only needs the total, but the portal needs the detail — export it from
your broker rather than typing it. This is the longest data-entry task in a
return with equity, and it is pure transcription.

## Set-off and carry-forward

- Short-term losses set off against **both** short- and long-term gains.
- Long-term losses set off against **long-term gains only**.
- Unabsorbed losses carry forward **eight years** — but only if the return is
  filed **by the due date**. A belated return forfeits the carry-forward. That is
  often the single largest cost of filing late, and it does not show up as
  interest or a fee.
- Never against VDA (s.115BBH(2)) or winnings (s.58(4)).

**This tool does not track carried-forward losses (Schedule CFL).** If you have
brought-forward losses from an earlier year, the engine's figure is too high and
it will say so. That part needs the portal's own schedule or a CA.

## The s.112 indexation cap

For **land or buildings acquired on or before 22 July 2024**, tax on that asset is
capped at 20% of the *indexed* gain (2nd proviso to s.112(1)(a)) — a cap on tax,
not an alternative gain figure. Always enter the **unindexed** gain, because that
is what enters total income.

The engine applies 12.5% unindexed and warns. If 20% × indexed works out lower on
your numbers, that asset needs the offline utility or a CA. Do not adjust the
input to fake the result — that breaks total income everywhere else.

## Property sales

Also check: TDS under s.194-IA (1% where consideration ≥ 50 lakh, claimable in
26AS), s.54/54F/54EC exemptions if you reinvested, and stamp-duty value under
s.50C where it exceeds the sale consideration. None of the three is modelled
here.
