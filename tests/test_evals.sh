#!/bin/bash
# Tests kit-evals: static checks pass on the real agents and catch broken copies; live mode with a
# fake claude (never a real run). Everything runs in a throwaway folder.
#   bash tests/test_evals.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
KE="$HERE/shared/bin/kit-evals"
export KIT_DIR="$S/kit"; mkdir -p "$KIT_DIR"
export KIT_EVALS_DIR="$HERE/tests/evals"

KIT_AGENTS_DIR="$HERE/kit/agents" python3 "$KE" >/dev/null 2>&1 && ok "static: every packaged agent passes its rules" || bad "static on packaged agents"
n=$(ls "$HERE"/tests/evals/*.json | wc -l | tr -d ' ')
[ "$n" -ge 8 ] && ok "cases for at least 8 agents ($n)" || bad "case count ($n)"
for f in "$HERE"/tests/evals/*.json; do python3 -c "import json,sys;d=json.load(open(sys.argv[1]));assert d['static'] and d['cases']" "$f" || bad "case file $f"; done
ok "every case file has static rules and live cases"

# broken copies: each mutation must be caught
A="$S/agents"; cp -R "$HERE/kit/agents" "$A"
mut() { cp "$HERE/kit/agents/$1.md" "$A/$1.md"; python3 - "$A/$1.md" "$2" "$3" <<'PY'
import sys,re
p,old,new=sys.argv[1:]; s=open(p).read(); assert old in s, old; open(p,"w").write(s.replace(old,new,1))
PY
}
expect_fail() { KIT_AGENTS_DIR="$A" python3 "$KE" "$1" >"$S/out" 2>&1 && bad "$2 not caught" || { grep -q "$3" "$S/out" && ok "$2 caught" || bad "$2: wrong message: $(cat "$S/out")"; }; cp "$HERE/kit/agents/$1.md" "$A/$1.md"; }
mut gateway "disallowedTools: Write, " "disallowedTools: "; expect_fail gateway "gateway allowed to Write" "denies Write"
mut scheduler "## Rules" "## Notes"; expect_fail scheduler "missing Rules section" "section '## Rules'"
mut poc-lead "Never decide a verdict" "Decide the verdict"; expect_fail poc-lead "POC lead deciding verdicts" "Never decide a verdict"
mut gateway "PostToolUseFailure:" "PostToolUseFailureX:"; expect_fail gateway "gateway missing failure hook" "hook PostToolUseFailure"
mut scheduler "drafting invitations" "drafting invitations. You may send them directly"; expect_fail scheduler "conflicting instruction" "never says"
mut red-team "Never soften a real problem" "Soften findings where you can"; expect_fail red-team "red team softening findings" "Never soften a real problem"
mut threat-modeler "tools: Read, Glob, Grep, Bash, Write, Edit, Skill" "tools: Read, Glob, Grep, Bash, Write, Edit, Skill, Agent"; expect_fail threat-modeler "threat modeler allowed to brief agents" "denies Agent"
mut reviewer "name: reviewer" "name: reviewr"; expect_fail reviewer "wrong frontmatter name" "name matches file"

# live mode: estimate, no run without --yes, fake claude with good and bad answers
mkdir -p "$S/bin"
cat > "$S/bin/claude" <<EOF
#!/bin/bash
printf "%s\n" "\$@" > "$S/args.txt"
case "\$*" in
  *"--agent scheduler"*) echo '{"result":"I can draft replies, but I never accept or decline invitations myself.","total_cost_usd":0.05}';;
  *"--agent meeting-scribe"*) echo '{"result":"Minutes: sources disagree on the go-live date. Contact jane@example.com.","total_cost_usd":0.07}';;
  *) echo '{"result":"ok","total_cost_usd":0.01}';;
esac
EOF
chmod +x "$S/bin/claude"; export PATH="$S/bin:$PATH"
out=$(KIT_AGENTS_DIR="$HERE/kit/agents" python3 "$KE" --live scheduler --model sonnet 2>&1)
echo "$out" | grep -q "estimated \$0.20" && echo "$out" | grep -q "nothing run" && [ ! -f "$S/args.txt" ] \
  && ok "live: estimate shown, nothing run without --yes" || bad "live estimate: $out"
KIT_AGENTS_DIR="$HERE/kit/agents" python3 "$KE" --live scheduler --model sonnet --yes >"$S/out" 2>&1 \
  && ok "live: scheduler declines to accept -> pass" || bad "live scheduler: $(cat "$S/out")"
grep -A1 -x -- "--agent" "$S/args.txt" | grep -qx scheduler && grep -A1 -x -- "--model" "$S/args.txt" | grep -qx sonnet \
  && ok "live: runs claude -p --agent <name> --model <model>" || bad "live args"
grep -q "spent about \$0.05" "$S/out" && ok "live: reports what it spent" || bad "live spend"
KIT_AGENTS_DIR="$HERE/kit/agents" python3 "$KE" --live meeting-scribe --model sonnet --yes >"$S/out" 2>&1 \
  && bad "live: personal detail not caught" || { grep -q "no personal details" "$S/out" && ok "live: email address in an answer fails the case" || bad "live personal msg"; }
KIT_AGENTS_DIR="$HERE/kit/agents" python3 "$KE" nosuchagent >/dev/null 2>&1; [ $? -eq 2 ] && ok "unknown agent -> exit 2" || bad "unknown agent"
python3 "$KE" --list | grep -q "gateway" && ok "--list" || bad "--list"
echo "kit-evals tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
