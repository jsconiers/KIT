#!/usr/bin/env python3
"""Deliver a finished Kit run (morning brief, weekly review, ...) to its owner. Cross-platform.

  python3 deliver.py --mode morning --text briefs/latest-text.txt --brief briefs/2026-01-05.md
  python3 deliver.py --mode weekly  --text briefs/weekly-text.txt --brief briefs/weekly-...md --test

The run scripts (platform/mac/morning/run.sh, platform/windows/morning/run.ps1) call this after
the agent has written its files. The channels come from DELIVERY in the shared config
(.install/shared/morning/config), space-separated, any of:

  local           (default) desktop notification with the first lines of the text, then a
                  dashboard rebuild. The brief itself is already on disk.
  outlook-drafts  save the brief as a draft in Outlook's Drafts folder, addressed to
                  DELIVERY_EMAIL_TO. No window opens and nothing is sent: open Drafts to read it.
                  Falls back to local if Outlook isn't running or scripting fails.
  outlook-review  the same draft, but opened in a window for review. Never sent.
  imessage        LEGACY, macOS, opt-in: texts the short version by iMessage to IMESSAGE_TO
                  (then IMESSAGE_TO_ALT). Leaves Microsoft 365; not for work content.
  sms             LEGACY, Windows, opt-in: SMS gateway hook (a stub until you wire a provider).
                  Leaves Microsoft 365; not for work content.

Kit never sends mail: the Outlook channels only ever save or open a draft. Outlook must already
be running; this script never launches it. Each channel's result goes to stdout. Exit 0 if at
least one channel worked, 1 otherwise. --test prefixes "[Test]" to the notification and
"Kit TEST" to the draft subject. --channels overrides DELIVERY and --config reads another
settings file (both for testing).
"""
import argparse
import datetime as dt
import html
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

HOME = pathlib.Path.home()
KIT = HOME / "Claude/Agents/kit"
CONFIG = KIT / ".install/shared/morning/config"
DASHBOARD = pathlib.Path(__file__).resolve().parent / "dashboard.py"
IS_MAC = sys.platform == "darwin"
IS_WIN = os.name == "nt"
KNOWN = ("local", "outlook-drafts", "outlook-review", "imessage", "sms")


def say(msg):
    print(f"deliver: {msg}", flush=True)


def read_config(path=CONFIG):
    """Parse the shared KEY="value" config (shell syntax) without sourcing it."""
    cfg = {}
    if not path.exists():
        return cfg
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if not t or t.startswith("#") or "=" not in t:
            continue
        key, val = t.split("=", 1)
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        elif " #" in val:
            val = val.split(" #", 1)[0].strip()
        cfg[key] = val
    return cfg


def run(cmd, timeout=120, env=None, stdin=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env=env, input=stdin)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as ex:
        return 1, "", str(ex)


# --- markdown -> simple HTML (stdlib only) ---------------------------------------------------

def _inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return s


def md_to_html(md):
    out, para, lists = [], [], []

    def flush_para():
        if para:
            out.append("<p>" + "<br>".join(_inline(p) for p in para) + "</p>")
            para.clear()

    def close_lists(depth=0):
        while len(lists) > depth:
            out.append(f"</{lists.pop()}>")

    for raw in md.splitlines():
        line = raw.rstrip()
        m_head = re.match(r"^(#{1,6})\s+(.*)$", line)
        m_item = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if not line.strip():
            flush_para()
            close_lists()
        elif m_head:
            flush_para()
            close_lists()
            n = len(m_head.group(1))
            out.append(f"<h{n}>{_inline(m_head.group(2))}</h{n}>")
        elif re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", line):
            flush_para()
            close_lists()
            out.append("<hr>")
        elif m_item:
            flush_para()
            depth = len(m_item.group(1).expandtabs(4)) // 2 + 1
            tag = "ol" if m_item.group(2)[0].isdigit() else "ul"
            close_lists(depth)
            if len(lists) == depth and lists[-1] != tag:
                close_lists(depth - 1)
            while len(lists) < depth:
                out.append(f"<{tag}>")
                lists.append(tag)
            text = re.sub(r"^\[( |x|X)\]\s+", lambda m: "&#9745; " if m.group(1) != " "
                          else "&#9744; ", _inline(m_item.group(3)))
            out.append(f"<li>{text}</li>")
        else:
            close_lists()
            para.append(line.strip())
    flush_para()
    close_lists()
    return ("<html><body style=\"font-family:-apple-system,Segoe UI,Helvetica,Arial,"
            "sans-serif;font-size:14px\">\n" + "\n".join(out) + "\n</body></html>")


# --- channel: local --------------------------------------------------------------------------

WIN_TOAST = r"""
$ErrorActionPreference = 'Stop'
$title = $env:KIT_NOTIFY_TITLE
$body  = $env:KIT_NOTIFY_BODY
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$t = [System.Security.SecurityElement]::Escape($title)
$b = [System.Security.SecurityElement]::Escape($body)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
# Single quotes only in this script, so it survives Windows command-line quoting intact.
$xml.LoadXml('<toast><visual><binding template=''ToastGeneric''><text>' + $t + '</text><text>' + $b + '</text></binding></visual></toast>')
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
# Windows PowerShell's own app ID, so no app registration is needed.
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
"""


def notify(title, body):
    """Desktop notification. Returns True if it was shown (or at least handed to the OS)."""
    if IS_MAC:
        rc, _, err = run(["/usr/bin/osascript", "-e", "on run argv",
                          "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                          "-e", "end run", title, body], timeout=30)
        if rc == 0:
            return True
        say(f"local: notification failed: {err[:200]}")
        return False
    if IS_WIN:
        # Built-in WinRT toast API; needs Windows PowerShell 5.1 (powershell.exe), not pwsh 7.
        env = dict(os.environ, KIT_NOTIFY_TITLE=title, KIT_NOTIFY_BODY=body)
        rc, _, err = run(["powershell.exe", "-NoProfile", "-NonInteractive",
                          "-ExecutionPolicy", "Bypass", "-Command", WIN_TOAST], timeout=60, env=env)
        if rc == 0:
            return True
        say(f"local: toast unavailable ({err[:200]}); message follows")
        say(f"local: {title}: {body}")
        return False
    say(f"local: no notifier on this OS; message follows: {title}: {body}")
    return False


def rebuild_dashboard():
    if not DASHBOARD.exists():
        say("local: dashboard.py not found; skipped rebuild")
        return False
    rc, _, err = run([sys.executable, str(DASHBOARD)], timeout=120)
    if rc == 0:
        say("local: dashboard rebuilt")
        return True
    say(f"local: dashboard rebuild failed: {err[:200]}")
    return False


def ch_local(ctx):
    lines = [ln.strip() for ln in ctx["text"].splitlines() if ln.strip()]
    body = " ".join(lines[:2])[:220] or f"Kit's {ctx['mode']} run finished."
    title = ("[Test] " if ctx["test"] else "") + f"Kit {ctx['mode']}"
    shown = notify(title, body)
    if shown:
        say("local: notification shown")
    dash = rebuild_dashboard()
    # The brief is already on disk; local counts as delivered if either step worked.
    return shown or dash


# --- channels: outlook-drafts / outlook-review -----------------------------------------------

MAC_OUTLOOK = r'''
on run argv
    set theTo to item 1 of argv
    set theSubject to item 2 of argv
    set bodyPath to item 3 of argv
    set doOpen to (item 4 of argv) is "open"
    set theBody to read (POSIX file bodyPath) as «class utf8»
    if application "Microsoft Outlook" is not running then error "Outlook is not running" number 1001
    tell application "Microsoft Outlook"
        -- A new outgoing message is saved in Drafts. Kit never sends it.
        set newMsg to make new outgoing message with properties {subject:theSubject, content:theBody}
        make new to recipient at newMsg with properties {email address:{address:theTo}}
        if doOpen then
            open newMsg
            activate
        end if
    end tell
    return "ok"
end run
'''

WIN_OUTLOOK = r"""
$ErrorActionPreference = 'Stop'
# Attach to the running Outlook only; never start it.
try { $ol = [Runtime.InteropServices.Marshal]::GetActiveObject('Outlook.Application') }
catch { [Console]::Error.WriteLine('Outlook is not running'); exit 3 }
$m = $ol.CreateItem(0)   # olMailItem
$m.To = $env:KIT_MAIL_TO
$m.Subject = $env:KIT_MAIL_SUBJECT
$m.HTMLBody = Get-Content -LiteralPath $env:KIT_MAIL_BODY_FILE -Raw -Encoding UTF8
$m.Save()                # lands in Drafts. Kit never calls .Send().
if ($env:KIT_MAIL_OPEN -eq '1') { $m.Display() }
Write-Output 'ok'
"""


def outlook_draft(ctx, open_window):
    label = "outlook-review" if open_window else "outlook-drafts"
    to = ctx["cfg"].get("DELIVERY_EMAIL_TO", "").strip()
    if not to:
        say(f"{label}: DELIVERY_EMAIL_TO is not set")
        return False
    subject = ("Kit TEST " if ctx["test"] else "Kit ") + f"{ctx['mode']} brief {ctx['date']}"
    source = ctx["brief"] if ctx["brief"].strip() else ctx["text"]
    body = md_to_html(source)
    fd, body_path = tempfile.mkstemp(prefix="kit-deliver-", suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        if IS_MAC:
            rc, out, err = run(["/usr/bin/osascript", "-", to, subject, body_path,
                                "open" if open_window else "save"], timeout=120,
                               stdin=MAC_OUTLOOK)
        elif IS_WIN:
            env = dict(os.environ, KIT_MAIL_TO=to, KIT_MAIL_SUBJECT=subject,
                       KIT_MAIL_BODY_FILE=body_path, KIT_MAIL_OPEN="1" if open_window else "0")
            rc, out, err = run(["powershell.exe", "-NoProfile", "-NonInteractive",
                                "-ExecutionPolicy", "Bypass", "-Command", WIN_OUTLOOK],
                               timeout=120, env=env)
        else:
            say(f"{label}: Outlook scripting isn't available on this OS")
            return False
    finally:
        try:
            os.unlink(body_path)
        except OSError:
            pass
    if rc == 0 and out.endswith("ok"):
        say(f"{label}: draft '{subject}' saved to Drafts for {to}"
            + (" and opened for review" if open_window else "") + "; not sent")
        return True
    say(f"{label}: failed: {(err or out)[:300]}")
    return False


def ch_outlook_drafts(ctx):
    return outlook_draft(ctx, open_window=False)


def ch_outlook_review(ctx):
    return outlook_draft(ctx, open_window=True)


# --- legacy channels (opt-in) ----------------------------------------------------------------

# LEGACY: iMessage goes through Apple's servers, outside Microsoft 365. Opt-in only, and never
# for work content.
MAC_IMESSAGE = r'''
on run argv
  tell application "Messages"
    set svc to 1st account whose service type = iMessage
    send (item 2 of argv) to participant (item 1 of argv) of svc
  end tell
end run
'''


def ch_imessage(ctx):
    if not IS_MAC:
        say("imessage: macOS only")
        return False
    cfg = ctx["cfg"]
    targets = [t for t in (cfg.get("IMESSAGE_TO", ""), cfg.get("IMESSAGE_TO_ALT", "")) if t]
    if not targets:
        say("imessage: IMESSAGE_TO is not set")
        return False
    msg = ("[Test] " if ctx["test"] else "") + ctx["text"]
    # Keep trying for about 20 minutes (one try in test mode), as the old run.sh did.
    waits = (0,) if ctx["test"] else (0, 120, 240, 360, 480)
    for wait in waits:
        time.sleep(wait)
        for to in targets:
            rc, _, err = run(["/usr/bin/osascript", "-", to, msg], timeout=60, stdin=MAC_IMESSAGE)
            if rc == 0:
                say("imessage: texted")
                return True
            say(f"imessage: send failed: {err[:200]}")
    return False


# LEGACY: an SMS gateway is a third party outside Microsoft 365. Opt-in only, never for work
# content. The API key is referenced by the NAME of an environment variable, never stored.
def ch_sms(ctx):
    if not IS_WIN:
        say("sms: Windows only")
        return False
    cfg = ctx["cfg"]
    to, url, key_env = (cfg.get("DELIVERY_SMS_TO", ""), cfg.get("DELIVERY_SMS_API_URL", ""),
                        cfg.get("DELIVERY_SMS_API_KEY_ENV", ""))
    if not (to and url and key_env):
        say("sms: not configured (need DELIVERY_SMS_TO, DELIVERY_SMS_API_URL, "
            "DELIVERY_SMS_API_KEY_ENV)")
        return False
    if not os.environ.get(key_env):
        say(f"sms: environment variable {key_env} is not set")
        return False
    # TODO (hook): POST to your provider here and return True only on a confirmed send.
    say("sms: hook present but not implemented")
    return False


CHANNELS = {
    "local": ch_local,
    "outlook-drafts": ch_outlook_drafts,
    "outlook-review": ch_outlook_review,
    "imessage": ch_imessage,
    "sms": ch_sms,
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deliver a finished Kit run.")
    ap.add_argument("--mode", default="morning", help="morning, open, weekly, journal, ...")
    ap.add_argument("--text", help="the short text version written by the run")
    ap.add_argument("--brief", help="the full brief (.md) written by the run")
    ap.add_argument("--test", action="store_true", help="mark the delivery as a test")
    ap.add_argument("--channels", help="override DELIVERY (space-separated)")
    ap.add_argument("--config", help="read settings from this file instead (for testing)")
    a = ap.parse_args(argv)

    def slurp(p):
        if p and pathlib.Path(p).is_file():
            return pathlib.Path(p).read_text(encoding="utf-8", errors="replace")
        return ""

    cfg = read_config(pathlib.Path(a.config)) if a.config else read_config()
    wanted = (a.channels or cfg.get("DELIVERY", "") or "local").lower().split()
    ctx = {"mode": a.mode, "text": slurp(a.text).strip(), "brief": slurp(a.brief),
           "test": a.test, "cfg": cfg, "date": dt.date.today().strftime("%d-%b-%Y")}
    if not ctx["text"] and ctx["brief"]:
        ctx["text"] = ctx["brief"].strip()

    results, fallback = {}, False
    for name in dict.fromkeys(wanted):  # de-duplicate, keep order
        fn = CHANNELS.get(name)
        if fn is None:
            say(f"{name}: unknown channel (known: {', '.join(KNOWN)})")
            results[name] = False
            continue
        try:
            results[name] = bool(fn(ctx))
        except Exception as ex:  # noqa: BLE001 - one bad channel must not stop the others
            say(f"{name}: error: {ex}")
            results[name] = False
        if name.startswith("outlook-") and not results[name]:
            fallback = True
    if fallback and "local" not in results:
        say("falling back to local")
        results["local (fallback)"] = bool(ch_local(ctx))

    for name, ok in results.items():
        say(f"result {name}: {'ok' if ok else 'FAILED'}")
    return 0 if any(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
