// kitmail: Kit's mail tool for Apple Mail (all accounts set up in Mail, including Gmail).
//
// Safety, enforced here: accounts listed under "exclude" in the config are never read, and there
// is no send command. A draft opens in a Mail window for the owner to review and send himself.
//
//   kitmail accounts
//   kitmail inbox [--hours 24] [--unread] [--limit 50]
//   kitmail read --id ID
//   kitmail draft --to ADDRESS [--to ADDRESS ...] --subject S (--body TEXT | --body-file PATH) [--from ADDRESS]
//
// Config: ~/Claude/Agents/kit/.install/mail/config.json = {"exclude": ["account name or address"]}
import Foundation
import OSAKit

let usage = "kitmail accounts | inbox [--hours N] [--unread] [--limit N] | read --id ID | draft --to A --subject S --body T\n"
let configPath = NSHomeDirectory() + "/Claude/Agents/kit/.install/mail/config.json"

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

var args = Array(CommandLine.arguments.dropFirst())
let cmd = args.isEmpty ? "help" : args.removeFirst()
func opt(_ name: String) -> String? {
    if let i = args.firstIndex(of: "--" + name), i + 1 < args.count { return args[i + 1] }
    return nil
}
func opts(_ name: String) -> [String] {
    var found: [String] = []
    var i = 0
    while i < args.count {
        if args[i] == "--" + name, i + 1 < args.count { found.append(args[i + 1]); i += 2 } else { i += 1 }
    }
    return found
}
func flag(_ name: String) -> Bool { args.contains("--" + name) }

var exclude: [String] = []
if let data = FileManager.default.contents(atPath: configPath),
   let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
    exclude = (json["exclude"] as? [String]) ?? []
}

let jxa = """
var Mail = Application('Mail');
function pad(n) { return (n < 10 ? '0' : '') + n; }
function stamp(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()); }
function lc(s) { return String(s || '').toLowerCase(); }
function excluded(acc, ex) {
  var name = lc(acc.name());
  var emails = (acc.emailAddresses() || []).map(lc);
  return ex.some(function (x) { x = lc(x); return name === x || emails.indexOf(x) >= 0; });
}
function inboxOf(acc) {
  var boxes = acc.mailboxes();
  for (var i = 0; i < boxes.length; i++) { if (lc(boxes[i].name()) === 'inbox') { return boxes[i]; } }
  return null;
}
function main(a) {
  var ex = a.exclude || [];
  if (a.cmd === 'accounts') {
    return JSON.stringify(Mail.accounts().filter(function (acc) { return !excluded(acc, ex); }).map(function (acc) {
      return {name: acc.name(), emails: acc.emailAddresses(), enabled: acc.enabled()};
    }));
  }
  if (a.cmd === 'inbox') {
    var since = new Date(Date.now() - a.hours * 3600 * 1000);
    var out = [];
    Mail.accounts().forEach(function (acc) {
      if (!acc.enabled() || excluded(acc, ex)) { return; }
      var box = inboxOf(acc);
      if (!box) { return; }
      box.messages.whose({dateReceived: {_greaterThan: since}})().forEach(function (m) {
        if (a.unread && m.readStatus()) { return; }
        out.push({id: acc.name() + '|' + m.id(), account: acc.name(), from: m.sender(), subject: m.subject(),
                  received: stamp(m.dateReceived()), read: m.readStatus(), flagged: m.flaggedStatus()});
      });
    });
    out.sort(function (x, y) { return x.received < y.received ? 1 : -1; });
    return JSON.stringify(out.slice(0, a.limit));
  }
  if (a.cmd === 'read') {
    var bar = a.id.lastIndexOf('|');
    var acc = Mail.accounts.byName(a.id.slice(0, bar));
    if (excluded(acc, ex)) { throw new Error('That account is off-limits.'); }
    var m = inboxOf(acc).messages.byId(parseInt(a.id.slice(bar + 1), 10));
    return JSON.stringify({from: m.sender(), to: m.toRecipients().map(function (r) { return r.address(); }),
      subject: m.subject(), received: stamp(m.dateReceived()), body: String(m.content() || '').slice(0, 8000)});
  }
  if (a.cmd === 'draft') {
    var msg = Mail.OutgoingMessage({subject: a.subject, content: a.body, visible: true});
    Mail.outgoingMessages.push(msg);
    a.to.forEach(function (addr) { msg.toRecipients.push(Mail.Recipient({address: addr})); });
    if (a.from) { msg.sender = a.from; }
    Mail.activate();
    return JSON.stringify({opened: true, to: a.to, subject: a.subject});
  }
  throw new Error('Unknown command');
}
"""

var payload: [String: Any] = ["cmd": cmd, "exclude": exclude]
switch cmd {
case "accounts":
    break
case "inbox":
    payload["hours"] = Double(opt("hours") ?? "24") ?? 24
    payload["unread"] = flag("unread")
    payload["limit"] = Int(opt("limit") ?? "50") ?? 50
case "read":
    guard let id = opt("id") else { fail("read needs --id from kitmail inbox.") }
    payload["id"] = id
case "draft":
    let to = opts("to")
    if to.isEmpty { fail("draft needs at least one --to.") }
    var body = opt("body") ?? ""
    if let file = opt("body-file") {
        guard let text = try? String(contentsOfFile: file, encoding: .utf8) else { fail("Can't read \(file).") }
        body = text
    }
    payload["to"] = to
    payload["subject"] = opt("subject") ?? ""
    payload["body"] = body
    if let from = opt("from") { payload["from"] = from }
default:
    print(usage, terminator: "")
    exit(cmd == "help" || cmd == "--help" ? 0 : 1)
}

let json = String(data: try! JSONSerialization.data(withJSONObject: payload), encoding: .utf8)!
let script = OSAScript(source: jxa + "\nmain(" + json + ");", language: OSALanguage(forName: "JavaScript"))
var errorInfo: NSDictionary?
guard let result = script.executeAndReturnError(&errorInfo) else {
    let info = (errorInfo as? [String: Any]) ?? [:]
    let message = info.first(where: { $0.key.contains("Message") })?.value as? String ?? "\(info)"
    fail("Mail: \(message)")
}
print(result.stringValue ?? "")
