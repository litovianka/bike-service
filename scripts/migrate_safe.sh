#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [ ! -f "manage.py" ]; then
  echo "ERROR: manage.py not found in $PROJECT_DIR"
  exit 1
fi

if [ -z "${VIRTUAL_ENV:-}" ]; then
  echo "ERROR: venv is not activated. Run: source venv/bin/activate"
  exit 1
fi

bash scripts/pre_migrate_backup.sh
python3 manage.py makemigrations
python3 manage.py migrate
echo "Done"
