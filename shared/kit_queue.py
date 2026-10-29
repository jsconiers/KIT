"""Read and change QUEUE.md: items, "updated" stamps, hygiene checks, and the sprint section.

Used by `todo`, `kit-queue`, and the dashboard. Standard library only.

Item lines look like `- [ ] **Title**: due DD-Mmm-YYYY (added DD-Mmm-YYYY, updated DD-Mmm-YYYY)`,
with detail and sub-items in lines indented two spaces. Sub-items are `  - [ ] text`.
"""
import datetime as dt
import math
import os
import pathlib
import re

KIT = pathlib.Path(os.path.expanduser(os.environ.get("KIT_DIR", "~/Claude/Agents/kit")))
QUEUE = KIT / "QUEUE.md"
DATE = r"\d{2}-[A-Z][a-z]{2}-\d{4}"
POINTS = {"S": 1, "M": 3, "L": 5}
EMPTY_SPRINT = "No sprint running. Start one with `todo sprint start <name> <start> <end>`."


def today():
    return dt.date.today()


def fmt(d):
    return d.strftime("%d-%b-%Y")


def parse_date(s):
    try:
        return dt.datetime.strptime(s, "%d-%b-%Y").date()
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- structure

def heads(lines):
    return {ln[3:].strip(): i for i, ln in enumerate(lines) if ln.startswith("## ")}


# The sections every queue has besides the owner's own (which the installer names for the owner).
SECTIONS = ("Sprint", "Kit", "Waiting on others", "Someday", "Done")


def configured_owner(config_text):
    """OWNER_NAME from the text of the config (shared/morning/config), or None when it isn't set."""
    m = re.search(r'^OWNER_NAME="?([^"\n]+)"?', config_text or "", re.M)
    return m.group(1).strip() if m and m.group(1).strip() else None


def owner_section(lines, configured=None):
    """The owner's section of QUEUE.md: `configured` (OWNER_NAME) when the queue has a section by that name,
    otherwise the queue's own owner section, the first that isn't one of SECTIONS. A fresh install has one
    named for its owner before OWNER_NAME is set, and a copied config can name someone else. None when the
    queue has neither."""
    names = [ln[3:].strip() for ln in lines if ln.startswith("## ")]
    if configured and configured in names:
        return configured
    return next((n for n in names if n not in SECTIONS), None)


def section_range(lines, name):
    h = heads(lines)
    if name not in h:
        return None
    end = min([i for i in h.values() if i > h[name]] + [len(lines)])
    return h[name], end


def blocks(lines, name, checked=False):
    """Items in a section as (start, end) line ranges, sub-lines included. Open items only, unless
    checked=True, which returns checked ones."""
    r = section_range(lines, name)
    if not r:
        return []
    mark = "- [x]" if checked else "- [ ]"
    found, i = [], r[0] + 1
    while i < r[1]:
        if lines[i].startswith(mark):
            j = i + 1
            while j < r[1] and lines[j].startswith("  "):
                j += 1
            found.append((i, j))
            i = j
        else:
            i += 1
    return found


def split_item(line):
    """(title, rest) from an item line, open or checked."""
    m = re.match(r"- \[[ x]\] \*\*(.+?)\*\*(.*)", line)
    if m:
        return m.group(1), m.group(2)
    return re.sub(r"^- \[[ x]\] ", "", line), ""


def dates_in(rest):
    added = re.search(r"added (" + DATE + ")", rest)
    updated = re.search(r"updated (" + DATE + ")", rest)
    done = re.search(r"(?:done|dropped) (" + DATE + ")", rest)
    return (parse_date(added.group(1)) if added else None,
            parse_date(updated.group(1)) if updated else None,
            parse_date(done.group(1)) if done else None)


def stamp(line, when=None):
    """Set or add "updated <date>" in an item line's trailing (added ...) note."""
    d = fmt(when or today())
    if re.search(r"updated " + DATE, line):
        return re.sub(r"updated " + DATE, f"updated {d}", line)
    # The last parenthesised note that mentions "added".
    m = None
    for m in re.finditer(r"\(([^()]*added " + DATE + r"[^()]*)\)", line):
        pass
    if m:
        return line[:m.end(1)] + f", updated {d}" + line[m.end(1):]
    return line.rstrip() + f" (updated {d})"


def open_items(lines, skip=("Done", "Sprint", "Someday")):
    """Every open item and sub-item, as dicts, in file order. Sections in skip are left out."""
    out = []
    for name, _ in sorted(heads(lines).items(), key=lambda kv: kv[1]):
        if name in skip:
            continue
        n = 0
        for (i, j) in blocks(lines, name):
            n += 1
            title, rest = split_item(lines[i])
            added, updated, _ = dates_in(rest)
            current = {"section": name, "n": n, "line": i, "end": j, "title": title, "rest": rest,
                       "added": added, "updated": updated, "parent": None, "sub": 0}
            out.append(current)
            s = 0
            for x in range(i + 1, j):
                sm = re.match(r"  - \[ \] (.+)", lines[x])
                if sm:
                    s += 1
                    out.append({"section": name, "n": n, "line": x, "end": x + 1, "title": sm.group(1).strip(),
                                "rest": "", "added": None, "updated": None, "parent": title, "sub": s})
    return out


def load(path=None):
    return (path or QUEUE).read_text().splitlines()


def write(lines, path=None):
    path = path or QUEUE
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines).rstrip("\n") + "\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- hygiene

STOP = set("""a an and the of for to in on with by at from into via or as is it its this that be
up out not no new set use using per each every all any first then than only also more most
item items merged merge done doc docs option options v1 v2 day days total phase eg e g i ie
one two three week weekly kit kits kit's""".split())


def tokens(text):
    text = re.sub(r"`[^`]*`", lambda m: m.group(0).replace("-", " ").replace("_", " "), text)
    text = re.sub(DATE, " ", text)
    toks = []
    for t in re.findall(r"[a-z][a-z0-9]*", text.lower()):
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        if t in STOP or len(t) < 3 or t.isdigit():
            continue
        toks.append(t)
    return set(toks)


def duplicates(items, ignore=(), threshold=0.85):
    """Likely duplicate or overlapping pairs, by IDF-weighted token overlap of their titles."""
    units = [(it, tokens(it["title"])) for it in items]
    df = {}
    for _, ts in units:
        for t in ts:
            df[t] = df.get(t, 0) + 1
    n = max(len(units), 1)
    idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
    pairs = []
    for a in range(len(units)):
        for b in range(a + 1, len(units)):
            (ia, ta), (ib, tb) = units[a], units[b]
            if not ta or not tb:
                continue
            if ia["parent"] == ib["title"] or ib["parent"] == ia["title"]:
                continue  # an item and its own sub-item
            common = ta & tb
            if not common:
                continue
            wc = sum(idf[t] for t in common)
            wa, wb = sum(idf[t] for t in ta), sum(idf[t] for t in tb)
            contain = wc / min(wa, wb)          # how much of the shorter title the other covers
            jaccard = wc / (wa + wb - wc)        # how alike the two are overall
            # Enough shared weight, or words only these two items use.
            weighty = wc >= 2.0 or all(df[t] <= 2 for t in common)
            score = max(contain if weighty else 0, jaccard)
            # Flag when one title is (almost) inside the other, or the two mostly match.
            if (contain >= threshold and weighty) or jaccard >= 0.8:
                key = "||".join(sorted([ia["title"], ib["title"]]))
                if key in ignore:
                    continue
                pairs.append((round(score, 2), ia, ib, sorted(common)))
    pairs.sort(key=lambda p: -p[0])
    return pairs


def week_of(d):
    return d - dt.timedelta(days=d.weekday())


def trend(lines, weeks=6):
    """Added and closed counts per week (Monday start) for the last `weeks` weeks."""
    t = today()
    starts = [week_of(t) - dt.timedelta(weeks=k) for k in range(weeks - 1, -1, -1)]
    added = {s: 0 for s in starts}
    closed = {s: 0 for s in starts}
    for ln in lines:
        if not re.match(r"\s*- \[[ x]\] ", ln):
            continue
        a, _, c = dates_in(ln)
        if a and week_of(a) in added:
            added[week_of(a)] += 1
        if ln.startswith("- [x]") and c and week_of(c) in closed:
            closed[week_of(c)] += 1
    return [{"week": fmt(s), "added": added[s], "closed": closed[s]} for s in starts]


def ref(it):
    return {"section": it["section"], "title": it["title"], "parent": it["parent"]}


def hygiene(lines, stale_days=7, ignore=()):
    items = open_items(lines)
    t = today()
    entries, k = [], 0
    for it in items:
        if it["parent"]:
            continue
        known = [d for d in (it["updated"], it["added"]) if d]
        if not known:
            continue
        last = max(known)
        age = (t - last).days
        if age >= stale_days:
            k += 1
            entries.append({"id": f"H{k}", "kind": "stale", "item": ref(it), "days": age,
                            "last_touched": fmt(last), "verdict": None})
    for score, a, b, common in duplicates(items, ignore):
        k += 1
        entries.append({"id": f"H{k}", "kind": "duplicate", "a": ref(a), "b": ref(b), "score": score,
                        "common": common, "verdict": None})
    top = [i for i in items if not i["parent"]]
    size = {}
    for i in items:
        s = size.setdefault(i["section"], {"items": 0, "sub_items": 0})
        s["sub_items" if i["parent"] else "items"] += 1
    return {"date": fmt(t), "stale_days": stale_days, "entries": entries, "trend": trend(lines),
            "size": size, "open_items": len(top), "open_sub_items": len(items) - len(top)}


# ---------------------------------------------------------------- finding and moving items

def find(lines, r):
    """Line index of the item a ref names, or None. Matches by section, title, and parent."""
    for it in open_items(lines):
        if it["title"] == r["title"] and it["section"] == r["section"] and it["parent"] == r.get("parent"):
            return it
    return None


def block_of(lines, it):
    if it["parent"]:
        return it["line"], it["line"] + 1
    return it["line"], it["end"]


def to_done(lines, title, note, sub_lines=()):
    h = heads(lines)
    if "Done" not in h:
        lines += ["", "## Done"]
        h = heads(lines)
    at = h["Done"] + 1
    lines[at:at] = [f"- [x] **{title}**: {note}"] + list(sub_lines)


def parent_line(lines, it):
    """Index of the top-level item line a sub-item belongs to."""
    i = it["line"]
    while i > 0 and lines[i].startswith("  "):
        i -= 1
    return i


# ---------------------------------------------------------------- sprint

def sprint(lines):
    """The sprint section: {'name','start','end','items':[...],'carry':[...]} or None if absent."""
    r = section_range(lines, "Sprint")
    if not r:
        return None
    out = {"name": None, "start": None, "end": None, "items": [], "carry": [], "range": r}
    in_carry = False
    for i in range(r[0] + 1, r[1]):
        ln = lines[i]
        m = re.match(r"Sprint (.+?): (" + DATE + ") to (" + DATE + ")", ln)
        if m:
            out.update(name=m.group(1), start=parse_date(m.group(2)), end=parse_date(m.group(3)))
            continue
        if ln.startswith("Carry-over"):
            in_carry = True
            continue
        im = re.match(r"- \[([ x])\] \*\*(.+?)\*\* \(([SML])\)(?: \[([^\]]*)\])?(.*)", ln)
        if im:
            item = {"line": i, "done": im.group(1) == "x", "title": im.group(2), "size": im.group(3),
                    "status": (im.group(4) or ("done" if im.group(1) == "x" else "open")).strip(),
                    "tail": im.group(5)}
            (out["carry"] if in_carry else out["items"]).append(item)
    return out


def sprint_points(sp):
    total = sum(POINTS[i["size"]] for i in sp["items"])
    done = sum(POINTS[i["size"]] for i in sp["items"] if i["done"])
    return total, done


def sprint_line(title, size, status, done=False, tail=""):
    return f"- [{'x' if done else ' '}] **{title}** ({size}) [{status}]{tail}"


def ensure_sprint_section(lines):
    """Add an empty ## Sprint section after the title block, before the first ## section."""
    if section_range(lines, "Sprint"):
        return lines
    h = heads(lines)
    at = min(h.values()) if h else len(lines)
    lines[at:at] = ["## Sprint", "", EMPTY_SPRINT, ""]
    return lines


def roadmap_subitems(lines):
    """Open sub-items of every Kit item whose title mentions "roadmap" (one roadmap, or a roadmap
    split into groups such as "Roadmap A: Connections"), in queue order, numbered from 1."""
    items = open_items(lines)
    groups = [it["title"] for it in items
              if not it["parent"] and it["section"] == "Kit" and "roadmap" in it["title"].lower()]
    return [s for g in groups for s in items if s["parent"] == g]
