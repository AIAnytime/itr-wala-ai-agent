# The status page

A filing session runs for hours and, from the outside, most of it looks like
nothing happening. The person whose return it is should not have to read a
terminal to find out where they are.

```bash
python3 <skill>/scripts/status_server.py --workspace itr-workspace
# -> http://127.0.0.1:7391
```

It opens a browser tab. Tell them to leave it open, in one sentence: *"this
shows where we are, it updates on its own, and it'll tell you when I need
something from you."*

## What it answers

Three questions, in this order, because that is the order they matter:

1. **Is it waiting on me?** A large amber card with the specific ask, and an
   "I've done this" button.
2. **Where are we?** Thirteen steps with a progress bar.
3. **What is the number?** The refund or payable figure as soon as one exists —
   marked *not final* while any blocker is open.

Below that: what needs sorting out, the step list, and a short activity feed.

## The states

| State | Page | Use it when |
|---|---|---|
| `start` | Blue, "Working on…" | You begin a step |
| `done` | Green tick | The step finished |
| `block` | Red, "Paused" | You cannot continue until something is resolved |
| `wait` | Amber, "Your turn" | You need the user to do something |

## Recording

Four scripts update themselves when passed `--progress itr-workspace`:
`check_return.py`, `tax_core.py`, `filing_pack.py`, `portal_agent.py`. Mark the
rest by hand:

```bash
P="python3 <skill>/scripts/progress.py --workspace itr-workspace"

$P start documents
$P done  documents --detail "Form 16, AIS and 26AS received"
$P block extract   --detail "Page 2 of the Form 16 is unreadable"
$P wait  handover  --title "Pay 12,340 first" --detail "Challan 280, minor head 300"
$P set   --form ITR-3 --regime new --refund 105410
$P note  "Fresh AIS downloaded - two new entries"
$P show
```

Stages: `setup` `documents` `extract` `validate` `deductions` `compute` `form`
`reconcile` `pack` `portal` `check` `handover` `filed`.

Marking a stage active backfills the earlier ones, so the bar can never go
backwards if a step was missed.

## Writing for the person, not the log

The `--detail` line is the part they actually read.

| Don't | Do |
|---|---|
| `compute complete` | `New regime is cheaper by 1,45,430` |
| `validation failed` | `TDS in your Form 16 is 8,000 less than 26AS` |
| `awaiting user input` | `Pay 12,340 — challan 280, minor head 300` |

Two habits matter more than the rest:

**Use `wait` every time you need them.** Not a line in the terminal they may not
be watching. The amber card states the ask and gives them a button; the
acknowledgement lands in `progress.json`, so check it before asking twice.

**Use `block` rather than going quiet.** A stalled session with no explanation is
the worst possible state for someone who does not know what the tool is doing. A
blocker in one plain sentence is fine — and it marks any figure already on
screen as provisional, so a stale refund number is never mistaken for a settled
one.

## Privacy

The server binds **`127.0.0.1` only**, and there is no flag to change that. The
page shows a name, a salary, a refund and a filing position — it is not
something to expose on a network, however convenient it would be to check from a
phone.

The HTML is one self-contained file: CSS and JS inline, no CDN, no web fonts, no
analytics, no outbound request of any kind. It works with the machine offline,
and a test asserts the page contains no external URL. Request logging is off —
an access log of someone's tax dashboard is just a second copy of the problem.

`progress.json` lives in `work/`, which the workspace `.gitignore` already
blocks. Keep it that way: it holds figures, and it should hold no identifiers.

## If it is not running

Nothing happens. Every script behaves identically, progress writes are
best-effort and swallow their own errors, and the filing is unaffected. The page
is a window onto the work, never part of it.
