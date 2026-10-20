#!/bin/bash
# Tests kit-pause, kit-outlook, kit-backup, kit-retention, and their hooks in run.sh, doctor.py, and
# dashboard.py. Everything runs in a throwaway folder with a fake Kit; nothing real is touched, and
# no launchd job is loaded or unloaded.
#   bash tests/test_batch2_tools.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HERE/shared/bin"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
export KIT_DIR="$S/kit"
mkdir -p "$KIT_DIR/.install/shared/morning" "$KIT_DIR/memory/context" "$KIT_DIR/briefs"

# ---- kit-pause ---------------------------------------------------------------------------------
python3 "$BIN/kit-pause" status | grep -q "not paused" && ok "pause: status when running" || bad "pause status"
python3 "$BIN/kit-pause" credits ran out >/dev/null
[ "$(head -1 "$KIT_DIR/.install/PAUSED")" = "credits ran out" ] && ok "pause: marker holds the reason" || bad "pause marker"
python3 "$BIN/kit-pause" status | grep -q "PAUSED: credits ran out" && ok "pause: status shows reason" || bad "pause status reason"
mkdir -p "$S/LaunchAgents"; touch "$S/LaunchAgents/com.$USER.kit.morning.plist" "$S/LaunchAgents/com.$USER.kit.weekly.plist" "$S/LaunchAgents/com.other.thing.plist"
out=$(KIT_LAUNCHAGENTS="$S/LaunchAgents" python3 "$BIN/kit-pause" incident --hard)
echo "$out" | grep -q "would run" && [ "$(echo "$out" | grep -c 'launchctl bootout')" = 2 ] && ! echo "$out" | grep -q other.thing \
  && ok "pause --hard without --yes: shows 2 bootout commands, runs none" || bad "pause --hard dry run: $out"

# run.sh skips while paused (HOME points at the sandbox, so the real Kit is never read).
mkdir -p "$S/home/Claude/Agents"; ln -s "$KIT_DIR" "$S/home/Claude/Agents/kit"
HOME="$S/home" zsh "$HERE/platform/mac/morning/run.sh" morning; rc=$?
grep -q "run skipped: Kit is paused (incident)" "$KIT_DIR/.install/logs/$(date +%Y-%m-%d).log" 2>/dev/null && [ $rc -eq 0 ] \
  && ok "run.sh: exits early with a log line while paused" || bad "run.sh pause (rc=$rc)"

# doctor and dashboard report the pause.
python3 - "$HERE/shared" "$KIT_DIR" <<'EOF' && ok "doctor and dashboard show PAUSED" || bad "doctor/dashboard pause"
import sys, pathlib, importlib.util
sys.path.insert(0, sys.argv[1])
def load(name):
    spec = importlib.util.spec_from_file_location(name, f"{sys.argv[1]}/{name}.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
doc = load("doctor"); doc.KIT = pathlib.Path(sys.argv[2]); doc.results.clear(); doc.check_paused()
assert doc.results and doc.results[0][0] == "warn" and "incident" in doc.results[0][2], doc.results
dash = load("dashboard"); dash.KIT = pathlib.Path(sys.argv[2])
b = dash.state_banners(); assert "Kit is paused" in b and "incident" in b, b
EOF
python3 "$BIN/kit-pause" resume >/dev/null; [ ! -f "$KIT_DIR/.install/PAUSED" ] && ok "pause: resume removes the marker" || bad "resume"

# ---- kit-outlook (fake pgrep and osascript) ----------------------------------------------------
FAKE="$S/fakebin"; mkdir -p "$FAKE"
cat > "$FAKE/pgrep" <<'EOF'
#!/bin/bash
[ -f "$OUTLOOK_FAKE/running" ]
EOF
cat > "$FAKE/osascript" <<'EOF'
#!/bin/bash
cat >/dev/null
n=$(cat "$OUTLOOK_FAKE/count" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$OUTLOOK_FAKE/count"
mode=$(cat "$OUTLOOK_FAKE/mode")
if [ "$mode" = ok ] || { [ "$mode" = slow-then-ok ] && [ $n -ge 2 ]; }; then echo "16.89"; exit 0; fi
if [ "$mode" = blocked ]; then echo "execution error: Not authorized to send Apple events to Microsoft Outlook. (-1743)" >&2; exit 1; fi
echo "execution error: Microsoft Outlook got an error: AppleEvent timed out. (-1712)" >&2; exit 1
EOF
chmod +x "$FAKE/pgrep" "$FAKE/osascript"
export OUTLOOK_FAKE="$S/ofake"; mkdir -p "$OUTLOOK_FAKE"
ol() { echo "$1" > "$OUTLOOK_FAKE/mode"; rm -f "$OUTLOOK_FAKE/count"; PATH="$FAKE:$PATH" OUTLOOK_RETRY_WAITS="0 0" python3 "$BIN/kit-outlook" check ${2:-} --write "$KIT_DIR/briefs/outlook.txt"; }
rm -f "$OUTLOOK_FAKE/running"
ol ok >/dev/null; grep -q "^not-running" "$KIT_DIR/briefs/outlook.txt" && [ ! -f "$OUTLOOK_FAKE/count" ] \
  && ok "outlook: not running -> says so, never calls Outlook" || bad "outlook not running"
touch "$OUTLOOK_FAKE/running"
ol ok >/dev/null && grep -q "^ok .*16.89" "$KIT_DIR/briefs/outlook.txt" && ok "outlook: answers -> ok" || bad "outlook ok"
ol slow-then-ok --retry >/dev/null && [ "$(cat "$OUTLOOK_FAKE/count")" = 2 ] && grep -q "^ok" "$KIT_DIR/briefs/outlook.txt" \
  && ok "outlook: -1712 then ok on retry" || bad "outlook retry recovers"
ol timeout --retry >/dev/null; rc=$?
[ $rc -eq 1 ] && [ "$(cat "$OUTLOOK_FAKE/count")" = 3 ] && grep -q "^not-responding .*restart Outlook.*after 3 tries" "$KIT_DIR/briefs/outlook.txt" \
  && ok "outlook: -1712 three times -> not-responding, restart prompt" || bad "outlook persistent timeout: $(cat "$KIT_DIR/briefs/outlook.txt")"
python3 - "$HERE/shared" "$KIT_DIR" <<'EOF' && ok "doctor warns on today's not-responding Outlook" || bad "doctor outlook"
import sys, pathlib, importlib.util
spec = importlib.util.spec_from_file_location("doctor", f"{sys.argv[1]}/doctor.py"); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
d.KIT = pathlib.Path(sys.argv[2]); d.results.clear(); d.check_outlook()
assert d.results and d.results[0][0] == "warn" and "restart Outlook" in d.results[0][2], d.results
EOF
ol blocked >/dev/null; grep -q "^blocked .*Automation" "$KIT_DIR/briefs/outlook.txt" && ok "outlook: -1743 -> blocked, Automation hint" || bad "outlook blocked"

# ---- kit-backup --------------------------------------------------------------------------------
# HOME is the test folder so the backup folder counts as inside home (plain backups are refused elsewhere).
K="$KIT_DIR"; export BACKUP_DIR="$S/backups" BACKUP_KEEP=2
( cd "$K" && git init -q -b main && echo "queue v1" > QUEUE.md && mkdir -p memory/people && echo "fact" > memory/people/a.md \
  && git add -A && git -c user.name=t -c user.email=t@t commit -qm one && git checkout -q -b side && echo x > side.txt && git add side.txt \
  && git -c user.name=t -c user.email=t@t commit -qm side && git checkout -q main )
echo "uncommitted edit" >> "$K/QUEUE.md"; mkdir -p "$K/.install/logs"; echo noisy > "$K/.install/logs/x.log"
HOME="$S" python3 "$BIN/kit-backup" | grep -q "MB), checked$" && ok "backup: made and checked" || bad "backup make"
A=$(ls "$S/backups"/kit-backup-*.tar.gz | head -1)
[ "$(stat -f %Lp "$A")" = 600 ] && [ "$(stat -f %Lp "$S/backups")" = 700 ] && ok "backup: owner-only permissions" || bad "backup perms"
tar -tzf "$A" | grep -q "files/.install/logs" && bad "backup: logs excluded" || ok "backup: logs excluded"
HOME="$S" python3 "$BIN/kit-backup" restore "$A" --to "$S/restored" >/dev/null
diff -q "$K/QUEUE.md" "$S/restored/QUEUE.md" >/dev/null && [ -f "$S/restored/memory/people/a.md" ] \
  && [ "$(git -C "$S/restored" log --oneline main | wc -l | tr -d ' ')" = 1 ] && git -C "$S/restored" rev-parse -q --verify side >/dev/null \
  && [ -z "$(git -C "$S/restored" remote)" ] && [ "$(git -C "$S/restored" symbolic-ref --short HEAD)" = main ] \
  && git -C "$S/restored" status --porcelain | grep -q "QUEUE.md" \
  && ok "backup: round trip restores files, uncommitted edit, both branches, no remote" || bad "backup round trip"
HOME="$S" python3 "$BIN/kit-backup" restore "$A" --to "$S/restored" >/dev/null 2>&1 && bad "backup: refuses non-empty target" || ok "backup: refuses non-empty target"
mkdir -p "$S/tamper" && tar -xzf "$A" -C "$S/tamper" && echo evil >> "$S/tamper/files/QUEUE.md" && (cd "$S/tamper" && tar -czf "$S/bad.tar.gz" .)
HOME="$S" python3 "$BIN/kit-backup" verify "$S/bad.tar.gz" | grep -q "checksum differs: QUEUE.md" && ok "backup: verify catches a changed file" || bad "backup tamper"
sleep 1; HOME="$S" python3 "$BIN/kit-backup" >/dev/null; sleep 1; HOME="$S" python3 "$BIN/kit-backup" >/dev/null
[ "$(ls "$S/backups"/kit-backup-*.tar.gz | wc -l | tr -d ' ')" = 2 ] && ok "backup: keeps the newest BACKUP_KEEP (2)" || bad "backup rotation"

# ---- kit-retention -----------------------------------------------------------------------------
R="$KIT_DIR"; mkdir -p "$R/briefs" "$R/artifacts/payments/meetings" "$R/artifacts/other"
for f in briefs/2024-01-02.md briefs/2024-01-03.md artifacts/payments/meetings/old.md artifacts/other/old.md; do echo "content" > "$R/$f"; touch -t 202401020900 "$R/$f"; done
echo "notes [payments] tagged" > "$R/briefs/2024-01-04.md"; touch -t 202401020900 "$R/briefs/2024-01-04.md"
echo "new" > "$R/briefs/2026-10-01.md"
python3 "$BIN/kit-retention" report | grep -q "no disposal rules are set" && ok "retention: no rules -> keep everything" || bad "retention default keep"
cat > "$R/memory/context/retention.json" <<'EOF'
{"default": "keep", "rules": [{"name": "old briefs", "root": "kit", "paths": ["briefs/*.md"], "older_than_days": 365, "action": "dispose"},
 {"name": "old artifacts", "root": "kit", "paths": ["artifacts/**/*.md"], "older_than_days": 365, "action": "dispose"}]}
EOF
python3 "$BIN/kit-retention" hold payments --reason "matter 12" >/dev/null
[ "$(python3 "$BIN/kit-retention" holds --brief)" = "payments (since $(date +%d-%b-%Y))" ] && ok "retention: holds --brief line" || bad "holds brief"
rep=$(python3 "$BIN/kit-retention" report)
echo "$rep" | grep -q "3 eligible, 2 kept by legal holds" && echo "$rep" | grep -q "held .*payments/meetings/old.md" \
  && echo "$rep" | grep -q "held .*2024-01-04.md" && ! echo "$rep" | grep -q "2026-10-01" \
  && ok "retention: report: 3 eligible, path hold and tag hold respected, new file kept" || bad "retention report: $rep"
python3 "$BIN/kit-retention" dispose >/dev/null 2>&1 && bad "retention: dispose needs --yes" || ok "retention: dispose refuses without --yes"
echo changed >> "$R/briefs/2024-01-03.md"   # changed after the report: must be skipped
python3 "$BIN/kit-retention" dispose --yes >/dev/null
H="$R/.install/retention-holding/$(date +%Y-%m-%d)/kit"
[ -f "$H/briefs/2024-01-02.md" ] && [ -f "$H/artifacts/other/old.md" ] && [ -f "$R/briefs/2024-01-03.md" ] \
  && [ -f "$R/artifacts/payments/meetings/old.md" ] && [ -f "$R/briefs/2024-01-04.md" ] && [ ! -f "$R/briefs/2024-01-02.md" ] \
  && ok "retention: dispose moves only unchanged eligible files to the holding folder" || bad "retention dispose"
python3 - "$HERE/shared" "$KIT_DIR" <<'EOF' && ok "dashboard and doctor show the legal hold" || bad "hold banner"
import sys, pathlib, importlib.util
sys.path.insert(0, sys.argv[1])
def load(n):
    spec = importlib.util.spec_from_file_location(n, f"{sys.argv[1]}/{n}.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
dash = load("dashboard"); dash.KIT = pathlib.Path(sys.argv[2]); b = dash.state_banners()
assert "Legal hold" in b and "payments" in b, b
doc = load("doctor"); doc.KIT = pathlib.Path(sys.argv[2]); doc.results.clear(); doc.check_holds()
assert doc.results and "payments" in doc.results[0][2]
EOF
python3 "$BIN/kit-retention" release payments >/dev/null && [ -z "$(python3 "$BIN/kit-retention" holds --brief)" ] && ok "retention: release ends the hold" || bad "release"

# ---- run.sh: Outlook stale notice and legal holds reach the prompt (fake claude records it) -----
python3 "$BIN/kit-retention" hold payments --reason "matter 12" >/dev/null
LB="$S/home/.local/bin"; mkdir -p "$LB" "$KIT_DIR/.install/shared/bin" "$KIT_DIR/.install/shared/morning"
cp "$BIN/kit-outlook" "$BIN/kit-retention" "$KIT_DIR/.install/shared/bin/"
cp "$HERE/shared/morning/prompt.md" "$KIT_DIR/.install/shared/morning/"
cp "$FAKE/pgrep" "$FAKE/osascript" "$LB/"
printf '#!/bin/bash\nprintf "%%s\\n" "$@" > "%s/claude-args.txt"\n' "$S" > "$LB/claude"; chmod +x "$LB/claude"
echo 'OUTLOOK_RETRY_WAITS="0 0"' > "$KIT_DIR/.install/shared/morning/config"
touch "$OUTLOOK_FAKE/running"; echo timeout > "$OUTLOOK_FAKE/mode"; rm -f "$OUTLOOK_FAKE/count"
rm -f "$KIT_DIR/.install/logs/"*.done
HOME="$S/home" OUTLOOK_FAKE="$OUTLOOK_FAKE" zsh "$HERE/platform/mac/morning/run.sh" morning >/dev/null 2>&1
grep -q "Stale: Outlook didn't respond; restart Outlook" "$S/claude-args.txt" 2>/dev/null && grep -q "Don't call the Outlook calendar or mail commands" "$S/claude-args.txt" \
  && ok "run.sh: Outlook not responding -> stale notice in the prompt" || bad "run.sh outlook prompt"
grep -q "Active legal holds .*payments (since" "$S/claude-args.txt" 2>/dev/null && ok "run.sh: legal holds reach the prompt" || bad "run.sh holds prompt"
echo ok > "$OUTLOOK_FAKE/mode"; rm -f "$OUTLOOK_FAKE/count" "$KIT_DIR/.install/logs/"*.done "$S/claude-args.txt"
HOME="$S/home" OUTLOOK_FAKE="$OUTLOOK_FAKE" zsh "$HERE/platform/mac/morning/run.sh" morning >/dev/null 2>&1
[ -f "$S/claude-args.txt" ] && ! grep -q "Stale:" "$S/claude-args.txt" && ok "run.sh: Outlook ok -> no stale notice" || bad "run.sh outlook ok"

echo "batch 2 tool tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
