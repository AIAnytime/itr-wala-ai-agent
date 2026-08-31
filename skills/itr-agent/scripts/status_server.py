#!/usr/bin/env python3
"""status_server - a plain-English filing dashboard, on your machine only.

Filing a return is a long process with a lot of waiting, and a terminal full of
Python output tells a non-technical person nothing about where they are. This
serves one page that answers three questions: what stage are we at, is it
waiting on me, and what is the number.

    python3 status_server.py --workspace itr-workspace
    -> http://127.0.0.1:7391

**It binds to 127.0.0.1 and nothing else.** The page shows your salary, your
refund and your filing position; it is not something to expose on a network,
and there is no flag to make it listen elsewhere. No CDN, no fonts, no
analytics, no outbound request of any kind - the page is one file with its CSS
and JS inline, so it works with the machine offline.

Stop it with Ctrl-C. Nothing depends on it; the filing works exactly the same
whether it is running or not.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import progress  # noqa: E402

HOST = "127.0.0.1"  # deliberate; see the module docstring
DEFAULT_PORT = 7391

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Your tax return</title>
<style>
  :root{
    --bg:#f6f7f9; --card:#fff; --ink:#16181d; --muted:#666e7a; --line:#e3e6ea;
    --done:#16794a; --done-bg:#e7f4ec;
    --active:#1c5fd0; --active-bg:#e8f0fd;
    --you:#8a5800; --you-bg:#fdf3e0;
    --stop:#a52424; --stop-bg:#fceded;
    --pending:#9aa1ab;
  }
  @media (prefers-color-scheme:dark){
    :root:not([data-theme=light]){
      --bg:#14161a; --card:#1c1f25; --ink:#e9ecf1; --muted:#98a0ac; --line:#2b3038;
      --done:#5fd39b; --done-bg:#16301f;
      --active:#7fb0ff; --active-bg:#152337;
      --you:#f0bd5e; --you-bg:#332614;
      --stop:#ff8f8f; --stop-bg:#341a1a;
      --pending:#6b7280;
    }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
       padding:24px 16px 64px}
  .wrap{max-width:760px;margin:0 auto}
  h1{font-size:22px;margin:0 0 4px}
  .sub{color:var(--muted);font-size:14px;margin-bottom:20px;
       display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .chip{background:var(--card);border:1px solid var(--line);border-radius:999px;
        padding:2px 10px;font-size:12.5px;color:var(--ink)}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--done);
       display:inline-block;margin-right:5px}
  .dot.stale{background:var(--pending)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;
        padding:18px 20px;margin-bottom:14px}
  .card h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;
           color:var(--muted);margin:0 0 10px;font-weight:600}

  .hero{border-left:4px solid var(--active)}
  .hero.you{border-left-color:var(--you);background:var(--you-bg)}
  .hero.stop{border-left-color:var(--stop);background:var(--stop-bg)}
  .hero.filed{border-left-color:var(--done);background:var(--done-bg)}
  .hero .big{font-size:19px;font-weight:600;margin-bottom:6px}
  .hero .why{color:var(--muted);font-size:14.5px}
  .act{margin-top:14px;background:var(--you);color:#fff;border:0;border-radius:8px;
       padding:9px 16px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}
  .act:hover{opacity:.9}
  .act[disabled]{opacity:.55;cursor:default}

  .bar{height:7px;background:var(--line);border-radius:99px;overflow:hidden;margin:10px 0 6px}
  .bar > i{display:block;height:100%;background:var(--done);
           transition:width .4s ease;border-radius:99px}
  .count{font-size:13px;color:var(--muted)}

  .money{font-size:30px;font-weight:650;letter-spacing:-.01em}
  .money.refund{color:var(--done)} .money.payable{color:var(--you)}
  .prov{font-size:13px;color:var(--stop);margin-top:6px}

  ol{list-style:none;margin:0;padding:0}
  li{display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);
     align-items:flex-start}
  li:last-child{border-bottom:0}
  .mark{flex:0 0 22px;height:22px;border-radius:50%;display:grid;place-items:center;
        font-size:12px;font-weight:700;background:var(--line);color:var(--pending);
        margin-top:1px}
  .s-done .mark{background:var(--done-bg);color:var(--done)}
  .s-active .mark{background:var(--active-bg);color:var(--active)}
  .s-you .mark{background:var(--you-bg);color:var(--you)}
  .s-blocked .mark{background:var(--stop-bg);color:var(--stop)}
  .s-pending .name{color:var(--muted)}
  .s-active .name{font-weight:600;color:var(--active)}
  .name{font-size:15px}
  .about{font-size:13.5px;color:var(--muted);margin-top:1px}
  .when{margin-left:auto;font-size:12px;color:var(--muted);white-space:nowrap;
        padding-left:10px}

  .feed{font-size:13.5px;color:var(--muted)}
  .feed div{padding:4px 0;display:flex;gap:10px}
  .feed b{font-weight:400;color:var(--ink)}
  .feed time{flex:0 0 auto;margin-left:auto;font-size:12px;white-space:nowrap}
  .empty{color:var(--muted);font-size:14px}
  footer{text-align:center;color:var(--muted);font-size:12.5px;margin-top:26px;
         line-height:1.7}
  @media(max-width:520px){.when{display:none}.money{font-size:26px}}
</style>
</head>
<body>
<div class="wrap">
  <h1>Your tax return</h1>
  <div class="sub" id="sub"></div>

  <div class="card hero" id="hero">
    <div class="big" id="heroBig">Waiting to start…</div>
    <div class="why" id="heroWhy">Nothing has happened yet.</div>
    <button class="act" id="ack" hidden>I've done this</button>
  </div>

  <div class="card">
    <h2>Progress</h2>
    <div class="bar"><i id="fill" style="width:0%"></i></div>
    <div class="count" id="count">0 of 13 steps</div>
  </div>

  <div class="card" id="moneyCard" hidden>
    <h2 id="moneyLabel">Refund due</h2>
    <div class="money" id="money"></div>
    <div class="prov" id="prov" hidden>Not final — something above still needs sorting out.</div>
  </div>

  <div class="card" id="blockCard" hidden>
    <h2>Needs sorting out first</h2>
    <div id="blockers"></div>
  </div>

  <div class="card">
    <h2>Steps</h2>
    <ol id="steps"></ol>
  </div>

  <div class="card">
    <h2>Recent activity</h2>
    <div class="feed" id="feed"><div class="empty">Nothing yet.</div></div>
  </div>

  <footer>
    <span class="dot" id="live"></span><span id="liveText">connecting…</span><br>
    This page runs on your computer only. Nothing is sent anywhere.
  </footer>
</div>

<script>
const MARK = {done:"✓", active:"›", you:"!", blocked:"✕", pending:""};
let misses = 0, ackedStage = null;

function ago(iso){
  if(!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso)) / 1000);
  if(s < 60) return "just now";
  if(s < 3600) return Math.floor(s/60) + "m ago";
  if(s < 86400) return Math.floor(s/3600) + "h ago";
  return Math.floor(s/86400) + "d ago";
}
function money(n){ return "₹" + Math.round(n).toLocaleString("en-IN"); }

function render(d){
  const sub = [];
  if(d.taxpayer_label) sub.push(d.taxpayer_label);
  sub.push("AY " + d.assessment_year);
  if(d.itr_form) sub.push(d.itr_form);
  if(d.regime) sub.push(d.regime === "new" ? "New regime" : "Old regime");
  document.getElementById("sub").innerHTML =
    sub.map(t => '<span class="chip">' + t + '</span>').join("");

  const done = d.stages.filter(s => s.status === "done").length;
  document.getElementById("fill").style.width =
    Math.round(done / d.stages.length * 100) + "%";
  document.getElementById("count").textContent =
    done + " of " + d.stages.length + " steps done";

  // Hero: the one thing they should read.
  const hero = document.getElementById("hero");
  const big = document.getElementById("heroBig");
  const why = document.getElementById("heroWhy");
  const ack = document.getElementById("ack");
  const blocked = (d.blockers || [])[0];
  const active = d.stages.find(s => s.status === "active");
  const filed = d.stages[d.stages.length - 1].status === "done";
  hero.className = "card hero";
  ack.hidden = true;

  if(d.waiting_on_you){
    hero.classList.add("you");
    big.textContent = "Your turn — " + d.waiting_on_you.title;
    why.textContent = d.waiting_on_you.detail;
    ack.hidden = false;
    const already = d.waiting_on_you.acknowledged_at || ackedStage === d.waiting_on_you.stage;
    ack.disabled = !!already;
    ack.textContent = already ? "Thanks — noted" : "I've done this";
    ack.onclick = () => {
      ackedStage = d.waiting_on_you.stage;
      ack.disabled = true; ack.textContent = "Thanks — noted";
      fetch("/api/ack", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({stage: d.waiting_on_you.stage})}).then(tick);
    };
  } else if(blocked){
    hero.classList.add("stop");
    big.textContent = "Paused — " + blocked.label;
    why.textContent = blocked.detail;
  } else if(filed){
    hero.classList.add("filed");
    big.textContent = "Filed";
    why.textContent = "Keep the acknowledgement. Expect an intimation in a few weeks.";
  } else if(active){
    big.textContent = "Working on: " + active.label;
    why.textContent = active.detail || active.about;
  } else if(done === 0){
    big.textContent = "Waiting to start…";
    why.textContent = "Tell your agent \"file my ITR\" to begin.";
  } else {
    big.textContent = "Paused between steps";
    why.textContent = "Nothing is running right now.";
  }

  const h = d.headline || {};
  const mc = document.getElementById("moneyCard");
  if(h.kind && h.amount !== null){
    mc.hidden = false;
    document.getElementById("moneyLabel").textContent =
      h.kind === "refund" ? "Refund due to you" : "Tax still to pay";
    const el = document.getElementById("money");
    el.textContent = money(h.amount);
    el.className = "money " + h.kind;
    // A figure shown next to an unresolved blocker reads as settled. Say it isn't.
    document.getElementById("prov").hidden = !(d.blockers || []).length;
  } else { mc.hidden = true; }

  const bc = document.getElementById("blockCard");
  bc.hidden = !(d.blockers || []).length;
  document.getElementById("blockers").innerHTML = (d.blockers || [])
    .map(b => "<div><b>" + b.label + "</b> — " + b.detail + "</div>").join("");

  document.getElementById("steps").innerHTML = d.stages.map(s =>
    '<li class="s-' + s.status + '">' +
      '<span class="mark">' + MARK[s.status] + '</span>' +
      '<span><span class="name">' + s.label + '</span>' +
      '<div class="about">' + (s.detail || s.about) + '</div></span>' +
      '<span class="when">' + ago(s.at) + '</span>' +
    '</li>').join("");

  const feed = (d.events || []).slice(0, 8);
  document.getElementById("feed").innerHTML = feed.length
    ? feed.map(e => "<div><b>" + e.text + "</b><time>" + ago(e.at) + "</time></div>").join("")
    : '<div class="empty">Nothing yet.</div>';
}

async function tick(){
  try{
    const r = await fetch("/api/progress", {cache:"no-store"});
    if(!r.ok) throw new Error(r.status);
    render(await r.json());
    misses = 0;
    document.getElementById("live").className = "dot";
    document.getElementById("liveText").textContent = "live · updates every 2s";
  }catch(e){
    if(++misses > 2){
      document.getElementById("live").className = "dot stale";
      document.getElementById("liveText").textContent =
        "not connected — is the status server still running?";
    }
  }
}
tick(); setInterval(tick, 2000);
</script>
</body>
</html>
"""


def make_handler(workspace: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "itr-status/1.0"

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path.startswith("/api/progress"):
                body = json.dumps(progress.load(workspace)).encode("utf-8")
                self._send(200, body, "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/ack":
                self._send(404, b"not found", "text/plain")
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                stage = json.loads(self.rfile.read(n) or b"{}").get("stage", "")
                state = progress.acknowledge(workspace, stage)
                self._send(200, json.dumps(state).encode("utf-8"), "application/json")
            except Exception:  # noqa: BLE001 - a bad click must not kill the server
                self._send(400, b'{"ok":false}', "application/json")

        def log_message(self, *a) -> None:
            pass  # a request log of someone's tax dashboard is just noise

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", default="itr-workspace")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-open", action="store_true",
                    help="do not open a browser tab automatically")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    url = f"http://{HOST}:{args.port}"
    try:
        httpd = ThreadingHTTPServer((HOST, args.port), make_handler(ws))
    except OSError as exc:
        print(f"status_server: cannot bind {url} - {exc}\n"
              f"  Another copy may already be running. Try --port {args.port + 1}.",
              file=sys.stderr)
        return 1

    if not progress.path_for(ws).exists():
        print(f"note: {progress.path_for(ws)} does not exist yet - the page will "
              "show 'waiting to start' until the agent begins.")
    print(f"Filing status page: {url}")
    print("This page is served to your machine only. Ctrl-C to stop.")
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - headless box, no browser; not fatal
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Your filing is unaffected.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
