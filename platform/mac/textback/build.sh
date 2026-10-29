#!/bin/zsh
# Build KitMessages.app, which reads the owner's own Messages conversation for kit-textback, so macOS
# grants Full Disk Access to "KitMessages" only. A rebuild changes the app's signature, so macOS may
# need the access granted again afterward (System Settings > Privacy & Security > Full Disk Access).
set -e
cd "$(dirname "$0")"
rm -rf KitMessages.app
mkdir -p KitMessages.app/Contents/MacOS
swiftc -swift-version 5 -O KitMessages.swift -o KitMessages.app/Contents/MacOS/KitMessages -lsqlite3
cat > KitMessages.app/Contents/Info.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>KitMessages</string>
  <key>CFBundleIdentifier</key><string>local.kit.kitmessages</string>
  <key>CFBundleName</key><string>KitMessages</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
</dict>
</plist>
PLIST
codesign --force --sign - --identifier local.kit.kitmessages KitMessages.app
echo "Built KitMessages.app"
