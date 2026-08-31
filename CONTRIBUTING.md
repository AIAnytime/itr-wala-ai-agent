# Contributing

## The bar for a tax-rule change

This tool computes numbers people file with. A wrong figure is a notice from CPC,
not a rendering bug. So:

1. **Cite the section.** In the PR description, name the section, sub-section or
   proviso — and the Finance Act that amended it, if it is recent.
2. **Write the test first, from the statute.** Assert what the law says, not what
   the code returns. It should fail before your change and pass after.
3. **Update both places.** The implementation in `scripts/tax_core.py` *and* the
   narration in `references/rates-ay2026-27.md`. They are read by different
   audiences and must not drift.
4. **Say when practitioners disagree.** Several rules here are genuinely
   contested — 87A against 111A tax is the clearest example. Where the courts and
   CBDT differ, the engine takes the safer posture and *warns*, rather than
   picking a side silently. Preserve that pattern.

## What will be declined

- Anything that lets the agent handle credentials, solve an OTP or CAPTCHA, pay,
  submit, or e-verify. Not a flag, not an opt-in, not "for testing".
- Third-party dependencies in `scripts/` other than Playwright in
  `portal_agent.py`.
- Loosening the validator to accept unknown keys.
- Widening scope — non-resident, audit cases, F&O — without the tests and
  references to support it. Saying "out of scope, see a CA" is a feature.

## Reporting a wrong number

Open an issue with a **minimal `return.json`** using fictional figures, what the
engine produced, what you expected, and the section that says so. Never paste
real financial data, a PAN, or an Aadhaar into an issue — synthesise a case that
reproduces it.

If the portal and the engine disagreed on a real return, that is the most
valuable bug report there is. Redact everything and describe the shape.

## Selectors

`LOCATORS` in `portal_agent.py` goes stale every season, because the portal is
re-skinned and its element ids are generated. Fixes there are welcome and easy to
review. Prefer visible text over ids, and always leave the "stop and ask"
behaviour intact — a misfired click on a tax portal can discard a draft.

## Style

Match what is there. Standard library, `Decimal` for money, no `float`
arithmetic on rupees, comments that explain *why* a rule exists rather than
restating the code.
