// kitcal: Kit's calendar tool for Apple Calendar, built on EventKit.
//
// Safety, enforced here rather than left to the agent:
// - Calendars and accounts listed under "exclude" in the config are never read or written.
// - Events with attendees are never changed or deleted, so kitcal can't notify anyone.
//
//   kitcal calendars
//   kitcal events [--from DATE] [--to DATE] [--cal NAME ...]
//   kitcal free [--date DATE] [--from HH:MM] [--to HH:MM]
//   kitcal add --title T (--start "DATE HH:MM" --end "DATE HH:MM" | --all-day --date DATE)
//              [--cal NAME] [--location L] [--notes N] [--alert MINUTES]
//   kitcal move --id ID --start "DATE HH:MM" [--end "DATE HH:MM"] [--span this|future]
//   kitcal update --id ID [--title T] [--location L] [--notes N] [--cal NAME] [--span this|future]
//   kitcal delete --id ID [--span this|future]
//
// DATE is YYYY-MM-DD, "today", or "tomorrow". Output is JSON. Config:
// ~/Claude/Agents/kit/.install/calendar/config.json = {"default": "...", "exclude": ["..."]}
import EventKit
import Foundation

let usage = """
kitcal calendars | events | free | add | move | update | delete  (see the top of kitcal.swift)
"""
let configPath = NSHomeDirectory() + "/Claude/Agents/kit/.install/calendar/config.json"

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

func emit(_ obj: Any) {
    let data = try! JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}

var defaultCalendar: String? = nil
var excludeNames: Set<String> = []
if let data = FileManager.default.contents(atPath: configPath),
   let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
    defaultCalendar = json["default"] as? String
    excludeNames = Set(((json["exclude"] as? [String]) ?? []).map { $0.lowercased() })
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

func formatter(_ pattern: String) -> DateFormatter {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = TimeZone.current
    f.dateFormat = pattern
    return f
}
let dayFmt = formatter("yyyy-MM-dd")
let timeFmt = formatter("yyyy-MM-dd HH:mm")
let cal = Calendar.current

func day(_ s: String?) -> Date {
    switch s?.lowercased() {
    case nil, "today"?: return cal.startOfDay(for: Date())
    case "tomorrow"?: return cal.date(byAdding: .day, value: 1, to: cal.startOfDay(for: Date()))!
    default:
        guard let d = dayFmt.date(from: s!) else { fail("Dates look like 2026-10-08, today, or tomorrow.") }
        return d
    }
}
func moment(_ s: String?) -> Date {
    guard let s = s, let d = timeFmt.date(from: s) else { fail("Times look like \"2026-10-08 14:30\".") }
    return d
}
func show(_ d: Date) -> String { timeFmt.string(from: d) }

let store = EKEventStore()

func ensureAccess() {
    let status = EKEventStore.authorizationStatus(for: .event)
    if status == .fullAccess { return }
    if status == .denied || status == .restricted || status == .writeOnly {
        fail("KitCal doesn't have full calendar access. Turn it on in System Settings > Privacy & Security > Calendars.")
    }
    let sem = DispatchSemaphore(value: 0)
    var granted = false
    store.requestFullAccessToEvents { ok, _ in
        granted = ok
        sem.signal()
    }
    if sem.wait(timeout: .now() + 90) == .timedOut {
        fail("Waiting for calendar permission. Approve the KitCal prompt, then run this again.")
    }
    if !granted { fail("Calendar access wasn't granted.") }
    store.reset()
}

func isExcluded(_ c: EKCalendar) -> Bool {
    excludeNames.contains(c.title.lowercased()) || excludeNames.contains(c.source.title.lowercased())
}
func allowedCalendars() -> [EKCalendar] { store.calendars(for: .event).filter { !isExcluded($0) } }

func calendarNamed(_ name: String?) -> EKCalendar {
    // Accepts "Name" or "Name|Account". Refuses a bare name that matches more than one calendar.
    let raw = name ?? defaultCalendar ?? ""
    if raw.isEmpty { fail("Name a calendar with --cal; no default is set.") }
    let parts = raw.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
    let title = parts[0].lowercased()
    let account = parts.count > 1 ? parts[1].lowercased() : nil
    if excludeNames.contains(title) || (account.map { excludeNames.contains($0) } ?? false) {
        fail("That calendar is off-limits.")
    }
    let matches = allowedCalendars().filter {
        $0.title.lowercased() == title && (account == nil || $0.source.title.lowercased() == account!)
    }
    if matches.isEmpty { fail("No calendar named \(raw). Run: kitcal calendars") }
    if matches.count > 1 {
        fail("More than one calendar is named \(parts[0]): "
             + matches.map { "\($0.title)|\($0.source.title)" }.joined(separator: ", ")
             + ". Use one of those.")
    }
    return matches[0]
}

func ident(_ e: EKEvent) -> String { "\(e.eventIdentifier ?? "")|\(show(e.startDate))" }

func describe(_ e: EKEvent) -> [String: Any] {
    var d: [String: Any] = [
        "id": ident(e), "title": e.title ?? "", "calendar": "\(e.calendar.title)|\(e.calendar.source.title)",
        "start": e.isAllDay ? dayFmt.string(from: e.startDate) : show(e.startDate),
        "end": e.isAllDay ? dayFmt.string(from: e.endDate) : show(e.endDate),
        "all_day": e.isAllDay, "recurring": e.hasRecurrenceRules,
        "attendees": e.attendees?.count ?? 0,
    ]
    if let l = e.location, !l.isEmpty { d["location"] = l }
    return d
}

func findEvent(_ id: String?) -> EKEvent {
    let parts = (id ?? "").components(separatedBy: "|")
    guard parts.count == 2, let at = timeFmt.date(from: parts[1]) else {
        fail("Use an id from kitcal events.")
    }
    let pred = store.predicateForEvents(withStart: at.addingTimeInterval(-86_400),
                                        end: at.addingTimeInterval(2 * 86_400),
                                        calendars: allowedCalendars())
    guard let e = store.events(matching: pred).first(where: {
        $0.eventIdentifier == parts[0] && abs($0.startDate.timeIntervalSince(at)) < 60
    }) else { fail("Event not found. Run kitcal events again for a fresh id.") }
    if (e.attendees?.count ?? 0) > 0 {
        fail("That event has attendees, so changing it would notify them. Change it in Calendar yourself.")
    }
    if !e.calendar.allowsContentModifications { fail("\(e.calendar.title) is read-only.") }
    return e
}

func span() -> EKSpan { opt("span") == "future" ? .futureEvents : .thisEvent }

func save(_ e: EKEvent, as key: String) {
    do { try store.save(e, span: span(), commit: true) } catch {
        fail("Couldn't save: \(error.localizedDescription)")
    }
    emit([key: describe(e)])
}

switch cmd {
case "calendars":
    ensureAccess()
    let def = (defaultCalendar ?? "").lowercased()
    emit(allowedCalendars().map { c -> [String: Any] in
        let ref = "\(c.title)|\(c.source.title)"
        return ["ref": ref, "writable": c.allowsContentModifications,
                "default": def == ref.lowercased() || def == c.title.lowercased()]
    })

case "events":
    ensureAccess()
    let from = day(opt("from"))
    let to = cal.date(byAdding: .day, value: 1, to: day(opt("to") ?? opt("from")))!
    let names = opts("cal")
    let cals = names.isEmpty ? allowedCalendars() : names.map { calendarNamed($0) }
    if cals.isEmpty { emit([Any]()); exit(0) }
    let found = store.events(matching: store.predicateForEvents(withStart: from, end: to, calendars: cals))
    emit(found.sorted { $0.startDate < $1.startDate }.map(describe))

case "free":
    ensureAccess()
    let d = dayFmt.string(from: day(opt("date")))
    let winStart = moment("\(d) \(opt("from") ?? "08:00")")
    let winEnd = moment("\(d) \(opt("to") ?? "21:00")")
    let cals = allowedCalendars()
    let found = cals.isEmpty ? [] : store.events(matching: store.predicateForEvents(
        withStart: winStart, end: winEnd, calendars: cals))
    let busy = found.filter { !$0.isAllDay && $0.availability != .free }
        .map { (max($0.startDate, winStart), min($0.endDate, winEnd)) }
        .sorted { $0.0 < $1.0 }
    var merged: [(Date, Date)] = []
    for b in busy {
        if let last = merged.last, b.0 <= last.1 { merged[merged.count - 1].1 = max(last.1, b.1) }
        else { merged.append(b) }
    }
    var open: [[String: String]] = []
    var cursor = winStart
    for b in merged {
        if b.0 > cursor { open.append(["from": show(cursor), "to": show(b.0)]) }
        cursor = max(cursor, b.1)
    }
    if cursor < winEnd { open.append(["from": show(cursor), "to": show(winEnd)]) }
    emit(["date": d, "busy": merged.map { ["from": show($0.0), "to": show($0.1)] }, "free": open])

case "add":
    ensureAccess()
    guard let title = opt("title") else { fail("add needs --title.") }
    let target = calendarNamed(opt("cal"))
    if !target.allowsContentModifications { fail("\(target.title) is read-only.") }
    let e = EKEvent(eventStore: store)
    e.calendar = target
    e.title = title
    if flag("all-day") {
        let d = day(opt("date"))
        e.isAllDay = true
        e.startDate = d
        e.endDate = d
    } else {
        e.startDate = moment(opt("start"))
        e.endDate = moment(opt("end"))
        if e.endDate <= e.startDate { fail("--end has to be after --start.") }
    }
    if let l = opt("location") { e.location = l }
    if let n = opt("notes") { e.notes = n }
    if let a = opt("alert"), let m = Double(a) { e.addAlarm(EKAlarm(relativeOffset: -m * 60)) }
    save(e, as: "added")

case "move":
    ensureAccess()
    let e = findEvent(opt("id"))
    let length = e.endDate.timeIntervalSince(e.startDate)
    let start = moment(opt("start"))
    e.startDate = start
    e.endDate = opt("end").map { moment($0) } ?? start.addingTimeInterval(length)
    save(e, as: "moved")

case "update":
    ensureAccess()
    let e = findEvent(opt("id"))
    if let t = opt("title") { e.title = t }
    if let l = opt("location") { e.location = l }
    if let n = opt("notes") { e.notes = n }
    if let c = opt("cal") {
        let target = calendarNamed(c)
        if !target.allowsContentModifications { fail("\(target.title) is read-only.") }
        e.calendar = target
    }
    save(e, as: "updated")

case "delete":
    ensureAccess()
    let e = findEvent(opt("id"))
    let gone = describe(e)
    do { try store.remove(e, span: span(), commit: true) } catch {
        fail("Couldn't delete: \(error.localizedDescription)")
    }
    emit(["deleted": gone])

default:
    print(usage)
    exit(cmd == "help" || cmd == "--help" ? 0 : 1)
}
