#!/bin/zsh
# Build KitMail.app (the mail tool) and put `kitmail` on your PATH.
# macOS asks once to let "KitMail" control Mail. A rebuild changes the app's signature, so macOS
# may ask again afterward.
set -e
cd "$(dirname "$0")"
rm -rf KitMail.app
mkdir -p KitMail.app/Contents/MacOS
swiftc -swift-version 5 -O kitmail.swift -o KitMail.app/Contents/MacOS/kitmail
cat > KitMail.app/Contents/Info.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>kitmail</string>
  <key>CFBundleIdentifier</key><string>local.kit.kitmail</string>
  <key>CFBundleName</key><string>KitMail</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>Kit reads your mail and opens drafts for you to review. It never sends anything.</string>
</dict>
</plist>
PLIST
codesign --force --sign - --identifier local.kit.kitmail KitMail.app
cat > kitmail <<'WRAP'
#!/bin/zsh
# kitmail: runs KitMail.app, so Mail access belongs to "KitMail" whoever calls it.
APP="$HOME/Claude/Agents/kit/.install/platform/mac/mail/KitMail.app"
out=$(/usr/bin/mktemp -t kitmail) err=$(/usr/bin/mktemp -t kitmail) oerr=$(/usr/bin/mktemp -t kitmail)
trap 'rm -f "$out" "$err" "$oerr"' EXIT
# inbox: the quick way first (kitmail_fast.py reads Mail's index through KitMessages.app), else ask Mail.
# Each try is logged in .install/logs/mail.log, which kit doctor reads. KITMAIL_FAST=off skips it.
FAST="$HOME/Claude/Agents/kit/.install/platform/mac/mail/kitmail_fast.py"
if [ "${1:-}" = "inbox" ] && [ "${KITMAIL_FAST:-on}" != "off" ] && [ -f "$FAST" ]; then
  MLOG="$HOME/Claude/Agents/kit/.install/logs/mail.log"
  mkdir -p "${MLOG:h}"
  if /usr/bin/python3 "$FAST" "$@" > "$out" 2> "$err"; then
    print "$(date '+%Y-%m-%d %H:%M:%S') quick inbox ok" >> "$MLOG"
    cat "$out"; exit 0
  fi
  print "$(date '+%Y-%m-%d %H:%M:%S') quick inbox unavailable ($(head -c 120 "$err" | tr '\n' ' '))" >> "$MLOG"
  : > "$out"; : > "$err"
fi
/usr/bin/open -W -n -g --stdout "$out" --stderr "$err" "$APP" --args "$@" 2>"$oerr"
if [ ! -s "$out" ] && [ ! -s "$err" ]; then cat "$oerr" >&2; exit 1; fi
cat "$out"
if [ -s "$err" ]; then cat "$err" >&2; exit 1; fi
WRAP
chmod +x kitmail
mkdir -p "$HOME/.local/bin"
ln -sf "$PWD/kitmail" "$HOME/.local/bin/kitmail"
echo "Built KitMail.app; kitmail is on your PATH."
