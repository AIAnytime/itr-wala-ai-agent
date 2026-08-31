#!/usr/bin/env python3
"""Tests for progress tracking and the status server.

The dashboard is a convenience, so the tests that matter most are the ones
proving it can never break a filing: a corrupt file must not crash a reader,
and `record()` must swallow everything.

    python3 test_progress.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import progress  # noqa: E402
import status_server  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name) / "itr-workspace"

    def tearDown(self):
        self._tmp.cleanup()

    def stage(self, state, sid):
        return next(s for s in state["stages"] if s["id"] == sid)


class TestState(Base):
    def test_missing_file_reads_as_a_fresh_start(self):
        state = progress.load(self.ws)
        self.assertEqual(len(state["stages"]), len(progress.STAGES))
        self.assertTrue(all(s["status"] == progress.PENDING for s in state["stages"]))
        self.assertIsNone(state["waiting_on_you"])

    def test_start_marks_active_and_backfills_earlier_stages(self):
        """Reaching a later stage means the earlier ones happened, even if a
        script forgot to say so - the bar must never lie backwards."""
        progress.set_status(self.ws, "compute", progress.ACTIVE)
        state = progress.load(self.ws)
        self.assertEqual(self.stage(state, "compute")["status"], progress.ACTIVE)
        self.assertEqual(self.stage(state, "extract")["status"], progress.DONE)
        self.assertEqual(self.stage(state, "portal")["status"], progress.PENDING)

    def test_only_one_stage_is_ever_active(self):
        progress.set_status(self.ws, "extract", progress.ACTIVE)
        progress.set_status(self.ws, "compute", progress.ACTIVE)
        state = progress.load(self.ws)
        active = [s for s in state["stages"] if s["status"] == progress.ACTIVE]
        self.assertEqual([s["id"] for s in active], ["compute"])

    def test_blocking_records_a_blocker_and_done_clears_it(self):
        progress.set_status(self.ws, "validate", progress.BLOCKED, "TDS is 8,000 off")
        state = progress.load(self.ws)
        self.assertEqual(len(state["blockers"]), 1)
        self.assertIn("8,000", state["blockers"][0]["detail"])

        progress.set_status(self.ws, "validate", progress.DONE)
        self.assertEqual(progress.load(self.ws)["blockers"], [])

    def test_blocking_twice_does_not_duplicate(self):
        progress.set_status(self.ws, "validate", progress.BLOCKED, "one")
        progress.set_status(self.ws, "validate", progress.BLOCKED, "two")
        state = progress.load(self.ws)
        self.assertEqual(len(state["blockers"]), 1)
        self.assertEqual(state["blockers"][0]["detail"], "two")

    def test_waiting_on_you_is_surfaced_then_cleared(self):
        progress.set_status(self.ws, "handover", progress.YOU,
                            detail="Challan 280", title="Pay 12,340")
        w = progress.load(self.ws)["waiting_on_you"]
        self.assertEqual(w["title"], "Pay 12,340")
        self.assertIsNone(w["acknowledged_at"])

        progress.set_status(self.ws, "handover", progress.DONE)
        self.assertIsNone(progress.load(self.ws)["waiting_on_you"])

    def test_starting_a_new_stage_clears_a_stale_prompt(self):
        progress.set_status(self.ws, "handover", progress.YOU, title="Pay")
        progress.set_status(self.ws, "portal", progress.ACTIVE)
        self.assertIsNone(progress.load(self.ws)["waiting_on_you"])

    def test_acknowledge_marks_but_does_not_advance(self):
        progress.set_status(self.ws, "handover", progress.YOU, title="Pay")
        progress.acknowledge(self.ws, "handover")
        state = progress.load(self.ws)
        self.assertIsNotNone(state["waiting_on_you"]["acknowledged_at"])
        # Only the agent may advance a stage - a click is a signal, not a fact.
        self.assertNotEqual(self.stage(state, "handover")["status"], progress.DONE)

    def test_acknowledge_ignores_the_wrong_stage(self):
        progress.set_status(self.ws, "handover", progress.YOU, title="Pay")
        progress.acknowledge(self.ws, "compute")
        self.assertIsNone(progress.load(self.ws)["waiting_on_you"]["acknowledged_at"])

    def test_meta_and_headline(self):
        progress.update_meta(self.ws, itr_form="ITR-3", regime="new", refund=105410)
        state = progress.load(self.ws)
        self.assertEqual(state["itr_form"], "ITR-3")
        self.assertEqual(state["headline"], {"kind": "refund", "amount": 105410.0})

        progress.update_meta(self.ws, payable=2400)
        self.assertEqual(progress.load(self.ws)["headline"]["kind"], "payable")

    def test_events_are_capped(self):
        for i in range(progress.MAX_EVENTS + 25):
            progress.note(self.ws, f"event {i}")
        events = progress.load(self.ws)["events"]
        self.assertEqual(len(events), progress.MAX_EVENTS)
        self.assertEqual(events[0]["text"], f"event {progress.MAX_EVENTS + 24}")

    def test_unknown_stage_is_refused(self):
        with self.assertRaises(KeyError):
            progress.set_status(self.ws, "not_a_stage", progress.DONE)

    def test_unknown_status_is_refused(self):
        with self.assertRaises(ValueError):
            progress.set_status(self.ws, "compute", "finished-ish")


class TestResilience(Base):
    """The dashboard must never be the reason anything fails."""

    def test_corrupt_file_reads_as_a_fresh_start(self):
        p = progress.path_for(self.ws)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{ this is not json", encoding="utf-8")
        state = progress.load(self.ws)
        self.assertEqual(len(state["stages"]), len(progress.STAGES))

    def test_old_schema_is_discarded_not_half_read(self):
        p = progress.path_for(self.ws)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"schema": 0, "stages": []}), encoding="utf-8")
        self.assertEqual(len(progress.load(self.ws)["stages"]), len(progress.STAGES))

    def test_a_file_missing_a_stage_is_reconciled(self):
        progress.set_status(self.ws, "compute", progress.DONE)
        p = progress.path_for(self.ws)
        state = json.loads(p.read_text())
        state["stages"] = [s for s in state["stages"] if s["id"] != "portal"]
        p.write_text(json.dumps(state), encoding="utf-8")

        reloaded = progress.load(self.ws)
        self.assertEqual(len(reloaded["stages"]), len(progress.STAGES))
        self.assertEqual(self.stage(reloaded, "portal")["status"], progress.PENDING)
        self.assertEqual(self.stage(reloaded, "compute")["status"], progress.DONE)

    def test_record_swallows_every_error(self):
        progress.record(None, "compute", progress.DONE)               # no workspace
        progress.record(self.ws, "nonsense", progress.DONE)           # bad stage
        progress.record(self.ws, "compute", "nonsense")               # bad status
        progress.record("/proc/nope/nowhere", "compute", progress.DONE)  # unwritable
        # Reaching here without an exception is the assertion.

    def test_writes_are_atomic(self):
        """A reader must never catch a half-written file."""
        progress.set_status(self.ws, "compute", progress.DONE)
        stray = list(progress.path_for(self.ws).parent.glob("*.tmp"))
        self.assertEqual(stray, [], "a temp file was left behind")
        json.loads(progress.path_for(self.ws).read_text())


class TestServer(Base):
    def setUp(self):
        super().setUp()
        progress.set_status(self.ws, "compute", progress.DONE, "New regime wins")
        progress.update_meta(self.ws, itr_form="ITR-3", refund=105410)
        progress.set_status(self.ws, "handover", progress.YOU, title="Submit it")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                         status_server.make_handler(self.ws))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_binds_loopback_only(self):
        self.assertEqual(status_server.HOST, "127.0.0.1")
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")

    def test_page_is_self_contained(self):
        """No CDN, no fonts, no outbound anything - it must work offline."""
        body = urllib.request.urlopen(self.url("/")).read().decode()
        self.assertIn("<title>Your tax return</title>", body)
        for bad in ("http://", "https://", "//cdn", "<script src", "<link "):
            self.assertNotIn(bad, body, f"page reaches outside for {bad!r}")

    def test_api_returns_current_state(self):
        d = json.loads(urllib.request.urlopen(self.url("/api/progress")).read())
        self.assertEqual(d["itr_form"], "ITR-3")
        self.assertEqual(d["headline"]["amount"], 105410.0)
        self.assertEqual(d["waiting_on_you"]["title"], "Submit it")

    def test_ack_endpoint_round_trips(self):
        req = urllib.request.Request(
            self.url("/api/ack"), data=json.dumps({"stage": "handover"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        d = json.loads(urllib.request.urlopen(req).read())
        self.assertIsNotNone(d["waiting_on_you"]["acknowledged_at"])

    def test_bad_ack_body_does_not_kill_the_server(self):
        req = urllib.request.Request(self.url("/api/ack"), data=b"not json",
                                     method="POST")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
        # still serving
        self.assertEqual(urllib.request.urlopen(self.url("/")).status, 200)

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url("/../etc/passwd"))
        self.assertEqual(ctx.exception.code, 404)


class TestStageList(unittest.TestCase):
    def test_ids_are_unique(self):
        self.assertEqual(len(progress.STAGE_IDS), len(set(progress.STAGE_IDS)))

    def test_every_stage_is_written_in_plain_english(self):
        """No snake_case or jargon leaks into what a non-technical user reads."""
        for sid, label, about in progress.STAGES:
            self.assertNotIn("_", label, f"{sid}: label reads like code")
            self.assertTrue(label[0].isupper(), f"{sid}: label not capitalised")
            self.assertTrue(about.endswith("."), f"{sid}: description not a sentence")


if __name__ == "__main__":
    unittest.main(verbosity=2)
