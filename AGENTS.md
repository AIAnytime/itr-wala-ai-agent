# For coding agents working in this repo

The skill itself lives in `skills/itr-agent/SKILL.md`. **If you are here to help
someone file a return, read that file, not this one.** This file is about
changing the repo.

## The one invariant

**The model never does tax arithmetic.** Every rupee comes out of
`scripts/tax_core.py`. If you find yourself computing a figure to explain, to
check, or to fill a gap — stop and run the engine instead. This is the property
the whole design exists to protect, and it is easy to erode one helpful
paragraph at a time.

## Layout

```
skills/itr-agent/
  SKILL.md               the workflow the agent follows
  references/*.md        tax law, in prose, for narration only
  scripts/tax_core.py    the tax engine - stdlib only, no network
  scripts/check_return.py    input validator, closed whitelist
  scripts/filing_pack.py     portal field map
  scripts/portal_agent.py    supervised Playwright session
  scripts/progress.py        filing state the status page reads
  scripts/status_server.py   localhost-only status page
  scripts/test_*.py      102 tests
  assets/example-return.json fictional figures, must always validate
```

## Rules for changes

**Tax rules change in two places or none.** A rate lives in `tax_core.py` (the
implementation) and `references/rates-ay2026-27.md` (the narration). Change one
without the other and the agent will confidently explain a figure the engine did
not produce.

**Every rule change needs a test that states the statute.** Assert what the
section says, not what the code currently returns — write the case from the Act
and let it fail first. Tests written by reading the implementation only pin in
whatever bug is already there.

**`scripts/` stays standard library.** No requests, no pandas, no pydantic. CI
enforces it. The guarantee is that the tax math runs offline on a fresh machine
with nothing installed, and it is worth more than any convenience a dependency
buys. `portal_agent.py` is the sole exception — Playwright, imported lazily,
documented as an extra.

**The validator's whitelist stays closed.** Adding a field means adding it to
`SCHEMA` in `check_return.py`. Never loosen it to accept unknown keys: a silently
ignored typo costs a real person a real deduction.

**The status page stays local and optional.** `status_server.py` binds
`127.0.0.1` by design — do not add a host flag, a tunnel, or a "share this
link" feature; the page shows someone's salary and refund. Keep it dependency-
free and self-contained (a test asserts the HTML contains no outbound URL), and
keep every progress write best-effort: a failed status update must never be the
reason a tax computation fails.

**Never widen what the agent may do on the portal.** No credential handling, no
OTP or CAPTCHA path, no pay, no submit, no e-verify. These are not
configuration. A PR that adds a flag for any of them will be closed.

## Before you push

```bash
python3 skills/itr-agent/scripts/test_tax_core.py
python3 skills/itr-agent/scripts/test_check_return.py
python3 skills/itr-agent/scripts/test_progress.py
python3 skills/itr-agent/scripts/check_return.py skills/itr-agent/assets/example-return.json
python3 skills/itr-agent/scripts/tax_core.py    skills/itr-agent/assets/example-return.json
```

All five must pass. The example is fictional but it is a real regression test —
it exercises presumptive income, Schedule FA and capital gains together.

## Never commit

Real tax documents, real figures, screenshots, `.env`, a PAN, an Aadhaar, an
account number. `.gitignore` blocks the obvious paths, but it cannot read a
diff. Check yours.
