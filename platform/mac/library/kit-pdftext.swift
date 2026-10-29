import AppKit
import Foundation
import PDFKit
import Vision

// kit-pdftext: the text of PDF files, for kit-library. Reads one path per line on standard input and
// writes one JSON line per path: {"path": P, "pages": N, "text": T, "ocr_pages": K}, or
// {"path": P, "error": E} for a PDF it can't read (damaged, locked). Read-only.
//
//   kit-pdftext [--max-chars N] [--max-pages N] [--ocr] [--ocr-max-pages N]
//
// --ocr reads the pages that have no text layer (scans) with the Mac's own text recognition
// (Vision), on this computer; nothing is sent anywhere. --ocr-max-pages caps how many pages of one
// PDF it recognizes (default 60), since a scanned page takes about a second.

var maxChars = 600_000
var maxPages = 2000
var ocr = false
var ocrMaxPages = 60
let argv = CommandLine.arguments
if let i = argv.firstIndex(of: "--max-chars"), i + 1 < argv.count, let n = Int(argv[i + 1]) { maxChars = n }
if let i = argv.firstIndex(of: "--max-pages"), i + 1 < argv.count, let n = Int(argv[i + 1]) { maxPages = n }
if let i = argv.firstIndex(of: "--ocr-max-pages"), i + 1 < argv.count, let n = Int(argv[i + 1]) { ocrMaxPages = n }
ocr = argv.contains("--ocr")

func emit(_ obj: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: obj, options: []),
          let line = String(data: data, encoding: .utf8) else { return }
    FileHandle.standardOutput.write((line + "\n").data(using: .utf8)!)
}

func recognize(_ page: PDFPage) -> String {
    let box = page.bounds(for: .mediaBox)
    let longest = max(box.width, box.height)
    guard longest > 0 else { return "" }
    let scale = min(3.0, 2200.0 / longest)                 // about 200 dpi for a letter page
    let size = NSSize(width: box.width * scale, height: box.height * scale)
    let image = page.thumbnail(of: size, for: .mediaBox)
    var rect = CGRect(origin: .zero, size: image.size)
    guard let cg = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else { return "" }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US"]
    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
    } catch {
        return ""
    }
    return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
}

func meaningful(_ s: String?) -> Bool {
    guard let s = s else { return false }
    return s.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) }.count >= 20
}

while let line = readLine(strippingNewline: true) {
    let path = line.trimmingCharacters(in: .whitespaces)
    if path.isEmpty { continue }
    autoreleasepool {
        guard let doc = PDFDocument(url: URL(fileURLWithPath: path)) else {
            emit(["path": path, "error": "unreadable"])
            return
        }
        if doc.isLocked {
            emit(["path": path, "error": "locked", "pages": doc.pageCount])
            return
        }
        var parts: [String] = []
        var total = 0
        var recognized = 0
        for i in 0..<min(doc.pageCount, maxPages) {
            guard let page = doc.page(at: i) else { continue }
            var s = page.string ?? ""
            if ocr && !meaningful(s) && recognized < ocrMaxPages {
                autoreleasepool { s = recognize(page) }
                recognized += 1
            }
            if s.isEmpty { continue }
            parts.append(s)
            total += s.utf16.count
            if total >= maxChars { break }
        }
        emit(["path": path, "pages": doc.pageCount, "text": parts.joined(separator: "\n\n"), "ocr_pages": recognized])
    }
}
