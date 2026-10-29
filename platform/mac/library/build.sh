#!/bin/zsh
# Build kit-library's Mac helpers:
#   kit-pdftext      reads the text of PDFs (PDFKit); no special permission of its own
#   KitLibrary.app   runs kit-library index / flush / --check, so macOS grants access to Documents (and
#                    any other protected folder you catalog) to "KitLibrary" only
# A rebuild changes KitLibrary.app's signature, so macOS asks for the folder permission again afterward
# (or turn it on in System Settings > Privacy & Security > Files and Folders). "build.sh pdftext"
# rebuilds only kit-pdftext and leaves the app (and its permission) alone.
set -e
cd "$(dirname "$0")"
swiftc -swift-version 5 -O kit-pdftext.swift -o kit-pdftext
if [ "${1:-}" = "pdftext" ]; then echo "Built kit-pdftext"; exit 0; fi
rm -rf KitLibrary.app
mkdir -p KitLibrary.app/Contents/MacOS
swiftc -swift-version 5 -O KitLibrary.swift -o KitLibrary.app/Contents/MacOS/KitLibrary
cat > KitLibrary.app/Contents/Info.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>KitLibrary</string>
  <key>CFBundleIdentifier</key><string>local.kit.kitlibrary</string>
  <key>CFBundleName</key><string>KitLibrary</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSDocumentsFolderUsageDescription</key><string>Kit catalogs the document folders you chose and saves its finished work in Kit Output.</string>
  <key>NSUbiquitousContainersUsageDescription</key><string>Kit copies Kit Output to iCloud Drive so you can open it on your phone.</string>
  <key>NSDesktopFolderUsageDescription</key><string>Kit catalogs the folders you chose.</string>
  <key>NSDownloadsFolderUsageDescription</key><string>Kit catalogs the folders you chose.</string>
</dict>
</plist>
PLIST
codesign --force --sign - --identifier local.kit.kitlibrary KitLibrary.app
echo "Built kit-pdftext and KitLibrary.app"
