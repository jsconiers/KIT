#!/usr/bin/env python3
"""kit_teamviews: team views built from cached records, used by kit-team and team_dashboard.py.

  load_view(records, threshold, today)   open demands, IAs, GDSs, and POCs per Kit (by owner role):
                                         by kind, by stage, by due window, aging, and an overload flag
  experts(records, topic, today)         Kits ranked by evidence of experience on a topic, each with
                                         the record ids it rests on
  overload_threshold(kit)                Overload threshold from sharing.md (default 8)

Everything is by Kit id and owner role, never by name. Records are other Kits' information: these
functions count and cite them and never act on them.
"""
import datetime as dt
import math
import re
import statistics

DEFAULT_THRESHOLD = 8
KINDS = ("demand", "ia", "gds", "poc", "other")
WINDOWS = ("overdue", "7 days", "30 days", "later", "no date")
# How much one piece of evidence counts, before recency. Self-declared expertise is listed apart.
WEIGHTS = {"decision": 3.0, "artifact-pointer": 2.0, "lesson": 2.0, "handoff-pointer": 1.5,
           "demand-rollup": 1.0, "status-snapshot": 0.5}
LEVEL_POINTS = {"aware": 1, "working": 2, "expert": 3}
HALF_LIFE_DAYS = 365


def _date(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def overload_threshold(kit):
    """Overload threshold from sharing.md: open items per Kit at or above which it's flagged."""
    import kit_transport as kt
    raw = kt._setting_lines(kit / "memory/context/sharing.md").get("overload threshold", "")
    m = re.search(r"\d+", raw or "")
    return int(m.group(0)) if m else DEFAULT_THRESHOLD


def _window(due, today):
    d = _date(due)
    if d is None:
        return "no date"
    days = (d - today).days
    if days < 0:
        return "overdue"
    if days <= 7:
        return "7 days"
    if days <= 30:
        return "30 days"
    return "later"


def load_view(records, threshold=DEFAULT_THRESHOLD, today=None):
    """One row per Kit with demand roll-ups. Each row: kit_id, owner_role, open, by_kind, by_stage,
    due (windows), aging (max and median days open, how many items have no opened date), as_of (the
    newest roll-up date), stale_days, overloaded."""
    today = today or dt.date.today()
    rows = {}
    for r in records:
        if r.get("schema") != "demand-rollup":
            continue
        k = rows.setdefault(r["kit_id"], {
            "kit_id": r["kit_id"], "owner_role": r.get("owner_role", ""), "open": 0, "projects": set(),
            "by_kind": {x: 0 for x in KINDS}, "by_stage": {}, "due": {w: 0 for w in WINDOWS},
            "ages": [], "no_opened": 0, "as_of": None})
        body = r.get("body", {})
        a = _date(body.get("as_of"))
        if a and (k["as_of"] is None or a > k["as_of"]):
            k["as_of"] = a
        for it in body.get("items", []):
            if not it.get("open"):
                continue
            k["open"] += 1
            k["projects"].add(r.get("project", ""))
            kind = it.get("kind") if it.get("kind") in KINDS else "demand"
            k["by_kind"][kind] += 1
            stage = (it.get("stage") or it.get("status") or "unknown").strip().lower() or "unknown"
            k["by_stage"][stage] = k["by_stage"].get(stage, 0) + 1
            k["due"][_window(it.get("due"), today)] += 1
            o = _date(it.get("opened"))
            if o:
                k["ages"].append(max(0, (today - o).days))
            else:
                k["no_opened"] += 1
    out = []
    for k in rows.values():
        ages = k.pop("ages")
        k["aging"] = {"max_days": max(ages) if ages else None,
                      "median_days": int(statistics.median(ages)) if ages else None,
                      "unknown": k.pop("no_opened")}
        k["projects"] = sorted(p for p in k["projects"] if p)
        k["stale_days"] = (today - k["as_of"]).days if k["as_of"] else None
        k["as_of"] = k["as_of"].isoformat() if k["as_of"] else None
        k["overloaded"] = k["open"] >= threshold
        out.append(k)
    return sorted(out, key=lambda k: (-k["open"], k["kit_id"]))


# ---------- expertise ----------

def _words(text):
    return re.findall(r"[a-z0-9][a-z0-9+#.]*", (text or "").lower())


def _texts(r):
    """(text, label) pairs worth matching in one record, per type."""
    b = r.get("body", {})
    t = r.get("schema")
    if t == "decision":
        return [(" ".join(str(b.get(f, "")) for f in ("title", "summary", "why")) + " " +
                 " ".join(map(str, b.get("options", []) or [])), b.get("title", ""))]
    if t == "artifact-pointer":
        return [(" ".join(str(b.get(f, "")) for f in ("title", "type", "doc_number")), b.get("title", ""))]
    if t == "lesson":
        return [(" ".join(str(b.get(f, "")) for f in ("title", "rule", "how_to_apply")), b.get("title", ""))]
    if t == "handoff-pointer":
        return [(str(b.get("title", "")) + " " + str(b.get("where_it_stands", "")), b.get("title", ""))]
    if t == "demand-rollup":
        return [(str(it.get("title", "")), it.get("title", "")) for it in b.get("items", [])]
    if t == "status-snapshot":
        return [(str(b.get("headline", "")) + " " + " ".join(str(x) for x in b.get("in_progress", []) or []),
                 b.get("headline", ""))]
    return []


def _matches(text, terms):
    words = set(_words(text))
    return all(any(w == term or w.startswith(term) for w in words) for term in terms)


def _recency(r, today):
    d = _date(r.get("updated")) or _date(r.get("created")) or today
    return 0.5 ** (max(0, (today - d).days) / HALF_LIFE_DAYS)


def experts(records, topic, today=None, per_kit=5):
    """Kits ranked by evidence on a topic. Each: kit_id, owner_role, score, evidence (count),
    citations (up to per_kit: record id, type, label, date), declared (self-declared level, or None).
    An empty list means no evidence in the cache."""
    today = today or dt.date.today()
    terms = _words(topic)
    if not terms:
        return []
    kits = {}
    for r in records:
        t = r.get("schema")
        if t == "expertise":
            for tp in r.get("body", {}).get("topics", []):
                if _matches(tp.get("topic", ""), terms):
                    k = kits.setdefault(r["kit_id"], {"kit_id": r["kit_id"], "owner_role": r.get("owner_role", ""),
                                                      "score": 0.0, "evidence": 0, "citations": [], "declared": None})
                    lvl = tp.get("level")
                    if k["declared"] is None or LEVEL_POINTS.get(lvl, 0) > LEVEL_POINTS.get(k["declared"], 0):
                        k["declared"] = lvl
            continue
        if t not in WEIGHTS:
            continue
        hits = [label for text, label in _texts(r) if _matches(text, terms)]
        if not hits:
            continue
        k = kits.setdefault(r["kit_id"], {"kit_id": r["kit_id"], "owner_role": r.get("owner_role", ""),
                                          "score": 0.0, "evidence": 0, "citations": [], "declared": None})
        k["score"] += WEIGHTS[t] * _recency(r, today) * (1 + math.log(len(hits)))
        k["evidence"] += len(hits)
        k["citations"].append({"id": r["id"], "type": t, "label": str(hits[0])[:80],
                               "date": (r.get("updated") or "")[:10]})
    out = []
    for k in kits.values():
        k["citations"].sort(key=lambda c: (WEIGHTS.get(c["type"], 0), c["date"]), reverse=True)
        k["citations"] = k["citations"][:per_kit]
        k["score"] = round(k["score"], 2)
        out.append(k)
    # Evidence first; a Kit with only a self-declared level comes after Kits with records.
    return sorted(out, key=lambda k: (-k["score"], -LEVEL_POINTS.get(k["declared"] or "", 0), k["kit_id"]))
