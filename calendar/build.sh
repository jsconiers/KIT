#!/bin/zsh
# Build KitCal.app (the calendar tool, on EventKit) and put `kitcal` on your PATH.
# macOS asks once for calendar access, under the name "KitCal". A rebuild changes the app's
# signature, so macOS may ask again afterward.
set -e
cd "$(dirname "$0")"
rm -rf KitCal.app
mkdir -p KitCal.app/Contents/MacOS
swiftc -swift-version 5 -O kitcal.swift -o KitCal.app/Contents/MacOS/kitcal
cat > KitCal.app/Contents/Info.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>kitcal</string>
  <key>CFBundleIdentifier</key><string>local.kit.kitcal</string>
  <key>CFBundleName</key><string>KitCal</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSCalendarsFullAccessUsageDescription</key>
  <string>Kit reads your calendars, and with your OK adds and changes events.</string>
</dict>
</plist>
PLIST
codesign --force --sign - --identifier local.kit.kitcal KitCal.app
cat > kitcal <<'WRAP'
#!/bin/zsh
# kitcal: runs KitCal.app, so calendar access belongs to "KitCal" whoever calls it.
APP="$HOME/Claude/Agents/kit/.install/calendar/KitCal.app"
out=$(/usr/bin/mktemp -t kitcal) err=$(/usr/bin/mktemp -t kitcal) oerr=$(/usr/bin/mktemp -t kitcal)
trap 'rm -f "$out" "$err" "$oerr"' EXIT
/usr/bin/open -W -n -g --stdout "$out" --stderr "$err" "$APP" --args "$@" 2>"$oerr"
if [ ! -s "$out" ] && [ ! -s "$err" ]; then cat "$oerr" >&2; exit 1; fi
cat "$out"
if [ -s "$err" ]; then cat "$err" >&2; exit 1; fi
WRAP
chmod +x kitcal
mkdir -p "$HOME/.local/bin"
ln -sf "$PWD/kitcal" "$HOME/.local/bin/kitcal"
echo "Built KitCal.app; kitcal is on your PATH."
