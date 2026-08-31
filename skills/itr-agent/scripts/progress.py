#!/usr/bin/env python3
"""progress - the shared filing state that the status page reads.

One JSON file, `work/progress.json`, written atomically so a reader never sees
half a file. Every script and the agent write to it; `status_server.py` polls it.

The stage list is deliberately phrased for someone who does not file returns for
a living. "Cross-checking your documents" tells them what is happening;
"validate_income" does not.

    python3 progress.py --workspace itr-workspace start   compute
    python3 progress.py --workspace itr-workspace done     compute --detail "New regime saves 1,45,430"
    python3 progress.py --workspace itr-workspace wait     handover --title "Pay 12,340" --detail "Challan 280, minor head 300"
    python3 progress.py --workspace itr-workspace block     validate --detail "TDS is 8,000 off 26AS"
    python3 progress.py --workspace itr-workspace set --form ITR-3 --regime new --refund 105410
    python3 progress.py --workspace itr-workspace note "Fresh AIS downloaded"
    python3 progress.py --workspace itr-workspace show
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = 1
MAX_EVENTS = 60

# (id, what the user sees, one line of plain English)
STAGES: list[tuple[str, str, str]] = [
    ("setup",     "Getting set up",             "Checking the tax engine's own maths before trusting it with yours."),
    ("documents", "Collecting your documents",  "Form 16, AIS, 26AS, bank and broker statements."),
    ("extract",   "Reading your documents",     "Copying every figure across exactly as printed."),
    ("validate",  "Cross-checking the figures", "Comparing what was copied against the totals on your documents."),
    ("deductions","Looking for deductions",     "Making sure nothing you are entitled to is left behind."),
    ("compute",   "Calculating your tax",       "Both regimes, so the cheaper one can be picked on evidence."),
    ("form",      "Choosing your ITR form",     "Which form you qualify for, and the deadline that comes with it."),
    ("reconcile", "Matching the department's records", "Every entry the department already knows about is accounted for."),
    ("pack",      "Preparing your filing pack", "A field-by-field map of what goes where on the portal."),
    ("portal",    "Filling in the portal",      "Entering the return on the income-tax website."),
    ("check",     "Checking the portal agrees", "The portal's total must match ours to the rupee."),
    ("handover",  "Your turn",                  "Pay, submit and e-verify - the three steps only you can do."),
    ("filed",     "Filed",                      "Return submitted and e-verified."),
]

STAGE_IDS = [s[0] for s in STAGES]

PENDING, ACTIVE, DONE, BLOCKED, YOU = "pending", "active", "done", "blocked", "you"
STATUSES = {PENDING, ACTIVE, DONE, BLOCKED, YOU}


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _blank() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "updated_at": _now(),
        "taxpayer_label": None,
        "assessment_year": "2026-27",
        "itr_form": None,
        "regime": None,
        "headline": {"kind": None, "amount": None},
        "waiting_on_you": None,
        "stages": [
            {"id": i, "label": lbl, "about": about, "status": PENDING,
             "detail": None, "at": None}
            for i, lbl, about in STAGES
        ],
        "blockers": [],
        "events": [],
    }


def path_for(workspace: str | os.PathLike) -> Path:
    return Path(workspace) / "work" / "progress.json"


def load(workspace: str | os.PathLike) -> dict[str, Any]:
    p = path_for(workspace)
    if not p.exists():
        return _blank()
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt or half-written file must never take the dashboard down.
        return _blank()
    if state.get("schema") != SCHEMA:
        return _blank()

    # Reconcile against the current stage list so an upgrade cannot orphan a
    # stage or lose one that was added since the file was written.
    by_id = {s["id"]: s for s in state.get("stages", [])}
    state["stages"] = [
        {**{"id": i, "label": lbl, "about": about, "status": PENDING,
            "detail": None, "at": None},
         **{k: v for k, v in by_id.get(i, {}).items() if k in
            ("status", "detail", "at")}}
        for i, lbl, about in STAGES
    ]
    return state


def save(workspace: str | os.PathLike, state: dict[str, Any]) -> Path:
    """Atomic write - the server polls this file constantly."""
    p = path_for(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return p


def _event(state: dict, text: str) -> None:
    state["events"].insert(0, {"at": _now(), "text": text})
    del state["events"][MAX_EVENTS:]


def _stage(state: dict, stage_id: str) -> dict:
    for s in state["stages"]:
        if s["id"] == stage_id:
            return s
    raise KeyError(
        f"unknown stage {stage_id!r} - expected one of: {', '.join(STAGE_IDS)}"
    )


def set_status(workspace, stage_id: str, status: str, detail: str | None = None,
               title: str | None = None) -> dict:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    state = load(workspace)
    st = _stage(state, stage_id)
    st["status"] = status
    st["at"] = _now()
    if detail is not None:
        st["detail"] = detail

    if status == ACTIVE:
        # Only one stage is ever active, and reaching a later one means the
        # earlier ones happened - even if a script forgot to say so.
        idx = STAGE_IDS.index(stage_id)
        for other in state["stages"]:
            if other["id"] == stage_id:
                continue
            if other["status"] == ACTIVE:
                other["status"] = DONE
            if STAGE_IDS.index(other["id"]) < idx and other["status"] == PENDING:
                other["status"] = DONE
        state["waiting_on_you"] = None
        _event(state, f"Started: {st['label']}")

    elif status == DONE:
        _event(state, f"Finished: {st['label']}" + (f" - {detail}" if detail else ""))
        if state.get("waiting_on_you", {}) and \
                (state["waiting_on_you"] or {}).get("stage") == stage_id:
            state["waiting_on_you"] = None
        state["blockers"] = [b for b in state["blockers"] if b["stage"] != stage_id]

    elif status == BLOCKED:
        state["blockers"] = [b for b in state["blockers"] if b["stage"] != stage_id]
        state["blockers"].append({
            "stage": stage_id, "label": st["label"],
            "detail": detail or "Blocked.", "at": _now(),
        })
        _event(state, f"Blocked: {st['label']}" + (f" - {detail}" if detail else ""))

    elif status == YOU:
        state["waiting_on_you"] = {
            "stage": stage_id,
            "title": title or st["label"],
            "detail": detail or st["about"],
            "since": _now(),
            "acknowledged_at": None,
        }
        _event(state, f"Waiting for you: {title or st['label']}")

    return save(workspace, state) and state


def acknowledge(workspace, stage_id: str) -> dict:
    """The 'I've done that' button on the status page."""
    state = load(workspace)
    w = state.get("waiting_on_you")
    if not w or w.get("stage") != stage_id:
        return state
    w["acknowledged_at"] = _now()
    _event(state, f"You confirmed: {w['title']}")
    save(workspace, state)
    return state


def update_meta(workspace, **fields) -> dict:
    state = load(workspace)
    changed = []
    for key in ("taxpayer_label", "assessment_year", "itr_form", "regime"):
        if fields.get(key) is not None:
            state[key] = fields[key]
            changed.append(f"{key.replace('_', ' ')} {fields[key]}")
    if fields.get("refund") is not None:
        state["headline"] = {"kind": "refund", "amount": float(fields["refund"])}
        changed.append(f"refund {float(fields['refund']):,.0f}")
    if fields.get("payable") is not None:
        state["headline"] = {"kind": "payable", "amount": float(fields["payable"])}
        changed.append(f"payable {float(fields['payable']):,.0f}")
    if changed:
        _event(state, "Updated: " + ", ".join(changed))
    save(workspace, state)
    return state


def note(workspace, text: str) -> dict:
    state = load(workspace)
    _event(state, text)
    save(workspace, state)
    return state


def reset(workspace) -> dict:
    state = _blank()
    _event(state, "Started a new filing session.")
    save(workspace, state)
    return state


def record(workspace: str | os.PathLike | None, stage_id: str, status: str,
           detail: str | None = None, **meta) -> None:
    """Best-effort hook for the other scripts.

    Progress tracking is a convenience. It must never be the reason a tax
    computation fails, so every error here is swallowed deliberately.
    """
    if not workspace:
        return
    try:
        set_status(workspace, stage_id, status, detail)
        if meta:
            update_meta(workspace, **meta)
    except Exception:  # noqa: BLE001 - see docstring
        pass


# --------------------------------------------------------------------------


def _render(state: dict) -> str:
    glyph = {DONE: "[x]", ACTIVE: "[>]", BLOCKED: "[!]", YOU: "[?]", PENDING: "[ ]"}
    L = [f"AY {state['assessment_year']}"
         + (f" · {state['itr_form']}" if state["itr_form"] else "")
         + (f" · {state['regime']} regime" if state["regime"] else "")]
    h = state.get("headline") or {}
    if h.get("kind"):
        L.append(f"{h['kind'].capitalize()}: {h['amount']:,.0f}")
    L.append("")
    for s in state["stages"]:
        line = f"  {glyph[s['status']]} {s['label']}"
        if s.get("detail"):
            line += f"  - {s['detail']}"
        L.append(line)
    if state.get("waiting_on_you"):
        w = state["waiting_on_you"]
        L += ["", f"WAITING FOR YOU: {w['title']}", f"  {w['detail']}"]
    for b in state.get("blockers", []):
        L += ["", f"BLOCKED at {b['label']}: {b['detail']}"]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", default="itr-workspace")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("start", "done", "block"):
        p = sub.add_parser(name)
        p.add_argument("stage", choices=STAGE_IDS)
        p.add_argument("--detail")

    p = sub.add_parser("wait", help="hand control back to the user")
    p.add_argument("stage", choices=STAGE_IDS)
    p.add_argument("--title")
    p.add_argument("--detail")

    p = sub.add_parser("set", help="form, regime, refund or payable")
    p.add_argument("--form")
    p.add_argument("--regime", choices=("new", "old"))
    p.add_argument("--label", dest="taxpayer_label")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--refund", type=float)
    g.add_argument("--payable", type=float)

    p = sub.add_parser("note")
    p.add_argument("text")

    sub.add_parser("reset")
    p = sub.add_parser("show")
    p.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    ws = args.workspace

    try:
        if args.cmd in ("start", "done", "block"):
            status = {"start": ACTIVE, "done": DONE, "block": BLOCKED}[args.cmd]
            set_status(ws, args.stage, status, args.detail)
        elif args.cmd == "wait":
            set_status(ws, args.stage, YOU, args.detail, title=args.title)
        elif args.cmd == "set":
            update_meta(ws, itr_form=args.form, regime=args.regime,
                        taxpayer_label=args.taxpayer_label,
                        refund=args.refund, payable=args.payable)
        elif args.cmd == "note":
            note(ws, args.text)
        elif args.cmd == "reset":
            reset(ws)
    except (KeyError, ValueError) as exc:
        print(f"progress: {exc}", file=sys.stderr)
        return 2

    state = load(ws)
    print(json.dumps(state, indent=2) if getattr(args, "json", False)
          else _render(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
