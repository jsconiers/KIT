#!/bin/bash
# Tests the installer's handling of Kit's staff: scaffold refreshes the agents in Kit's folder that
# the owner hasn't edited, keeps and reports the ones they have, keeps models.json's model lines,
# and copies the agents into ~/.claude/agents. Runs in a temp HOME. Run: bash tests/test_agents_install.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if [[ "$3" == *"$2"* ]]; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -30; fi; }

PKG="$T/pkg"; mkdir -p "$PKG"
cp -R "$HERE/shared" "$HERE/kit" "$PKG/"; cp "$HERE/VERSION" "$HERE/CHANGELOG.md" "$PKG/" 2>/dev/null
H="$T/home"; mkdir -p "$H"
run() { env -u KIT_SKILLS_DIR -u KIT_DIR HOME="$H" KIT_OWNER=Tester python3 "$PKG/shared/kit_setup.py" scaffold 2>&1; }
N="$(ls "$PKG/kit/agents/"*.md | wc -l | tr -d ' ')"
A="$H/Claude/Agents/kit/agents"; CA="$H/.claude/agents"

out="$(run)"
has "first scaffold adds every agent" "$N added, 0 updated, 0 already current, 0 kept" "$out"
has "first scaffold installs them for Claude Code" "$N installed, 0 updated, 0 already current." "$out"
cmp -s "$A/auditor.md" "$CA/auditor.md" && ok "agent copied into ~/.claude/agents" || bad "agent copied"
[ -f "$H/Claude/Agents/kit/.install/agents-installed.json" ] && ok "agent hashes recorded" || bad "agent hashes"

out="$(run)"
has "re-run changes nothing" "0 added, 0 updated, $N already current, 0 kept" "$out"
has "re-run leaves Claude Code's copies" "0 installed, 0 updated, $N already current." "$out"

# models.json sets a model line; the owner edits one agent; the package changes two agents
cat > "$H/Claude/Agents/kit/models.json" <<'JSON'
{"default_profile": "deep", "agents": {"auditor": "fast"},
 "providers": {"anthropic": {"kind": "anthropic"}},
 "profiles": {"deep": {"provider": "anthropic", "model": "opus"}, "fast": {"provider": "anthropic", "model": "haiku"}}}
JSON
python3 - "$A/auditor.md" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]); p.write_text(re.sub(r"(?m)^model:.*$", "model: haiku", p.read_text(), count=1))
PY
printf '\nMy own rule.\n' >> "$A/curator.md"
printf '\nA new packaged rule.\n' >> "$PKG/kit/agents/auditor.md"
printf '\nAnother packaged rule.\n' >> "$PKG/kit/agents/curator.md"
out="$(run)"
has "unedited agent refreshed, edited one kept" "0 added, 1 updated, $((N-2)) already current, 1 kept" "$out"
has "edited agent reported" "Kept agent curator" "$out"
grep -q "A new packaged rule." "$A/auditor.md" && ok "refreshed agent has the new text" || bad "refresh"
grep -q "^model: haiku" "$A/auditor.md" && ok "refresh keeps models.json's model line" || { bad "model line kept"; grep -n "^model" "$A/auditor.md"; }
grep -q "My own rule." "$A/curator.md" && ! grep -q "Another packaged rule." "$A/curator.md" \
  && ok "owner's edited agent untouched" || bad "owner's agent overwritten"
grep -q "A new packaged rule." "$CA/auditor.md" && grep -q "My own rule." "$CA/curator.md" \
  && ok "Claude Code gets the live agents" || bad "Claude Code copies"

# an install from before the hash record: the previous package copy is the baseline
rm "$H/Claude/Agents/kit/.install/agents-installed.json"
printf '\nThird rule.\n' >> "$PKG/kit/agents/auditor.md"
out="$(run)"
has "old install without a record still refreshes unedited agents" "1 updated" "$out"
grep -q "Third rule." "$A/auditor.md" && ok "refreshed from the previous package copy" || bad "baseline refresh"
has "edited agent still kept without a record" "Kept agent curator" "$out"

out="$(env -u KIT_DIR HOME="$H" python3 "$PKG/shared/kit_setup.py" agents 2>&1)"
has "agents command reports" "Kit's staff in $H/.claude/agents" "$out"

echo "$pass passed, $fail failed"
[ $fail -eq 0 ]
