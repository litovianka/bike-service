import os
from pathlib import Path


def _load_dotenv():
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    base_dir = Path(__file__).resolve().parent.parent
    env_path = base_dir / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)


_load_dotenv()

from django.core.wsgi import get_wsgi_application  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bikelog.settings")

application = get_wsgi_application()