#!/bin/bash
# Tests for shared/bin/kit-questions against synthetic drafts and notes. Run: bash tests/test_questions.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-questions"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if grep -qF -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -40; fi; }
hasnot() { if grep -qF -- "$2" <<<"$3"; then bad "$1"; echo "$3" | sed 's/^/     /' | head -40; else ok "$1"; fi; }
mkdir -p "$T/kit/memory/context" "$T/lib/artifacts/project-beta/intake"
export KIT_DIR="$T/kit"     # no library.md: --root or a folder path is used
P="$T/lib/artifacts/project-beta"
Q() { python3 "$TOOL" "$@"; }

cat > "$P/project-beta-ia-v1.md" <<'EOF'
# DOC-101 Impact assessment: project beta

## Summary of requirements

### Connectivity requirements
Files move from the billing service to the ledger over a managed file transfer endpoint.

### Recovery requirements
Recovery time and recovery point objectives for the payment store.

## Security architecture
Encryption of stored bank details and key rotation.

## Open questions
For the requester and the demand manager unless another owner is named.

1. Confirm the project name in the demand record.
2. Which payment option (card or transfer) will be used?
3. SRE: which protocol and endpoint carry files to the ledger, and who runs the transfer?
4. What are the recovery time and recovery point objectives for the payment store? (SRE)
5. Is the ledger interface in audit scope [S2 4.1]? (Owner: Compliance)
6. How are stored bank details encrypted,
   and where are the keys rotated? (Cybersecurity)
- What is the expected volume per day?

## Steps
1. Build the queue.
2. Is the queue in scope for this release?

## Risks
1. Cutoff could be missed?
EOF

# Word draft built on the fly: Heading2 section, literal numbers and an auto-numbered item
python3 - "$P/project-beta-gds-v0.1.docx" <<'EOF'
import sys, zipfile
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
def p(text, style=None, num=False):
    ppr = ""
    if style or num:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "") + \
              ('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>' if num else "") + "</w:pPr>"
    return f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"
body = "".join([
    p("DOC-202 Design specification", "Title"),
    p("Integration design", "Heading1"),
    p("The ledger interface uses a managed transfer endpoint.", "BodyText"),
    p("Vendor bank changes", "Heading2"),
    p("Approval of vendor bank changes follows the payments control.", "BodyText"),
    p("Open Questions", "Heading2"),
    p("1. Which protocol and endpoint carry files to the ledger, and who runs the transfer? (SRE)"),
    p("Who approves vendor bank changes? (AP)", num=True),
    p("Appendix", "Heading1"),
    p("2. Not a question in an appendix list."),
])
doc = f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body>{body}</w:body></w:document>'
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("[Content_Types].xml", "<Types/>")
    z.writestr("word/document.xml", doc)
EOF

cat > "$P/intake/triage-note.md" <<'EOF'
# Triage note: DOC-303

**Clarifying questions**

1. Who is the business sponsor?
2. When must the change be live? (Treasury)
EOF

# ---------- extract: read-only by default ----------
out="$(Q extract "$P/project-beta-ia-v1.md" --project "$P")"
has "extract counts" "9 questions in project-beta-ia-v1.md; 9 new, 0 already tracked" "$out"
has "read-only note" "(read-only; add --write to save)" "$out"
[ ! -e "$P/questions.md" ] && ok "nothing written without --write" || bad "nothing written without --write"

out="$(Q extract "$P/project-beta-ia-v1.md" --project project-beta --root "$T/lib" --write)"
has "project by name under --root" "artifacts/project-beta/questions.md" "$out"
trk="$(cat "$P/questions.md")"
row() { grep -- "^| $1 |" "$P/questions.md"; }
has "title" "# Open questions: project-beta" "$trk"
has "classification row" "| Classification |" "$trk"
has "header columns" "| Q-ID | Question | Source | Owner role | Asked | Due | Status | Answer | Answer source | Answer goes to |" "$trk"
has "intro line sets the default owner" "| requester |" "$(row Q-001)"
has "mid-sentence parenthesis is not an owner" "| requester |" "$(row Q-002)"
has "prefix owner hint" "| SRE |" "$(row Q-003)"
has "prefix hint removed from text" "| Which protocol and endpoint" "$(row Q-003)"
has "trailing owner hint" "| SRE |" "$(row Q-004)"
hasnot "trailing hint removed from text" "(SRE)" "$(row Q-004)"
has "(Owner: X) hint" "| Compliance |" "$(row Q-005)"
has "wrapped item joined" "encrypted, and where are the keys rotated?" "$(row Q-006)"
has "wrapped item owner" "| Cybersecurity |" "$(row Q-006)"
has "bullet in the section" "expected volume per day" "$(row Q-007)"
has "source document and section" "project-beta-ia-v1.md § DOC-101 Impact assessment: project beta > Open questions, item 3" "$(row Q-003)"
has "numbered ? outside the section" "Is the queue in scope for this release?" "$trk"
has "numbered ? in another section" "Cutoff could be missed?" "$trk"
hasnot "numbered statement outside not taken" "Build the queue" "$trk"
has "status open" "| open |" "$(row Q-001)"
has "answer goes to a suggested IA section" "IA § DOC-101 Impact assessment: project beta > Summary of requirements > Recovery requirements (suggested)" "$(row Q-004)"
hasnot "answer never routed to the questions section" "> Open questions (suggested)" "$trk"
has "summary by owner" "By owner role: requester" "$trk"
has "source stamped" "| Sources | project-beta-ia-v1.md (" "$trk"

# ---------- no duplicates; answers kept ----------
Q answer Q-004 "RTO 4 hours, RPO 15 minutes" --source "Email from SRE, 21-Oct-2026" --project "$P" --write >/dev/null
sed -i.bak 's/^4\. What are the recovery time/4) WHAT ARE THE RECOVERY TIME/; s/rotated? (Cybersecurity)/rotated (Cybersecurity)?/' "$P/project-beta-ia-v1.md"
out="$(Q extract "$P/project-beta-ia-v1.md" --project "$P" --write)"
has "re-extract adds nothing" "9 questions in project-beta-ia-v1.md; 0 new, 9 already tracked" "$out"
has "answer kept after re-extract" "| answered | RTO 4 hours, RPO 15 minutes | Email from SRE, 21-Oct-2026 |" "$(row Q-004)"

out="$(Q extract "$P/project-beta-gds-v0.1.docx" --project "$P" --write)"
has "docx: two questions found" "2 questions in project-beta-gds-v0.1.docx; 1 new, 1 already tracked" "$out"
has "docx: auto-numbered item and owner" "Q-010 [AP] Who approves vendor bank changes?" "$out"
hasnot "docx: appendix statement ignored" "Not a question" "$(cat "$P/questions.md")"
has "docx: GDS section suggested" "GDS § Integration design > Vendor bank changes (suggested)" "$(row Q-010)"

out="$(Q extract "$P/intake/triage-note.md" --project "$P" --write)"
has "intake: bold clarifying heading" "2 questions in triage-note.md; 2 new" "$out"
has "intake: clarifying defaults to requester" "| requester |" "$(row Q-011)"
has "intake: owner hint kept" "| Treasury |" "$(row Q-012)"
has "intake: source is relative to the project" "intake/triage-note.md § Triage note: DOC-303 > Clarifying questions, item 1" "$(row Q-011)"
has "intake: no keyword match falls back to the IA" "| IA: section to be chosen by the writer |" "$(row Q-012)"
n="$(grep -cE '^\| Q-[0-9]+ ' "$P/questions.md")"
[ "$n" = 12 ] && ok "12 questions tracked" || bad "12 questions tracked (got $n)"

# ---------- list ----------
out="$(Q list --project "$P" --owner sre)"
has "list filters by owner (case-insensitive)" "2 questions" "$out"
has "list shows status" "Q-004 [answered] (SRE)" "$out"
Q list --project "$P" --json | python3 -c '
import json, sys
d = json.load(sys.stdin)
r = {x["id"]: x for x in d["questions"]}
assert len(r) == 12, len(r)
assert set(r["Q-001"]) == {"id","question","source","owner","asked","due","status","answer","answer_source","goes_to"}, r["Q-001"].keys()
assert r["Q-005"]["owner"] == "Compliance" and r["Q-004"]["status"] == "answered"
' && ok "--json list shape" || bad "--json list shape"

# ---------- ask ----------
out="$(Q ask --project "$P" --due 01-Jan-2020)"
has "ask groups by owner" "## To: SRE (1)" "$out"
has "ask requester group" "## To: requester (" "$out"
has "ask says drafts only" "Nothing has been sent." "$out"
hasnot "answered question not asked" "Q-004:" "$out"
has "ask read-only" "(read-only; add --write" "$out"
ls "$P"/questions-ask-* >/dev/null 2>&1 && bad "ask writes nothing without --write" || ok "ask writes nothing without --write"
out="$(Q ask Q-003 Q-5,Q-006 --project "$P" --due 01-Jan-2020 --write)"
d="$(ls "$P"/questions-ask-*.md)"
has "ask saves a draft in the project folder" "wrote " "$out"; has "draft file name" "questions-ask-" "$d"
has "draft has Compliance group" "## To: Compliance (1)" "$(cat "$d")"
has "draft lists the ID" "1. Q-006: How are stored bank details" "$(cat "$d")"
has "a draft leaves the status open" "| 01-Jan-2020 | open |" "$(row Q-003)"
Q status Q-003 Q-5 Q-006 asked --project "$P" --write >/dev/null
has "asked status and dates after sending" "| 01-Jan-2020 | asked |" "$(row Q-003)"
Q ask Q-003 --project "$P" --write >/dev/null 2>&1 && bad "ask refuses to overwrite a draft" || ok "ask refuses to overwrite a draft"
Q ask Q-999 --project "$P" >/dev/null 2>&1 && bad "unknown ID refused" || ok "unknown ID refused"

# ---------- due ----------
out="$(Q due --project "$P")"
has "due lists overdue asked questions" "Q-003 [OVERDUE 01-Jan-2020] (SRE)" "$out"
hasnot "due skips open questions with no date" "Q-001" "$out"

# ---------- answer and apply ----------
out="$(Q answer Q-005 "Yes, in scope" --source "Compliance minutes, 22-Oct-2026" --project "$P")"
has "answer dry run" "Q-005 answered: Yes, in scope" "$out"
hasnot "answer dry run leaves the tracker" "Yes, in scope" "$(cat "$P/questions.md")"
Q answer Q-005 "Yes | in scope" --source "Compliance minutes, 22-Oct-2026" --goes-to "IA § Security architecture" --project "$P" --write >/dev/null
has "pipe in an answer is made safe" "| Yes / in scope |" "$(row Q-005)"
Q answer Q-005 "x" --source "  " --project "$P" >/dev/null 2>&1 && bad "blank source refused" || ok "blank source refused"
out="$(Q apply --project "$P")"
has "apply names the section" "- IA § Security architecture" "$out"
has "apply shows the answer and source" "Answer: Yes / in scope [source: Compliance minutes, 22-Oct-2026]" "$out"
has "apply includes the suggested section" "Recovery requirements (suggested)" "$out"
Q apply --project "$P" --json | python3 -c '
import json, sys
d = json.load(sys.stdin)
ids = [u["id"] for u in d["updates"]]
assert ids == ["Q-004", "Q-005"], ids
assert d["updates"][1]["goes_to"] == "IA § Security architecture"
' && ok "--json apply shape" || bad "--json apply shape"

# ---------- status ----------
Q status Q-004 closed --project "$P" --write >/dev/null
has "status closed" "| closed |" "$(row Q-004)"
Q status Q-001 maybe --project "$P" --write >/dev/null 2>&1 && bad "bad status refused" || ok "bad status refused"
out="$(Q apply --project "$P")"
hasnot "closed question leaves apply" "Q-004" "$out"

# ---------- hygiene ----------
Q list --project "$T/nope" >/dev/null 2>&1 && bad "missing project refused" || ok "missing project refused"
grep -qE 'urllib|requests|socket|http\.client|subprocess' "$TOOL" && bad "no network or subprocess use" || ok "no network or subprocess use"
python3 "$TOOL" --help | grep -q "never calls an outside service" && ok "help says it stays local" || bad "help says it stays local"

echo "questions tests: $pass passed, $fail failed"
[ "$fail" = 0 ]
