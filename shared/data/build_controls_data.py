#!/usr/bin/env python3
"""Rebuild kit-controls' data files from public sources you have already downloaded.

  python3 -I build_controls_data.py --nist DIR --attack FILE --ctid FILE [--out DIR] [--date DD-Mmm-YYYY]

  --nist DIR     a folder holding the NIST SP 800-53 Rev 5 OSCAL catalog and baseline profiles (JSON),
                 from github.com/usnistgov/oscal-content, nist.gov/SP800-53/rev5/json/:
                 NIST_SP-800-53_rev5_catalog.json and NIST_SP-800-53_rev5_{LOW,MODERATE,HIGH,PRIVACY}-
                 baseline_profile.json
  --attack FILE  the Enterprise ATT&CK STIX 2.x bundle, github.com/mitre/cti,
                 enterprise-attack/enterprise-attack.json (pin a release tag)
  --ctid FILE    the Center for Threat-Informed Defense Mappings Explorer ATT&CK-to-NIST 800-53 Rev 5
                 mapping (JSON), github.com/center-for-threat-informed-defense/mappings-explorer,
                 mappings/nist_800_53/attack-<v>/nist_800_53-rev5/enterprise/
  --out DIR      where to write (default: this folder)

Writes nist-800-53r5.json, mitre-attack-enterprise.json, and attack-to-800-53.json: IDs, names, titles,
and a one-line summary of each 800-53 control statement, never the full prose. It reads only the
files you give it, downloads nothing, and runs nothing it reads. Fill in the source URLs and commits
in SOURCES below when you refresh, then run tests/test_controls.sh.
"""
import argparse
import datetime
import json
import pathlib
import re
import sys

SOURCES = {
    "nist": {"repo": "https://github.com/usnistgov/oscal-content",
             "path": "nist.gov/SP800-53/rev5/json/",
             "commit": "f0de6d8d8c059d374f15e0ae07508d82e370fc1d"},
    "attack": {"repo": "https://github.com/mitre/cti",
               "path": "enterprise-attack/enterprise-attack.json",
               "tag": "ATT&CK-v20.0",
               "commit": "50be388e93819a5d20e71cbaaeccfda157abc846"},
    "ctid": {"repo": "https://github.com/center-for-threat-informed-defense/mappings-explorer",
             "path": "mappings/nist_800_53/attack-16.1/nist_800_53-rev5/enterprise/"
                     "nist_800_53-rev5_attack-16.1-enterprise.json",
             "commit": "a85e55af3c9fa55359a98621745b9b039a088bec"},
}

MITRE_NOTICE = ("© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission "
                "of The MITRE Corporation.")
MITRE_LICENSE = ("The MITRE Corporation (MITRE) hereby grants you a non-exclusive, royalty-free license to use "
                 "ATT&CK® for research, development, and commercial purposes. Any copy you make for such "
                 "purposes is authorized provided that you reproduce MITRE's copyright designation and this "
                 "license in any such copy.")
MITRE_DISCLAIMER = ("MITRE does not claim ATT&CK enumerates all possibilities for the types of actions and "
                    "behaviors documented as part of its adversary model and framework of techniques. Using the "
                    "information contained within ATT&CK to address or cover full categories of techniques will "
                    "not guarantee full defensive coverage as there may be undisclosed techniques or variations "
                    "on existing techniques not documented by ATT&CK. ALL DOCUMENTS AND THE INFORMATION "
                    "CONTAINED THEREIN ARE PROVIDED ON AN \"AS IS\" BASIS; see the LICENSE.txt in "
                    "github.com/mitre/cti for the full disclaimer.")
SUMMARY_MAX = 200


def label(ctl):
    """'ac-2' -> 'AC-2', 'ac-2.1' -> 'AC-2(1)'."""
    m = re.fullmatch(r"([a-z]{2})-(\d+)(?:\.(\d+))?", ctl)
    if not m:
        return ctl.upper()
    return f"{m.group(1).upper()}-{int(m.group(2))}" + (f"({int(m.group(3))})" if m.group(3) else "")


def norm_ctid(cid):
    """'AC-02' -> 'AC-2', 'AC-02(01)' -> 'AC-2(1)'."""
    m = re.fullmatch(r"([A-Z]{2})-0*(\d+)(?:\s*\(0*(\d+)\))?", cid.strip().upper())
    if not m:
        return cid.strip().upper()
    return f"{m.group(1)}-{m.group(2)}" + (f"({m.group(3)})" if m.group(3) else "")


def prop(obj, name):
    for p in obj.get("props", []):
        if p["name"] == name and "class" not in p:
            return p["value"]
    return None


def params_of(ctl, inherited):
    out = dict(inherited)
    for p in ctl.get("params", []):
        if "select" in p:
            ch = p["select"].get("choice", [])
            out[p["id"]] = "[Selection: " + "; ".join(ch) + "]" if ch else "[Selection]"
        elif p.get("label"):
            out[p["id"]] = f"[organization-defined {p['label']}]"
        else:
            out[p["id"]] = "[Assignment]"
    return out


def fill(prose, params):
    def sub(m):
        return params.get(m.group(1), "[Assignment]")
    s = re.sub(r"\{\{\s*insert:\s*param,\s*([^\s}]+)\s*\}\}", sub, prose)
    return re.sub(r"\s+", " ", s).strip()


def summary(ctl, params):
    st = next((p for p in ctl.get("parts", []) if p.get("name") == "statement"), None)
    if not st:
        return ""
    if st.get("prose"):
        text = fill(st["prose"], params)
    else:
        items = [fill(p.get("prose", ""), params) for p in st.get("parts", []) if p.get("prose")]
        items = items[:1] + [i[0].lower() + i[1:] if len(i) > 1 and i[1].islower() else i for i in items[1:]]
        text = " ".join(items)
    if len(text) <= SUMMARY_MAX:
        return text
    cut = text[:SUMMARY_MAX].rsplit(" ", 1)[0].rstrip(" ;,:")
    return cut + " …"


def build_nist(d, date):
    cat = json.loads((d / "NIST_SP-800-53_rev5_catalog.json").read_text(encoding="utf-8-sig"))["catalog"]
    baselines = {}
    for name in ("LOW", "MODERATE", "HIGH", "PRIVACY"):
        f = d / f"NIST_SP-800-53_rev5_{name}-baseline_profile.json"
        prof = json.loads(f.read_text(encoding="utf-8-sig"))["profile"]
        ids = set()
        for imp in prof.get("imports", []):
            for inc in imp.get("include-controls", []):
                ids.update(inc.get("with-ids", []))
        baselines[name.lower()] = ids
    order = ("low", "moderate", "high", "privacy")
    families, controls = [], []
    for g in cat["groups"]:
        families.append({"id": g["id"].upper(), "title": g["title"]})
        for c in g.get("controls", []):
            withdrawn = prop(c, "status") == "withdrawn"
            prm = params_of(c, {})
            rec = {"id": label(c["id"]), "family": g["id"].upper(), "title": c["title"]}
            if withdrawn:
                rec["withdrawn"] = True
            else:
                rec["summary"] = summary(c, prm)
            bl = [b for b in order if c["id"] in baselines[b]]
            if bl:
                rec["baselines"] = bl
            enh = []
            for e in c.get("controls", []):
                er = {"id": label(e["id"]), "title": e["title"]}
                if prop(e, "status") == "withdrawn":
                    er["withdrawn"] = True
                ebl = [b for b in order if e["id"] in baselines[b]]
                if ebl:
                    er["baselines"] = ebl
                enh.append(er)
            if enh:
                rec["enhancements"] = enh
            controls.append(rec)
    md = cat["metadata"]
    base = SOURCES["nist"]["repo"].replace("github.com", "raw.githubusercontent.com") + "/" + \
        SOURCES["nist"]["commit"] + "/" + SOURCES["nist"]["path"]
    return {
        "framework": "NIST SP 800-53 Rev 5",
        "version": md.get("version"),
        "source": f"NIST SP 800-53 Rev 5 OSCAL catalog, version {md.get('version')}, "
                  f"last modified {md.get('last-modified', '')[:10]}",
        "source_urls": [base + "NIST_SP-800-53_rev5_catalog.json"] +
                       [base + f"NIST_SP-800-53_rev5_{b}-baseline_profile.json"
                        for b in ("LOW", "MODERATE", "HIGH", "PRIVACY")],
        "source_repo_commit": SOURCES["nist"]["commit"],
        "retrieved": date,
        "licence": "Public domain: a work of the US government (NIST), not subject to copyright in the United "
                   "States. Derived and abridged by Kit; read the catalog for the full control text.",
        "note": "Control IDs, families, titles, a one-line summary of each control statement from the catalog's "
                "own text (shortened, with parameters shown in brackets), baseline membership (low, moderate, "
                "and high security baselines, and the privacy baseline, from SP 800-53B as published in OSCAL), "
                "and each control's enhancements as IDs and titles. No discussion, guidance, or assessment text.",
        "families": families,
        "controls": controls,
    }


def ext_id(o):
    for r in o.get("external_references", []):
        if r.get("source_name") == "mitre-attack" and r.get("external_id"):
            return r["external_id"]
    return None


def build_attack(path, date):
    b = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    objs = b["objects"]
    live = lambda o: not o.get("revoked") and not o.get("x_mitre_deprecated")
    tactics, by_stix_t, by_stix_m, techniques, mitigations = [], {}, {}, {}, {}
    matrix = next((o for o in objs if o["type"] == "x-mitre-matrix"), {})
    tactic_order = matrix.get("tactic_refs", [])
    tac = {o["id"]: o for o in objs if o["type"] == "x-mitre-tactic" and live(o)}
    for ref in tactic_order + [k for k in tac if k not in tactic_order]:
        o = tac.get(ref)
        if o:
            tactics.append({"id": ext_id(o), "shortname": o["x_mitre_shortname"], "name": o["name"]})
    for o in objs:
        if o["type"] == "attack-pattern" and live(o):
            tid = ext_id(o)
            if not tid:
                continue
            by_stix_t[o["id"]] = tid
            techniques[tid] = {"id": tid, "name": o["name"],
                               "tactics": [k["phase_name"] for k in o.get("kill_chain_phases", [])
                                           if k.get("kill_chain_name") == "mitre-attack"],
                               "platforms": o.get("x_mitre_platforms", [])}
        elif o["type"] == "course-of-action" and live(o):
            mid = ext_id(o)
            if mid and mid.startswith("M"):
                by_stix_m[o["id"]] = mid
                mitigations[mid] = {"id": mid, "name": o["name"]}
    links = set()
    for o in objs:
        if o["type"] == "relationship" and o.get("relationship_type") == "mitigates" and live(o):
            m, t = by_stix_m.get(o["source_ref"]), by_stix_t.get(o["target_ref"])
            if m and t:
                links.add((t, m))
    for t, m in links:
        techniques[t].setdefault("mitigations", []).append(m)
    # Old technique IDs that ATT&CK revoked in favour of another, followed to a live one.
    ids = {o["id"]: ext_id(o) for o in objs if o["type"] == "attack-pattern"}
    rv = {}
    for o in objs:
        if o["type"] == "relationship" and o.get("relationship_type") == "revoked-by":
            s, t = ids.get(o["source_ref"]), ids.get(o["target_ref"])
            if s and t and s != t:
                rv[s] = t
    revoked = {}
    for s in rv:
        t, seen = rv[s], {s}
        while t in rv and t not in seen:
            seen.add(t)
            t = rv[t]
        if t in techniques and s not in techniques:
            revoked[s] = t
    key = lambda s: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]
    out_t = []
    for tid in sorted(techniques, key=key):
        t = techniques[tid]
        if "." in tid:
            t["parent"] = tid.split(".")[0]
        if "mitigations" in t:
            t["mitigations"] = sorted(t["mitigations"], key=key)
        out_t.append(t)
    version = "20.0"
    m = re.search(r"v([\d.]+)", SOURCES["attack"].get("tag", ""))
    if m:
        version = m.group(1)
    url = SOURCES["attack"]["repo"].replace("github.com", "raw.githubusercontent.com") + "/" + \
        SOURCES["attack"]["tag"].replace("&", "%26") + "/" + SOURCES["attack"]["path"]
    return {
        "framework": "MITRE ATT&CK Enterprise",
        "version": version,
        "source": f"MITRE ATT&CK Enterprise v{version} (STIX bundle, mitre/cti release {SOURCES['attack']['tag']})",
        "source_url": url,
        "source_repo_commit": SOURCES["attack"]["commit"],
        "retrieved": date,
        "attribution": MITRE_NOTICE,
        "licence": MITRE_LICENSE,
        "disclaimer": MITRE_DISCLAIMER,
        "trademark": "MITRE ATT&CK and ATT&CK are registered trademarks of The MITRE Corporation.",
        "note": "Techniques and sub-techniques (ID, name, tactics by shortname, platforms, and mitigations by "
                "M-ID), mitigations (M-ID and name), and tactics. Revoked and deprecated objects are left out. "
                "Revoked holds old technique IDs and the live ID that replaced each. No descriptions, procedures, or "
                "detections; read attack.mitre.org for those.",
        "tactics": tactics,
        "techniques": out_t,
        "mitigations": [mitigations[k] for k in sorted(mitigations, key=key)],
        "revoked": {k: revoked[k] for k in sorted(revoked, key=key)},
    }


def build_ctid(path, date, known=None):
    d = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    md = d["metadata"]
    mp = {}
    non = []
    for o in d["mapping_objects"]:
        t = o.get("attack_object_id")
        if o.get("status") == "non_mappable" or not o.get("capability_id"):
            if t:
                non.append(t)
            continue
        if o.get("mapping_type") not in (None, "mitigates"):
            continue
        mp.setdefault(t, set()).add(norm_ctid(o["capability_id"]))
    key = lambda s: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]
    # Keys the current ATT&CK data can't place (not live, not revoked into a live ID, no live parent).
    dropped = [t for t in mp if known is not None and t not in known and t.split(".")[0] not in known]
    for t in dropped:
        del mp[t]
    url = SOURCES["ctid"]["repo"].replace("github.com", "raw.githubusercontent.com") + "/" + \
        SOURCES["ctid"]["commit"] + "/" + SOURCES["ctid"]["path"]
    return {
        "mapping": "MITRE ATT&CK Enterprise techniques to NIST SP 800-53 Rev 5 controls (mitigates)",
        "attack_version": md.get("attack_version"),
        "framework_version": md.get("mapping_framework_version"),
        "source": f"Center for Threat-Informed Defense, Mappings Explorer: NIST 800-53 Rev 5 to ATT&CK "
                  f"{md.get('attack_version')} Enterprise, last updated {md.get('last_update')}",
        "source_url": url,
        "source_repo_commit": SOURCES["ctid"]["commit"],
        "retrieved": date,
        "licence": "Apache License 2.0, © The MITRE Corporation (Center for Threat-Informed Defense, Mappings "
                   "Explorer). Derived by Kit: technique IDs and control IDs only. ATT&CK content: "
                   + MITRE_NOTICE,
        "note": "Each technique ID lists the 800-53 Rev 5 controls the mapping says mitigate it. The mapping "
                f"was made against ATT&CK {md.get('attack_version')}; techniques added since have no entry, so "
                "kit-controls also uses the entries of IDs ATT&CK revoked in their favour, then the parent "
                "technique. A mapping is a starting point for review, "
                "not evidence that a control is in place. Not_in_attack lists mapped IDs the current ATT&CK data "
                "doesn't have, left out of the map.",
        "non_mappable": sorted(set(non) - set(mp), key=key),
        "not_in_attack": sorted(dropped, key=key),
        "map": {t: sorted(mp[t], key=key) for t in sorted(mp, key=key)},
    }


def dump(obj, path, lists):
    """JSON with one record per line for the big lists, so diffs stay readable."""
    out = ["{"]
    items = list(obj.items())
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if k in lists and isinstance(v, list):
            out.append(f"  {json.dumps(k)}: [")
            for j, r in enumerate(v):
                out.append("    " + json.dumps(r, ensure_ascii=False) + ("," if j < len(v) - 1 else ""))
            out.append("  ]" + comma)
        elif k in lists and isinstance(v, dict):
            out.append(f"  {json.dumps(k)}: {{")
            ks = list(v)
            for j, kk in enumerate(ks):
                out.append(f"    {json.dumps(kk)}: " + json.dumps(v[kk], ensure_ascii=False) +
                           ("," if j < len(ks) - 1 else ""))
            out.append("  }" + comma)
        else:
            out.append(f"  {json.dumps(k)}: " + json.dumps(v, ensure_ascii=False) + comma)
    out.append("}")
    pathlib.Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nist", required=True)
    ap.add_argument("--attack", required=True)
    ap.add_argument("--ctid", required=True)
    ap.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parent))
    ap.add_argument("--date", default=datetime.date.today().strftime("%d-%b-%Y"))
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    n = build_nist(pathlib.Path(a.nist), a.date)
    dump(n, out / "nist-800-53r5.json", ("families", "controls"))
    t = build_attack(a.attack, a.date)
    dump(t, out / "mitre-attack-enterprise.json", ("tactics", "techniques", "mitigations", "revoked"))
    c = build_ctid(a.ctid, a.date, {x["id"] for x in t["techniques"]} | set(t["revoked"]))
    dump(c, out / "attack-to-800-53.json", ("map",))
    print(f"800-53: {len(n['controls'])} controls, "
          f"{sum(len(x.get('enhancements', [])) for x in n['controls'])} enhancements")
    print(f"ATT&CK: {len(t['techniques'])} techniques, {len(t['mitigations'])} mitigations, "
          f"{sum(len(x.get('mitigations', [])) for x in t['techniques'])} links")
    print(f"Mapping: {len(c['map'])} techniques, {sum(len(v) for v in c['map'].values())} links")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
