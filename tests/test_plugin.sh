#!/bin/bash
# Tests kit-plugin: build a marketplace from fixture Kit content, then check it: clean passes; a
# planted denylist term, an unshared lesson, and an unreviewed hook each fail. Throwaway folders only.
#   bash tests/test_plugin.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P="$HERE/shared/bin/kit-plugin"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
export KIT_DIR="$S/kit" KIT_SKILLS_DIR="$S/skills"
mkdir -p "$KIT_DIR/lessons" "$KIT_SKILLS_DIR/diagram-helper/scripts"
printf 'share: team\n# Check dates first\n\nCheck the document date before citing it.\n\n**Why:** old copies.\n\n**How to apply:** look first.\n' > "$KIT_DIR/lessons/check-dates.md"
printf '# Private habit\n\nA personal rule.\n' > "$KIT_DIR/lessons/private-habit.md"
printf -- '---\nname: diagram-helper\ndescription: Helps with diagrams.\n---\n# Diagram helper\nUse the script.\n' > "$KIT_SKILLS_DIR/diagram-helper/SKILL.md"
printf '#!/bin/sh\necho hi\n' > "$KIT_SKILLS_DIR/diagram-helper/scripts/run.sh"; chmod +x "$KIT_SKILLS_DIR/diagram-helper/scripts/run.sh"
DENY="$S/deny.txt"; printf '# planted term for the test\nacmeinternal\n' > "$DENY"
M="$S/marketplace"

# ---- build ----
python3 "$P" build arch-pack --agents precedent-finder,poc-lead --templates poc-charter-template,adr-template \
  --lessons check-dates --marketplace "$M" --author-role "solutions architect" > "$S/out.txt" 2>&1 \
  && ok "build a plugin with agents, templates, and a shared lesson" || { bad "build"; cat "$S/out.txt"; }
R="$M/plugins/arch-pack"
[ -f "$R/.claude-plugin/plugin.json" ] && [ -f "$R/agents/poc-lead.md" ] && [ -f "$R/skills/arch-pack-templates/poc-charter-template.md" ] \
  && [ -f "$R/skills/arch-pack-lessons/SKILL.md" ] && [ -f "$R/REVIEW.md" ] && ok "plugin layout: manifest, agents/, skills/, REVIEW.md" || bad "layout"
python3 - "$R" "$M" <<'PY' && ok "manifests: name, version, author role, license placeholder; marketplace entry" || echo "FAIL manifests" >&2
import json, sys, pathlib
r, m = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
p = json.loads((r / ".claude-plugin/plugin.json").read_text())
mk = json.loads((m / ".claude-plugin/marketplace.json").read_text())
assert p["name"] == "arch-pack" and p["version"] == "0.1.0" and p["author"]["name"] == "solutions architect"
assert p["license"] == "LicenseRef-TBD"
assert mk["owner"]["name"] and mk["plugins"][0] == {"name": "arch-pack", "source": "./plugins/arch-pack",
                                                    "description": p["description"], "version": "0.1.0"}
PY
grep -q "share: team source: check-dates.md" "$R/skills/arch-pack-lessons/SKILL.md" && ok "lesson carries the share: team mark" || bad "lesson mark"
python3 "$P" build bad --lessons private-habit --marketplace "$M" > "$S/o2.txt" 2>&1
[ $? -ne 0 ] && grep -q "isn't tagged share: team" "$S/o2.txt" && ok "build refuses a lesson not tagged share: team" || bad "unshared lesson at build"
python3 "$P" build claude-tools --agents poc-lead --marketplace "$M" > /dev/null 2>&1
[ $? -ne 0 ] && ok "build refuses a reserved plugin name" || bad "reserved name"

# ---- check ----
python3 "$P" check "$M" --denylist "$DENY" > "$S/c1.txt" 2>&1 && grep -q "0 problem" "$S/c1.txt" \
  && ok "check passes a clean marketplace" || { bad "clean check"; cat "$S/c1.txt"; }
python3 "$P" check "$R" --denylist "$DENY" > /dev/null 2>&1 && ok "check works on a single plugin too" || bad "single plugin check"

cp -R "$M" "$S/m-deny"
echo "Ask the AcmeInternal platform team first." >> "$S/m-deny/plugins/arch-pack/skills/arch-pack-templates/adr-template.md"
python3 "$P" check "$S/m-deny" --denylist "$DENY" > "$S/c2.txt" 2>&1
[ $? -eq 1 ] && grep -q "public denylist" "$S/c2.txt" && ok "check fails on a planted denylist term" || { bad "denylist"; cat "$S/c2.txt"; }

cp -R "$M" "$S/m-cred"
echo '{"api_token": "abcdefgh12345"}' > "$S/m-cred/plugins/arch-pack/skills/arch-pack-templates/settings.json"
python3 "$P" check "$S/m-cred" --denylist "$DENY" > "$S/c3.txt" 2>&1
[ $? -eq 1 ] && grep -qi "credential" "$S/c3.txt" && ok "check fails on a credential-looking value" || { bad "credential"; cat "$S/c3.txt"; }

cp -R "$M" "$S/m-lesson"
printf '\n## private-habit\n\nA personal rule.\n' >> "$S/m-lesson/plugins/arch-pack/skills/arch-pack-lessons/SKILL.md"
python3 "$P" check "$S/m-lesson" --denylist "$DENY" > "$S/c4.txt" 2>&1
[ $? -eq 1 ] && grep -q "share: team" "$S/c4.txt" && ok "check fails on a lesson without the share: team mark" || { bad "unshared lesson"; cat "$S/c4.txt"; }

cp -R "$M" "$S/m-hook"
mkdir -p "$S/m-hook/plugins/arch-pack/hooks"
echo '{"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}' > "$S/m-hook/plugins/arch-pack/hooks/hooks.json"
python3 "$P" check "$S/m-hook" --denylist "$DENY" > "$S/c5.txt" 2>&1
[ $? -eq 1 ] && grep -q "need a person's review" "$S/c5.txt" && ok "check fails on an unreviewed hook" || { bad "unreviewed hook"; cat "$S/c5.txt"; }
sed -i.bak 's/^- \[ \] Hooks, scripts, and servers reviewed by: <role>, <YYYY-MM-DD>/- [x] Hooks, scripts, and servers reviewed by: security reviewer, 2026-10-19/' "$S/m-hook/plugins/arch-pack/REVIEW.md"
python3 "$P" check "$S/m-hook" --denylist "$DENY" > "$S/c6.txt" 2>&1 && ok "a recorded review clears the hook" || { bad "review clears"; cat "$S/c6.txt"; }

python3 "$P" build tools-pack --skills diagram-helper --marketplace "$S/m-skill" > /dev/null 2>&1
python3 "$P" check "$S/m-skill" --denylist "$DENY" > "$S/c7.txt" 2>&1
[ $? -eq 1 ] && grep -q "run.sh" "$S/c7.txt" && ok "a skill's script is flagged for review" || { bad "skill script"; cat "$S/c7.txt"; }

cp -R "$M" "$S/m-mismatch"
python3 - "$S/m-mismatch" <<'PY'
import json, sys, pathlib
m = pathlib.Path(sys.argv[1]) / ".claude-plugin/marketplace.json"
d = json.loads(m.read_text()); d["plugins"][0]["name"] = "other-name"; m.write_text(json.dumps(d))
PY
python3 "$P" check "$S/m-mismatch" --denylist "$DENY" > "$S/c8.txt" 2>&1
[ $? -eq 1 ] && grep -q "differs from its manifest name" "$S/c8.txt" && ok "entry and manifest names must match" || bad "name mismatch"

# ---- list ----
python3 "$P" list --marketplace "$M" > "$S/l.txt" 2>&1 && grep -q "arch-pack" "$S/l.txt" && grep -q "no hooks or scripts" "$S/l.txt" \
  && ok "list shows plugins and review state" || { bad "list"; cat "$S/l.txt"; }
grep -rq "git push\|subprocess.run(\[\"git\"" "$P" && bad "kit-plugin never pushes" || ok "kit-plugin never pushes or publishes"

echo "kit-plugin tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
