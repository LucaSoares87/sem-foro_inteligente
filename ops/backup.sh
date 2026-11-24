#!/usr/bin/env sh
set -eu
umask 077

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
OUT_DIR=${BACKUP_DIR:-"$ROOT/backups"}
mkdir -p "$OUT_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET=${1:-"$OUT_DIR/traffic-$STAMP.dump"}
TMP="$TARGET.tmp.$$"

cleanup(){ rm -f "$TMP"; }
trap cleanup EXIT INT TERM

docker compose exec -T postgres sh -ceu 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$TMP"
if [ ! -s "$TMP" ]; then
  echo "backup vazio; abortando" >&2
  exit 1
fi
mv "$TMP" "$TARGET"
trap - EXIT INT TERM

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$TARGET" > "$TARGET.sha256"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$TARGET" > "$TARGET.sha256"
else
  echo "ferramenta SHA-256 ausente" >&2
  exit 1
fi
chmod 600 "$TARGET" "$TARGET.sha256" 2>/dev/null || true
printf '%s\n' "$TARGET"
