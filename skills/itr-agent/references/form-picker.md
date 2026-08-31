# Which ITR form

Work down the list. **The first rule that fires wins** — later rules cannot
promote you back to a simpler form.

## 1. Anything here → out of scope, see a CA

Non-resident or RNOR · F&O or intraday trading (speculative/non-speculative
business income) · books of account with a s.44AB audit · a partnership or
directorship · unlisted equity shares held at any point · agricultural income
above 5,000 · income from outside India that needs a DTAA treaty position.

Foreign **tax credit** (Form 67 / DTAA relief) is also out of scope for the
engine — but a foreign **asset** is not. You can still file ITR-3 with
Schedule FA here; only the credit computation needs a CA.

## 2. Foreign assets or foreign income → ITR-2, or ITR-3 with business income

Schedule FA exists only on ITR-2 and ITR-3. **This is the single most common
reason a "simple" return is not simple** — one overseas brokerage account, one
RSU vest sitting abroad, one foreign bank account left open from a stint
overseas, and ITR-1 and ITR-4 are both off the table no matter how small the
balance. See `schedule-fa.md`.

## 3. Business or professional income → ITR-4 or ITR-3

- **ITR-4 (Sugam)** if *all* of: presumptive under 44AD/44ADA/44AE · total income
  ≤ 50,00,000 · no foreign assets or income · at most one house property · no
  capital losses to carry forward. Small LTCG under s.112A within the 1,25,000
  exemption is tolerated.
- **ITR-3** otherwise, and always when Schedule FA is needed.

**Presumptive income is not lost by moving to ITR-3.** s.44ADA is declared inside
ITR-3's Schedule BP exactly as it would be in ITR-4. Only the form changes — the
50% benefit survives. This trips people up constantly.

## 4. Capital gains, crypto, or more than one house → ITR-2

Any 111A / 112A / 112 gain, any VDA, more than one house property, or a loss to
carry forward.

## 5. Otherwise → ITR-1 (Sahaj)

Only if all of: resident and ordinarily resident · total income ≤ 50,00,000 ·
salary, one house property, and other sources only · agricultural income ≤ 5,000
· no capital gains beyond LTCG u/s 112A within the exemption · no foreign assets
· not a director, no unlisted shares.

## Deadlines follow the form

| Form | Due date |
|---|---|
| ITR-1, ITR-2 | 31 Jul 2026 |
| ITR-3, ITR-4 (no s.44AB audit) | 31 Aug 2026 |
| Audit cases | 31 Oct 2026 |

Set `meta.due_date` accordingly and **recompute** — 234A interest and the 234F
fee both hang off it. Re-verify the date on the portal; CBDT moves it.

## Two things worth saying out loud

**Filing a simpler form than you qualify for is a defective return** under
s.139(9), not a shortcut. The department issues a notice and you re-file.

**Form 10-IEA** is required to elect the old regime *when you have business
income*, and it must be filed **before** the return. With business income the
switch is close to once-in-a-lifetime rather than an annual choice — the engine
warns, but the decision is yours to make deliberately.
