# kitmail (Windows): Kit's mail tool for desktop Outlook, driven over COM (pywin32).
#
# UNTESTED on Windows -- validate on a real Windows box with Outlook installed.
#
# This is the Windows counterpart to platform/mac/mail/kitmail.swift and mirrors its CLI
# surface, argument parsing, and JSON output exactly. The Mac tool is the authoritative
# behavior; this file replicates it against the Outlook Application object model.
#
# Safety, enforced here (same guarantees as the Mac tool):
#   - Accounts listed under "exclude" in the config are never read.
#   - There is NO send command and NO call to .Send() anywhere. A draft is created and
#     .Display()ed in an Outlook window for the owner to review and send himself.
#
#   kitmail accounts
#   kitmail inbox [--hours 24] [--unread] [--limit 50]
#   kitmail read --id ID
#   kitmail draft --to ADDRESS [--to ADDRESS ...] --subject S (--body TEXT | --body-file PATH) [--from ADDRESS]
#
# Config: %USERPROFILE%\Claude\Agents\kit\.install\mail\config.json
#         = {"exclude": ["account name or address"]}
# (Same relative location and semantics as the Mac tool, which uses
#  ~/Claude/Agents/kit/.install/mail/config.json.)

import json
import os
import sys

# Outlook OlDefaultFolders / OlItemType constants (hard-coded so we don't depend on the
# generated COM type library / makepy cache being present).
OL_FOLDER_INBOX = 6   # olFolderInbox
OL_MAIL_ITEM = 0      # olMailItem
OL_TO = 1             # olTo (Recipient.Type)
OL_FLAG_MARKED = 2    # olFlagMarked (MailItem.FlagStatus)

CONFIG_PATH = os.path.join(
    os.path.expanduser("~"),
    "Claude", "Agents", "kit", ".install", "mail", "config.json",
)

USAGE = (
    "kitmail accounts | inbox [--hours N] [--unread] [--limit N] | "
    "read --id ID | draft --to A --subject S --body T\n"
)


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def emit(obj):
    # Compact JSON, matching the Mac tool's JSONSerialization output.
    sys.stdout.write(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    sys.stdout.write("\n")


# ---- argument parsing (mirrors the Swift opt/opts/flag helpers) --------------------------

ARGS = sys.argv[2:]  # everything after the subcommand


def opt(name):
    key = "--" + name
    for i, a in enumerate(ARGS):
        if a == key and i + 1 < len(ARGS):
            return ARGS[i + 1]
    return None


def opts(name):
    key = "--" + name
    found = []
    i = 0
    while i < len(ARGS):
        if ARGS[i] == key and i + 1 < len(ARGS):
            found.append(ARGS[i + 1])
            i += 2
        else:
            i += 1
    return found


def flag(name):
    return ("--" + name) in ARGS


# ---- config ------------------------------------------------------------------------------

def load_exclude():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        ex = data.get("exclude", [])
        return [x for x in ex if isinstance(x, str)]
    except FileNotFoundError:
        return []
    except (ValueError, OSError):
        # Malformed or unreadable config: behave as if no exclusions, like the Mac tool,
        # which silently falls back to [] when the file can't be parsed.
        return []


# ---- Outlook connection ------------------------------------------------------------------

def connect():
    """Return (outlook_app, mapi_namespace), or fail() with a clear message."""
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        fail(
            "pywin32 is not installed. Run:  pip install pywin32\n"
            "(kitmail drives desktop Outlook over COM and needs win32com.client.)"
        )
    try:
        import pythoncom  # provided by pywin32
        pythoncom.CoInitialize()
    except Exception:
        pass  # CoInitialize is best-effort; Dispatch works without it in most hosts.
    try:
        import win32com.client
        app = win32com.client.Dispatch("Outlook.Application")
        namespace = app.GetNamespace("MAPI")
        return app, namespace
    except Exception as exc:  # pragma: no cover - environment dependent
        fail(
            "Could not connect to Outlook. Make sure the desktop Outlook client is "
            "installed and configured.\nOutlook: " + str(exc)
        )


# ---- helpers (mirror the Mac JXA helpers) ------------------------------------------------

def lc(s):
    return ("" if s is None else str(s)).lower()


def stamp(dt):
    """Format a COM/datetime value as 'YYYY-MM-DD HH:MM' (same as the Mac stamp())."""
    if dt is None:
        return ""
    try:
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt)


def account_emails(account):
    """Best-effort list of email addresses for an Outlook Account."""
    emails = []
    for attr in ("SmtpAddress",):
        try:
            val = getattr(account, attr, None)
            if val:
                emails.append(str(val))
        except Exception:
            pass
    return emails


def account_name(account):
    try:
        return str(account.DisplayName)
    except Exception:
        return ""


def is_excluded(name, emails, exclude):
    name_lc = lc(name)
    emails_lc = [lc(e) for e in emails]
    for x in exclude:
        xl = lc(x)
        if name_lc == xl or xl in emails_lc:
            return True
    return False


def sender_string(item):
    """Build a human-readable 'Name <addr>' sender, like Apple Mail's sender()."""
    name = ""
    addr = ""
    try:
        name = str(getattr(item, "SenderName", "") or "")
    except Exception:
        pass
    try:
        addr = str(getattr(item, "SenderEmailAddress", "") or "")
    except Exception:
        pass
    if addr and "@" in addr:
        return "{0} <{1}>".format(name, addr) if name else addr
    return name or addr


def inbox_of(namespace, account):
    """Return the Inbox folder for an account's delivery store, or None."""
    try:
        store = account.DeliveryStore
        if store is None:
            return None
        return store.GetDefaultFolder(OL_FOLDER_INBOX)
    except Exception:
        return None


def store_id_of(folder):
    try:
        return str(folder.StoreID)
    except Exception:
        try:
            return str(folder.EntryID)
        except Exception:
            return None


# ---- commands ----------------------------------------------------------------------------

def cmd_accounts(namespace, exclude):
    out = []
    accounts = namespace.Accounts
    for i in range(1, accounts.Count + 1):  # Outlook collections are 1-based
        acc = accounts.Item(i)
        name = account_name(acc)
        emails = account_emails(acc)
        if is_excluded(name, emails, exclude):
            continue
        # Outlook has no per-account "enabled" flag like Apple Mail; a configured account
        # is active, so we report enabled=True to keep the field shape identical.
        out.append({"name": name, "emails": emails, "enabled": True})
    emit(out)


def cmd_inbox(namespace, exclude, hours, unread_only, limit):
    import datetime
    since = datetime.datetime.now() - datetime.timedelta(hours=hours)
    out = []
    seen_stores = set()
    accounts = namespace.Accounts
    for i in range(1, accounts.Count + 1):
        acc = accounts.Item(i)
        name = account_name(acc)
        emails = account_emails(acc)
        if is_excluded(name, emails, exclude):
            continue
        box = inbox_of(namespace, acc)
        if box is None:
            continue
        # Dedupe: several accounts can deliver to the same store/inbox.
        sid = store_id_of(box)
        if sid is not None and sid in seen_stores:
            continue
        if sid is not None:
            seen_stores.add(sid)
        try:
            items = box.Items
            items.Sort("[ReceivedTime]", True)  # descending (newest first)
        except Exception:
            continue
        try:
            item = items.GetFirst()
        except Exception:
            item = None
        while item is not None:
            try:
                received = getattr(item, "ReceivedTime", None)
                # Compare naive local datetimes; stop once we pass the cutoff (sorted desc).
                rcv_naive = None
                if received is not None:
                    try:
                        rcv_naive = received.replace(tzinfo=None)
                    except Exception:
                        rcv_naive = received
                if rcv_naive is not None and rcv_naive < since:
                    break
                is_unread = bool(getattr(item, "UnRead", False))
                if unread_only and not is_unread:
                    item = items.GetNext()
                    continue
                try:
                    entry_id = str(item.EntryID)
                except Exception:
                    entry_id = ""
                try:
                    flag_status = int(getattr(item, "FlagStatus", 0) or 0)
                except Exception:
                    flag_status = 0
                out.append({
                    "id": name + "|" + entry_id,
                    "account": name,
                    "from": sender_string(item),
                    "subject": str(getattr(item, "Subject", "") or ""),
                    "received": stamp(received),
                    "read": not is_unread,
                    "flagged": flag_status == OL_FLAG_MARKED,
                })
            except Exception:
                # Non-mail items (meeting requests, reports) can raise on these props; skip.
                pass
            try:
                item = items.GetNext()
            except Exception:
                break
    # Sort by received string descending, then slice -- identical to the Mac tool.
    out.sort(key=lambda m: m["received"], reverse=True)
    emit(out[:limit])


def cmd_read(namespace, exclude, msg_id):
    bar = msg_id.rfind("|")
    if bar < 0:
        fail("Bad --id. Use an id from kitmail inbox.")
    name = msg_id[:bar]
    entry_id = msg_id[bar + 1:]

    # Find the account by name to (a) honor the exclude-list and (b) locate the store.
    accounts = namespace.Accounts
    account = None
    for i in range(1, accounts.Count + 1):
        acc = accounts.Item(i)
        if account_name(acc) == name:
            account = acc
            break
    if account is not None:
        if is_excluded(account_name(account), account_emails(account), exclude):
            fail("That account is off-limits.")

    item = None
    store_id = None
    box = inbox_of(namespace, account) if account is not None else None
    if box is not None:
        store_id = store_id_of(box)
    try:
        if store_id:
            item = namespace.GetItemFromID(entry_id, store_id)
        else:
            item = namespace.GetItemFromID(entry_id)
    except Exception as exc:
        fail("Could not open that message: " + str(exc))

    to_addrs = []
    try:
        recips = item.Recipients
        for i in range(1, recips.Count + 1):
            r = recips.Item(i)
            try:
                if int(getattr(r, "Type", OL_TO)) != OL_TO:
                    continue
            except Exception:
                pass
            addr = ""
            try:
                addr = str(getattr(r, "Address", "") or "")
            except Exception:
                pass
            if not addr:
                try:
                    addr = str(getattr(r, "Name", "") or "")
                except Exception:
                    pass
            if addr:
                to_addrs.append(addr)
    except Exception:
        pass

    try:
        body = str(getattr(item, "Body", "") or "")
    except Exception:
        body = ""

    emit({
        "from": sender_string(item),
        "to": to_addrs,
        "subject": str(getattr(item, "Subject", "") or ""),
        "received": stamp(getattr(item, "ReceivedTime", None)),
        "body": body[:8000],
    })


def cmd_draft(app, namespace, to_list, subject, body, from_addr):
    try:
        mail = app.CreateItem(OL_MAIL_ITEM)
        mail.Subject = subject
        mail.Body = body
        for addr in to_list:
            mail.Recipients.Add(addr)  # default Recipient.Type is olTo
        try:
            mail.Recipients.ResolveAll()
        except Exception:
            pass
        if from_addr:
            # Mirror the Mac tool's msg.sender = from. SentOnBehalfOfName sets the From
            # account without sending. Best-effort match to a real account as well.
            try:
                mail.SentOnBehalfOfName = from_addr
            except Exception:
                pass
            try:
                accounts = namespace.Accounts
                for i in range(1, accounts.Count + 1):
                    acc = accounts.Item(i)
                    if lc(from_addr) in [lc(e) for e in account_emails(acc)] \
                       or lc(from_addr) == lc(account_name(acc)):
                        mail.SendUsingAccount = acc
                        break
            except Exception:
                pass
        # CRITICAL: Display() only. We NEVER call mail.Send(); the owner reviews and sends.
        mail.Display()
    except Exception as exc:
        fail("Could not open a draft: " + str(exc))
    emit({"opened": True, "to": to_list, "subject": subject})


# ---- dispatch ----------------------------------------------------------------------------

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd in ("help", "--help", "-h"):
        sys.stdout.write(USAGE)
        sys.exit(0)

    if cmd not in ("accounts", "inbox", "read", "draft"):
        sys.stdout.write(USAGE)
        sys.exit(1)

    exclude = load_exclude()

    # Parse args before connecting, so bad input fails fast (matches the Mac tool).
    if cmd == "inbox":
        try:
            hours = float(opt("hours") or "24")
        except ValueError:
            hours = 24.0
        unread_only = flag("unread")
        try:
            limit = int(opt("limit") or "50")
        except ValueError:
            limit = 50
    elif cmd == "read":
        msg_id = opt("id")
        if not msg_id:
            fail("read needs --id from kitmail inbox.")
    elif cmd == "draft":
        to_list = opts("to")
        if not to_list:
            fail("draft needs at least one --to.")
        subject = opt("subject") or ""
        body = opt("body") or ""
        body_file = opt("body-file")
        if body_file:
            try:
                with open(body_file, "r", encoding="utf-8") as fh:
                    body = fh.read()
            except OSError:
                fail("Can't read " + body_file + ".")
        from_addr = opt("from")

    app, namespace = connect()

    if cmd == "accounts":
        cmd_accounts(namespace, exclude)
    elif cmd == "inbox":
        cmd_inbox(namespace, exclude, hours, unread_only, limit)
    elif cmd == "read":
        cmd_read(namespace, exclude, msg_id)
    elif cmd == "draft":
        cmd_draft(app, namespace, to_list, subject, body, from_addr)


if __name__ == "__main__":
    main()
