# Driving the e-filing portal

`scripts/portal_agent.py` opens a real Chromium on
`eportal.incometax.gov.in`. This file is what the agent follows while that
browser is open.

## The division of labour

| The agent | You |
|---|---|
| Opens the browser and navigates | **Log in** — PAN, password, CAPTCHA, OTP |
| Reads what the portal already knows | |
| Compares portal figures to the engine, to the rupee | |
| Captures a screenshot at every step | |
| Fills fields (only in `--mode assist`) | **Pay** self-assessment tax |
| | **Submit** the return |
| | **e-Verify** it |

There is no flag that makes the agent do the last three. It is not a
configuration choice.

## Credentials

`portal_agent.py` has **no code path that types into a password field.** It does
not read a `.env`, does not take a password argument, and does not store a
session. It opens the login page and waits — up to ten minutes — for the URL to
become the dashboard.

If you are running an agent that has filesystem access to a `.env` holding your
portal password: delete that file. The portal is a two-factor system and the
agent gains nothing from the first factor except the ability to leak it.

Nothing here attempts to solve, bypass, outsource, or automate a CAPTCHA or an
OTP. If that is what you wanted, this is the wrong tool.

## The route through the portal

1. **Login** → dashboard.
2. **e-File → Income Tax Returns → File Income Tax Return.**
3. **Assessment Year 2026-27**, mode **Online**, status **Individual**.
4. If a draft exists, **Resume Filing** — do not start a new one. Starting fresh
   discards a partially completed return that may already hold prefilled data.
5. Choose the ITR form per `form-picker.md`.
6. **Select your schedules.** The portal presents a checklist and gets it wrong
   in one specific way: **Schedule FA is off by default.** If you have foreign
   assets you must enable it by hand. Nothing later in the flow will remind you.
7. **Load prefilled data.** Never overwrite it silently — see below.
8. Fill each schedule from the filing pack, in portal order.
9. **Preview**, and compare against the engine before anything else.
10. Pay if payable → Submit → e-Verify. Yours.

## Prefilled data is evidence, not truth

The portal prefills from AIS, TIS, 26AS and your employer's TDS return. It is
usually right and occasionally very wrong — duplicated entries where a bank
reported to both AIS and 26AS, a sale reported by the broker and the depository,
income belonging to a joint holder.

**When prefilled disagrees with your documents, that is a finding, not a
formatting problem.** Work out which is right before touching either. If the
portal is wrong, correct it *and* file AIS feedback so it does not recur. If your
extraction is wrong, fix `return.json` and recompute — do not patch the number
into the portal and leave the engine disagreeing.

`portal_agent.py` refuses to overwrite a non-empty prefilled field with a
different value, in `assist` mode too. It raises and asks.

## `compare` is the gate

```bash
python3 scripts/filing_pack.py work/return.json --json output/computation.json
python3 scripts/portal_agent.py compare --pack output/computation.json
```

The agent reads the preview screen, matches its labels against the engine's
lines, and prints a delta column. Tolerance is **±10** (s.288B rounding).

Anything larger and it exits non-zero and says do not submit. It is right. A
mismatch means either the extraction missed income the portal knows about — check
AIS first, that is where it usually is — or the engine was fed a wrong figure.
**Never split the difference, and never accept the portal's number just because
it is the portal's.** Find the rupee.

## When a selector breaks

The portal is re-skinned most seasons and its generated element ids change every
release. `LOCATORS` in `portal_agent.py` prefers visible text for that reason,
but text moves too.

When a locator misses, the agent **stops and tells you which one**. It does not
try a nearby element. Fix the entry in `LOCATORS`, or drive that step by hand and
tell the agent what you see. A misfired click on a tax portal is not a
recoverable error — it can discard a draft or file something.

## Evidence

Every step writes a numbered full-page screenshot into `artifacts/`. Keep them.
If CPC raises a query eighteen months from now, a dated capture of what the
portal showed at submission is the difference between reconstructing an argument
and having one.

`artifacts/` is git-ignored by default. Those images contain your name, PAN and
full financial position.

## After submission

- **e-Verify within 30 days** or the return is legally not filed — the filing
  date rolls to the verification date, with 234A interest and the 234F fee
  computed from there. Aadhaar OTP is the fastest route; net banking and demat
  EVC also work.
- Save the acknowledgement number and the ITR-V.
- Expect a s.143(1) intimation within weeks. If it disagrees with the engine,
  the filing pack shows exactly which line to argue.
