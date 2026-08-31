#!/usr/bin/env bash
# Regenerate demo/status-page.gif.
#
# Walks the status page through a realistic filing story and captures one frame
# per beat with headless Chrome, then assembles them with ffmpeg. Kept in the
# repo so the demo can be rebuilt when the page changes, rather than being a
# binary nobody can reproduce.
#
# Needs: ffmpeg, and Chrome (or set CHROME=/path/to/binary).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$ROOT/skills/itr-agent/scripts"
WS="${WS:-/tmp/itr-demo-ws}"
PORT="${PORT:-7399}"
OUT="$ROOT/demo/status-page.gif"
FRAMES="$(mktemp -d)"

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
[ -x "$CHROME" ] || CHROME="$(command -v google-chrome || command -v chromium || true)"
[ -n "$CHROME" ] && [ -x "$CHROME" ] || { echo "error: Chrome not found; set CHROME=" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "error: ffmpeg not found" >&2; exit 1; }

P="python3 $S/progress.py --workspace $WS"
n=0
shot() {                                  # shot -> capture the page as it stands
  n=$((n + 1))
  "$CHROME" --headless --disable-gpu --hide-scrollbars \
    --force-device-scale-factor=2 --virtual-time-budget=2500 \
    --window-size=880,700 \
    --screenshot="$FRAMES/$(printf '%02d' $n).png" \
    "http://127.0.0.1:$PORT/" >/dev/null 2>&1
  echo "  frame $n"
}

cleanup() { kill %1 2>/dev/null || true; rm -rf "$FRAMES"; }
trap cleanup EXIT

rm -rf "$WS"; $P reset >/dev/null
python3 "$S/status_server.py" --workspace "$WS" --port "$PORT" --no-open >/dev/null 2>&1 &
sleep 2

echo "Recording..."

# 1. Mid-flight, so the page opens on something happening rather than an empty shell.
$P done  setup     --detail "Tax engine self-test passed - 102 checks" >/dev/null
$P done  documents --detail "Form 16, AIS and 26AS received"           >/dev/null
$P start extract                                                        >/dev/null
shot

# 2. The reconciliation catches a real discrepancy. This is the state the page
#    exists for: a stall with an explanation instead of a silent terminal.
$P done  extract   --detail "47 figures copied, each traced to a document"  >/dev/null
$P block validate  --detail "TDS in your Form 16 is 8,000 less than Form 26AS. A bank probably deducted tax too - we need that certificate." >/dev/null
shot

# 3. Resolved, and the deduction interview earns its keep.
$P done  validate  --detail "Everything matches your documents"        >/dev/null
$P done  deductions --detail "80D on your parents' premium was missing - added" >/dev/null
$P start compute                                                        >/dev/null
shot

# 4. The number arrives.
$P done  compute   --detail "New regime is cheaper by 1,45,430"        >/dev/null
$P set --form ITR-3 --regime new --refund 105410                       >/dev/null
shot

# 5. Onto the portal.
$P done  form      --detail "ITR-3 - foreign assets rule out ITR-4"    >/dev/null
$P done  reconcile --detail "Every AIS entry accounted for"            >/dev/null
$P done  pack      --detail "Field-by-field map ready"                 >/dev/null
$P start portal                                                         >/dev/null
shot

# 6. The handover - the whole point of the amber state.
$P done  portal    --detail "All schedules entered, Schedule FA included" >/dev/null
$P done  check     --detail "The portal agrees with our figures to the rupee" >/dev/null
$P wait  handover  --title "Submit, then e-verify" \
                   --detail "Nothing to pay - a refund is due. These two are yours alone." >/dev/null
shot

# 7. Done.
$P done  handover  --detail "Submitted and e-verified"                 >/dev/null
$P done  filed     --detail "Acknowledgement saved to artifacts/"      >/dev/null
shot

echo "Assembling..."
{ for f in "$FRAMES"/*.png; do
    echo "file '$f'"
    case "$f" in *06.png|*07.png) echo "duration 3.0" ;; *) echo "duration 2.5" ;; esac
  done
  ls "$FRAMES"/*.png | tail -1 | sed "s/^/file '/;s/$/'/"
} > "$FRAMES/list.txt"

ffmpeg -y -f concat -safe 0 -i "$FRAMES/list.txt" \
  -vf "fps=2,scale=880:-1:flags=lanczos,split[a][b];\
[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=none" \
  -loop 0 "$OUT" >/dev/null 2>&1

echo "Wrote $OUT ($(du -h "$OUT" | cut -f1))"
