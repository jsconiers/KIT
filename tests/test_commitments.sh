#!/bin/bash
# Tests kit-commitments: promises found in your own text (fixtures only, no real mail), proposals
# written to briefs/pending-commitments.md, dedupe against QUEUE.md, and never touching the queue.
#   bash tests/test_commitments.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }
export KIT_DIR="$S/kit"
mkdir -p "$KIT_DIR/briefs"
cat > "$KIT_DIR/QUEUE.md" <<'EOF'
# Queue

## Alex

- [ ] **Review the firewall change** [work] (added 01-Oct-2026)

## Kit

## Done
EOF
cp "$KIT_DIR/QUEUE.md" "$S/queue-before.md"
KC="python3 $HERE/shared/bin/kit-commitments"

# Two messages in kitmail `read` format, plus one separated with "=== message".
cat > "$S/mail.txt" <<'EOF'
From:    Alex Example <alex@example.com>
Date:    Mon 19-Oct-2026 10:15
Subject: Re: GDS review
------------------------------------------------------------
Thanks for the notes. I'll send the updated GDS by Friday.
Let me know if that works. I'll be out Monday.

On Fri, someone <pm@example.com> wrote:
> I will send the budget tomorrow.
=== message
From:    Alex Example <alex@example.com>
Date:    Mon 19-Oct-2026 14:00
Subject: Licensing
Role:    vendor manager
------------------------------------------------------------
Let me get back to you on the licensing question next week. I will review the firewall change tomorrow.
I can have the draft to bob@example.com by 23-Oct.
EOF

out=$($KC scan --source mail --file "$S/mail.txt")
echo "$out" | grep -q "proposed" && ok "scan reports what it found" || bad "scan output: $out"
P="$KIT_DIR/briefs/pending-commitments.md"
[ -f "$P" ] && ok "proposals written to pending-commitments.md" || bad "no pending file"
grep -q "Send the updated GDS by Friday | recipient | 23-Oct-2026" "$P" && ok "promise with 'by Friday' resolved to the date" || bad "Friday commitment"
grep -q "Get back to you on the licensing question next week | vendor manager | 26-Oct-2026" "$P" \
  && ok "'let me get back to you next week' with the counterpart role from Role:" || bad "next week / role"
grep -q "Have the draft to \[address\] by 23-Oct | vendor manager | 23-Oct-2026" "$P" \
  && ok "'I can have ... by 23-Oct': action kept, address masked" || bad "23-Oct / masking"
grep -q "budget" "$P" && bad "quoted reply text was scanned" || ok "quoted replies below your text are skipped"
grep -qi "let me know\|be out" "$P" && bad "non-commitments captured" || ok "'let me know' and 'I'll be out' aren't commitments"
grep -qi "firewall" "$P" && bad "duplicate of a queue item proposed" || ok "a promise already in QUEUE.md isn't proposed again"
grep -q "alex@example.com\|Alex Example\|bob@" "$P" && bad "names or addresses leaked" || ok "no names or addresses in the proposals"
cmp -s "$S/queue-before.md" "$KIT_DIR/QUEUE.md" && ok "QUEUE.md is never changed by scan" || bad "queue changed"
[ "$(stat -f %Lp "$P" 2>/dev/null || stat -c %a "$P")" = "600" ] && ok "pending file is owner-only" || bad "pending perms"

n1=$(grep -c "^| C" "$P")
$KC scan --source mail --file "$S/mail.txt" >/dev/null
[ "$(grep -c "^| C" "$P")" = "$n1" ] && ok "a second scan doesn't duplicate proposals" || bad "rescan duplicated"

$KC list | grep -q "C1" && ok "list shows proposed rows" || bad "list"
out=$($KC mark C1 confirmed)
echo "$out" | grep -q "todo work" && grep -q "| C1 | confirmed |" "$P" && ok "mark confirmed records it and shows the todo command" || bad "mark: $out"
$KC mark C2 dropped >/dev/null && ! $KC list | grep -q " C2 " && ok "dropped rows leave the default list" || bad "drop"
$KC mark C99 dropped >/dev/null 2>&1 && bad "unknown id accepted" || ok "unknown id refused"
cmp -s "$S/queue-before.md" "$KIT_DIR/QUEUE.md" && ok "QUEUE.md still unchanged after mark" || bad "queue changed by mark"

printf 'Minutes 19-Oct\nI will circulate the minutes by Wednesday.\n' | $KC scan --source minutes --role "project manager" >/dev/null
grep -q "Circulate the minutes by Wednesday | project manager" "$P" && ok "minutes from stdin, role from --role" || bad "minutes/stdin"

grep -q "Commitments," "$HERE/shared/morning/prompt.md" && grep -q "Never quote mail" "$HERE/shared/morning/prompt.md" \
  && ok "morning prompt counts commitments without quoting mail" || bad "prompt"

echo "commitments tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
