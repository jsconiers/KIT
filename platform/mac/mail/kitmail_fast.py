#!/usr/bin/env python3
"""kitmail_fast: the quick way to list Mail's inboxes, from Mail's own index instead of asking Mail.

  kitmail_fast.py inbox [--hours 24] [--unread] [--limit 50]   same JSON as `kitmail inbox`
  kitmail_fast.py accounts                                     each inbox's account and whether Kit may read it

Asking Mail for messages (AppleScript) can take minutes on big inboxes; reading the list from Mail's
index takes a second. KitMessages.app does the reading, read-only, because it alone has Full Disk
Access; it reads headers only (sender, subject, date, read, flagged), never bodies, and only for
accounts it can name that the exclude list in .install/mail/config.json doesn't cover. Exit 0 with the
JSON on stdout, or exit 3 with the reason on stderr (no access yet, an exclusion it can't verify, ...),
and kitmail falls back to asking Mail. Message ids look like kitmail's ("Account|N"), so kitmail read
works the same, as long as Mail's message id matches its index (it has on every version checked).
"""
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile

APP = pathlib.Path.home() / "Claude/Agents/kit/.install/platform/mac/textback/KitMessages.app"


def opt(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def call(args, timeout=60):
    if not APP.exists():
        return None, "KitMessages.app isn't built"
    fd, out = tempfile.mkstemp(prefix="kitmail-fast-", suffix=".json")
    os.close(fd)
    os.unlink(out)
    try:
        subprocess.run(["/usr/bin/open", "-W", "-n", "-g", str(APP), "--args", "--out", out, *args],
                       capture_output=True, timeout=timeout)
        data = json.loads(pathlib.Path(out).read_text())
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return None, f"no answer from KitMessages ({str(e)[:80]})"
    finally:
        if os.path.exists(out):
            os.unlink(out)
    if data.get("error"):
        return None, f"{data['error']}: {data.get('detail', '')}"
    return data, None


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "accounts":
        data, err = call(["--mail-accounts"])
        if err:
            print(err, file=sys.stderr)
            return 3
        print(json.dumps(data, indent=2))
        return 0
    if cmd != "inbox":
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    hours = float(opt(argv, "--hours", "24"))
    limit = int(opt(argv, "--limit", "50"))
    since = int((dt.datetime.now() - dt.timedelta(hours=hours)).timestamp())
    args = ["--mail", "--since", str(since), "--limit", str(limit)] + (["--unread"] if "--unread" in argv else [])
    data, err = call(args)
    if err:
        print(err, file=sys.stderr)
        return 3
    out = [{"id": f"{m['account']}|{m['id']}", "account": m["account"], "from": m["from"], "subject": m["subject"],
            "received": dt.datetime.fromtimestamp(m["received"]).strftime("%Y-%m-%d %H:%M"),
            "read": bool(m["read"]), "flagged": bool(m["flagged"])} for m in data.get("messages", [])]
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
