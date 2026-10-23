#!/usr/bin/env python3
"""monitor_drift.py: three-way agent drift, an alert kind for run_alerts.py (kind "drift").

  python3 monitor_drift.py [--kit DIR] [--diff AGENT]

For each of Kit's agents it compares three copies:
  shipped    ~/Claude/Agents/kit/.install/kit/agents/<a>.md, the package the install came from
             (the installer copies the whole package's kit/ folder there on every install);
  live       ~/Claude/Agents/kit/agents/<a>.md, Kit's own copy, which keeps local customizations
             (the installer never overwrites it once it exists);
  installed  ~/.claude/agents/<a>.md, the copy Claude Code loads.
Before comparing, the shipped copy's {{OWNER}} becomes the owner's name (OWNER_NAME in the config,
else KIT_OWNER, else inferred from the live copy), the `model:` line is ignored on both sides (kit-models
sets it per install), and line endings and trailing blank lines are evened out. Any difference left
is real.

Two alerts, each listing its agents, each cleared when everything is in sync again:
  drift:shipped    a shipped agent differs from (or is missing in) the live copy: a missed sync after an
                   update. "Differs from the shipped version: review and sync." Compare with
                   `kit-alerts drift --diff <agent>`; nothing is ever overwritten automatically.
  drift:installed  a live agent is missing from or different in ~/.claude/agents: doctor.py's own check
                   (agent_drift), fixed with `doctor.py --fix-agents`.
Live agents with no shipped copy (your own agents) are left alone. Read-only; never fails.
"""
import argparse
import difflib
import os
import pathlib
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.dirname(HERE)
MODEL = re.compile(r"^model:.*$", re.M)


def shipped_dir(kit):
    return pathlib.Path(kit) / ".install" / "kit" / "agents"


def live_dir(kit):
    return pathlib.Path(kit) / "agents"


def read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def infer_owner(shipped, live):
    """The name that replaced {{OWNER}}, from the first shipped line that has it."""
    for line in shipped.splitlines():
        if "{{OWNER}}" in line:
            pat = "^" + re.escape(line).replace(re.escape("{{OWNER}}"), "(.+?)") + "$"
            for cand in live.splitlines():
                m = re.match(pat, cand)
                if m:
                    return m.group(1)
            return None
    return None


def owner_name(cfg):
    name = (cfg.get("OWNER_NAME", "") if cfg else "") or os.environ.get("KIT_OWNER", "")
    return name.strip() or None


def normalise(text, owner=None, drop_model=True):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if owner:
        text = text.replace("{{OWNER}}", owner)
    if drop_model:
        text = MODEL.sub("", text)
    return "\n".join(ln.rstrip() for ln in text.split("\n")).strip("\n") + "\n"


def shipped_vs_live(kit, cfg=None, deadline=None):
    """(differs, missing): shipped agents whose live copy differs after normalising, and shipped agents
    with no live copy. None when there's no shipped copy to compare with."""
    sd, ld = shipped_dir(kit), live_dir(kit)
    if not sd.is_dir():
        return None
    owner = owner_name(cfg)
    differs, missing = [], []
    for f in sorted(sd.glob("*.md")):
        live = read(ld / f.name)
        if live is None:
            missing.append(f.stem)
            continue
        shipped = read(f) or ""
        who = owner or infer_owner(shipped, live)
        if normalise(shipped, who) != normalise(live, who):
            differs.append(f.stem)
    return differs, missing


def live_vs_installed(kit, home=None):
    """doctor.py's check: live agents missing from or different in ~/.claude/agents."""
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    import doctor  # noqa: E402  (shared/doctor.py; agent_drift is its existing check)
    return doctor.agent_drift(kit, home or pathlib.Path.home())


def names(agents, n=8):
    return ", ".join(agents[:n]) + (f" (+{len(agents) - n} more)" if len(agents) > n else "")


def problems(kit, cfg=None, now=None, deadline=None, home=None):
    """{key: problem} for run_alerts.track_monitor. Never raises past run_alerts' guard."""
    out = {}
    sl = shipped_vs_live(kit, cfg, deadline)
    if sl is not None:
        differs, missing = sl
        agents = sorted(set(differs) | set(missing))
        if agents:
            parts = []
            if differs:
                parts.append(f"{len(differs)} live agent{'s' if len(differs) != 1 else ''} "
                             f"differ{'s' if len(differs) == 1 else ''} from the shipped version ({names(differs)})")
            if missing:
                parts.append(f"{len(missing)} shipped agent{'s' if len(missing) != 1 else ''} not in the live "
                             f"folder ({names(missing)})")
            reason = "; ".join(parts) + ": review and sync"
            out["drift:shipped"] = {
                "drift": "shipped", "agents": agents, "reason": reason,
                "title": "Review Kit's agents that differ from the shipped version, since {since} (kit-alerts drift)",
                "detail": f"{{today}}: {reason}. Compare with: kit-alerts drift --diff <agent>. Nothing is "
                          "overwritten automatically. Kit clears its alert when the live agents match the shipped "
                          "ones (owner name and model line aside).",
                "recovered": "Recovered {today}: the live agents match the shipped version again; check this off "
                             "when you're satisfied."}
    inst = live_vs_installed(kit, home)
    if inst:
        reason = (f"{len(inst)} agent{'s' if len(inst) != 1 else ''} out of date in ~/.claude/agents "
                  f"({names(inst)})")
        out["drift:installed"] = {
            "drift": "installed", "agents": inst, "reason": reason,
            "title": "Copy Kit's staff into ~/.claude/agents, out of date since {since} (doctor.py --fix-agents)",
            "detail": f"{{today}}: {reason}. Run: python3 ~/Claude/Agents/kit/.install/shared/doctor.py "
                      "--fix-agents. Kit clears its alert when the installed agents match the live ones.",
            "recovered": "Recovered {today}: ~/.claude/agents matches Kit's live agents again; check this off "
                         "when you're satisfied."}
    return out


def diff(kit, agent, cfg=None):
    """(rc, text): a unified diff of the shipped agent (owner filled in, model line set to the live one)
    against the live one. rc 0 when they match, 1 when they differ, 2 when one is missing."""
    agent = agent[:-3] if agent.endswith(".md") else agent
    if not re.fullmatch(r"[A-Za-z0-9._-]+", agent):
        return 2, f"kit-alerts: no such agent: {agent}"
    s_path, l_path = shipped_dir(kit) / f"{agent}.md", live_dir(kit) / f"{agent}.md"
    shipped, live = read(s_path), read(l_path)
    if shipped is None or live is None:
        which = "shipped" if shipped is None else "live"
        return 2, f"kit-alerts: no {which} copy of {agent} ({s_path if shipped is None else l_path})"
    who = owner_name(cfg) or infer_owner(shipped, live)
    if normalise(shipped, who) == normalise(live, who):
        return 0, f"{agent}: the live copy matches the shipped version (owner name and model line aside)."
    m = MODEL.search(live)
    a = normalise(shipped, who, drop_model=False)
    if m:
        a = MODEL.sub(lambda _x: m.group(0).rstrip(), a)
    b = normalise(live, who, drop_model=False)
    lines = difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                                 fromfile=f"shipped/{agent}.md (owner filled in)", tofile=f"live/{agent}.md")
    return 1, "".join(lines).rstrip("\n") + "\n\nNothing was changed. To take the shipped version, review the " \
        "diff and copy what you want into the live file, then run doctor.py --fix-agents."


def main(argv):
    ap = argparse.ArgumentParser(prog="monitor_drift.py")
    ap.add_argument("--kit", default=os.environ.get("KIT_DIR", os.path.expanduser("~/Claude/Agents/kit")))
    ap.add_argument("--diff")
    a = ap.parse_args(argv)
    if a.diff:
        rc, text = diff(a.kit, a.diff)
        print(text)
        return rc
    for key, p in sorted(problems(a.kit).items()):
        print(f"{key}: {p['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
