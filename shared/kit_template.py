"""Find and fill the HTML templates the dashboards render into.

A template is a plain HTML file with $placeholders (Python string.Template syntax; write a literal
dollar sign as $$). Where a dashboard looks for its template, first match wins:

  1. the --template PATH option
  2. the environment variable the dashboard names (for example KIT_DASHBOARD_TEMPLATE)
  3. ~/Claude/Agents/kit/templates/<name>   (the owner's own copy, kept across reinstalls)
  4. shared/templates/<name>                (the packaged default)

If none is found, the dashboard uses its small built-in page, so it always renders.
"""
import os
import pathlib
import re
import string
import sys

HERE = pathlib.Path(__file__).resolve().parent
OWNER_DIR = pathlib.Path.home() / "Claude/Agents/kit/templates"


def find(name, explicit=None, env=None):
    """Return the path of the template to use, or None for the built-in page."""
    candidates = [explicit, os.environ.get(env) if env else None, OWNER_DIR / name, HERE / "templates" / name]
    for c in candidates:
        if c and pathlib.Path(c).expanduser().is_file():
            return pathlib.Path(c).expanduser()
    if explicit:
        print(f"template not found: {explicit}; using the next one available", file=sys.stderr)
    return None


def render(text, values, label="template"):
    """Fill $placeholders from values. Unknown placeholders stay as they are, and the ones the
    template leaves out are reported, so a customized template can't fail silently."""
    used = set(re.findall(r"\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)", text))
    missing = sorted(k for k in values if k not in used)
    unknown = sorted(k for k in used if k not in values)
    if missing:
        print(f"{label}: these sections aren't in the template, so they won't show: {', '.join(missing)}",
              file=sys.stderr)
    if unknown:
        print(f"{label}: unknown placeholders left as they are: {', '.join(unknown)}", file=sys.stderr)
    return string.Template(text).safe_substitute(values)


def args_template(argv):
    """Pull --template PATH out of an argv list; return (path or None, remaining argv)."""
    rest, path, i = [], None, 0
    while i < len(argv):
        if argv[i] == "--template" and i + 1 < len(argv):
            path = argv[i + 1]
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    return path, rest
