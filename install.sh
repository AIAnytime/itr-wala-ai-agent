#!/usr/bin/env bash
# Install the itr-agent skill from THIS checkout.
#
# No network access. It copies the files sitting next to this script - the ones
# you just read - so what you reviewed is what runs. For a tool that handles
# salary and bank data, that property is the point.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills/itr-agent"
NAME="itr-agent"

[ -d "$SRC" ] || { echo "error: $SRC not found - run install.sh from its checkout" >&2; exit 1; }

CLAUDE=0; CODEX=0; GEMINI=0; HERE=0
[ $# -eq 0 ] && CLAUDE=1
for arg in "$@"; do
  case "$arg" in
    --claude) CLAUDE=1 ;;
    --codex)  CODEX=1 ;;
    --gemini) GEMINI=1 ;;
    --all)    CLAUDE=1; CODEX=1; GEMINI=1 ;;
    --here)   CLAUDE=1; HERE=1 ;;
    -h|--help)
      cat <<'USAGE'
usage: ./install.sh [--claude] [--codex] [--gemini] [--all] [--here]

  (no flags)  Claude Code, user scope   ~/.claude/skills/itr-agent
  --here      Claude Code, this dir only  ./.claude/skills/itr-agent
  --codex     ~/.codex/skills/itr-agent
  --gemini    ~/.gemini/extensions/itr-agent
  --all       every agent, user scope

Scoping with --here keeps the skill out of unrelated sessions. If your tax
documents live in one folder, that is the better default.
USAGE
      exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

install_to() {
  local dest="$1" label="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ]; then
    printf '  %s already exists. Overwrite? [y/N] ' "$dest"
    read -r reply </dev/tty || reply=n
    case "$reply" in [yY]*) rm -rf "$dest" ;; *) echo "  skipped $label"; return ;; esac
  fi
  cp -R "$SRC" "$dest"
  echo "  installed $label -> $dest"
}

echo "Installing $NAME from $SRC"
[ "$CLAUDE" = 1 ] && {
  if [ "$HERE" = 1 ]; then install_to "$PWD/.claude/skills/$NAME" "Claude Code (this directory)"
  else install_to "$HOME/.claude/skills/$NAME" "Claude Code (user)"; fi
}
[ "$CODEX"  = 1 ] && install_to "$HOME/.codex/skills/$NAME" "Codex"
[ "$GEMINI" = 1 ] && install_to "$HOME/.gemini/extensions/$NAME" "Gemini"

echo
echo "Verifying the tax engine (do not skip this - it is the whole guarantee):"
if python3 "$SRC/scripts/test_tax_core.py"     >/dev/null 2>&1 \
&& python3 "$SRC/scripts/test_check_return.py" >/dev/null 2>&1 \
&& python3 "$SRC/scripts/test_progress.py"     >/dev/null 2>&1; then
  echo "  102/102 tests pass."
else
  echo "  TESTS FAILED. Do not file with this install." >&2
  echo "  Run them directly to see why:" >&2
  echo "    python3 $SRC/scripts/test_tax_core.py" >&2
  exit 1
fi

cat <<'NEXT'

Done. Open your agent and say "file my ITR".

For a live view of where the filing has got to, in plain English:
    python3 skills/itr-agent/scripts/status_server.py --workspace itr-workspace

The portal driver additionally needs Playwright:
    pip install playwright && playwright install chromium
NEXT
