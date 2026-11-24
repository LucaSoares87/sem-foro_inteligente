#!/usr/bin/env sh
set -eu

if [ "$#" -lt 2 ]; then
  echo "uso: $0 BACKUP.dump BANCO_DESTINO" >&2
  exit 2
fi

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
BACKUP=$1
TARGET_DB=$2

case "$TARGET_DB" in
  *[!A-Za-z0-9_]*|'') echo "nome de banco destino inválido" >&2; exit 2 ;;
esac
[ -f "$BACKUP" ] || { echo "backup não encontrado" >&2; exit 2; }

if [ -f "$BACKUP.sha256" ]; then
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$(dirname "$BACKUP")" && sha256sum -c "$(basename "$BACKUP").sha256")
  elif command -v shasum >/dev/null 2>&1; then
    expected=$(awk '{print $1}' "$BACKUP.sha256")
    actual=$(shasum -a 256 "$BACKUP" | awk '{print $1}')
    [ "$expected" = "$actual" ] || { echo "checksum inválido" >&2; exit 1; }
  else
    echo "ferramenta SHA-256 ausente" >&2
    exit 1
  fi
fi

CURRENT_DB=$(docker compose exec -T postgres sh -ceu 'printf "%s" "$POSTGRES_DB"')
if [ "$TARGET_DB" = "$CURRENT_DB" ] && [ "${ALLOW_DESTRUCTIVE_RESTORE:-NO}" != "YES" ]; then
  echo "restore sobre o banco ativo recusado; use banco alternativo ou ALLOW_DESTRUCTIVE_RESTORE=YES" >&2
  exit 1
fi

EXISTS=$(docker compose exec -T -e TARGET_DB="$TARGET_DB" postgres sh -ceu   'psql -U "$POSTGRES_USER" -d postgres -v target="$TARGET_DB" -Atqc "SELECT 1 FROM pg_database WHERE datname = :'\''target'\''"')
if [ "$EXISTS" = "1" ]; then
  if [ "${RESTORE_REPLACE:-NO}" != "YES" ]; then
    echo "banco destino já existe; defina RESTORE_REPLACE=YES para substituí-lo" >&2
    exit 1
  fi
  docker compose exec -T -e TARGET_DB="$TARGET_DB" postgres sh -ceu     'psql -U "$POSTGRES_USER" -d postgres -v target="$TARGET_DB" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'\''target'\'' AND pid <> pg_backend_pid();" >/dev/null'
  docker compose exec -T -e TARGET_DB="$TARGET_DB" postgres sh -ceu 'dropdb -U "$POSTGRES_USER" "$TARGET_DB"'
fi

docker compose exec -T -e TARGET_DB="$TARGET_DB" postgres sh -ceu 'createdb -U "$POSTGRES_USER" "$TARGET_DB"'
cat "$BACKUP" | docker compose exec -T -e TARGET_DB="$TARGET_DB" postgres sh -ceu   'pg_restore -U "$POSTGRES_USER" -d "$TARGET_DB" --no-owner --no-privileges --exit-on-error'
REVISION=$(docker compose exec -T -e TARGET_DB="$TARGET_DB" postgres sh -ceu   'psql -U "$POSTGRES_USER" -d "$TARGET_DB" -Atqc "SELECT version_num FROM alembic_version"')
[ -n "$REVISION" ] || { echo "restore sem revisão Alembic" >&2; exit 1; }
printf 'restore_validado banco=%s revision=%s\n' "$TARGET_DB" "$REVISION"
