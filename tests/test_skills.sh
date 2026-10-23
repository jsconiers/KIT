#!/bin/bash
# Tests Kit's skills (kit/skills/*/SKILL.md): valid frontmatter, the installer copying them into
# ~/.claude/skills without overwriting the owner's own, and kit-plugin packaging them.
# Runs in a temp HOME. Run: bash tests/test_skills.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if [[ "$3" == *"$2"* ]]; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -30; fi; }

# ---- frontmatter ----
for want in exec-summary requirements-extraction; do
  [ -f "$HERE/kit/skills/$want/SKILL.md" ] && ok "skill $want ships" || bad "skill $want ships"
done
out="$(python3 - "$HERE/kit/skills" <<'PY' 2>&1
import pathlib, re, sys
probs, n = [], 0
for f in sorted(pathlib.Path(sys.argv[1]).glob("*/SKILL.md")):
    n += 1
    text = f.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        probs.append(f"{f.parent.name}: no frontmatter block"); continue
    fm = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if not sep or not re.fullmatch(r"[a-z][a-z-]*", k.strip()):
            probs.append(f"{f.parent.name}: bad frontmatter line {line!r}"); continue
        fm[k.strip()] = v.strip().strip('"')
    if fm.get("name") != f.parent.name:
        probs.append(f"{f.parent.name}: name {fm.get('name')!r} doesn't match the folder")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", fm.get("name", "")):
        probs.append(f"{f.parent.name}: name isn't kebab-case")
    d = fm.get("description", "")
    if not (40 <= len(d) <= 1024):
        probs.append(f"{f.parent.name}: description is {len(d)} characters (want 40-1024)")
    if "<" in d or ">" in d:
        probs.append(f"{f.parent.name}: description has angle brackets")
    if not re.search(r"(?m)^# ", m.group(2)):
        probs.append(f"{f.parent.name}: no heading after the frontmatter")
    if not re.search(r"(?m)^## Checklist", m.group(2)):
        probs.append(f"{f.parent.name}: no checklist")
    if re.search(r"\b(IA|GDS)-\d{3}\b", text):
        probs.append(f"{f.parent.name}: uses a team-specific document number")
print("\n".join(probs) if probs else f"frontmatter-ok {n}")
PY
)"
has "every SKILL.md has valid frontmatter, a heading, and a checklist" "frontmatter-ok" "$out"
grep -q "BR-" "$HERE/kit/skills/requirements-extraction/SKILL.md" && grep -q "NFR-" "$HERE/kit/skills/requirements-extraction/SKILL.md" \
  && ok "requirements-extraction uses BR-/FR-/NFR- IDs" || bad "requirement ID series"
grep -qi "lead with the answer" "$HERE/kit/skills/exec-summary/SKILL.md" && ok "exec-summary leads with the answer" || bad "exec-summary rule"

# ---- installer: fresh install ----
H="$T/home"; mkdir -p "$H"
SETUP="$HERE/shared/kit_setup.py"
run() { env -u KIT_SKILLS_DIR HOME="$H" KIT_OWNER=Tester python3 "$SETUP" skills 2>&1; }
SK="$H/.claude/skills"
out="$(run)"
has "first run installs both skills" "2 installed, 0 updated, 0 already current" "$out"
cmp -s "$HERE/kit/skills/exec-summary/SKILL.md" "$SK/exec-summary/SKILL.md" && ok "skill copied as shipped" || bad "skill copied"
[ -f "$SK/exec-summary/.kit-installed.json" ] && ok "install marker written" || bad "install marker"
out="$(run)"
has "re-run leaves them as they are" "0 installed, 0 updated, 2 already current" "$out"

# ---- installer: never overwrite the owner's skills ----
printf -- '---\nname: exec-summary\ndescription: my own\n---\n# Mine\n' > "$SK/exec-summary/SKILL.md"   # edited since install
rm -rf "$SK/requirements-extraction"; mkdir -p "$SK/requirements-extraction"
printf -- '---\nname: requirements-extraction\ndescription: the owner wrote this one\n---\n# Theirs\n' > "$SK/requirements-extraction/SKILL.md"
out="$(run)"
has "edited skill skipped and reported" "Skipped skill exec-summary" "$out"
has "owner's same-named skill skipped and reported" "Skipped skill requirements-extraction" "$out"
grep -q "# Mine" "$SK/exec-summary/SKILL.md" && ok "edited skill not overwritten" || bad "edited skill overwritten"
grep -q "# Theirs" "$SK/requirements-extraction/SKILL.md" && ok "owner's skill not overwritten" || bad "owner's skill overwritten"
[ ! -f "$SK/requirements-extraction/.kit-installed.json" ] && ok "no marker added to the owner's skill" || bad "marker on owner's skill"

# ---- installer: Kit's own unedited copy is refreshed when Kit's version changes ----
H2="$T/home2"; mkdir -p "$H2"; PKG="$T/pkg"; mkdir -p "$PKG"
cp -R "$HERE/shared" "$HERE/kit" "$PKG/"; cp "$HERE/VERSION" "$PKG/" 2>/dev/null
env -u KIT_SKILLS_DIR HOME="$H2" python3 "$PKG/shared/kit_setup.py" skills > /dev/null 2>&1
printf '\nOne more rule.\n' >> "$PKG/kit/skills/exec-summary/SKILL.md"
out="$(env -u KIT_SKILLS_DIR HOME="$H2" python3 "$PKG/shared/kit_setup.py" skills 2>&1)"
has "unedited Kit skill refreshed" "0 installed, 1 updated, 1 already current" "$out"
grep -q "One more rule." "$H2/.claude/skills/exec-summary/SKILL.md" && ok "refreshed copy has the new text" || bad "refresh"

# ---- KIT_SKILLS_DIR and scaffold ----
out="$(KIT_SKILLS_DIR="$T/alt" HOME="$H2" python3 "$SETUP" skills 2>&1)"
[ -f "$T/alt/requirements-extraction/SKILL.md" ] && ok "KIT_SKILLS_DIR honoured" || { bad "KIT_SKILLS_DIR"; echo "$out"; }
H3="$T/home3"; mkdir -p "$H3/.claude/skills/exec-summary"
printf -- '---\nname: exec-summary\ndescription: preexisting\n---\n# Pre\n' > "$H3/.claude/skills/exec-summary/SKILL.md"
out="$(env -u KIT_SKILLS_DIR HOME="$H3" KIT_OWNER=Tester python3 "$SETUP" scaffold 2>&1)"
has "scaffold installs skills too" "Kit's skills in" "$out"
has "scaffold reports what it skipped" "Skipped skill exec-summary" "$out"
[ -f "$H3/.claude/skills/requirements-extraction/SKILL.md" ] && grep -q "# Pre" "$H3/.claude/skills/exec-summary/SKILL.md" \
  && ok "scaffold copies new skills and keeps the existing one" || bad "scaffold skills"

# ---- kit-plugin packages Kit's skills even before they're installed ----
M="$T/market"
out="$(KIT_DIR="$T/kitdir" KIT_SKILLS_DIR="$T/empty-skills" python3 "$HERE/shared/bin/kit-plugin" build writing-pack \
  --skills exec-summary,requirements-extraction --marketplace "$M" 2>&1)"
[ -f "$M/plugins/writing-pack/skills/exec-summary/SKILL.md" ] && [ -f "$M/plugins/writing-pack/skills/requirements-extraction/SKILL.md" ] \
  && ok "kit-plugin packages kit/skills" || { bad "kit-plugin packages kit/skills"; echo "$out" | head; }
[ ! -e "$M/plugins/writing-pack/skills/exec-summary/.kit-installed.json" ] && ok "install marker not packaged" || bad "marker packaged"

echo "$pass passed, $fail failed"
[ $fail -eq 0 ]
