"""kit_models: which model each agent and each scheduled run uses, from Kit's model config.

Phase 1 of model routing: Claude models only, reached through Claude Code. The config names
providers and profiles; agents and runs refer to profiles, never to models directly.

Files, in the Kit folder (KIT_DIR, default ~/Claude/Agents/kit):
  models.json              the combined file: providers, profiles, default_profile, agents, runs
  models/<agent>.json      optional, one per agent; wins over the combined file for that agent

Which setting wins, highest first:
  1. organization profile  org_profile.allowed_providers in models.json caps everything below
                           (a ceiling, not a preference; phase 1 checks only the provider list)
  2. per-run override      a profile or model given for one run or one lookup
  3. per-agent file        models/<agent>.json "profile"
  4. combined file         models.json "agents" (or "runs" for scheduled runs)
  5. default_profile       models.json "default_profile", shipped as "deep" (Opus)
  6. built-in default      Opus, used only when there's no config at all

A profile whose provider isn't available in phase 1 (anything but Anthropic), or that the
organization profile doesn't allow, is refused: the lookup falls back to the profile's
"fallback", else to default_profile, and says why.

Model values are what Claude Code accepts in a subagent's `model` field and in --model: the
aliases opus, sonnet, haiku, and fable, a full model ID such as claude-opus-5-5, or inherit.

Phase 2 and 3 (kit-delegate, kit-run) call models directly instead of through Claude Code, so they
use resolve_dispatch(), which adds two rules on top of the ones above:
  - providers whose "phase" is above models.json "enabled_phase" (default 1) are refused, so
    nothing outside Claude is reachable until the owner turns phase 2 on;
  - data class: each request carries one (public < internal < confidential). A provider takes
    data up to its "max_data_class" (Anthropic: confidential; others: public unless set), and
    non-Claude providers are further capped by org_profile.non_claude_max_data_class (default
    public), so internal or confidential work never leaves Claude unless the org profile says so.
A refused profile falls back along its "fallback" chain, then default_profile, ending in Claude.
"""
import json
import os
import pathlib
import re

KIT = pathlib.Path(os.path.expanduser(os.environ.get("KIT_DIR", "~/Claude/Agents/kit")))
BUILTIN_DEFAULT = {"provider": "anthropic", "model": "opus"}
PHASE1_KINDS = {"anthropic"}
ALIASES = {"opus", "sonnet", "haiku", "fable", "inherit"}
FULL_ID = re.compile(r"^claude-[a-z0-9][a-z0-9.\-]*(\[1m\])?$")
RUN_MODES = ("morning", "weekly", "worklist", "open", "journal")


class ConfigError(Exception):
    pass


def valid_model(value):
    return isinstance(value, str) and (value in ALIASES or bool(FULL_ID.match(value)))


def load(kit=None):
    """The combined config plus any per-agent files. A missing models.json means built-in Opus."""
    kit = pathlib.Path(kit or KIT)
    path = kit / "models.json"
    cfg = {}
    if path.exists():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            raise ConfigError(f"{path} isn't valid JSON: {e}")
        if not isinstance(cfg, dict):
            raise ConfigError(f"{path} must hold a JSON object")
    per_agent = {}
    folder = kit / "models"
    if folder.is_dir():
        for f in sorted(folder.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except ValueError as e:
                raise ConfigError(f"{f} isn't valid JSON: {e}")
            if not isinstance(data, dict):
                raise ConfigError(f"{f} must hold a JSON object")
            per_agent[f.stem] = data
    cfg["_per_agent"] = per_agent
    cfg["_path"] = str(path) if path.exists() else None
    return cfg


def profiles(cfg):
    return cfg.get("profiles") or {}


def provider_of(cfg, prof):
    return (cfg.get("providers") or {}).get(prof.get("provider", ""), {})


def refusal(cfg, name):
    """Why a profile can't be used in phase 1, or None if it can."""
    prof = profiles(cfg).get(name)
    if prof is None:
        return f"unknown profile '{name}'"
    pname = prof.get("provider", "")
    prov = provider_of(cfg, prof)
    if not prov:
        return f"profile '{name}' names unknown provider '{pname}'"
    kind = prov.get("kind", pname)
    if kind not in PHASE1_KINDS:
        return f"profile '{name}' uses provider '{pname}' ({kind}), not available until phase {prov.get('phase', 2)}"
    allowed = (cfg.get("org_profile") or {}).get("allowed_providers")
    if allowed is not None and pname not in allowed:
        return f"the organization profile doesn't allow provider '{pname}' (profile '{name}')"
    if not valid_model(prof.get("model")):
        return f"profile '{name}' has model '{prof.get('model')}', which Claude Code doesn't accept"
    return None


def _usable(cfg, name, notes, seen=None):
    """Follow refusals to a usable profile name, or None. Notes collect the reasons."""
    seen = seen or set()
    while name is not None and name not in seen:
        seen.add(name)
        why = refusal(cfg, name)
        if why is None:
            return name
        notes.append(why)
        prof = profiles(cfg).get(name) or {}
        name = prof.get("fallback")
    return None


def _finish(cfg, choice, source, notes):
    """Turn a chosen profile name into a result, falling back when it's refused."""
    if choice is None:
        return {"profile": None, "provider": BUILTIN_DEFAULT["provider"], "model": BUILTIN_DEFAULT["model"],
                "source": "built-in default (no config)", "notes": notes}
    got = _usable(cfg, choice, notes)
    if got is None and choice != cfg.get("default_profile"):
        default = cfg.get("default_profile")
        if default:
            notes.append(f"fell back to default_profile '{default}'")
            got = _usable(cfg, default, notes)
    if got is None:
        notes.append("fell back to the built-in default, opus")
        return {"profile": None, "provider": BUILTIN_DEFAULT["provider"], "model": BUILTIN_DEFAULT["model"],
                "source": source + " (refused)", "notes": notes}
    prof = profiles(cfg)[got]
    if got != choice:
        source += f" -> fallback '{got}'"
    return {"profile": got, "provider": prof.get("provider"), "model": prof.get("model"),
            "source": source, "notes": notes}


def _override(cfg, override, notes):
    """A per-run override is a profile name or a model value."""
    if override in profiles(cfg):
        return override, None
    if valid_model(override):
        allowed = (cfg.get("org_profile") or {}).get("allowed_providers")
        if allowed is not None and "anthropic" not in allowed:
            notes.append(f"the organization profile doesn't allow model override '{override}'")
            return None, None
        return None, override
    raise ConfigError(f"override '{override}' is neither a profile nor a model Claude Code accepts")


def resolve_agent(cfg, agent, override=None):
    notes = []
    if override:
        prof, model = _override(cfg, override, notes)
        if model:
            return {"profile": None, "provider": "anthropic", "model": model,
                    "source": f"per-run override '{override}'", "notes": notes}
        if prof:
            return _finish(cfg, prof, f"per-run override '{override}'", notes)
    own = cfg["_per_agent"].get(agent)
    if own and own.get("profile"):
        return _finish(cfg, own["profile"], f"models/{agent}.json", notes)
    combined = (cfg.get("agents") or {}).get(agent)
    if combined:
        return _finish(cfg, combined, "models.json agents", notes)
    if cfg.get("default_profile"):
        return _finish(cfg, cfg["default_profile"], "default_profile", notes)
    return _finish(cfg, None, "", notes)


def resolve_run(cfg, mode, override=None):
    notes = []
    if override:
        prof, model = _override(cfg, override, notes)
        if model:
            return {"profile": None, "provider": "anthropic", "model": model,
                    "source": f"per-run override '{override}'", "notes": notes}
        if prof:
            return _finish(cfg, prof, f"per-run override '{override}'", notes)
    combined = (cfg.get("runs") or {}).get(mode)
    if combined:
        return _finish(cfg, combined, "models.json runs", notes)
    if cfg.get("default_profile"):
        return _finish(cfg, cfg["default_profile"], "default_profile", notes)
    return _finish(cfg, None, "", notes)


def check(cfg, known_agents):
    """Problems with the config: (errors, warnings). Errors stop kit-models apply."""
    errors, warnings = [], []
    profs = profiles(cfg)
    for name, prof in profs.items():
        if not isinstance(prof, dict) or "provider" not in prof or "model" not in prof:
            errors.append(f"profile '{name}' needs a provider and a model")
            continue
        fb = prof.get("fallback")
        if fb and fb not in profs:
            errors.append(f"profile '{name}' falls back to unknown profile '{fb}'")
    default = cfg.get("default_profile")
    if cfg.get("_path") and not default:
        errors.append("models.json has no default_profile")
    elif default and default not in profs:
        errors.append(f"default_profile '{default}' isn't a profile")
    elif default and refusal(cfg, default):
        errors.append(f"default_profile: {refusal(cfg, default)}")
    known = set(known_agents)
    assigned = [("models.json agents", a, p) for a, p in (cfg.get("agents") or {}).items()]
    assigned += [(f"models/{a}.json", a, d.get("profile")) for a, d in cfg["_per_agent"].items()]
    for where, agent, prof in assigned:
        if known and agent not in known:
            errors.append(f"{where}: unknown agent '{agent}'")
        if prof is None:
            errors.append(f"{where}: no profile for '{agent}'")
        elif prof not in profs:
            errors.append(f"{where}: '{agent}' uses unknown profile '{prof}'")
        elif refusal(cfg, prof):
            r = resolve_agent(cfg, agent)
            warnings.append(f"{where}: '{agent}': {refusal(cfg, prof)}; uses {r['model']} instead")
    for mode, prof in (cfg.get("runs") or {}).items():
        if mode not in RUN_MODES:
            errors.append(f"models.json runs: unknown run '{mode}' (known: {', '.join(RUN_MODES)})")
        if prof not in profs:
            errors.append(f"models.json runs: '{mode}' uses unknown profile '{prof}'")
        elif refusal(cfg, prof):
            warnings.append(f"models.json runs: '{mode}': {refusal(cfg, prof)}; uses "
                            f"{resolve_run(cfg, mode)['model']} instead")
    for agent, data in cfg["_per_agent"].items():
        for task, prof in (data.get("tasks") or {}).items():
            warnings.append(f"models/{agent}.json: task '{task}' -> '{prof}' is recorded but not used until "
                            "phase 2 (Claude Code picks one model per agent)")
    return errors, warnings


def set_model_line(text, model):
    """The agent file's text with its frontmatter `model:` line set. Only that line changes."""
    if not text.startswith("---\n"):
        raise ConfigError("no frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        raise ConfigError("frontmatter isn't closed")
    head, rest = text[4:end], text[end:]
    lines = head.split("\n")
    for i, ln in enumerate(lines):
        if re.match(r"^model:\s*", ln):
            lines[i] = f"model: {model}"
            break
    else:
        lines.append(f"model: {model}")
    return "---\n" + "\n".join(lines) + rest


def env_text(cfg):
    lines = ["# Written by kit-models apply from models.json. run.sh passes MODEL_<RUN> as --model.",
             "# Edit models.json and rerun kit-models apply instead of editing this file."]
    for mode in RUN_MODES:
        lines.append(f"MODEL_{mode.upper()}={resolve_run(cfg, mode)['model']}")
    return "\n".join(lines) + "\n"


# ---- phase 2 and 3: direct dispatch (kit-delegate, kit-run) -------------------------------------
DATA_CLASSES = ("public", "internal", "confidential")


class PolicyError(Exception):
    pass


def _rank(dc):
    if dc not in DATA_CLASSES:
        raise PolicyError(f"unknown data class '{dc}' (use {', '.join(DATA_CLASSES)})")
    return DATA_CLASSES.index(dc)


def enabled_phase(cfg):
    try:
        return int(cfg.get("enabled_phase", 1))
    except (TypeError, ValueError):
        return 1


def data_ceiling(cfg, pname):
    """The highest data class a provider may receive, after the org profile's cap."""
    prov = (cfg.get("providers") or {}).get(pname, {})
    claude = prov.get("kind", pname) == "anthropic"
    own = prov.get("max_data_class", "confidential" if claude else "public")
    if not claude:
        org = (cfg.get("org_profile") or {}).get("non_claude_max_data_class", "public")
        own = DATA_CLASSES[min(_rank(own), _rank(org))]
    return own


def dispatch_refusal(cfg, name, data_class):
    """Why a profile can't take this request directly, or None."""
    prof = profiles(cfg).get(name)
    if prof is None:
        return f"unknown profile '{name}'"
    pname = prof.get("provider", "")
    prov = (cfg.get("providers") or {}).get(pname)
    if not prov:
        return f"profile '{name}' names unknown provider '{pname}'"
    phase = int(prov.get("phase", 1 if prov.get("kind") == "anthropic" else 2))
    if phase > enabled_phase(cfg):
        return (f"provider '{pname}' is phase {phase}; models.json enabled_phase is {enabled_phase(cfg)}")
    allowed = (cfg.get("org_profile") or {}).get("allowed_providers")
    if allowed is not None and pname not in allowed:
        return f"the organization profile doesn't allow provider '{pname}'"
    ceiling = data_ceiling(cfg, pname)
    if _rank(data_class) > _rank(ceiling):
        return f"provider '{pname}' takes data up to '{ceiling}', and this request is '{data_class}'"
    if not prof.get("model"):
        return f"profile '{name}' has no model"
    return None


def resolve_dispatch(cfg, profile=None, agent=None, data_class="internal"):
    """The profile, provider, and model to call directly for this request. Follows refusals along
    the fallback chain, then default_profile, then any Claude profile; raises PolicyError when
    nothing is allowed."""
    _rank(data_class)
    notes = []
    if profile:
        start, source = profile, f"profile '{profile}'"
    elif agent and cfg["_per_agent"].get(agent, {}).get("profile"):
        start, source = cfg["_per_agent"][agent]["profile"], f"models/{agent}.json"
    elif agent and (cfg.get("agents") or {}).get(agent):
        start, source = cfg["agents"][agent], "models.json agents"
    else:
        start, source = cfg.get("default_profile"), "default_profile"
    tried = []
    chain = []
    name = start
    while name and name not in chain:
        chain.append(name)
        name = (profiles(cfg).get(name) or {}).get("fallback")
    for extra in [cfg.get("default_profile")] + [n for n, p in profiles(cfg).items()
                                                  if (cfg.get("providers") or {}).get(p.get("provider"), {}).get("kind") == "anthropic"]:
        if extra and extra not in chain:
            chain.append(extra)
    for name in chain:
        why = dispatch_refusal(cfg, name, data_class)
        if why is None:
            prof = profiles(cfg)[name]
            prov = cfg["providers"][prof["provider"]]
            if name != start:
                source += f" -> fallback '{name}'"
            return {"profile": name, "provider_name": prof["provider"], "provider": prov,
                    "kind": prov.get("kind"), "model": prof["model"], "data_class": data_class,
                    "prices": prof.get("usd_per_mtok"),
                    "source": source, "notes": notes + tried}
        tried.append(why)
    raise PolicyError("no profile may take this request: " + "; ".join(tried or ["no profiles configured"]))
