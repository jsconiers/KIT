"""kit_arch: shared helpers for Kit's architecture tools (kit-refarch, kit-sysprofile).

Finds the library root and the reference-architecture index from Kit's setup files, splits text
into search terms, and reads the library's indexes and registers line by line so every finding can
be cited by file and line. Read-only; nothing here reaches outside this computer.
"""
import os
import pathlib
import re

KIT = pathlib.Path(os.path.expanduser(os.environ.get("KIT_DIR", "~/Claude/Agents/kit")))
CONTEXT = KIT / "memory/context"
DEFAULT_REFARCH = "published/gds-index.md"

STOP = set("""
a an and are as at be been being but by can could do does for from had has have how i if in into is
it its may might more most must need needs new not of on or our out over per please should so some
such than that the their them then there these they this those to under up use used using via want
wants was we were what when where which while who will with within without would you your also all
any each other only same very just about after again against between both during few further here
once own too able across allow allows based build built create current existing make many much now
provide provides support supports team teams work working request requests requested project system
systems service services solution solutions design designs change changes
""".split())

NFR = {
    "availability": ["availability", "uptime", "ha", "high-availability", "99.9", "99.99", "99.999"],
    "resilience": ["dr", "disaster", "recovery", "failover", "rpo", "rto", "backup", "replication", "resilience"],
    "performance": ["latency", "throughput", "tps", "rps", "performance", "low-latency", "realtime", "real-time"],
    "scale": ["scale", "scalability", "elastic", "autoscaling", "capacity", "growth", "peak"],
    "security": ["encryption", "tls", "mfa", "sso", "authentication", "authorization", "pki", "secrets",
                 "zero-trust", "segmentation", "firewall", "waf", "hsm", "vault"],
    "compliance": ["audit", "retention", "compliance", "regulatory", "sox", "pci", "gdpr", "logging"],
    "observability": ["monitoring", "observability", "telemetry", "alerting", "tracing", "metrics"],
}
NFR_WORDS = {w: cat for cat, ws in NFR.items() for w in ws}


def expand(p):
    return pathlib.Path(os.path.expanduser(str(p).strip().strip("`")))


def library_root():
    f = CONTEXT / "library.md"
    if not f.exists():
        return None
    m = re.search(r"\*\*Library root:\*\*\s*`([^`]+)`", f.read_text(errors="ignore"))
    return expand(m.group(1)) if m else None


def field(text, label):
    m = re.search(r"^- \*\*" + re.escape(label) + r":\*\*(.*?)(?=^- \*\*|\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def refarch_sources(root):
    """Index files the 'Reference architectures' setting points at (standards.md, then
    precedent.md), as paths; the published GDS index by default."""
    found = []
    for name in ("standards.md", "precedent.md"):   # the first file that names an index wins
        f = CONTEXT / name
        if not f.exists() or found:
            continue
        body = field(f.read_text(errors="ignore"), "Reference architectures")
        for ref in re.findall(r"`([^`]+\.(?:md|txt|csv))`", body):
            if (CONTEXT / pathlib.Path(ref).name).exists() and "/" not in ref:
                continue                      # a setup file such as library.md, not an index
            p = expand(ref)
            if not p.is_absolute() and root:
                p = root / ref
                if not p.exists() and (root / "published" / ref).exists():
                    p = root / "published" / ref
            if p not in found:
                found.append(p)
    if not found and root:
        found.append(root / DEFAULT_REFARCH)
    return found


def tokens(text):
    """Lower-case search words: drops stop words and short words, keeps version-like tokens."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]*[A-Za-z0-9+#]|[A-Za-z]{2}|\d{2}\.\d+", text or "")
    out = []
    for w in words:
        lw = w.lower().strip(".-")
        if len(lw) < 3 and lw not in NFR_WORDS:
            continue
        if lw in STOP:
            continue
        out.append(lw)
    return out


def key_terms(text):
    """Terms from a demand: technologies and systems (capitalised or product-like words), other
    content words, and non-functional requirements by category."""
    tech = []
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9+#.\-]*[A-Za-z0-9+#]", text or ""):
        w, lw = m.group(0), m.group(0).lower()
        if lw in STOP or lw in NFR_WORDS or len(lw) < 3:
            continue
        before = (text or "")[:m.start()].rstrip()
        sentence_start = not before or before[-1] in ".!?:\n"
        product_like = (any(c.isdigit() for c in w) or "-" in w or w.isupper()
                        or any(c.isupper() for c in w[1:]))
        if product_like or (w[0].isupper() and not sentence_start):
            if lw not in tech:
                tech.append(lw)
    words = []
    for w in tokens(text):
        if w not in words and w not in NFR_WORDS:
            words.append(w)
    nfr = {}
    for w in tokens(text):
        if w in NFR_WORDS:
            nfr.setdefault(NFR_WORDS[w], [])
            if w not in nfr[NFR_WORDS[w]]:
                nfr[NFR_WORDS[w]].append(w)
    return {"technologies": tech, "words": words, "nfr": nfr}


def read_lines(path, limit=5 * 1024 * 1024):
    try:
        if path.stat().st_size > limit:
            return []
        return path.read_text(errors="ignore").splitlines()
    except OSError:
        return []


def table_rows(path):
    """Markdown table rows of a file as (line number, header-lower dict). Skips the separator."""
    out, head = [], None
    for n, line in enumerate(read_lines(path), 1):
        s = line.strip()
        if not s.startswith("|"):
            head = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if head is None:
            head = [c.lower() for c in cells]
            continue
        if re.fullmatch(r"[\s:|-]+", s):
            continue
        cells += [""] * (len(head) - len(cells))
        out.append((n, dict(zip(head, cells))))
    return out


def cell(row, *names):
    for n in names:
        for k, v in row.items():
            if n in k and v and not v.startswith("<"):
                return v
    return ""


def cite(path, n, root):
    try:
        rel = path.relative_to(root) if root else path
    except ValueError:
        rel = path
    return f"{rel}:{n}"
