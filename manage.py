#!/usr/bin/env python3
import os
import sys
from pathlib import Path


def _strip_quotes(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
        return v[1:-1]
    return v


def _load_dotenv_simple():
    """
    Jednoduché načítanie .env bez python-dotenv.
    Podporuje KEY=VALUE a ignoruje prázdne riadky a komentáre.
    """
    base_dir = Path(__file__).resolve().parent
    env_path = base_dir / ".env"
    if not env_path.exists():
        return

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = _strip_quotes(value)

            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        return


def main():
    _load_dotenv_simple()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bikelog.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("Django sa nepodarilo importovať. Skontroluj venv a závislosti.") from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()