#!/bin/bash
# Tests the monthly regulatory watch (shared/morning/reg_watch.py and its run.sh / run.ps1 wiring):
# off by default, first-Monday detection, the "not set" skip, budget and time skips, the output
# folder, the prompt text when on, and the web tools allowed only when it's on and due.
# Fake Kit and fake claude in a throwaway folder; no web, connector, or model call.
#   bash tests/test_reg_watch.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
RW="$HERE/shared/morning/reg_watch.py"
H="$S/home"; KIT="$H/Claude/Agents/kit"; C="$KIT/memory/context"
mkdir -p "$C"
cp "$HERE/kit/memory/context/compliance.md" "$HERE/kit/memory/context/library.md" "$C/"
rw() { python3 "$RW" --home "$H" --prompt "$HERE/shared/morning/prompt-reg-watch.md" --out "$S/out.txt" "$@"; }
set_regimes() { python3 - "$C/compliance.md" "$1" <<'PY'
import re, sys
p, v = sys.argv[1], sys.argv[2]
s = open(p).read()
s = re.sub(r"^- \*\*Regulatory watch:\*\* not set\..*?(?=^- \*\*)", f"- **Regulatory watch:** {v}\n", s, flags=re.M | re.S)
open(p, "w").write(s)
PY
}

# ---- first-Monday detection ------------------------------------------------------------------
for d in 2026-11-02 2026-12-07 2027-02-01; do
  rm -f "$S/out.txt"; r=$(rw --date $d | head -1)
  [ "$r" != "not-due" ] && ok "first Monday $d is due" || bad "first Monday $d: $r"
done
for d in 2026-11-09 2026-10-21 2026-12-01 2026-11-08; do
  rm -f "$S/out.txt"; r=$(rw --date $d | head -1)
  [ "$r" = "not-due" ] && [ ! -f "$S/out.txt" ] && ok "$d isn't the first Monday: not due, no prompt text" || bad "$d: $r"
done
r=$(rw --date 2026-11-09 --when every-run | head -1)
[ "$r" != "not-due" ] && ok "REG_WATCH_WHEN=every-run runs it on any weekly review" || bad "every-run"

# ---- not set: skip with a note ---------------------------------------------------------------
r=$(rw --date 2026-11-02)
[ "$r" = "skip no regimes set in compliance.md (Regulatory watch)" ] && grep -q 'Skipped: no regimes set' "$S/out.txt" \
  && ok "regimes 'not set': skipped, with a line for the review" || bad "not set: $r"
! grep -q WebSearch <<<"$r" && ok "skip: no tools added" || bad "skip added tools"

# ---- on and due ------------------------------------------------------------------------------
set_regimes '"SEC Reg SCI, CFTC; DORA, NYDFS 500, NIST".'
out=$(rw --date 2026-11-02)
[ "$(head -1 <<<"$out")" = "on" ] && ok "regimes set, first Monday: on" || bad "on: $out"
grep -qF "SEC Reg SCI; CFTC; DORA; NYDFS 500; NIST" "$S/out.txt" && ok "the brief lists the regimes (cleaned)" || bad "regimes in brief"
grep -q "Monthly regulatory watch for October 2026" "$S/out.txt" && grep -q "regulatory-watch-template.md" "$S/out.txt" \
  && grep -q "Public sources only" "$S/out.txt" && grep -q "never add a company" "$S/out.txt" \
  && ok "the brief covers last month, the template, public sources, and no company content" || bad "brief text"
grep -q 'exactly three lines' "$S/out.txt" && ok "the review gets a three-line summary" || bad "summary"
grep -qF "$KIT/briefs/regulatory-watch-2026-10.md" "$S/out.txt" && grep -q "no library folder is set" "$S/out.txt" \
  && ok "no folder or library root: saved in briefs/, and the review says so" || bad "fallback path"
grep -qx "Agent" <<<"$out" && grep -qx "WebSearch" <<<"$out" && grep -qx "WebFetch" <<<"$out" && ! grep -q "^Edit" <<<"$out" \
  && ok "on: Agent, WebSearch, WebFetch (no Edit rule needed for briefs/)" || bad "rules: $out"
! grep -q '{{' "$S/out.txt" && ok "every placeholder is filled" || bad "placeholders left"
sed -i.bak 's#^- \*\*Library root:\*\* not set\..*#- **Library root:** `~/Library-root`.#' "$C/library.md"
out=$(rw --date 2026-11-02)
grep -qF "$H/Library-root/regulatory-watch/regulatory-watch-2026-10.md" "$S/out.txt" && grep -qxF 'Edit(~/Library-root/regulatory-watch/**)' <<<"$out" \
  && ok "library root set: regulatory-watch/ in it, with an Edit rule" || bad "library path: $out"
python3 - "$C/compliance.md" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
s = re.sub(r"^- \*\*Regulatory watch folder:\*\* optional\..*?(?=^- \*\*|^\n)", "- **Regulatory watch folder:** `/srv/lib/regwatch`\n", s, flags=re.M | re.S)
open(p, "w").write(s)
PY
out=$(rw --date 2026-11-02)
grep -qF "/srv/lib/regwatch/regulatory-watch-2026-10.md" "$S/out.txt" && grep -qxF 'Edit(//srv/lib/regwatch/**)' <<<"$out" \
  && ok "the setup's folder wins" || bad "setup folder: $out"
r=$(rw --date 2026-11-02 --cost-level warn | head -1)
[ "$r" = "skip the monthly budget is at its warn level" ] && ok "budget at warn: skipped" || bad "warn: $r"
r=$(rw --date 2026-11-02 --cost-level stop | head -1)
[ "$r" = "skip the monthly budget is at its stop level" ] && ok "budget at stop: skipped" || bad "stop: $r"
r=$(rw --date 2026-11-02 --timeout 600 --min-left 15 | head -1)
[ "$r" = "skip the run's time limit is too short" ] && ok "time limit too short: skipped" || bad "timeout: $r"

# ---- run.sh wiring ---------------------------------------------------------------------------
M="$KIT/.install/shared/morning"
mkdir -p "$M" "$KIT/.install/logs" "$KIT/briefs" "$H/.local/bin"
cp "$HERE/shared/morning/prompt.md" "$HERE/shared/morning/prompt-weekly.md" "$HERE/shared/morning/reg_watch.py" "$HERE/shared/morning/prompt-reg-watch.md" "$M/"
cat > "$H/.local/bin/claude" <<EOF
#!/bin/bash
printf "%s\\n" "\$@" > "$S/claude-args.txt"
echo "Kit test" > "$KIT/briefs/weekly-text.txt"
echo '{"type":"result","result":"done","total_cost_usd":0.01,"usage":{}}'
EOF
chmod +x "$H/.local/bin/claude"
ARGS="$S/claude-args.txt"
runsh() { rm -f "$KIT/.install/logs/"*.done "$ARGS"; HOME="$H" zsh "$HERE/platform/mac/morning/run.sh" weekly >/dev/null 2>&1; }
printf 'OUTLOOK_CHECK="off"\n' > "$M/config"
runsh
[ -s "$ARGS" ] && ! grep -q "regulatory watch" "$ARGS" && ! grep -qx "WebSearch" "$ARGS" && ! grep -qx "WebFetch" "$ARGS" \
  && ok "run.sh: off by default (no brief, no web tools)" || bad "run.sh default"
grep -q '^REG_WATCH="off"' "$HERE/shared/morning/config.example" && ok "config.example: REG_WATCH off" || bad "config.example"
printf 'OUTLOOK_CHECK="off"\nREG_WATCH="on"\nREG_WATCH_WHEN="every-run"\n' > "$M/config"
runsh
grep -q "Monthly regulatory watch (REG_WATCH is on" "$ARGS" && grep -qF "SEC Reg SCI; CFTC" "$ARGS" \
  && ok "run.sh: on, the weekly prompt carries the brief" || bad "run.sh prompt"
grep -qx "WebSearch" "$ARGS" && grep -qx "WebFetch" "$ARGS" && grep -qx "Agent" "$ARGS" && grep -qxF 'Edit(//srv/lib/regwatch/**)' "$ARGS" \
  && ok "run.sh: on, web tools, Agent, and Edit on the folder are allowed" || bad "run.sh tools"
printf 'OUTLOOK_CHECK="off"\nREG_WATCH="on"\nREG_WATCH_WHEN="every-run"\nALLOW_TOOLS_WEEKLY="Agent"\n' > "$M/config"
runsh
[ "$(grep -cx Agent "$ARGS")" = "1" ] && ok "run.sh: Agent isn't doubled" || bad "Agent doubled"
TODAY_FM=$(python3 -c "import datetime as d; t=d.date.today(); print(int(t.weekday()==0 and t.day<=7))")
printf 'OUTLOOK_CHECK="off"\nREG_WATCH="on"\n' > "$M/config"
runsh
if [ "$TODAY_FM" = "0" ]; then
  [ -s "$ARGS" ] && ! grep -q "regulatory watch" "$ARGS" && ! grep -qx "WebSearch" "$ARGS" && ok "run.sh: on but not the first Monday: nothing added" || bad "run.sh not due"
else
  grep -qx "WebSearch" "$ARGS" && ok "run.sh: on, today is the first Monday: added" || bad "run.sh due today"
fi
printf 'OUTLOOK_CHECK="off"\nREG_WATCH="on"\nREG_WATCH_WHEN="every-run"\n' > "$M/config"
rm -f "$KIT/.install/logs/"*.done "$ARGS"; HOME="$H" zsh "$HERE/platform/mac/morning/run.sh" morning >/dev/null 2>&1
[ -s "$ARGS" ] && ! grep -q "regulatory watch" "$ARGS" && ! grep -qx "WebSearch" "$ARGS" && ok "run.sh: the morning run is unaffected" || bad "run.sh morning"
mkdir -p "$KIT/.install/shared/bin"
cat > "$KIT/.install/shared/bin/kit-cost" <<'KC'
import sys
if sys.argv[1:2] == ["check"]:
    print("warn 85%; budget 100")
KC
runsh
grep -q "Skipped: the monthly budget is at its warn level" "$ARGS" && ! grep -qx "WebSearch" "$ARGS" \
  && ok "run.sh: at the budget's warning level, skipped with a line and no web tools" || bad "run.sh budget"
rm -f "$KIT/.install/shared/bin/kit-cost"

# ---- run.ps1 wiring (under pwsh, when present) --------------------------------------------------
P1="$HERE/platform/windows/morning/run.ps1"
grep -q '"REG_WATCH" "off"' "$P1" && grep -q 'reg_watch.py' "$P1" && ok "run.ps1: calls reg_watch.py, off by default" || bad "run.ps1 wiring"
if command -v pwsh >/dev/null 2>&1 && command -v python >/dev/null 2>&1; then
  mkdir -p "$S/bin"; cp "$H/.local/bin/claude" "$S/bin/claude"
  runps() { rm -f "$KIT/.install/logs/"*.done "$ARGS"; USERPROFILE="$H" KIT_DIR="$KIT" PATH="$S/bin:$PATH" pwsh -NoProfile -File "$P1" weekly >/dev/null 2>&1; }
  printf 'OUTLOOK_CHECK="off"\n' > "$M/config"
  runps
  [ -s "$ARGS" ] && ! grep -q "regulatory watch" "$ARGS" && ! grep -qx "WebSearch" "$ARGS" && ok "run.ps1: off by default" || bad "run.ps1 default"
  printf 'OUTLOOK_CHECK="off"\nREG_WATCH="on"\nREG_WATCH_WHEN="every-run"\n' > "$M/config"
  runps
  grep -q "Monthly regulatory watch (REG_WATCH is on" "$ARGS" && grep -qx "WebSearch" "$ARGS" && grep -qx "WebFetch" "$ARGS" && grep -qx "Agent" "$ARGS" \
    && ok "run.ps1: on, the brief and the web tools are added" || bad "run.ps1 on"
else
  echo "skip run.ps1 run (needs pwsh and python)"
fi

echo "regulatory watch tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
