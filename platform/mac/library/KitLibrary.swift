import Foundation

// KitLibrary: runs kit-library for the jobs that need to read or write folders macOS protects
// (Documents, and iCloud Drive for the phone copy), so that permission belongs to "KitLibrary" alone,
// whoever starts it. It runs only these kit-library commands: index (read the cataloged folders),
// flush (copy finished deliveries from Kit's outbox into the output folder), mirror (copy the output
// folder to the phone folder in iCloud Drive), fetch (copy one cataloged file into Kit's own folder so
// it can be texted to you), and --check. Anything else is refused.

let allowed: Set<String> = ["index", "flush", "mirror", "fetch", "--check"]
let args = Array(CommandLine.arguments.dropFirst())
guard let first = args.first, allowed.contains(first) else {
    FileHandle.standardError.write(Data("KitLibrary runs only: kit-library index | flush | mirror | fetch | --check\n".utf8))
    exit(2)
}
let home = NSHomeDirectory()
let script = home + "/Claude/Agents/kit/.install/shared/bin/kit-library"
var env = ProcessInfo.processInfo.environment
env["PATH"] = home + "/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
env["KIT_LIBRARY_IN_APP"] = "1"
let p = Process()
p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
p.arguments = ["python3", script] + args
p.environment = env
do {
    try p.run()
    p.waitUntilExit()
    exit(p.terminationStatus)
} catch {
    FileHandle.standardError.write(Data("KitLibrary: \(error)\n".utf8))
    exit(1)
}
