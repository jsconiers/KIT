#!/bin/bash
# Tests the smaller core fixes: kit-expiry stays off the network unless --live, --help exits 0 on the
# commands that have it, and the other one-line behaviours listed below. Runs in a temp HOME.
# Run: bash tests/test_core_fixes.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if [[ "$3" == *"$2"* ]]; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -20; fi; }
B="$HERE/shared/bin"
K="$T/kit"; mkdir -p "$K"

# ---- kit-expiry: cache only unless --live ----
FAKE="$T/fakebin"; mkdir -p "$FAKE"
for t in openssl curl; do
  printf '#!/bin/sh\necho "%s $*" >> "%s/network.log"\n' "$t" "$T" > "$FAKE/$t"; chmod +x "$FAKE/$t"
done
cat > "$K/expiry.json" <<'JSON'
{"warn_days": 30, "items": [
  {"name": "example.org certificate", "check": "cert", "host": "example.org"},
  {"name": "example.org domain", "check": "domain", "domain": "example.org"},
  {"name": "Passport", "kind": "document", "expires": "2031-05-12"}]}
JSON
X() { PATH="$FAKE:$PATH" KIT_DIR="$K" python3 "$B/kit-expiry" "$@" 2>&1; }
out="$(X)"; X --check --health > /dev/null; X --json > /dev/null; X --json --cached > /dev/null
[ ! -f "$T/network.log" ] && ok "kit-expiry, --check, and --json stay off the network" || { bad "no network by default"; cat "$T/network.log"; }
has "an item never looked up says how to look it up" "kit-expiry --live" "$out"
X --live > /dev/null
grep -q "^openssl" "$T/network.log" 2>/dev/null && grep -q "^curl.*rdap.org" "$T/network.log" 2>/dev/null \
  && ok "--live looks certificates and domains up" || bad "--live lookups"
out="$(X --help)"; rc=$?
[ $rc -eq 0 ] && ok "kit-expiry --help exits 0" || bad "kit-expiry --help exit $rc"
has "kit-expiry --help explains --live" "--live" "$out"

# ---- deliver.py: no work text means the work side sends nothing; NO TEXT sends nothing anywhere ----
D="$T/deliver"; mkdir -p "$D"
printf 'DELIVERY_PERSONAL="nochannel"\nDELIVERY_WORK="nochannel"\nPHONE_APPROVALS="off"\n' > "$D/config"
printf 'Kit brief: dentist at 3, call Mom\n' > "$D/latest-text.txt"
dl() { HOME="$T" KIT_DIR="$K" python3 "$HERE/shared/deliver.py" --mode morning --text "$D/latest-text.txt" --config "$D/config" 2>&1; }
out="$(dl)"
has "no -work.txt: the work side sends nothing" "work: nothing to send" "$out"
has "the personal side still gets the combined text" "personal/nochannel" "$out"
[[ "$out" != *"work/nochannel"* ]] && ok "no work channel is even tried" || bad "work channel tried"
printf 'Work: 2 meetings\n' > "$D/latest-text-work.txt"
has "a -work.txt goes to the work side" "work/nochannel" "$(dl)"
printf 'NO TEXT\n' > "$D/latest-text.txt"; rm "$D/latest-text-work.txt"
out="$(dl)"; has "NO TEXT: nothing sent on the split path" "nothing to send (NO TEXT)" "$out"
[[ "$out" != *"nochannel"* ]] && ok "NO TEXT: no channel tried" || bad "NO TEXT channel tried"
out="$(HOME="$T" KIT_DIR="$K" python3 "$HERE/shared/deliver.py" --mode morning --text "$D/latest-text.txt" --channels nochannel --config "$D/config" 2>&1)"
has "NO TEXT: nothing sent on the single-channel path" "nothing to send (NO TEXT)" "$out"

# ---- uninstall.sh: unloads and removes Kit's launchd jobs and its ~/.local/bin links, nothing else ----
U="$T/uhome"; mkdir -p "$U/Library/LaunchAgents" "$U/.local/bin" "$U/Claude/Agents/kit/.install/shared/bin" "$U/elsewhere"
USERNAME="${USER:-$(id -un)}"
for j in morning textback sync; do touch "$U/Library/LaunchAgents/com.$USERNAME.kit.$j.plist"; done
touch "$U/Library/LaunchAgents/com.other.app.plist"
ln -s "$U/Claude/Agents/kit/.install/shared/bin/todo" "$U/.local/bin/todo"
ln -s "$U/elsewhere/tool" "$U/.local/bin/mytool"; printf 'x\n' > "$U/.local/bin/plainfile"
printf '#!/bin/sh\necho "$*" >> "%s/launchctl.log"\n' "$T" > "$T/fake-launchctl"; chmod +x "$T/fake-launchctl"
out="$(HOME="$U" KIT_LAUNCHCTL="$T/fake-launchctl" bash "$HERE/platform/mac/uninstall.sh" 2>&1)"
has "uninstall reports what it removed" "Removed 3 launchd job(s) and 1 command link(s)" "$out"
[ "$(grep -c '^bootout gui/' "$T/launchctl.log" 2>/dev/null)" = "3" ] && grep -q "kit.textback.plist" "$T/launchctl.log" \
  && ok "every Kit job is unloaded, textback included" || bad "jobs unloaded"
[ -z "$(ls "$U/Library/LaunchAgents" | grep kit)" ] && [ -f "$U/Library/LaunchAgents/com.other.app.plist" ] \
  && ok "Kit's job files removed, others kept" || bad "job files"
[ ! -e "$U/.local/bin/todo" ] && [ -L "$U/.local/bin/mytool" ] && [ -f "$U/.local/bin/plainfile" ] \
  && ok "only links into Kit's copy removed from ~/.local/bin" || bad "links"
[ -d "$U/Claude/Agents/kit" ] && ok "Kit's folder kept" || bad "Kit's folder removed"

# ---- preflight.sh: its paid check goes in the cost ledger; no call to a kit-catalog that doesn't exist ----
P="$T/phome"; PK="$P/Claude/Agents/kit"; mkdir -p "$P/.local/bin" "$PK/.install/shared/bin" "$PK/.install/shared/morning"
cp "$B/kit-cost" "$PK/.install/shared/bin/"
cat > "$P/.local/bin/claude" <<'SH'
#!/bin/sh
echo '{"type":"result","result":"OK","total_cost_usd":0.0004,"usage":{"input_tokens":12,"output_tokens":2},"modelUsage":{"claude-haiku":{"costUSD":0.0004}}}'
SH
chmod +x "$P/.local/bin/claude"
printf '#!/bin/sh\ntouch "%s/catalog-ran"\n' "$T" > "$P/.local/bin/kit-catalog"; chmod +x "$P/.local/bin/kit-catalog"
env -u KIT_DIR HOME="$P" CLAUDE_CODE_OAUTH_TOKEN=test-run zsh "$HERE/platform/mac/morning/preflight.sh" > /dev/null 2>&1
grep -q '"mode": "preflight"' "$PK/.install/logs/cost.jsonl" 2>/dev/null && ok "preflight's check is in the cost ledger" \
  || { bad "preflight cost"; cat "$PK/.install/logs/preflight.log" 2>/dev/null; }
grep -q "login ok" "$PK/.install/logs/preflight.log" && ok "preflight still reads the OK from JSON output" || bad "preflight OK"
[ ! -f "$T/catalog-ran" ] && ! grep -q "kit-catalog" "$HERE/platform/mac/morning/preflight.sh" \
  && ok "preflight no longer calls kit-catalog" || bad "kit-catalog call"

# ---- --help exits 0, and todo's help needs no QUEUE.md ----
for c in kit-dates kit-grammar kit-textback todo; do
  out="$(env -u KIT_DIR HOME="$T/nohome" KIT_DIR="$T/nokit" python3 "$B/$c" --help 2>&1)"; rc=$?
  [ $rc -eq 0 ] && [ -n "$out" ] && [[ "$out" != *"Can't find"* ]] && ok "$c --help exits 0 with its help" || bad "$c --help (exit $rc): ${out:0:80}"
done
# ---- the read-only kit-library commands are allowed bare; kit-ppmx setup names the token's store ----
python3 -c '
import sys; sys.path.insert(0, sys.argv[1] + "/shared"); import kit_setup as k
assert {"Bash(kit-library)", "Bash(kit-library search)", "Bash(kit-library status)", "Bash(kit-library --check)"} <= set(k.ALLOW)
assert not any(r in k.ALLOW for r in ("Bash(kit-library index)", "Bash(kit-library mirror)", "Bash(kit-library flush)"))
' "$HERE" && ok "bare kit-library read commands are allowed, and none that change things" || bad "bare kit-library rules"
mkdir -p "$T/ppk/.install/shared/morning"
out="$(KIT_DIR="$T/ppk" PPMX_TOKEN_KEYCHAIN="Kit PPMX" PPMX_TOKEN= python3 "$B/kit-ppmx" setup 2>&1)"
if [ "$(uname)" = "Darwin" ]; then
  has "kit-ppmx setup puts the Keychain entry's name in credential_env" '"credential_env": {"ppmx": ["Kit PPMX"]}' "$out"
fi
has "kit-ppmx setup says credential_env holds a name, not the token" "holds only the name" "$out"
# ---- the kitmail wrapper tries the quick inbox first and logs it for kit doctor ----
W="$T/whome"; mkdir -p "$W/Claude/Agents/kit/.install/platform/mac/mail"
sed -n "/^cat > kitmail <<'WRAP'/,/^WRAP/p" "$HERE/platform/mac/mail/build.sh" | sed '1d;$d' > "$T/kitmail"
printf 'import sys\nif "--fail" in sys.argv: sys.exit("no-access: KitMessages needs Full Disk Access")\nprint("[]")\n' \
  > "$W/Claude/Agents/kit/.install/platform/mac/mail/kitmail_fast.py"
out="$(HOME="$W" zsh "$T/kitmail" inbox --hours 2 2>&1)"
[ "$out" = "[]" ] && grep -q "quick inbox ok" "$W/Claude/Agents/kit/.install/logs/mail.log" \
  && ok "kitmail inbox answers from the quick index and logs it" || bad "quick inbox: $out"
HOME="$W" zsh "$T/kitmail" inbox --fail > /dev/null 2>&1
grep -q "quick inbox unavailable (no-access" "$W/Claude/Agents/kit/.install/logs/mail.log" \
  && ok "a failed quick inbox is logged the way kit doctor reads it" || bad "quick inbox failure log"

echo "$pass passed, $fail failed"
[ $fail -eq 0 ]
