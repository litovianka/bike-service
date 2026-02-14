# scripts/pre_migrate_backup.sh
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p backups
TS="$(date +"%Y%m%d_%H%M%S")"
OUT="backups/backup_${TS}.zip"

FILES=()

if [ -f "db.sqlite3" ]; then
  FILES+=("db.sqlite3")
fi

if [ -f "manage.py" ]; then
  FILES+=("manage.py")
fi

while IFS= read -r -d '' f; do
  FILES+=("${f#./}")
done < <(
  find . \
    -type f \
    \( -path "*/migrations/*.py" -o -path "*/migrations/*.json" -o -path "*/migrations/*.yaml" -o -path "*/migrations/*.yml" \) \
    -not -path "*/migrations/__pycache__/*" \
    -print0
)

if [ "${#FILES[@]}" -eq 0 ]; then
  echo "Nothing to back up."
  exit 0
fi

zip -q -r "$OUT" "${FILES[@]}"
echo "Backup created: $OUT"