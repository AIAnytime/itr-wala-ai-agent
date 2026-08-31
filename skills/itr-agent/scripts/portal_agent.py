#!/usr/bin/env python3
"""portal_agent - a supervised Playwright session on the e-filing portal.

This is the half of the problem that a filing checklist cannot solve: reading
what the portal already knows about you, and comparing it - to the rupee -
against what the tax engine computed.

Design constraints, in the order they matter:

* **You log in. Not the agent.** The session opens the login page and waits for
  a human. No password is read, stored, typed or passed as an argument, and
  there is no code path that fills a credential field. OTP and CAPTCHA are for
  you to solve; nothing here tries to route around either.
* **Read-only by default.** `--mode read` navigates and captures. Writing to
  form fields requires `--mode assist`, which still refuses the three acts the
  filer must perform personally: Pay, Submit, e-Verify. There is no flag that
  enables them.
* **Every step leaves evidence.** Each action writes a numbered screenshot into
  the artifacts directory, so the session can be audited after the fact.
* **The portal is authoritative about layout, this file is not.** Selectors on
  eportal.incometax.gov.in change between seasons. Every locator lives in
  LOCATORS below with a text-based fallback; when one misses, the agent stops
  and asks rather than clicking something adjacent.

    python3 portal_agent.py open                     # login page, then hand over
    python3 portal_agent.py prefill  --out work/     # capture prefilled figures
    python3 portal_agent.py compare  --pack output/filing-pack.json

Requires: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

PORTAL = "https://eportal.incometax.gov.in/iec/foservices/#/login"
DASHBOARD_HINT = "/dashboard"

# Locators are (role/name) pairs tried in order. Text first, because the portal's
# generated ids churn every season while the visible labels are stable.
LOCATORS: dict[str, list[str]] = {
    "efile_menu": ["text=e-File", "role=link[name='e-File']"],
    "itr_submenu": ["text=Income Tax Returns"],
    "file_return": ["text=File Income Tax Return"],
    "assessment_year": ["text=Assessment Year", "select#assessmentYear"],
    "mode_online": ["text=Online"],
    "status_individual": ["text=Individual"],
    "resume_filing": ["text=Resume Filing"],
    "start_new": ["text=Start New Filing"],
    "prefill_summary": ["text=Let's Get Started", "text=Total Income"],
}

# Field labels the portal shows on its confirmation screens, mapped to the
# engine's line keys. This is the whole point of `compare`.
PORTAL_TO_ENGINE = {
    "Gross Total Income": "gross_total_income",
    "Total Deductions": "chapter_via",
    "Total Income": "total_income",
    "Net Tax Payable": "net_payable",
    "Total Tax Paid": "tds_tcs",
    "Refund": "refund_due",
    "Interest u/s 234A": "interest_234a",
    "Interest u/s 234B": "interest_234b",
    "Interest u/s 234C": "interest_234c",
    "Fee u/s 234F": "fee_234f",
}

TOLERANCE = 10  # s.288B rounding; anything larger is a real disagreement

REFUSED = {
    "pay": "Paying self-assessment tax",
    "submit": "Submitting the return",
    "everify": "e-Verifying the return",
}


class PortalError(Exception):
    pass


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        raise PortalError(
            "Playwright is not installed. Run:\n"
            "    pip install playwright && playwright install chromium"
        )
    from playwright.sync_api import sync_playwright
    return sync_playwright


class Session:
    """A browser on the portal with a human in the driver's seat."""

    def __init__(self, artifacts: Path, headed: bool = True, mode: str = "read"):
        if mode not in ("read", "assist"):
            raise PortalError("mode must be 'read' or 'assist'")
        self.mode = mode
        self.artifacts = artifacts
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.headed = headed
        self._step = 0
        self._pw = None
        self._browser = None
        self.page = None

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "Session":
        sync_playwright = _require_playwright()
        self._pw = sync_playwright().start()
        # Headed always, in practice: the user has to see what is happening and
        # be able to take the keyboard for the login, the OTP and the CAPTCHA.
        self._browser = self._pw.chromium.launch(headless=not self.headed)
        ctx = self._browser.new_context(viewport={"width": 1440, "height": 900})
        self.page = ctx.new_page()
        return self

    def __exit__(self, *exc) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    # -- evidence ----------------------------------------------------------

    def shot(self, label: str) -> Path:
        self._step += 1
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)
        path = self.artifacts / f"{self._step:02d}-{safe}.png"
        self.page.screenshot(path=str(path), full_page=True)
        print(f"  captured {path.name}")
        return path

    # -- navigation --------------------------------------------------------

    def find(self, key: str, timeout: int = 8000):
        """Try each locator for `key`; give up loudly rather than guess."""
        last = None
        for sel in LOCATORS.get(key, [key]):
            try:
                loc = self.page.locator(sel).first
                loc.wait_for(state="visible", timeout=timeout)
                return loc
            except Exception as exc:  # locator missing or ambiguous
                last = exc
        raise PortalError(
            f"Could not find {key!r} on the current page. The portal's layout has "
            f"probably changed for this season.\n"
            f"  Last error: {type(last).__name__}\n"
            f"  Fix the entry for {key!r} in LOCATORS, or drive this step by hand and "
            f"tell the agent what you see. Do NOT let it click something nearby."
        )

    def open_login(self) -> None:
        print(f"Opening {PORTAL}")
        self.page.goto(PORTAL, wait_until="domcontentloaded")
        self.shot("login-page")
        print(
            "\n  The browser is yours. Log in with your PAN and password, and solve the\n"
            "  CAPTCHA/OTP yourself. This tool never reads, stores or types a credential.\n"
        )

    def await_dashboard(self, timeout_s: int = 600) -> None:
        """Block until the human has logged in. Nothing here hurries that along."""
        print(f"  Waiting up to {timeout_s // 60} minutes for the dashboard...")
        try:
            self.page.wait_for_url(f"**{DASHBOARD_HINT}**", timeout=timeout_s * 1000)
        except Exception:
            raise PortalError(
                "Did not reach the dashboard. If you are logged in but the URL differs, "
                "the portal changed its post-login route - update DASHBOARD_HINT."
            )
        print("  Logged in.")
        self.shot("dashboard")

    def to_filing(self) -> None:
        for key in ("efile_menu", "itr_submenu", "file_return"):
            self.find(key).click()
            self.page.wait_for_load_state("networkidle")
        self.shot("file-return-entry")

    # -- reading -----------------------------------------------------------

    def scrape_amounts(self) -> dict[str, float]:
        """Pull every label->amount pair the portal is currently showing.

        Deliberately dumb: it reads visible text and matches known labels. No
        identity fields are collected - only figures, which is all `compare`
        needs and all that should ever be written to disk.
        """
        text = self.page.inner_text("body")
        found: dict[str, float] = {}
        for line in text.splitlines():
            line = line.strip()
            for label in PORTAL_TO_ENGINE:
                if line.startswith(label):
                    digits = (
                        line[len(label):]
                        .replace(",", "").replace("₹", "").replace("Rs.", "")
                        .strip()
                    )
                    token = digits.split()[0] if digits.split() else ""
                    try:
                        found[label] = float(token)
                    except ValueError:
                        continue
        return found

    # -- writing (assist mode only) ---------------------------------------

    def fill(self, selector: str, value: str, label: str) -> None:
        if self.mode != "assist":
            raise PortalError(
                f"Refusing to type into {label!r}: the session is in read mode. "
                "Re-run with --mode assist if you want the agent to fill fields."
            )
        loc = self.page.locator(selector).first
        loc.wait_for(state="visible", timeout=8000)
        existing = (loc.input_value() or "").strip()
        if existing and existing != value:
            raise PortalError(
                f"{label}: the portal already has {existing!r} prefilled and the return "
                f"says {value!r}. Prefilled data is not overwritten silently - resolve "
                f"the difference with the user first."
            )
        loc.fill(value)
        print(f"  filled {label} = {value}")

    def refuse(self, act: str) -> None:
        raise PortalError(
            f"{REFUSED[act]} is yours to do, not the agent's. Everything is prepared; "
            "click it yourself once the figures match."
        )


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_open(args) -> int:
    with Session(Path(args.artifacts), mode=args.mode) as s:
        s.open_login()
        s.await_dashboard()
        s.to_filing()
        print("\nAt the filing entry point. Continue in the browser.")
        input("Press Enter here when you want to close the session... ")
    return 0


def cmd_prefill(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with Session(Path(args.artifacts), mode="read") as s:
        s.open_login()
        s.await_dashboard()
        s.to_filing()
        print("\n  Navigate to the prefilled summary in the browser, then come back.")
        input("  Press Enter once the summary is on screen... ")
        s.shot("prefill-summary")
        amounts = s.scrape_amounts()

    path = out / "portal-prefill.json"
    path.write_text(json.dumps({
        "captured_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "source": "eportal.incometax.gov.in prefilled summary",
        "amounts": amounts,
    }, indent=2), encoding="utf-8")
    print(f"\nWrote {path} with {len(amounts)} figure(s).")
    if not amounts:
        print(
            "  Nothing matched. The portal's labels may have changed - update "
            "PORTAL_TO_ENGINE, or read the figures off the screenshot by hand."
        )
    return 0


def cmd_compare(args) -> int:
    """The step that decides whether it is safe to submit."""
    pack = json.loads(Path(args.pack).read_text(encoding="utf-8"))
    engine = pack["regimes"][pack["recommended_regime"]]["lines"]

    if args.prefill:
        portal = json.loads(Path(args.prefill).read_text(encoding="utf-8"))["amounts"]
    else:
        with Session(Path(args.artifacts), mode="read") as s:
            s.open_login()
            s.await_dashboard()
            print("\n  Open the return's Preview / Confirmation page, then come back.")
            input("  Press Enter once the tax summary is on screen... ")
            s.shot("portal-preview")
            portal = s.scrape_amounts()

    rows, mismatches = [], 0
    for label, key in PORTAL_TO_ENGINE.items():
        if label not in portal:
            continue
        theirs = portal[label]
        ours = engine.get(key, 0.0)
        delta = theirs - ours
        flag = "" if abs(delta) <= TOLERANCE else "  <-- MISMATCH"
        if flag:
            mismatches += 1
        rows.append(f"{label:<28}{ours:>14,.0f}{theirs:>14,.0f}{delta:>12,.0f}{flag}")

    print(f"\n{'':<28}{'ENGINE':>14}{'PORTAL':>14}{'DELTA':>12}")
    print("-" * 80)
    print("\n".join(rows) if rows else "  (no comparable figures found)")
    print("-" * 80)

    if not rows:
        print("Nothing to compare. Read the figures off the screenshot manually.")
        return 1
    if mismatches:
        print(
            f"\n{mismatches} figure(s) disagree by more than {TOLERANCE}.\n"
            "Do NOT submit. Either the extraction missed something the portal knows "
            "about (check AIS), or the engine was fed a wrong number. Reconcile first - "
            "never split the difference."
        )
        return 1
    print(
        f"\nAll {len(rows)} figures agree within {TOLERANCE} (s.288B rounding).\n"
        "Safe to proceed. Paying, submitting and e-verifying are yours to click."
    )
    return 0


def cmd_refuse(args) -> int:
    with Session(Path(args.artifacts), mode=args.mode) as s:
        s.refuse(args.act)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--artifacts", default="artifacts",
                    help="where numbered screenshots are written")
    ap.add_argument("--mode", choices=("read", "assist"), default="read",
                    help="'read' never types into the page; 'assist' may fill fields "
                         "but still refuses pay/submit/e-verify")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("open", help="open the login page and navigate to filing")

    p = sub.add_parser("prefill", help="capture the portal's prefilled figures")
    p.add_argument("--out", default="work", help="directory for portal-prefill.json")

    p = sub.add_parser("compare", help="engine vs portal, to the rupee")
    p.add_argument("--pack", required=True, help="computation.json from tax_core")
    p.add_argument("--prefill", help="reuse a saved portal-prefill.json instead of "
                                     "opening a browser")

    args = ap.parse_args(argv)
    try:
        return {"open": cmd_open, "prefill": cmd_prefill, "compare": cmd_compare}[args.cmd](args)
    except PortalError as exc:
        print(f"\nportal_agent: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing was submitted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
