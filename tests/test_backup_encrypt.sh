#!/bin/bash
# Tests kit-backup's encryption and backup-location rules. Everything runs in a throwaway folder with a
# fake Kit; the passphrase is a plain test phrase from an environment variable. A wrapper around the
# real openssl records its command lines, so the test can check the passphrase never appears there.
#   bash tests/test_backup_encrypt.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HERE/shared/bin"
S="$(mktemp -d)"; trap 'rm -rf "$S"' EXIT
S="$(cd "$S" && pwd -P)"
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; }

export KIT_DIR="$S/home/kit" HOME="$S/home"
mkdir -p "$KIT_DIR/memory" "$S/wrap"
( cd "$KIT_DIR" && git init -q -b main && echo "queue v1" > QUEUE.md && echo "note" > memory/a.md \
  && git add -A && git -c user.name=t -c user.email=t@t commit -qm one )
REAL=$(command -v openssl)
cat > "$S/wrap/openssl" <<EOF
#!/bin/bash
printf '%s\n' "\$*" >> "$S/openssl-args.txt"
exec "$REAL" "\$@"
EOF
chmod +x "$S/wrap/openssl"
export PATH="$S/wrap:$PATH"
PHRASE="purple elephant riverbank"
export KIT_TEST_PHRASE="$PHRASE" BACKUP_KEY_ENV=KIT_TEST_PHRASE BACKUP_ENCRYPT=on BACKUP_DIR="$HOME/bk"
BK() { python3 "$BIN/kit-backup" "$@"; }

# ---- encrypted round trip --------------------------------------------------------------------------
out=$(BK 2>&1)
echo "$out" | grep -q "encrypted), checked$" && ok "encrypted backup made and checked" || bad "encrypted make: $out"
A=$(ls "$HOME/bk"/kit-backup-*.tar.gz.enc 2>/dev/null | head -1)
[ -n "$A" ] && ok "archive ends in .tar.gz.enc" || bad "no .enc archive"
ls "$HOME/bk"/*.tar.gz 2>/dev/null | grep -q . && bad "plain .tar.gz left behind" || ok "no plain archive left behind"
head -c 8 "$A" | grep -q "KITBAK1" && ok "file starts with the Kit header" || bad "header missing"
tar -tzf "$A" >/dev/null 2>&1 && bad "encrypted file opens as a plain tar" || ok "contents unreadable without decrypting"
[ "$(stat -f %Lp "$A")" = 600 ] && ok "owner-only permissions" || bad "perms"
BK verify "$A" | grep -q "checks out" && ok "verify with the right passphrase" || bad "verify"
BK restore "$A" --to "$S/restored" >/dev/null 2>&1
diff -q "$KIT_DIR/QUEUE.md" "$S/restored/QUEUE.md" >/dev/null && [ -f "$S/restored/memory/a.md" ] \
  && [ "$(git -C "$S/restored" log --oneline | wc -l | tr -d ' ')" = 1 ] \
  && ok "restore decrypts files and history" || bad "restore"
BK list | grep -q ".tar.gz.enc" && ok "list shows encrypted backups" || bad "list"

# ---- secrecy: passphrase never on a command line or in output ---------------------------------------
grep -q "fd:" "$S/openssl-args.txt" && ok "openssl gets the passphrase on a file descriptor" || bad "no fd pass"
grep -qF "$PHRASE" "$S/openssl-args.txt" && bad "passphrase appeared in openssl's arguments" \
  || ok "passphrase never in openssl's arguments"
echo "$out" | grep -qF "$PHRASE" && bad "passphrase printed" || ok "passphrase never printed"
grep -qF "$PHRASE" "$A" && bad "passphrase stored in the archive" || ok "passphrase not stored in the archive"

# ---- wrong passphrase and tampering: caught before decrypting, nothing written -----------------------
r=$(KIT_TEST_PHRASE="green meadow lantern" BK verify "$A" 2>&1)
echo "$r" | grep -q "wrong passphrase, or the file was changed" && ok "wrong passphrase is caught" || bad "wrong pass: $r"
KIT_TEST_PHRASE="green meadow lantern" BK restore "$A" --to "$S/r2" >/dev/null 2>&1
[ ! -e "$S/r2/QUEUE.md" ] && ok "wrong passphrase restores nothing" || bad "wrong pass wrote files"
python3 - "$A" "$S/ct-bad.enc" <<'PY'
import sys
d = bytearray(open(sys.argv[1], "rb").read()); d[-10] ^= 0x01
open(sys.argv[2], "wb").write(d)
PY
BK verify "$S/ct-bad.enc" 2>&1 | grep -q "wrong passphrase, or the file was changed" && ok "changed ciphertext is caught" || bad "ct tamper"
python3 - "$A" "$S/hdr-bad.enc" <<'PY'
import sys
d = open(sys.argv[1], "rb").read()
d = d.replace(b'"iterations": 600000', b'"iterations": 600001', 1)
open(sys.argv[2], "wb").write(d)
PY
BK verify "$S/hdr-bad.enc" 2>&1 | grep -qE "wrong passphrase, or the file was changed|damaged" && ok "changed header is caught" || bad "hdr tamper"
printf 'not a backup' > "$S/junk.enc"; cp "$S/junk.enc" "$HOME/bk/kit-backup-20000101-000000.tar.gz.enc"
BK verify "$S/junk.enc" 2>&1 | grep -q "bad header" && ok "junk file is refused" || bad "junk"
rm -f "$HOME/bk/kit-backup-20000101-000000.tar.gz.enc"

# ---- no passphrase source --------------------------------------------------------------------------
r=$(env -u BACKUP_KEY_ENV BACKUP_KEY_KEYCHAIN= python3 "$BIN/kit-backup" 2>&1)
echo "$r" | grep -q "no passphrase source is set" && ok "encryption without a passphrase source writes nothing" || bad "no source: $r"
r=$(KIT_TEST_PHRASE= BK 2>&1)
echo "$r" | grep -q "isn't set" && ok "empty passphrase variable is refused" || bad "empty var: $r"

# ---- location of your choice, and plain backups kept off shared folders -------------------------------
mkdir -p "$S/elsewhere"
r=$(BACKUP_ENCRYPT=off BK --dir "$S/elsewhere" 2>&1)
echo "$r" | grep -q "outside your home folder" && ok "plain backup outside home is refused" || bad "plain outside home: $r"
mkdir -p "$HOME/Library/CloudStorage/OneDrive-Example/Kit"
r=$(BACKUP_ENCRYPT=off BK --dir "$HOME/Library/CloudStorage/OneDrive-Example/Kit" 2>&1)
echo "$r" | grep -q "synced or shared folder" && ok "plain backup to a synced folder is refused" || bad "plain cloud: $r"
ls "$HOME/Library/CloudStorage/OneDrive-Example/Kit" | grep -q . && bad "refused backup left a file" || ok "refused backup writes nothing"
BACKUP_ENCRYPT=off BK --dir "$S/elsewhere" --allow-plain | grep -q "checked$" && ok "--allow-plain overrides, on purpose" || bad "allow-plain"
BK --dir "$HOME/Library/CloudStorage/OneDrive-Example/Kit" | grep -q "encrypted), checked$" \
  && ok "encrypted backup to a synced folder of your choice" || bad "encrypted cloud"
BK --dir "$S/elsewhere" --encrypt | grep -q "encrypted), checked$" && ok "--dir and --encrypt for one run" || bad "dir+encrypt"

echo "backup encryption tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
