"""kit_usage: record a direct model call (kit-delegate, kit-run) in kit-cost's ledger.

Uses `kit-cost record-usage --source delegate|kit-run --provider P --model M [--input N]
[--output N] [--cost USD] --mode SOURCE` when that command exists, so kit-cost owns the ledger
format; else it appends one line to .install/logs/cost.jsonl itself, in the same shape run.sh's
records use, plus provider, profile, model, source, and turns. Cost is filled in only when the
profile names prices ("usd_per_mtok": {"input": N, "output": N}); otherwise it's left empty rather than guessed.
Recording never stops the call it records.
"""
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

KIT = pathlib.Path(os.path.expanduser(os.environ.get("KIT_DIR", "~/Claude/Agents/kit")))


def _cost(usage, prices):
    try:
        return round((usage.get("input_tokens") or 0) / 1e6 * float(prices["input"])
                     + (usage.get("output_tokens") or 0) / 1e6 * float(prices["output"]), 6)
    except (KeyError, TypeError, ValueError):
        return None


def record(source, choice, usage, rc=0, turns=1, duration_ms=None, kit=None):
    """source: "delegate" or "kit-run:<agent>"; choice: a resolve_dispatch() result."""
    kit = pathlib.Path(kit or KIT)
    prof = choice.get("profile")
    prices = (choice.get("prices") or {})
    rec = {"date": dt.datetime.now().isoformat(timespec="seconds"), "mode": source.split(":")[0],
           "source": source, "rc": rc, "provider": choice.get("provider_name"), "profile": prof,
           "model": choice.get("model"), "cost_usd": _cost(usage or {}, prices) if prices else None,
           "input_tokens": (usage or {}).get("input_tokens"), "output_tokens": (usage or {}).get("output_tokens"),
           "cache_read_tokens": (usage or {}).get("cache_read_tokens"),
           "cache_write_tokens": (usage or {}).get("cache_write_tokens"),
           "duration_ms": duration_ms, "turns": turns}
    tool = kit / ".install/shared/bin/kit-cost"
    try:
        if tool.exists() and "record-usage" in tool.read_text(errors="ignore"):
            cmd = [sys.executable, str(tool), "record-usage", "--source", rec["mode"],
                   "--provider", str(rec["provider"]), "--model", str(rec["model"]), "--mode", source]
            for flag, key in (("--input", "input_tokens"), ("--output", "output_tokens"), ("--cost", "cost_usd")):
                if rec.get(key) is not None:
                    cmd += [flag, str(rec[key])]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                               env={**os.environ, "KIT_DIR": str(kit)})
            if r.returncode == 0:
                return "kit-cost"
        ledger = kit / ".install/logs/cost.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        new = not ledger.exists()
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        if new and os.name != "nt":
            os.chmod(ledger, 0o600)
        return "ledger"
    except (OSError, subprocess.SubprocessError):
        return None
