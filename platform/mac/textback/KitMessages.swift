import Foundation
import SQLite3

// KitMessages: reads new messages in the owner's own Messages conversation for kit-textback, and the
// list of messages in Mail's inboxes for kitmail (--mail, below), so Full Disk Access belongs to
// "KitMessages" alone, whoever starts it. Read-only: it opens each database read-only and never
// sends, changes, or deletes anything.
//
//   KitMessages --out FILE --since ROWID --chats ID1,ID2 [--wait SECONDS] [--every SECONDS]
//
// Writes JSON to FILE (mode 600): {"max_rowid": N, "messages": [...]}, or {"error": "no-access" |
// "db", "detail": "..."} when the database can't be read. --since -1 reports the newest message
// number only, so a first run starts from now. With --wait it checks every --every seconds (default
// 3) until a new message arrives in one of the chats or the wait is over. Each message: rowid, guid,
// text (null when it's only in the archived body), body (base64 of attributedBody, when text is
// null), from_me, date (Unix seconds), service, handle, chat, assoc (reactions are nonzero), item.

let args = CommandLine.arguments
func arg(_ name: String) -> String? {
    guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
    return args[i + 1]
}
guard let outPath = arg("--out") else {
    FileHandle.standardError.write(Data("usage: KitMessages --out FILE --since ROWID --chats IDS\n".utf8))
    exit(2)
}
let since = Int64(arg("--since") ?? "-1") ?? -1
let chats = (arg("--chats") ?? "").split(separator: ",").map { String($0) }.filter { !$0.isEmpty }
let waitSeconds = Double(arg("--wait") ?? "0") ?? 0
let every = max(1.0, Double(arg("--every") ?? "3") ?? 3)
let dbPath = NSHomeDirectory() + "/Library/Messages/chat.db"

func write(_ obj: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: obj, options: []) else { return }
    let tmp = outPath + ".tmp"
    FileManager.default.createFile(atPath: tmp, contents: data, attributes: [.posixPermissions: 0o600])
    _ = try? FileManager.default.removeItem(atPath: outPath)
    try? FileManager.default.moveItem(atPath: tmp, toPath: outPath)
}

func fail(_ kind: String, _ detail: String) -> Never {
    write(["error": kind, "detail": detail])
    exit(3)
}

// ------------------------------------------------------------------ Mail's message list
// KitMessages --mail --out FILE --since UNIXSECONDS [--limit N] [--unread]
// KitMessages --mail-accounts --out FILE
//
// Reads the list of messages in each Mail inbox (sender, subject, date, read and flagged) from
// Mail's own index, read-only, so Kit's mail check doesn't wait on Mail. Never reads message bodies.
// Accounts are allowed by name, never assumed: an inbox is read only when its account is found in
// macOS's account list and matches none of the "exclude" entries in Kit's mail config
// (~/Claude/Agents/kit/.install/mail/config.json). If an exclude entry matches no account at all,
// nothing is read ("exclusion-unverified"), so a renamed or unrecognized account can't slip through;
// kitmail then falls back to asking Mail. --mail-accounts lists the accounts and the verdicts only.
// Test overrides: --mail-db PATH --accounts-db PATH --mail-config PATH.
if args.contains("--mail") || args.contains("--mail-accounts") {
    runMail()
}

func openReadOnly(_ path: String) -> (OpaquePointer?, String?) {
    var handle: OpaquePointer?
    if sqlite3_open_v2(path, &handle, SQLITE_OPEN_READONLY, nil) != SQLITE_OK {
        let msg = handle != nil ? String(cString: sqlite3_errmsg(handle)) : "can't open"
        sqlite3_close(handle)
        return (nil, msg)
    }
    sqlite3_busy_timeout(handle, 3000)
    return (handle, nil)
}

func text(_ stmt: OpaquePointer?, _ i: Int32) -> String {
    guard sqlite3_column_type(stmt, i) != SQLITE_NULL, let c = sqlite3_column_text(stmt, i) else { return "" }
    return String(cString: c)
}

func columns(_ handle: OpaquePointer?, _ table: String) -> Set<String> {
    var stmt: OpaquePointer?
    var out = Set<String>()
    if sqlite3_prepare_v2(handle, "PRAGMA table_info(\(table))", -1, &stmt, nil) == SQLITE_OK {
        while sqlite3_step(stmt) == SQLITE_ROW { out.insert(text(stmt, 1).lowercased()) }
    }
    sqlite3_finalize(stmt)
    return out
}

func isDenied(_ msg: String) -> Bool {
    let m = msg.lowercased()
    return m.contains("authorization") || m.contains("not permitted") || m.contains("permission")
}

func emails(in s: String) -> [String] {
    guard let rx = try? NSRegularExpression(pattern: "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}") else { return [] }
    let range = NSRange(s.startIndex..., in: s)
    return rx.matches(in: s, range: range).compactMap { Range($0.range, in: s).map { String(s[$0]) } }
}

func runMail() -> Never {
    let home = NSHomeDirectory()
    // Which Mail index: the newest Library/Mail/V*/MailData/Envelope Index.
    var mailDB = arg("--mail-db")
    if mailDB == nil {
        let lib = home + "/Library/Mail"
        do {
            let names = try FileManager.default.contentsOfDirectory(atPath: lib)
            let versions = names.compactMap { n -> Int? in n.hasPrefix("V") ? Int(n.dropFirst()) : nil }.sorted(by: >)
            mailDB = versions.map { "\(lib)/V\($0)/MailData/Envelope Index" }
                .first { FileManager.default.fileExists(atPath: $0) }
        } catch {
            let ns = error as NSError
            fail(ns.code == NSFileReadNoPermissionError || isDenied(ns.localizedDescription) ? "no-access" : "db",
                 "Library/Mail: \(ns.localizedDescription)")
        }
    }
    guard let mailPath = mailDB else { fail("db", "no Mail index found (is Mail set up?)") }

    // What's excluded: Kit's mail config, never anything from the command line alone.
    var exclude: [String] = []
    let configPath = arg("--mail-config") ?? home + "/Claude/Agents/kit/.install/mail/config.json"
    if let data = FileManager.default.contents(atPath: configPath),
       let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
        exclude = ((json["exclude"] as? [String]) ?? []).map { $0.lowercased().trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    } else if FileManager.default.fileExists(atPath: configPath) {
        fail("config", "can't read \(configPath)")
    }

    // macOS's account list: identifier -> the names that identify it (own and parent's).
    var known: [String: [String]] = [:]
    var labels: [String: String] = [:]
    let (acc, accErr) = openReadOnly(arg("--accounts-db") ?? home + "/Library/Accounts/Accounts4.sqlite")
    if let accErr = accErr { fail(isDenied(accErr) ? "no-access" : "db", "accounts: \(accErr)") }
    var stmt: OpaquePointer?
    let accSQL = """
        SELECT a.ZIDENTIFIER, IFNULL(a.ZUSERNAME, ''), IFNULL(a.ZACCOUNTDESCRIPTION, ''),
               IFNULL(p.ZUSERNAME, ''), IFNULL(p.ZACCOUNTDESCRIPTION, '')
        FROM ZACCOUNT a LEFT JOIN ZACCOUNT p ON p.Z_PK = a.ZPARENTACCOUNT
        """
    if sqlite3_prepare_v2(acc, accSQL, -1, &stmt, nil) != SQLITE_OK {
        let msg = String(cString: sqlite3_errmsg(acc))
        fail(isDenied(msg) ? "no-access" : "db", "accounts: \(msg)")
    }
    while sqlite3_step(stmt) == SQLITE_ROW {
        let id = text(stmt, 0).uppercased()
        if id.isEmpty { continue }
        let names = (1...4).map { text(stmt, Int32($0)) }.filter { !$0.isEmpty }
        known[id] = names.map { $0.lowercased() }
        labels[id] = [text(stmt, 2), text(stmt, 4), text(stmt, 1), text(stmt, 3)].first { !$0.isEmpty } ?? id
    }
    sqlite3_finalize(stmt)
    sqlite3_close(acc)

    let (db, dbErr) = openReadOnly(mailPath)
    if let dbErr = dbErr { fail(isDenied(dbErr) ? "no-access" : "db", dbErr) }

    // Inboxes, and the account each belongs to (the host part of the mailbox URL).
    var inboxes: [Int64: String] = [:]      // mailbox ROWID -> account key
    var verdicts: [String: [String: Any]] = [:]
    var matched = Set<String>()
    if sqlite3_prepare_v2(db, "SELECT ROWID, IFNULL(url, '') FROM mailboxes", -1, &stmt, nil) != SQLITE_OK {
        let msg = String(cString: sqlite3_errmsg(db))
        fail(isDenied(msg) ? "no-access" : "db", msg)
    }
    while sqlite3_step(stmt) == SQLITE_ROW {
        let rowid = sqlite3_column_int64(stmt, 0)
        let url = text(stmt, 1)
        guard let comps = URLComponents(string: url), let rawHost = comps.percentEncodedHost ?? comps.host else { continue }
        let path = comps.path.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard path == "inbox" else { continue }
        var key = (rawHost.removingPercentEncoding ?? rawHost)
        if let user = comps.user?.removingPercentEncoding { key = user + "@" + key }
        let upper = key.uppercased()
        if verdicts[upper] == nil {
            var ids: [String] = []
            var label = key
            if let names = known[upper] {
                ids = names
                label = labels[upper] ?? key
            } else {
                ids = emails(in: key).map { $0.lowercased() }
                if let e = ids.first { label = e }
            }
            let hits = exclude.filter { term in ids.contains { $0 == term || (term.count >= 5 && $0.contains(term)) } }
            hits.forEach { matched.insert($0) }
            let allowed = !ids.isEmpty && hits.isEmpty
            verdicts[upper] = ["key": key, "label": label, "allowed": allowed,
                               "why": hits.isEmpty ? (ids.isEmpty ? "unknown account" : "ok") : "excluded"]
        }
        if verdicts[upper]?["allowed"] as? Bool == true { inboxes[rowid] = upper }
    }
    sqlite3_finalize(stmt)

    // Exclusions that matched no inbox's account: maybe an account the config names but that isn't in
    // Mail, maybe one Kit can't recognize. Check the whole account list before trusting the result.
    let unverified = exclude.filter { term in
        !matched.contains(term) && !known.values.contains { ids in ids.contains { $0 == term || (term.count >= 5 && $0.contains(term)) } }
    }
    let accountList = verdicts.values.map { v -> [String: Any] in
        ["label": v["label"] ?? "", "allowed": v["allowed"] ?? false, "why": v["why"] ?? ""]
    }
    if args.contains("--mail-accounts") {
        write(["accounts": accountList, "unverified_excludes": unverified.count, "index": mailPath])
        exit(0)
    }
    if !unverified.isEmpty {
        fail("exclusion-unverified", "\(unverified.count) exclude entr\(unverified.count == 1 ? "y matches" : "ies match") no account; not reading mail this way")
    }
    if inboxes.isEmpty { fail("no-inboxes", "no allowed inboxes found") }

    let have = columns(db, "messages")
    func col(_ name: String, _ fallback: String) -> String { have.contains(name) ? "m.\(name)" : fallback }
    let marks = Array(repeating: "?", count: inboxes.count).joined(separator: ",")
    let sql = """
        SELECT m.ROWID, m.mailbox, IFNULL(a.address, ''), IFNULL(a.comment, ''), IFNULL(\(col("subject_prefix", "''")), ''),
               IFNULL(s.subject, ''), IFNULL(\(col("date_received", "0")), 0), IFNULL(\(col("read", "0")), 0),
               IFNULL(\(col("flagged", "0")), 0)
        FROM messages m
        LEFT JOIN addresses a ON a.ROWID = m.sender
        LEFT JOIN subjects s ON s.ROWID = m.subject
        WHERE m.mailbox IN (\(marks)) AND IFNULL(\(col("date_received", "0")), 0) >= ?
          AND IFNULL(\(col("deleted", "0")), 0) = 0
        ORDER BY \(col("date_received", "m.ROWID")) DESC LIMIT ?
        """
    if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) != SQLITE_OK {
        fail("db", String(cString: sqlite3_errmsg(db)))
    }
    let ids = Array(inboxes.keys)
    for (i, id) in ids.enumerated() { sqlite3_bind_int64(stmt, Int32(i + 1), id) }
    let sinceMail = Int64(arg("--since") ?? "0") ?? 0
    let limit = Int64(arg("--limit") ?? "50") ?? 50
    let unreadOnly = args.contains("--unread")
    sqlite3_bind_int64(stmt, Int32(ids.count + 1), sinceMail)
    sqlite3_bind_int64(stmt, Int32(ids.count + 2), unreadOnly ? limit * 20 : limit)
    var out: [[String: Any]] = []
    while sqlite3_step(stmt) == SQLITE_ROW {
        let read = sqlite3_column_int64(stmt, 7) != 0
        if unreadOnly && read { continue }
        let key = inboxes[sqlite3_column_int64(stmt, 1)] ?? ""
        let address = text(stmt, 2), name = text(stmt, 3)
        let prefix = text(stmt, 4), subject = text(stmt, 5)
        out.append(["id": sqlite3_column_int64(stmt, 0),
                    "account": (verdicts[key]?["label"] as? String) ?? "",
                    "from": name.isEmpty ? address : (address.isEmpty ? name : "\(name) <\(address)>"),
                    "subject": prefix.isEmpty ? subject : prefix + subject,
                    "received": sqlite3_column_int64(stmt, 6),
                    "read": read, "flagged": sqlite3_column_int64(stmt, 8) != 0])
        if out.count >= Int(limit) { break }
    }
    sqlite3_finalize(stmt)
    sqlite3_close(db)
    write(["messages": out, "accounts": accountList])
    exit(0)
}

var db: OpaquePointer?
if sqlite3_open_v2(dbPath, &db, SQLITE_OPEN_READONLY, nil) != SQLITE_OK {
    let msg = db != nil ? String(cString: sqlite3_errmsg(db)) : "can't open"
    fail(msg.lowercased().contains("authorization") ? "no-access" : "db", msg)
}
sqlite3_busy_timeout(db, 3000)

func errorText() -> String { String(cString: sqlite3_errmsg(db)) }

func checkAccess(_ rc: Int32) {
    if rc != SQLITE_OK {
        let msg = errorText()
        let denied = msg.lowercased().contains("authorization") || rc == SQLITE_AUTH || rc == SQLITE_CANTOPEN
            || rc == SQLITE_PERM
        fail(denied ? "no-access" : "db", msg)
    }
}

func maxRowid() -> Int64 {
    var stmt: OpaquePointer?
    checkAccess(sqlite3_prepare_v2(db, "SELECT IFNULL(MAX(ROWID), 0) FROM message", -1, &stmt, nil))
    defer { sqlite3_finalize(stmt) }
    return sqlite3_step(stmt) == SQLITE_ROW ? sqlite3_column_int64(stmt, 0) : 0
}

func column(_ stmt: OpaquePointer?, _ i: Int32) -> String? {
    guard sqlite3_column_type(stmt, i) != SQLITE_NULL, let c = sqlite3_column_text(stmt, i) else { return nil }
    return String(cString: c)
}

func newMessages(after rowid: Int64) -> [[String: Any]] {
    if chats.isEmpty { return [] }
    let marks = Array(repeating: "?", count: chats.count).joined(separator: ",")
    let sql = """
        SELECT m.ROWID, IFNULL(m.guid, ''), m.text, m.attributedBody, IFNULL(m.is_from_me, 0),
               IFNULL(m.date, 0), IFNULL(m.service, ''), IFNULL(h.id, ''), IFNULL(c.chat_identifier, ''),
               IFNULL(m.associated_message_type, 0), IFNULL(m.item_type, 0)
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        JOIN chat c ON c.ROWID = cmj.chat_id
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        WHERE m.ROWID > ? AND c.chat_identifier IN (\(marks))
        ORDER BY m.ROWID LIMIT 50
        """
    var stmt: OpaquePointer?
    checkAccess(sqlite3_prepare_v2(db, sql, -1, &stmt, nil))
    defer { sqlite3_finalize(stmt) }
    sqlite3_bind_int64(stmt, 1, rowid)
    let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
    for (i, chat) in chats.enumerated() {
        sqlite3_bind_text(stmt, Int32(i + 2), chat, -1, transient)
    }
    var out: [[String: Any]] = []
    while sqlite3_step(stmt) == SQLITE_ROW {
        var row: [String: Any] = ["rowid": sqlite3_column_int64(stmt, 0), "guid": column(stmt, 1) ?? ""]
        let text = column(stmt, 2)
        row["text"] = text ?? NSNull()
        if text == nil, let blob = sqlite3_column_blob(stmt, 3) {
            let data = Data(bytes: blob, count: Int(sqlite3_column_bytes(stmt, 3)))
            row["body"] = data.base64EncodedString()
        }
        row["from_me"] = sqlite3_column_int64(stmt, 4)
        let raw = Double(sqlite3_column_int64(stmt, 5))
        row["date"] = (raw > 1e12 ? raw / 1e9 : raw) + 978_307_200   // Apple's 2001 epoch to Unix
        row["service"] = column(stmt, 6) ?? ""
        row["handle"] = column(stmt, 7) ?? ""
        row["chat"] = column(stmt, 8) ?? ""
        row["assoc"] = sqlite3_column_int64(stmt, 9)
        row["item"] = sqlite3_column_int64(stmt, 10)
        out.append(row)
    }
    return out
}

let deadline = Date().addingTimeInterval(waitSeconds)
while true {
    let top = maxRowid()
    if since < 0 {
        write(["max_rowid": top, "messages": []])
        exit(0)
    }
    let found = top > since ? newMessages(after: since) : []
    if !found.isEmpty || Date() >= deadline {
        let last = (found.last?["rowid"] as? Int64) ?? since
        write(["max_rowid": found.count == 50 ? last : max(top, since), "messages": found])
        exit(0)
    }
    Thread.sleep(forTimeInterval: every)
}
